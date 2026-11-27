"""값 파서 테스트: `*` 처리, 날짜·시각 파싱."""

from __future__ import annotations

from datetime import date, time

import pytest

from app.impact.parse import parse_count, parse_date, parse_hour, parse_time


def test_count_star_is_suppressed_not_filled() -> None:
    assert parse_count("*") == (None, True)
    assert parse_count(" ** ") == (None, True)


def test_count_numbers_and_missing() -> None:
    assert parse_count("12.5") == (12.5, False)
    assert parse_count("1,234") == (1234.0, False)
    assert parse_count("0") == (0.0, False)
    assert parse_count("") == (None, False)
    assert parse_count(None) == (None, False)


def test_count_unknown_notation_raises() -> None:
    for bad in ("N/A", "-", "3명 이하", "1.2.3"):
        with pytest.raises(ValueError):
            parse_count(bad)


@pytest.mark.parametrize("raw", ["2025-10-18", "2025/10/18", "2025.10.18", "20251018", "2025년 10월 18일",
                                 "2025-10-18 19:00:00", " 2025-10-18 "])
def test_date_formats(raw: str) -> None:
    assert parse_date(raw) == date(2025, 10, 18)


@pytest.mark.parametrize("raw", ["", None, "2025-02-30", "18/10/2025", "abc", "2025-13-01", "2025101"])
def test_date_invalid_is_none(raw: str | None) -> None:
    assert parse_date(raw) is None


@pytest.mark.parametrize("raw,expect", [("19:00", time(19, 0)), ("9:30", time(9, 30)), ("19:00:00", time(19, 0)),
                                        ("1930", time(19, 30)), ("19시", time(19, 0)), ("19시 30분", time(19, 30))])
def test_time_formats(raw: str, expect: time) -> None:
    assert parse_time(raw) == expect


@pytest.mark.parametrize("raw", ["", None, "24:00", "25:00", "19:75", "저녁"])
def test_time_invalid_is_none(raw: str | None) -> None:
    assert parse_time(raw) is None


def test_hour() -> None:
    assert parse_hour("0") == 0 and parse_hour("07") == 7 and parse_hour("23") == 23
    assert parse_hour("0700") == 7 and parse_hour("07:00") == 7
    assert parse_hour("24") is None and parse_hour("") is None and parse_hour("x") is None
