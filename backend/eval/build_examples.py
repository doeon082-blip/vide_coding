"""화면의 예시 답을 만든다(H4): 예시 질문을 실제 엔진에 돌려 응답을 그대로 `web/data/examples.json`에 저장한다.

실행: `uv run python -m eval.build_examples [--refresh]` (backend/ 에서, Ollama 필요). 저장된 답이 있으면 새 질문만 만든다.
원칙
- 답을 손으로 쓰지 않는다. 엔진이 낸 응답을 그대로 저장한다(규칙 12).
- 예시 질문(`eval/example_questions.json`)은 개발용 질문과 겹치지 않게 정하고, 시험용 60문항은 열지 않는다(규칙 11).
- 정상 답(status=answered, 숫자 미확인 없음)과, '모른다'를 보여 주는 예시(expect=unknown)만 저장한다. 그렇지 않은 질문은 이유를 출력하고 빼 둔다 → 사람이 질문을 바꾼다.
- 응답에서 meta는 질문 갈래(intent)만 남긴다(토큰 수·걸린 시간은 화면에 필요 없다).
화면은 이 파일의 답을 "미리 계산한 답 · 날짜 기준"으로 표시한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.chaesan.core.config import KST
from app.chaesan.core.engine import Engine
from app.chaesan.ingest.load import BACKEND_DIR
from app.chaesan.local.app import build_engine

QUESTIONS = BACKEND_DIR / "eval" / "example_questions.json"
OUT = BACKEND_DIR / "app" / "chaesan" / "web" / "data" / "examples.json"


def usable(card: dict[str, Any], expect: str = "answered") -> str | None:
    """예시로 저장해도 되는 답인가. 안 되면 이유를, 되면 None.
    expect="unknown"은 '근거가 없으면 모른다고 한다'를 보여 주는 예시: 답을 지어내지 않고 unknown이어야 하고, 근거 표·출처는 없어야 한다."""
    if card["status"] != expect:
        return f"status={card['status']} (기대 {expect})"
    if expect == "unknown":
        return None if not (card["evidence_rows"] or card["documents"]) else "모른다 예시인데 근거가 있음"
    if card["unsupported_numbers"]:
        return "숫자 미확인"
    if not (card["sources"] or card["documents"]):
        return "출처 없음"
    return None


def slim(card: dict[str, Any]) -> dict[str, Any]:
    """화면이 쓰는 값만 남긴다(JSON으로 왕복 가능한 모양). meta는 질문 갈래만."""
    keep = {k: card[k] for k in ("status", "answer", "evidence_kind", "evidence_rows", "documents", "sources", "badges", "corrections", "unsupported_numbers", "notice")}
    keep["meta"] = {"intent": card["meta"].get("intent")}
    return json.loads(json.dumps(keep, ensure_ascii=False, default=str))


ATTEMPTS = 3  # 같은 질문도 실행마다 답이 조금 달라질 수 있어(프롬프트의 1회용 난수), 정상 답이 나온 첫 결과를 저장한다. 최대 시도 횟수.


async def build(
    engine: Engine, questions: list[dict[str, str]], keep: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """질문 목록 순서대로 예시를 만든다. keep(이미 저장된 예시)에 있는 질문은 다시 돌리지 않는다(저장된 답을 안정적으로 유지)."""
    kept: list[dict[str, Any]] = []
    skipped: list[str] = []
    for item in questions:
        if item["question"] in keep:
            kept.append(keep[item["question"]])
            continue
        reason = "시도 안 함"
        for _ in range(ATTEMPTS):
            card = (await engine.ask(item["question"])).to_dict()
            reason = usable(card, item.get("expect", "answered")) or ""
            if not reason:
                kept.append({"lane": item["lane"], "question": item["question"], "response": slim(card)})
                break
        else:
            skipped.append(f"{item['question']} → {reason}")
    return kept, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="저장된 답을 버리고 모두 다시 만든다")
    args = parser.parse_args()
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    saved: dict[str, dict[str, Any]] = {}
    if OUT.is_file() and not args.refresh:
        saved = {e["question"]: e for e in json.loads(OUT.read_text(encoding="utf-8"))["examples"]}
    kept, skipped = asyncio.run(build(build_engine(record_demand=False), questions, saved))
    stamp = datetime.now(KST).isoformat(timespec="seconds")
    OUT.write_text(json.dumps({"generated_at": stamp, "examples": kept}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장 {len(kept)}개 → {Path(OUT).relative_to(BACKEND_DIR)} ({stamp})")
    for line in skipped:
        print("빠짐:", line)


if __name__ == "__main__":
    main()
