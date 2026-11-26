"""Ollama-backed festival summaries / typo correction / RAG answers.

모든 LLM 호출은 app.prompt_injection_defense 를 거친다:
  입력 정제·탐지 → 데이터 격리(1회용 구분자 + system 규칙 + 카나리) → 출력 검증.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import httpx
from chromadb.api.models.Collection import Collection

from app.database import BACKEND_DIR  # noqa: F401  (ensures .env is loaded)
from app.models import FestivalRecord
from app.prompt_injection_defense import (
    LEAK_MARKERS,
    InjectionBlocked,
    build_system_prompt,
    check_user_input,
    detect,
    log_event,
    new_canary,
    new_nonce,
    sanitize_untrusted,
    validate_output,
    wrap_untrusted,
)

logger = logging.getLogger(__name__)

# 사용자에게 보여 줄 일반 메시지 (내부 주소·모델명·예외 상세는 로그에만 남긴다)
PUBLIC_AI_ERROR = "AI 서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요."


class AIServiceError(RuntimeError):
    """Raised when the local Ollama server cannot produce a usable result."""


def _clean(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip().strip("\"'“”‘’").strip()
    return text.splitlines()[0].strip() if text else ""


def _chat(system: str, prompt: str, num_predict: int = 200, temperature: float = 0.3, fmt: dict | None = None) -> str:
    """로컬 Ollama /api/chat 호출 (비-thinking, system 메시지 분리). 첫 호출은 모델 로딩 중 실패할 수 있어 1회 재시도."""
    base = (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
    model = (os.getenv("OLLAMA_MODEL") or "qwen3:4b").strip()
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }
    if fmt:
        payload["format"] = fmt  # Ollama 구조화 출력(JSON 스키마)
    timeout = float(os.getenv("OLLAMA_TIMEOUT") or 120)
    last_exc: httpx.HTTPError | None = None
    for attempt in range(2):
        try:
            resp = httpx.post(f"{base}/api/chat", json=payload, timeout=timeout)
            resp.raise_for_status()
            break
        except httpx.HTTPError as exc:
            last_exc = exc
            logger.warning("Ollama call failed (attempt %d): %s", attempt + 1, exc)
            time.sleep(2)
    else:
        # 내부 주소/모델명이 응답에 새지 않도록 일반 메시지만 올린다 (상세는 위 로그)
        raise AIServiceError(PUBLIC_AI_ERROR) from last_exc
    text = re.sub(r"<think>.*?</think>", "", resp.json().get("message", {}).get("content", ""), flags=re.DOTALL)
    return text.strip()


def _guarded_call(task: str, data_block: str, instruction: str, *, num_predict: int, temperature: float, max_len: int):
    """격리된 데이터 + 규칙(system) + 출력 검증을 한 번에 적용한다. 반환: 검증된 출력 텍스트."""
    nonce, canary = new_nonce(), new_canary()
    system = build_system_prompt(task, nonce, canary)
    user = f"{wrap_untrusted(data_block, nonce)}\n\n{instruction}"
    raw = _chat(system, user, num_predict=num_predict, temperature=temperature)
    check = validate_output(raw, canary=canary, max_len=max_len)
    if not check.ok:
        logger.warning("AI output rejected: %s", check.reason)
        raise AIServiceError(PUBLIC_AI_ERROR)
    return check.text


def guarded_json(task: str, data_block: str, instruction: str, schema: dict, *, num_predict: int = 500, temperature: float = 0.4) -> dict:
    """격리된 데이터 + system 규칙 + 카나리를 적용하고 JSON(스키마 고정)으로 응답을 받는다.
    문자열 필드의 내용 검증은 호출한 쪽(사실 대조)이 한다."""
    nonce, canary = new_nonce(), new_canary()
    system = build_system_prompt(task, nonce, canary)
    raw = _chat(system, f"{wrap_untrusted(data_block, nonce)}\n\n{instruction}", num_predict=num_predict, temperature=temperature, fmt=schema)
    if canary in raw or any(m in raw for m in LEAK_MARKERS):
        log_event("output_leak", raw, ["canary_or_rules"])
        raise AIServiceError(PUBLIC_AI_ERROR)
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning("AI returned non-JSON output")
        raise AIServiceError(PUBLIC_AI_ERROR) from None
    if not isinstance(data, dict):
        raise AIServiceError(PUBLIC_AI_ERROR)
    return data


# ----------------------------------------------------------------------------- 요약


def _festival_block(f: FestivalRecord) -> str:
    def field(label: str, value: str, n: int) -> str | None:
        clean, _ = sanitize_untrusted(value, n)
        return f"{label}: {clean}" if clean else None

    parts = [
        field("축제명", f.fstvl_nm, 100),
        f"기간: {re.sub(r'[^0-9~ -]', '', f'{f.fstvl_start_date} ~ {f.fstvl_end_date}')}",
        field("장소", f.opar, 100),
        field("주소", f.rdnmadr, 100),
        field("내용", f.fstvl_co, 800),
    ]
    return "\n".join(p for p in parts if p)


def generate_summary(festival: FestivalRecord) -> str:
    out = _guarded_call(
        "데이터 블록의 축제 정보를 한국어 한 문장(60자 이내)으로 요약해 핵심 매력을 알려준다.",
        _festival_block(festival),
        "위 데이터를 바탕으로 이 축제의 핵심 매력을 한국어 한 문장(60자 이내)으로만 출력해. 인사말·따옴표·부연설명 금지.",
        num_predict=200,
        temperature=0.3,
        max_len=200,
    )
    summary = _clean(out)
    if not summary:
        raise AIServiceError(PUBLIC_AI_ERROR)
    return summary


# ----------------------------------------------------------------------------- 오타 교정


def correct_query(query: str, candidates: list[str]) -> str | None:
    """오타 교정: 후보 축제명 중 사용자가 의도했을 법한 검색어를 고른다. 없으면 None.
    결과는 반드시 '후보 목록에 있는 값'이어야 인정한다(모델이 임의 문자열을 만들어도 무시)."""
    try:
        safe_query = check_user_input(query, max_len=100)
    except InjectionBlocked:
        return None  # 인젝션 의심 입력은 AI를 호출하지 않는다
    safe_candidates = [c for c in (sanitize_untrusted(c, 100)[0] for c in candidates) if c]
    if not safe_candidates:
        return None
    data = f"입력: {safe_query}\n후보:\n" + "\n".join(f"- {c}" for c in safe_candidates)
    out = _guarded_call(
        "검색창 입력의 오타를 교정할 후보 축제명을 후보 목록에서만 고른다.",
        data,
        "입력 의도에 가장 가까운 축제명을 후보에서 정확히 그대로 한 줄로만 출력해. "
        "입력이 이미 올바르거나 후보 중 맞는 것이 없으면 NONE 만 출력해.",
        num_predict=60,
        temperature=0.0,
        max_len=120,
    )
    out = _clean(out)
    if not out or out.upper().startswith("NONE"):
        return None
    out = out.lstrip("-• ").strip()
    return out if out in safe_candidates and out != safe_query else None


# ----------------------------------------------------------------------------- RAG 답변


def answer_question(question: str, today: str, items: list[str]) -> str:
    """RAG: 검색된 축제 정보만 근거로 추천/답변. 질문이 인젝션이면 InjectionBlocked."""
    safe_question = check_user_input(question, max_len=200)
    lines = []
    for i, t in enumerate(items, 1):
        clean, _ = sanitize_untrusted(t, 400)
        if clean:
            lines.append(f"{i}. {clean}")
    if not lines:
        raise AIServiceError(PUBLIC_AI_ERROR)
    data = f"오늘 날짜: {re.sub(r'[^0-9-]', '', today)}\n축제 목록:\n" + "\n".join(lines)
    return _guarded_call(
        "검색된 축제 목록만 근거로 사용자의 질문에 한국어 3~4문장으로 친근하게 답한다. 추천하는 축제는 이름을 그대로 적고, "
        "이미 끝난(완료) 축제는 추천하지 않으며, 목록에 없는 정보는 지어내지 않는다.",
        data,
        f"사용자 질문: {safe_question}\n답변:",
        num_predict=400,
        temperature=0.4,
        max_len=800,
    )


# ----------------------------------------------------------------------------- 캐시


def summarize_festival(collection: Collection, festival: FestivalRecord) -> tuple[str, bool]:
    """Return (summary, cached). Calls Ollama only when no cached summary exists.
    검증을 통과한 요약만 저장한다(오염된 출력이 캐시에 남지 않도록)."""
    if festival.ai_summary:
        logger.info("Summary cache hit id=%s", festival.id[:8])
        return festival.ai_summary, True
    summary = generate_summary(festival)
    if detect(summary).flagged:  # 모델이 인젝션 문구를 그대로 따라 쓴 경우도 저장하지 않는다
        log_event("summary_rejected", summary, detect(summary).hits)
        raise AIServiceError(PUBLIC_AI_ERROR)
    festival.ai_summary = summary
    festival.ai_summarized_at = datetime.now(timezone.utc).isoformat()
    # metadata-only update: no re-embedding
    collection.update(ids=[festival.id], metadatas=[festival.to_metadata()])
    logger.info("Summary generated id=%s", festival.id[:8])
    return festival.ai_summary, False
