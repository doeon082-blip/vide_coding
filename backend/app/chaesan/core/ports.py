"""실행 환경 어댑터 인터페이스(db, llm, clock).

어댑터 = 로컬(sqlite3·Ollama·시스템 시각)과 서비스(D1·Workers AI·요청 시각)에서 바뀌는 부분만 감싼 얇은 층.
core 코드는 이 인터페이스만 알고, 구현은 local/ 과 worker/ 에 둔다.
D1 바인딩이 비동기라서 세 어댑터 모두 async로 통일한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(slots=True)
class QueryResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    # 이 쿼리가 읽은 행 수. D1 무료 한도(하루 읽기 행 수)를 보기 위해 로그에 남긴다.
    rows_read: int = 0


@dataclass(slots=True)
class LLMResult:
    text: str
    # 질문당 비용·무료 한도 계산(F·G단계)에 쓰는 토큰 수. 제공사가 안 주면 0.
    input_tokens: int = 0
    output_tokens: int = 0


class DB(Protocol):
    async def query(self, sql: str, params: tuple[Any, ...] = ()) -> QueryResult:
        """읽기 전용 조회. 쓰기는 하지 않는다(로컬은 mode=ro로 연다)."""
        ...


class LLM(Protocol):
    async def chat_json(
        self, system: str, user: str, schema: dict[str, Any], *, max_tokens: int, temperature: float
    ) -> LLMResult:
        """JSON 한 덩어리를 돌려받는다. 형식 검사는 core.guard.parse_guarded_json이 한다."""
        ...


class Clock(Protocol):
    async def now(self) -> datetime:
        """KST 시각(tz 포함)."""
        ...
