"""적재(ingest) 테스트: 변환기, 명세 대조, 무결성 장치, 실제 데이터 결과."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from app.chaesan.ingest import convert
from app.chaesan.ingest.load import RAW_DIR, LoadError, build, read_csv
from app.chaesan.ingest.specs import SPEC_BY_ID, SPECS, FileSpec

# --------------------------------------------------------------------------- 변환기


@pytest.mark.parametrize(
    "fn, raw, expected",
    [
        (convert.iso_date, "2024-07-01", ("2024-07-01", None)),
        (convert.iso_date, "1990-01-01", (None, "1990-01-01")),  # 기본값 = 날짜 없음, 원래 값은 남긴다
        (convert.iso_date, "9999-12-31", ("9999-12-31", None)),  # 운영 중(종료일 없음)이라는 뜻이 있다
        (convert.iso_date, "2024-02-30", (None, "2024-02-30")),
        (convert.iso_date, "", (None, None)),
        (convert.iso_datetime, "2024-07-01 19:45", ("2024-07-01 19:45:00", None)),
        (convert.integer, "1,234", (1234, None)),
        (convert.integer, "약 10", (None, "약 10")),
        (convert.yyyymmdd, "20120816", ("2012-08-16", None)),
        (convert.yyyymmdd, "201200820", (None, "201200820")),  # 15160326의 자리 수 틀린 이름
        (convert.month_ko, "01월", (1, None)),
        (convert.hour_of_time, "17:08:12", (17, None)),
        (convert.first_date, "2008-12-13(토) 7:00 / 2008-12-14(일)", ("2008-12-13", None)),
        (convert.first_date, "2009- 3- 1(일) 18:00", ("2009-03-01", None)),  # 0 없이·공백 낀 날짜
        (convert.first_date, "12- 20(금)", (None, "12- 20(금)")),  # 연도 없음
    ],
)
def test_converters(fn: convert.Converter, raw: str, expected: convert.Converted) -> None:
    assert fn(raw) == expected


def test_ranges() -> None:
    assert convert.split_date_range("2026-01-01~9999-12-31") == (("2026-01-01", None), ("9999-12-31", None))
    assert convert.split_date_range("1990-01-01 00:00:00~2025-06-01 00:00:00") == ((None, "1990-01-01 00:00:00"), ("2025-06-01", None))
    assert convert.split_time_range("9:00-9:50") == (("09:00", None), ("09:50", None))
    assert convert.split_time_range("종일") == ((None, "종일"), (None, "종일"))


def test_specs_are_unique_and_snake_case() -> None:
    assert len(SPECS) == 30 and len(SPEC_BY_ID) == 30
    for s in SPECS:
        ens = [c.en for c in s.cols]
        assert len(ens) == len(set(ens)), s.id
        assert all(e.isascii() and e == e.lower() and " " not in e for e in ens), s.id


# --------------------------------------------------------------------------- 무결성 장치 (작은 가짜 파일)

TENNIS = replace(SPEC_BY_ID["15133891"], expected_rows=None)
PARKING = replace(SPEC_BY_ID["15138735"], expected_rows=None)


def _write(d: Path, spec: FileSpec, lines: list[str], enc: str = "cp949") -> None:
    (d / f"{spec.id}.csv").write_bytes(("\n".join(lines) + "\n").encode(enc))


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    d = tmp_path / "raw"
    d.mkdir()
    _write(d, TENNIS, ["순번,구분,시작일,종료일,이용자수", "1,월회원,2023-01-01,2023-01-31,469", "2,일반,1990-01-01,2023-01-31,1200"])
    _write(d, PARKING, ["입차일,입차일시,출차일시", "2024-07-01,2024-07-01 08:10,2024-07-01 09:00", "2024-07-01,2024-07-01 08:30,2024-07-02 00:10"])
    return d


def test_build_small(raw: Path, tmp_path: Path) -> None:
    out = tmp_path / "x.sqlite"
    report = build(raw, out, (TENNIS, PARKING))
    assert report["t_15133891"] == {"start_date": 1}
    con = sqlite3.connect(out)
    assert con.execute("SELECT _row, start_date, start_date_raw FROM t_15133891 ORDER BY _row").fetchall() == [
        (1, "2023-01-01", None),
        (2, None, "1990-01-01"),
    ]
    assert con.execute("SELECT encoding, rows FROM meta_load WHERE table_name='t_15133891'").fetchone() == ("cp949", 2)
    rows = con.execute("SELECT date, hour, weekday, entries, exits FROM s_parking_hourly ORDER BY 1, 2").fetchall()
    assert rows == [("2024-07-01", 8, 0, 2, 0), ("2024-07-01", 9, 0, 0, 1), ("2024-07-02", 0, 1, 0, 1)]


def test_header_change_stops(raw: Path, tmp_path: Path) -> None:
    _write(raw, TENNIS, ["순번,구분,시작일,종료일,이용자 수", "1,월회원,2023-01-01,2023-01-31,469"])
    with pytest.raises(LoadError, match="헤더"):
        build(raw, tmp_path / "x.sqlite", (TENNIS, PARKING))


def test_ragged_row_and_row_count_stop(raw: Path, tmp_path: Path) -> None:
    _write(raw, TENNIS, ["순번,구분,시작일,종료일,이용자수", "1,월회원,2023-01-01,2023-01-31"])
    with pytest.raises(LoadError, match="열 개수"):
        build(raw, tmp_path / "x.sqlite", (TENNIS, PARKING))
    _write(raw, TENNIS, ["순번,구분,시작일,종료일,이용자수", "1,월회원,2023-01-01,2023-01-31,469"])
    with pytest.raises(LoadError, match="행 수"):
        build(raw, tmp_path / "x.sqlite", (replace(TENNIS, expected_rows=99), PARKING))


def test_undecodable_file_stops(raw: Path, tmp_path: Path) -> None:
    (raw / "15133891.csv").write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(LoadError, match="인코딩"):
        build(raw, tmp_path / "x.sqlite", (TENNIS, PARKING))


def test_failed_build_keeps_previous_db(raw: Path, tmp_path: Path) -> None:
    out = tmp_path / "x.sqlite"
    build(raw, out, (TENNIS, PARKING))
    before = out.read_bytes()
    (raw / "15138735.csv").unlink()
    with pytest.raises(LoadError, match="없는 파일"):
        build(raw, out, (TENNIS, PARKING))
    assert out.read_bytes() == before and not out.with_suffix(".tmp").exists()


# --------------------------------------------------------------------------- 실제 데이터 (있을 때만)

needs_data = pytest.mark.skipif(not all((RAW_DIR / f"{s.id}.csv").is_file() for s in SPECS), reason="원본 데이터 없음")


@needs_data
@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.id)
def test_real_headers_match_specs(spec: FileSpec) -> None:
    assert [h.strip() for h in read_csv(RAW_DIR / f"{spec.id}.csv").header] == [c.ko for c in spec.cols]


@needs_data
def test_real_build(tmp_path: Path) -> None:
    out = tmp_path / "real.sqlite"
    build(RAW_DIR, out)
    con = sqlite3.connect(out)
    assert con.execute("SELECT COUNT(*), SUM(rows) FROM meta_load").fetchone() == (30, 266920)
    assert con.execute("SELECT SUM(entries), SUM(exits) FROM s_parking_hourly").fetchone() == (215528, 215528)
    for (table,) in con.execute("SELECT table_name FROM meta_load").fetchall():
        n = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        assert n == con.execute("SELECT rows FROM meta_load WHERE table_name=?", (table,)).fetchone()[0]
