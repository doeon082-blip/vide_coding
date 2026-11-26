"""FastAPI entrypoint."""

from __future__ import annotations

import logging
import math
import os
import re
import unicodedata
from collections.abc import AsyncIterator
from datetime import date
from typing import Literal
from contextlib import asynccontextmanager

from chromadb.api.models.Collection import Collection
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.ai_service import AIServiceError, answer_question, correct_query, summarize_festival
from app.database import get_festivals_collection, init_db
from app.logging_config import setup_logging
from app.models import FestivalRecord
from app.photo_service import PhotoResult, get_photos
from app.ratelimit import RateLimitMiddleware
from app.search import canonical_name, hybrid_search, hybrid_search_scored, suggest_names
from app.schemas import AskIn, AskOut, CorrectionOut, FestivalOut, FestivalPage, SummaryOut, compute_status

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    logger.info("API started")
    yield


_docs = (os.getenv("ENABLE_DOCS") or "off").lower() == "on"
app = FastAPI(
    title="Festival API",
    lifespan=lifespan,
    docs_url="/docs" if _docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _docs else None,
)

origins = [o.strip() for o in (os.getenv("CORS_ORIGINS") or "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(RateLimitMiddleware, enabled=(os.getenv("RATE_LIMIT", "on").lower() != "off"))
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])


# 스크립트/SQL 인젝션 등 허용되지 않는 입력 패턴
_FORBIDDEN = re.compile(
    r"<\s*/?\s*(script|iframe|img|svg|object)|javascript:|on\w+\s*=|"
    r"\b(union\s+select|drop\s+table|insert\s+into|delete\s+from|select\s+.+\s+from)\b|"
    r"(--|/\*|\*/|;\s*\w+\s*=)|[\x00-\x08\x0b\x0c\x0e-\x1f]|\{\{|\$\{",
    re.IGNORECASE,
)
VIOLATION_MESSAGE = "규정위반: 허용되지 않는 입력입니다"


def _validate_query(q: str) -> str:
    q = unicodedata.normalize("NFC", q).strip()
    if len(q) > 100 or _FORBIDDEN.search(q):
        logger.warning("Blocked search input (len=%d)", len(q))
        raise HTTPException(400, VIOLATION_MESSAGE)
    return q


def _collection() -> Collection:
    return get_festivals_collection()


def _all_records(col: Collection) -> list[FestivalRecord]:
    res = col.get(include=["metadatas"])
    return [FestivalRecord.from_chroma(i, m) for i, m in zip(res["ids"], res["metadatas"] or [])]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _sort_by_status(records: list[FestivalRecord]) -> dict[str, list[FestivalRecord]]:
    """진행중(곧 끝나는 순) / 예정(곧 시작하는 순) / 완료(최근 종료 순)로 분류·정렬."""
    groups: dict[str, list[FestivalRecord]] = {"진행중": [], "예정": [], "완료": [], "미정": []}
    for r in records:
        groups[compute_status(r.fstvl_start_date, r.fstvl_end_date) or "미정"].append(r)
    groups["진행중"].sort(key=lambda r: (r.fstvl_end_date or r.fstvl_start_date, r.id))
    groups["예정"].sort(key=lambda r: (r.fstvl_start_date, r.id))
    groups["완료"].sort(key=lambda r: (r.fstvl_end_date or r.fstvl_start_date, r.id), reverse=True)
    return groups


@app.get("/api/festivals", response_model=FestivalPage)
def list_festivals(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    status: Literal["진행중", "예정", "완료"] | None = Query(None, description="상태 필터 (없으면 전체)"),
    col: Collection = Depends(_collection),
) -> FestivalPage:
    groups = _sort_by_status(_all_records(col))
    counts = {k: len(v) for k, v in groups.items() if k != "미정"}
    counts["전체"] = sum(len(v) for v in groups.values())
    records = groups[status] if status else groups["진행중"] + groups["예정"] + groups["완료"] + groups["미정"]
    total = len(records)
    chunk = records[(page - 1) * size : page * size]
    return FestivalPage(
        total=total,
        page=page,
        size=size,
        total_pages=max(1, math.ceil(total / size)),
        counts=counts,
        items=[FestivalOut(**r.model_dump()) for r in chunk],
    )


@app.get("/api/festivals/search", response_model=list[FestivalOut])
def search_festivals(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    col: Collection = Depends(_collection),
) -> list[FestivalOut]:
    """하이브리드 검색: 철자/부분일치(오타 허용) + 벡터 유사도."""
    q = _validate_query(q)
    return [FestivalOut(**r.model_dump()) for r in hybrid_search(col, q, limit)]


@app.get("/api/festivals/suggest", response_model=list[str])
def suggest(
    q: str = Query(..., min_length=1),
    limit: int = Query(6, ge=1, le=10),
    col: Collection = Depends(_collection),
) -> list[str]:
    """연관검색어: 하이브리드 랭킹 상위 축제명 (오타 교정 포함)."""
    return suggest_names(col, _validate_query(q), limit)


@app.get("/api/festivals/{festival_id}/photos", response_model=PhotoResult)
def photos(festival_id: str, col: Collection = Depends(_collection)) -> PhotoResult:
    """한국관광공사 TourAPI 기반 축제/지역 사진 (디스크 캐싱)."""
    res = col.get(ids=[festival_id], include=["metadatas"])
    if not res["ids"]:
        raise HTTPException(404, "축제를 찾을 수 없습니다.")
    record = FestivalRecord.from_chroma(res["ids"][0], (res["metadatas"] or [None])[0])
    return get_photos(record)


@app.get("/api/ai/correct", response_model=CorrectionOut)
def ai_correct(q: str = Query(..., min_length=1), col: Collection = Depends(_collection)) -> CorrectionOut:
    """로컬 AI 오타 교정: '혹시 ○○을(를) 찾으셨나요?'. 이미 정확히 일치하면 AI를 호출하지 않는다."""
    q = _validate_query(q)
    hits = hybrid_search_scored(col, q, limit=20)
    if not hits or hits[0].lexical >= 0.9:
        return CorrectionOut()
    candidates: list[str] = []
    for h in hits:
        name = canonical_name(h.record.fstvl_nm)
        if name not in candidates:
            candidates.append(name)
    try:
        return CorrectionOut(corrected=correct_query(q, candidates[:12]))
    except AIServiceError as exc:
        logger.error("AI correct failed: %s", exc)
        return CorrectionOut()


@app.post("/api/ai/ask", response_model=AskOut)
def ai_ask(body: AskIn, col: Collection = Depends(_collection)) -> AskOut:
    """로컬 AI 큐레이터(RAG): 자연어 질문 → 관련 축제 검색 → 검색 결과만 근거로 추천."""
    question = _validate_query(body.question)
    hits = hybrid_search_scored(col, question, limit=8)
    if not hits:
        return AskOut(answer="관련된 축제를 찾지 못했어요. 다른 표현으로 질문해 주세요.", festivals=[])
    today = date.today().isoformat()
    lines = []
    for h in hits:
        r = h.record
        status = compute_status(r.fstvl_start_date, r.fstvl_end_date) or "일정미정"
        lines.append(
            f"[{status}] {r.fstvl_nm} | {r.fstvl_start_date}~{r.fstvl_end_date} | {r.opar or r.rdnmadr} | {r.fstvl_co[:120]}"
        )
    try:
        answer = answer_question(question, today, lines)
    except AIServiceError as exc:
        logger.error("AI ask failed: %s", exc)
        raise HTTPException(503, str(exc)) from exc
    return AskOut(answer=answer, festivals=[FestivalOut(**h.record.model_dump()) for h in hits[:5]])


@app.post("/api/festivals/{festival_id}/summarize", response_model=SummaryOut)
def summarize(festival_id: str, col: Collection = Depends(_collection)) -> SummaryOut:
    res = col.get(ids=[festival_id], include=["metadatas"])
    if not res["ids"]:
        raise HTTPException(404, "축제를 찾을 수 없습니다.")
    record = FestivalRecord.from_chroma(res["ids"][0], (res["metadatas"] or [None])[0])
    try:
        summary, cached = summarize_festival(col, record)
    except AIServiceError as exc:
        logger.error("Summarize failed id=%s: %s", festival_id[:8], exc)
        raise HTTPException(503, str(exc)) from exc
    return SummaryOut(id=record.id, ai_summary=summary, cached=cached)
