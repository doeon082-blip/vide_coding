"""채산 답변 엔진 (로컬·서비스 공통, 표준 라이브러리만).

흐름(지시서 E단계):
  질문 정제(인젝션 방어) → 오타 보정 → 기간 해석 → 후보 데이터 선정(코드) → 계획(LLM 1회, JSON)
  → 코드가 검사·실행(SQL 또는 문서 검색) → 설명(LLM 1회) → 숫자·한글 수 대조 → 답변 카드

원칙: 숫자·날짜·판정은 코드가 계산하고 LLM은 계획과 설명만 한다. LLM 호출은 질문당 최대 MAX_LLM_CALLS(3)번이고
이 한도는 코드(_llm_json)가 강제한다. 근거가 없으면 지어내지 않고 "모른다"로 답하며 개방 수요를 기록한다(질문 원문은 저장 안 함).
어떤 입력에도 예외를 밖으로 던지지 않는다: 실패는 status="error"인 카드로 돌려주고 상세는 로그에만 남긴다.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Final, Literal

from app.chaesan.core import demand, guard
from app.chaesan.core.answer import (
    ANSWER_SCHEMA,
    NO_BODY_BADGE,
    build_explain_prompt,
    card_badges,
    fallback_answer,
    find_unsupported_numbers,
    has_hangul_number,
)
from app.chaesan.core.catalog import Card, Catalog
from app.chaesan.core.config import (
    ANSWER_MAX_TOKENS,
    DOC_HITS,
    DOC_SOURCES,
    EVIDENCE_ROWS_FOR_LLM,
    MAX_ANSWER_CHARS,
    MAX_LLM_CALLS,
    NOTICE,
    PLAN_MAX_TOKENS,
    SQL_ROW_LIMIT,
)
from app.chaesan.core.correct import Corrector, Vocab
from app.chaesan.core.dates import period_end
from app.chaesan.core.planner import (
    PLAN_SCHEMA,
    Candidate,
    Plan,
    PlanError,
    Ranking,
    build_plan_prompt,
    name_terms,
    parse_plan,
    rank_cards,
    schema_lines,
)
from app.chaesan.core.ports import DB, LLM, Clock, DemandSink, LLMError
from app.chaesan.core.search import Hit, SearchResult, boosted_sources, list_docs_in_period, search_docs
from app.chaesan.core.sql_guard import SqlRejected, validate_sql
from app.chaesan.core.when import Prefer, When, parse_when

logger = logging.getLogger(__name__)

type Status = Literal["answered", "unknown", "clarify", "blocked", "planned", "error"]

MSG_UNKNOWN: Final = "한체산 개방 데이터에서 이 질문에 답할 근거를 찾지 못했어요. 추측해서 말씀드리지 않을게요."
MSG_ERROR: Final = "지금은 답을 만들 수 없어요. 잠시 후 다시 물어봐 주세요."
MSG_FUTURE: Final = (
    "내일·모레 같은 앞으로의 날짜는 예보 자료가 있어야 답할 수 있는데, 아직 연결하지 않았어요(연결 예정으로 기록할게요)."
)
MSG_CONFLICT: Final = "말씀하신 날짜와 요일이 맞지 않아요. 날짜나 요일을 다시 확인해서 물어봐 주세요."
_ASC: Final = re.compile(r"언제부터|언제\s*처음|처음|최초|맨\s*처음|가장\s*먼저|첫\s*(?:기사|보도|소식)|제일\s*오래")
_DESC: Final = re.compile(r"최근|요즘|최신|가장\s*늦|마지막|방금|이번에")
FORECAST_GROUPS: Final = frozenset({"parking", "facility_usage", "sports_courses"})  # 미래 날짜는 예보가 필요한 갈래


@dataclass(slots=True)
class AnswerCard:
    status: Status
    answer: str
    evidence_kind: Literal["table", "documents", "none"] = "none"
    evidence_rows: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    badges: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)
    notice: str = NOTICE
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _Budget(RuntimeError):
    """LLM 호출 한도(질문당 3번)를 다 썼다."""


class _NotAnswering(RuntimeError):
    """설명 단계에서 LLM이 '근거가 질문에 직접 답하지 못한다'고 스스로 판단했다(예: 질문과 뜻이 다른 열)."""


class _QueryFailed(RuntimeError):
    """계획의 SQL이 실행에 실패했다(열 이름 오류 등). 상세는 로그에만, 재계획에는 고정 문장만 알려 준다."""


@dataclass(slots=True)
class _Ctx:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    rows_read: int = 0
    intent: str = "unknown"
    plan_ok: bool = False
    hangul_number: bool = False


@dataclass(slots=True)
class _Evidence:
    rows: list[dict[str, Any]] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    cards: list[Card] = field(default_factory=list)
    # 문서 검색 전체에 대한 요약(코드가 센 값): 상위 몇 건이 아니라 일치한 모든 문서 기준
    sql: str | None = None  # 코드가 검사하고 실행한 SQL(설명 LLM이 결과 열의 뜻을 알도록 보여 준다)
    total: int = 0
    first_date: str | None = None
    last_date: str | None = None
    capped: bool = False

    @property
    def kind(self) -> Literal["table", "documents", "none"]:
        return "table" if self.rows else "documents" if self.hits else "none"


def _parse_day(text: str | None, *, end: bool) -> date | None:
    if not text:
        return None
    parsed = period_end(text)
    if parsed is None:
        return None
    if end:
        return parsed[2]
    year, month, _ = parsed
    return date(year, month or 1, 1)


def _card_range(card: Card) -> tuple[date, date] | None:
    start, stop = _parse_day(card.period_start, end=False), _parse_day(card.period_end, end=True)
    return (start, stop) if start and stop else None


class Engine:
    def __init__(
        self,
        *,
        db: DB,
        llm: LLM,
        clock: Clock,
        catalog: Catalog,
        vocab: Vocab,
        sink: DemandSink | None = None,
        corrector: Corrector | None = None,
    ) -> None:
        self._db, self._llm, self._clock, self._catalog, self._sink = db, llm, clock, catalog, sink
        self._corrector = corrector or Corrector(vocab)
        self._weights = {c.id: c.weight for c in catalog.cards.values()}
        self._boost_names = {c.id: name_terms(c) for c in catalog.loaded() if c.id in DOC_SOURCES}
        # 개방 수요 기록에 넣어도 되는 낱말: 사전·보호 낱말·데이터 이름뿐(이름·전화번호 같은 개인정보는 여기에 없다)
        self._whitelist = frozenset(
            [*vocab.words, *vocab.known, *vocab.abbreviations, *(t for c in catalog.cards.values() for t in name_terms(c))]
        )

    @property
    def llm_label(self) -> str:
        """어느 LLM으로 답했는지 구분하는 이름(사용 기록용). 어댑터가 label을 주지 않으면 'unknown'."""
        return str(getattr(self._llm, "label", "unknown"))

    # ------------------------------------------------------------------ 공개 진입점

    async def ask(self, question: str) -> AnswerCard:
        started = time.perf_counter()
        ctx = _Ctx()
        try:
            card = await self._ask(question, ctx)
        except (LLMError, _Budget):
            card = AnswerCard("error", MSG_ERROR)
        except Exception:
            logger.exception("chaesan engine failure")  # 상세는 로그에만. 질문 원문은 기록하지 않는다
            card = AnswerCard("error", MSG_ERROR)
        card.meta = {
            "llm_calls": ctx.calls,
            "input_tokens": ctx.input_tokens,
            "output_tokens": ctx.output_tokens,
            "rows_read": ctx.rows_read,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "intent": ctx.intent,
            "plan_ok": ctx.plan_ok,
            "hangul_number": ctx.hangul_number,
        }
        return card

    # ------------------------------------------------------------------ 본 흐름

    async def _ask(self, question: str, ctx: _Ctx) -> AnswerCard:
        try:
            clean = guard.check_user_input(question)
        except guard.InjectionBlocked:
            return AnswerCard("blocked", guard.BLOCK_MESSAGE)  # LLM을 부르기 전에 끝낸다
        now = await self._clock.now()
        today = now.date()
        fixed = self._corrector.correct(clean)
        notes = [c.describe() for c in fixed.corrections]
        if fixed.needs_confirmation:  # 확신이 중간이면 고치지 않고 되묻는다(LLM 호출 없음)
            asks = [s.describe() for s in fixed.suggestions]
            return AnswerCard("clarify", " ".join(asks), corrections=notes, suggestions=asks)
        q = fixed.text
        ranking = rank_cards(q, self._catalog)

        if ranking.planned and not any(c.direct for c in ranking.candidates):
            names = ", ".join(c.name for c in ranking.planned[:2])
            await self._record(now, "planned_api", "unknown", ranking, q, [c.id for c in ranking.planned])
            return AnswerCard(
                "planned",
                f"'{names}'은(는) 아직 채산에 연결하지 않은 데이터예요. 연결 예정 목록에 기록해 둘게요.",
                corrections=notes,
            )

        top = ranking.candidates[0].card if ranking.candidates else None
        data_range = _card_range(top) if top else None
        prefer: Prefer = "future" if top is not None and top.group == "events_news" else "past"
        when = parse_when(q, today, data_range, prefer)
        if when is not None and when.conflict:
            return AnswerCard("clarify", MSG_CONFLICT, corrections=notes)
        if when is not None and when.future and top is not None and top.group in FORECAST_GROUPS:
            await self._record(now, "planned_api", "unknown", ranking, q, [])
            return AnswerCard("planned", MSG_FUTURE, corrections=notes)

        plan, evidence = await self._plan_and_run(q, today, when, ranking, ctx)
        if plan is None:  # 계획을 두 번 시도했지만 쓸 만한 계획이 없다
            return AnswerCard("unknown", MSG_UNKNOWN, corrections=notes)
        ctx.intent, ctx.plan_ok = plan.intent, True
        if not plan.answerable:
            await self._record(now, "no_data", plan.intent, ranking, q, [])
            return AnswerCard("unknown", MSG_UNKNOWN, corrections=notes)
        if evidence is None or evidence.kind == "none":
            await self._record(now, "no_evidence", plan.intent, ranking, q, plan.card_ids)
            latest = await self._latest_outside_window(plan, when, today, ctx)
            return AnswerCard("unknown", latest or MSG_UNKNOWN, corrections=notes)
        try:
            return await self._finish(q, today, when, evidence, notes, ctx)
        except _NotAnswering:  # 근거가 질문과 맞지 않는다: 억지로 답하지 않고 모른다고 하며 수요로 남긴다
            await self._record(now, "no_data", plan.intent, ranking, q, plan.card_ids)
            return AnswerCard("unknown", MSG_UNKNOWN, corrections=notes)

    # ------------------------------------------------------------------ 계획 + 실행(재계획 1회)

    async def _llm_json(
        self, ctx: _Ctx, parts: tuple[str, str, str], schema: dict[str, Any], max_tokens: int, temperature: float
    ) -> dict[str, Any]:
        if ctx.calls >= MAX_LLM_CALLS:
            raise _Budget
        task, data, instruction = parts
        nonce, canary = guard.new_nonce(), guard.new_canary()
        system = guard.build_system_prompt(task, nonce, canary)
        user = f"{guard.wrap_untrusted(data, nonce)}\n\n{instruction}"
        ctx.calls += 1
        res = await self._llm.chat_json(system, user, schema, max_tokens=max_tokens, temperature=temperature)
        ctx.input_tokens += res.input_tokens
        ctx.output_tokens += res.output_tokens
        return guard.parse_guarded_json(res.text, canary)

    async def _plan_and_run(
        self, q: str, today: date, when: When | None, ranking: Ranking, ctx: _Ctx
    ) -> tuple[Plan | None, _Evidence | None]:
        cands = {c.card.id: c.card for c in ranking.candidates}
        feedback: str | None = None
        for attempt in range(2):  # 계획 1회 + 재계획 1회
            parts = build_plan_prompt(q, today, when, ranking.candidates, feedback)
            # 재계획은 온도를 올린다: 온도 0이면 같은 입력에 같은 출력이 나와 거부된 계획을 그대로 되풀이한다(실제 모델에서 관찰)
            temperature = 0.0 if attempt == 0 else 0.4
            try:
                data = await self._llm_json(ctx, parts, PLAN_SCHEMA, PLAN_MAX_TOKENS, temperature)
                plan = parse_plan(data, cands, period_ok=bool(when and when.start and when.end))
                if not plan.answerable:
                    return plan, None
                return plan, await self._execute(plan, q, when, cands, ctx)
            except guard.OutputRejected:
                feedback = "JSON 형식이 올바르지 않다"
            except PlanError as exc:
                feedback = str(exc)
            except SqlRejected as exc:
                feedback = f"SQL 검사를 통과하지 못했다({exc})"
            except _QueryFailed:
                feedback = "SQL 실행 오류(후보의 표·열 이름을 그대로 쓴다)"
        return None, None

    async def _execute(self, plan: Plan, q: str, when: When | None, cands: Mapping[str, Card], ctx: _Ctx) -> _Evidence:
        ev = _Evidence()
        used: dict[str, Card] = {}
        if plan.sql:
            allowed = {t for i in plan.card_ids for t in cands[i].tables}
            sql = validate_sql(plan.sql, allowed)  # 실행 직전 검사: 계획 단계의 검사와 별개로 한 번 더
            try:
                res = await self._db.query(sql)
            except Exception as exc:  # DB 오류 종류는 어댑터마다 다르다(sqlite3.Error, D1 오류 …)
                logger.warning("chaesan sql failed: %s", type(exc).__name__)
                raise _QueryFailed from exc
            ctx.rows_read += res.rows_read
            logger.info("chaesan query rows_read=%d rows=%d", res.rows_read, len(res.rows))
            ev.rows = res.rows[:SQL_ROW_LIMIT]
            ev.sql = sql
            words = set(re.findall(r"[a-z0-9_]+", sql.lower()))
            used.update({c.id: c for c in cands.values() if any(t.lower() in words for t in c.tables)})
        sources = [i for i in plan.card_ids if i in DOC_SOURCES]
        period = when is not None and when.start is not None and when.end is not None
        if sources and (plan.search_terms or period):
            order = self._order(q, plan.intent)
            docs: SearchResult | None = None
            if plan.search_terms:
                names = {i: terms for i, terms in self._boost_names.items() if i in sources}
                docs = await search_docs(
                    self._db,
                    plan.search_terms,
                    weights=self._weights,
                    source_ids=sources,
                    boosted=boosted_sources(q, names),
                    start=when.start if when else None,
                    end=when.end if when else None,
                    order=order,
                    limit=DOC_HITS,
                )
                ctx.rows_read += docs.rows_read
            if (docs is None or not docs.hits) and period and when is not None:
                # 검색어가 문서 본문에 없어도(예: '2020년 12월', '연혁') 코드가 해석한 기간만으로 목록을 뽑는다
                docs = await list_docs_in_period(
                    self._db,
                    weights=self._weights,
                    source_ids=sources,
                    start=when.start,
                    end=when.end,
                    order=order,
                    limit=DOC_HITS,
                )
                ctx.rows_read += docs.rows_read
            if docs is not None:
                ev.hits = docs.hits
                ev.total, ev.first_date, ev.last_date, ev.capped = docs.total, docs.first_date, docs.last_date, docs.capped
                used.update({h.source_id: cands[h.source_id] for h in ev.hits if h.source_id in cands})
        ev.cards = list(used.values())
        return ev

    async def _latest_outside_window(self, plan: Plan, when: When | None, today: date, ctx: _Ctx) -> str | None:
        """해석한 기간 안에 문서가 없을 때, 같은 출처에서 가장 최근 기록이 언제인지(코드가 센 값)를 알려 준다.
        '요즘 무슨 행사가?'에 그냥 '근거가 없어요'라고만 하면, 자료가 오래돼서 없는 것인지 처음부터 없는 것인지 알 수 없다."""
        sources = [i for i in plan.card_ids if i in DOC_SOURCES]
        if when is None or when.start is None or when.end is None or not sources:
            return None
        res = await list_docs_in_period(
            self._db, weights=self._weights, source_ids=sources, start=date(1900, 1, 1), end=today, order="date_desc", limit=1
        )
        ctx.rows_read += res.rows_read
        if res.last_date is None:
            return None
        return f"{when.label}({when.start}~{when.end}) 기간의 기록은 없어요. 이 자료에서 가장 최근 기록은 {res.last_date}예요."

    @staticmethod
    def _order(q: str, intent: str) -> Literal["score", "date_asc", "date_desc"]:
        """'언제부터·처음'이면 오래된 순, '최근·마지막'(또는 소식 갈래)이면 최신순. 안 그러면 점수순.
        상위 몇 건만 보여 주면서 '처음'을 말하면 틀리므로, 날짜 질문의 정렬은 LLM이 아니라 코드가 정한다."""
        if _ASC.search(q):
            return "date_asc"
        if _DESC.search(q) or intent == "news":
            return "date_desc"
        return "score"

    @staticmethod
    def _evidence_lines(ev: _Evidence, names: Mapping[str, str]) -> list[str]:
        lines: list[str] = []
        if ev.hits:
            note = " (검색 후보 상한에 걸려 일부일 수 있어요)" if ev.capped else ""
            lines.append(
                f"[요약] 일치하는 문서 총 {ev.total}건, 가장 이른 날짜 {ev.first_date}, 가장 늦은 날짜 {ev.last_date}{note}. "
                f"아래는 그중 {len(ev.hits)}건."
            )
        for i, row in enumerate(ev.rows[:EVIDENCE_ROWS_FOR_LLM], start=1):
            cells = ", ".join(f"{k}={guard.sanitize_untrusted(str(v), 80)[0]}" for k, v in row.items())
            lines.append(f"{i}) {cells}")
        for h in ev.hits:
            body = f" / {guard.sanitize_untrusted(h.body, 120)[0]}" if h.body else ""
            title = guard.sanitize_untrusted(h.title, 120)[0]  # 데이터 속 지시문은 삭제한 사본만 LLM에 준다
            lines.append(f"- [{h.doc_date or '날짜 없음'}] {title}{body} (출처 {names.get(h.source_id, h.source_id)})")
        return lines

    async def _finish(self, q: str, today: date, when: When | None, ev: _Evidence, notes: list[str], ctx: _Ctx) -> AnswerCard:
        names = {c.id: c.name for c in ev.cards}
        caveats = [cv for c in ev.cards[:1] for cv in c.caveats]
        count = len(ev.rows) if ev.rows else len(ev.hits)
        unsupported: list[str] = []
        answer = fallback_answer("table" if ev.rows else "documents", count)
        try:
            data = await self._llm_json(
                ctx,
                build_explain_prompt(
                    q,
                    self._evidence_lines(ev, names),
                    caveats,
                    schema_lines(ev.cards),
                    [guard.sanitize_untrusted(ev.sql, 400)[0]] if ev.sql else [],
                ),
                ANSWER_SCHEMA,
                ANSWER_MAX_TOKENS,
                0.2,
            )
            if data.get("answers_question") is False:
                raise _NotAnswering
            text = guard.sanitize_output_text(data.get("answer"), MAX_ANSWER_CHARS)
            if text:
                allowed: list[dict[str, Any]] = [
                    *ev.rows,
                    *({"title": h.title, "date": h.doc_date, "body": h.body} for h in ev.hits),
                    {"n": count, "total": ev.total, "shown": len(ev.hits)},
                    {"first": ev.first_date, "last": ev.last_date},
                    {"periods": [f"{c.period_start}~{c.period_end}" for c in ev.cards]},
                    {"when": [str(when.start), str(when.end)] if when and when.start else []},
                ]
                unsupported = find_unsupported_numbers(text, allowed)
                ctx.hangul_number = has_hangul_number(text)
                if not unsupported and not ctx.hangul_number:
                    answer = text  # 숫자 대조를 통과한 설명만 쓴다. 아니면 숫자 없는 대체 답 + 근거 표
        except (guard.OutputRejected, _Budget):
            logger.info("chaesan explanation skipped")
        badges: list[str] = []
        for c in ev.cards:
            badges += [b for b in card_badges(c, today) if b not in badges]
        if any(not h.body_available for h in ev.hits) and NO_BODY_BADGE not in badges:
            badges.append(NO_BODY_BADGE)
        sources = [
            {
                "id": c.id,
                "name": c.name,
                "period": f"{c.period_start}~{c.period_end}" if c.period_start else None,
                "url": c.portal_url,
            }
            for c in ev.cards
        ]
        docs = [
            {
                "title": h.title,
                "date": h.doc_date,
                "source": names.get(h.source_id, h.source_id),
                "url": h.url,
                "body_available": h.body_available,
            }
            for h in ev.hits
        ]
        return AnswerCard("answered", answer, ev.kind, ev.rows, docs, sources, badges, notes, [], unsupported)

    # ------------------------------------------------------------------ 개방 수요 기록

    async def _record(
        self, now: Any, reason: demand.Reason, intent: str, ranking: Ranking, q: str, card_ids: Sequence[str]
    ) -> None:
        if self._sink is None:
            return
        top: Candidate | None = ranking.candidates[0] if ranking.candidates and not ranking.fallback else None
        ids = list(card_ids) or ([top.card.id] if top else [])
        group = top.card.group if top else None
        rec = demand.make_record(
            now=now, reason=reason, intent=intent, group=group, card_ids=ids, terms=demand.topic_terms(q, self._whitelist)
        )
        try:
            await self._sink.record(rec)
        except Exception:  # 기록 실패가 답을 막으면 안 된다
            logger.warning("chaesan demand sink failed")
