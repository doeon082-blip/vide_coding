"""화면 예시 답(web/data/examples.json) 검사: 구조·개인정보·링크 도메인, 개발용 질문과의 겹침, 그리고 숫자를 DB로 다시 확인한다.

예시 답은 엔진이 낸 응답을 그대로 저장한 것이라(손으로 쓰지 않음), 데이터가 바뀌어 틀린 답이 남지 않도록 DB로 다시 맞춰 본다.
이 파일은 시험용 60문항(test_questions.jsonl)을 열지 않는다(규칙 11).
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any
from urllib.parse import urlparse

import pytest

from app.chaesan.core.answer import find_unsupported_numbers
from app.chaesan.ingest.load import BACKEND_DIR, DB_PATH

EXAMPLES = BACKEND_DIR / "app" / "chaesan" / "web" / "data" / "examples.json"
QUESTIONS = BACKEND_DIR / "eval" / "example_questions.json"
DEV = BACKEND_DIR / "eval" / "dev_questions.jsonl"
ALLOWED_HOSTS = ("data.go.kr", "ksponco.or.kr", "alio.go.kr")  # 화면 js/lib/safe-url.js의 허용 목록과 같아야 한다
LANES = {"역사", "시설·이용", "소식", "기관 정보", "데이터"}

DATA: dict[str, Any] = json.loads(EXAMPLES.read_text(encoding="utf-8"))
ITEMS: list[dict[str, Any]] = DATA["examples"]


def test_examples_follow_the_question_list_and_cover_all_five_lanes() -> None:
    asked = [q["question"] for q in json.loads(QUESTIONS.read_text(encoding="utf-8"))]
    assert [e["question"] for e in ITEMS] == asked  # 목록과 같은 순서·같은 개수(빠진 질문 없음)
    assert {e["lane"] for e in ITEMS} == LANES
    assert 8 <= len(ITEMS) <= 12
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00", DATA["generated_at"])  # KST 생성 시각


def test_examples_do_not_overlap_with_dev_questions() -> None:
    dev = [json.loads(line)["question"] for line in DEV.read_text(encoding="utf-8").splitlines() if line.strip()]
    for e in ITEMS:
        assert e["question"] not in dev, e["question"]


def test_every_response_is_the_engine_shape_without_internal_details() -> None:
    allowed = {
        "status",
        "answer",
        "evidence_kind",
        "evidence_rows",
        "documents",
        "sources",
        "badges",
        "corrections",
        "unsupported_numbers",
        "notice",
        "meta",
    }
    for e in ITEMS:
        r = e["response"]
        assert set(r) == allowed, e["question"]
        assert set(r["meta"]) == {"intent"}  # 토큰 수·걸린 시간·계획 내용은 싣지 않는다
        assert r["unsupported_numbers"] == []
        assert len(r["evidence_rows"]) <= 50
        assert len(r["answer"]) < 600


def test_answered_examples_have_evidence_and_the_unknown_example_has_none() -> None:
    kinds = {e["response"]["status"] for e in ITEMS}
    assert kinds == {"answered", "unknown"}  # 근거가 없으면 모른다고 답하는 모습도 보여 준다
    for e in ITEMS:
        r = e["response"]
        has = bool(r["sources"] or r["documents"])
        assert has if r["status"] == "answered" else not (has or r["evidence_rows"]), e["question"]


def test_example_links_are_https_and_allowlisted() -> None:
    urls = [s.get("url") for e in ITEMS for s in e["response"]["sources"]] + [
        d.get("url") for e in ITEMS for d in e["response"]["documents"]
    ]
    assert urls
    for url in filter(None, urls):
        parsed = urlparse(url)
        host = parsed.hostname or ""
        assert parsed.scheme == "https" and not parsed.username, url
        assert any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS), url


def test_no_personal_data_in_examples() -> None:
    text = EXAMPLES.read_text(encoding="utf-8")
    assert not re.search(r"\b01[016789][- ]?\d{3,4}[- ]?\d{4}\b", text)  # 휴대전화 번호
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)  # 이메일


def test_numeric_answers_only_use_numbers_found_in_the_evidence() -> None:
    """표 근거로 답한 예시는 답 속 숫자가 모두 근거 표(또는 출처 기간·질문)에 있다(숫자 대조 통과)."""
    checked = 0
    for e in ITEMS:
        r = e["response"]
        if r["evidence_rows"]:
            rows = [
                *r["evidence_rows"],
                *({"period": s.get("period", "")} for s in r["sources"]),
                {"question": e["question"]},
            ]  # 질문에 쓴 연도 등도 허용(엔진도 같다)
            assert find_unsupported_numbers(r["answer"], rows) == [], e["question"]
            checked += 1
    assert checked >= 2


def _db() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        pytest.skip("데이터 없음")
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def test_hourly_parking_example_matches_the_database() -> None:
    example = next(e for e in ITEMS if "시간대별 입차" in e["question"])["response"]
    with _db() as con:
        truth = dict(con.execute("SELECT hour, SUM(entries) FROM s_parking_hourly WHERE date LIKE '2024-07-%' GROUP BY hour"))
    assert {row["hour"]: row["total_entries"] for row in example["evidence_rows"]} == truth


def test_monthly_parking_example_matches_the_database() -> None:
    example = next(e for e in ITEMS if "미사경정공원" in e["question"])["response"]
    with _db() as con:
        table = next(
            name
            for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 't\\_%' ESCAPE '\\'")
            if {"year", "month", "lot", "cars"} <= {c[1] for c in con.execute(f'PRAGMA table_info("{name}")')}
        )
        truth = dict(con.execute(f'SELECT month, cars FROM "{table}" WHERE year = 2024 AND lot = ?', ("미사경정공원",)))
    assert {row["month"]: row["cars"] for row in example["evidence_rows"]} == truth


def test_frontend_example_file_is_valid_for_the_page() -> None:
    """화면이 읽는 모양: lane·question 문자열, response는 객체 또는 null."""
    for e in ITEMS:
        assert isinstance(e["lane"], str) and isinstance(e["question"], str) and len(e["question"]) <= 200
        assert isinstance(e["response"], dict)
