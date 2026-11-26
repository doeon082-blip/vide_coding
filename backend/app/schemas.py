"""Pydantic response models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field

Status = Literal["진행중", "예정", "완료"]


def compute_status(start: str, end: str, today: date | None = None) -> Status | None:
    """Return 진행중/예정/완료 relative to the server's today, or None if dates are unparseable."""
    today_s = (today or date.today()).isoformat()  # YYYY-MM-DD compares lexicographically
    start = start.strip() or end.strip()
    end = end.strip() or start
    if len(start) != 10 or len(end) != 10:
        return None
    if today_s < start:
        return "예정"
    if today_s > end:
        return "완료"
    return "진행중"


class FestivalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fstvl_nm: str
    fstvl_start_date: str
    fstvl_end_date: str
    opar: str
    fstvl_co: str
    rdnmadr: str
    ai_summary: str | None = None
    ai_summarized_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> Status | None:
        return compute_status(self.fstvl_start_date, self.fstvl_end_date)


class FestivalPage(BaseModel):
    total: int
    page: int
    size: int
    total_pages: int
    items: list[FestivalOut]


class SummaryOut(BaseModel):
    id: int
    ai_summary: str
    cached: bool
