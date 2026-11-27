"""핵심 함수 4개의 테스트: validate_sql, find_unsupported_numbers, to_jamo, edit_distance.

특히 validate_sql은 보안 함수라서 '사례 목록'만으로 끝내지 않는다. 무작위로 만든 SQL을 SQLite 자체의 authorizer(실행할 때
어떤 표·함수를 쓰는지 알려 주는 기능)로 실제 실행해서, 검사를 통과한 SQL이 허용하지 않은 표를 읽거나 쓰기를 하지 못함을 확인한다.
"""

from __future__ import annotations

import contextlib
import random
import re
import sqlite3
import time
from functools import cache
from typing import Any

import pytest

from app.chaesan.core.answer import find_unsupported_numbers
from app.chaesan.core.config import MAX_SQL_LEN, MAX_SQL_TABLE_REFS
from app.chaesan.core.sql_guard import SQL_ROW_LIMIT, SqlRejected, validate_sql
from app.chaesan.core.typo import edit_distance, to_jamo

# --------------------------------------------------------------------------- validate_sql: 사례

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
        "SELECT release_date FROM t_15133891 WHERE title = 'delete; drop -- /* x */'",  # 문자열 안의 ; -- 는 문법이 아니다
        "SELECT * FROM t_15133891 WHERE a IN (SELECT a FROM s_parking_hourly)",
        'SELECT * FROM "t_15133891" AS t WHERE t.users > 1',
        "SELECT * FROM T_15133891",  # 표 이름은 대소문자를 구분하지 않는다(SQLite와 같다)
        "SELECT * FROM (SELECT * FROM t_15133891) AS s",
        "SELECT a FROM t_15133891 UNION SELECT a FROM s_parking_hourly",
        "SELECT * FROM t_15133891 WHERE b = 'it''s'",
    ],
)
def test_validate_sql_accepts_and_forces_limit(sql: str) -> None:
    out = validate_sql(sql, ALLOWED)
    assert _limit(out) is not None
    assert _limit(out) <= SQL_ROW_LIMIT
    assert not out.rstrip().endswith(";")
    assert validate_sql(out, ALLOWED) == out  # 두 번 넣어도 같다(멱등)


def test_validate_sql_limit_rewrite_keeps_the_rest() -> None:
    assert validate_sql("SELECT * FROM t_15133891 LIMIT 100000", ALLOWED) == f"SELECT * FROM t_15133891 LIMIT {SQL_ROW_LIMIT}"
    assert validate_sql("SELECT * FROM t_15133891 LIMIT 7", ALLOWED) == "SELECT * FROM t_15133891 LIMIT 7"
    assert validate_sql("SELECT * FROM t_15133891 LIMIT 3 OFFSET 99999", ALLOWED).endswith("LIMIT 3 OFFSET 99999")
    assert validate_sql("SELECT * FROM t_15133891 LIMIT 99999, 9999", ALLOWED).endswith(f"LIMIT 99999, {SQL_ROW_LIMIT}")
    # 부속 질의의 LIMIT은 최상위 LIMIT이 아니다 → 바깥에 따로 붙인다
    out = validate_sql("SELECT * FROM (SELECT * FROM t_15133891 LIMIT 3) AS s", ALLOWED)
    assert out.endswith(f"AS s LIMIT {SQL_ROW_LIMIT}")
    assert "LIMIT 3)" in out


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
        "   ",
        # --- 허용하지 않은 표를 읽는 우회 시도 ---
        "SELECT * FROM t_15133891, t_15138735",  # 쉼표 조인
        "SELECT * FROM t_15133891 a, t_15133891 b, t_15138735 c",
        "SELECT * FROM t_15133891 NATURAL JOIN t_15138735",
        "SELECT * FROM t_15133891 CROSS JOIN t_15138735",
        "SELECT * FROM t_15133891 LEFT OUTER JOIN t_15138735 ON 1",
        'SELECT * FROM "t_15138735"',
        "SELECT * FROM `t_15138735`",
        "SELECT * FROM [t_15138735]",
        "SELECT * FROM 't_15138735'",  # SQLite는 작은따옴표 문자열을 표 이름으로 읽기도 한다
        "SELECT * FROM main.t_15138735",
        "SELECT * FROM main.t_15133891",  # 스키마를 붙인 이름은 허용 표라도 거부
        "SELECT * FROM (t_15138735)",  # 괄호로 묶은 표
        "SELECT * FROM (t_15133891 JOIN t_15138735)",
        "SELECT * FROM ((SELECT * FROM t_15138735))",
        "SELECT * FROM (SELECT * FROM t_15138735)",
        "SELECT * FROM t_15133891 WHERE a IN (SELECT a FROM t_15138735)",
        "SELECT (SELECT a FROM t_15138735)",
        "SELECT a FROM t_15133891 UNION SELECT a FROM t_15138735",
        "SELECT * FROM json_each('[1]')",  # 표 함수
        "SELECT * FROM pragma_table_info('t_15133891')",
        "SELECT * FROM t_15133891 WHERE a IN (SELECT name FROM pragma_table_list)",
        "SELECT * FROM sqlite_temp_master",
        "SELECT * FROM T_15138735",  # 대소문자만 바꾼 허용 외 표
        # --- 쓰기·위험 기능 ---
        "SELECT * FROM t_15133891 WHERE 1; INSERT INTO t_15133891 VALUES (1)",
        "SELECT zeroblob(1000000000) FROM t_15133891",
        "SELECT randomblob(1000000000) FROM t_15133891",
        "SELECT load_extension('x') FROM t_15133891",
        "SELECT printf('%1000000000d', 1) FROM t_15133891",
        "SELECT replace(a, 'x', 'y') FROM t_15133891",
        "SELECT * FROM t_15133891 WHERE a IN (WITH x AS (SELECT 1) SELECT * FROM x)",
        # --- LIMIT 우회 ---
        "SELECT * FROM t_15133891 LIMIT -1",  # SQLite에서 -1은 '제한 없음'
        "SELECT * FROM t_15133891 LIMIT (SELECT 999999)",
        "SELECT * FROM t_15133891 LIMIT 5 LIMIT 6",
        "SELECT * FROM t_15133891 LIMIT 1e9",
        "SELECT * FROM t_15133891 LIMIT 0x10",
        "SELECT * FROM t_15133891 LIMIT 5, 6, 7",
        "SELECT * FROM t_15133891 LIMIT 5 ORDER BY a",
        # --- 마지막 점검에서 찾은 우회 ---
        "SELECT * FROM t_15133891 WHERE a IN t_15138735",  # IN 뒤에 표 이름만 써도 그 표를 읽는다
        "SELECT * FROM t_15133891 WHERE a NOT IN main.t_15138735",
        "SELECT * FROM t_15133891 WHERE a IN t_15133891",  # 허용 표라도 괄호 없는 IN 표는 거부
        "SELECT * FROM t_15133891 INDEXED BY i, t_15138735",  # INDEXED BY 뒤의 쉼표 조인
        "SELECT * FROM t_15133891 NOT INDEXED, t_15138735",
        'SELECT "zeroblob"(1000000000) FROM t_15133891',  # 따옴표로 감싼 함수 이름
        "SELECT [printf]('%1000000000d', 1) FROM t_15133891",
        "SELECT `load_extension`('x') FROM t_15133891",
        # --- 문법 흉내·이상한 입력 ---
        "SELECT * FROM t_15133891 WHERE a = ?",  # 매개변수
        "SELECT * FROM t_15133891 WHERE a = :x",
        "SELECT * FROM t_15133891 WHERE a = 'unterminated",
        'SELECT * FROM t_15133891 WHERE "a = 1',
        "SELECT * FROM t_15133891\x00; DROP TABLE x",
        "SELECT * FROM t_15133891\v",
        "SELECT * FROM t_15133891 WHERE ａ = 1",  # 전각 문자(문자열 밖)
        "ＳＥＬＥＣＴ * FROM t_15133891",
        "SELECT * FROM t_15133891 WHERE a = 1)",
        "SELECT * FROM (t_15133891",
        "SELECT * FROM t_15133891 WHERE a = 1 & 2",
        "SELECT * FROM t_15133891 WHERE a = 1abc",
        "SELECT * FROM",
        "SELECT * FROM t_15133891 JOIN",
        "SELECT * FROM t_15133891 AS",
        "SELECT " + "a, " * 2000 + "a FROM t_15133891",  # 너무 긴 SQL
    ],
)
def test_validate_sql_rejects(sql: str) -> None:
    with pytest.raises(SqlRejected):
        validate_sql(sql, ALLOWED)


def test_validate_sql_limits_table_references_and_length() -> None:
    refs = ", ".join(f"t_15133891 a{i}" for i in range(MAX_SQL_TABLE_REFS))
    validate_sql(f"SELECT 1 FROM {refs}", ALLOWED)
    with pytest.raises(SqlRejected, match="너무 많다"):
        validate_sql(f"SELECT 1 FROM {refs}, t_15133891 extra", ALLOWED)
    assert len("SELECT * FROM t_15133891 WHERE b = '" + "x" * 100 + "'") < MAX_SQL_LEN


def test_validate_sql_message_never_echoes_the_sql() -> None:
    attempt = "SELECT * FROM t_hidden_zzz"
    with pytest.raises(SqlRejected) as err:
        validate_sql(attempt, ALLOWED)
    assert "zzz" not in str(err.value)


def test_validate_sql_allowed_set_is_case_insensitive_and_unchanged() -> None:
    allowed = {"T_15133891"}  # 허용 목록의 대소문자는 상관없다
    assert validate_sql("select * from t_15133891", allowed).startswith("select * from t_15133891")
    assert allowed == {"T_15133891"}
    with pytest.raises(SqlRejected):
        validate_sql("SELECT * FROM t_15133891", set())  # 빈 허용 목록 = 아무 표도 못 읽는다


# --------------------------------------------------------------------------- validate_sql: 실제 실행으로 검증(authorizer)

_FORBIDDEN_FUNCS = {"zeroblob", "randomblob", "load_extension", "readfile", "writefile", "printf", "format", "replace"}


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.executescript(
        "CREATE TABLE t_ok (a INTEGER, b TEXT); CREATE TABLE t_secret (s TEXT); INSERT INTO t_secret VALUES ('비밀');"
    )
    con.executemany("INSERT INTO t_ok VALUES (?, ?)", [(i, f"v{i}") for i in range(200)])
    return con


def _run_watched(con: sqlite3.Connection, sql: str) -> tuple[set[str], set[str], list[int], int]:
    reads: set[str] = set()
    funcs: set[str] = set()
    other: list[int] = []

    def authorizer(action: int, arg1: str | None, arg2: str | None, _db: str | None, _src: str | None) -> int:
        if action == sqlite3.SQLITE_READ and arg1:
            reads.add(arg1.lower())
        elif action == sqlite3.SQLITE_FUNCTION and arg2:
            funcs.add(arg2.lower())
        elif action != sqlite3.SQLITE_SELECT:
            other.append(action)  # 쓰기·스키마 변경·ATTACH 등
        return sqlite3.SQLITE_OK

    con.set_authorizer(authorizer)
    rows = 0
    try:
        rows = len(con.execute(sql).fetchall())
    except sqlite3.Error:
        pass  # 문법 오류는 거부와 상관없다. 중요한 것은 '실제로 무엇을 건드렸나'다
    finally:
        con.set_authorizer(None)
    return reads, funcs, other, rows


_TABLES = [
    "t_ok", "T_OK", '"t_ok"', "`t_ok`", "[t_ok]", "t_ok t", "t_ok AS t", "t_secret", "T_SECRET", '"t_secret"', "[t_secret]",
    "'t_secret'", "main.t_ok", "main.t_secret", "sqlite_master", "(t_secret)", "(t_ok)", "((SELECT * FROM t_secret))",
    "t_ok INDEXED BY i", "t_ok NOT INDEXED", "t_ok INDEXED BY i, t_secret",
    "(SELECT * FROM t_ok)", "(SELECT * FROM t_secret)", "(SELECT * FROM t_ok) x", "(SELECT * FROM t_secret) x",
    "json_each('[1]')", "pragma_table_info('t_ok')", "t_ok JOIN t_secret", "t_ok x",
]  # fmt: skip
_JOINS = [", ", " JOIN ", " LEFT JOIN ", " NATURAL JOIN ", " CROSS JOIN ", " INNER JOIN "]
_SELECTS = [
    "*", "a", "b, a", "count(*)", "(SELECT s FROM t_secret)", "(SELECT a FROM t_ok)", "replace(b, 'x', 'y')",
    "zeroblob(10)", '"zeroblob"(10)', "[printf]('%d', 1)", "'--'", "';'", "length(b)", "t.a", "(SELECT count(*) FROM t_ok)",
]  # fmt: skip
_WHERES = [
    "", " WHERE a > 1", " WHERE b = 'it''s'", " WHERE b = '--'", " WHERE b = ';'", " WHERE a IN (SELECT s FROM t_secret)",
    " WHERE a IN (SELECT a FROM t_ok)", " WHERE EXISTS (SELECT 1 FROM t_secret)", " WHERE 1; DROP TABLE t_ok", " -- c",
    " GROUP BY a", " HAVING count(*) > 0", ' WHERE "a" = 1', " WHERE a IN t_secret", " WHERE a NOT IN main.t_secret",
    " WHERE a IN (1, 2)", " WHERE a IN t_ok",
]  # fmt: skip
_TAILS = [
    "", " ORDER BY a", " LIMIT 5", " LIMIT 5 OFFSET 2", " LIMIT 2, 5", " LIMIT -1", " LIMIT 100000", " LIMIT 0",
    " UNION SELECT s FROM t_secret", " UNION SELECT a FROM t_ok", " UNION ALL SELECT a FROM t_ok LIMIT 3",
    ";", " ;", "; SELECT 1", " /* x */", " LIMIT (SELECT 5)", " LIMIT 5 LIMIT 6",
]  # fmt: skip


def _random_sql(rng: random.Random) -> str:
    src = rng.choice(_TABLES)
    if rng.random() < 0.4:
        src += rng.choice(_JOINS) + rng.choice(_TABLES) + rng.choice(["", " ON 1", " ON t.a = x.a", " USING (a)"])
    sql = f"SELECT {rng.choice(_SELECTS)} FROM {src}{rng.choice(_WHERES)}{rng.choice(_TAILS)}"
    if rng.random() < 0.3:
        sql = "".join(c.upper() if rng.random() < 0.5 else c.lower() for c in sql)  # 대소문자 섞기
    if rng.random() < 0.3:
        sql = sql.replace(" ", rng.choice(["  ", "\n", "\t", " \n "]), rng.randint(1, 3))  # 공백 변형
    return sql


def test_accepted_sql_never_touches_forbidden_tables_or_writes() -> None:
    """무작위 SQL 3만 개 중 검사를 통과한 것을 실제로 실행해, 허용한 표(t_ok)만 읽고 행 수가 상한 이내인지 확인한다."""
    rng = random.Random(20261128)
    con = _db()
    accepted = rejected = 0
    for _ in range(30000):
        sql = _random_sql(rng)
        try:
            out = validate_sql(sql, {"t_ok"})
        except SqlRejected:
            rejected += 1
            continue
        accepted += 1
        reads, funcs, other, rows = _run_watched(con, out)
        assert reads <= {"t_ok"}, (sql, out, reads)  # 허용 표 밖을 읽지 않았다(t_secret·sqlite_master 등)
        assert not other, (sql, out, other)  # 쓰기·스키마 변경 없음
        assert not funcs & _FORBIDDEN_FUNCS, (sql, funcs)
        assert rows <= SQL_ROW_LIMIT, (sql, out, rows)
        assert validate_sql(out, {"t_ok"}) == out  # 멱등
    assert accepted > 500
    assert rejected > 5000  # 시험이 한쪽으로 치우치지 않았다


def test_validate_sql_only_raises_sqlrejected_on_garbage() -> None:
    rng = random.Random(5)
    alphabet = "SELECT*FROMtwhere ,;()'\"`[]-/*<>=!|%+0123456789abc\n\t가나ａ\x00\x7f?:@$.&~^{}\\"
    for _ in range(20000):
        sql = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 60)))
        try:
            out = validate_sql(sql, {"t"})
        except SqlRejected:
            continue
        assert isinstance(out, str)
        assert out
    for junk in (None, 5, b"SELECT * FROM t", ["SELECT 1"]):
        with pytest.raises(SqlRejected):
            validate_sql(junk, {"t"})  # type: ignore[arg-type]


def test_validate_sql_is_fast_on_hostile_inputs() -> None:
    """정규식 폭주(ReDoS) 없이 길이 제한 안에서 항상 빨리 끝난다."""
    nasty = [
        "'" * 1999,
        "(" * 1999,
        "SELECT " + "(" * 900 + "1" + ")" * 900 + " FROM t",
        "a" * 1999,
        "SELECT * FROM t WHERE " + "a=1 OR " * 280 + "1",
    ]
    start = time.perf_counter()
    for sql in nasty:
        with contextlib.suppress(SqlRejected):
            validate_sql(sql, {"t"})
    assert time.perf_counter() - start < 1.0


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
        # --- 값으로 비교 ---
        ("3.50입니다", [{"r": 3.5}], []),
        ("3.5입니다", [{"r": "3.50"}], []),
        ("120.0명", [{"users": 120}], []),
        ("215528건", [{"n": 215528}], []),  # 쉼표가 없어도 같은 값
        ("1,234,567원", [{"won": 1234567}], []),
        ("0.1입니다", [{"r": 0.1}], []),  # 부동소수점 잡음(0.1000000000000000055…)이 끼지 않는다
        # --- 부호 ---
        ("-5명 줄었어요", [{"d": 5}], ["-5"]),
        ("-5명 줄었어요", [{"d": -5}], []),
        ("5명 늘었어요", [{"d": -5}], ["5"]),
        ("2024-07-01 자료", [{"date": "2024-07-01"}], []),  # 날짜의 하이픈은 부호가 아니다
        # --- 문자열 칸·중첩 ---
        ("12명입니다", [{"label": "총 12명"}], []),
        ("12명입니다", [{"vals": [10, 12]}], []),
        ("12명입니다", [{"vals": {"a": (11, 12)}}], []),
        ("12명입니다", [{"a": None, "b": False, "c": "없음"}], ["12"]),
        ("12명입니다", [], ["12"]),  # 결과가 비면 어떤 숫자도 근거가 없다
        # --- 우회 시도 ---
        ("１２０명이에요", [{"users": 120}], []),  # 전각 숫자도 읽어서 대조한다
        ("１３０명이에요", [{"users": 120}], ["130"]),  # 전각으로 써도 틀린 숫자는 걸린다
        ("12,34명", [{"n": 12}], ["34"]),
        ("1.2.3", [{"n": 1.2}], ["3"]),
        ("1,000,00명", [{"n": 1000}], ["00"]),
        # --- 글자가 바로 붙은 숫자(점검에서 찾은 구멍: 앞 글자를 따지면 한글 뒤의 숫자가 검사를 빠져나갔다) ---
        ("약120명", [{"users": 100}], ["120"]),
        ("총130건이에요", [{"n": 100}], ["130"]),
        ("약120명", [{"users": 120}], []),
        ("A2024와 v3", [{"n": 1}], ["2024", "3"]),
        ("점수는.5입니다", [{"n": 0.5}], ["5"]),  # 앞 0을 뺀 소수는 보수적으로 걸러낸다
        ("٣명", [{"n": 3}], []),  # 아랍-인도 숫자도 값으로 읽는다
        ("٤명", [{"n": 3}], ["٤"]),  # 보인 모양 그대로 돌려준다
        ("－5명", [{"n": -5}], []),  # 전각 마이너스
        ("① ②", [{"n": 1}], ["2"]),  # 동그라미 숫자(NFKC로 1, 2)
        ("①②", [{"n": 1}], ["12"]),  # 붙어 있으면 12 한 덩어리로 읽는 쪽이 안전하다
        ("5 and 3 and 5 and 9", [], ["5", "3", "9"]),  # 나온 순서, 중복 한 번
    ],
)
def test_find_unsupported_numbers(answer: str, rows: list[dict[str, Any]], expected: list[str]) -> None:
    assert find_unsupported_numbers(answer, rows) == expected


def test_numbers_never_crash_and_report_each_value_once() -> None:
    rng = random.Random(3)
    alphabet = "0123456789,.-+ 가나다%명건nan inf e"
    for _ in range(5000):
        answer = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        rows: list[dict[str, Any]] = [{"a": rng.choice([1, 2.5, float("nan"), float("inf"), "x1", None, True, -3])}]
        out = find_unsupported_numbers(answer, rows)
        assert len(out) == len(set(out))
        assert all(isinstance(x, str) and x for x in out)


def test_every_number_in_answer_is_supported_when_rows_contain_them() -> None:
    rng = random.Random(9)
    for _ in range(2000):
        nums = [rng.choice([rng.randint(0, 10**6), round(rng.random() * 1000, 2)]) for _ in range(rng.randint(1, 5))]
        answer = " 그리고 ".join(f"{n:,}" for n in nums)
        assert find_unsupported_numbers(answer, [{"v": n} for n in nums]) == []


# --------------------------------------------------------------------------- to_jamo / edit_distance


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("가", "ㄱㅏ"),
        ("한", "ㅎㅏㄴ"),
        ("수영장", "ㅅㅜㅇㅕㅇㅈㅏㅇ"),
        ("닭", "ㄷㅏㄺ"),
        ("a1 ", "a1 "),
        ("", ""),
        ("힣", "ㅎㅣㅎ"),  # 마지막 음절
        ("각", "ㄱㅏㄱ"),
        ("ㄱㅏ", "ㄱㅏ"),  # 이미 낱자인 호환 자모는 그대로
        ("가가나", "ㄱㅏㄱㅏㄴㅏ"),  # NFD 낱자(초성+중성)는 합쳐서 같은 음절로 본다
        ("A가-1😀", "Aㄱㅏ-1😀"),
    ],
)
def test_to_jamo(text: str, expected: str) -> None:
    assert to_jamo(text) == expected


_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = ["", *"ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"]


def test_to_jamo_covers_all_11172_syllables_and_is_reversible() -> None:
    """모든 완성형 음절을 풀었다가 다시 합쳐서 원래 글자가 나오는지 본다(표의 순서·길이가 틀리면 여기서 걸린다)."""
    seen: set[str] = set()
    for code in range(0xAC00, 0xD7A4):
        ch = chr(code)
        jamo = to_jamo(ch)
        assert len(jamo) in (2, 3)
        assert jamo not in seen
        seen.add(jamo)
        cho, jung = _CHO.index(jamo[0]), _JUNG.index(jamo[1])
        jong = _JONG.index(jamo[2]) if len(jamo) == 3 else 0
        assert chr(0xAC00 + (cho * 21 + jung) * 28 + jong) == ch
    assert len(seen) == 11172


def test_to_jamo_is_idempotent() -> None:
    rng = random.Random(1)
    pool = [chr(c) for c in range(0xAC00, 0xD7A4)] + list("abc 123-ㄱ😀") + ["ᄀ", "ᅡ"]
    for _ in range(3000):
        text = "".join(rng.choice(pool) for _ in range(rng.randint(0, 12)))
        once = to_jamo(text)
        assert to_jamo(once) == once  # 이미 푼 것을 다시 풀어도 같다


@cache
def _slow(a: str, b: str) -> int:
    """비교용 느린 정의: 마지막 글자를 기준으로 한 재귀(독립 구현)."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    return min(_slow(a[:-1], b) + 1, _slow(a, b[:-1]) + 1, _slow(a[:-1], b[:-1]) + (a[-1] != b[-1]))


@pytest.mark.parametrize(
    ("a", "b", "d"),
    [
        ("", "", 0),
        ("abc", "abc", 0),
        ("", "abc", 3),
        ("abc", "", 3),
        ("kitten", "sitting", 3),
        ("수영징", "수영장", 1),
        ("flaw", "lawn", 2),
    ],
)
def test_edit_distance(a: str, b: str, d: int) -> None:
    assert edit_distance(a, b) == d


def test_edit_distance_matches_independent_definition_and_axioms() -> None:
    rng = random.Random(2)
    for _ in range(4000):
        a = "".join(rng.choice("abcd") for _ in range(rng.randint(0, 8)))
        b = "".join(rng.choice("abcd") for _ in range(rng.randint(0, 8)))
        c = "".join(rng.choice("abcd") for _ in range(rng.randint(0, 8)))
        d = edit_distance(a, b)
        assert d == _slow(a, b)
        assert d == edit_distance(b, a)  # 대칭
        assert (d == 0) == (a == b)
        assert abs(len(a) - len(b)) <= d <= max(len(a), len(b))
        assert edit_distance(a, c) <= d + edit_distance(b, c)  # 삼각부등식


def test_jamo_distance_is_finer_than_syllable() -> None:
    # 글자 단위로는 둘 다 1이지만, 자모 단위로는 '징→장'(모음 하나)이 '징→방'(자음·모음)보다 가깝다
    near = edit_distance(to_jamo("수영징"), to_jamo("수영장"))
    far = edit_distance(to_jamo("수영징"), to_jamo("수영방"))
    assert edit_distance("수영징", "수영장") == edit_distance("수영징", "수영방") == 1
    assert near == 1
    assert near < far


def test_edit_distance_long_inputs_are_fast() -> None:
    start = time.perf_counter()
    assert edit_distance("가" * 400, "나" * 400) == 400
    assert time.perf_counter() - start < 1.0
