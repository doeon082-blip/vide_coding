"""문서 색인과 키워드 검색 테스트: 색인 정합성, 검색 규칙, 이상한 입력에 대한 안전성."""

from __future__ import annotations

import asyncio
import random
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.chaesan.core import search as S
from app.chaesan.core.ports import QueryResult
from app.chaesan.ingest.cards import HISTORY_HTML, parse_history
from app.chaesan.ingest.docs import SOURCES, build_docs, clean
from app.chaesan.ingest.load import RAW_DIR, build
from app.chaesan.ingest.specs import SPECS
from app.chaesan.local.db import SqliteDB

HAVE_DATA = all((RAW_DIR / f"{s.id}.csv").is_file() for s in SPECS) and HISTORY_HTML.is_file()
needs_data = pytest.mark.skipif(not HAVE_DATA, reason="원본 데이터 없음")

WEIGHTS = {
    "15089962": 1.0,
    "15137825": 1.0,
    "15137824": 1.0,
    "15090715": 1.0,
    "15143220": 1.0,
    "15090257": 0.5,
    "15090260": 0.5,
    "history": 1.0,
}


def run[T](coro: Any) -> T:
    return asyncio.run(coro)  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("docs") / "chaesan.sqlite"
    build(RAW_DIR, path)
    con = sqlite3.connect(path)
    build_docs(con, HISTORY_HTML)
    con.close()
    return path


@pytest.fixture(scope="module")
def db(db_path: Path) -> SqliteDB:
    return SqliteDB(db_path)


def find(db: SqliteDB, terms: list[str], **kw: Any) -> S.SearchResult:
    kw.setdefault("weights", WEIGHTS)
    return run(S.search_docs(db, terms, **kw))


# --------------------------------------------------------------------------- 순수 함수


def test_squash_and_clean_terms() -> None:
    assert S.squash_text("올림픽 공원, 장미-축제!") == "올림픽공원장미축제"
    assert S.squash_text("ＡＢＣ") == ""  # 전각 영문은 NFC로는 그대로라 글자로 보지 않는다(질문은 guard에서 NFKC로 먼저 정리)
    assert S.clean_terms(["올림픽 공원", "올림픽공원", "꽃", "", "  ", "*", "A", "수영"]) == ["올림픽공원", "수영"]
    assert len(S.clean_terms([f"단어{i}번" for i in range(20)])) == S.MAX_TERMS
    assert len(S.clean_terms(["가" * 100])[0]) == S.MAX_TERM_CHARS


def test_fts_phrase_and_like_pattern_escape() -> None:
    assert S.fts_phrase('a"b') == '"a""b"'
    assert S.fts_phrase("NEAR(a b)") == '"NEAR(a b)"'
    assert S.like_pattern("100%_x\\") == "%100\\%\\_x\\\\%"


def test_boosted_sources() -> None:
    names = {"15133891": ["테니스장", "테니스"], "15138735": ["입출차"], "x": ["", "가"]}
    assert S.boosted_sources("올림픽공원 테니스 장은 몇 월에 붐벼?", names) == {"15133891"}
    assert S.boosted_sources("아무 상관 없는 질문", names) == set()
    assert S.boosted_sources("가 가 가", names) == set()  # 한 글자·빈 별칭은 쓰지 않는다


def test_clean_text_for_index() -> None:
    assert clean("  가\n\t나   다 ") == "가 나 다"
    assert clean("   ") is None and clean(None) is None


# --------------------------------------------------------------------------- 색인 정합성


@needs_data
def test_index_counts_match_sources(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    try:
        counts = dict(con.execute("SELECT source_id, COUNT(*) FROM docs GROUP BY 1").fetchall())
        for src in SOURCES:
            assert counts[src.source_id] == con.execute(f"SELECT COUNT(*) FROM {src.table}").fetchone()[0], src.source_id
        assert counts["history"] == len(parse_history(HISTORY_HTML.read_text(encoding="utf-8")))
        total = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        assert total == con.execute("SELECT COUNT(*) FROM docs_fts").fetchone()[0] == sum(counts.values()) == 3635
    finally:
        con.close()


@needs_data
def test_every_doc_traces_back_to_its_source_row(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    try:
        for src in SOURCES:
            bad = con.execute(
                f"SELECT COUNT(*) FROM docs d JOIN {src.table} t ON t._row = d.source_row "
                "WHERE d.source_id = ? AND REPLACE(REPLACE(d.title, ' ', ''), char(10), '') "
                f"!= REPLACE(REPLACE(t.{src.title}, ' ', ''), char(10), '')",
                (src.source_id,),
            ).fetchone()[0]
            assert bad == 0, src.source_id  # 색인의 제목이 원본 행의 제목과 같다(공백 정리 외에는 바뀌지 않음)
        assert con.execute("SELECT COUNT(*) FROM docs WHERE squash = '' OR title = ''").fetchone()[0] == 0
    finally:
        con.close()


@needs_data
def test_body_available_flags(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    try:
        flags = dict(con.execute("SELECT source_id, MAX(body_available) FROM docs GROUP BY 1").fetchall())
        assert flags == {
            "15089962": 1,
            "15143220": 1,
            "history": 1,
            "15137825": 0,
            "15137824": 0,
            "15090715": 0,
            "15090257": 0,
            "15090260": 0,
        }
        assert con.execute("SELECT COUNT(*) FROM docs WHERE source_id='15089962' AND body IS NULL").fetchone()[0] == 0
    finally:
        con.close()


# --------------------------------------------------------------------------- 검색 규칙


@needs_data
def test_basic_search_and_trace(db: SqliteDB) -> None:
    r = find(db, ["장미"])
    assert r.hits and all("장미" in S.squash_text(h.title + (h.body or "")) for h in r.hits)
    assert all(h.url is None or h.url.startswith("http") for h in r.hits)  # 사업실명제의 상대 경로는 url로 내보내지 않는다
    assert r.rows_read > 0


@needs_data
def test_short_terms_use_like_and_find_things(db: SqliteDB) -> None:
    assert find(db, ["수영"]).hits  # 2글자는 trigram이 못 찾으므로 LIKE 경로
    assert find(db, ["주차"]).hits


@needs_data
def test_spacing_does_not_matter(db: SqliteDB) -> None:
    ids = lambda terms: {h.doc_id for h in find(db, terms, limit=500).hits}  # noqa: E731
    assert ids(["올림픽 공원", "관리"]) == ids(["올림픽공원", "관리"])
    assert ids(["스케이트 장"]) == ids(["스케이트장"]) != set()
    assert ids(["10만 명"]) == ids(["10만명"]) != set()


@needs_data
def test_missing_word_returns_nothing_not_something_else(db: SqliteDB) -> None:
    """데이터에 없는 표현은 비슷한 것으로 바꿔 내놓지 않고 빈 결과(= 근거 없음)를 돌려준다."""
    assert find(db, ["장미축제"]).hits == []
    assert find(db, ["존재하지않는단어xyz"]).hits == []


@needs_data
def test_coverage_ranking_and_matched_terms(db: SqliteDB) -> None:
    r = find(db, ["스케이트장", "10만"], limit=50)
    both = [h for h in r.hits if len(h.matched_terms) == 2]
    one = [h for h in r.hits if len(h.matched_terms) == 1]
    assert both and one
    assert min(h.score for h in both) > max(h.score for h in one)  # 둘 다 맞은 문서가 하나만 맞은 문서보다 위


@needs_data
def test_weights_and_boost_reorder(db: SqliteDB) -> None:
    low = {**WEIGHTS, "15089962": 0.1}
    top_normal = find(db, ["주차"], weights=WEIGHTS).hits[0].source_id
    r_low = find(db, ["주차"], weights=low, limit=3)
    assert top_normal == "15089962" or r_low.hits[0].source_id != "15089962"
    assert all(h.source_id != "15089962" for h in r_low.hits[:1])  # 낮춘 출처는 밀려난다
    r_boost = find(db, ["주차"], weights=low, boosted={"15089962"}, limit=3)
    assert (
        r_boost.hits[0].score >= r_low.hits[0].score and r_boost.hits[0].source_id == "15089962"
    )  # 질문에 이름이 나오면 1.0으로 복귀


@needs_data
def test_source_filter_period_and_order(db: SqliteDB) -> None:
    r = find(db, ["스케이트장"], source_ids=["15137825"], limit=100)
    assert r.hits and {h.source_id for h in r.hits} == {"15137825"}
    r19 = find(db, ["스케이트장"], source_ids=["15137825"], start=date(2019, 1, 1), end=date(2019, 12, 31), limit=100)
    assert r19.hits and all(h.doc_date and h.doc_date.startswith("2019") for h in r19.hits)
    newest = find(db, ["스케이트장"], source_ids=["15137825"], order="date_desc", limit=10).hits
    assert [h.doc_date for h in newest] == sorted((h.doc_date for h in newest), key=lambda d: d or "", reverse=True)
    # 날짜를 모르는 문서는 기간 조건이 있으면 빠진다(날짜를 지어내지 않는다)
    assert find(db, ["잔디"], source_ids=["15143220"]).hits
    assert find(db, ["잔디"], source_ids=["15143220"], start=date(2000, 1, 1)).hits == []


@needs_data
def test_history_month_precision_overlaps_period(db: SqliteDB) -> None:
    r = find(db, ["올림픽공원"], source_ids=["history"], start=date(1993, 7, 15), end=date(1993, 7, 20), limit=50)
    assert r.hits and all(h.doc_date == "1993-07" for h in r.hits)  # 'YYYY-MM' 문서는 그 달 전체에 걸친 것으로 본다


@needs_data
def test_fts_and_like_modes_agree(db: SqliteDB) -> None:
    for term in ["스케이트장", "올림픽수영장", "장미정원", "테니스장"]:
        a = {h.doc_id for h in find(db, [term], mode="fts", limit=500).hits}
        b = {h.doc_id for h in find(db, [term], mode="like", limit=500).hits}
        assert a == b and a, term  # 서비스에서 trigram을 못 쓰면 LIKE로 바꿔도 같은 문서를 찾는다


@needs_data
def test_weird_input_is_safe_and_tables_survive(db: SqliteDB, db_path: Path) -> None:
    nasty = [
        '"; DROP TABLE docs;--',
        "NEAR(a b)",
        "* OR 1=1",
        "a AND b",
        '""""',
        "'",
        "%",
        "_",
        "\\",
        "-",
        "한글\x00널",
        "퟿" * 50,
    ]
    for term in nasty:
        r = find(db, [term, term + "x"])
        assert r.rows_read <= S.MAX_TERMS * S.CANDIDATES_PER_TERM
    con = sqlite3.connect(db_path)
    try:
        assert con.execute("SELECT COUNT(*) FROM docs").fetchone()[0] == 3635
    finally:
        con.close()


@needs_data
def test_adapter_is_read_only(db: SqliteDB) -> None:
    with pytest.raises(sqlite3.OperationalError):
        run(db.query("DELETE FROM docs"))
    with pytest.raises(sqlite3.OperationalError):
        run(db.query("DROP TABLE docs"))


@needs_data
def test_random_terms_never_crash_and_stay_bounded(db: SqliteDB) -> None:
    rng = random.Random(7)
    alphabet = "가나다라마바사아자차카타파하 장미수영주차10만%_\"'*()-"
    for _ in range(300):
        terms = ["".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8))) for _ in range(rng.randint(0, 4))]
        r = find(db, terms, limit=rng.randint(0, 5), mode=rng.choice(["fts", "like"]))
        assert len(r.hits) <= 5 and r.rows_read <= S.MAX_TERMS * S.CANDIDATES_PER_TERM


# --------------------------------------------------------------------------- DB를 부르지 않는 경우


class CountingDB:
    def __init__(self) -> None:
        self.calls = 0

    async def query(self, sql: str, params: tuple[Any, ...] = ()) -> QueryResult:
        self.calls += 1
        return QueryResult()


def test_unusable_terms_do_not_touch_the_database() -> None:
    fake = CountingDB()
    for terms in ([], [""], ["꽃"], ["*", "!"], ["a"]):
        r = run(S.search_docs(fake, terms, weights=WEIGHTS))
        assert r.hits == [] and r.rows_read == 0
    assert run(S.search_docs(fake, ["수영장"], weights=WEIGHTS, limit=0)).hits == []
    assert fake.calls == 0  # 근거 없는 질문에 D1 읽기 한도를 쓰지 않는다


@needs_data
def test_summary_and_date_orders(db: SqliteDB) -> None:
    """상위 몇 건이 아니라 전체 일치 문서에 대한 요약(총 건수·가장 이른/늦은 날짜)을 코드가 센다."""
    r = find(db, ["장미"], source_ids=["15137825"], limit=3, order="date_asc")
    assert r.total > 3
    assert r.first_date == r.hits[0].doc_date == "2014-06-01"
    assert r.last_date and r.last_date >= r.first_date
    assert [h.doc_date for h in r.hits] == sorted(h.doc_date or "" for h in r.hits)
    desc = find(db, ["장미"], source_ids=["15137825"], limit=3, order="date_desc")
    assert desc.hits[0].doc_date == desc.last_date
    assert (desc.total, desc.first_date, desc.last_date) == (r.total, r.first_date, r.last_date)  # 정렬과 상관없는 같은 요약
    assert not r.capped
    none = find(db, ["존재하지않는낱말xyz"])
    assert (none.total, none.first_date, none.last_date) == (0, None, None)


@needs_data
def test_list_docs_in_period(db: SqliteDB) -> None:
    """검색어 없이 코드가 해석한 기간만으로 문서를 나열한다('○년 ○월에 무슨 일')."""
    r = run(S.list_docs_in_period(db, weights=WEIGHTS, source_ids=["history"], start=date(2015, 12, 1), end=date(2015, 12, 31)))
    assert r.total >= 1
    assert {h.doc_date for h in r.hits} == {"2015-12"}
    assert r.first_date == r.last_date == "2015-12"
    assert all(h.matched_terms == () for h in r.hits)
    # 여러 해에 걸친 기간과 정렬
    wide = run(
        S.list_docs_in_period(
            db, weights=WEIGHTS, source_ids=["history"], start=date(2000, 1, 1), end=date(2009, 12, 31), order="date_asc", limit=5
        )
    )
    assert wide.total > 5
    assert [h.doc_date for h in wide.hits] == sorted(h.doc_date or "" for h in wide.hits)
    desc = run(
        S.list_docs_in_period(
            db,
            weights=WEIGHTS,
            source_ids=["history"],
            start=date(2000, 1, 1),
            end=date(2009, 12, 31),
            order="date_desc",
            limit=3,
        )
    )
    assert desc.hits[0].doc_date == desc.last_date
    assert (desc.total, desc.first_date, desc.last_date) == (wide.total, wide.first_date, wide.last_date)


@needs_data
def test_list_docs_in_period_edge_cases(db: SqliteDB) -> None:
    kw: dict[str, Any] = {"weights": WEIGHTS, "start": date(2015, 12, 1), "end": date(2015, 12, 31)}
    assert run(S.list_docs_in_period(db, source_ids=[], **kw)).hits == []  # 출처가 없으면 아무것도 읽지 않는다
    assert (
        run(S.list_docs_in_period(db, source_ids=["history"], weights=WEIGHTS, start=None, end=None)).hits == []
    )  # 기간이 없으면 안 한다
    assert run(S.list_docs_in_period(db, source_ids=["history"], limit=0, **kw)).hits == []
    assert run(S.list_docs_in_period(db, source_ids=["15143220"], **kw)).hits == []  # 날짜 칸이 없는 문서는 기간 조건에서 빠진다
    far = run(S.list_docs_in_period(db, source_ids=["history"], weights=WEIGHTS, start=date(1850, 1, 1), end=date(1850, 12, 31)))
    assert (far.total, far.first_date) == (0, None)
