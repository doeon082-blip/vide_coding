"""개방 수요 기록 저장(로컬): JSON Lines 파일에 한 줄씩 덧붙인다. 기록에는 질문 원문이 없다(core.demand 참고)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.chaesan.ingest.load import BACKEND_DIR

DEMAND_PATH = BACKEND_DIR / "data" / "demand.jsonl"  # data/는 git에 올리지 않는다


class JsonlDemandSink:
    def __init__(self, path: Path = DEMAND_PATH) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def record(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        async with self._lock:
            await asyncio.to_thread(self._append, line)

    def _append(self, line: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
