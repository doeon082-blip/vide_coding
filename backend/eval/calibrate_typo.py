"""오타 보정 확신도 기준값 측정 (재현용).

실행: `uv run python -m eval.calibrate_typo` (backend/ 에서). typo.to_jamo / typo.edit_distance를 쓴다.

무엇을 재나
1. 합성 오타: 어휘 단어의 음절 하나의 초성·중성·종성을 바꿔(자모 1개 / 2개 차이) 만든 오타를 얼마나 맞게 고치는지.
2. 처음 보는 정상 낱말: 문서의 절반으로 '보호 목록'을 만들고 나머지 절반에서만 나온 낱말을 잘못 고치는 비율.
시험 질문은 쓰지 않는다(질문 단어가 사전·기준값에 스며드는 것을 막기 위해). 정상 낱말은 데이터 문서의 낱말이다.
"""

from __future__ import annotations

import argparse
import random
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from app.chaesan.core import correct
from app.chaesan.ingest.aliases import ALIASES_PATH, hangul_words
from app.chaesan.ingest.load import DB_PATH

_CHO, _JUNG, _JONG = 19, 21, 28


def _parts(ch: str) -> tuple[int, int, int]:
    c = ord(ch) - 0xAC00
    return c // 588, (c % 588) // 28, c % 28


def _compose(cho: int, jung: int, jong: int) -> str:
    return chr(0xAC00 + (cho * _JUNG + jung) * _JONG + jong)


def one_edit(word: str, rng: random.Random) -> str:
    """음절 하나의 초성·중성·종성 중 하나만 다른 값으로 바꾼다(자모 1개 차이)."""
    i = rng.randrange(len(word))
    cho, jung, jong = _parts(word[i])
    kind = rng.choice(("cho", "jung", "jong"))
    if kind == "cho":
        cho = rng.choice([x for x in range(_CHO) if x != cho])
    elif kind == "jung":
        jung = rng.choice([x for x in range(_JUNG) if x != jung])
    else:
        jong = rng.choice([x for x in range(_JONG) if x != jong])
    return word[:i] + _compose(cho, jung, jong) + word[i + 1 :]


def make_typos(word: str, rng: random.Random, edits: int, n: int) -> list[str]:
    out: set[str] = set()
    for _ in range(n * 6):
        w = word
        for _ in range(edits):
            w = one_edit(w, rng)
        if w != word:
            out.add(w)
        if len(out) >= n:
            break
    return sorted(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="오타 보정 확신도 기준값을 잰다.")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--aliases", type=Path, default=ALIASES_PATH)
    args = parser.parse_args()
    vocab = correct.load_vocab(args.aliases)
    rng = random.Random(args.seed)
    targets = [w for w in vocab.words if len(w) >= correct.MIN_STEM]
    typos = {e: [(t, w) for w in targets for t in make_typos(w, rng, e, 3)] for e in (1, 2)}

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    half: tuple[dict[str, int], dict[str, int]] = (defaultdict(int), defaultdict(int))
    for doc_id, title, body in con.execute("SELECT doc_id, title, body FROM docs"):
        for w in hangul_words(f"{title} {body or ''}"):
            if len(w) >= correct.MIN_STEM:
                half[doc_id % 2][w] += 1
    known = frozenset(w for w, n in half[1].items() if n >= 2 and w not in vocab.words)
    unseen = sorted(w for w in half[0] if w not in known and w not in vocab.words and w not in vocab.abbreviations)

    print(f"기준값: 고침 거리≤{correct.HIGH_MAX_DISTANCE}, 되묻기 거리≤{correct.ASK_MAX_DISTANCE}, 최소 길이 {correct.MIN_STEM}")
    cor = correct.Corrector(correct.Vocab(vocab.words, vocab.abbreviations, vocab.known))
    for e, pairs in typos.items():
        c: Counter[str] = Counter()
        for typo, word in pairs:
            r = cor.correct(typo)
            if r.corrections:
                c["고침-맞음" if r.text == word else "고침-틀림"] += 1
            elif r.suggestions:
                c["되묻기(후보에 있음)" if word in r.suggestions[0].candidates else "되묻기(후보에 없음)"] += 1
            else:
                c["그대로"] += 1
        print(f"자모 {e}개 오타 {len(pairs)}개:", {k: f"{v}({v / len(pairs):.1%})" for k, v in c.most_common()})
    cor2 = correct.Corrector(correct.Vocab(vocab.words, vocab.abbreviations, known))
    fixed = sum(1 for w in unseen if cor2.correct(w).corrections)
    asked = sum(1 for w in unseen if cor2.correct(w).suggestions)
    n = len(unseen)
    print(f"처음 보는 정상 낱말 {n}개: 잘못 고침 {fixed}({fixed / n:.2%}), 잘못 되묻기 {asked}({asked / n:.2%})")
    if re.search(r"\d", "".join(unseen)):
        raise SystemExit("낱말에 숫자가 섞여 있다(한글 낱말만 써야 한다)")


if __name__ == "__main__":
    main()
