"""Hybrid festival search: lexical/typo-tolerant scoring fused with vector similarity.

score = lexical (0..1)  +  vector bonus (<= 0.4, decays with vector rank)

lexical:
  1.00        정확히 일치 (공백/기호 무시)
  0.90-1.00   축제명에 검색어가 포함
  0.60-0.85   검색어 토큰이 모두 포함 / 오타 허용(가장 비슷한 구간과의 철자 유사도)
  0.40        개최장소·주소에 포함
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from chromadb.api.models.Collection import Collection

from app.models import FestivalRecord

_STRIP = re.compile(r"[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ]+")
VECTOR_BONUS = 0.4
FUZZY_MIN = 0.6
_TTL = 60.0


def normalize(text: str) -> str:
    return _STRIP.sub("", unicodedata.normalize("NFC", text).lower())


@dataclass
class _Entry:
    record: FestivalRecord
    name_n: str
    extra_n: str


_cache: tuple[float, int, list[_Entry]] | None = None


def _entries(col: Collection) -> list[_Entry]:
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < _TTL:
        return _cache[2]
    res = col.get(include=["metadatas"])
    entries = []
    for i, m in zip(res["ids"], res["metadatas"] or []):
        r = FestivalRecord.from_chroma(i, m)
        entries.append(_Entry(r, normalize(r.fstvl_nm), normalize(f"{r.opar} {r.rdnmadr}")))
    _cache = (now, len(entries), entries)
    return entries


def invalidate_cache() -> None:
    """메타데이터(AI 요약 등)가 바뀐 뒤 캐시를 비워 목록에 바로 반영한다."""
    global _cache
    _cache = None


def all_records(col: Collection) -> list[FestivalRecord]:
    """전체 레코드(60초 캐시). 목록 요청마다 Chroma 전체를 읽지 않게 해 DoS 증폭을 줄인다."""
    return [e.record for e in _entries(col)]


def _best_window_ratio(q: str, name: str) -> float:
    """검색어와 가장 비슷한 축제명 구간의 철자 유사도 (오타 허용)."""
    n = len(q)
    if n < 2 or not name:
        return 0.0
    if len(name) <= n + 1:
        return SequenceMatcher(None, q, name).ratio()
    best = 0.0
    for size in (n - 1, n, n + 1):
        if size < 2:
            continue
        for s in range(0, len(name) - size + 1):
            sm = SequenceMatcher(None, q, name[s : s + size])
            if sm.real_quick_ratio() <= best or sm.quick_ratio() <= best:
                continue
            best = max(best, sm.ratio())
    return best


def lexical_score(q_raw: str, q: str, e: _Entry) -> float:
    if not q:
        return 0.0
    if q == e.name_n:
        return 1.0
    if q in e.name_n:
        return 0.9 + 0.1 * len(q) / len(e.name_n)
    tokens = [t for t in (normalize(t) for t in q_raw.split()) if t]
    if len(tokens) > 1 and all(t in e.name_n for t in tokens):
        return 0.85
    score = 0.0
    ratio = _best_window_ratio(q, e.name_n)
    if ratio >= FUZZY_MIN:
        score = 0.85 * ratio
    if q in e.extra_n:
        score = max(score, 0.4)
    return score


@dataclass
class Hit:
    record: FestivalRecord
    lexical: float
    score: float


def hybrid_search_scored(col: Collection, q_raw: str, limit: int = 10) -> list[Hit]:
    q = normalize(q_raw)
    entries = _entries(col)
    by_id = {e.record.id: e for e in entries}

    lex = {e.record.id: lexical_score(q_raw, q, e) for e in entries}
    scores = dict(lex)

    vres = col.query(query_texts=[q_raw], n_results=max(limit * 3, 30), include=["metadatas"])
    for rank, vid in enumerate(vres["ids"][0]):
        if vid in scores:
            scores[vid] += VECTOR_BONUS / (1 + 0.5 * rank)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [Hit(by_id[rid].record, lex[rid], sc) for rid, sc in ranked[:limit] if sc > 0]


def hybrid_search(col: Collection, q_raw: str, limit: int = 10) -> list[FestivalRecord]:
    return [h.record for h in hybrid_search_scored(col, q_raw, limit)]


_EDITION = re.compile(r"제?\s*\d+\s*회|20\d{2}\s*년?")


def canonical_name(name: str) -> str:
    """'제29회 보령머드축제' / '2026 보령머드축제' → '보령머드축제' (회차·연도 변형을 한 항목으로 묶는다)"""
    return re.sub(r"\s+", " ", _EDITION.sub(" ", name)).strip() or name


MIN_SUGGEST_SCORE = 0.19  # 어휘 점수가 있거나, 벡터 상위 3위 안일 때만 제안


def suggest_names(col: Collection, q_raw: str, limit: int = 6) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for h in hybrid_search_scored(col, q_raw, limit=limit * 5):
        if h.score < MIN_SUGGEST_SCORE:
            continue
        name = canonical_name(h.record.fstvl_nm)
        key = normalize(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
        if len(names) >= limit:
            break
    return names
