"""날짜 문자열 도우미 (표준 라이브러리만): 'YYYY-MM-DD', 'YYYY-MM', 'YYYY' 꼴의 부분 날짜를 다룬다.

데이터 카드의 기간·문서 날짜는 정밀도가 제각각(일/월/연)이라, 그 기간의 마지막 날 같은 값을 한 곳에서 계산해 쓴다.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Final

_PARTIAL: Final = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")


def period_end(text: str) -> tuple[int, int | None, date] | None:
    """'2024-07-31' / '2024-07' / '2024' → (연, 월 또는 None, 그 기간의 마지막 날). 형식이 다르면 None."""
    m = _PARTIAL.match(text)
    if not m:
        return None
    year, month, day = int(m.group(1)), int(m.group(2)) if m.group(2) else None, int(m.group(3)) if m.group(3) else None
    if month is not None and not 1 <= month <= 12:  # 13월·0월을 다음·이전 달 계산에 흘려보내면 엉뚱한 날짜가 나온다
        return None
    try:
        if month is None:
            return year, None, date(year, 12, 31)
        if day is None:
            return year, month, date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
        return year, month, date(year, month, day)
    except ValueError:
        return None
