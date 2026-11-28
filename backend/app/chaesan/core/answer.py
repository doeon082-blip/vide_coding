"""답변 검사 (핵심 함수 2). 설명 생성·배지는 E단계에서 이 파일에 더한다.

역할 원칙: 숫자는 코드가 계산하고 LLM은 설명만 한다. 그래서 LLM이 쓴 문장의 숫자가 **조회 결과에 있는 값**인지 코드가 확인하고,
하나라도 없으면 그 숫자를 말하지 않는다(근거 표만 보여 준다).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from app.chaesan.core.catalog import Card
from app.chaesan.core.config import STALE_DAYS
from app.chaesan.core.dates import period_end

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


# --------------------------------------------------------------------------- 배지(최신성·주의 표시)

FLAG_BADGES: Final[dict[str, str]] = {
    "check_operating": "운영 여부는 센터에 확인하세요",
    "mixed_sources": "같은 기간 다른 자료와 값이 다를 수 있어요(주의점 참고)",
}
NO_BODY_BADGE: Final = "본문 없음, 원문 링크 확인"


def freshness_badges(card: Card, today: date) -> list[str]:
    """카드의 마지막 자료 날짜와 오늘(KST)을 비교한 배지: '2024년 7월 자료', 1년을 넘으면 '1년 넘게 갱신 안 됨'."""
    parsed = period_end(card.last_data_date) if card.last_data_date else None
    if parsed is None:
        return ["기간 정보 없음"]
    year, month, end = parsed
    badges = [f"{year}년 {month}월 자료" if month else f"{year}년 자료"]
    if (today - end).days > STALE_DAYS:
        badges.append("1년 넘게 갱신 안 됨")
    return badges


def card_badges(card: Card, today: date) -> list[str]:
    """최신성 배지 + 카드의 주의 표시(운영 여부 확인, 값 충돌)."""
    return freshness_badges(card, today) + [FLAG_BADGES[f] for f in card.flags if f in FLAG_BADGES]


# --------------------------------------------------------------------------- 한글로 쓴 수

_UNITS: Final = r"(?:명|건|대|개|원|회|곳|배|번|시간|분|개월|퍼센트)"
_SINO: Final = re.compile(r"(?<![가-힣\d])(?:[일이삼사오육칠팔구]?[십백천만억][일이삼사오육칠팔구십백천만억]*)\s*" + _UNITS)
_NATIVE: Final = re.compile(
    r"(?<![가-힣\d])(?:열|스물|스무|서른|마흔|쉰|예순|일흔|여든|아흔)[한두세네다섯여섯일곱여덟아홉]?\s*" + _UNITS
)


def has_hangul_number(text: str) -> bool:
    """'삼십 명', '이천 원', '열 명'처럼 한글로 쓴 수가 있는가. find_unsupported_numbers는 아라비아 숫자만 읽으므로,
    한글 수가 섞인 문장은 숫자 대조를 통과한 것으로 볼 수 없어 따로 거른다.
    '한 명'처럼 십·백·천·만이 없는 한 글자 수는 보지 않는다(흔한 낱말과 구분할 수 없다)."""
    return bool(_SINO.search(text) or _NATIVE.search(text))


# --------------------------------------------------------------------------- 설명 생성

ANSWER_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "answers_question": {"type": "boolean"}},
    "required": ["answer", "answers_question"],
}


def build_explain_prompt(
    question: str,
    evidence_lines: Sequence[str],
    caveats: Sequence[str],
    schema: Sequence[str] = (),
    queries: Sequence[str] = (),
) -> tuple[str, str, str]:
    """(임무 문장, 데이터 블록, 지시문). 채산 말투는 여기(설명 생성 프롬프트)에만 둔다: 말투를 바꾸는 별도 LLM 호출을 만들면
    호출 수와 숫자가 변형될 위험이 늘기 때문이다."""
    data = "[질문] " + question + "\n[근거]\n" + "\n".join(evidence_lines)
    if schema:
        data += "\n[자료 설명: 열 이름과 뜻]\n" + "\n".join(schema)
    if queries:
        data += "\n[조회한 SQL: 코드가 검사하고 실행한 것]\n" + "\n".join(queries)
    if caveats:
        data += "\n[주의점]\n" + "\n".join(f"- {c[:120]}" for c in caveats[:3])
    instruction = (
        "위 [근거]만으로 질문에 두 문장 이내(150자 이내)로 답하고 "
        'JSON {"answer": "...", "answers_question": true|false}만 출력한다. '
        "숫자와 날짜는 [근거]에 있는 것만 아라비아 숫자(0~9)로 쓰고, 직접 계산하거나 합치지 않는다. "
        "[근거]에 없는 내용은 말하지 않는다. 근거가 문서 제목뿐이면 내용을 지어내지 말고 '기록에 따르면'처럼 말한다. "
        "열의 뜻은 [자료 설명]을 따른다. 결과 열 이름이 SUM(users)처럼 모호하면 [조회한 SQL]의 조건과 계산이 그 값의 뜻이다: "
        "그 계산이 질문의 조건을 그대로 구했다면 그 값으로 답한다. 질문의 말(붐빈다, 많다)을 근거의 수량(대수, 인원, 건수)으로 "
        "읽을 수 있으면 답하되, 어떤 수량을 기준으로 읽었는지 답에 밝힌다. "
        "[주의점] 중 이 답에 실제로 영향을 주는 것만 한 문장으로 덧붙이고(해당이 없으면 아무것도 덧붙이지 않는다), "
        "그 때문에 answers_question을 false로 하지 않는다. "
        "질문에 나온 이름(장소·종목·기관 등)이 [근거]·[자료 설명]·[조회한 SQL] 어디에도 나오지 않으면 "
        "비슷해 보이는 다른 항목으로 대신 답하지 말고 answers_question=false로 한다. "
        "answers_question=false는 근거의 열이 질문이 묻는 것과 종류가 다를 때(예: 금액 열로 인원을 답해야 할 때)나 "
        "근거가 비었을 때만 쓰고, 그때 answer에는 '이 자료로는 알 수 없어요'라고 쓴다. "
        "[요약]이 있으면 그것이 전체 일치 문서에 대한 사실이다: "
        "'언제부터·처음'에는 '가장 이른 날짜', '최근·마지막'에는 '가장 늦은 날짜', '몇 건'에는 '총 건수'를 쓴다. "
        "말투는 채산: 짧고 친절한 존댓말('~예요', '~했어요'). 링크·URL·SQL은 쓰지 않는다."
    )
    return "[근거]에 있는 사실만으로 시민의 질문에 짧게 답한다.", data, instruction


def fallback_answer(kind: str, count: int) -> str:
    """LLM 설명을 쓸 수 없을 때(숫자 대조 실패, 한글 수, 오류)의 답. 숫자는 코드가 센 값(count)뿐이다."""
    if kind == "documents":
        return f"관련 기록 {count}건을 찾았어요. 자세한 내용은 아래 목록과 원문 링크를 확인해 주세요."
    return f"조회한 결과 {count}행을 표로 보여 드려요. 숫자는 아래 표를 확인해 주세요."
