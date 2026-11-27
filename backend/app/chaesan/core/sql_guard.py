"""LLM이 쓴 SQL을 실행 전에 검사한다 (핵심 함수 1, 사용자 작성).

LLM이 쓴 SQL은 믿지 않는다. 읽기(SELECT)만, 허용한 표만, 행 수 상한(LIMIT)을 코드가 강제한다.
DB 자체도 읽기 전용으로 열지만(로컬 mode=ro), 서비스 D1 바인딩은 쓰기가 가능하므로 여기서 한 번 더 막는다.
"""

from __future__ import annotations

from app.chaesan.core.config import SQL_ROW_LIMIT


class SqlRejected(ValueError):
    """검사를 통과하지 못한 SQL. 메시지에는 거부 이유만 담는다(SQL 원문은 넣지 않음)."""


def validate_sql(sql: str, allowed_tables: set[str]) -> str:
    """검사를 통과한 SQL(LIMIT ≤ SQL_ROW_LIMIT 보장)을 돌려준다. 통과 못 하면 SqlRejected.

    힌트(순서대로):
    1. 앞뒤 공백과 끝의 세미콜론 하나는 지운다. 가운데 세미콜론이 남아 있으면 거부(여러 문장).
    2. 주석(`--`, `/*`)이 있으면 거부. 주석으로 뒤쪽 검사를 숨길 수 있다.
    3. 대소문자 무시하고 SELECT로 시작해야 한다(WITH·PRAGMA·ATTACH·INSERT 등은 거부).
    4. 금지어가 단어로 들어 있으면 거부: insert update delete drop alter create attach detach pragma
       replace vacuum. 정규식 `\\b`로 단어 경계를 본다("updated_at" 같은 열 이름은 통과해야 함).
    5. FROM·JOIN 뒤에 오는 표 이름을 모두 모아, 하나라도 allowed_tables에 없으면 거부.
       sqlite_master 같은 시스템 표도 이 단계에서 걸러진다. FROM 이 아예 없으면 거부.
    6. 끝에 `LIMIT n`이 있으면 n을 min(n, SQL_ROW_LIMIT)으로, 없으면 `LIMIT SQL_ROW_LIMIT`를 붙인다.
    """
    raise NotImplementedError("사용자 직접 작성 대기 (CLAUDE.md '작성 방식')")


__all__ = ["SQL_ROW_LIMIT", "SqlRejected", "validate_sql"]
