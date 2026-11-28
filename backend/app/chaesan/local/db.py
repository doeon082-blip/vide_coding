"""로컬 DB 어댑터: sqlite3를 읽기 전용(mode=ro)으로 열어 core.ports.DB 인터페이스를 만족시킨다.

서비스(D1)는 쓰기가 가능한 바인딩이라 sql_guard로 막지만, 로컬은 DB 자체를 읽기 전용으로 열어 한 겹을 더 둔다.
sqlite3는 읽은 행 수를 알려 주지 않아 rows_read는 돌려받은 행 수로 센다(D1의 rows_read보다 작을 수 있다 = 하한값).
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path
from typing import Any, Final

from app.chaesan.core.ports import QueryResult

QUERY_TIMEOUT_S: Final = 2.0  # 한 번의 SQL이 쓸 수 있는 최대 시간(질문 하나의 조회는 보통 수십 ms)
PROGRESS_STEPS: Final = 20_000  # SQLite 가상 기계 명령 이만큼마다 시간을 확인한다


def ro_uri(path: Path) -> str:
    """읽기 전용(mode=ro) sqlite URI. 경로를 퍼센트 인코딩해 '#', '?', 공백이 들어 있어도 깨지지 않는다."""
    return f"{path.resolve().as_uri()}?mode=ro"


class SqliteDB:
    def __init__(self, path: Path, *, timeout_s: float = QUERY_TIMEOUT_S) -> None:
        self._timeout_s = timeout_s
        # check_same_thread=False: 이벤트 루프와 작업 스레드가 같은 연결을 번갈아 쓰기 때문(동시 사용은 lock으로 막는다)
        self._con = sqlite3.connect(ro_uri(path), uri=True, check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()

    async def query(self, sql: str, params: tuple[Any, ...] = ()) -> QueryResult:
        async with self._lock:
            rows = await asyncio.to_thread(self._run, sql, params)
        return QueryResult(rows=rows, rows_read=len(rows))

    def _run(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        # 시간 제한: AI가 만든 SQL이 같은 큰 표(21만 행)끼리 조인하는 식으로 무거워지면
        # 한 요청이 DB와 동시 처리 자리를 오래 붙잡아 다른 사용자가 모두 막힌다.
        # 시간이 지나면 SQLite가 조회를 중단하고(OperationalError: interrupted) 엔진은 이를 '조회 실패'로 처리한다.
        deadline = time.monotonic() + self._timeout_s
        self._con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, PROGRESS_STEPS)
        try:
            return [dict(r) for r in self._con.execute(sql, params).fetchall()]
        finally:
            self._con.set_progress_handler(None, 0)

    def close(self) -> None:
        self._con.close()
