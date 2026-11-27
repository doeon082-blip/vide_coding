"""질문 속 기간 표현("7월", "지난달", "작년", "주말")을 날짜 범위로 바꾼다.

축제 앱의 parse_window는 앞으로 열릴 축제를 찾느라 "7월"을 다가올 7월로 읽었다.
채산은 이미 쌓인 데이터를 묻는 질문이 대부분이라 **과거를 기본**으로 읽는다.
연도 없는 "M월"은 데이터 기간(data_range)이 주어지면 그 안에서 가장 최근의 M월로 정한다
(예: 입출차 자료가 2024년 7월뿐이면 "7월"은 2024년 7월). 판단은 코드가 하고 LLM에 맡기지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True, slots=True)
class When:
    start: date | None  # None이면 기간 제한 없음(요일 조건만 있는 경우)
    end: date | None
    label: str
    weekdays: frozenset[int] | None = None  # 0=월 … 6=일. "주말"이면 {5, 6}
    future: bool = False  # 예보가 필요한 질문(내일·모레). 1단계에서는 "아직 연결 안 됨"으로 답한다


_WEEKEND = frozenset({5, 6})
_WEEKDAYS = frozenset({0, 1, 2, 3, 4})
_DAY_NAMES = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}

_YEAR_MONTH = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*년\s*(1[0-2]|0?[1-9])\s*월")
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*년")
_MONTH = re.compile(r"(?<!\d)(1[0-2]|0?[1-9])\s*월")
_DAY_OF_WEEK = re.compile(r"([월화수목금토일])요일")


def _month_end(year: int, month: int) -> date:
    first_next = date(year + (month == 12), month % 12 + 1, 1)
    return first_next - timedelta(days=1)


def _month(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), _month_end(year, month)


def _overlaps(a: tuple[date, date], b: tuple[date, date]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def _resolve_month(month: int, today: date, data_range: tuple[date, date] | None) -> int:
    """연도 없는 M월의 연도를 정한다: 데이터 기간 안의 가장 최근 M월 → 없으면 오늘 이전의 가장 최근 M월."""
    if data_range:
        for year in range(data_range[1].year, data_range[0].year - 1, -1):
            if _overlaps(_month(year, month), data_range):
                return year
    return today.year if month <= today.month else today.year - 1


def _weekday_filter(msg: str) -> tuple[frozenset[int] | None, str]:
    if "주말" in msg:
        return _WEEKEND, "주말"
    if "평일" in msg:
        return _WEEKDAYS, "평일"
    days = _DAY_OF_WEEK.findall(msg)
    if days:
        return frozenset(_DAY_NAMES[d] for d in days), "·".join(f"{d}요일" for d in days)
    return None, ""


def _period(msg: str, today: date, data_range: tuple[date, date] | None) -> When | None:
    if "모레" in msg:
        d = today + timedelta(days=2)
        return When(d, d, "모레", future=True)
    if "내일" in msg:
        d = today + timedelta(days=1)
        return When(d, d, "내일", future=True)
    m = _YEAR_MONTH.search(msg)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return When(*_month(y, mo), f"{y}년 {mo}월")
    if re.search(r"지난\s*달|저번\s*달", msg):
        prev_end = today.replace(day=1) - timedelta(days=1)
        return When(*_month(prev_end.year, prev_end.month), f"지난달({prev_end.year}년 {prev_end.month}월)")
    if re.search(r"이번\s*달", msg):
        return When(today.replace(day=1), today, f"이번 달({today.year}년 {today.month}월)")
    last_year = bool(re.search(r"작년|지난\s*해", msg))
    this_year = bool(re.search(r"올해|금년", msg))
    m = _MONTH.search(msg)
    if m:  # "작년 7월", "올해 3월"처럼 상대 연도가 붙으면 그 연도, 아니면 데이터 기준으로 정한다
        mo = int(m.group(1))
        y = today.year - 1 if last_year else today.year if this_year else _resolve_month(mo, today, data_range)
        return When(*_month(y, mo), f"{y}년 {mo}월")
    if last_year:
        y = today.year - 1
        return When(date(y, 1, 1), date(y, 12, 31), f"작년({y}년)")
    if this_year:
        return When(date(today.year, 1, 1), today, f"올해({today.year}년)")
    m = _YEAR.search(msg)
    if m:
        y = int(m.group(1))
        return When(date(y, 1, 1), date(y, 12, 31), f"{y}년")
    if "요즘" in msg or "최근" in msg:
        return When(today - timedelta(days=30), today, "최근 30일")
    if re.search(r"오늘|지금|현재", msg):
        return When(today, today, "오늘")
    return None


def parse_when(msg: str, today: date, data_range: tuple[date, date] | None = None) -> When | None:
    """질문에서 기간과 요일 조건을 읽는다. 아무 표현도 없으면 None.
    today는 반드시 KST 날짜(ports.Clock)를 넘긴다. data_range는 그 질문이 쓸 데이터 카드의 실제 기간."""
    period = _period(msg, today, data_range)
    weekdays, wlabel = _weekday_filter(msg)
    if period is None and weekdays is None:
        return None
    if period is None:
        return When(None, None, wlabel, weekdays=weekdays)
    if weekdays is None:
        return period
    return When(period.start, period.end, f"{period.label} {wlabel}", weekdays=weekdays, future=period.future)
