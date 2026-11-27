"""In-memory per-client sliding-window rate limiting (single-process, no external service)."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

# (경로 접두사, 메서드) -> (허용 횟수, 윈도우 초). 위에서부터 먼저 일치하는 규칙 적용.
RULES: list[tuple[str, str | None, int, int]] = [
    ("/api/festivals/", "POST", 10, 60),  # summarize: Ollama 호출이라 가장 엄격
    ("/api/ai/", None, 12, 60),  # 로컬 LLM 호출
    ("/api/chat", None, 20, 60),  # 챗봇(RAG)
    ("/api/festivals/search", None, 40, 60),
    ("/api/festivals/suggest", None, 90, 60),
]
DEFAULT_LIMIT = (120, 60)


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
MAX_BODY_BYTES = 8 * 1024


def client_ip(request: Request) -> str:
    """실제 연결 상대의 IP. 상대가 같은 PC의 터널(cloudflared)일 때만 Cloudflare가 넣어 주는
    CF-Connecting-IP를 신뢰한다. 외부에서 직접 붙은 요청의 헤더(X-Forwarded-For 등)는 위조될 수 있어 무시한다."""
    peer = request.client.host if request.client else "unknown"
    if peer in _LOOPBACK:
        return request.headers.get("cf-connecting-ip") or peer
    return peer


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled: bool = True) -> None:  # noqa: ANN001
        super().__init__(app)
        self.enabled = enabled
        self.hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    def _rule(self, request: Request) -> tuple[str, int, int]:
        path = request.url.path
        if path.endswith("/photos"):  # 목록 한 페이지가 10건을 한꺼번에 요청
            return "photos", 240, 60
        for prefix, method, limit, window in RULES:
            if path.startswith(prefix) and (method is None or request.method == method):
                return f"{prefix}|{method}", limit, window
        return "default", *DEFAULT_LIMIT

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.enabled or request.method == "OPTIONS" or request.url.path == "/api/health":
            return await call_next(request)

        # 비정상적으로 큰 본문은 파싱 전에 차단 (이 API의 요청 본문은 짧은 질문뿐)
        if request.method in {"POST", "PUT", "PATCH"}:
            try:
                length = int(request.headers.get("content-length") or 0)
            except ValueError:  # 숫자가 아닌 길이 헤더가 서버 오류(500)를 내지 않도록 400으로 막는다
                return JSONResponse({"detail": "잘못된 요청입니다."}, status_code=400)
            if length > MAX_BODY_BYTES:
                return JSONResponse({"detail": "요청 본문이 너무 큽니다."}, status_code=413)

        now = time.monotonic()
        bucket, limit, window = self._rule(request)
        q = self.hits[(client_ip(request), bucket)]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            retry = max(1, int(window - (now - q[0])))
            return JSONResponse(
                {"detail": f"요청이 너무 많습니다. {retry}초 후 다시 시도해 주세요."},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        q.append(now)

        if now - self._last_sweep > 300:  # 오래된 키 정리
            self._last_sweep = now
            for key in [k for k, v in self.hits.items() if not v or now - v[-1] > 300]:
                del self.hits[key]
        return await call_next(request)
