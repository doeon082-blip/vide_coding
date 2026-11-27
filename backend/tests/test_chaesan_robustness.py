"""견고성 테스트: 무작위·극단 입력에도 약속한 예외 말고는 터지지 않는다.

고정 시드의 난수로 반복한다(같은 결과가 재현되도록, 새 의존성 없이).
시민 질문은 무엇이든 들어올 수 있으므로, 입력 때문에 서버 오류(500)가 나면 안 된다.
"""

from __future__ import annotations

import random
import string
from datetime import date, timedelta

import pytest

from app.chaesan.core import guard
from app.chaesan.core.guard import InjectionBlocked, OutputRejected
from app.chaesan.core.when import parse_when

RNG_SEED = 20261128
ITERATIONS = 3000

_SPECIAL = ["\x00", "​", "﻿", "‮", "＜ｓｃｒｉｐｔ＞", "<|im_start|>", "```", "<<<", ">>>", "\n\n\n", "\t", "　", "'; DROP TABLE x;--", "\\", "%", "😀", "ㅋㅋ", "ㅎ"]
_WORDS = ["올림픽공원", "테니스장", "수영장", "주차", "이용자", "몇 월", "가장", "많았어", "언제", "알려줘", "ignore", "previous", "시스템 프롬프트", "무시", "만 출력", "SELECT", "FROM", "UNION"]


def _random_text(rng: random.Random) -> str:
    parts: list[str] = []
    for _ in range(rng.randint(0, 12)):
        kind = rng.random()
        if kind < 0.3:
            parts.append(rng.choice(_WORDS))
        elif kind < 0.5:
            parts.append(rng.choice(_SPECIAL))
        elif kind < 0.7:
            parts.append("".join(rng.choice("가나다라마바사아자차카타파하") for _ in range(rng.randint(1, 8))))
        elif kind < 0.85:
            parts.append("".join(rng.choice(string.printable) for _ in range(rng.randint(1, 10))))
        else:
            parts.append("".join(chr(rng.randint(0x20, 0xFFFF)) for _ in range(rng.randint(1, 6)) if not 0xD800 <= rng.randint(0, 0xFFFF) <= 0xDFFF))
    return rng.choice(["", " ", "\n"]).join(parts)


def test_check_user_input_only_returns_text_or_blocks() -> None:
    rng = random.Random(RNG_SEED)
    for _ in range(ITERATIONS):
        text = _random_text(rng)
        try:
            out = guard.check_user_input(text)
        except InjectionBlocked:
            continue
        assert isinstance(out, str) and out and len(out) <= 200
        assert "\x00" not in out and "​" not in out and "﻿" not in out


def test_huge_and_odd_inputs_do_not_hang_or_crash() -> None:
    for text in ["가" * 1_000_000, "a" * 1_000_000, "\n" * 100_000, "(" * 50_000, "<" * 50_000, "ignore " * 20_000, "퟿" * 5000]:
        with pytest.raises(InjectionBlocked):
            guard.check_user_input(text)  # 길이 제한으로 막혀야 하고, 정규식이 오래 걸려 멈추면 안 된다


def test_sanitize_untrusted_never_raises_and_respects_limit() -> None:
    rng = random.Random(RNG_SEED + 1)
    for _ in range(ITERATIONS):
        out, flagged = guard.sanitize_untrusted(_random_text(rng), max_len=300)
        assert isinstance(out, str) and len(out) <= 300 and isinstance(flagged, bool)
        assert "<<<" not in out


def test_parse_guarded_json_only_dict_or_rejected() -> None:
    rng = random.Random(RNG_SEED + 2)
    samples = ['{"a": 1}', "[]", "null", "1", '"x"', "{", "}", '{"a": ', "```json\n{}\n```", "<think>x</think>{}", "\x00", ""]
    for _ in range(ITERATIONS):
        raw = rng.choice(samples) if rng.random() < 0.5 else _random_text(rng)
        try:
            out = guard.parse_guarded_json(raw, "CANARY-x")
        except OutputRejected:
            continue
        assert isinstance(out, dict)


# --------------------------------------------------------------------------- 기간 해석

_WHEN_TOKENS = [
    "7월", "13월", "0월", "00월", "1월", "12월", "2월 30일", "2월 29일", "31일", "0일", "32일", "4월 31일", "12월 31일",
    "작년", "올해", "지난달", "이번 달", "지난주", "이번 주", "이번 주말", "주말", "평일", "월요일", "일요일", "내일", "모레",
    "오늘", "요즘", "최근", "2024년", "1999년", "2099년", "0000년", "9999년", "1800년", "2024년 7월", "2024년 13월", "일", "월", "요일",
    "테니스장", "이용자", "몇", "?", "  ", "\n",
]  # fmt: skip
_TODAYS = [date(2026, 11, 28), date(2026, 1, 1), date(2026, 12, 31), date(2024, 2, 29), date(2026, 3, 1), date(2027, 1, 3)]
_RANGES = [None, (date(2024, 7, 1), date(2024, 7, 31)), (date(2021, 1, 1), date(2025, 12, 31)), (date(2026, 6, 1), date(2026, 6, 1))]


def test_parse_when_never_raises_and_results_are_consistent() -> None:
    rng = random.Random(RNG_SEED + 3)
    for _ in range(ITERATIONS * 3):
        msg = " ".join(rng.choice(_WHEN_TOKENS) for _ in range(rng.randint(0, 5)))
        today = rng.choice(_TODAYS)
        w = parse_when(msg, today, rng.choice(_RANGES), prefer=rng.choice(["past", "future"]))
        if w is None:
            continue
        assert w.label
        if w.start is not None or w.end is not None:
            assert w.start is not None and w.end is not None and w.start <= w.end, (msg, w)
        if w.weekdays is not None:
            assert w.weekdays and w.weekdays <= frozenset(range(7))
        assert w.future == (w.start is not None and w.start > today), (msg, today, w)
        if w.conflict:
            assert w.weekdays is not None and w.start is not None and (w.end - w.start).days < 6


def test_parse_when_every_calendar_month_and_day() -> None:
    """모든 달·일 조합과 윤년 경계를 빠짐없이 돌려 본다."""
    for today in (date(2026, 11, 28), date(2024, 2, 29), date(2026, 12, 31)):
        for month in range(1, 13):
            for day in range(1, 32):
                w = parse_when(f"{month}월 {day}일", today)
                assert w is not None and w.start is not None and w.start.month == month
                if w.start == w.end:
                    assert w.start.day == day  # 달력에 있는 날은 그날 하루
                else:
                    assert w.start.day == 1  # 없는 날(2월 30일 등)은 달 전체로 읽는다


def test_parse_when_week_boundaries() -> None:
    """모든 요일에서 '이번 주'는 월~일 7일이고 오늘을 포함하며, '지난주'는 정확히 7일 전이다."""
    start = date(2026, 11, 2)  # 월요일
    for i in range(14):
        today = start + timedelta(days=i)
        this_week = parse_when("이번 주", today)
        last_week = parse_when("지난주", today)
        assert this_week and last_week and this_week.start and this_week.end and last_week.start and last_week.end
        assert this_week.start.weekday() == 0 and (this_week.end - this_week.start).days == 6
        assert this_week.start <= today <= this_week.end
        assert (this_week.start - last_week.start).days == 7
        weekend = parse_when("이번 주말", today)
        assert weekend and weekend.start and weekend.start.weekday() == 5 and weekend.weekdays == frozenset({5, 6})


def test_too_long_input_is_rejected_before_running_detectors(monkeypatch: pytest.MonkeyPatch) -> None:
    """긴 입력은 탐지 정규식을 돌리기 전에 막는다(CPU 낭비·정규식 공격 방지)."""
    calls: list[int] = []
    monkeypatch.setattr(guard, "detect", lambda text: calls.append(len(text)) or guard.Detection())
    with pytest.raises(InjectionBlocked):
        guard.check_user_input("가" * 5000)
    assert calls == []
    guard.check_user_input("테니스장 이용자")  # 정상 질문은 탐지를 거친다
    assert len(calls) == 1
