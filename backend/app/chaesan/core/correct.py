"""오타·줄임말 보정 (로컬·서비스 공통, 표준 라이브러리만).

순서(지시서 3-2): ① 약칭 사전(올팍 → 올림픽공원) → ② 어휘 사전과 **자모 편집거리** 비교 → ③ 확신도에 따라
고치기 / 되묻기 / 그대로 두기. LLM에게 맡기지 않는 이유: LLM은 고유명사를 말없이 다른 이름으로 바꿀 수 있지만,
코드로 고치면 무엇을 어떻게 고쳤는지 기록이 남는다(corrections).

**숫자·날짜·연도는 절대 고치지 않는다.** 숫자 옆의 한글 덩어리(10만명, 2024년 7월)는 통째로 건너뛴다.

to_jamo·edit_distance(typo.py)는 인자로 주입받는다. 그래서 이 파일의 판단 규칙(조사 처리, 임계값, 되묻기)을
실제 계산 없이도 시험할 수 있고, 기본값은 typo.py의 실제 함수로 연결된다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

from app.chaesan.core.typo import edit_distance, to_jamo

type JamoFn = Callable[[str], str]
type DistanceFn = Callable[[str, str], int]

# ---- 확신도 기준값. 값을 정한 근거와 측정 결과는 eval/calibrate_typo.py와 CLAUDE.md '설계 결정'에 있다 ----
HIGH_MAX_DISTANCE: Final = 1  # 자모 1개 차이이고 후보가 하나뿐이면 고친다(+ 고쳤다고 답에 표시)
ASK_MAX_DISTANCE: Final = 2  # 자모 2개 이내이거나 후보가 여럿이면 고치지 않고 되묻는다
MIN_STEM: Final = 3  # 이보다 짧은 낱말은 오타로 보지 않는다(2글자는 다른 낱말과 너무 가깝다)
LENGTH_SLACK: Final = 1  # 글자 수가 이만큼 넘게 다른 어휘는 후보로 보지 않는다
MAX_SUGGESTIONS: Final = 3

# 낱말 끝에 붙는 조사·어미. 긴 것부터 떼어 본다("올팍에서" → 올팍 + 에서).
_JOSA_TEXT: Final = (
    "에서는 에서 에게 으로 까지 부터 처럼 보다 이나 이랑 하고 이고 이며 인데 이라 에는 에도 "
    "은 는 이 가 을 를 의 에 도 만 로 와 과 나 랑 요 인 이다"
)
_JOSA: Final = tuple(sorted(_JOSA_TEXT.split(), key=len, reverse=True))
# '주차 + 한', '수영 + 했어'처럼 사전 낱말에 하다 동사 어미가 붙은 꼴은 오타가 아니다(자모 거리가 가까워도 고치거나 되묻지 않는다)
_HADA: Final = tuple(
    sorted(
        {
            "합니다",
            "했는데",
            "하려고",
            "했던",
            "했다",
            "했어",
            "했어요",
            "하는",
            "하고",
            "하면",
            "한다",
            "해서",
            "하려",
            "하기",
            "하나",
            "한",
            "했",
            "할",
            "해",
            "하",
        },
        key=len,
        reverse=True,
    )
)
_HANGUL_RUN: Final = re.compile(r"[가-힣]+")


@dataclass(frozen=True, slots=True)
class Vocab:
    words: Mapping[str, int]  # 어휘 → 등장 횟수(후보가 같은 거리일 때 흔한 쪽을 앞세운다)
    abbreviations: Mapping[str, str]  # 약칭 → 정식 이름
    # 데이터 문서에 여러 번 나오는 정상 낱말(인라인, 특별한 …). 오타 후보로 보지 않고 보호한다.
    known: frozenset[str] = frozenset()


def load_vocab(path: Path) -> Vocab:
    """aliases.json을 읽는다. 형식이 다르면 KeyError/ValueError로 멈춘다(조용히 빈 사전으로 동작하지 않는다)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["version"] != 1:
        raise ValueError(f"지원하지 않는 사전 버전: {data['version']}")
    return Vocab(
        {item["w"]: int(item["n"]) for item in data["vocab"]}, dict(data["abbreviations"]), frozenset(data.get("known", []))
    )


@dataclass(frozen=True, slots=True)
class Correction:
    original: str
    corrected: str
    kind: Literal["abbreviation", "typo"]

    def describe(self) -> str:
        """답변에 밝힐 문장. 고친 단어를 반드시 보여 준다."""
        return f"'{self.original}'을(를) '{self.corrected}'(으)로 읽었어요"


@dataclass(frozen=True, slots=True)
class Suggestion:
    original: str
    candidates: tuple[str, ...]

    def describe(self) -> str:
        return f"혹시 {' / '.join(self.candidates)} 말씀이세요?"


@dataclass(slots=True)
class CorrectionResult:
    text: str  # 고친 질문(되묻는 낱말은 원문 그대로)
    corrections: list[Correction] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)

    @property
    def needs_confirmation(self) -> bool:
        return bool(self.suggestions)


class Corrector:
    """어휘 사전과 두 계산 함수를 묶는다. 어휘의 자모는 한 번만 계산해 둔다."""

    def __init__(self, vocab: Vocab, *, jamo: JamoFn = to_jamo, distance: DistanceFn = edit_distance) -> None:
        self._vocab = vocab
        self._distance = distance
        self._jamo = jamo
        # 오타 후보가 될 수 있는 어휘: MIN_STEM 글자 이상
        self._targets: dict[str, str] = {w: jamo(w) for w in vocab.words if len(w) >= MIN_STEM}

    def _splits(self, token: str) -> list[tuple[str, str]]:
        """(어간, 조사) 후보. 조사 없음이 먼저, 그다음 긴 조사부터."""
        out = [(token, "")]
        out += [(token[: -len(j)], j) for j in _JOSA if token.endswith(j) and len(token) - len(j) >= 2]
        return out

    def _decide(self, token: str) -> tuple[str, Correction | Suggestion | None]:
        """낱말 하나의 판단. 반환: (바꿀 낱말, 보정 기록 또는 되묻기 또는 None)."""
        splits = self._splits(token)
        for suffix in _HADA:
            base = token[: -len(suffix)]
            if token.endswith(suffix) and len(base) >= 2 and (base in self._vocab.words or base in self._vocab.known):
                return token, None
        for stem, josa in splits:  # ① 사전에 이미 있는 말이거나 약칭이면 오타 계산을 하지 않는다
            if stem in self._vocab.abbreviations:
                full = self._vocab.abbreviations[stem]
                return full + josa, Correction(stem, full, "abbreviation")
            if stem in self._vocab.words or stem in self._vocab.known:
                return token, None
        scored: dict[str, tuple[int, str]] = {}  # 후보 어휘 → (최소 거리, 그때의 어간)
        for stem, _ in splits:
            if len(stem) < MIN_STEM:
                continue
            sj = self._jamo(stem)
            for word, wj in self._targets.items():
                if abs(len(word) - len(stem)) > LENGTH_SLACK:
                    continue
                d = self._distance(sj, wj)
                if d <= ASK_MAX_DISTANCE and (word not in scored or d < scored[word][0]):
                    scored[word] = (d, stem)
        if not scored:
            return token, None
        top = min(d for d, _ in scored.values())
        ranked = sorted((w for w, (d, _) in scored.items() if d == top), key=lambda w: (-self._vocab.words[w], w))
        stem = scored[ranked[0]][1]  # 고르는 어휘와 같은 어간을 쓴다(어간이 다르면 조사가 엉뚱하게 붙거나 사라진다)
        if top <= HIGH_MAX_DISTANCE and len(ranked) == 1:  # ③ 확신이 높다: 고친다
            return ranked[0] + token[len(stem) :], Correction(stem, ranked[0], "typo")
        return token, Suggestion(stem, tuple(ranked[:MAX_SUGGESTIONS]))  # 중간: 고치지 않고 되묻는다

    def correct(self, text: str) -> CorrectionResult:
        result = CorrectionResult(text)
        pieces: list[str] = []
        cursor = 0
        for m in _HANGUL_RUN.finditer(text):
            start, end = m.span()
            before, after = text[start - 1 : start], text[end : end + 1]
            if before.isdigit() or after.isdigit():  # 숫자·날짜·연도 옆의 낱말(10만명, 2024년)은 건드리지 않는다
                continue
            replacement, note = self._decide(m.group())
            if isinstance(note, Correction):
                result.corrections.append(note)
                pieces += [text[cursor:start], replacement]
                cursor = end
            elif isinstance(note, Suggestion):
                result.suggestions.append(note)
        pieces.append(text[cursor:])
        result.text = "".join(pieces)
        return result
