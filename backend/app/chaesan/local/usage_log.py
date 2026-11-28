"""사용 기록(로그): 누가·언제·얼마나 썼는지, 어떻게 처리됐는지를 JSON 한 줄씩 파일에 남긴다.

무엇을 남기고 무엇을 남기지 않는가 (서비스 약속: "질문 원문은 저장하지 않아요")
- 남긴다: 시각(KST), 경로·상태 코드·걸린 시간, 처리 결과(answered/unknown/…), 질문 갈래, LLM 호출 수·토큰 수, 읽은 행 수,
  사용한 데이터 번호, 질문 글자 수, 그리고 질문·IP의 **가명 값**(아래).
- 남기지 않는다: 질문 원문, 답변 원문, IP 원문, 헤더, 토큰·키. 질문에는 이름·전화번호 같은 개인정보가 섞일 수 있고,
  원문을 저장하면 개인정보 처리방침·동의·보관기간 의무가 생기기 때문이다(필요한 통계는 아래 값으로 충분하다).
- 가명 값: HMAC-SHA256(하루마다 바뀌는 키, 값)의 앞 12자. 같은 날 같은 질문·같은 사용자는 같은 값이라 '반복 질문 수'와
  '사용자 수'를 셀 수 있지만, 키가 서버 메모리에만 있고 날마다 바뀌어서 원문으로 되돌릴 수도, 다른 날과 이을 수도 없다.

파일: `data/logs/usage.jsonl`(자정마다 넘기고 30일치만 보관). 기록 실패는 요청을 막지 않는다.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Final, Protocol

from app.chaesan.core.config import KST
from app.chaesan.ingest.load import BACKEND_DIR

logger = logging.getLogger(__name__)

USAGE_LOG_DIR: Final = BACKEND_DIR / "data" / "logs"  # data/는 git에 올리지 않는다
USAGE_LOG_NAME: Final = "usage.jsonl"
USAGE_LOG_DAYS: Final = 30  # 보관 기간(일). 넘은 파일은 저절로 지워진다


class UsageSink(Protocol):
    """사용 기록을 받는 곳. 서버는 이 모양만 안다(시험에서는 메모리 목록으로 바꿔 끼운다)."""

    def record(self, event: dict[str, Any]) -> None: ...


class Pseudonymizer:
    """값을 하루짜리 가명으로 바꾼다. 키는 메모리에만 있고(저장하지 않음) 날짜마다 달라진다."""

    def __init__(self) -> None:
        self._master = secrets.token_bytes(32)

    def __call__(self, value: str, when: datetime) -> str:
        day_key = hmac.new(self._master, when.astimezone(KST).strftime("%Y-%m-%d").encode(), hashlib.sha256).digest()
        return hmac.new(day_key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:12]


class FileUsageLog:
    """JSON Lines 파일 기록기. 파일은 처음 기록할 때 만든다(import만으로 파일이 생기지 않게)."""

    def __init__(self, directory: Path = USAGE_LOG_DIR, days: int = USAGE_LOG_DAYS) -> None:
        self._path = directory / USAGE_LOG_NAME
        self._days = days
        self._handler: TimedRotatingFileHandler | None = None
        self._lock = threading.Lock()
        self._warned = False

    def _open(self) -> TimedRotatingFileHandler:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handler = TimedRotatingFileHandler(self._path, when="midnight", backupCount=self._days, encoding="utf-8", delay=True)
        handler.setFormatter(logging.Formatter("%(message)s"))
        return handler

    def record(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str)
        try:
            with self._lock:
                if self._handler is None:
                    self._handler = self._open()
                self._handler.emit(logging.LogRecord("usage", logging.INFO, "", 0, line, None, None))
        except OSError as exc:
            # 디스크가 차거나 권한이 없어도 시민의 질문은 계속 처리한다. 경고는 한 번만(로그가 로그를 폭주시키지 않게).
            if not self._warned:
                self._warned = True
                logger.warning("usage log write failed: %s", type(exc).__name__)

    def close(self) -> None:
        with self._lock:
            if self._handler is not None:
                self._handler.close()
                self._handler = None


def build_event(
    *, now: datetime, method: str, path: str, status_code: int, elapsed_ms: int, ip_pseudonym: str, extra: dict[str, Any] | None
) -> dict[str, Any]:
    """요청 하나의 기록. extra는 질문 처리 결과(ask 경로에서만). 모르는 키는 버려서 실수로 원문이 섞이지 않게 한다."""
    event: dict[str, Any] = {
        "ts": now.astimezone(KST).isoformat(timespec="seconds"),
        "method": method,
        "path": path,
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "ip": ip_pseudonym,
    }
    for key, value in (extra or {}).items():
        if key in ALLOWED_EXTRA:
            event[key] = value
    return event


# 기록에 실을 수 있는 처리 결과 칸(허용 목록). 질문·답변 글자를 담는 칸은 이 목록에 없다.
ALLOWED_EXTRA: Final = frozenset(
    {
        "q_len", "q_hash", "result", "intent", "llm_calls", "input_tokens", "output_tokens", "rows_read", "engine_ms",
        "sources", "corrections", "unsupported_numbers", "documents", "evidence_rows",
    }
)  # fmt: skip
