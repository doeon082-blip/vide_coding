"""데이터 카드 읽기와 검증 (로컬·서비스 공통, 표준 라이브러리만).

카드는 ingest.cards가 만든 JSON이다. 여기서는 읽어서 형식이 맞는지 한 번 더 확인하고, 질문 처리에 쓰기 좋게 꺼내 준다.
형식이 틀린 카드가 있으면 조용히 건너뛰지 않고 CatalogError로 멈춘다(틀린 카드로 틀린 답을 내는 것보다 낫다).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from app.chaesan.core.config import TIER_WEIGHTS

_REQUIRED: Final = (
    "id", "name", "kind", "loaded", "portal_url", "group", "tier", "weight", "tier_reason", "rows", "period",
    "last_data_date", "columns", "caveats", "example_questions", "aliases", "in_service",
)  # fmt: skip
_KINDS: Final = frozenset({"file", "web", "api"})


class CatalogError(ValueError):
    """카드 형식이 맞지 않다."""


@dataclass(frozen=True, slots=True)
class Card:
    id: str
    name: str
    kind: str  # file(포털 파일데이터) / web(누리집 페이지) / api(오픈API)
    loaded: bool  # False면 아직 연결하지 않은 데이터 → '연결 예정'으로 답한다
    portal_url: str
    group: str | None
    tier: str
    weight: float  # 검색 점수 = 유사도 × weight (질문에 이름·별칭이 직접 나오면 1.0)
    tier_reason: str
    table: str | None
    in_service: bool  # False면 서비스(D1)에는 집계 표만 있다
    aggregate_tables: tuple[str, ...]
    rows: int | None
    period_start: str | None
    period_end: str | None
    period_precision: str | None
    last_data_date: str | None
    caveats: tuple[str, ...]
    example_questions: tuple[str, ...]
    aliases: tuple[str, ...]
    summary: str | None
    source_kind: str | None
    body_available: bool | None
    columns: tuple[dict[str, Any], ...]

    @property
    def tables(self) -> tuple[str, ...]:
        """질문 처리에서 SQL이 읽을 수 있는 표(서비스 기준: 큰 원본은 집계 표로 대신한다)."""
        base = (self.table,) if self.table and self.in_service else ()
        return base + self.aggregate_tables


@dataclass(frozen=True, slots=True)
class Group:
    id: str
    title: str
    representative: str
    rule: str
    members: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Catalog:
    cards: dict[str, Card]
    groups: dict[str, Group]

    def get(self, card_id: str) -> Card | None:
        return self.cards.get(card_id)

    def loaded(self) -> Iterator[Card]:
        return (c for c in self.cards.values() if c.loaded)

    def in_group(self, group_id: str) -> list[Card]:
        return [self.cards[m] for m in self.groups[group_id].members]


def _card(raw: dict[str, Any]) -> Card:
    missing = [k for k in _REQUIRED if k not in raw]
    if missing:
        raise CatalogError(f"{raw.get('id')}: 빠진 항목 {missing}")
    if raw["kind"] not in _KINDS:
        raise CatalogError(f"{raw['id']}: 알 수 없는 kind {raw['kind']}")
    if raw["tier"] not in TIER_WEIGHTS or raw["weight"] != TIER_WEIGHTS[raw["tier"]]:
        raise CatalogError(f"{raw['id']}: 등급과 가중치가 맞지 않다")
    if raw["loaded"] and (not raw["table"] and raw["kind"] == "file"):
        raise CatalogError(f"{raw['id']}: 적재됐다는데 표가 없다")
    if raw["loaded"] and len(raw["example_questions"]) != 3:
        raise CatalogError(f"{raw['id']}: 예시 질문은 3개여야 한다")
    if not raw["loaded"] and (raw["table"] or raw["rows"] is not None or raw["period"] is not None):
        raise CatalogError(f"{raw['id']}: 연결 안 된 데이터에 표·행 수·기간이 있다(지어낸 값)")
    period = raw["period"] or {}
    return Card(
        id=raw["id"], name=raw["name"], kind=raw["kind"], loaded=raw["loaded"], portal_url=raw["portal_url"],
        group=raw["group"], tier=raw["tier"], weight=raw["weight"], tier_reason=raw["tier_reason"],
        table=raw.get("table"), in_service=raw["in_service"], aggregate_tables=tuple(raw.get("aggregate_tables", ())),
        rows=raw["rows"], period_start=period.get("start"), period_end=period.get("end"),
        period_precision=period.get("precision"), last_data_date=raw["last_data_date"],
        caveats=tuple(raw["caveats"]), example_questions=tuple(raw["example_questions"]), aliases=tuple(raw["aliases"]),
        summary=raw.get("summary"), source_kind=raw.get("source_kind"), body_available=raw.get("body_available"),
        columns=tuple(raw["columns"]),
    )  # fmt: skip


def load_catalog(cards_dir: Path) -> Catalog:
    """cards_dir의 <번호>.json과 _groups.json을 읽어 검증한다."""
    cards: dict[str, Card] = {}
    for path in sorted(cards_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        card = _card(json.loads(path.read_text(encoding="utf-8")))
        if path.stem != card.id:
            raise CatalogError(f"파일 이름 {path.name}과 카드 번호 {card.id}가 다르다")
        cards[card.id] = card
    raw_groups = json.loads((cards_dir / "_groups.json").read_text(encoding="utf-8"))
    groups = {gid: Group(gid, g["title"], g["representative"], g["rule"], tuple(g["members"])) for gid, g in raw_groups.items()}
    for g in groups.values():
        unknown = [m for m in g.members if m not in cards]
        if unknown or g.representative not in g.members:
            raise CatalogError(f"묶음 {g.id}: 없는 구성원 {unknown} 또는 대표 {g.representative}가 구성원이 아니다")
    in_group = {m for g in groups.values() for m in g.members}
    orphans = [c.id for c in cards.values() if c.loaded and c.id not in in_group]
    if orphans:
        raise CatalogError(f"묶음에 없는 적재 카드: {orphans}")
    return Catalog(cards, groups)
