"""LLM이 쓴 SQL을 실행 전에 검사한다 (핵심 함수 1).

LLM이 쓴 SQL은 믿지 않는다. 읽기(SELECT)만, 허용한 표만, 행 수 상한(LIMIT)을 코드가 강제한다.
DB 자체도 읽기 전용으로 열지만(로컬 mode=ro), 서비스 D1 바인딩은 쓰기가 가능하므로 여기서 한 번 더 막는다.

왜 정규식이 아니라 토큰 분석인가: 문자열 '…' 안에 들어 있는 `;`·`--`·`FROM`은 SQL 문법이 아니고, `FROM a, b`나
`FROM "t"` 같은 표 참조는 정규식 한두 줄로 놓치기 쉽다(놓치면 허용하지 않은 표를 읽게 된다). 그래서 SQL을 낱말(토큰)로 쪼개
따옴표 규칙을 SQLite와 똑같이 따라가며 검사한다. **의심스러우면 거부**한다: 정상 질문 몇 개를 못 답하는 것이 훨씬 싸다.

거부하는 것
- SELECT가 아닌 문, 여러 문장(`;`), 주석(`--`, `/* */`), 매개변수(`?`, `:x`), ASCII 밖의 글자(문자열 안은 허용), 제어문자
- 쓰기·스키마·설정 키워드(insert/update/delete/drop/pragma/attach/with …)와 위험 함수(zeroblob, load_extension, printf …).
  함수 이름을 따옴표로 감싼 것도 같다. `IN` 뒤에 괄호 없이 표 이름이 오는 것(`a IN secret`)과 `INDEXED BY`도 거부한다
- 허용 목록에 없는 표, `main.t`처럼 스키마를 붙인 이름, `FROM f(...)` 같은 표 함수, `FROM (t1 JOIN t2)` 같은 괄호 표
- 표 참조가 없는 SELECT, 표 참조가 MAX_SQL_TABLE_REFS개를 넘는 SQL(교차 조인으로 서버를 느리게 하는 것 방지), 너무 긴 SQL
- 최상위 LIMIT이 `LIMIT n [OFFSET m]` 또는 `LIMIT m, n` 꼴이 아닌 SQL(`LIMIT -1`은 SQLite에서 '제한 없음'이다)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

from app.chaesan.core.config import MAX_SQL_LEN, MAX_SQL_TABLE_REFS, SQL_ROW_LIMIT


class SqlRejected(ValueError):
    """검사를 통과하지 못한 SQL. 메시지에는 거부 이유만 담는다(SQL 원문은 넣지 않는다: 로그·화면에 새지 않게)."""


# 쓰기·스키마·트랜잭션·설정 키워드. 글자(단어) 단위로 비교하므로 updated_at, release_date 같은 열 이름은 걸리지 않는다.
_FORBIDDEN_WORDS: Final = frozenset(
    {
        "insert", "update", "delete", "drop", "alter", "create", "attach", "detach", "pragma", "replace", "vacuum",
        "reindex", "analyze", "begin", "commit", "rollback", "savepoint", "release", "explain", "trigger", "virtual",
        "with", "recursive",
        "indexed",  # `FROM t INDEXED BY i, secret`처럼 인덱스 지정 뒤의 쉼표 조인을 따라가지 못해 아예 거부한다
    }
)  # fmt: skip
# 메모리·파일을 건드리는 함수. 함수 호출이 아니어도 이름이 나오면 거부한다.
_FORBIDDEN_FUNCS: Final = frozenset(
    {"zeroblob", "randomblob", "load_extension", "readfile", "writefile", "fts3_tokenizer", "printf", "format"}
)
# 별칭 자리에 올 수 없는 낱말(표 참조 다음에 이 낱말이 오면 그것은 별칭이 아니라 다음 절이다)
_NOT_ALIAS: Final = frozenset(
    {
        "join", "on", "using", "where", "group", "order", "limit", "offset", "union", "except", "intersect", "having",
        "window", "natural", "left", "right", "inner", "cross", "outer", "full", "indexed", "not", "as",
    }
)  # fmt: skip
_WORD: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_NUMBER: Final = re.compile(r"\d+(?:\.\d+)?")
_PUNCT: Final = frozenset("(),.*=<>!+-/%|;")
_SPACE: Final = frozenset(" \t\n\r\f")

type Kind = Literal["word", "qident", "string", "number", "punct"]


@dataclass(frozen=True, slots=True)
class _Tok:
    kind: Kind
    text: str  # word는 원문, qident는 따옴표를 벗긴 이름, string은 원문
    start: int
    end: int

    @property
    def low(self) -> str:
        return self.text.lower()


def _reject(reason: str) -> SqlRejected:
    return SqlRejected(reason)


def _scan_quoted(sql: str, i: int, quote: str) -> int:
    """따옴표로 시작하는 위치 i에서 닫는 따옴표 다음 위치를 돌려준다. 같은 따옴표 두 개('')는 따옴표 글자 하나다(SQLite 규칙)."""
    j = i + 1
    n = len(sql)
    while j < n:
        if sql[j] == quote:
            if j + 1 < n and sql[j + 1] == quote:
                j += 2
                continue
            return j + 1
        j += 1
    raise _reject("닫히지 않은 따옴표")


def _tokenize(sql: str) -> list[_Tok]:
    if any((ord(c) < 32 and c not in _SPACE) or c == "\x7f" for c in sql):
        raise _reject("제어문자")
    toks: list[_Tok] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in _SPACE:
            i += 1
        elif ch == "'":
            j = _scan_quoted(sql, i, "'")
            toks.append(_Tok("string", sql[i:j], i, j))
            i = j
        elif ch in '"`':
            j = _scan_quoted(sql, i, ch)
            toks.append(_Tok("qident", sql[i + 1 : j - 1].replace(ch + ch, ch), i, j))
            i = j
        elif ch == "[":
            j = sql.find("]", i + 1)
            if j < 0:
                raise _reject("닫히지 않은 대괄호")
            toks.append(_Tok("qident", sql[i + 1 : j], i, j + 1))
            i = j + 1
        elif sql.startswith(("--", "/*"), i):
            raise _reject("주석")
        elif ch.isascii() and ch.isdigit():
            m = _NUMBER.match(sql, i)
            assert m is not None  # noqa: S101 - 위에서 숫자로 시작함을 확인했다
            j = m.end()
            if j < n and (sql[j].isalnum() or sql[j] in "_."):  # 1abc, 0x1F, 1e5, 1.2.3 같은 모호한 숫자
                raise _reject("모호한 숫자")
            toks.append(_Tok("number", m.group(), i, j))
            i = j
        elif ch.isascii() and (ch.isalpha() or ch == "_"):
            m = _WORD.match(sql, i)
            assert m is not None  # noqa: S101
            toks.append(_Tok("word", m.group(), i, m.end()))
            i = m.end()
        elif ch in _PUNCT:
            toks.append(_Tok("punct", ch, i, i + 1))
            i += 1
        else:
            raise _reject("허용되지 않는 문자")  # ASCII 밖 글자(문자열 밖), 매개변수 ? : @ $, 비트 연산자 등
    return toks


def _is(tok: _Tok | None, kind: Kind, text: str) -> bool:
    return tok is not None and tok.kind == kind and tok.low == text


def _source_tables(toks: list[_Tok]) -> list[str]:
    """FROM·JOIN 뒤의 모든 표 이름(소문자). 쉼표로 이은 표(`FROM a, b`)와 별칭을 따라가고,
    스키마가 붙은 이름·표 함수·괄호로 묶은 표는 거부한다. 부속 질의(`FROM (SELECT …)`) 안의 FROM은 바깥 반복에서 따로 만난다."""
    names: list[str] = []

    def at(k: int) -> _Tok | None:
        return toks[k] if k < len(toks) else None

    def source(j: int) -> int:
        t = at(j)
        if t is None:
            raise _reject("FROM 뒤에 표가 없다")
        if _is(t, "punct", "("):
            if not _is(at(j + 1), "word", "select"):
                raise _reject("괄호로 묶은 표는 허용하지 않는다")
            depth = 0  # 부속 질의 전체를 건너뛴다
            while j < len(toks):
                if _is(toks[j], "punct", "("):
                    depth += 1
                elif _is(toks[j], "punct", ")"):
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
        elif t.kind in ("word", "qident"):
            nxt = at(j + 1)
            if _is(nxt, "punct", "."):
                raise _reject("스키마를 붙인 표 이름")
            if _is(nxt, "punct", "("):
                raise _reject("표 함수")
            names.append(t.text.lower())  # word든 따옴표 이름이든 SQLite는 대소문자를 구분하지 않는다
            j += 1
        else:
            raise _reject("표 이름이 아니다")
        a = at(j)  # 별칭: `AS x` 또는 `x`
        if _is(a, "word", "as"):
            b = at(j + 1)
            if b is None or b.kind not in ("word", "qident"):
                raise _reject("별칭이 없다")
            j += 2
        elif a is not None and (a.kind == "qident" or (a.kind == "word" and a.low not in _NOT_ALIAS)):
            j += 1
        return j

    for idx, tok in enumerate(toks):
        if tok.kind == "word" and tok.low in ("from", "join"):
            j = source(idx + 1)
            while _is(at(j), "punct", ","):
                j = source(j + 1)
    return names


def _apply_limit(sql: str, toks: list[_Tok]) -> str:
    """최상위(괄호 밖) LIMIT을 SQL_ROW_LIMIT 이하로 맞추고, 없으면 붙인다."""
    depth = 0
    limits: list[int] = []
    for k, t in enumerate(toks):
        if t.kind == "punct" and t.text == "(":
            depth += 1
        elif t.kind == "punct" and t.text == ")":
            depth -= 1
            if depth < 0:
                raise _reject("괄호가 맞지 않는다")
        elif depth == 0 and t.kind == "word" and t.low == "limit":
            limits.append(k)
    if depth != 0:
        raise _reject("괄호가 맞지 않는다")
    if not limits:
        return f"{sql} LIMIT {SQL_ROW_LIMIT}"
    if len(limits) > 1:
        raise _reject("LIMIT이 여러 개")
    k = limits[0]
    rest = toks[k + 1 :]
    ints = all(r.kind == "number" and r.text.isdigit() for r in rest if r.kind == "number")
    shape = [r.low if r.kind in ("word", "punct") else "n" for r in rest]
    if not ints or shape not in (["n"], ["n", "offset", "n"], ["n", ",", "n"]):
        raise _reject("LIMIT 형식")
    count = rest[-1] if shape == ["n", ",", "n"] else rest[0]  # LIMIT 오프셋, 개수 꼴에서는 마지막 수가 개수다
    if int(count.text) <= SQL_ROW_LIMIT:
        return sql
    return sql[: count.start] + str(SQL_ROW_LIMIT) + sql[count.end :]


def validate_sql(sql: str, allowed_tables: set[str]) -> str:
    """검사를 통과한 SQL(LIMIT ≤ SQL_ROW_LIMIT 보장, 끝의 `;` 제거)을 돌려준다. 통과 못 하면 SqlRejected.

    같은 SQL을 다시 넣어도 결과가 같다(멱등). allowed_tables의 이름은 대소문자를 구분하지 않고 비교한다(SQLite와 같다).
    """
    if not isinstance(sql, str) or not sql.strip():
        raise _reject("빈 SQL")
    if len(sql) > MAX_SQL_LEN:
        raise _reject("SQL이 너무 길다")
    toks = _tokenize(sql)
    semis = [k for k, t in enumerate(toks) if t.kind == "punct" and t.text == ";"]
    if semis and semis != [len(toks) - 1]:
        raise _reject("여러 문장")
    if semis:
        toks = toks[:-1]  # 끝의 세미콜론 하나는 지운다
    if not toks or not _is(toks[0], "word", "select"):
        raise _reject("SELECT만 허용")
    for k, t in enumerate(toks):
        # 함수 이름은 "zeroblob"(…), [printf](…)처럼 따옴표로 감싸도 SQLite가 같은 함수로 읽으므로 따옴표 이름도 같이 본다
        if t.kind == "qident" and (t.low in _FORBIDDEN_FUNCS or t.low.startswith("pragma_")):
            raise _reject("허용되지 않는 함수")
        if t.kind != "word":
            continue
        if t.low in _FORBIDDEN_WORDS or t.low in _FORBIDDEN_FUNCS or t.low.startswith(("pragma_", "sqlite_")):
            raise _reject("허용되지 않는 키워드")
        # `x IN 표이름`은 괄호 없이도 그 표를 읽는다(FROM·JOIN이 없어 표 검사가 못 본다). IN 뒤에는 반드시 ( 가 와야 한다
        if t.low == "in" and not (k + 1 < len(toks) and _is(toks[k + 1], "punct", "(")):
            raise _reject("IN 뒤에는 괄호가 필요하다")
    tables = _source_tables(toks)
    if not tables:
        raise _reject("표를 읽지 않는 SELECT")
    if len(tables) > MAX_SQL_TABLE_REFS:
        raise _reject("표 참조가 너무 많다")
    allowed = {t.lower() for t in allowed_tables}
    if any(t not in allowed for t in tables):
        raise _reject("허용되지 않은 표")
    return _apply_limit(sql[: toks[-1].end], toks)


__all__ = ["SQL_ROW_LIMIT", "SqlRejected", "validate_sql"]
