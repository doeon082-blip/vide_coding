"""질문 → 후보 데이터 선정 → 계획(JSON) 프롬프트와 계획 검증 (로컬·서비스 공통, 표준 라이브러리만).

역할 분담: **후보 데이터는 코드가 고르고**(카드의 이름·별칭·설명·등급 가중치), LLM은 그 후보 안에서 무엇을 어떻게 조회할지
JSON 계획으로만 답한다. LLM이 낸 계획은 믿지 않고 여기서 한 번, 실행 직전에 sql_guard에서 한 번 더 검사한다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

from app.chaesan.core.catalog import Card, Catalog
from app.chaesan.core.config import AGGREGATE_SCHEMAS, DOC_SOURCES, MAX_CANDIDATES
from app.chaesan.core.search import squash_text
from app.chaesan.core.when import When

INTENTS: Final = ("history", "facility", "news", "org", "data", "unknown")  # 역사·시설이용·소식·기관 정보·데이터·모름
# 이 낱말만으로는 어느 데이터인지 알 수 없는 이름 조각(대부분의 카드 이름에 들어 있다)
GENERIC: Final = frozenset(
    {"올림픽공원", "한국체육산업개발", "한체산", "정보", "현황", "목록", "데이터", "자료", "정보목록", "강좌정보"}
)
_WORD: Final = re.compile(r"[0-9A-Za-z가-힣]+")

PLAN_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "answerable": {"type": "boolean"},
        "card_ids": {"type": "array", "items": {"type": "string"}},
        "sql": {"type": "string"},
        "search_terms": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["intent", "answerable", "card_ids", "sql", "search_terms"],
}


class PlanError(ValueError):
    """LLM의 계획이 형식·후보 범위를 벗어났다. 메시지는 재계획 때 LLM에게 알려 줘도 안전한 짧은 문장이다."""


@dataclass(frozen=True, slots=True)
class Candidate:
    card: Card
    score: float
    direct: bool  # 질문에 데이터 이름·별칭이 직접 나왔는가(그러면 등급 가중치를 1.0으로 본다)


@dataclass(slots=True)
class Ranking:
    candidates: list[Candidate]  # 적재된 후보(점수순, 최대 MAX_CANDIDATES)
    planned: list[Card]  # 질문이 가리키지만 아직 연결하지 않은 오픈API
    fallback: bool  # 어느 데이터도 직접 가리키지 않아 묶음 대표로 채웠는가


def _name_terms(card: Card) -> list[str]:
    """카드 이름의 낱말(일반 낱말 제외)과 별칭을 squash 형태로. 2글자 이상만."""
    words = [w for w in _WORD.findall(card.name) if w not in GENERIC]
    out: list[str] = []
    for raw in (*words, *card.aliases):
        t = squash_text(raw)
        if len(t) >= 2 and t not in out and t not in GENERIC:
            out.append(t)
    return out


def rank_cards(question: str, catalog: Catalog, *, limit: int = MAX_CANDIDATES) -> Ranking:
    """질문에 맞는 데이터 카드를 고른다(LLM 없이). 점수 = 등급 가중치 × (직접 언급 3점 + 설명과 겹치는 낱말 0.3점).
    직접 언급이면 등급과 상관없이 가중치 1.0(지시서 3-1절)이다."""
    q = squash_text(question)
    q_words = {squash_text(w) for w in _WORD.findall(question)}
    q_words = {w for w in q_words if len(w) >= 3 and w not in GENERIC}  # 겹침 점수는 3글자 이상 낱말만(질문 말투가 섞이지 않게)
    scored: list[Candidate] = []
    loaded_terms: set[str] = set()
    for card in catalog.loaded():
        terms = _name_terms(card)
        loaded_terms.update(terms)
        direct_hits = sum(1 for t in terms if t in q)
        pool = squash_text(" ".join([card.name, card.summary or "", *card.example_questions]))
        overlap = sum(1 for w in q_words if w in pool)
        if direct_hits == 0 and overlap == 0:
            continue
        weight = 1.0 if direct_hits else card.weight
        scored.append(Candidate(card, weight * (3.0 * direct_hits + 0.3 * overlap), direct_hits > 0))
    scored.sort(key=lambda c: (-c.score, c.card.id))
    any_direct = any(c.direct for c in scored)
    planned: list[Card] = []
    if not any_direct:  # 적재된 데이터를 직접 가리키지 않을 때만 '연결 예정' 오픈API를 본다
        for card in catalog.cards.values():
            if card.loaded:
                continue
            distinct = [t for t in _name_terms(card) if t not in loaded_terms]
            if any(t in q for t in distinct):
                planned.append(card)
    top = scored[:limit]
    fallback = False
    if not top and not planned:  # 단서가 없으면 주제 묶음의 대표 데이터를 후보로 준다(LLM이 고르게)
        fallback = True
        top = [Candidate(catalog.cards[g.representative], 0.0, False) for g in catalog.groups.values()]
    return Ranking(top, planned, fallback)


def _columns_text(card: Card) -> str:
    return ", ".join(f"{c['name']}({c['ko']}, {c['sql_type']})" for c in card.columns if not str(c["name"]).endswith("_raw"))


def describe_candidate(card: Card, number: int) -> str:
    """계획 프롬프트에 넣는 후보 한 개의 설명. 주의점은 앞의 두 개만(토큰 절약)."""
    period = f"{card.period_start}~{card.period_end}" if card.period_start else "기간 정보 없음"
    lines = [f"{number}) id={card.id} | {card.name} | 갈래={card.group} | 실제 기간 {period} | {card.summary or ''}"]
    for t in card.tables:
        schema = AGGREGATE_SCHEMAS.get(t) or _columns_text(card)
        lines.append(f"   표 {t}: {schema}")
    if card.id in DOC_SOURCES:
        lines.append("   문서 검색 가능(search_terms 사용)" + ("" if card.body_available else " — 제목 수준, 본문 없음"))
    for caveat in card.caveats[:2]:
        lines.append(f"   주의: {caveat[:140]}")
    return "\n".join(lines)


def when_text(when: When | None) -> str:
    if when is None:
        return "없음"
    span = f"{when.start} ~ {when.end}" if when.start and when.end else "기간 제한 없음"
    days = f", 요일 조건 {sorted(when.weekdays)}(0=월 … 6=일)" if when.weekdays is not None else ""
    return f"{when.label} ({span}{days})"


def build_plan_prompt(
    question: str, today: date, when: When | None, candidates: Sequence[Candidate], feedback: str | None
) -> tuple[str, str, str]:
    """(임무 문장, 데이터 블록, 지시문). 데이터 블록은 호출한 쪽이 1회용 구분자로 감싸고, 질문은 신뢰하지 않는 입력이다."""
    cards = "\n".join(describe_candidate(c.card, i) for i, c in enumerate(candidates, start=1))
    data = f"[오늘] {today.isoformat()} (KST)\n[질문] {question}\n[코드가 해석한 기간] {when_text(when)}\n[후보 데이터]\n{cards}"
    instruction = (
        "위 질문에 답하기 위한 계획을 다음 JSON으로만 출력한다: "
        '{"intent": "history|facility|news|org|data|unknown", "answerable": true|false, '
        '"card_ids": [...], "sql": "...", "search_terms": [...]}\n'
        "규칙: ① 후보에 없는 데이터·표·열은 쓰지 않는다. 후보로 답할 수 없으면 answerable=false로 하고 나머지는 비운다. "
        "② 숫자·날짜는 직접 계산하지 말고 SQL로 구한다: SELECT만, 후보 표만, LIMIT 50 이하, "
        "날짜는 'YYYY-MM-DD' 문자열로 비교한다. "
        "③ 문서(FAQ·보도·연혁·소식)는 sql을 비우고 search_terms(질문에 나온 핵심 낱말 1~4개, 2글자 이상)를 쓴다. "
        "④ 기간은 위 '코드가 해석한 기간'을 그대로 쓰고 직접 해석하지 않는다. ⑤ card_ids에는 실제로 쓰는 후보의 id를 모두 적는다."
    )
    if feedback:
        instruction += f"\n이전 계획이 거부되었다(사유: {feedback}). 후보와 규칙에 맞게 다시 만든다."
    return "시민의 질문에 답하기 위한 조회 계획 JSON을 만든다.", data, instruction


@dataclass(frozen=True, slots=True)
class Plan:
    intent: str
    answerable: bool
    card_ids: tuple[str, ...]
    sql: str
    search_terms: tuple[str, ...]


def parse_plan(data: Mapping[str, Any], candidates: Mapping[str, Card]) -> Plan:
    """LLM의 계획을 검증해 Plan으로 만든다. 후보 밖의 id, 잘못된 형식, 근거 없는 '답할 수 있음'은 PlanError."""
    intent = data.get("intent")
    if intent not in INTENTS:
        raise PlanError("intent가 올바르지 않다")
    answerable = data.get("answerable")
    if not isinstance(answerable, bool):
        raise PlanError("answerable은 true/false여야 한다")
    ids = data.get("card_ids")
    sql = data.get("sql", "")
    terms = data.get("search_terms")
    if not (isinstance(ids, list) and all(isinstance(i, str) for i in ids)):
        raise PlanError("card_ids는 문자열 목록이어야 한다")
    if not isinstance(sql, str) or not (isinstance(terms, list) and all(isinstance(t, str) for t in terms)):
        raise PlanError("sql은 문자열, search_terms는 문자열 목록이어야 한다")
    if not answerable:
        return Plan(str(intent), False, (), "", ())
    chosen = tuple(dict.fromkeys(ids))
    unknown = [i for i in chosen if i not in candidates]
    if unknown or not chosen:
        raise PlanError("card_ids는 후보 데이터의 id여야 한다")
    if sql.strip() and not any(candidates[i].tables for i in chosen):
        raise PlanError("선택한 데이터에는 SQL로 조회할 표가 없다")
    kept = tuple(t.strip() for t in terms[:6] if t.strip())
    if kept and not any(i in DOC_SOURCES for i in chosen):
        raise PlanError("선택한 데이터는 문서 검색 대상이 아니다")
    if not sql.strip() and not kept:
        raise PlanError("sql 또는 search_terms가 필요하다")
    return Plan(str(intent), True, chosen, sql.strip(), kept)
