"""FastAPI entrypoint."""

from __future__ import annotations

import logging
import math
import os
import re
import unicodedata
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from chromadb.api.models.Collection import Collection
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.ai_service import AIServiceError, summarize_festival
from app.database import get_festivals_collection, init_db
from app.logging_config import setup_logging
from app.models import FestivalRecord
from app.photo_service import PhotoResult, get_photos
from app.ratelimit import RateLimitMiddleware
from app.search import hybrid_search, suggest_names
from app.schemas import FestivalOut, FestivalPage, SummaryOut

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    logger.info("API started")
    yield


app = FastAPI(title="Festival API", lifespan=lifespan)

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


@app.get("/api/festivals", response_model=FestivalPage)
def list_festivals(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    col: Collection = Depends(_collection),
) -> FestivalPage:
    records = sorted(_all_records(col), key=lambda r: (r.fstvl_start_date, r.id), reverse=True)
    total = len(records)
    chunk = records[(page - 1) * size : page * size]
    return FestivalPage(
        total=total,
        page=page,
        size=size,
        total_pages=max(1, math.ceil(total / size)),
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
