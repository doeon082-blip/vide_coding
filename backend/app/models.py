"""Festival table schema."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def build_festival_key(
    fstvl_nm: str,
    fstvl_start_date: str,
    fstvl_end_date: str,
    opar: str | None = None,
) -> str:
    """Deterministic SHA-256 key used to make upserts idempotent."""
    normalized = "|".join(
        part.strip() for part in (fstvl_nm, fstvl_start_date, fstvl_end_date, opar or "")
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Festival(Base):
    __tablename__ = "festivals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 중복 방지용 고유 키 (축제명 + 시작일 + 종료일 + 개최장소)
    unique_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    fstvl_nm: Mapped[str] = mapped_column(String(300))
    fstvl_start_date: Mapped[str] = mapped_column(String(10), default="", index=True)
    fstvl_end_date: Mapped[str] = mapped_column(String(10), default="")
    opar: Mapped[str] = mapped_column(String(300), default="")
    fstvl_co: Mapped[str] = mapped_column(Text, default="")
    rdnmadr: Mapped[str] = mapped_column(String(300), default="")

    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summarized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
