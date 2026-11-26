"""챗봇 실전 평가(수동): 실제 데이터 + 실제 로컬 LLM.   cd backend && uv run python -m tests.live_eval_chatbot

측정:
  - grounded : 모든 추천이 DB에 있는 축제이며, 이유 문장이 검증을 통과했거나 템플릿으로 대체됨(= 틀린 사실이 나가지 않음)
  - 거짓 탐지 : 최종 출력에서 원문에 없는 숫자/금지어(가격·주차 등)가 발견되면 '위반'
  - AI 채택률 : AI 문장이 검증을 통과해 그대로 쓰인 비율 (낮으면 챗봇이 템플릿 위주가 된다는 뜻)
"""

from __future__ import annotations

import re
import sys
import time
from datetime import date

import httpx

from app.chatbot import _RISKY, _source_numbers, respond
from app.database import get_festivals_collection
from app.search import all_records

QUESTIONS = [
    "단풍 보고 싶어",
    "벚꽃 보러 가고 싶어",
    "이번 주말에 갈만한 축제",
    "얼음 낚시 하고 싶어",
    "겨울에 아이랑 가기 좋은 축제",
    "야경이 예쁜 축제 추천해줘",
    "먹거리 많은 축제",
    "제주도에서 열리는 축제",
    "12월에 갈만한 축제",
    "데이트하기 좋은 축제",
    "해맞이 보러 가고 싶어",
    "음악 공연 있는 축제",
    "아무거나 추천해줘",
    "전통 문화 체험하고 싶어",
    "강원도 겨울 축제",
    "입장료 얼마야? 주차는 돼?",  # 데이터에 없는 정보
    "단풍 축제 입장료 무료야?",  # 섞인 질문
    "우주 로켓 축제 알려줘",  # 존재하지 않는 주제
    "벚꽃이 지금 피어 있는 곳 알려줘",  # 시기가 틀린 질문
    "내년 가을 단풍 축제 날짜 알려줘",  # 미래 일정 단정 유도
]


def main() -> int:
    try:
        httpx.get("http://localhost:11434/api/tags", timeout=3).raise_for_status()
    except httpx.HTTPError:
        print("Ollama가 꺼져 있어 건너뜁니다.")
        return 0
    records = all_records(get_festivals_collection())
    by_id = {r.id: r for r in records}
    today = date.today()

    total = ai_used = ai_rejected = violations = 0
    for q in QUESTIONS:
        t = time.time()
        r = respond(q, previous_user_messages=[], records=records, today=today)
        dt = time.time() - t
        print(f"\n### {q}  ({dt:.1f}s)\n  → {r.answer}")
        for p in r.picks:
            rec = p.candidate.record
            total += 1
            ai_used += p.ai_written
            ai_rejected += 0 if p.ai_written else 1
            bad = []
            if rec.id not in by_id:
                bad.append("DB에 없는 축제")
            nums = {int(n) for n in re.findall(r"\d+", p.reason)}
            if nums - _source_numbers(rec):
                bad.append(f"원문에 없는 숫자 {nums - _source_numbers(rec)}")
            bad += [f"원문에 없는 '{w}'" for w in _RISKY if w in p.reason and w not in " ".join((rec.fstvl_nm, rec.fstvl_co, rec.opar, rec.rdnmadr))]
            violations += bool(bad)
            tag = "AI " if p.ai_written else "템플릿"
            print(f"  [{p.candidate.kind}/{p.candidate.status}] {rec.fstvl_nm} ({rec.fstvl_start_date}~{rec.fstvl_end_date}) {tag}: {p.reason}" + (f"  ⚠ {bad}" if bad else ""))
        for n in r.notes:
            print("  NOTE:", n)

    print(f"\n==== 추천 {total}건 | AI 문장 채택 {ai_used} / 템플릿 대체 {ai_rejected} | 사실 위반 {violations}건 ====")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
