"""오타 보정용 어휘 사전(aliases.json) 만들기 (로컬 전용).

규칙(지시서 3-2): 사전은 **데이터 안의 시설명·강좌명·종목명과 기관 공식 약칭**으로만 만든다.
시험·개발용 질문에서는 단어를 가져오지 않는다(과적합 방지). 그래서 출처 열을 아래 상수로 고정하고,
사전의 모든 단어에 어느 데이터의 어느 열에서 왔는지(src)를 남겨 무결성 테스트가 검사할 수 있게 한다.

실행: `uv run python -m app.chaesan.ingest.aliases` (backend/ 에서, 먼저 `ingest.load` 필요)
출력: app/chaesan/aliases.json (커밋 대상: 공개 데이터의 이름뿐이고 비밀·개인정보가 없다)
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Final

from app.chaesan.ingest.card_meta import META
from app.chaesan.ingest.load import BACKEND_DIR, DB_PATH
from app.chaesan.ingest.specs import SPECS
from app.chaesan.local.db import ro_uri

ALIASES_PATH: Final = BACKEND_DIR / "app" / "chaesan" / "aliases.json"

# (표, 열): 시설명·강좌명·종목명이 들어 있는 열만. 날짜·숫자·링크·긴 문장 열은 넣지 않는다.
VOCAB_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("t_15101610", "course_type"),  # 올림픽수영장 강좌코드명
    ("t_15114776", "course_type"),  # 일산 강좌코드명
    ("t_15110953", "sport"),  # 올림픽스포츠센터 종목
    ("t_15118652", "sport"),  # 분당 종목
    ("t_15144839", "item_name"),  # 종목정보의 종목명
    ("t_15147992", "center"),
    ("t_15147992", "course_name"),
    ("t_15099006", "venue"),  # 공연장소
    ("t_15143220", "place"),  # 잔디시설 장소
    ("t_15098997", "center"),
    ("t_15131671", "lot"),  # 주차 장소
    ("t_15133891", "member_type"),
    ("t_15144222", "dept"),  # 부서명
)

# 기관 공식 약칭. 지시서·기획서가 예로 든 것이고, '올팍'은 데이터 안에도 쓰인다(올팍소식·올팍축구장, 무결성 테스트가 확인).
ABBREVIATIONS: Final[dict[str, str]] = {"올팍": "올림픽공원", "한체산": "한국체육산업개발"}

_HANGUL_RUN: Final = re.compile(r"[가-힣]+")
MIN_WORD, MAX_WORD = 2, 10


def hangul_words(text: str) -> list[str]:
    """문장에서 한글 낱말(공백·기호·숫자·영문으로 끊어진 한글 덩어리)만 뽑는다. 길이는 2~10자."""
    return [w for w in _HANGUL_RUN.findall(unicodedata.normalize("NFC", text)) if MIN_WORD <= len(w) <= MAX_WORD]


def build_vocab(con: sqlite3.Connection) -> list[dict[str, object]]:
    """어휘 목록: 단어, 등장 횟수, 출처(표.열). 빈도 내림차순 → 가나다순으로 고정해 실행할 때마다 같은 파일이 나오게 한다."""
    count: dict[str, int] = defaultdict(int)
    src: dict[str, set[str]] = defaultdict(set)
    for table, col in VOCAB_COLUMNS:
        for (value,) in con.execute(f'SELECT "{col}" FROM {table} WHERE "{col}" IS NOT NULL'):
            for w in hangul_words(value):
                count[w] += 1
                src[w].add(f"{table}.{col}")
    for spec in SPECS:  # 데이터 이름(제목)의 낱말
        for w in hangul_words(spec.title):
            count[w] += 1
            src[w].add(f"title.{spec.id}")
    for card_id, meta in META.items():  # 카드 별칭(이미 데이터 이름·값에서 나온 것만 허용된다)
        for alias in meta.aliases:
            for w in hangul_words(alias):
                count[w] += 1
                src[w].add(f"alias.{card_id}")
    return [{"w": w, "n": count[w], "src": sorted(src[w])} for w in sorted(count, key=lambda x: (-count[x], x))]


KNOWN_MIN_COUNT: Final = 2  # 문서에 이 횟수 이상 나온 낱말만 '정상'으로 보호한다(한 번뿐인 낱말은 데이터 속 오탈자일 수 있다)


def build_known(con: sqlite3.Connection, exclude: set[str], min_count: int = KNOWN_MIN_COUNT) -> list[str]:
    """문서(docs)의 제목·본문에 min_count번 이상 나오는 3글자 이상 한글 낱말. 어휘에 이미 있는 것은 뺀다."""
    count: dict[str, int] = defaultdict(int)
    for title, body in con.execute("SELECT title, body FROM docs"):
        for w in hangul_words(f"{title} {body or ''}"):
            if len(w) >= 3:
                count[w] += 1
    return sorted(w for w, n in count.items() if n >= min_count and w not in exclude)


def build_aliases(db_path: Path = DB_PATH) -> dict[str, object]:
    con = sqlite3.connect(ro_uri(db_path), uri=True)
    try:
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='docs'").fetchone() is None:
            raise RuntimeError("문서 색인(docs)이 없다: 먼저 `python -m app.chaesan.ingest.docs`를 실행한다")
        vocab = build_vocab(con)
        known = build_known(con, {str(v["w"]) for v in vocab} | set(ABBREVIATIONS))
    finally:
        con.close()
    return {"version": 1, "abbreviations": dict(ABBREVIATIONS), "vocab": vocab, "known": known}


def write_aliases(data: dict[str, object], path: Path = ALIASES_PATH) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="채산 오타 보정용 어휘 사전을 만든다.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--out", type=Path, default=ALIASES_PATH)
    args = parser.parse_args()
    data = build_aliases(args.db)
    write_aliases(data, args.out)
    print(f"어휘 {len(data['vocab'])}개, 보호 낱말 {len(data['known'])}개, 약칭 {len(ABBREVIATIONS)}개 → {args.out}")  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
