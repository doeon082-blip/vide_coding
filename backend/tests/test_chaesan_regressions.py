"""마지막 점검(리뷰)에서 찾은 문제들의 회귀 테스트. 각 테스트에 어떤 문제였는지 적어 둔다."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from app.chaesan.core import search as S
from app.chaesan.core.correct import Corrector, Vocab
from app.chaesan.core.ports import QueryResult
from app.chaesan.ingest import aliases as A
from app.chaesan.ingest.cards import HISTORY_HTML
from app.chaesan.ingest.docs import build_docs, safe_url
from app.chaesan.ingest.load import RAW_DIR, build
from app.chaesan.ingest.specs import SPECS
from app.chaesan.local.db import SqliteDB, ro_uri

HAVE_DATA = all((RAW_DIR / f"{s.id}.csv").is_file() for s in SPECS) and HISTORY_HTML.is_file()
needs_data = pytest.mark.skipif(not HAVE_DATA, reason="원본 데이터 없음")


class CountingDB:
    def __init__(self) -> None:
        self.calls = 0

    async def query(self, sql: str, params: tuple[Any, ...] = ()) -> QueryResult:
        self.calls += 1
        return QueryResult()


def test_empty_source_list_means_no_sources_not_all_sources() -> None:
    """문제: source_ids=[]를 '필터 없음'으로 읽어 전체 출처를 검색했다. None=전체, 빈 목록=아무 출처도 아님."""
    db = CountingDB()
    r = asyncio.run(S.search_docs(db, ["수영장"], weights={}, source_ids=[]))
    assert r.hits == [] and db.calls == 0
    asyncio.run(S.search_docs(db, ["수영장"], weights={}, source_ids=None))
    assert db.calls == 1  # None은 전체 검색


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.ksponco.or.kr/a?b=1", "https://www.ksponco.or.kr/a?b=1"),
        ("  http://example.com/x  ", "http://example.com/x"),
        ("javascript:alert(1)", None),  # 문제: 데이터의 링크가 그대로 답변 링크가 될 수 있었다
        ("/attachFiles/board/0055/x.hwp", None),
        ("data:text/html;base64,AAAA", None),
        ("https://a.com/ 다른글", None),
        ("", None),
        (None, None),
    ],
)
def test_only_http_links_survive(raw: str | None, expected: str | None) -> None:
    assert safe_url(raw) == expected


def test_readonly_uri_survives_awkward_paths(tmp_path: Path) -> None:
    """문제: f"file:{path}?mode=ro"는 경로에 '#', '?', 공백이 있으면 URI가 깨져 엉뚱한 파일을 열거나 실패했다."""
    folder = tmp_path / "a b#c?d%e"
    folder.mkdir()
    path = folder / "x.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (v INTEGER)")
    con.execute("INSERT INTO t VALUES (7)")
    con.commit()
    con.close()
    assert "#" not in ro_uri(path).split("?")[0] and ro_uri(path).endswith("?mode=ro")
    db = SqliteDB(path)
    assert asyncio.run(db.query("SELECT v FROM t")).rows == [{"v": 7}]
    with pytest.raises(sqlite3.OperationalError):
        asyncio.run(db.query("DELETE FROM t"))
    db.close()


def test_suggestion_uses_the_stem_of_the_chosen_word() -> None:
    """문제: 어간이 다른 두 후보가 같은 거리면 되묻기에 엉뚱한 어간이 붙을 수 있었다(고칠 때는 조사가 사라질 수 있는 구조)."""
    dist = {("수영징은", "테니스장"): 1, ("수영징", "수영장"): 1}
    cor = Corrector(Vocab({"수영장": 50, "테니스장": 30}, {}), jamo=lambda s: s, distance=lambda a, b: dist.get((a, b), 99))
    r = cor.correct("수영징은")
    assert r.suggestions and r.suggestions[0].candidates == ("수영장", "테니스장")
    assert r.suggestions[0].original == "수영징"  # 1순위 후보 '수영장'과 같은 어간
    only = Corrector(Vocab({"수영장": 50}, {}), jamo=lambda s: s, distance=lambda a, b: dist.get((a, b), 99))
    assert only.correct("수영징은").text == "수영장은"  # 조사가 보존된다


def test_aliases_need_docs_index(tmp_path: Path) -> None:
    """문제: 문서 색인 없이 사전을 만들면 'no such table' 같은 알아보기 어려운 오류가 났다."""
    path = tmp_path / "no_docs.sqlite"
    sqlite3.connect(path).close()
    with pytest.raises(RuntimeError, match=r"ingest\.docs"):
        A.build_aliases(path)


@needs_data
def test_failed_docs_build_keeps_previous_index(tmp_path: Path) -> None:
    """문제: 표 삭제·생성(DDL)이 트랜잭션 밖이면 재생성이 중간에 실패할 때 이전 색인이 사라진다."""
    db = tmp_path / "x.sqlite"
    build(RAW_DIR, db)
    con = sqlite3.connect(db)
    build_docs(con, HISTORY_HTML)
    before = con.execute("SELECT COUNT(*), SUM(doc_id) FROM docs").fetchone()
    with pytest.raises(FileNotFoundError):
        build_docs(con, tmp_path / "missing.html")  # 연혁 파일이 없어 중간에 실패
    assert con.execute("SELECT COUNT(*), SUM(doc_id) FROM docs").fetchone() == before
    assert con.execute("SELECT COUNT(*) FROM docs_fts").fetchone()[0] == before[0]
    assert con.in_transaction is False
    con.close()


@needs_data
def test_indexed_links_are_http_only(tmp_path: Path) -> None:
    db = tmp_path / "x.sqlite"
    build(RAW_DIR, db)
    con = sqlite3.connect(db)
    build_docs(con, HISTORY_HTML)
    urls = [u for (u,) in con.execute("SELECT url FROM docs WHERE url IS NOT NULL")]
    assert urls and all(u.startswith(("http://", "https://")) for u in urls)
    con.close()
