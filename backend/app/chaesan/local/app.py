"""채산 로컬 API 서버 (FastAPI). 기존 축제 앱(app.main)과 따로 실행한다: 규칙 5(기존 기능은 바꾸지 않는다).

실행: `uv run uvicorn app.chaesan.local.app:app --port 8100 --no-proxy-headers` (backend/ 에서)
  - --no-proxy-headers: 요청 제한이 위조된 X-Forwarded-For에 속지 않게(ratelimit.client_ip 참고)

방어: 질문 길이 제한(pydantic + 엔진), 질문 속 지시문 차단(엔진, LLM 호출 전), IP별 요청 제한(분당 10회),
본문 8KB 제한, 보안 헤더, /docs 기본 비공개, CORS는 허용 출처만. 오류 상세는 응답에 싣지 않는다.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from app.chaesan.core import guard
from app.chaesan.core.catalog import load_catalog
from app.chaesan.core.config import MAX_QUESTION_LEN
from app.chaesan.core.correct import load_vocab
from app.chaesan.core.engine import MSG_ERROR, Engine
from app.chaesan.ingest.aliases import ALIASES_PATH
from app.chaesan.ingest.cards import CARDS_DIR
from app.chaesan.ingest.load import DB_PATH
from app.chaesan.local.clock import SystemClock
from app.chaesan.local.db import SqliteDB
from app.chaesan.local.demand import JsonlDemandSink
from app.chaesan.local.llm import OllamaLLM
from app.ratelimit import RateLimitMiddleware

logger = logging.getLogger(__name__)
ASK_PATH = "/api/chaesan/ask"
INDEX_PATH = Path(__file__).parent / "static" / "index.html"
ASK_LIMIT_PER_MINUTE = 10  # 질문 한 번에 LLM을 최대 3번 부르므로 축제 앱의 일반 한도보다 엄격하게
MAX_RUNNING = 2  # 동시에 처리하는 질문 수(로컬 LLM 한 대가 감당할 수준)
MAX_WAITING = 4  # 처리 순서를 기다리는 질문 수. 넘치면 기다리게 하지 않고 바로 503
MSG_BUSY = "지금은 질문이 많아요. 잠시 후 다시 물어봐 주세요."


class Gate:
    """동시 처리 제한. IP별 요청 제한만으로는 여러 IP가 한꺼번에 오는 것을 막지 못해 로컬 LLM에 질문이 쌓인다."""

    def __init__(self, running: int = MAX_RUNNING, waiting: int = MAX_WAITING) -> None:
        self._slots = asyncio.Semaphore(running)
        self._max_waiting = waiting
        self._waiting = 0

    @asynccontextmanager
    async def enter(self) -> AsyncIterator[None]:
        if self._slots.locked() and self._waiting >= self._max_waiting:
            raise HTTPException(status_code=503, detail=MSG_BUSY)
        self._waiting += 1
        try:
            await self._slots.acquire()
        finally:
            self._waiting -= 1
        try:
            yield
        finally:
            self._slots.release()


def page_csp(html: str) -> str:
    """화면(index.html)용 CSP. 인라인 <script>·<style>은 내용의 SHA-256 해시로만 허용한다('unsafe-inline' 없음):
    페이지에 다른 스크립트가 끼어들면(주입) 해시가 달라 실행되지 않는다. 서버 응답과의 통신은 같은 출처로만 허용한다."""

    def digest(tag: str) -> str:
        m = re.search(rf"<{tag}>(.*?)</{tag}>", html, re.DOTALL)
        if m is None:
            raise ValueError(f"index.html에 <{tag}>가 없다")
        return "'sha256-" + base64.b64encode(hashlib.sha256(m.group(1).encode("utf-8")).digest()).decode() + "'"

    return (
        f"default-src 'none'; script-src {digest('script')}; style-src {digest('style')}; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LEN)


class ChaesanRateLimit(RateLimitMiddleware):
    """기존 요청 제한(IP 판별·본문 크기 검사 포함)을 그대로 쓰고 채산 전용 규칙만 바꾼다. 기존 파일은 수정하지 않는다."""

    def _rule(self, request: Request) -> tuple[str, int, int]:
        if request.url.path == ASK_PATH:
            return "chaesan|ask", ASK_LIMIT_PER_MINUTE, 60
        return "default", 60, 60


def build_engine(
    cards_dir: Path = CARDS_DIR, db_path: Path = DB_PATH, aliases: Path = ALIASES_PATH, *, record_demand: bool = True
) -> Engine:
    """파일에서 엔진을 만든다. 파일이 없거나 형식이 틀리면 시작할 때 바로 멈춘다(조용히 빈 데이터로 시작하지 않는다)."""
    return Engine(
        db=SqliteDB(db_path),
        llm=OllamaLLM(),
        clock=SystemClock(),
        catalog=load_catalog(cards_dir),
        vocab=load_vocab(aliases),
        sink=JsonlDemandSink() if record_demand else None,  # 개발용 검사·스모크는 실제 시민 수요 통계에 섞이지 않게 끈다
    )


def create_app(engine: Engine | None = None, *, rate_limit: bool | None = None, gate: Gate | None = None) -> FastAPI:
    limiter = gate or Gate()
    docs_on = os.getenv("ENABLE_DOCS", "off").lower() == "on"

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = engine or build_engine()
        yield

    app = FastAPI(
        title="채산(비공식)",
        lifespan=lifespan,
        docs_url="/docs" if docs_on else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_on else None,
    )
    enabled = rate_limit if rate_limit is not None else os.getenv("RATE_LIMIT", "on").lower() != "off"
    origins = [o.strip() for o in os.getenv("CHAESAN_CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'")  # 화면 경로는 자기 CSP를 먼저 넣는다
        response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(ChaesanRateLimit, enabled=enabled)
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["content-type"])

    index_html = INDEX_PATH.read_text(encoding="utf-8")  # 시작할 때 읽어, 파일이 없거나 <script>가 없으면 바로 멈춘다
    index_headers = {"Content-Security-Policy": page_csp(index_html)}

    @app.get("/", include_in_schema=False)
    async def index() -> HTMLResponse:
        return HTMLResponse(index_html, headers=index_headers)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(ASK_PATH)
    async def ask(body: AskIn, request: Request) -> JSONResponse:
        async with limiter.enter():
            card = await request.app.state.engine.ask(body.question)
        if card.status == "blocked":
            raise HTTPException(status_code=400, detail=guard.BLOCK_MESSAGE)
        if card.status == "error":
            raise HTTPException(status_code=503, detail=MSG_ERROR)
        return JSONResponse(json.loads(json.dumps(card.to_dict(), ensure_ascii=False, default=str)))

    return app


app = create_app()
