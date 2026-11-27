"""핵심 함수 4개(사용자 작성)의 테스트. 함수가 아직 NotImplementedError면 건너뛴다(skip)."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import pytest

from app.chaesan.core.answer import find_unsupported_numbers
from app.chaesan.core.sql_guard import SQL_ROW_LIMIT, SqlRejected, validate_sql
from app.chaesan.core.typo import edit_distance, to_jamo


def call(fn: Callable[..., Any], *args: Any) -> Any:
    try:
        return fn(*args)
    except NotImplementedError:
        pytest.skip(f"{fn.__name__}: 사용자 작성 대기")


# --------------------------------------------------------------------------- validate_sql

ALLOWED = {"t_15133891", "s_parking_hourly"}


def _limit(sql: str) -> int | None:
    m = re.search(r"\blimit\s+(\d+)\s*$", sql, re.IGNORECASE)
    return int(m.group(1)) if m else None


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT month, users FROM t_15133891",
        "select month, users from t_15133891 where users > 10;",
        "SELECT h.hour, COUNT(*) FROM s_parking_hourly h GROUP BY h.hour ORDER BY 2 DESC",
        "SELECT updated_at FROM t_15133891",  # 열 이름 속 'update'는 금지어가 아니다
    ],
)
def test_validate_sql_accepts_and_forces_limit(sql: str) -> None:
    out = call(validate_sql, sql, ALLOWED)
    assert _limit(out) is not None and _limit(out) <= SQL_ROW_LIMIT
    assert ";" not in out
    assert call(validate_sql, out, ALLOWED) == out  # 두 번 넣어도 같다


def test_validate_sql_caps_large_limit() -> None:
    out = call(validate_sql, "SELECT * FROM t_15133891 LIMIT 100000", ALLOWED)
    assert _limit(out) == SQL_ROW_LIMIT


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM t_15133891",
        "SELECT * FROM t_15133891; DROP TABLE t_15133891",
        "SELECT * FROM t_15138735",  # 허용 목록에 없는 큰 원본 표
        "SELECT * FROM t_15133891 JOIN t_15138735 USING (date)",
        "SELECT * FROM sqlite_master",
        "SELECT * FROM t_15133891 -- 주석",
        "SELECT * FROM t_15133891 /* x */",
        "PRAGMA table_info(t_15133891)",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "SELECT 1",
        "",
    ],
)
def test_validate_sql_rejects(sql: str) -> None:
    with pytest.raises(SqlRejected):
        call(validate_sql, sql, ALLOWED)


# --------------------------------------------------------------------------- find_unsupported_numbers


@pytest.mark.parametrize(
    ("answer", "rows", "expected"),
    [
        ("입출차는 215,528건이에요.", [{"n": 215528}], []),
        ("비율은 3.5%예요.", [{"r": 3.5}], []),
        ("7월에 120명이 이용했어요.", [{"month": 7, "users": 120}], []),
        ("2024년 7월 자료예요.", [{"date": "2024-07-01"}], []),
        ("130명이 이용했어요.", [{"users": 120}], ["130"]),
        ("215,529건", [{"n": 215528}], ["215,529"]),  # 쪼개서 215·529로 보면 놓친다
        ("1명, 1명, 9명", [{"x": True}], ["1", "9"]),  # bool은 숫자가 아니고, 중복은 한 번만
        ("숫자 없는 답", [], []),
    ],
)
def test_find_unsupported_numbers(answer: str, rows: list[dict[str, Any]], expected: list[str]) -> None:
    assert call(find_unsupported_numbers, answer, rows) == expected


# --------------------------------------------------------------------------- to_jamo / edit_distance


@pytest.mark.parametrize(
    ("text", "expected"),
    [("가", "ㄱㅏ"), ("한", "ㅎㅏㄴ"), ("수영장", "ㅅㅜㅇㅕㅇㅈㅏㅇ"), ("닭", "ㄷㅏㄺ"), ("a1 ", "a1 "), ("", "")],
)
def test_to_jamo(text: str, expected: str) -> None:
    assert call(to_jamo, text) == expected


@pytest.mark.parametrize(
    ("a", "b", "d"),
    [("", "", 0), ("abc", "abc", 0), ("", "abc", 3), ("kitten", "sitting", 3), ("수영징", "수영장", 1)],
)
def test_edit_distance(a: str, b: str, d: int) -> None:
    assert call(edit_distance, a, b) == d


def test_jamo_distance_is_finer_than_syllable() -> None:
    # 글자 단위로는 둘 다 1이지만, 자모 단위로는 '징→장'(모음 하나)이 '징→방'보다 가깝다
    near = call(edit_distance, call(to_jamo, "수영징"), call(to_jamo, "수영장"))
    far = call(edit_distance, call(to_jamo, "수영징"), call(to_jamo, "수영방"))
    assert near < far
