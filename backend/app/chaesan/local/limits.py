"""하루 질문 한도: AI를 부르는 질문 수를 사용자별·전체로 세어 넘으면 막는다.

왜: 분당 제한(IP당 10회)만으로는 한 사람이 하루 종일 질문해 무료 AI 한도(Cloudflare Workers AI는 하루 10,000 Neurons)를
다 써 버릴 수 있다(예산 소진 공격). 전체 한도가 차면 다음 날까지 AI 답은 멈추고, 화면은 미리 계산한 예시 답으로 안내한다.
하루의 경계는 Workers AI 한도가 초기화되는 UTC 0시(한국 시각 09시)에 맞춘다.
AI를 실제로 부른 질문(llm_calls > 0)만 센다: 차단된 질문·모른다로 끝난 질문(LLM 없음)은 예산을 쓰지 않는다.
메모리에만 두므로 서버를 다시 켜면 0으로 돌아간다(한도는 가벼운 안전장치이지 정산 장부가 아니다).
"""

from __future__ import annotations

import os
import threading
from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Final, Literal

DEFAULT_TOTAL: Final = 300  # 하루 전체. 첫 실측(질문당 Neurons) 뒤에 .env의 DAILY_ASK_LIMIT으로 조정한다
DEFAULT_PER_IP: Final = 40  # 하루 사용자별


def _utc_today() -> date:
    return datetime.now(UTC).date()


def _positive_int(raw: str | None, default: int) -> int:
    """환경변수 값을 양의 정수로 읽는다. 비었거나 숫자가 아니거나 0 이하면 기본값(잘못된 설정이 한도를 없애지 못하게)."""
    try:
        value = int(raw) if raw else default
    except ValueError:
        return default
    return value if value > 0 else default


class DailyBudget:
    def __init__(self, total: int = DEFAULT_TOTAL, per_ip: int = DEFAULT_PER_IP, today: Callable[[], date] = _utc_today) -> None:
        self._total, self._per_ip, self._today = total, per_ip, today
        self._day = today()
        self._used = 0
        self._by_ip: Counter[str] = Counter()
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> DailyBudget:
        return cls(
            _positive_int(os.getenv("DAILY_ASK_LIMIT"), DEFAULT_TOTAL),
            _positive_int(os.getenv("DAILY_ASK_LIMIT_PER_IP"), DEFAULT_PER_IP),
        )

    def _roll(self) -> None:
        today = self._today()
        if today != self._day:  # 날이 바뀌면 모두 0으로
            self._day, self._used = today, 0
            self._by_ip.clear()

    def check(self, ip: str) -> Literal["total", "ip"] | None:
        """이 사용자가 지금 질문해도 되는가. 막아야 하면 이유('total' 전체 한도, 'ip' 사용자 한도), 아니면 None."""
        with self._lock:
            self._roll()
            if self._used >= self._total:
                return "total"
            if self._by_ip[ip] >= self._per_ip:
                return "ip"
            return None

    def charge(self, ip: str) -> None:
        """AI를 부른 질문 한 건을 센다."""
        with self._lock:
            self._roll()
            self._used += 1
            self._by_ip[ip] += 1
