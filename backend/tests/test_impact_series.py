"""시계열 변환 테스트: `*` 채움값, 칸 누락 시각 제외."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.impact.series import load_series
from app.impact.store import merge_rows_into_parquet


def _setup(proc: Path) -> None:
    merge_rows_into_parquet("cells", [
        {"cell_id": "A1", "lat": 37.5, "lon": 127.1, "zone": "park"},
        {"cell_id": "A2", "lat": 37.5, "lon": 127.1, "zone": "park"},
        {"cell_id": "B1", "lat": 37.5, "lon": 127.1, "zone": "ring1"},
    ], proc)
    def r(h: int, c: str, v: float | None, s: bool = False) -> dict:
        return {"date": "2025-10-18", "hour": h, "cell_id": c, "kind": "native", "value": v, "suppressed": s}
    merge_rows_into_parquet("pop_hourly", [
        r(19, "A1", 10.0), r(19, "A2", None, True), r(19, "B1", 5.0),   # 19시: park에 `*` 하나
        r(20, "A1", 20.0), r(20, "B1", 6.0),                             # 20시: park의 A2 행 없음
        r(21, "A1", 1.0), r(21, "A2", None, False), r(21, "B1", 7.0),    # 21시: A2 빈 값(결측)
    ], proc)


def test_suppressed_fill_changes_sum(tmp_path: Path) -> None:
    _setup(tmp_path)
    t = datetime(2025, 10, 18, 19)
    assert load_series(tmp_path, suppressed_fill=0.0)["park"][t] == 10.0
    assert load_series(tmp_path, suppressed_fill=3.0)["park"][t] == 13.0
    assert load_series(tmp_path)["ring1"][t] == 5.0


def test_incomplete_hours_are_dropped_by_default(tmp_path: Path) -> None:
    _setup(tmp_path)
    park = load_series(tmp_path)["park"]
    assert datetime(2025, 10, 18, 20) not in park  # 칸 누락
    assert datetime(2025, 10, 18, 21) not in park  # 결측 값
    assert datetime(2025, 10, 18, 20) in load_series(tmp_path)["ring1"]  # 다른 구역은 영향 없음


def test_full_coverage_can_be_disabled(tmp_path: Path) -> None:
    _setup(tmp_path)
    park = load_series(tmp_path, require_full_coverage=False)["park"]
    assert park[datetime(2025, 10, 18, 20)] == 20.0
