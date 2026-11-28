"""개발용 질문 검사: 질문을 엔진에 넣어 자료 선택·숫자·모른다·오타 보정·시간·토큰을 잰다(F단계).

실행: `uv run python -m eval.run_eval [--file eval/dev_questions.jsonl] [--limit N]` (backend/ 에서, Ollama 필요)
출력: 표 + data/eval_<이름>_results.json(질문별 카드와 채점, data/는 git 제외)

이 도구는 점수를 보고 코드를 질문에 맞춰 고치는 데 쓰지 않는다(규칙 11·12). 틀린 질문은 원인만 분류해 보고한다.
시험용 60문항은 사용자가 '시험'이라고 한 뒤 한 번만 같은 도구로 돌린다.

채점
- 자료 선택: 정답이 있는 질문은 expected_tables가 답변의 sources에 모두 있어야 한다. 근거 없는 질문은 status가 expect_status 안이어야 한다.
- 숫자·사실 일치: expect_contains의 각 항목(대안 목록)이 답·근거·문서 제목 어딘가에 하나는 있어야 한다.
- 문서 찾기: expect_docs 낱말이 evidence 문서 제목 어딘가에 있어야 한다.
- 모른다: 근거 없는 질문에 answered로 답하면 '지어낸 답'이다.
- 오타 보정: typos의 (입력, 고칠 말) 쌍이 corrections에 있어야 한다. 기대하지 않은 보정은 '잘못 고친 수'.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from pathlib import Path
from typing import Any

from app.chaesan.core.engine import AnswerCard
from app.chaesan.ingest.load import BACKEND_DIR

DEFAULT = BACKEND_DIR / "eval" / "dev_questions.jsonl"


def load_questions(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _norm(text: str) -> str:
    return text.replace(",", "").replace(" ", "")


def haystack(card: dict[str, Any]) -> str:
    """사실 일치를 찾는 곳: 답 + 근거 표 + 문서 제목·날짜. 쉼표와 공백은 무시하고 비교한다."""
    docs = " ".join(f"{d.get('title', '')} {d.get('date', '')}" for d in card["documents"])
    return _norm(" ".join([card["answer"], json.dumps(card["evidence_rows"], ensure_ascii=False), docs]))


def grade(q: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    """질문 하나를 채점한다. 반환: 항목별 결과(True/False/None=해당 없음)와 실패 원인 분류."""
    status = card["status"]
    expects_answer = "answered" in q["expect_status"]
    source_ids = {s["id"] for s in card["sources"]} | {d.get("source") for d in card["documents"]}
    hay = haystack(card)
    r: dict[str, Any] = {"id": q["id"], "status": status}
    if expects_answer:
        r["selection"] = status == "answered" and all(t in source_ids for t in q["expected_tables"])
        r["facts"] = (
            all(any(_norm(a) in hay for a in group) for group in q["expect_contains"]) if q["expect_contains"] else None
        )
        titles = _norm(" ".join(d.get("title", "") for d in card["documents"]))
        r["docs"] = all(_norm(w) in titles for w in q["expect_docs"]) if q["expect_docs"] else None
        r["unknown_ok"] = None
    else:
        r["selection"] = status in q["expect_status"]
        r["facts"] = r["docs"] = None
        r["unknown_ok"] = status in ("unknown", "planned")
    fixes = list(card["corrections"])
    want = [f"'{a}'을(를) '{b}'(으)로 읽었어요" for a, b in q["typos"]]
    allowed = [f"'{a}'을(를) '{b}'(으)로 읽었어요" for a, b in q.get("allowed_fixes", [])]
    r["typo_ok"] = all(w in fixes for w in want) if q["typos"] else None
    r["wrong_fixes"] = [c for c in fixes if c not in want and c not in allowed]
    r["passed"] = all(v is not False for v in (r["selection"], r["facts"], r["docs"], r["unknown_ok"], r["typo_ok"]))
    r["cause"] = None if r["passed"] else classify(q, card, r)
    return r


def classify(q: dict[str, Any], card: dict[str, Any], r: dict[str, Any]) -> str:
    """실패 원인(지시서 F단계): 자료 선택 / SQL / 검색 / 설명 / 대조 / 오류·차단 / 오타 보정."""
    if card["status"] in ("error", "blocked"):
        return "오류·차단"
    if r["typo_ok"] is False:
        return "오타 보정"
    if "answered" not in q["expect_status"]:
        return "지어낸 답(근거 없는 질문에 답함)"
    if card["status"] != "answered":
        return "자료 선택(모른다·되묻기로 끝남)"
    if r["selection"] is False:
        return "자료 선택(다른 데이터를 고름)"
    if card["unsupported_numbers"]:
        return "대조(숫자가 근거에 없음)"
    if r["docs"] is False:
        return "검색(알맞은 문서를 못 찾음)"
    if r["facts"] is False:
        evidence = _norm(json.dumps(card["evidence_rows"], ensure_ascii=False) + " ".join(str(d) for d in card["documents"]))
        has = all(any(_norm(a) in evidence for a in g) for g in q["expect_contains"])
        return "설명(근거엔 있는데 답에 빠짐/틀림)" if has else ("SQL(근거 표에 정답이 없음)" if card["evidence_rows"] else "검색(근거에 정답이 없음)")
    return "기타"


def rate(vals: list[bool | None]) -> str:
    v = [x for x in vals if x is not None]
    return f"{sum(v)}/{len(v)} ({sum(v) / len(v):.0%})" if v else "해당 없음"


def summarize(questions: list[dict[str, Any]], cards: list[dict[str, Any]], graded: list[dict[str, Any]]) -> str:
    out: list[str] = []
    ans = [g for q, g in zip(questions, graded, strict=True) if "answered" in q["expect_status"]]
    out.append(f"자료 선택(전체)        : {rate([g['selection'] for g in graded])}   ← 지시서 기준 80% 이상이면 계속")
    out.append(f"자료 선택(정답 있는 질문): {rate([g['selection'] for g in ans])}")
    out.append(f"숫자·사실 일치          : {rate([g['facts'] for g in graded])}")
    out.append(f"알맞은 문서 찾기        : {rate([g['docs'] for g in graded])}")
    out.append(f"'모른다' 정답           : {rate([g['unknown_ok'] for g in graded])}")
    out.append(f"오타 보정 정답          : {rate([g['typo_ok'] for g in graded])}")
    wrong = sum(len(g["wrong_fixes"]) for g in graded)
    out.append(f"잘못 고친 수            : {wrong}건")
    t = [c["meta"]["elapsed_ms"] / 1000 for c in cards]
    out.append(f"질문당 시간(초)         : 평균 {statistics.mean(t):.1f} / 중앙값 {statistics.median(t):.1f} / 최대 {max(t):.1f}")
    out.append(
        f"질문당 토큰             : 입력 평균 {statistics.mean(c['meta']['input_tokens'] for c in cards):.0f}, "
        f"출력 평균 {statistics.mean(c['meta']['output_tokens'] for c in cards):.0f}, "
        f"LLM 호출 평균 {statistics.mean(c['meta']['llm_calls'] for c in cards):.1f}회"
    )
    out.append(f"전체 통과               : {sum(g['passed'] for g in graded)}/{len(graded)}")
    return "\n".join(out)


async def main_async(path: Path, limit: int | None, tag: str = "") -> None:
    from app.chaesan.local.app import build_engine  # Ollama·DB가 필요해서 여기서 불러온다

    questions = load_questions(path)[:limit]
    engine = build_engine()
    cards: list[dict[str, Any]] = []
    graded: list[dict[str, Any]] = []
    for q in questions:
        card = (await engine.ask(q["question"])).to_dict()
        g = grade(q, card)
        cards.append(card)
        graded.append(g)
        mark = "OK  " if g["passed"] else "FAIL"
        print(f"{mark} {q['id']} [{q['type']}] {card['status']:<8} {card['meta']['elapsed_ms'] / 1000:4.1f}s  {q['question']}")
        if not g["passed"]:
            print(f"       원인: {g['cause']} | 기대: {str(q['expected_answer'])[:70]}")
            print(f"       답  : {card['answer'][:110]}")
    print("\n" + summarize(questions, cards, graded))
    out = BACKEND_DIR / "data" / f"eval_{path.stem}{tag}_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"questions": questions, "cards": cards, "graded": graded}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n질문별 결과: {out}")


def regrade(results: Path, questions_file: Path) -> None:
    """저장된 결과를 (고친 채점 기준으로) 다시 채점한다. 모델은 다시 부르지 않는다."""
    saved = json.loads(results.read_text(encoding="utf-8"))
    questions = load_questions(questions_file)[: len(saved["cards"])]
    graded = [grade(q, c) for q, c in zip(questions, saved["cards"], strict=True)]
    for q, g in zip(questions, graded, strict=True):
        print(("OK  " if g["passed"] else "FAIL"), q["id"], g["cause"] or "")
    print("\n" + summarize(questions, saved["cards"], graded))


def main() -> None:
    parser = argparse.ArgumentParser(description="채산 개발용 질문 검사")
    parser.add_argument("--file", type=Path, default=DEFAULT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--tag", default="", help="결과 파일 이름 뒤에 붙일 표시(같은 질문을 여러 번 돌릴 때)")
    parser.add_argument("--regrade", type=Path, default=None, help="저장된 결과 파일을 모델 호출 없이 다시 채점")
    args = parser.parse_args()
    if args.regrade:
        regrade(args.regrade, args.file)
        return
    asyncio.run(main_async(args.file, args.limit, args.tag))


if __name__ == "__main__":
    main()
