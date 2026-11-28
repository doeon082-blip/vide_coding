"""개발용 질문 검사 도구 테스트: 문항 파일의 형식·균형, 채점기의 판정, 생성기의 재현성."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from app.chaesan.ingest.load import DB_PATH
from app.chaesan.local.db import ro_uri
from eval import make_dev_questions as gen
from eval import run_eval as ev

QUESTIONS = ev.load_questions(gen.OUT)


def card(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": "answered", "answer": "", "evidence_rows": [], "documents": [], "sources": [], "corrections": [],
        "unsupported_numbers": [], "meta": {},
    }  # fmt: skip
    return {**base, **kw}


def test_dev_file_shape_and_balance() -> None:
    assert len(QUESTIONS) == 20
    assert len({q["id"] for q in QUESTIONS}) == 20
    assert sum(1 for q in QUESTIONS if q["typos"]) == 5  # 오타·줄임말 5개(지시서 F단계)
    assert sum(1 for q in QUESTIONS if "answered" not in q["expect_status"]) == 3  # 근거 없는 질문 3개
    for q in QUESTIONS:
        assert q["question"].strip()
        answerable = "answered" in q["expect_status"]
        assert bool(q["expected_tables"]) == answerable
        if answerable:
            assert q["expect_contains"] or q["expect_docs"], q["id"]  # 채점할 사실이 없는 문항은 없다
        for group in q["expect_contains"]:
            assert group
            assert all(isinstance(x, str) and x for x in group)


def test_questions_avoid_the_ones_used_while_building_the_engine() -> None:
    """엔진을 만들며 직접 돌려 보고 고친 질문은 개발용에서도 오염되어 제외한다."""
    text = " ".join(q["question"] for q in QUESTIONS)
    for contaminated in ("몇 월에 이용자가 가장 많았", "몇 시에 가장 붐벼", "장미 기사", "한산"):
        assert contaminated not in text


@pytest.mark.skipif(not DB_PATH.is_file(), reason="DB 없음")
def test_generator_is_reproducible_and_answers_come_from_the_db() -> None:
    con = sqlite3.connect(ro_uri(DB_PATH), uri=True)
    try:
        fresh = gen.build(con)
    finally:
        con.close()
    assert fresh == QUESTIONS  # 같은 시드·같은 데이터면 같은 파일(데이터가 바뀌면 여기서 알린다)


def test_grader_pass_and_fail_cases() -> None:
    q = next(x for x in QUESTIONS if x["id"] == "dev01")
    ok = card(answer="7,970명이에요", sources=[{"id": "15133891"}])
    assert ev.grade(q, ok)["passed"]
    assert not ev.grade(q, card(answer="7,971명이에요", sources=[{"id": "15133891"}]))["passed"]  # 틀린 숫자
    assert ev.grade(q, card(answer="7970명", sources=[{"id": "15133891"}]))["passed"]  # 쉼표 표기 차이는 같은 값
    wrong_card = ev.grade(q, card(answer="7,970명", sources=[{"id": "15131671"}]))
    assert wrong_card["selection"] is False
    assert wrong_card["cause"].startswith("자료 선택")
    refused = ev.grade(q, card(status="unknown", answer="모른다"))
    assert refused["cause"].startswith("자료 선택")


def test_grader_unknown_and_typo_cases() -> None:
    unknown = next(x for x in QUESTIONS if x["type"] == "unknown")
    assert ev.grade(unknown, card(status="unknown"))["passed"]
    made_up = ev.grade(unknown, card(status="answered", answer="12개예요"))
    assert not made_up["passed"]
    assert made_up["cause"].startswith("지어낸 답")
    typo = next(x for x in QUESTIONS if x["id"] == "dev20")
    base = card(answer="294,816명", sources=[{"id": "15133891"}])
    assert not ev.grade(typo, base)["passed"]  # 보정 기록이 없다
    fixed = card(answer=base["answer"], sources=base["sources"], corrections=["'테니스짱'을(를) '테니스장'(으)로 읽었어요"])
    assert ev.grade(typo, fixed)["typo_ok"] is True
    extra = card(corrections=["'가'을(를) '나'(으)로 읽었어요"], status="unknown")
    assert ev.grade(next(x for x in QUESTIONS if x["id"] == "dev14"), extra)["wrong_fixes"] == extra["corrections"]


def test_rate_and_summary_format() -> None:
    assert ev.rate([True, False, None]) == "1/2 (50%)"
    assert ev.rate([None]) == "해당 없음"
    assert json.loads(Path(gen.OUT).read_text(encoding="utf-8").splitlines()[0])["id"] == "dev01"


def test_allowed_abbreviation_expansion_is_not_a_wrong_fix() -> None:
    """질문에 쓴 공식 약칭(한체산)을 풀어 읽는 것은 설계된 동작이라 '잘못 고친 수'에 세지 않는다."""
    q = next(x for x in QUESTIONS if x["id"] == "dev14")
    expanded = "'한체산'을(를) '한국체육산업개발'(으)로 읽었어요"
    assert ev.grade(q, card(status="answered", corrections=[expanded]))["wrong_fixes"] == []
    assert ev.grade(q, card(status="answered", corrections=["'가'을(를) '나'(으)로 읽었어요"]))["wrong_fixes"] != []
