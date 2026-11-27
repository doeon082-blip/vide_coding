"""오타·줄임말 보정과 어휘 사전 테스트.

판단 규칙(조사 처리, 임계값, 되묻기, 숫자 보호)은 '가짜 거리 함수'로 시험해 계산 부분과 따로 확인하고,
맨 아래에서 실제 to_jamo·edit_distance를 연결한 결과도 확인한다.
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
from pathlib import Path

import pytest

from app.chaesan.core.correct import Corrector, Vocab, load_vocab
from app.chaesan.ingest import aliases as A
from app.chaesan.ingest.cards import HISTORY_HTML
from app.chaesan.ingest.docs import build_docs
from app.chaesan.ingest.load import RAW_DIR, build
from app.chaesan.ingest.specs import SPECS

ALIASES_FILE = A.ALIASES_PATH
HAVE_DATA = all((RAW_DIR / f"{s.id}.csv").is_file() for s in SPECS) and HISTORY_HTML.is_file()
needs_data = pytest.mark.skipif(not HAVE_DATA, reason="원본 데이터 없음")

VOCAB = Vocab(
    words={"수영장": 50, "수상장": 10, "테니스장": 30, "주차장": 20, "수영": 999},
    abbreviations={"올팍": "올림픽공원", "한체산": "한국체육산업개발"},
    known=frozenset({"인라인"}),
)
# 가짜 자모 거리: 표에 없는 쌍은 멀다(99). 판단 규칙만 시험하려고 실제 계산을 흉내 내지 않고 값을 정해 둔다.
FAKE = {
    ("수영징", "수영장"): 1,
    ("수영짱", "수영장"): 1,
    ("테니스짱", "테니스장"): 1,
    ("수양장", "수영장"): 1,
    ("수양장", "수상장"): 1,  # 후보가 둘 → 되묻기
    ("수연징", "수영장"): 2,  # 거리 2 → 되묻기
    ("수연짐", "수영장"): 3,  # 거리 3 → 그대로
}


class Spy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, a: str, b: str) -> int:
        self.calls.append((a, b))
        return FAKE.get((a, b), 99)


def make(spy: Spy | None = None) -> Corrector:
    return Corrector(VOCAB, jamo=lambda s: s, distance=spy or Spy())


# --------------------------------------------------------------------------- 약칭과 이미 맞는 말


def test_abbreviation_is_expanded_and_reported() -> None:
    r = make().correct("올팍 수영장 알려줘")
    assert r.text == "올림픽공원 수영장 알려줘"
    assert [(c.original, c.corrected, c.kind) for c in r.corrections] == [("올팍", "올림픽공원", "abbreviation")]
    assert r.corrections[0].describe() == "'올팍'을(를) '올림픽공원'(으)로 읽었어요"
    assert not r.needs_confirmation


def test_abbreviation_with_josa() -> None:
    assert make().correct("올팍에서 한체산이 관리해?").text == "올림픽공원에서 한국체육산업개발이 관리해?"


def test_known_words_are_never_touched_and_cost_no_distance_calls() -> None:
    spy = Spy()
    r = make(spy).correct("수영장은 인라인 테니스장에서 수영")
    assert r.text == "수영장은 인라인 테니스장에서 수영" and not r.corrections and not r.suggestions
    assert spy.calls == []  # 이미 맞는 말(어휘·보호 낱말)에는 거리 계산을 하지 않는다


# --------------------------------------------------------------------------- 확신도


def test_high_confidence_is_corrected_and_josa_kept() -> None:
    r = make().correct("올팍 수영징 언제 열어?")
    assert r.text == "올림픽공원 수영장 언제 열어?"
    assert r.corrections[1].describe() == "'수영징'을(를) '수영장'(으)로 읽었어요"
    assert make().correct("테니스짱은 어때").text == "테니스장은 어때"  # 조사 '은'은 그대로 붙는다


def test_ambiguous_candidates_ask_instead_of_guessing() -> None:
    r = make().correct("수양장 위치")
    assert r.text == "수양장 위치" and not r.corrections  # 고치지 않는다
    assert r.needs_confirmation and r.suggestions[0].candidates == ("수영장", "수상장")  # 흔한 쪽이 먼저
    assert r.suggestions[0].describe() == "혹시 수영장 / 수상장 말씀이세요?"


def test_distance_two_asks_and_distance_three_leaves_alone() -> None:
    r = make().correct("수연징 시간")
    assert r.text == "수연징 시간" and r.suggestions[0].candidates == ("수영장",)
    r = make().correct("수연짐 시간")
    assert r.text == "수연짐 시간" and not r.corrections and not r.suggestions


def test_short_words_are_not_treated_as_typos() -> None:
    spy = Spy()
    r = make(spy).correct("수양 주차")  # 2글자는 오타 후보에서 제외
    assert r.text == "수양 주차" and spy.calls == []


def test_length_filter_skips_far_candidates() -> None:
    spy = Spy()
    vocab = Vocab({"수영장": 5, "올림픽수영장": 5, "테니스장": 5}, {})
    Corrector(vocab, jamo=lambda s: s, distance=spy).correct("수영징")
    compared = {b for _, b in spy.calls}
    assert compared == {"수영장", "테니스장"}  # 글자 수 차이가 1 이내인 것만 비교한다
    assert "올림픽수영장" not in compared  # 6글자는 3글자 낱말과 비교조차 하지 않는다(계산량·오탐 모두 줄인다)


# --------------------------------------------------------------------------- 숫자·날짜 보호


def test_numbers_and_adjacent_words_are_never_changed() -> None:
    spy = Spy()
    text = "2024년 7월 10만명 수영징 3개월 100%"
    r = make(spy).correct(text)
    assert r.text == "2024년 7월 10만명 수영장 3개월 100%"  # 오타인 '수영징'만 고쳐졌다
    assert not any(a in {"개월", "만명", "년"} for a, _ in spy.calls)
    assert re.findall(r"\d+", r.text) == re.findall(r"\d+", text)


def test_digit_adjacent_hangul_is_skipped_even_if_it_looks_like_a_typo() -> None:
    always_one = Corrector(VOCAB, jamo=lambda s: s, distance=lambda a, b: 1)  # 모든 낱말이 후보와 1칸 차이라고 우기는 극단
    r = always_one.correct("7수영징 수영징7 10수연장명")
    assert r.text == "7수영징 수영징7 10수연장명" and not r.corrections


def test_idempotent() -> None:
    first = make().correct("올팍 수영징 테니스짱")
    second = make().correct(first.text)
    assert second.text == first.text and not second.corrections and not second.suggestions


def test_fuzz_never_crashes_and_keeps_digits() -> None:
    rng = random.Random(11)
    always_one = Corrector(VOCAB, jamo=lambda s: s, distance=lambda a, b: rng.choice([1, 2, 3]))
    alphabet = "수영장징짱올팍테니스 0123456789년월만명%?!가나다"
    for _ in range(2000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
        r = always_one.correct(text)
        assert re.findall(r"\d+", r.text) == re.findall(r"\d+", text)
        for m in re.finditer(r"\d[가-힣]+|[가-힣]+\d", text):  # 숫자에 붙은 한글은 그대로 남아 있다
            assert m.group() in r.text


# --------------------------------------------------------------------------- 사전 파일


def test_load_vocab_rejects_bad_files(tmp_path: Path) -> None:
    bad = tmp_path / "a.json"
    bad.write_text(json.dumps({"version": 2, "vocab": [], "abbreviations": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="버전"):
        load_vocab(bad)
    bad.write_text(json.dumps({"version": 1, "vocab": [{"w": "가"}], "abbreviations": {}}), encoding="utf-8")
    with pytest.raises(KeyError):
        load_vocab(bad)


def test_committed_aliases_file_is_well_formed() -> None:
    data = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
    vocab = load_vocab(ALIASES_FILE)
    assert vocab.abbreviations == {"올팍": "올림픽공원", "한체산": "한국체육산업개발"}
    allowed_prefix = ("title.", "alias.", *(f"{t}.{c}" for t, c in A.VOCAB_COLUMNS))
    for item in data["vocab"]:
        assert re.fullmatch(r"[가-힣]{2,10}", item["w"]), item
        assert item["n"] >= 1 and item["src"]
        assert all(s.startswith(allowed_prefix) for s in item["src"]), item  # 출처가 데이터·데이터 이름뿐(시험 질문 단어 금지)
    assert len({w["w"] for w in data["vocab"]}) == len(data["vocab"])
    assert all(re.fullmatch(r"[가-힣]{3,10}", w) for w in data["known"])
    assert not set(data["known"]) & set(vocab.words) and data["known"] == sorted(data["known"])
    assert any("올팍" in w for w in vocab.words)  # 약칭 '올팍'은 데이터 안의 이름(올팍워킹 등)에도 쓰인다
    assert {"수영장", "테니스장", "올림픽공원"} <= set(vocab.words)


@needs_data
def test_committed_aliases_match_regenerated_from_data(tmp_path: Path) -> None:
    """데이터가 바뀌었는데 사전을 다시 만들지 않으면 여기서 알린다."""
    db = tmp_path / "x.sqlite"
    build(RAW_DIR, db)
    con = sqlite3.connect(db)
    build_docs(con, HISTORY_HTML)
    con.close()
    fresh = json.loads(json.dumps(A.build_aliases(db), ensure_ascii=False))
    assert fresh == json.loads(ALIASES_FILE.read_text(encoding="utf-8"))


def test_hangul_words() -> None:
    assert A.hangul_words("올림픽 수영장(성인)/A반 2기") == ["올림픽", "수영장", "성인"]
    assert A.hangul_words("가") == [] and A.hangul_words("") == []


# --------------------------------------------------------------------------- 실제 함수 연결(작성 후 자동으로 켜짐)


def real() -> Corrector:
    return Corrector(load_vocab(ALIASES_FILE))  # 기본값 = typo.py의 실제 to_jamo·edit_distance


@pytest.mark.parametrize(
    ("typed", "fixed"),
    [
        ("올팍 수영징", "올림픽공원 수영장"),
        ("테니스짱", "테니스장"),
        ("올림피공원 주차", "올림픽공원 주차"),
        ("수영장은", "수영장은"),
    ],
)
def test_real_functions_fix_obvious_typos(typed: str, fixed: str) -> None:
    assert real().correct(typed).text == fixed


def test_real_functions_leave_numbers_and_known_words() -> None:
    r = real().correct("2024년 7월 인라인 10만명")
    assert r.text == "2024년 7월 인라인 10만명" and not r.corrections
