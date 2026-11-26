"""FastAPI entrypoint."""

from __future__ import annotations

import math
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_service import AIServiceError, summarize_festival
from app.database import get_db, init_db
from app.models import Festival
from app.schemas import FestivalPage, SummaryOut


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="Festival API", lifespan=lifespan)

origins = [o.strip() for o in (os.getenv("CORS_ORIGINS") or "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/festivals", response_model=FestivalPage)
def list_festivals(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> FestivalPage:
    total = db.scalar(select(func.count(Festival.id))) or 0
    rows = db.scalars(
        select(Festival)
        .order_by(Festival.fstvl_start_date.desc(), Festival.id)
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return FestivalPage(
        total=total,
        page=page,
        size=size,
        total_pages=max(1, math.ceil(total / size)),
        items=rows,  # type: ignore[arg-type]
    )


@app.post("/api/festivals/{festival_id}/summarize", response_model=SummaryOut)
def summarize(festival_id: int, db: Session = Depends(get_db)) -> SummaryOut:
    festival = db.get(Festival, festival_id)
    if festival is None:
        raise HTTPException(404, "축제를 찾을 수 없습니다.")
    try:
        summary, cached = summarize_festival(db, festival)
    except AIServiceError as exc:
        raise HTTPException(503, str(exc)) from exc
    return SummaryOut(id=festival.id, ai_summary=summary, cached=cached)
