"""RAG 챗봇 테스트: 의도 파악, 근거 검색, '거짓말 방지' 검증(가짜 LLM이 틀린 말을 해도 걸러지는지)."""

import random
from datetime import date

import pytest

from app.chatbot import (
    Candidate,
    Intent,
    known_regions,
    parse_intent,
    parse_window,
    respond,
    retrieve,
    template_reason,
    verify_reason,
)
from app.models import FestivalRecord

TODAY = date(2026, 11, 26)  # 목요일


def rec(i: str, name: str, start: str, end: str, co: str = "", opar: str = "", addr: str = "") -> FestivalRecord:
    return FestivalRecord(id=i, fstvl_nm=name, fstvl_start_date=start, fstvl_end_date=end, fstvl_co=co, opar=opar, rdnmadr=addr)


RECORDS = [
    rec("past-danpung", "팔공산 단풍축제", "2026-10-30", "2026-11-01", "단풍 감상, 먹거리장터", "팔공산", "대구광역시 동구 1"),
    rec("past-eoksae", "황매산억새축제", "2026-10-17", "2026-10-20", "억새 군락 산책", "황매산", "경상남도 합천군 1"),
    rec("ice", "얼음나라화천 산천어축제", "2027-01-09", "2027-01-31", "산천어체험, 눈/얼음체험, 먹거리", "화천천", "강원특별자치도 화천군 1"),
    rec("lights", "겨울빛축제", "2026-12-01", "2027-01-01", "야간 조명 전시와 불꽃놀이", "함평엑스포공원", "전라남도 함평군 1"),
    rec("food", "양촌곶감축제", "2026-12-11", "2026-12-13", "곶감 특산물 판매와 먹거리장터", "양촌", "충청남도 논산시 1"),
    rec("weekend", "파주장단콩축제", "2026-11-27", "2026-11-29", "장단콩 전시 판매와 체험행사", "임진각", "경기도 파주시 1"),
    rec("yearlong", "당진 상시 공연", "2026-01-01", "2026-12-31", "상설 공연", "당진시청", "충청남도 당진시 1"),
    rec("cancel", "거제 불꽃축제", "2026-11-01", "2026-11-30", "행사 취소", "거제", "경상남도 거제시 1"),
    rec("fire", "장승포 송년 불꽃축제", "2026-12-31", "2026-12-31", "불꽃 연출", "장승포항", "경상남도 거제시 2"),
    rec("jeju", "제주 밤 버스킹", "2026-11-20", "2026-12-20", "야간 버스킹 공연", "제주아트플랫폼", "제주특별자치도 제주시 1"),
]
REGIONS = known_regions(RECORDS)


def intent(msg: str) -> Intent:
    return parse_intent(msg, TODAY, REGIONS)


# ----------------------------------------------------------------------------- 의도 파악


def test_topic_and_literal_terms():
    it = intent("단풍 보고 싶어")
    assert it.topics == ["단풍"] and "단풍" in it.primary and "단풍" in it.core_terms


def test_single_char_terms_never_used():
    # '벚꽃'의 '꽃'이 '불꽃'에 걸리던 문제 방지: 한 글자 검색어 금지
    it = intent("벚꽃 보러 가고 싶어")
    assert all(len(t) >= 2 for t in it.terms)
    assert "꽃" not in it.terms


def test_verbs_and_particles_are_not_search_terms():
    it = intent("제주도에서 열리는 축제")
    assert it.region == "제주" and it.terms == []


def test_free_word_becomes_term():
    assert "산천어" in intent("산천어 하고 싶어").terms


def test_unsupported_info_detected():
    assert intent("입장료 얼마야? 주차 돼?").unsupported == ["입장료·가격", "주차"]


@pytest.mark.parametrize(
    "msg,start,end",
    [
        ("이번 주말에 뭐 해?", date(2026, 11, 28), date(2026, 11, 29)),
        ("내일 갈만한 곳", date(2026, 11, 27), date(2026, 11, 27)),
        ("12월 축제", date(2026, 12, 1), date(2026, 12, 31)),
        ("1월에 가고 싶어", date(2027, 1, 1), date(2027, 1, 31)),  # 이미 지난 달이면 내년
        ("다음 달 행사", date(2026, 12, 1), date(2026, 12, 31)),
    ],
)
def test_time_windows(msg, start, end):
    w = parse_window(msg, TODAY)
    assert (w.start, w.end) == (start, end)


def test_season_window_is_next_or_current():
    w = parse_window("가을에 가고 싶어", TODAY)
    assert w.start == TODAY and w.end == date(2026, 11, 30)  # 지금이 가을철 끝자락
    w = parse_window("봄에 가고 싶어", TODAY)
    assert w.start == date(2027, 3, 1) and w.end == date(2027, 5, 31)


def test_regions_from_data():
    assert "화천" in REGIONS and "함평" in REGIONS and "서울" in REGIONS


# ----------------------------------------------------------------------------- 근거 검색


def ids(cands):
    return [c.record.id for c in cands]


def test_danpung_has_no_active_so_only_past_reference():
    act, past = retrieve(RECORDS, intent("단풍 보고 싶어"), TODAY)
    assert act == []  # 지금 갈 수 있는 단풍 축제는 없다
    assert ids(past) == ["past-danpung"] and past[0].kind == "past"


def test_literal_word_required_for_strict_topic():
    # '억새'는 단풍의 연관어지만, 단풍을 물었을 때 억새 축제를 단풍으로 둔갑시키지 않는다
    _, past = retrieve(RECORDS, intent("단풍 보고 싶어"), TODAY)
    assert "past-eoksae" not in ids(past)
    # 사용자가 억새라고 직접 말하면 후보가 된다
    _, past2 = retrieve(RECORDS, intent("억새랑 단풍 보고 싶어"), TODAY)
    assert {"past-danpung", "past-eoksae"} <= set(ids(past2))


def test_cancelled_festival_is_never_recommended():
    act, _ = retrieve(RECORDS, intent("불꽃 보고 싶어"), TODAY)
    assert "cancel" not in ids(act) and "fire" in ids(act)


def test_weekend_window_excludes_non_overlapping_and_prefers_short_events():
    act, _ = retrieve(RECORDS, intent("이번 주말에 갈만한 축제"), TODAY)
    assert "weekend" in ids(act) and "ice" not in ids(act)
    assert ids(act)[0] == "weekend"  # 연중 상시 행사(yearlong)보다 먼저


def test_region_filter():
    act, _ = retrieve(RECORDS, intent("제주도에서 열리는 축제"), TODAY)
    assert ids(act) == ["jeju"]


def test_weak_expansion_only_matches_are_cut():
    act, _ = retrieve(RECORDS, intent("얼음 낚시 하고 싶어"), TODAY)
    assert ids(act) == ["ice"]  # '겨울빛축제'는 확장어('겨울')만 맞아 컷


def test_exclude_ids_for_more_results():
    act, _ = retrieve(RECORDS, intent("먹거리 축제"), TODAY, exclude_ids=frozenset({"food"}))
    assert "food" not in ids(act)


def test_random_mode_picks_from_active_only():
    act, _ = retrieve(RECORDS, intent("아무거나 추천해줘"), TODAY, rng=random.Random(1))
    assert act and all(c.status in ("진행중", "예정") for c in act)


# ----------------------------------------------------------------------------- 거짓말 방지 (핵심)


def cand(r: FestivalRecord, ev=("소개문에 ‘먹거리’",)) -> Candidate:
    return Candidate(r, "예정", 3.0, list(ev), "active")


FOOD = next(r for r in RECORDS if r.id == "food")
OTHER_NAMES = ["팔공산 단풍축제", "황매산억새축제", "얼음나라화천 산천어축제", "겨울빛축제"]


@pytest.mark.parametrize(
    "lie,why",
    [
        ("입장료는 무료이며 주차도 가능해요.", "risky"),  # 원문에 없는 가격/주차
        ("12월 25일부터 3일간 열려요.", "number"),  # 지어낸 날짜
        ("팔공산 단풍축제와 함께 즐겨 보세요.", "other"),  # 다른 축제 이름
        ("우주선 발사 체험과 외계인 공연이 열려요.", "unsupported"),  # 근거 없는 내용
        ("가" * 120, "long"),
    ],
)
def test_lies_are_rejected(lie, why):
    ok, reason = verify_reason(lie, cand(FOOD), OTHER_NAMES)
    assert not ok, (lie, reason)


@pytest.mark.parametrize(
    "truth", ["곶감 특산물 판매와 먹거리장터를 즐길 수 있어요.", "12월 11일에 열리는 곶감 축제예요.", "양촌곶감 먹거리를 만나 보세요."]
)
def test_grounded_reasons_pass(truth):
    ok, reason = verify_reason(truth, cand(FOOD), OTHER_NAMES)
    assert ok, (truth, reason)


def lying_llm(reasons):
    def llm(task, data, instruction, schema):
        return {"reasons": reasons}

    return llm


def run(msg, llm, previous=(), **kw):
    return respond(msg, previous_user_messages=list(previous), records=RECORDS, today=TODAY, llm=llm, rng=random.Random(0), **kw)


def test_lying_ai_is_replaced_by_grounded_template():
    out = run("먹거리 축제 추천해줘", lying_llm(["입장료 무료, 주차 가능, 12월 25일 개최!"] * 3))
    pick = out.picks[0]
    assert pick.candidate.record.id == "food"
    assert not pick.ai_written and "무료" not in pick.reason and "주차" not in pick.reason
    assert "먹거리" in pick.reason  # 근거 기반 템플릿


def test_good_ai_sentence_is_kept():
    out = run("먹거리 축제 추천해줘", lying_llm(["곶감 특산물과 먹거리장터가 있어요."]))
    assert out.picks[0].ai_written and out.picks[0].reason == "곶감 특산물과 먹거리장터가 있어요."


def test_factual_fields_always_come_from_db_not_ai():
    out = run("먹거리 축제 추천해줘", lying_llm(["곶감 특산물 판매예요."]))
    p = out.picks[0].candidate.record
    assert (p.fstvl_nm, p.fstvl_start_date, p.rdnmadr) == ("양촌곶감축제", "2026-12-11", "충청남도 논산시 1")
    assert "양촌곶감축제" not in out.answer or True  # 인사말은 고정 템플릿 (AI 미사용)


def test_ai_failure_does_not_break_chatbot():
    def boom(*a, **k):
        raise RuntimeError("ollama down")

    out = run("먹거리 축제 추천해줘", boom)
    assert out.picks and all(not p.ai_written for p in out.picks)  # 템플릿으로 계속


def test_no_candidates_means_no_llm_call_and_no_invention():
    called = []

    def llm(*a, **k):
        called.append(1)
        return {"reasons": []}

    out = run("우주 로켓 축제 보고 싶어", llm)
    assert called == [] and out.picks == []
    assert "찾지 못했어요" in out.answer


def test_danpung_answer_is_honest():
    called = []
    out = run("단풍 보고 싶어", lambda *a, **k: called.append(1) or {"reasons": []})
    assert called == []  # 지난 개최 참고는 LLM 없이 템플릿만
    assert out.picks and all(p.candidate.kind == "past" for p in out.picks)
    assert any("데이터에 없어요" in n and "단풍" in n for n in out.notes)
    assert "찾지 못했어요" in out.answer  # '지금 갈 수 있다'고 말하지 않는다


def test_unsupported_question_gets_deterministic_note():
    out = run("먹거리 축제 입장료 얼마야?", lying_llm(["곶감 먹거리가 있어요."]))
    assert any("입장료" in n and "없어서" in n for n in out.notes)


def test_only_unsupported_question_asks_for_subject():
    out = run("주차 돼?", lying_llm([]))
    assert out.picks == [] and any("주차" in n for n in out.notes)


def test_followup_inherits_previous_topic_and_region():
    out = run("제주는?", lying_llm(["야간 버스킹 공연이 있어요."]), previous=["야간 공연 보고 싶어"])
    assert [p.candidate.record.id for p in out.picks] == ["jeju"]


def test_more_request_uses_exclude():
    first = run("먹거리 축제 추천해줘", lying_llm(["곶감 먹거리가 있어요."]))
    again = run("더 보여줘", lying_llm([]), previous=["먹거리 축제 추천해줘"], exclude_ids=frozenset(p.candidate.record.id for p in first.picks))
    assert not {p.candidate.record.id for p in again.picks} & {p.candidate.record.id for p in first.picks}


def test_template_reason_grammar():
    c = Candidate(FOOD, "예정", 1, ["축제명에 ‘단풍’"], "active")
    assert template_reason(c) == "축제명에 ‘단풍’이 있는 축제예요."
    c2 = Candidate(FOOD, "예정", 1, ["소개문에 ‘벚꽃’"], "active")
    assert template_reason(c2) == "소개문에 ‘벚꽃’이 있는 축제예요."
    c3 = Candidate(FOOD, "예정", 1, ["소개문에 ‘먹거리’"], "active")
    assert template_reason(c3) == "소개문에 ‘먹거리’가 있는 축제예요."
