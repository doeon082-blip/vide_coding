"""채산 로컬 API 서버 (FastAPI). 기존 축제 앱(app.main)과 따로 실행한다: 규칙 5(기존 기능은 바꾸지 않는다).

실행: `uv run uvicorn app.chaesan.local.app:app --port 8100 --no-proxy-headers` (backend/ 에서)
  - --no-proxy-headers: 요청 제한이 위조된 X-Forwarded-For에 속지 않게(ratelimit.client_ip 참고)

방어: 질문 길이 제한(pydantic + 엔진), 질문 속 지시문 차단(엔진, LLM 호출 전), IP별 요청 제한(분당 10회),
본문 8KB 제한, 보안 헤더, /docs 기본 비공개, CORS는 허용 출처만. 오류 상세는 응답에 싣지 않는다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from app.chaesan.core import guard
from app.chaesan.core.catalog import load_catalog
from app.chaesan.core.config import KST, MAX_QUESTION_LEN
from app.chaesan.core.correct import load_vocab
from app.chaesan.core.engine import MSG_ERROR, Engine
from app.chaesan.ingest.aliases import ALIASES_PATH
from app.chaesan.ingest.cards import CARDS_DIR
from app.chaesan.ingest.load import BACKEND_DIR, DB_PATH
from app.chaesan.local.clock import SystemClock
from app.chaesan.local.db import SqliteDB
from app.chaesan.local.demand import JsonlDemandSink
from app.chaesan.local.limits import DailyBudget
from app.chaesan.local.llm import make_llm
from app.chaesan.local.ratelimit import MAX_BODY_BYTES, RateLimitMiddleware, client_ip
from app.chaesan.local.usage_log import FileUsageLog, Pseudonymizer, UsageSink, build_event

logger = logging.getLogger(__name__)
ASK_PATH = "/api/chaesan/ask"
WEB_DIR = (
    BACKEND_DIR.parent / "frontend"
)  # 화면 전체(HTML·CSS·JS·예시)는 저장소 루트의 frontend/. 서비스(Cloudflare)도 같은 폴더를 올린다
# 화면 CSP: 같은 출처의 파일만 허용한다(인라인 코드·외부 자원 없음). 통신도 같은 출처로만, 프레임에 넣을 수 없다.
PAGE_CSP: Final = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
API_CSP: Final = "default-src 'none'"  # API 응답은 아무것도 불러올 수 없게
ASK_LIMIT_PER_MINUTE = 10  # 질문 한 번에 LLM을 최대 3번 부르므로 축제 앱의 일반 한도보다 엄격하게
MAX_RUNNING = 2  # 동시에 처리하는 질문 수(로컬 LLM 한 대가 감당할 수준)
MAX_WAITING = 4  # 처리 순서를 기다리는 질문 수. 넘치면 기다리게 하지 않고 바로 503
MSG_BUSY = "지금은 질문이 많아요. 잠시 후 다시 물어봐 주세요."
MSG_DAILY_LIMIT = "오늘 받을 수 있는 질문을 모두 썼어요. 내일 다시 물어봐 주세요. 예시 질문은 계속 볼 수 있어요."


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


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LEN)


async def read_question(request: Request) -> AskIn:
    """요청 본문을 **읽는 도중에** 크기를 제한하며 읽고 검사한다.

    왜: 요청 제한 미들웨어는 Content-Length 헤더만 보므로, 헤더 없이 조각(chunked)으로 큰 본문을 보내면 서버가 끝까지 읽어
    메모리를 쓴다. 질문 하나는 짧으니 MAX_BODY_BYTES를 넘는 순간 읽기를 멈추고 413으로 끊는다.
    """
    if "application/json" not in request.headers.get("content-type", ""):
        raise HTTPException(status_code=415, detail="JSON 형식으로 보내 주세요.")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="요청 본문이 너무 큽니다.")
        chunks.append(chunk)
    try:
        return AskIn.model_validate_json(b"".join(chunks))
    except ValidationError as exc:  # 검증 상세(내부 필드 이름 등)는 돌려주지 않고 일반 문장만
        raise HTTPException(status_code=422, detail=f"질문은 1자 이상 {MAX_QUESTION_LEN}자 이하로 써 주세요.") from exc


class ChaesanRateLimit(RateLimitMiddleware):
    """기존 요청 제한(IP 판별·본문 크기 검사 포함)을 그대로 쓰고 채산 전용 규칙만 바꾼다. 기존 파일은 수정하지 않는다."""

    def _rule(self, request: Request) -> tuple[str, int, int]:
        if request.url.path == ASK_PATH:
            return "chaesan|ask", ASK_LIMIT_PER_MINUTE, 60
        if not request.url.path.startswith("/api/"):
            return "static", 600, 60  # 화면 파일(모듈 10여 개)을 한 번 열 때 한도에 걸리지 않게
        return "default", 60, 60


def build_engine(
    cards_dir: Path = CARDS_DIR, db_path: Path = DB_PATH, aliases: Path = ALIASES_PATH, *, record_demand: bool = True
) -> Engine:
    """파일에서 엔진을 만든다. 파일이 없거나 형식이 틀리면 시작할 때 바로 멈춘다(조용히 빈 데이터로 시작하지 않는다)."""
    return Engine(
        db=SqliteDB(db_path),
        llm=make_llm(),  # LLM_PROVIDER에 따라 Ollama 또는 Workers AI
        clock=SystemClock(),
        catalog=load_catalog(cards_dir),
        vocab=load_vocab(aliases),
        sink=JsonlDemandSink() if record_demand else None,  # 개발용 검사·스모크는 실제 시민 수요 통계에 섞이지 않게 끈다
    )


def create_app(
    engine: Engine | None = None,
    *,
    rate_limit: bool | None = None,
    gate: Gate | None = None,
    usage: UsageSink | None = None,
    budget: DailyBudget | None = None,
) -> FastAPI:
    """usage: 사용 기록을 받는 곳(None이면 기록하지 않는다. 시험이 파일을 만들지 않게 기본값은 없음)."""
    limiter = gate or Gate()
    daily = budget or DailyBudget.from_env()  # 하루 질문 한도(AI 무료 한도를 한 사람이 다 쓰지 못하게)
    docs_on = os.getenv("ENABLE_DOCS", "off").lower() == "on"

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = engine or build_engine()
        logger.info("chaesan started: llm=%s", getattr(app.state.engine, "llm_label", "unknown"))  # 어느 모델인지만(키·주소 없음)
        yield

    app = FastAPI(
        title="채산(비공식)",
        lifespan=lifespan,
        docs_url="/docs" if docs_on else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_on else None,
    )
    enabled = rate_limit if rate_limit is not None else os.getenv("RATE_LIMIT", "on").lower() != "off"
    pseudonym = Pseudonymizer()

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        is_api = request.url.path.startswith("/api/")
        response.headers["Content-Security-Policy"] = API_CSP if is_api else PAGE_CSP
        response.headers["Cache-Control"] = "no-store"
        # 브라우저 기능을 모두 끄고(카메라·마이크·위치 등), 다른 출처가 이 페이지와 창·자원을 공유하지 못하게 한다.
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"  # HTTPS로만 접속하게(HTTPS일 때만 의미가 있다)
        return response

    app.add_middleware(ChaesanRateLimit, enabled=enabled)

    if usage is not None:
        sink = usage

        # 가장 바깥에 붙인다(요청 제한이 막은 429도 기록하려고). 경로가 /api/인 요청만, 건강 확인(/api/health)은 소음이라 뺀다.
        @app.middleware("http")
        async def usage_logging(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
            started = time.perf_counter()
            status_code = 500  # 처리 중 예외가 나면 기록은 500으로 남긴다
            try:
                response = await call_next(request)
                status_code = response.status_code
                return response
            finally:
                path = request.url.path
                if path.startswith("/api/") and path != "/api/health":
                    now = datetime.now(KST)
                    sink.record(
                        build_event(
                            now=now,
                            method=request.method,
                            path=path,
                            status_code=status_code,
                            elapsed_ms=round((time.perf_counter() - started) * 1000),
                            ip_pseudonym=pseudonym(client_ip(request), now),
                            extra=getattr(request.state, "usage", None),
                        )
                    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(ASK_PATH)
    async def ask(request: Request) -> JSONResponse:
        body = await read_question(request)
        ip = client_ip(request)
        if daily.check(ip) is not None:  # AI를 부르기 전에 막는다(예산을 쓰지 않는다)
            request.state.usage = {"q_len": len(body.question), "result": "daily_limit"}
            raise HTTPException(status_code=429, detail=MSG_DAILY_LIMIT)
        async with limiter.enter():
            card = await request.app.state.engine.ask(body.question)
        if card.meta.get("llm_calls"):
            daily.charge(ip)
        # 처리 결과 요약만 남긴다(질문·답변 글자는 싣지 않는다). 사용 기록 미들웨어가 요청 기록에 합쳐 쓴다.
        now = datetime.now(KST)
        request.state.usage = {
            "q_len": len(body.question),
            "q_hash": pseudonym(body.question, now),
            "result": card.status,
            "llm": getattr(request.app.state.engine, "llm_label", "unknown"),  # 이름을 모르는 엔진도 기록은 계속
            "intent": card.meta.get("intent"),
            "llm_calls": card.meta.get("llm_calls"),
            "input_tokens": card.meta.get("input_tokens"),
            "output_tokens": card.meta.get("output_tokens"),
            "rows_read": card.meta.get("rows_read"),
            "engine_ms": card.meta.get("elapsed_ms"),
            "sources": [str(src.get("id")) for src in card.sources],
            "corrections": len(card.corrections),
            "unsupported_numbers": len(card.unsupported_numbers),
            "documents": len(card.documents),
            "evidence_rows": len(card.evidence_rows),
        }
        if card.status == "blocked":
            raise HTTPException(status_code=400, detail=guard.BLOCK_MESSAGE)
        if card.status == "error":
            raise HTTPException(status_code=503, detail=MSG_ERROR)
        return JSONResponse(json.loads(json.dumps(card.to_dict(), ensure_ascii=False, default=str)))

    @app.api_route(ASK_PATH, methods=["GET", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    async def ask_wrong_method() -> Response:
        # 화면용 정적 마운트('/')가 POST 전용 경로의 다른 방식 요청을 404로 가로채지 못하게 405를 직접 돌려준다
        return Response(status_code=405, headers={"Allow": "POST"})

    # 화면 파일은 API 경로를 모두 등록한 뒤 맨 마지막에 '/'로 붙인다(먼저 붙이면 /api/...를 가려 버린다).
    # directory가 없으면 StaticFiles가 시작할 때 바로 오류를 낸다 → 화면 없이 조용히 뜨지 않는다.
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app(usage=FileUsageLog())
