"""문서 키워드 검색 (로컬·서비스 공통, 표준 라이브러리만).

LLM은 검색어(search_terms)만 고르고, 검색은 이 코드가 한다(LLM이 지어낸 문서가 끼어들 수 없다).

- 3글자 이상 검색어: FTS5 trigram 색인(MATCH). 검색어를 큰따옴표로 감싸 하나의 구절로 다루고, 안의 큰따옴표는
  두 번 써서 이스케이프한다 → 검색어에 `*`, `-`, `NEAR`, `OR` 같은 FTS 문법이 들어 있어도 문법으로 해석되지 않는다.
- 2글자 이하 검색어("수영", "주차"): trigram은 3글자 미만을 찾지 못하므로 LIKE로 보완한다. D1의 LIKE 패턴은 50바이트
  제한이 있어(한글 약 16자) 검색어를 잘라 넣고, `%`·`_`는 이스케이프해 와일드카드로 쓰이지 않게 한다.
- 점수 = (맞은 검색어 비율 + 제목에서 맞으면 가산 + 작은 bm25 보정) × 데이터 등급 가중치.
  질문에 데이터 이름·별칭이 직접 나오면 그 데이터의 가중치를 1.0으로 올린다(boosted).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Final, Literal

from app.chaesan.core.ports import DB

MAX_TERMS: Final = 6  # 검색어 개수 상한(LLM이 길게 내도 쿼리 수가 늘지 않게)
MAX_TERM_CHARS: Final = 16  # D1 LIKE 50바이트 제한: 한글 3바이트 × 16 = 48
MIN_TERM_CHARS: Final = 2  # 1글자 검색어(꽃, 물)는 뜻이 너무 넓어 잡음만 늘린다 → 버린다
_NOT_WORD: Final = re.compile(r"[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ]+")
TRIGRAM_MIN: Final = 3
CANDIDATES_PER_TERM: Final = 200  # 검색어 하나가 가져올 후보 상한(읽는 행 수 보호)
TITLE_BONUS: Final = 0.2
RANK_WEIGHT: Final = 0.1

type Order = Literal["score", "date_desc", "date_asc"]
type Mode = Literal["fts", "like"]

_COLUMNS: Final = (
    "d.doc_id, d.source_id, d.source_row, d.title, d.body, d.extra, d.doc_date, d.url, d.body_available, d.suspicious"
)


def squash_text(text: str) -> str:
    """검색용 정규화: NFC·소문자로 바꾸고 글자·숫자 외(띄어쓰기, 기호)를 모두 뺀다.
    한국어는 띄어쓰기가 제각각이라('장미 축제' / '장미축제') 양쪽을 같은 모양으로 맞춰야 찾는다. 색인과 검색어에 똑같이 쓴다."""
    return _NOT_WORD.sub("", unicodedata.normalize("NFC", text).lower())


@dataclass(frozen=True, slots=True)
class Hit:
    doc_id: int
    source_id: str
    source_row: int
    title: str
    body: str | None
    doc_date: str | None
    url: str | None
    body_available: bool
    suspicious: bool
    score: float
    matched_terms: tuple[str, ...]


@dataclass(slots=True)
class SearchResult:
    hits: list[Hit] = field(default_factory=list)
    rows_read: int = 0  # 이 검색이 읽은 행 수(하루 한도 점검용 로그)
    terms: tuple[str, ...] = ()  # 실제로 쓴 검색어(정리 후)
    # 상위 limit건만이 아니라 조건에 맞는 문서 전체에 대한 요약(코드가 센 값). "언제부터", "몇 건" 같은 질문은 이 값으로 답한다.
    total: int = 0
    first_date: str | None = None
    last_date: str | None = None
    capped: bool = False  # 검색어 하나가 후보 상한(CANDIDATES_PER_TERM)에 걸려 total·날짜가 일부일 수 있다


def clean_terms(terms: Sequence[str]) -> list[str]:
    """검색어 정리: squash 정규화, 너무 짧은 것·중복 제거, 길이·개수 제한. 순서는 유지한다."""
    out: list[str] = []
    for raw in terms:
        t = squash_text(str(raw))[:MAX_TERM_CHARS]
        if len(t) >= MIN_TERM_CHARS and t not in out:
            out.append(t)
        if len(out) >= MAX_TERMS:
            break
    return out


def fts_phrase(term: str) -> str:
    """FTS5 MATCH에 넣을 구절. 큰따옴표로 감싸고 안의 큰따옴표는 두 번 써서 FTS 문법 주입을 막는다."""
    return '"' + term.replace('"', '""') + '"'


def like_pattern(term: str) -> str:
    """LIKE 패턴. `\\`를 이스케이프 문자로 쓰고 `%`·`_`를 글자 그대로 찾게 한다."""
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _in_clause(values: Collection[str] | None) -> tuple[str, tuple[str, ...]]:
    if not values:
        return "", ()
    vals = tuple(values)
    return f" AND d.source_id IN ({', '.join('?' * len(vals))})", vals


def _doc_span(doc_date: str | None) -> tuple[date, date] | None:
    """'YYYY-MM-DD' 또는 'YYYY-MM' 또는 'YYYY' 문서 날짜가 걸치는 기간."""
    if not doc_date:
        return None
    try:
        parts = [int(p) for p in doc_date.split("-")]
        if len(parts) == 1:
            return date(parts[0], 1, 1), date(parts[0], 12, 31)
        if len(parts) == 2:
            first = date(parts[0], parts[1], 1)
            return first, (date(parts[0] + (parts[1] == 12), parts[1] % 12 + 1, 1) - timedelta(days=1))
        return date(*parts), date(*parts)
    except (ValueError, TypeError):
        return None


def _in_period(doc_date: str | None, start: date | None, end: date | None) -> bool:
    if start is None and end is None:
        return True
    span = _doc_span(doc_date)
    if span is None:
        return False  # 날짜를 모르는 문서는 기간 조건이 있으면 제외한다(날짜를 지어내지 않는다)
    return (end is None or span[0] <= end) and (start is None or span[1] >= start)


def boosted_sources(question: str, names: Mapping[str, Sequence[str]]) -> set[str]:
    """질문에 데이터 이름·별칭이 직접 나오는 출처. names: 카드 번호 → [이름, 별칭…]."""
    q = squash_text(question)
    return {sid for sid, words in names.items() if any(len(sw := squash_text(w)) >= MIN_TERM_CHARS and sw in q for w in words)}


async def search_docs(
    db: DB,
    terms: Sequence[str],
    *,
    weights: Mapping[str, float],
    source_ids: Collection[str] | None = None,
    boosted: Collection[str] = (),
    start: date | None = None,
    end: date | None = None,
    order: Order = "score",
    limit: int = 10,
    mode: Mode = "fts",
) -> SearchResult:
    """검색어로 문서를 찾는다. 결과가 없으면 빈 hits(= 근거 없음 → 모른다고 답한다).

    weights: 출처(카드 번호) → 등급 가중치. 목록에 없는 출처는 0.5(B)로 본다.
    mode="like"는 FTS5를 쓸 수 없는 환경(예: 서비스에서 trigram 미지원)을 위한 대비다.
    """
    cleaned = clean_terms(terms)
    result = SearchResult(terms=tuple(cleaned))
    # source_ids가 None이면 모든 출처, 빈 목록이면 '허용된 출처가 없음'이다(빈 목록을 '전체'로 읽으면 보안·정확성 사고가 난다)
    if not cleaned or limit <= 0 or (source_ids is not None and len(source_ids) == 0):
        return result
    src_sql, src_params = _in_clause(source_ids)
    found: dict[int, dict[str, Any]] = {}

    async def run(sql: str, params: tuple[Any, ...], term: str) -> None:
        res = await db.query(sql, params)
        result.rows_read += res.rows_read
        if len(res.rows) >= CANDIDATES_PER_TERM:
            result.capped = True
        for row in res.rows:
            slot = found.setdefault(row["doc_id"], {"row": row, "terms": set(), "rank": 0.0})
            slot["terms"].add(term)
            slot["rank"] = min(slot["rank"], float(row.get("rank") or 0.0))  # bm25는 작을수록(음수일수록) 좋다

    for term in cleaned:
        if mode == "fts" and len(term) >= TRIGRAM_MIN:
            sql = (
                f"SELECT {_COLUMNS}, bm25(docs_fts) AS rank FROM docs_fts JOIN docs d ON d.doc_id = docs_fts.rowid "  # noqa: S608
                f"WHERE docs_fts MATCH ?{src_sql} ORDER BY rank LIMIT {CANDIDATES_PER_TERM}"
            )
            await run(sql, (fts_phrase(term), *src_params), term)
        else:
            pat = like_pattern(term)
            sql = (
                f"SELECT {_COLUMNS}, 0.0 AS rank FROM docs d "  # noqa: S608
                f"WHERE d.squash LIKE ? ESCAPE '\\'{src_sql} "
                f"LIMIT {CANDIDATES_PER_TERM}"
            )
            await run(sql, (pat, *src_params), term)

    scored: list[Hit] = []
    for doc_id, slot in found.items():
        row = slot["row"]
        if not _in_period(row["doc_date"], start, end):
            continue
        matched = tuple(t for t in cleaned if t in slot["terms"])
        in_title = any(t in squash_text(row["title"]) for t in matched)
        base = len(matched) / len(cleaned) + (TITLE_BONUS if in_title else 0.0)
        base += RANK_WEIGHT / (1.0 + abs(slot["rank"]))  # bm25는 같은 점수대의 순서를 정하는 보정으로만 쓴다
        weight = 1.0 if row["source_id"] in boosted else weights.get(row["source_id"], 0.5)
        scored.append(
            Hit(
                doc_id=doc_id, source_id=row["source_id"], source_row=row["source_row"], title=row["title"], body=row["body"],
                doc_date=row["doc_date"], url=row["url"], body_available=bool(row["body_available"]),
                suspicious=bool(row["suspicious"]), score=round(base * weight, 6), matched_terms=matched,
            )
        )  # fmt: skip
    dates = [h.doc_date for h in scored if h.doc_date]
    result.total = len(scored)
    result.first_date = min(dates) if dates else None
    result.last_date = max(dates) if dates else None
    if order == "date_asc":
        scored.sort(key=lambda h: (h.doc_date is None, h.doc_date or "", -h.score, h.doc_id))
    elif order == "date_desc":
        scored.sort(key=lambda h: (h.doc_date or "", h.score), reverse=True)
    else:
        scored.sort(key=lambda h: (-h.score, -(len(h.matched_terms)), h.doc_id))
    result.hits = scored[:limit]
    return result


def _hit(row: Mapping[str, Any], score: float, matched: tuple[str, ...]) -> Hit:
    return Hit(
        doc_id=row["doc_id"], source_id=row["source_id"], source_row=row["source_row"], title=row["title"], body=row["body"],
        doc_date=row["doc_date"], url=row["url"], body_available=bool(row["body_available"]),
        suspicious=bool(row["suspicious"]), score=score, matched_terms=matched,
    )  # fmt: skip


async def list_docs_in_period(
    db: DB,
    *,
    weights: Mapping[str, float],
    source_ids: Collection[str],
    start: date | None,
    end: date | None,
    order: Order = "date_desc",
    limit: int = 10,
) -> SearchResult:
    """검색어 없이 기간(코드가 해석한 값)만으로 문서를 나열한다. '○년 ○월에 무슨 일이 있었어?'처럼 기간이 질문의 전부일 때 쓴다.
    날짜 칸이 없는 문서는 제외한다(날짜를 지어내지 않는다). 요약(total·first·last)은 일치한 전체 기준이다."""
    result = SearchResult()
    if limit <= 0 or not source_ids or (start is None and end is None):
        return result
    src_sql, src_params = _in_clause(source_ids)
    lo = start.strftime("%Y-%m") if start else "0000-00"
    hi = end.strftime("%Y-%m") if end else "9999-99"
    sql = (
        f"SELECT {_COLUMNS}, 0.0 AS rank FROM docs d "  # noqa: S608
        f"WHERE d.doc_date IS NOT NULL AND substr(d.doc_date, 1, 7) >= ? AND substr(d.doc_date, 1, 7) <= ?{src_sql} "
        f"ORDER BY d.doc_date LIMIT {CANDIDATES_PER_TERM}"
    )
    res = await db.query(sql, (lo, hi, *src_params))
    result.rows_read += res.rows_read
    result.capped = len(res.rows) >= CANDIDATES_PER_TERM
    hits = [_hit(r, weights.get(r["source_id"], 0.5), ()) for r in res.rows if _in_period(r["doc_date"], start, end)]
    dates = [h.doc_date for h in hits if h.doc_date]
    result.total = len(hits)
    result.first_date = min(dates) if dates else None
    result.last_date = max(dates) if dates else None
    if order == "date_desc":
        hits.sort(key=lambda h: (h.doc_date or "", h.doc_id), reverse=True)
    elif order == "date_asc":
        hits.sort(key=lambda h: (h.doc_date or "", h.doc_id))
    else:
        hits.sort(key=lambda h: (-h.score, h.doc_date or "", h.doc_id))
    result.hits = hits[:limit]
    return result
