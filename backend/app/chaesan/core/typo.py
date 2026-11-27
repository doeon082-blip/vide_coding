"""오타 보정의 기초 계산 (핵심 함수 3·4). 사전 비교·확신도는 correct.py에서 이 두 함수를 쓴다.

자모 = 한글 음절을 이루는 초성·중성·종성. "징"과 "장"은 글자로는 1개 다르지만 자모로는 ㅣ/ㅏ 1개만 달라,
자모 단위 거리가 한글 오타의 가까움을 더 잘 나타낸다.
"""

from __future__ import annotations

import unicodedata
from typing import Final

# 한글 음절 = U+AC00('가') ~ U+D7A3('힣'). 음절 번호 code = ord(ch) - 0xAC00 이고
# 초성 = code // 588, 중성 = (code % 588) // 28, 종성 = code % 28 (588 = 중성 21 × 종성 28, 종성 0 = 받침 없음).
_BASE: Final = 0xAC00
_LAST: Final = 0xD7A3
_JUNG_COUNT: Final = 21
_JONG_COUNT: Final = 28

# 호환 자모(U+3131 계열). 겹받침(ㄺ, ㄳ …)도 한 글자라서 "닭" → "ㄷㅏㄺ"이 된다.
_CHO: Final = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG: Final = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG: Final = ("", *"ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")

if not (len(_CHO) == 19 and len(_JUNG) == _JUNG_COUNT and len(_JONG) == _JONG_COUNT):  # 표가 틀리면 import 때 바로 알린다
    raise AssertionError("자모 표의 길이가 맞지 않다")


def to_jamo(text: str) -> str:
    """한글 음절을 호환 자모로 풀어 쓴다. 한글 음절이 아닌 글자는 그대로 둔다.
    예: "수영장" → "ㅅㅜㅇㅕㅇㅈㅏㅇ", "닭" → "ㄷㅏㄺ"(겹받침은 한 글자), "a1" → "a1"

    입력은 NFC로 정규화해서 처리한다. 키보드·붙여넣기에 따라 같은 글자가 '가'(한 글자)와 'ㄱ+ㅏ'(NFD 낱자)로 들어올 수
    있는데, 정규화하지 않으면 같은 낱말이 서로 다른 자모열이 되어 거리가 엉뚱하게 커진다.
    """
    out: list[str] = []
    for ch in unicodedata.normalize("NFC", text):
        code = ord(ch)
        if _BASE <= code <= _LAST:
            n = code - _BASE
            cho, rest = divmod(n, _JUNG_COUNT * _JONG_COUNT)
            jung, jong = divmod(rest, _JONG_COUNT)
            out.append(_CHO[cho] + _JUNG[jung] + _JONG[jong])
        else:
            out.append(ch)
    return "".join(out)


def edit_distance(a: str, b: str) -> int:
    """레벤슈타인 거리: a를 b로 바꾸는 데 필요한 한 글자 넣기·빼기·바꾸기의 최소 횟수(동적 계획법).

    dp[i][j] = a[:i]를 b[:j]로 바꾸는 최소 횟수. 한 줄(이전 줄)만 있으면 다음 줄을 만들 수 있어 메모리는 O(len(b))이다.
    """
    if a == b:
        return 0
    if len(a) < len(b):  # 짧은 쪽을 열로 둬서 줄 길이를 줄인다(거리는 a, b를 바꿔도 같다)
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))  # 빈 a에서 b[:j]를 만드는 비용 = j
    for i, ca in enumerate(a, start=1):
        cur = [i]  # a[:i]를 빈 문자열로 만드는 비용 = i
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]
