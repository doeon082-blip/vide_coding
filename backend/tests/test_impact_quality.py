"""품질 보고서 테스트: 가짜 표로 핵심 수치가 보고서에 나오는지 본다."""

from __future__ import annotations

from pathlib import Path

from app.impact.quality import build_quality_report, write_quality_report
from app.impact.store import merge_rows_into_parquet


def _pop(d: str, h: int, c: str, v: float | None, s: bool = False) -> dict:
    return {"date": d, "hour": h, "cell_id": c, "kind": "native", "value": v, "suppressed": s}


def test_report_without_any_tables_says_missing(tmp_path: Path) -> None:
    text = build_quality_report(tmp_path)
    assert "cells 표 없음" in text and "events 표 없음" in text and "이 데이터로 할 수 없는 것" in text


def test_report_numbers(tmp_path: Path) -> None:
    merge_rows_into_parquet("cells", [
        {"cell_id": "A1", "lat": 1, "lon": 1, "zone": "park"},
        {"cell_id": "A2", "lat": 1, "lon": 1, "zone": "park"},
    ], tmp_path)
    merge_rows_into_parquet("pop_hourly", [
        _pop("2025-10-01", 19, "A1", 5.0), _pop("2025-10-01", 19, "A2", None, True),
        _pop("2025-10-01", 20, "A1", 6.0),  # 20시는 A2 누락
        _pop("2025-10-03", 19, "A1", 7.0), _pop("2025-10-03", 19, "A2", 1.0),  # 10/2 빠짐
    ], tmp_path)
    merge_rows_into_parquet("events", [
        {"event_id": "e1", "name": "공연A", "venue": "올림픽홀", "date": "2025-10-18", "start_time": "19:00",
         "end_time": None, "source": "kspo", "lat": None, "lon": None},
        {"event_id": "e2", "name": "공연B", "venue": "올림픽홀", "date": "2025-10-18", "start_time": None,
         "end_time": None, "source": "kspo", "lat": None, "lon": None},
        {"event_id": "e3", "name": "공연A", "venue": "올림픽홀", "date": "2025-10-18", "start_time": "19:00",
         "end_time": None, "source": "seoul", "lat": None, "lon": None},
    ], tmp_path)
    text = build_quality_report(tmp_path)
    assert "| park | 2 |" in text
    assert "빠진 날짜 (native): 2025-10-01 ~ 2025-10-03 중 1일" in text and "2025-10-02" in text
    assert "시작 시각이 없는 행사: **1건**" in text
    assert "출처 간 중복 의심): **1건**" in text
    assert "같은 날 행사가 여러 건인 날: **1일**" in text
    assert "| park | native | 1 | 3 |" in text  # 20시 한 시각이 칸 일부 누락, 전체 3시각
    assert "parking_hourly: 표 없음" in text


def test_write_report_creates_file(tmp_path: Path) -> None:
    path = write_quality_report(tmp_path / "proc", tmp_path / "report")
    assert path.name == "quality.md" and path.read_text(encoding="utf-8").startswith("# 데이터 품질 보고서")
