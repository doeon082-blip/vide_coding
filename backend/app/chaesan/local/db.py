"""로컬 DB 어댑터: sqlite3를 읽기 전용(mode=ro)으로 열어 core.ports.DB 인터페이스를 만족시킨다.

서비스(D1)는 쓰기가 가능한 바인딩이라 sql_guard로 막지만, 로컬은 DB 자체를 읽기 전용으로 열어 한 겹을 더 둔다.
sqlite3는 읽은 행 수를 알려 주지 않아 rows_read는 돌려받은 행 수로 센다(D1의 rows_read보다 작을 수 있다 = 하한값).
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

from app.chaesan.core.ports import QueryResult


def ro_uri(path: Path) -> str:
    """읽기 전용(mode=ro) sqlite URI. 경로를 퍼센트 인코딩해 '#', '?', 공백이 들어 있어도 깨지지 않는다."""
    return f"{path.resolve().as_uri()}?mode=ro"


class SqliteDB:
    def __init__(self, path: Path) -> None:
        # check_same_thread=False: 이벤트 루프와 작업 스레드가 같은 연결을 번갈아 쓰기 때문(동시 사용은 lock으로 막는다)
        self._con = sqlite3.connect(ro_uri(path), uri=True, check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()

    async def query(self, sql: str, params: tuple[Any, ...] = ()) -> QueryResult:
        async with self._lock:
            rows = await asyncio.to_thread(self._run, sql, params)
        return QueryResult(rows=rows, rows_read=len(rows))

    def _run(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        return [dict(r) for r in self._con.execute(sql, params).fetchall()]

    def close(self) -> None:
        self._con.close()
