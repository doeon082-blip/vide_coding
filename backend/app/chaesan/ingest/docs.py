"""문서 색인 만들기 (로컬 전용): 문서형 자료를 `docs` 표와 FTS5 전문 색인 `docs_fts`로 모은다.

실행: `uv run python -m app.chaesan.ingest.docs` (backend/ 에서, 먼저 `ingest.load`로 DB를 만들어 둔다)

대상(지시서 D단계): FAQ(15089962), 연혁, 언론보도(15137825), 보도자료(15137824), 핫뉴스(15090715),
잔디시설(15143220), 사전정보공표(15090257, 제목·링크), 사업실명제(15090260, 제목·링크).

- 본문 없이 제목만 있는 자료는 body_available=0으로 표시해, 답변에 "본문 없음, 원문 링크 확인"을 붙이게 한다.
- 원본 표는 건드리지 않고, 검색용 사본(docs)을 따로 만든다. 모든 행은 source_id·source_row로 원본을 되짚을 수 있다.
- 데이터 속에 지시문처럼 보이는 문장이 있는지(suspicious)를 미리 표시한다. 문장을 지우지는 않는다(원본 보존).
- FTS5 trigram 토크나이저: 3글자 단위로 쪼개 색인한다. 한국어는 띄어쓰기·조사 때문에 단어 단위 색인이 잘 안 맞는다.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from app.chaesan.core.guard import detect
from app.chaesan.core.search import squash_text
from app.chaesan.ingest.cards import HISTORY_HTML, HISTORY_URL, parse_history
from app.chaesan.ingest.load import DB_PATH

_SCHEMA: Final = """
DROP TABLE IF EXISTS docs_fts;
DROP TABLE IF EXISTS docs;
CREATE TABLE docs (
  doc_id INTEGER PRIMARY KEY,
  source_id TEXT NOT NULL,          -- 데이터 카드 번호(연혁은 'history')
  source_row INTEGER NOT NULL,      -- 원본 표의 _row (연혁은 페이지 안 항목 순서)
  title TEXT NOT NULL,
  body TEXT,
  extra TEXT,                       -- 검색에만 쓰는 보조 문장(분류, 매체, 부서)
  doc_date TEXT,                    -- YYYY-MM-DD 또는 YYYY-MM
  url TEXT,                         -- 원문 링크(없으면 카드의 포털 주소를 쓴다)
  squash TEXT NOT NULL,             -- 제목·본문·보조 문장에서 띄어쓰기·기호를 뺀 검색용 문장(core.search.squash_text)
  body_available INTEGER NOT NULL,  -- 0이면 제목 수준
  suspicious INTEGER NOT NULL       -- 1이면 지시문처럼 보이는 문장이 들어 있음
);
CREATE INDEX docs_source ON docs (source_id);
CREATE VIRTUAL TABLE docs_fts USING fts5(squash, tokenize='trigram');
"""

_WS = re.compile(r"\s+")
_HTTP_URL = re.compile(r"https?://\S+", re.IGNORECASE)


def safe_url(url: str | None) -> str | None:
    """데이터에서 온 링크는 http(s)만 남긴다. 상대 경로·javascript: 같은 값은 답변 링크로 쓰지 않는다(데이터는 믿지 않는다)."""
    cleaned = clean(url)
    return cleaned if cleaned and _HTTP_URL.fullmatch(cleaned) else None


def clean(text: str | None) -> str | None:
    """색인용 문장: 유니코드 정규화(NFC)·공백 정리. 비면 None. 원본 표는 그대로 둔다."""
    if text is None:
        return None
    out = _WS.sub(" ", unicodedata.normalize("NFC", text)).strip()
    return out or None


@dataclass(frozen=True, slots=True)
class Source:
    source_id: str
    table: str
    title: str  # 제목으로 쓸 SQL 식
    body: str | None
    extra: str | None
    doc_date: str | None
    url: str | None
    body_available: bool


SOURCES: Final[tuple[Source, ...]] = (
    Source("15089962", "t_15089962", "title", "content", None, "reg_date", None, True),
    Source("15137825", "t_15137825", "title", None, "media", "report_date", None, False),
    Source("15137824", "t_15137824", "title", None, "media", "release_date", None, False),
    Source("15090715", "t_15090715", "title", None, None, "reg_date", "url", False),
    Source("15143220", "t_15143220", "place", "open_label || ': ' || open_detail", None, None, "url", True),
    Source(
        "15090257", "t_15090257", "title", None, "COALESCE(major, '') || ' ' || COALESCE(minor, '')", "reg_date", "url", False
    ),
    Source("15090260", "t_15090260", "title", None, "dept", "reg_date", None, False),
)


class DocsError(RuntimeError):
    """문서 색인을 만들 수 없다."""


def build_docs(con: sqlite3.Connection, history_html: Path = HISTORY_HTML) -> dict[str, int]:
    """docs와 docs_fts를 다시 만든다(한 트랜잭션: 중간에 실패하면 이전 색인이 그대로 남는다). 반환: 출처별 문서 수."""
    counts: dict[str, int] = {}
    # 표 삭제·생성(DDL)까지 한 트랜잭션에 넣는다. 파이썬 sqlite3는 DDL 앞에서 트랜잭션을 자동으로 열지 않아,
    # 명시적으로 BEGIN 하지 않으면 중간에 실패해도 이미 지운 이전 색인이 돌아오지 않는다.
    con.execute("BEGIN IMMEDIATE")
    try:
        for stmt in (s.strip() for s in _SCHEMA.split(";") if s.strip()):
            con.execute(stmt)
        rows: list[tuple[str, int, str, str | None, str | None, str | None, str | None, int, int]] = []
        for src in SOURCES:
            cols = [src.title, src.body or "NULL", src.extra or "NULL", src.doc_date or "NULL", src.url or "NULL"]
            sql = f"SELECT _row, {', '.join(cols)} FROM {src.table} ORDER BY _row"
            n = 0
            for row_no, title, body, extra, date, url in con.execute(sql).fetchall():
                t = clean(title)
                if t is None:
                    continue  # 제목이 없는 행은 검색할 수 없다
                b, e = clean(body), clean(extra)
                rows.append((src.source_id, row_no, t, b, e, date, safe_url(url), int(src.body_available), 0))
                n += 1
            counts[src.source_id] = n
        entries = parse_history(history_html.read_text(encoding="utf-8", errors="replace"))
        for i, ent in enumerate(entries, start=1):
            date = f"{ent.year}-{ent.month:02d}" if ent.month else str(ent.year)
            rows.append(("history", i, clean(ent.text) or "", None, None, date, HISTORY_URL, 1, 0))
        counts["history"] = len(entries)
        for r in rows:
            flagged = int(detect(" ".join(x for x in (r[2], r[3], r[4]) if x)).flagged)
            con.execute(
                "INSERT INTO docs (source_id, source_row, title, body, extra, doc_date, url, squash, body_available, suspicious) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*r[:7], squash_text(" ".join(x for x in (r[2], r[3], r[4]) if x)), r[7], flagged),
            )
        con.execute("INSERT INTO docs_fts (rowid, squash) SELECT doc_id, squash FROM docs")
        con.execute("INSERT OR REPLACE INTO meta_build VALUES ('docs_built', ?)", (str(sum(counts.values())),))
        total = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        fts = con.execute("SELECT COUNT(*) FROM docs_fts").fetchone()[0]
        if not total == fts == sum(counts.values()):
            raise DocsError(f"문서 수 불일치: docs {total}, fts {fts}, 출처 합 {sum(counts.values())}")
    except BaseException:
        con.rollback()
        raise
    con.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="채산 문서 색인(docs, docs_fts)을 만든다.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()
    con = sqlite3.connect(args.db)
    try:
        counts = build_docs(con)
        suspicious = con.execute("SELECT COUNT(*) FROM docs WHERE suspicious=1").fetchone()[0]
    finally:
        con.close()
    print(f"문서 {sum(counts.values())}건: {counts}")
    print(f"지시문처럼 보이는 문서: {suspicious}건")


if __name__ == "__main__":
    main()
