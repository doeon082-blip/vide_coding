"""부분 날짜(일·월·연 정밀도) 도우미 테스트."""

from __future__ import annotations

from datetime import date

import pytest

from app.chaesan.core.dates import period_end


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2024-07-31", (2024, 7, date(2024, 7, 31))),
        ("2024-07", (2024, 7, date(2024, 7, 31))),  # 월 정밀도는 그 달의 마지막 날
        ("2024-02", (2024, 2, date(2024, 2, 29))),  # 윤년
        ("2023-02", (2023, 2, date(2023, 2, 28))),
        ("2024-12", (2024, 12, date(2024, 12, 31))),
        ("2024", (2024, None, date(2024, 12, 31))),  # 연 정밀도는 그 해의 마지막 날
    ],
)
def test_period_end(text: str, expected: tuple[int, int | None, date]) -> None:
    assert period_end(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "2024-13", "2024-00", "2024-02-30", "24-07", "2024-7", "2024-07-01-02", " 2024"])
def test_period_end_rejects_bad_input(text: str) -> None:
    assert period_end(text) is None
