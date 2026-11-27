"""zip 스트리밍, `*` 처리, Parquet 중복 방지 테스트(작은 가짜 데이터)."""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import pytest

from app.impact.population import ColumnMap, ingest_population, iter_zip_csv, list_zip_members
from app.impact.store import merge_csv_into_parquet, merge_rows_into_parquet, read_table

CMAP = ColumnMap(date_col="일자", hour_col="시간", cell_col="격자", value_cols=("합계",))
ZONES = {"A1": "park", "B2": "ring1"}


def _make_zip(tmp_path: Path, text: str, encoding: str = "cp949") -> Path:
    zp = tmp_path / "fake.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("data.csv", text.encode(encoding))
    return zp


CSV = (
    "일자,시간,격자,합계\n"
    "20251018,19,A1,100.5\n"
    "20251018,19,B2,*\n"
    "20251018,19,Z9,7\n"  # 구역 밖 칸
    "20251018,xx,A1,5\n"  # 시 해석 불가
    "20251018,20,A1,N/A\n"  # 사람 수 해석 불가
    "20251018,21,A1,\n"  # 빈 값(결측)
)


def test_zip_listing_and_streaming_with_cp949(tmp_path: Path) -> None:
    zp = _make_zip(tmp_path, CSV)
    assert list_zip_members(zp) == [("data.csv", len(CSV.encode("cp949")))]
    rows = list(iter_zip_csv(zp, "data.csv", "cp949"))
    assert len(rows) == 6 and rows[0]["격자"] == "A1"


def test_ingest_keeps_zone_cells_and_marks_suppressed(tmp_path: Path) -> None:
    zp = _make_zip(tmp_path, CSV)
    out = tmp_path / "pop.csv"
    st = ingest_population(iter_zip_csv(zp, "data.csv", "cp949"), CMAP, ZONES, "native", out)
    assert (st.rows_read, st.rows_kept, st.rows_bad, st.suppressed) == (6, 2, 3, 1)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[1] == "2025-10-18,19,A1,native,100.5,false"
    assert lines[2] == "2025-10-18,19,B2,native,,true"  # `*`는 빈 값 + suppressed


def test_multiple_value_cols_sum_and_star_wins(tmp_path: Path) -> None:
    cmap = ColumnMap("일자", "시간", "격자", ("남", "여"))
    text = "일자,시간,격자,남,여\n20251018,19,A1,10,5.5\n20251018,20,A1,*,5\n"
    zp = _make_zip(tmp_path, text)
    out = tmp_path / "pop.csv"
    ingest_population(iter_zip_csv(zp, "data.csv", "cp949"), cmap, ZONES, "native", out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[1].endswith("15.5,false") and lines[2].endswith(",,true")


def test_missing_column_fails_loudly(tmp_path: Path) -> None:
    zp = _make_zip(tmp_path, "일자,시간,격자,인구\n20251018,19,A1,1\n")
    with pytest.raises(ValueError, match="원본에 없는 열"):
        ingest_population(iter_zip_csv(zp, "data.csv", "cp949"), CMAP, ZONES, "native", tmp_path / "o.csv")


def test_rerun_does_not_duplicate_and_latest_wins(tmp_path: Path) -> None:
    proc = tmp_path / "processed"
    csv1 = tmp_path / "a.csv"
    csv1.write_text("date,hour,cell_id,kind,value,suppressed\n2025-10-18,19,A1,native,100,false\n"
                    "2025-10-18,19,B2,native,,true\n", encoding="utf-8")
    assert merge_csv_into_parquet("pop_hourly", csv1, proc) == 2
    assert merge_csv_into_parquet("pop_hourly", csv1, proc) == 2  # 같은 파일 재실행
    csv2 = tmp_path / "b.csv"
    csv2.write_text("date,hour,cell_id,kind,value,suppressed\n2025-10-18,19,A1,native,120,false\n"
                    "2025-10-18,20,A1,native,90,false\n", encoding="utf-8")
    assert merge_csv_into_parquet("pop_hourly", csv2, proc) == 3
    rows = {(r["date"], r["hour"], r["cell_id"]): r for r in read_table("pop_hourly", proc)}
    assert rows[(date(2025, 10, 18), 19, "A1")]["value"] == 120.0  # 새 값이 덮어씀
    assert rows[(date(2025, 10, 18), 19, "B2")]["suppressed"] is True
    assert rows[(date(2025, 10, 18), 19, "B2")]["value"] is None


def test_merge_rows_for_small_tables(tmp_path: Path) -> None:
    proc = tmp_path / "processed"
    cells = [{"cell_id": "A1", "lat": 37.5, "lon": 127.1, "zone": "park"}]
    assert merge_rows_into_parquet("cells", cells, proc) == 1
    assert merge_rows_into_parquet("cells", cells, proc) == 1
    ev = [{"event_id": "e1", "name": "콘서트, 앙코르", "venue": "올림픽홀", "date": "2025-10-18",
           "start_time": "19:00", "end_time": None, "source": "kspo", "lat": None, "lon": None}]
    assert merge_rows_into_parquet("events", ev, proc) == 1  # 쉼표 포함 이름도 안전
    got = read_table("events", proc)[0]
    assert got["name"] == "콘서트, 앙코르" and got["end_time"] is None and got["date"] == date(2025, 10, 18)
