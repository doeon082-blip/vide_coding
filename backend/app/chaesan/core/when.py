"""질문 속 기간 표현("7월", "지난달", "작년", "주말")을 날짜 범위로 바꾼다.

축제 앱의 parse_window는 앞으로 열릴 축제를 찾느라 "7월"을 다가올 7월로 읽었다.
채산은 이미 쌓인 데이터를 묻는 질문이 대부분이라 **과거를 기본**으로 읽는다.
연도 없는 "M월"은 데이터 기간(data_range)이 주어지면 그 안에서 가장 최근의 M월로 정한다
(예: 입출차 자료가 2024년 7월뿐이면 "7월"은 2024년 7월). 판단은 코드가 하고 LLM에 맡기지 않는다.
다만 '소식' 갈래("12월 25일 행사 있어?")는 앞으로의 일을 묻는 경우가 많아 prefer="future"로 부른다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Literal

# 연도 없는 날짜를 과거로 읽을지 미래로 읽을지. 데이터·역사 질문은 past, 소식(행사 예정) 질문은 future.
type Prefer = Literal["past", "future"]


@dataclass(frozen=True, slots=True)
class When:
    start: date | None  # None이면 기간 제한 없음(요일 조건만 있는 경우)
    end: date | None
    label: str
    weekdays: frozenset[int] | None = None  # 0=월 … 6=일. "주말"이면 {5, 6}
    future: bool = False  # 기간이 오늘 이후(내일·이번 주말 등). 예보가 필요한지는 답변 엔진이 갈래를 보고 정한다
    # 날짜와 요일이 맞지 않음(예: 2026-07-01은 수요일인데 '7월 1일 일요일'). 답하지 말고 되묻는다.
    conflict: bool = False


_WEEKEND = frozenset({5, 6})
_WEEKDAYS = frozenset({0, 1, 2, 3, 4})
_DAY_NAMES = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}

# 일(day)은 선택. "7월 1일"은 그날 하루, "7월"은 한 달 전체.
_DAY = r"(?:\s*(3[01]|[12]\d|0?[1-9])\s*일(?!\s*요))?"
_YEAR_MONTH = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*년\s*(1[0-2]|0?[1-9])\s*월" + _DAY)
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*년")
_MONTH = re.compile(r"(?<!\d)(1[0-2]|0?[1-9])\s*월" + _DAY)
_DAY_OF_WEEK = re.compile(r"([월화수목금토일])요일")


def _month_end(year: int, month: int) -> date:
    first_next = date(year + (month == 12), month % 12 + 1, 1)
    return first_next - timedelta(days=1)


def _month(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), _month_end(year, month)


def _span(year: int, month: int, day: str | None, label: str) -> When:
    """M월 또는 M월 D일 → When. 달력에 없는 날(2월 30일)은 한 달 전체로 읽고 라벨에 일을 붙이지 않는다."""
    start, end = _month(year, month)
    if day and int(day) <= end.day:
        d = date(year, month, int(day))
        return When(d, d, f"{label} {int(day)}일")
    return When(start, end, label)


def _overlaps(a: tuple[date, date], b: tuple[date, date]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def _resolve_month(month: int, today: date, data_range: tuple[date, date] | None, prefer: Prefer) -> int:
    """연도 없는 M월의 연도를 정한다: 데이터 기간 안의 가장 최근 M월이 있으면 그것.
    없으면 past는 오늘 이전의 가장 최근 M월, future는 오늘 이후의 가장 가까운 M월(이번 달 포함)."""
    if data_range:
        for year in range(data_range[1].year, data_range[0].year - 1, -1):
            if _overlaps(_month(year, month), data_range):
                return year
    if prefer == "future":
        return today.year if month >= today.month else today.year + 1
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


def _period(msg: str, today: date, data_range: tuple[date, date] | None, prefer: Prefer) -> When | None:
    if "모레" in msg:
        d = today + timedelta(days=2)
        return When(d, d, "모레")
    if "내일" in msg:
        d = today + timedelta(days=1)
        return When(d, d, "내일")
    m = _YEAR_MONTH.search(msg)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return _span(y, mo, m.group(3), f"{y}년 {mo}월")
    monday = today - timedelta(days=today.weekday())
    if re.search(r"이번\s*주말", msg):  # '주말' 조건보다 먼저: 이번 주의 토·일 날짜
        sat = monday + timedelta(days=5)
        return When(sat, sat + timedelta(days=1), f"이번 주말({sat:%m/%d}~)", weekdays=_WEEKEND)
    if re.search(r"이번\s*주(?!말)", msg):
        return When(monday, monday + timedelta(days=6), "이번 주")
    if re.search(r"(?:지난|저번)\s*주(?!말)", msg):
        start = monday - timedelta(days=7)
        return When(start, start + timedelta(days=6), "지난주")
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
        y = today.year - 1 if last_year else today.year if this_year else _resolve_month(mo, today, data_range, prefer)
        return _span(y, mo, m.group(2), f"{y}년 {mo}월")
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


def _no_matching_day(start: date, end: date, weekdays: frozenset[int]) -> bool:
    """기간 안에 요일 조건에 맞는 날이 하루도 없는가. 7일 이상이면 모든 요일이 들어 있다."""
    span = (end - start).days + 1
    return span < 7 and not any((start + timedelta(days=i)).weekday() in weekdays for i in range(span))


def parse_when(
    msg: str, today: date, data_range: tuple[date, date] | None = None, prefer: Prefer = "past"
) -> When | None:
    """질문에서 기간과 요일 조건을 읽는다. 아무 표현도 없으면 None.
    today는 반드시 KST 날짜(ports.Clock)를 넘긴다. data_range는 그 질문이 쓸 데이터 카드의 실제 기간.
    prefer는 연도 없는 날짜의 방향(위 Prefer 설명)."""
    period = _period(msg, today, data_range, prefer)
    weekdays, wlabel = _weekday_filter(msg)
    if period is None and weekdays is None:
        return None
    if period is None:
        result = When(None, None, wlabel, weekdays=weekdays)
    elif weekdays is None or period.weekdays is not None:  # "이번 주말"은 이미 요일 조건을 가진다
        result = period
    else:
        result = replace(period, label=f"{period.label} {wlabel}", weekdays=weekdays)
    # 미래 여부는 경우마다 따로 적지 않고 시작일 하나로 정한다(빠뜨림 방지)
    conflict = bool(
        result.start and result.end and result.weekdays and _no_matching_day(result.start, result.end, result.weekdays)
    )
    return replace(result, future=result.start is not None and result.start > today, conflict=conflict)
