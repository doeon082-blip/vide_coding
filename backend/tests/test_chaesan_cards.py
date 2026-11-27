"""데이터 카드 테스트: 형식, 원본 CSV와의 독립 대조, 주의점 속 숫자의 정확성, 오류 처리."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from app.chaesan.core.catalog import CatalogError, load_catalog
from app.chaesan.ingest import cards as cards_mod
from app.chaesan.ingest.card_meta import GROUPS, META
from app.chaesan.ingest.cards import CardError, HistoryEntry, build_cards, parse_history, write_cards
from app.chaesan.ingest.load import RAW_DIR, build
from app.chaesan.ingest.specs import SPEC_BY_ID, SPECS

HISTORY = cards_mod.HISTORY_HTML
HAVE_DATA = all((RAW_DIR / f"{s.id}.csv").is_file() for s in SPECS) and HISTORY.is_file()
needs_data = pytest.mark.skipif(not HAVE_DATA, reason="원본 데이터 없음")


@pytest.fixture(scope="module")
def db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("cards") / "chaesan.sqlite"
    build(RAW_DIR, out)
    return out


@pytest.fixture(scope="module")
def cards(db_path: Path) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in build_cards(db_path, HISTORY)}


def _csv_rows(card_id: str) -> list[dict[str, str]]:
    """DB 적재 코드를 거치지 않고 원본 CSV를 직접 읽는다(독립 검증)."""
    raw = (RAW_DIR / f"{card_id}.csv").read_bytes()
    text = raw.decode("utf-8-sig") if raw.startswith(b"\xef\xbb\xbf") else raw.decode("cp949")
    return list(csv.DictReader(io.StringIO(text)))


def _q(db_path: Path, sql: str) -> list[tuple[Any, ...]]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


# --------------------------------------------------------------------------- 구성


@needs_data
def test_card_counts_and_groups(cards: dict[str, dict[str, Any]]) -> None:
    loaded = [c for c in cards.values() if c["loaded"]]
    assert len(loaded) == 31 and {c["id"] for c in loaded} == set(META) | {"history"}  # 파일 30 + 연혁
    assert all(c["kind"] == "api" for c in cards.values() if not c["loaded"])
    assert 8 <= len(GROUPS) <= 10
    for gid, g in GROUPS.items():
        rep = cards[g.representative]
        assert rep["loaded"] and rep["group"] == gid


@needs_data
def test_tiers_follow_the_criteria_table(cards: dict[str, dict[str, Any]]) -> None:
    """C는 근무복 2종뿐(지시서 기준표). 등급은 개발 점수가 아니라 기준과 이유로 정한다."""
    assert {i for i, c in cards.items() if c["tier"] == "C"} == {"15168248", "15168288"}
    assert all(c["tier_reason"].strip() for c in cards.values())
    assert {"15089962", "15138735", "15133891", "15101610", "15143220", "15137825"} <= {i for i, c in cards.items() if c["tier"] == "A"}


@needs_data
def test_unconnected_api_cards_have_no_invented_facts(cards: dict[str, dict[str, Any]]) -> None:
    api = [c for c in cards.values() if not c["loaded"]]
    assert len(api) == 27  # 개방목록에 있는 오픈API 항목 수. 기획서의 28종 중 1종은 목록에 없다(이름 미확인)
    for c in api:
        assert c["table"] is None and c["rows"] is None and c["period"] is None and c["last_data_date"] is None
        assert "연결" in c["caveats"][0]


@needs_data
def test_catalog_loads_written_cards(cards: dict[str, dict[str, Any]], tmp_path: Path) -> None:
    write_cards(list(cards.values()), tmp_path)
    cat = load_catalog(tmp_path)
    assert len(cat.cards) == 58 and len(list(cat.loaded())) == 31
    assert cat.get("15138735").tables == ("s_parking_hourly",)  # 서비스에서는 큰 원본 대신 집계 표
    assert cat.get("15101610").tables == ("t_15101610",)
    assert all(len(cat.in_group(g)) >= 1 for g in cat.groups)


@needs_data
def test_write_is_idempotent_and_removes_stale_files(cards: dict[str, dict[str, Any]], tmp_path: Path) -> None:
    stale = {"id": "99999999", "kind": "file", "tier": "A"}
    (tmp_path / "99999999.json").write_text(json.dumps(stale), encoding="utf-8")  # 이전 실행에서 남은 카드
    write_cards(list(cards.values()), tmp_path)
    first = {p.name: p.read_bytes() for p in tmp_path.glob("*.json")}
    write_cards(list(cards.values()), tmp_path)
    assert first == {p.name: p.read_bytes() for p in tmp_path.glob("*.json")}
    assert "99999999.json" not in first


# --------------------------------------------------------------------------- 원본 CSV와 독립 대조


@needs_data
@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.id)
def test_rows_match_raw_csv(cards: dict[str, dict[str, Any]], spec: Any) -> None:
    assert cards[spec.id]["rows"] == len(_csv_rows(spec.id))


@needs_data
@pytest.mark.parametrize(
    "card_id, col, end_col",
    [
        ("15089962", "등록일", None),
        ("15133891", "시작일", "종료일"),
        ("15137824", "배포일자", None),
        ("15137825", "보도일자", None),
        ("15138735", "입차일", None),
        ("15164156", "등록일", None),
        ("15168288", "주문일", None),
    ],
)
def test_period_matches_raw_csv(cards: dict[str, dict[str, Any]], card_id: str, col: str, end_col: str | None) -> None:
    rows = _csv_rows(card_id)
    starts = [r[col] for r in rows if r[col] and not r[col].startswith(("1990-01-01", "9999"))]
    ends = [r[end_col] for r in rows if r[end_col] and not r[end_col].startswith("9999")] if end_col else starts
    period = cards[card_id]["period"]
    assert (period["start"], period["end"]) == (min(starts), max(ends))


@needs_data
def test_monthly_parking_period_and_history(cards: dict[str, dict[str, Any]]) -> None:
    rows = _csv_rows("15131671")
    years = {int(r["연도"]) for r in rows}
    assert cards["15131671"]["period"]["start"] == f"{min(years)}-01-01"
    assert cards["15131671"]["period"]["end"] == f"{max(years)}-12-01"
    h = cards["history"]
    assert (h["rows"], h["period"]["start"], h["period"]["end"]) == (142, "1990-07", "2026-07")  # 기획서의 '1990~2026'과 일치


# --------------------------------------------------------------------------- 주의점 속 숫자가 데이터와 맞는가


@needs_data
@pytest.mark.parametrize(
    "sql, expected",
    [
        # 15101610: 시작월과 기간 시작이 다른 행 47건, 운영 중 표시 281건, 강좌번호 680개
        ("SELECT COUNT(*) FROM t_15101610 WHERE start_month IS NOT period_start", 47),
        ("SELECT COUNT(*) FROM t_15101610 WHERE period_end='9999-12-31'", 281),
        ("SELECT COUNT(DISTINCT course_no) FROM t_15101610", 680),
        # 15110953: 9999 종료 1,344건 중 시작이 1년 넘음 964건(오늘 2026-11-28 기준), 수강대상 빈 1,891건
        ("SELECT COUNT(*) FROM t_15110953 WHERE period_end='9999-12-31'", 1344),
        ("SELECT COUNT(*) FROM t_15110953 WHERE period_end='9999-12-31' AND period_start < '2025-11-28'", 940),
        ("SELECT COUNT(*) FROM t_15110953 WHERE period_end='9999-12-31' AND period_start IS NULL", 24),
        ("SELECT COUNT(*) FROM t_15110953 WHERE target IS NULL", 1891),
        # 15114776 / 15118652
        ("SELECT COUNT(*) FROM t_15114776 WHERE period_end='9999-12-31'", 359),
        ("SELECT COUNT(*) FROM t_15118652 WHERE period_end='9999-12-31'", 313),
        ("SELECT COUNT(*) FROM t_15118652 WHERE period_end='9999-12-31' AND period_start < '2025-11-28'", 50),
        # 15138735: 8월로 넘어간 출차 65건, 월별주차 값, 두 자료의 비율
        ("SELECT COUNT(*) FROM t_15138735 WHERE exit_at >= '2024-08-01'", 65),
        ("SELECT cars FROM t_15131671 WHERE lot='올림픽공원' AND year=2024 AND month=7", 59808),
        ("SELECT SUM(entries) FROM s_parking_hourly WHERE date LIKE '2024-07-%'", 215528),
        ("SELECT ROUND(215528.0 / (SELECT cars FROM t_15131671 WHERE lot='올림픽공원' AND year=2024 AND month=7), 1)", 3.6),
        # 그 밖의 숫자
        ("SELECT COUNT(*) FROM t_15090715 WHERE end_date > '2027-12-31'", 9),
        ("SELECT COUNT(*) FROM t_15090715 WHERE file_url IS NULL", 74),
        ("SELECT COUNT(DISTINCT reg_date) FROM t_15164156", 92),
        ("SELECT COUNT(*) FROM t_15164156 WHERE reg_hour IS NULL", 0),
        ("SELECT COUNT(*) FROM t_15090257 WHERE major IS NULL", 79),
        ("SELECT COUNT(*) FROM t_15144839 WHERE valid_start IS NULL", 253),
        ("SELECT COUNT(*) FROM t_15144839 WHERE valid_end='9999-12-31'", 374),
        ("SELECT COUNT(DISTINCT base_date) FROM t_15144222", 21),
        ("SELECT COUNT(*) FROM t_15147873", 42),
        ("SELECT COUNT(*) FROM t_15147873 WHERE description IS NULL", 29),
        ("SELECT COUNT(DISTINCT reg_date) FROM t_15089962", 8),
        ("SELECT COUNT(DISTINCT member_type) FROM t_15133891", 2),
    ],
)
def test_numbers_cited_in_caveats(db_path: Path, sql: str, expected: float) -> None:
    assert _q(db_path, sql)[0][0] == expected


@needs_data
def test_unlinked_facts_in_caveats(db_path: Path) -> None:
    """숫자가 아닌 주장도 데이터로 확인한다."""
    assert dict(_q(db_path, "SELECT open_label, COUNT(*) FROM t_15143220 GROUP BY 1")) == {"개방시간": 7, "출입금지기간": 1}
    assert _q(db_path, "SELECT place, open_detail FROM t_15143220 WHERE open_label='출입금지기간'") == [("잔디통제시기", "11-01 ~ 익년05-31")]
    assert _q(db_path, "SELECT COUNT(*) FROM t_15143220 WHERE place='나홀로나무'") == [(2,)]
    assert _q(db_path, "SELECT MAX(reg_date) FROM t_15090719") == [("2015-01-10",)]
    assert _q(db_path, "SELECT MAX(reg_date) FROM t_15119388") == [("2022-06-29",)]
    assert _q(db_path, "SELECT MAX(period_start) FROM t_15110953") == [("2026-06-01",)]
    # 테니스: 30배 넘게 크다는 주장
    users = dict(_q(db_path, "SELECT member_type, SUM(users) FROM t_15133891 GROUP BY 1"))
    assert users["일일입장"] > 30 * users["월회원"]
    # 센터별 마지막 등록일(문장에 적은 날짜)
    last = dict(_q(db_path, "SELECT center, MAX(reg_date) FROM t_15098997 GROUP BY 1"))
    assert last == {"올림픽수영장": "2026-06-17", "올림픽스포츠센터": "2026-03-17", "일산스포츠센터": "2025-02-24", "분당스포츠센터": "2024-09-30"}


# --------------------------------------------------------------------------- 별칭 규칙: 데이터 이름·값·열 이름·개방목록 키워드에서만


def _norm(s: str) -> str:
    return s.replace(" ", "").lower()


@needs_data
def test_aliases_come_from_data_only(db_path: Path, cards: dict[str, dict[str, Any]]) -> None:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        listing = " ".join(
            _norm(f"{n} {k or ''}") for n, k in con.execute("SELECT dataset_name, keywords FROM t_15147873")
        )
        bad: list[str] = []
        for cid, c in cards.items():
            for alias in c["aliases"]:
                a = _norm(alias)
                ok = a in _norm(c["name"]) or a in listing
                if not ok and c["table"]:
                    ok = any(a in _norm(col["ko"]) for col in c["columns"])
                    for col in c["columns"] if not ok else ():
                        if col["sql_type"] == "TEXT":
                            hit = con.execute(
                                f"SELECT 1 FROM {c['table']} WHERE REPLACE(LOWER(\"{col['name']}\"), ' ', '') LIKE ? LIMIT 1",
                                (f"%{a}%",),
                            ).fetchone()
                            if hit:
                                ok = True
                                break
                if not ok and cid == "history":
                    ok = a in _norm(parse_history_text())
                if not ok:
                    bad.append(f"{cid}:{alias}")
        assert not bad, f"데이터에서 찾을 수 없는 별칭: {bad}"
    finally:
        con.close()


def parse_history_text() -> str:
    return " ".join(e.text for e in parse_history(HISTORY.read_text(encoding="utf-8", errors="replace")))


# --------------------------------------------------------------------------- 오류 처리(조용히 넘어가지 않기)


def test_parse_history_counts_and_rejects_mismatch() -> None:
    ok = (
        '<div class="item year2026 active"><strong>2026</strong><ol>'
        "<li><span>7월.</span> <em>A 수상</em></li><li><span>3월.</span> <em>B 수상</em></li></ol></div><!-- //2026 -->"
    )
    assert parse_history(ok) == [HistoryEntry(2026, 7, "A 수상"), HistoryEntry(2026, 3, "B 수상")]
    broken = ok.replace("<em>B 수상</em>", "B 수상")  # 형식이 달라 항목을 놓치는 경우
    with pytest.raises(CardError, match="파싱 불일치"):
        parse_history(broken)
    with pytest.raises(CardError):
        parse_history("<html></html>")


@needs_data
def test_meta_and_spec_mismatch_stops(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    broken = dict(META)
    broken.pop("15133891")
    monkeypatch.setattr(cards_mod, "META", broken)
    with pytest.raises(CardError, match="명세와 카드 메타"):
        build_cards(db_path, HISTORY)


@needs_data
def test_bad_group_representative_stops(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    bad = dict(GROUPS)
    bad["parking"] = replace(bad["parking"], representative="15133891")  # 다른 묶음의 데이터
    monkeypatch.setattr(cards_mod, "GROUPS", bad)
    with pytest.raises(CardError, match="대표"):
        build_cards(db_path, HISTORY)


def _valid_card() -> dict[str, Any]:
    return {
        "id": "x1", "name": "n", "kind": "file", "loaded": True, "portal_url": "u", "group": "parking", "tier": "A",
        "weight": 1.0, "tier_reason": "r", "rows": 1, "period": None, "last_data_date": None, "columns": [],
        "caveats": [], "example_questions": ["a", "b", "c"], "aliases": [], "in_service": True, "table": "t_x1",
        "aggregate_tables": [],
    }  # fmt: skip


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda c: c.update(weight=0.5), "가중치"),
        (lambda c: c.update(tier="Z"), "가중치"),
        (lambda c: c.update(kind="csv"), "kind"),
        (lambda c: c.update(table=None), "표가 없다"),
        (lambda c: c.update(example_questions=["a"]), "3개"),
        (lambda c: c.pop("caveats"), "빠진 항목"),
        (lambda c: c.update(loaded=False, rows=5), "지어낸"),
    ],
)
def test_catalog_rejects_bad_cards(tmp_path: Path, mutate: Any, message: str) -> None:
    card = _valid_card()
    mutate(card)
    (tmp_path / "x1.json").write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "_groups.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CatalogError, match=message):
        load_catalog(tmp_path)


def test_catalog_rejects_orphan_and_mismatched_file(tmp_path: Path) -> None:
    (tmp_path / "x1.json").write_text(json.dumps(_valid_card()), encoding="utf-8")
    (tmp_path / "_groups.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CatalogError, match="묶음에 없는"):
        load_catalog(tmp_path)
    (tmp_path / "x1.json").rename(tmp_path / "y2.json")
    with pytest.raises(CatalogError, match="다르다"):
        load_catalog(tmp_path)


@needs_data
def test_write_never_deletes_non_card_json(cards: dict[str, dict[str, Any]], tmp_path: Path) -> None:
    """--out을 잘못 지정해도 카드가 아닌 JSON은 남아 있어야 한다."""
    other = {"settings.json": '{"a": 1}', "list.json": "[1, 2]", "broken.json": "{", "x.json": '{"id": "y", "kind": "file", "tier": "A"}'}
    for name, body in other.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    stale = {"id": "77777777", "kind": "file", "tier": "A"}
    (tmp_path / "77777777.json").write_text(json.dumps(stale), encoding="utf-8")  # 이전 실행의 카드
    write_cards(list(cards.values()), tmp_path)
    assert all((tmp_path / n).read_text(encoding="utf-8") == body for n, body in other.items())
    assert not (tmp_path / "77777777.json").exists()


def test_unsafe_sql_expressions_are_rejected() -> None:
    for expr in ["reg_date; DROP TABLE t", "reg_date -- x", "reg_date' OR '1'='1", "(SELECT 1)", "a.b"]:
        with pytest.raises(CardError):
            cards_mod._check_expr(expr)
    assert cards_mod._check_expr("printf('%04d-%02d-01', year, month)")
