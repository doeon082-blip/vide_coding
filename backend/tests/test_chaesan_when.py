"""기간 해석(core/when.py) 테스트. 오늘은 2026-11-28(토) KST로 고정한다."""

from __future__ import annotations

from datetime import date

import pytest

from app.chaesan.core.when import parse_when

TODAY = date(2026, 11, 28)
PARKING_RANGE = (date(2024, 7, 1), date(2024, 7, 31))  # 입출차 파일처럼 한 달분뿐인 데이터


@pytest.mark.parametrize(
    "msg, start, end",
    [
        ("7월에 몇 대였어?", date(2026, 7, 1), date(2026, 7, 31)),  # 축제 앱은 2027년 7월로 읽었다
        ("12월 이용자", date(2025, 12, 1), date(2025, 12, 31)),  # 아직 안 온 달은 작년
        ("11월 이용자", date(2026, 11, 1), date(2026, 11, 30)),
        ("지난달 이용자", date(2026, 10, 1), date(2026, 10, 31)),  # 축제 앱은 인식 못 했다
        ("이번 달", date(2026, 11, 1), TODAY),
        ("작년 이용자", date(2025, 1, 1), date(2025, 12, 31)),
        ("작년 7월", date(2025, 7, 1), date(2025, 7, 31)),
        ("올해 2월", date(2026, 2, 1), date(2026, 2, 28)),
        ("2024년 7월", date(2024, 7, 1), date(2024, 7, 31)),
        ("2023년", date(2023, 1, 1), date(2023, 12, 31)),
        ("요즘 행사", date(2026, 10, 29), TODAY),
    ],
)
def test_past_by_default(msg: str, start: date, end: date) -> None:
    w = parse_when(msg, TODAY)
    assert w is not None and (w.start, w.end) == (start, end) and not w.future


def test_month_resolved_inside_data_range() -> None:
    w = parse_when("7월 주차 몇 대야?", TODAY, PARKING_RANGE)
    assert w is not None and (w.start, w.end) == PARKING_RANGE and w.label == "2024년 7월"


def test_weekend_is_condition_not_this_weekend() -> None:
    w = parse_when("주말에 붐벼?", TODAY)  # 축제 앱은 '이번 주말' 날짜로 고정했다
    assert w is not None and w.start is None and w.weekdays == frozenset({5, 6})
    w = parse_when("2024년 7월 평일", TODAY)
    assert w is not None and w.start == date(2024, 7, 1) and w.weekdays == frozenset(range(5))
    w = parse_when("월요일 수영장", TODAY)
    assert w is not None and w.weekdays == frozenset({0})


def test_tomorrow_is_future() -> None:
    w = parse_when("내일 가도 돼?", TODAY)
    assert w is not None and w.future and w.start == date(2026, 11, 29)


@pytest.mark.parametrize("msg", ["테니스장은 몇 월에 붐벼?", "수영장 강좌 알려줘", "1990-01-01"])
def test_no_period(msg: str) -> None:
    assert parse_when(msg, TODAY) is None


@pytest.mark.parametrize(
    "msg, start, end",
    [
        ("10월 1일 행사", date(2026, 10, 1), date(2026, 10, 1)),  # 점검 전에는 10월 전체로 읽었다
        ("2024년 7월 15일", date(2024, 7, 15), date(2024, 7, 15)),
        ("2월 30일", date(2026, 2, 1), date(2026, 2, 28)),  # 없는 날은 달 전체
        ("이번 주 행사", date(2026, 11, 23), date(2026, 11, 29)),
        ("지난주 이용자", date(2026, 11, 16), date(2026, 11, 22)),
    ],
)
def test_day_and_week(msg: str, start: date, end: date) -> None:
    w = parse_when(msg, TODAY)
    assert w is not None and (w.start, w.end) == (start, end)


def test_this_weekend_has_dates_and_condition() -> None:
    w = parse_when("이번 주말 행사 있어?", date(2026, 11, 26))  # 목요일
    assert w is not None and (w.start, w.end) == (date(2026, 11, 28), date(2026, 11, 29))
    assert w.weekdays == frozenset({5, 6}) and w.future and w.label.count("주말") == 1


def test_month_day_does_not_eat_sunday() -> None:
    w = parse_when("7월 일요일", TODAY)
    assert w is not None and (w.start, w.end) == (date(2026, 7, 1), date(2026, 7, 31)) and w.weekdays == frozenset({6})
