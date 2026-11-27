"""행사 표(events)에 쓰는 공통 함수. 원본 파일의 열 이름은 확인 후에 추가한다."""

from __future__ import annotations

import hashlib
import re


def _clean(value: str | None) -> str:
    """앞뒤 공백 제거 + 연속 공백을 하나로. 같은 행사가 공백 차이로 다른 id가 되는 걸 막는다."""
    return re.sub(r"\s+", " ", (value or "")).strip()


def build_event_key(name: str, venue: str, date: str, start_time: str | None) -> str:
    """행사 id. 같은 입력이면 항상 같은 값이라 다시 수집해도 중복이 생기지 않는다.

    models.build_festival_key와 같은 방식(SHA-256, '|' 연결)이다. 그 함수는 축제 전용 인자에
    묶여 있어 직접 쓰지 못해 새로 만들었다. date는 'YYYY-MM-DD'로 정규화한 문자열을 받는다.
    시작 시각이 없는 행사는 빈 문자열로 처리한다.
    """
    joined = "|".join(_clean(p) for p in (name, venue, date, start_time))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
