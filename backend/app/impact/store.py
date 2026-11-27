"""Parquet 표 저장소. 같은 명령을 다시 실행해도 중복이 생기지 않게 키 기준으로 합친다.

Parquet = 열 단위로 압축하는 파일 형식. DuckDB = 파일을 SQL로 바로 읽는 내장 DB(서버 불필요).
표 구조는 우리가 정한 것이고(원본 열 이름과 무관), 원본 → 이 구조로의 변환은 population.py 등이 맡는다.
parking_hourly·weather_hourly는 원본 열을 확인한 뒤에 추가한다.
"""

from __future__ import annotations

import csv
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import duckdb

from app.impact import config

# 표 이름 → (열 이름과 DuckDB 타입 목록, 중복 판단 키)
SCHEMAS: dict[str, tuple[list[tuple[str, str]], tuple[str, ...]]] = {
    "cells": (
        [("cell_id", "VARCHAR"), ("lat", "DOUBLE"), ("lon", "DOUBLE"), ("zone", "VARCHAR")],
        ("cell_id",),
    ),
    "pop_hourly": (
        [("date", "DATE"), ("hour", "INTEGER"), ("cell_id", "VARCHAR"), ("kind", "VARCHAR"),
         ("value", "DOUBLE"), ("suppressed", "BOOLEAN")],
        ("date", "hour", "cell_id", "kind"),
    ),
    "events": (
        [("event_id", "VARCHAR"), ("name", "VARCHAR"), ("venue", "VARCHAR"), ("date", "DATE"),
         ("start_time", "VARCHAR"), ("end_time", "VARCHAR"), ("source", "VARCHAR"),
         ("lat", "DOUBLE"), ("lon", "DOUBLE")],
        ("event_id",),
    ),
}


def table_path(table: str, processed_dir: Path | None = None) -> Path:
    return (processed_dir or config.PROCESSED_DIR) / f"{table}.parquet"


def _q(path: Path | str) -> str:
    """SQL 문자열 리터럴용 따옴표 이스케이프(경로는 우리 설정에서 오지만 안전하게)."""
    return str(path).replace("'", "''")


def _columns_sql(table: str) -> str:
    cols, _ = SCHEMAS[table]
    return "{" + ", ".join(f"'{n}': '{t}'" for n, t in cols) + "}"


def merge_csv_into_parquet(table: str, csv_path: Path, processed_dir: Path | None = None) -> int:
    """CSV(우리 표 구조, 헤더 포함)를 표 Parquet에 합치고 합친 뒤 총 행 수를 돌려준다.

    키가 같은 행은 새 CSV 쪽이 이긴다(최신 수집 결과로 덮어쓰기). 그래서 재실행해도 행이 늘지 않는다.
    임시 파일에 쓴 뒤 교체해서, 중간에 실패해도 기존 표가 깨지지 않는다.
    """
    cols, keys = SCHEMAS[table]
    names = ", ".join(n for n, _ in cols)
    dest = table_path(table, processed_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    key_sql = ", ".join(keys)
    new_sql = f"SELECT {names}, 1 AS _o FROM read_csv('{_q(csv_path)}', header=true, columns={_columns_sql(table)})"
    parts = [new_sql]
    if dest.exists():
        parts.append(f"SELECT {names}, 0 AS _o FROM read_parquet('{_q(dest)}')")
    union = " UNION ALL ".join(parts)
    query = (
        f"SELECT {names} FROM ({union}) "
        f"QUALIFY row_number() OVER (PARTITION BY {key_sql} ORDER BY _o DESC) = 1 "
        f"ORDER BY {key_sql}"
    )
    fd, tmp_name = tempfile.mkstemp(suffix=".parquet", dir=dest.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    con = duckdb.connect()
    try:
        con.execute(f"COPY ({query}) TO '{_q(tmp)}' (FORMAT PARQUET)")
        total = con.execute(f"SELECT count(*) FROM read_parquet('{_q(tmp)}')").fetchone()[0]
        tmp.replace(dest)
        return int(total)
    finally:
        con.close()
        tmp.unlink(missing_ok=True)


def write_rows_csv(table: str, rows: Iterable[Mapping[str, Any]], csv_path: Path) -> int:
    """행(dict) 목록을 우리 표 구조의 CSV로 쓴다. 빈 값은 빈 칸(NULL), bool은 true/false."""
    cols, _ = SCHEMAS[table]
    n = 0
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([c for c, _ in cols])
        for row in rows:
            w.writerow([_cell(row.get(c)) for c, _ in cols])
            n += 1
    return n


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def merge_rows_into_parquet(table: str, rows: Iterable[Mapping[str, Any]], processed_dir: Path | None = None) -> int:
    """작은 표(cells, events)용: 행 목록을 바로 합친다. 총 행 수를 돌려준다."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / f"{table}.csv"
        write_rows_csv(table, rows, p)
        return merge_csv_into_parquet(table, p, processed_dir)


def read_table(table: str, processed_dir: Path | None = None) -> list[dict[str, Any]]:
    """표 전체를 dict 목록으로 읽는다(작은 표·테스트용). 파일이 없으면 빈 목록."""
    path = table_path(table, processed_dir)
    if not path.exists():
        return []
    con = duckdb.connect()
    try:
        cur = con.execute(f"SELECT * FROM read_parquet('{_q(path)}')")
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    finally:
        con.close()
