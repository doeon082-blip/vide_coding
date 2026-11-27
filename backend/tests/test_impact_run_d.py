"""D단계 실행기 종단 테스트: 가짜 Parquet 표만으로 보고서까지 만든다."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.impact.baseline import excess_profile
from app.impact.run_d import load_events, load_holidays, render_svg, run
from app.impact.store import merge_rows_into_parquet

SAT_EVENTS = [date(2025, 9, 20), date(2025, 10, 11), date(2025, 10, 25), date(2025, 11, 8), date(2025, 11, 22)]


def _build(proc: Path, boost: float) -> None:
    merge_rows_into_parquet("cells", [
        {"cell_id": "P1", "lat": 1, "lon": 1, "zone": "park"},
        {"cell_id": "R1", "lat": 1, "lon": 1, "zone": "ring1"},
        {"cell_id": "R2", "lat": 1, "lon": 1, "zone": "ring2"},
    ], proc)
    rows = []
    d = date(2025, 8, 1)
    while d <= date(2025, 12, 31):
        for h in range(24):
            for cell in ("P1", "R1", "R2"):
                v = 100.0 + (boost if cell == "P1" and d in SAT_EVENTS and 16 <= h <= 22 else 0.0)
                rows.append({"date": d.isoformat(), "hour": h, "cell_id": cell, "kind": "native", "value": v, "suppressed": False})
        d += timedelta(days=1)
    merge_rows_into_parquet("pop_hourly", rows, proc)
    merge_rows_into_parquet("events", [
        {"event_id": f"e{i}", "name": f"공연{i}", "venue": "올림픽홀", "date": d.isoformat(), "start_time": "19:00",
         "end_time": None, "source": "kspo", "lat": None, "lon": None} for i, d in enumerate(SAT_EVENTS)
    ] + [{"event_id": "x", "name": "공원 밖 행사", "venue": "다른곳", "date": "2025-10-18", "start_time": "19:00",
          "end_time": None, "source": "seoul", "lat": None, "lon": None}], proc)
    (proc / "holidays.json").write_text(json.dumps(["2025-10-03", "2025-10-04", "2025-10-05"]), encoding="utf-8")


def test_end_to_end_pass_and_report_files(tmp_path: Path) -> None:
    proc, rep = tmp_path / "proc", tmp_path / "rep"
    _build(proc, 10.0)
    v = run(proc, rep)
    assert v.passed and v.n_judgeable == 5 and v.n_pass == 5
    md = (rep / "effect.md").read_text(encoding="utf-8")
    assert "## 결과: 통과" in md and "공연0" in md and "공원 밖 행사" not in md
    assert "판정에 영향 없음" in md and "+0h" in md
    assert (rep / "effect.svg").read_text(encoding="utf-8").startswith("<svg")


def test_end_to_end_fail_is_reported_not_hidden(tmp_path: Path) -> None:
    proc, rep = tmp_path / "proc", tmp_path / "rep"
    _build(proc, 0.0)
    v = run(proc, rep)
    assert v.passed is False
    assert "통과하지 못함" in (rep / "effect.md").read_text(encoding="utf-8")


def test_missing_or_empty_holidays_stop_the_run(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_holidays(tmp_path / "nope.json")
    p = tmp_path / "h.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_holidays(p)


def test_load_events_splits_start_less_and_filters_source(tmp_path: Path) -> None:
    merge_rows_into_parquet("events", [
        {"event_id": "a", "name": "A", "venue": "v", "date": "2025-10-18", "start_time": "19:00", "end_time": None,
         "source": "kspo", "lat": None, "lon": None},
        {"event_id": "b", "name": "B", "venue": "v", "date": "2025-10-19", "start_time": None, "end_time": None,
         "source": "kspo", "lat": None, "lon": None},
        {"event_id": "c", "name": "C", "venue": "v", "date": "2025-10-20", "start_time": "18:00", "end_time": None,
         "source": "seoul", "lat": None, "lon": None},
    ], tmp_path)
    events, dates = load_events(tmp_path)
    assert [e.event_id for e in events] == ["a"] and dates == {date(2025, 10, 18), date(2025, 10, 19)}


def test_excess_profile_and_svg() -> None:
    base = datetime(2025, 10, 18)
    series = {base + timedelta(days=dd, hours=h): 100.0 for dd in range(-28, 29, 7) for h in range(24)}
    series[datetime(2025, 10, 18, 19)] = 130.0
    prof = excess_profile(series, datetime(2025, 10, 18, 19), set())
    assert prof[0] == 30.0 and prof[-1] == 0.0 and len(prof) == 7
    svg = render_svg({"park": {k: float(k) for k in range(-3, 4)}})
    assert "<polyline" in svg and svg.endswith("</svg>")
