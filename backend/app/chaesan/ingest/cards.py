"""데이터 카드 생성 (로컬 전용).

실행: `uv run python -m app.chaesan.ingest.cards` (backend/ 에서, 먼저 `ingest.load`로 DB를 만들어 둔다)
- 입력: data/chaesan.sqlite, data/raw/web/history.html, card_meta.py(사람이 확인한 뜻·주의점)
- 출력: data/cards/<번호>.json, data/cards/_groups.json, data/cards/_index.json

카드의 사실(행 수·실제 기간·열 정보)은 DB에서 직접 뽑고, 손으로 쓰는 값은 card_meta.py에만 둔다.
둘이 어긋나면(명세에 없는 데이터, 없는 묶음, 예시 질문 3개 미만 등) 조용히 넘어가지 않고 CardError로 멈춘다.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from app.chaesan.core.config import TIER_WEIGHTS
from app.chaesan.ingest.card_meta import (
    API_TIER_A_KEYWORDS,
    GROUPS,
    HISTORY_ID,
    HISTORY_META,
    META,
    Meta,
)
from app.chaesan.ingest.load import BACKEND_DIR, DB_PATH
from app.chaesan.ingest.specs import SPECS, FileSpec
from app.chaesan.local.db import ro_uri

CARDS_DIR: Final = BACKEND_DIR / "data" / "cards"
HISTORY_HTML: Final = BACKEND_DIR / "data" / "raw" / "web" / "history.html"
HISTORY_URL: Final = "https://www.ksponco.or.kr/menu.es?mid=a10601030000"
OPENDATA_LIST_ID: Final = "15147873"
NAME_PREFIX: Final = "한국체육산업개발주식회사_"

# 오픈API 항목을 주제 묶음에 넣는 규칙(이름만 보고 정한 것, 내용 미확인). 위에서부터 먼저 맞는 것.
_API_GROUPS: Final[tuple[tuple[tuple[str, ...], str], ...]] = (
    (("공연",), "performances"),
    (("보도자료",), "history_press"),
    (("공지사항", "올팍소식"), "events_news"),
    (("스포츠센터", "수영장", "축구장", "스케이트장", "교육강좌", "월회원"), "sports_courses"),
    (("운영현황", "유실물", "수목", "장미광장", "대관", "도서", "테니스장"), "facility_usage"),
    (("채용", "협력기관", "수상", "사회공헌"), "org_disclosure"),
    (("갤러리", "포토", "홍보동영상"), "media_gallery"),
)

_SAFE_EXPR = re.compile(r"^[a-z_0-9(),'%\- ]+$")  # 메타 상수에 들어 있는 SQL 식만 허용(사용자 입력은 절대 아님)


class CardError(RuntimeError):
    """카드 메타와 실제 데이터가 맞지 않다."""


def _check_expr(expr: str) -> str:
    if not _SAFE_EXPR.match(expr) or "--" in expr:  # '--'는 SQL 주석이라 뒤쪽 조건을 가릴 수 있다
        raise CardError(f"허용되지 않는 SQL 식: {expr!r}")
    return expr


def _period(con: sqlite3.Connection, table: str, meta: Meta) -> dict[str, Any] | None:
    if meta.time_expr is None:
        return None
    t = _check_expr(meta.time_expr)
    end = _check_expr(meta.end_expr) if meta.end_expr else None
    # 9999-…는 '종료일 없음(운영 중 표시)'이라 기간의 끝으로 세지 않는다
    sql = f"SELECT MIN({t}), MAX({t})" + (f", MAX(CASE WHEN {end} < '9999' THEN {end} END)" if end else "")
    sql += f" FROM {table} WHERE {t} IS NOT NULL AND {t} < '9999'"
    row = con.execute(sql).fetchone()
    start, last = row[0], row[1]
    stop = max(x for x in (last, row[2] if end else None) if x) if last else None
    if start is None:
        return None
    return {"start": start, "end": stop, "precision": "month" if "printf" in t else "day", "basis": meta.time_expr}


def _columns(con: sqlite3.Connection, table: str, meta: Meta) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, ko, kind, sql_type, nulls, raws in con.execute(
        "SELECT column_name, ko_name, kind, sql_type, null_count, raw_count "
        "FROM meta_columns WHERE table_name=? ORDER BY position",
        (table,),
    ):
        out.append(
            {"name": name, "ko": ko, "kind": kind, "sql_type": sql_type, "null_count": nulls, "raw_kept": raws,
             "note": meta.column_notes.get(name)}
        )  # fmt: skip
    unknown = set(meta.column_notes) - {c["name"] for c in out}
    if unknown:
        raise CardError(f"{table}: 없는 열에 대한 주석 {sorted(unknown)}")
    return out


def _validate_meta(spec_id: str, meta: Meta) -> None:
    if meta.group not in GROUPS:
        raise CardError(f"{spec_id}: 없는 묶음 {meta.group}")
    if meta.tier not in TIER_WEIGHTS:
        raise CardError(f"{spec_id}: 없는 등급 {meta.tier}")
    if len(set(meta.questions)) != 3 or not all(q.strip() for q in meta.questions):
        raise CardError(f"{spec_id}: 예시 질문은 서로 다른 3개여야 한다")
    if not meta.tier_reason.strip() or not meta.summary.strip():
        raise CardError(f"{spec_id}: 등급 이유·요약이 비어 있다")


def file_card(con: sqlite3.Connection, spec: FileSpec, meta: Meta) -> dict[str, Any]:
    _validate_meta(spec.id, meta)
    load = con.execute("SELECT rows, file_name, encoding, sha256 FROM meta_load WHERE table_name=?", (spec.table,)).fetchone()
    if load is None:
        raise CardError(f"{spec.id}: DB에 표가 없다(먼저 ingest.load)")
    period = _period(con, spec.table, meta)
    return {
        "id": spec.id, "name": spec.title, "kind": "file", "loaded": True,
        "portal_url": f"https://www.data.go.kr/data/{spec.id}/fileData.do",
        "table": spec.table,
        "aggregate_tables": ["s_parking_hourly"] if spec.id == "15138735" else [],
        "in_service": not spec.local_only,  # 큰 원본은 로컬에만 두고 서비스에는 집계 표만 올린다
        "group": meta.group, "tier": meta.tier, "weight": TIER_WEIGHTS[meta.tier], "tier_reason": meta.tier_reason,
        "source_kind": meta.source_kind, "body_available": meta.body_available,
        "summary": meta.summary, "rows": load[0], "period": period,
        "last_data_date": period["end"] if period else None,
        "columns": _columns(con, spec.table, meta),
        "caveats": list(meta.caveats), "example_questions": list(meta.questions), "aliases": list(meta.aliases),
        "load": {"file": load[1], "encoding": load[2], "sha256": load[3]},
    }  # fmt: skip


# --------------------------------------------------------------------------- 연혁(누리집 저장 페이지)

_ITEM = re.compile(r'<div class="item year(\d{4})[^"]*">(.*?)</div><!--', re.DOTALL)
_ENTRY = re.compile(r"<li><span>([^<]*)</span>\s*<em>(.*?)</em></li>", re.DOTALL)


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    year: int
    month: int | None
    text: str


def parse_history(html: str) -> list[HistoryEntry]:
    """저장한 연혁 페이지에서 (연, 월, 문장)을 뽑는다. 항목 수가 <li> 수와 다르면 멈춘다(파싱 누락 방지)."""
    entries: list[HistoryEntry] = []
    li_total = 0
    for year, body in _ITEM.findall(html):
        li_total += body.count("<li>")
        for label, text in _ENTRY.findall(body):
            m = re.match(r"\s*(\d{1,2})월", label)
            entries.append(HistoryEntry(int(year), int(m.group(1)) if m else None, re.sub(r"\s+", " ", text).strip()))
    if not entries or li_total != len(entries):
        raise CardError(f"연혁 파싱 불일치: <li> {li_total}개, 항목 {len(entries)}개")
    return entries


def history_card(html_path: Path = HISTORY_HTML) -> dict[str, Any]:
    meta = HISTORY_META
    _validate_meta(HISTORY_ID, meta)
    entries = parse_history(html_path.read_text(encoding="utf-8", errors="replace"))

    def key(e: HistoryEntry) -> tuple[int, int]:
        return e.year, e.month or 0

    def fmt(e: HistoryEntry) -> str:
        return f"{e.year}-{e.month:02d}" if e.month else str(e.year)

    first, last = min(entries, key=key), max(entries, key=key)
    return {
        "id": HISTORY_ID, "name": "기관 연혁(누리집)", "kind": "web", "loaded": True,
        "portal_url": HISTORY_URL, "table": None, "aggregate_tables": [], "in_service": True,
        "group": meta.group, "tier": meta.tier, "weight": TIER_WEIGHTS[meta.tier], "tier_reason": meta.tier_reason,
        "source_kind": meta.source_kind, "body_available": meta.body_available,
        "summary": meta.summary, "rows": len(entries),
        "period": {"start": fmt(first), "end": fmt(last), "precision": "month", "basis": "연혁 항목의 연·월"},
        "last_data_date": fmt(last), "columns": [],
        "caveats": list(meta.caveats), "example_questions": list(meta.questions), "aliases": list(meta.aliases),
        "load": {"file": html_path.name, "encoding": "utf-8", "sha256": None},
    }  # fmt: skip


# --------------------------------------------------------------------------- 오픈API(아직 연결 안 됨)


def api_cards(con: sqlite3.Connection) -> list[dict[str, Any]]:
    """개방목록(15147873)에 있는 오픈API 항목의 카드. 본문은 연결하지 않았으므로 loaded=False.
    이름과 링크만 개방목록에서 가져오고, 목록에 없는 설명·기간·행 수는 지어내지 않는다(null = 미확인)."""
    cards: list[dict[str, Any]] = []
    rows = con.execute(
        "SELECT _row, dataset_name, url, description FROM t_15147873 "
        "WHERE url LIKE '%openapi.do' OR url LIKE '%monthlyApi.do' ORDER BY _row"
    ).fetchall()
    for row_no, name, url, desc in rows:
        short = name.removeprefix(NAME_PREFIX)
        m = re.search(r"/data/(\d+)/openapi\.do", url)
        cid = m.group(1) if m else f"ext_{row_no}"  # 포털 번호가 없는 항목은 개방목록의 행 번호로 구분
        tier = "A" if any(k in short for k in API_TIER_A_KEYWORDS) else "B"
        group = next((g for kws, g in _API_GROUPS if any(k in short for k in kws)), None)
        cards.append(
            {
                "id": cid, "name": short, "kind": "api", "loaded": False, "portal_url": url, "table": None,
                "aggregate_tables": [], "in_service": False, "group": group, "tier": tier, "weight": TIER_WEIGHTS[tier],
                "tier_reason": "이름만 보고 기준표로 정함(내용 미확인)", "source_kind": None, "body_available": None,
                "summary": desc, "rows": None, "period": None, "last_data_date": None, "columns": [],
                "caveats": [
                    "아직 연결하지 않은 오픈API다. 질문이 이 데이터를 가리키면 '아직 연결 안 됨'으로 답하고 "
                    "개방 수요가 아니라 '연결 예정'으로 기록한다."
                ],
                "example_questions": [], "aliases": [], "load": None,
            }
        )  # fmt: skip
    ids = [c["id"] for c in cards]
    if len(ids) != len(set(ids)):
        raise CardError(f"오픈API 카드 번호가 겹친다: {ids}")
    return cards


# --------------------------------------------------------------------------- 전체 생성


def build_cards(db_path: Path = DB_PATH, history_html: Path = HISTORY_HTML) -> list[dict[str, Any]]:
    spec_ids = {s.id for s in SPECS}
    if spec_ids != set(META):
        raise CardError(
            f"명세와 카드 메타가 다르다: 메타에만 {sorted(set(META) - spec_ids)}, 명세에만 {sorted(spec_ids - set(META))}"
        )
    con = sqlite3.connect(ro_uri(db_path), uri=True)  # 읽기 전용
    try:
        cards = [file_card(con, s, META[s.id]) for s in SPECS]
        cards.append(history_card(history_html))
        cards += api_cards(con)
    finally:
        con.close()
    ids = [c["id"] for c in cards]
    if len(ids) != len(set(ids)):
        raise CardError("카드 번호가 겹친다")
    by_id = {c["id"]: c for c in cards}
    for gid, g in GROUPS.items():
        rep = by_id.get(g.representative)
        if rep is None or not rep["loaded"] or rep["group"] != gid:
            raise CardError(f"묶음 {gid}의 대표 {g.representative}가 그 묶음의 적재된 카드가 아니다")
    return cards


def _is_card_file(path: Path) -> bool:
    """이 도구가 만든 카드 파일인가: <번호>.json 이름 + 안에 id(이름과 같음)·kind·tier가 있는 JSON 객체."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("id") == path.stem and "kind" in data and "tier" in data


def write_cards(cards: list[dict[str, Any]], out_dir: Path = CARDS_DIR) -> None:
    """카드를 파일로 쓴다. 이전 실행에서 남은 '카드 파일'은 새 목록과 섞이지 않도록 지운다.
    카드가 아닌 JSON(다른 용도의 파일)은 절대 지우지 않는다: --out을 잘못 지정해도 남의 파일이 사라지지 않게."""
    out_dir.mkdir(parents=True, exist_ok=True)
    keep = {f"{c['id']}.json" for c in cards} | {"_groups.json", "_index.json"}
    for old in out_dir.glob("*.json"):
        if old.name not in keep and _is_card_file(old):
            old.unlink()
    for c in cards:
        (out_dir / f"{c['id']}.json").write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    groups = {
        gid: {
            "title": g.title, "representative": g.representative, "rule": g.rule,
            "members": [c["id"] for c in cards if c["group"] == gid],
        }
        for gid, g in GROUPS.items()
    }  # fmt: skip
    (out_dir / "_groups.json").write_text(json.dumps(groups, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index = [{k: c[k] for k in ("id", "name", "kind", "loaded", "group", "tier", "weight")} for c in cards]
    (out_dir / "_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="채산 데이터 카드를 만든다.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--out", type=Path, default=CARDS_DIR)
    args = parser.parse_args()
    cards = build_cards(args.db)
    write_cards(cards, args.out)
    loaded = sum(1 for c in cards if c["loaded"])
    print(f"카드 {len(cards)}개(적재 {loaded}, 미연결 API {len(cards) - loaded}) → {args.out}")


if __name__ == "__main__":
    main()
