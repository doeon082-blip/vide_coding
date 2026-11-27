"""원본 값 파싱: 사람 수(`*` 비식별 포함), 날짜, 시각, 시(hour).

원본의 실제 표기는 파일을 열어 확인하기 전이라, 흔한 형식을 받되 **모르는 표기는 조용히
넘기지 않는다**(사람 수는 ValueError, 날짜·시각은 None). 그래야 표기가 예상과 다를 때
수집 통계의 "bad rows"로 드러난다.
"""

from __future__ import annotations

import re
from datetime import date, time


def parse_count(raw: str | None) -> tuple[float | None, bool]:
    """사람 수 문자열 → (값, 비식별 여부).

    '*'(여러 개 포함)는 3명 이하 비식별이라 값을 만들지 않고 (None, True)로 돌려준다.
    빈 문자열은 (None, False)로 결측이다. 쉼표(천 단위)는 허용한다.
    숫자도 `*`도 아닌 값은 표기를 잘못 짐작한 것이므로 ValueError로 알린다.
    """
    s = (raw or "").strip()
    if s == "":
        return None, False
    if set(s) == {"*"}:
        return None, True
    try:
        return float(s.replace(",", "")), False
    except ValueError:
        raise ValueError(f"해석할 수 없는 사람 수 표기: {raw!r}") from None


_DATE_RES = (
    re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)"),  # 2025-10-18, 2025/10/18, 2025.10.18
    re.compile(r"^(\d{4})(\d{2})(\d{2})$"),  # 20251018
    re.compile(r"^(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"),  # 2025년 10월 18일
)


def parse_date(raw: str | None) -> date | None:
    """날짜 문자열 → date. 형식이나 값이 틀리면(2025-02-30 등) None."""
    s = (raw or "").strip()
    for rx in _DATE_RES:
        m = rx.match(s)
        if m:
            try:
                return date(int(m[1]), int(m[2]), int(m[3]))
            except ValueError:
                return None
    return None


_TIME_RES = (
    re.compile(r"^(\d{1,2}):(\d{2})(?::\d{2})?$"),  # 19:00, 9:30, 19:00:00
    re.compile(r"^(\d{2})(\d{2})$"),  # 1900
    re.compile(r"^(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?$"),  # 19시, 19시 30분
)


def parse_time(raw: str | None) -> time | None:
    """시각 문자열 → time. '24:00'처럼 하루를 넘는 표기는 모호하므로 None."""
    s = (raw or "").strip()
    for rx in _TIME_RES:
        m = rx.match(s)
        if m:
            hh, mm = int(m[1]), int(m[2] or 0)
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                return time(hh, mm)
            return None
    return None


def parse_hour(raw: str | None) -> int | None:
    """시(hour) 0~23. '7', '07', '0700', '07:00' 모두 받는다. 1~2자리는 시로 본다."""
    s = (raw or "").strip()
    if re.fullmatch(r"\d{1,2}", s):
        h = int(s)
        return h if 0 <= h <= 23 else None
    t = parse_time(s)
    return t.hour if t else None
