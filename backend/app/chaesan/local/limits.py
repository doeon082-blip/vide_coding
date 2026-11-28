"""하루 사용 한도: AI 사용량(추정 Neurons)을 사용자별·전체로 합쳐 넘으면 막는다.

왜: 분당 제한(IP당 10회)만으로는 한 사람이 하루 종일 질문해 무료 AI 한도(Cloudflare Workers AI는 하루 10,000 Neurons)를
다 써 버릴 수 있다(예산 소진 공격). 질문 수가 아니라 **토큰으로 추정한 Neurons**를 센다: 긴 질문과 여러 번 부른
질문이 더 많이 쓰기 때문이다. 전체 한도가 차면 다음 날까지 AI 답은 멈추고, 화면은 미리 계산한 예시 답으로 안내한다.
하루의 경계는 Workers AI 한도가 초기화되는 UTC 0시(한국 시각 09시)에 맞춘다.
AI를 부르지 않은 질문(차단·되묻기 등)은 토큰이 0이라 예산을 쓰지 않는다.
메모리에만 두므로 서버를 다시 켜면 0으로 돌아간다(한도는 가벼운 안전장치이지 정산 장부가 아니다).
"""

from __future__ import annotations

import os
import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Final, Literal

# 기본 모델(@cf/google/gemma-4-26b-a4b-it)의 단가: 입력 $0.10/M·출력 $0.30/M 토큰, Neurons $0.011/1,000 → 1달러 = 90,909 Neurons.
# (Cloudflare 모델 안내 페이지 기준. 모델을 바꾸면 이 두 값을 새 단가로 고친다. 실제 사용량은 대시보드 값이 정답이다.)
NEURONS_PER_M_INPUT: Final = 9_091
NEURONS_PER_M_OUTPUT: Final = 27_273
DEFAULT_TOTAL: Final = 8_000  # 하루 전체(무료 한도 10,000의 80%, 나머지는 여유). .env의 DAILY_NEURON_LIMIT으로 조정
DEFAULT_PER_IP: Final = 1_000  # 하루 사용자별: 평균 질문(약 29 Neurons)으로 약 34건


def estimate_neurons(input_tokens: int, output_tokens: int) -> float:
    """입력·출력 토큰 수로 쓴 Neurons를 추정한다. 음수·이상한 값은 0으로 본다."""
    inp, out = max(0, input_tokens), max(0, output_tokens)
    return (inp * NEURONS_PER_M_INPUT + out * NEURONS_PER_M_OUTPUT) / 1_000_000


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
    def __init__(
        self, total: float = DEFAULT_TOTAL, per_ip: float = DEFAULT_PER_IP, today: Callable[[], date] = _utc_today
    ) -> None:
        self._total, self._per_ip, self._today = total, per_ip, today
        self._day = today()
        self._used = 0.0
        self._by_ip: defaultdict[str, float] = defaultdict(float)  # 사용자별 추정 Neurons(소수)
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> DailyBudget:
        return cls(
            _positive_int(os.getenv("DAILY_NEURON_LIMIT"), DEFAULT_TOTAL),
            _positive_int(os.getenv("DAILY_NEURON_LIMIT_PER_IP"), DEFAULT_PER_IP),
        )

    def _roll(self) -> None:
        today = self._today()
        if today != self._day:  # 날이 바뀌면 모두 0으로
            self._day, self._used = today, 0.0
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

    def charge(self, ip: str, neurons: float) -> None:
        """쓴 Neurons(추정)를 더한다."""
        if neurons <= 0:
            return
        with self._lock:
            self._roll()
            self._used += neurons
            self._by_ip[ip] += neurons
