"""CSV 문자열 값을 DB 값으로 바꾸는 변환기.

변환기마다 (DB에 넣을 값, 원래 값 또는 None)을 돌려준다. 두 번째 값이 None이 아니면
변환에 실패했거나 기본값(1990-01-01)이라 날짜 없음으로 처리한 것이고, 원래 값은 `<열>_raw` 칸에 남긴다.
원본 데이터를 고치지 않고, 바꾼 흔적을 남기기 위해서다.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Final

type Value = str | int | None
type Converted = tuple[Value, str | None]
type Converter = Callable[[str], Converted]

# 여러 표에 "날짜 없음" 대신 들어 있는 기본값. 실제 날짜로 쓰지 않는다(B단계에서 15101610·15110953·15144839 확인).
DEFAULT_DATE: Final = "1990-01-01"

_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_TIME_RANGE = re.compile(r"^\s*(\d{1,2}:\d{2})\s*[~-]\s*(\d{1,2}:\d{2})\s*$")
# 15099006 공연일에는 "2011-9-18", "2009- 3- 1"처럼 0을 안 붙이거나 공백이 낀 날짜가 있다
_FIRST_DATE = re.compile(r"(?<!\d)(\d{4})-\s*(\d{1,2})-\s*(\d{1,2})(?!\d)")


def text(v: str) -> Converted:
    """앞뒤 공백만 지운다. 빈 문자열은 NULL."""
    s = v.strip()
    return (s or None), None


def integer(v: str) -> Converted:
    """정수. 쉼표는 허용한다. 빈 값은 NULL, 정수가 아니면 NULL + 원래 값."""
    s = v.strip().replace(",", "")
    if not s:
        return None, None
    return (int(s), None) if re.fullmatch(r"-?\d+", s) else (None, v)


def iso_date(v: str) -> Converted:
    """YYYY-MM-DD 날짜. 1990-01-01(기본값)과 달력에 없는 날은 NULL + 원래 값.
    9999-12-31은 '종료일 없음(운영 중)'이라는 뜻이 있어 그대로 둔다."""
    s = v.strip()
    if not s:
        return None, None
    if s == DEFAULT_DATE:
        return None, v
    try:
        return date.fromisoformat(s).isoformat(), None
    except ValueError:
        return None, v


def iso_datetime(v: str) -> Converted:
    """YYYY-MM-DD HH:MM[:SS] → 'YYYY-MM-DD HH:MM:SS'. 공백 구분은 SQLite 날짜 함수가 그대로 읽는 ISO 형식이다."""
    s = v.strip()
    if not s:
        return None, None
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None, v
    if d.date().isoformat() == DEFAULT_DATE:
        return None, v
    return d.strftime("%Y-%m-%d %H:%M:%S"), None


def yyyymmdd(v: str) -> Converted:
    """'20120816' 꼴 → ISO 날짜. 자리 수가 틀린 값('201200820')은 NULL + 원래 값."""
    s = v.strip()
    if not s:
        return None, None
    if not re.fullmatch(r"\d{8}", s):
        return None, v
    return iso_date(f"{s[:4]}-{s[4:6]}-{s[6:]}")


def month_ko(v: str) -> Converted:
    """'01월' → 1."""
    m = re.fullmatch(r"\s*(1[0-2]|0?[1-9])\s*월\s*", v)
    return (int(m.group(1)), None) if m else (None, v or None)


def hour_of_time(v: str) -> Converted:
    """'HH:MM:SS' → 시(hour)만. 15164156 등록시간의 분·초 자리에 등록일의 월·일이 들어 있어(699/699 확인) 시만 믿는다."""
    m = re.fullmatch(r"\s*([01]\d|2[0-3]):\d{2}:\d{2}\s*", v)
    return (int(m.group(1)), None) if m else (None, v or None)


def first_date(v: str) -> Converted:
    """자유 문장('2008-12-13(토) 7:00 / 2008-12-14(일)')에서 첫 날짜만 뽑는다. 원문은 따로 text 칸에 남긴다."""
    m = _FIRST_DATE.search(v)
    if not m:
        return None, v.strip() or None
    y, mo, d = m.groups()
    out, bad = iso_date(f"{y}-{int(mo):02d}-{int(d):02d}")
    return (out, None) if bad is None else (None, v)


def split_date_range(v: str) -> tuple[Converted, Converted]:
    """'시작~종료' → (시작, 종료). 시각이 붙어 있으면('1990-01-01 00:00:00~…') 날짜만 쓴다."""
    parts = v.split("~")
    if len(parts) != 2:
        return (None, v or None), (None, v or None)
    out: list[Converted] = []
    for part in (p.strip() for p in parts):
        value, bad = iso_date(part[:10])
        # 실패하면 잘린 10자가 아니라 원래 조각 전체를 남긴다(시각까지 보존)
        out.append((value, None) if bad is None else (None, part))
    return out[0], out[1]


def split_time_range(v: str) -> tuple[Converted, Converted]:
    """'11:20~12:50' 또는 '18:00-19:30' → ('11:20', '12:50'). 한 자리 시는 앞에 0을 붙인다."""
    m = _TIME_RANGE.match(v)
    if not m:
        return (None, v or None), (None, v or None)
    out: list[Converted] = []
    for t in m.groups():
        t = t.zfill(5)
        out.append((t, None) if _TIME.match(t) else (None, v))
    return out[0], out[1]
