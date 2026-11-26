from app.models import FestivalRecord
from app.search import _Entry, lexical_score, normalize


def entry(name: str, opar: str = "") -> _Entry:
    r = FestivalRecord(id=name, fstvl_nm=name, opar=opar)
    return _Entry(r, normalize(name), normalize(opar))


NAME = "제23회 광주 추억의 충장축제"


def score(q: str, e: _Entry = entry(NAME)) -> float:
    return lexical_score(q, normalize(q), e)


def test_exact_and_substring_rank_highest():
    assert score("제23회 광주 추억의 충장축제") == 1.0
    assert score("충장 축제") > 0.9  # 공백 무시 부분일치


def test_typo_still_matches_but_lower():
    typo = score("충장추제")
    assert 0.6 < typo < 0.9
    assert typo > score("전혀 다른 검색어")


def test_unrelated_is_zero():
    assert score("산천어") == 0.0


def test_location_match_is_weak():
    e = entry("가을 음악회", opar="광주광역시 충장로")
    assert score("충장로", e) == 0.4


def test_token_all_present():
    assert score("광주 충장") >= 0.85
