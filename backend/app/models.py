"""Festival record model stored as ChromaDB document + metadata."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def build_festival_key(
    fstvl_nm: str, fstvl_start_date: str, fstvl_end_date: str, opar: str | None = None
) -> str:
    """Deterministic SHA-256 id so re-running the collector upserts instead of duplicating."""
    normalized = "|".join(
        p.strip() for p in (fstvl_nm, fstvl_start_date, fstvl_end_date, opar or "")
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class FestivalRecord(BaseModel):
    id: str
    fstvl_nm: str
    fstvl_start_date: str = ""
    fstvl_end_date: str = ""
    opar: str = ""
    fstvl_co: str = ""
    rdnmadr: str = ""
    ai_summary: str = ""
    ai_summarized_at: str = ""
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_document(self) -> str:
        """Text that gets embedded (semantic search target)."""
        parts = [f"축제명: {self.fstvl_nm}", f"기간: {self.fstvl_start_date} ~ {self.fstvl_end_date}"]
        if self.opar:
            parts.append(f"개최장소: {self.opar}")
        if self.rdnmadr:
            parts.append(f"도로명주소: {self.rdnmadr}")
        if self.fstvl_co:
            parts.append(f"축제내용: {self.fstvl_co}")
        return "\n".join(parts)

    def to_metadata(self) -> dict[str, str]:
        data = self.model_dump()
        data.pop("id")
        return data

    @classmethod
    def from_chroma(cls, doc_id: str, metadata: dict[str, Any] | None) -> FestivalRecord:
        meta = {k: str(v) for k, v in (metadata or {}).items() if v is not None}
        return cls(id=doc_id, **{k: v for k, v in meta.items() if k in cls.model_fields})
