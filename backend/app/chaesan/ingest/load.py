"""파일 30종 → SQLite 적재 (로컬 전용).

실행: `uv run python -m app.chaesan.ingest.load` (backend/ 에서)
- 입력: backend/data/raw/files/<번호>.csv
- 출력: backend/data/chaesan.sqlite (임시 파일에 다 만든 뒤 한 번에 바꿔 넣어, 실패해도 기존 DB가 깨지지 않는다)

무결성 장치
- 파일 헤더가 specs.py와 다르면 멈춘다. 행마다 열 개수가 다르면 멈춘다. expected_rows가 있으면 행 수를 대조한다.
- 모든 표에 `_row`(원본 파일의 데이터 행 번호, 1부터)를 둬서 답변 근거를 원본 행까지 되짚을 수 있게 한다.
- 변환하지 못한 값은 버리지 않고 `<열>_raw`에 남기고, 그 개수를 meta_columns에 적는다.
- meta_load에 파일 SHA-256을 적어 어떤 원본으로 만든 DB인지 남긴다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import logging
import os
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from app.chaesan.ingest import convert
from app.chaesan.ingest.aggregate import build_aggregates
from app.chaesan.ingest.specs import SPECS, Col, FileSpec

logger = logging.getLogger(__name__)

BACKEND_DIR: Final = Path(__file__).resolve().parents[3]
RAW_DIR: Final = BACKEND_DIR / "data" / "raw" / "files"
DB_PATH: Final = BACKEND_DIR / "data" / "chaesan.sqlite"

# 한 칸 → (만들 열 이름, SQL 타입, 값 꺼내기) 목록. 범위 칸은 두 열로 나뉜다.
type Out = tuple[str, str, Callable[[str], convert.Converted]]

_SIMPLE: Final[dict[str, tuple[str, Callable[[str], convert.Converted]]]] = {
    "text": ("TEXT", convert.text),
    "int": ("INTEGER", convert.integer),
    "date": ("TEXT", convert.iso_date),
    "datetime": ("TEXT", convert.iso_datetime),
    "yyyymmdd": ("TEXT", convert.yyyymmdd),
    "month_ko": ("INTEGER", convert.month_ko),
    "hour_of_time": ("INTEGER", convert.hour_of_time),
}


class LoadError(RuntimeError):
    """원본이 명세와 맞지 않아 적재를 멈췄다. 메시지에 파일 번호와 이유를 담는다."""


def _outputs(col: Col) -> list[Out]:
    if col.kind in _SIMPLE:
        sql_type, fn = _SIMPLE[col.kind]
        return [(col.en, sql_type, fn)]
    if col.kind == "date_range":
        return [
            (f"{col.en}_start", "TEXT", lambda v: convert.split_date_range(v)[0]),
            (f"{col.en}_end", "TEXT", lambda v: convert.split_date_range(v)[1]),
        ]
    if col.kind == "time_range":
        return [
            (f"{col.en}_start", "TEXT", lambda v: convert.split_time_range(v)[0]),
            (f"{col.en}_end", "TEXT", lambda v: convert.split_time_range(v)[1]),
        ]
    if col.kind == "date_in_text":
        return [(col.en, "TEXT", convert.text), (f"{col.en}_date", "TEXT", convert.first_date)]
    raise LoadError(f"알 수 없는 값 종류: {col.kind}")


@dataclass(slots=True)
class RawFile:
    encoding: str
    sha256: str
    header: list[str]
    rows: list[list[str]]


def read_csv(path: Path) -> RawFile:
    """인코딩을 엄격하게 판별해 읽는다: BOM이 있으면 utf-8-sig, 아니면 utf-8 → cp949 순서로 '오류 없이' 풀리는 것.
    둘 다 실패하면 멈춘다(깨진 글자를 조용히 넣지 않기 위해 errors='replace'를 쓰지 않는다)."""
    data = path.read_bytes()
    candidates = ("utf-8-sig",) if data.startswith(b"\xef\xbb\xbf") else ("utf-8", "cp949")
    for enc in candidates:
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            continue
        rows = list(csv.reader(io.StringIO(text, newline="")))
        if not rows:
            raise LoadError(f"{path.name}: 빈 파일")
        return RawFile(enc, hashlib.sha256(data).hexdigest(), rows[0], rows[1:])
    raise LoadError(f"{path.name}: 인코딩 판별 실패({', '.join(candidates)})")


def _check(spec: FileSpec, raw: RawFile) -> None:
    expected = [c.ko for c in spec.cols]
    if [h.strip() for h in raw.header] != expected:
        raise LoadError(f"{spec.id}: 헤더가 명세와 다름\n  파일: {raw.header}\n  명세: {expected}")
    bad = [i + 1 for i, r in enumerate(raw.rows) if len(r) != len(expected)]
    if bad:
        raise LoadError(f"{spec.id}: 열 개수가 다른 행 {len(bad)}개(처음: {bad[:5]})")
    if spec.expected_rows is not None and len(raw.rows) != spec.expected_rows:
        raise LoadError(f"{spec.id}: 행 수 {len(raw.rows)} ≠ 기대 {spec.expected_rows}")


def _q(name: str) -> str:
    """SQL 식별자 따옴표. 이름은 specs.py에서만 오지만 예약어(year, month 등)와 겹쳐도 안전하게."""
    return '"' + name.replace('"', '""') + '"'


def load_file(con: sqlite3.Connection, spec: FileSpec, path: Path) -> dict[str, int]:
    """파일 하나를 t_<번호> 표로 적재하고 meta 표에 기록한다. 반환: 열별 변환 실패 수."""
    raw = read_csv(path)
    _check(spec, raw)
    # (원본 칸 위치, 원본 열 명세, 만들 열) — 위치를 미리 잡아 두어 행마다 찾지 않는다
    plan = [(src, col, out) for src, col in enumerate(spec.cols) for out in _outputs(col)]
    values: list[list[convert.Value]] = []
    raws: list[list[str | None]] = []
    for r in raw.rows:
        pairs = [fn(r[src]) for src, _, (_, _, fn) in plan]
        values.append([v for v, _ in pairs])
        raws.append([rv for _, rv in pairs])
    raw_counts = {plan[i][2][0]: sum(1 for rw in raws if rw[i] is not None) for i in range(len(plan))}
    raw_cols = [i for i, (_, _, out) in enumerate(plan) if raw_counts[out[0]]]

    names = ["_row", *(out[0] for _, _, out in plan), *(f"{plan[i][2][0]}_raw" for i in raw_cols)]
    types = ["INTEGER PRIMARY KEY", *(out[1] for _, _, out in plan), *("TEXT" for _ in raw_cols)]
    con.execute(f"DROP TABLE IF EXISTS {_q(spec.table)}")
    con.execute(f"CREATE TABLE {_q(spec.table)} ({', '.join(f'{_q(n)} {t}' for n, t in zip(names, types, strict=True))})")
    marks = ", ".join("?" * len(names))
    con.executemany(
        f"INSERT INTO {_q(spec.table)} VALUES ({marks})",
        ([n, *vals, *(rws[i] for i in raw_cols)] for n, (vals, rws) in enumerate(zip(values, raws, strict=True), start=1)),
    )
    con.execute(
        "INSERT INTO meta_load VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (spec.table, spec.id, spec.title, path.name, raw.encoding, raw.sha256, len(raw.rows), int(spec.local_only)),
    )
    for pos, (_, col, out) in enumerate(plan):
        nulls = sum(1 for v in values if v[pos] is None)
        con.execute(
            "INSERT INTO meta_columns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (spec.table, pos + 1, out[0], col.ko, col.kind, out[1], nulls, raw_counts[out[0]]),
        )
    return {k: v for k, v in raw_counts.items() if v}


_META: Final = """
CREATE TABLE meta_load (
  table_name TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, title TEXT NOT NULL, file_name TEXT NOT NULL,
  encoding TEXT NOT NULL, sha256 TEXT NOT NULL, rows INTEGER NOT NULL, local_only INTEGER NOT NULL
);
CREATE TABLE meta_columns (
  table_name TEXT NOT NULL, position INTEGER NOT NULL, column_name TEXT NOT NULL, ko_name TEXT NOT NULL,
  kind TEXT NOT NULL, sql_type TEXT NOT NULL, null_count INTEGER NOT NULL, raw_count INTEGER NOT NULL,
  PRIMARY KEY (table_name, column_name)
);
CREATE TABLE meta_build (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def iter_inputs(raw_dir: Path, specs: Sequence[FileSpec]) -> Iterator[tuple[FileSpec, Path]]:
    missing = [s.id for s in specs if not (raw_dir / f"{s.id}.csv").is_file()]
    if missing:
        raise LoadError(f"없는 파일: {missing}")
    for spec in specs:
        yield spec, raw_dir / f"{spec.id}.csv"


def build(raw_dir: Path = RAW_DIR, out_path: Path = DB_PATH, specs: Sequence[FileSpec] = SPECS) -> dict[str, dict[str, int]]:
    """적재. 반환: 표별 원래 값 보존 수(보고용). specs는 테스트에서 일부만 적재할 때 바꾼다."""
    tmp = out_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    report: dict[str, dict[str, int]] = {}
    con = sqlite3.connect(tmp)
    try:
        con.executescript(_META)
        for spec, path in iter_inputs(raw_dir, specs):
            report[spec.table] = load_file(con, spec, path)
            logger.info("loaded %s", spec.table)
        build_aggregates(con)
        con.execute("INSERT INTO meta_build VALUES ('built_at_utc', ?)", (datetime.now(UTC).isoformat(timespec="seconds"),))
        con.commit()
        if (problem := con.execute("PRAGMA integrity_check").fetchone()[0]) != "ok":
            raise LoadError(f"SQLite 무결성 검사 실패: {problem}")
    except BaseException:
        con.close()
        tmp.unlink(missing_ok=True)
        raise
    con.close()
    os.replace(tmp, out_path)  # 다 만든 뒤에만 바꿔 넣는다
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="채산 파일 30종을 SQLite로 적재한다.")
    parser.add_argument("--raw", type=Path, default=RAW_DIR)
    parser.add_argument("--out", type=Path, default=DB_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    report = build(args.raw, args.out)
    for table, fails in report.items():
        if fails:
            print(f"{table}: 원래 값 보존 {fails}")
    print(f"완료: {args.out}")


if __name__ == "__main__":
    main()
