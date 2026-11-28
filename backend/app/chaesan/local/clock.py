"""로컬 시계 어댑터: 시스템 시각을 KST로 돌려준다(서버가 UTC여도 '오늘·지난달' 해석이 같도록)."""

from __future__ import annotations

from datetime import datetime

from app.chaesan.core.config import KST


class SystemClock:
    async def now(self) -> datetime:
        return datetime.now(KST)
