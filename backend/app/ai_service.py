"""Ollama-backed one-line festival summaries with DB caching."""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone

import httpx
from chromadb.api.models.Collection import Collection

from app.database import BACKEND_DIR  # noqa: F401  (ensures .env is loaded)
from app.models import FestivalRecord


logger = logging.getLogger(__name__)


class AIServiceError(RuntimeError):
    """Raised when the local Ollama server cannot produce a summary."""


def _build_prompt(f: FestivalRecord) -> str:
    parts = [f"축제명: {f.fstvl_nm}", f"기간: {f.fstvl_start_date} ~ {f.fstvl_end_date}"]
    if f.opar:
        parts.append(f"장소: {f.opar}")
    if f.rdnmadr:
        parts.append(f"주소: {f.rdnmadr}")
    if f.fstvl_co:
        parts.append(f"내용: {f.fstvl_co[:800]}")
    info = "\n".join(parts)
    return (
        "다음 축제 정보를 바탕으로 이 축제의 핵심 매력을 한국어 한 문장(60자 이내)으로 요약해줘. "
        "인사말·따옴표·부연설명 없이 문장만 출력해.\n\n" + info
    )


def _clean(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip().strip("\"'“”‘’").strip()
    return text.splitlines()[0].strip() if text else ""


def generate_summary(festival: FestivalRecord) -> str:
    base = (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
    model = (os.getenv("OLLAMA_MODEL") or "qwen3:4b").strip()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": _build_prompt(festival)}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.3, "num_predict": 200},
    }
    timeout = float(os.getenv("OLLAMA_TIMEOUT") or 120)
    last_exc: httpx.HTTPError | None = None
    for attempt in range(2):  # first call can fail while the model is still loading
        try:
            resp = httpx.post(f"{base}/api/chat", json=payload, timeout=timeout)
            resp.raise_for_status()
            break
        except httpx.HTTPError as exc:
            last_exc = exc
            logger.warning("Ollama call failed (attempt %d): %s", attempt + 1, exc)
            time.sleep(2)
    else:
        raise AIServiceError(f"Ollama 호출 실패({base}, model={model}): {last_exc}") from last_exc
    summary = _clean(resp.json().get("message", {}).get("content", ""))
    if not summary:
        raise AIServiceError("Ollama가 빈 응답을 반환했습니다.")
    return summary


def summarize_festival(collection: Collection, festival: FestivalRecord) -> tuple[str, bool]:
    """Return (summary, cached). Calls Ollama only when no cached summary exists."""
    if festival.ai_summary:
        logger.info("Summary cache hit id=%s", festival.id[:8])
        return festival.ai_summary, True
    festival.ai_summary = generate_summary(festival)
    festival.ai_summarized_at = datetime.now(timezone.utc).isoformat()
    # metadata-only update: no re-embedding
    collection.update(ids=[festival.id], metadatas=[festival.to_metadata()])
    logger.info("Summary generated id=%s", festival.id[:8])
    return festival.ai_summary, False
