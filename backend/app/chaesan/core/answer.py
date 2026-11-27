"""답변 검사 (핵심 함수 2). 설명 생성·배지는 E단계에서 이 파일에 더한다.

역할 원칙: 숫자는 코드가 계산하고 LLM은 설명만 한다. 그래서 LLM이 쓴 문장의 숫자가 **조회 결과에 있는 값**인지 코드가 확인하고,
하나라도 없으면 그 숫자를 말하지 않는다(근거 표만 보여 준다).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any, Final

# 숫자 덩어리: 쉼표 천 단위(215,528)와 소수점(3.5)을 한 덩어리로 읽는다. 축제 앱의 `\d+`는 215,528을 215와 528로 쪼개서
# 틀린 숫자도 통과시킬 수 있었다. 앞의 '-'는 부호일 때만 붙인다: 바로 앞이 숫자면 하이픈이다(2024-07-01).
# 숫자 앞에 글자가 붙어 있어도(약120명, 총130건, A2024) 숫자로 읽는다. 앞 글자를 따지면 한글이 붙은 숫자가 검사를 빠져나간다.
_NUMBER: Final = re.compile(r"(?:(?<!\d)-)?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")


def _to_decimal(token: str) -> Decimal | None:
    """'1,234.50' → Decimal('1234.50'). 값으로 비교하므로 '120'과 '120.0'은 같다. 못 읽으면 None."""
    try:
        value = Decimal(token.replace(",", ""))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _numbers_in(text: str) -> list[tuple[str, Decimal]]:
    """문장 속 (표시된 모양, 값) 목록. 전각 숫자(１２３)는 NFKC로 반각으로 바꿔서 읽는다(숫자 대조를 우회하지 못하게)."""
    out: list[tuple[str, Decimal]] = []
    for m in _NUMBER.finditer(unicodedata.normalize("NFKC", text)):
        value = _to_decimal(m.group())
        if value is not None:
            out.append((m.group(), value))
    return out


def _values_in(obj: Any) -> Iterable[Decimal]:
    """조회 결과 한 칸에서 숫자 값을 모두 꺼낸다. 숫자(bool 제외)는 그대로, 문자열은 안의 숫자('2024-07-01' → 2024, 7, 1),
    목록·표·사전은 안쪽을 꺼낸다. None·bool·그 밖의 값은 숫자가 아니다."""
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, int):
        yield Decimal(obj)
    elif isinstance(obj, float):
        if math.isfinite(obj):
            yield Decimal(repr(obj))  # repr은 가장 짧게 왕복되는 표기라 0.1이 0.1000000000000000055…로 변하지 않는다
    elif isinstance(obj, str):
        for _, value in _numbers_in(obj):
            yield value
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _values_in(v)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            yield from _values_in(v)


def find_unsupported_numbers(answer: str, result_rows: list[dict[str, Any]]) -> list[str]:
    """답 문장 속 숫자 중 조회 결과(result_rows)에 없는 것을, 나온 순서대로 중복 없이 돌려준다.
    빈 리스트면 숫자 대조 통과. 하나라도 있으면 답에서 숫자를 빼고 근거 표만 보여 준다.

    - 값으로 비교한다: '215,528'과 215528, '3.50'과 3.5는 같다. 부호도 구분한다(-5와 5는 다르다).
    - 조회 결과의 문자열 칸 속 숫자도 허용한다('2024-07-01'이 있으면 답의 '2024년 7월 1일'이 통과).
    - 한글로 쓴 수(삼십 명, 이천이십사)는 읽지 못한다 → 시스템 프롬프트가 아라비아 숫자로만 쓰게 하고, 설명 문장은
      호출한 쪽이 출력 검증에서 한 번 더 거른다(한계로 문서에 적어 둠).
    """
    allowed: set[Decimal] = set()
    for row in result_rows:
        allowed.update(_values_in(row))
    missing: list[str] = []
    for shown, value in _numbers_in(answer):
        if value not in allowed and shown not in missing:
            missing.append(shown)
    return missing
