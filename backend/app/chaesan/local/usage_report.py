"""사용 기록 요약 도구: 로그 파일(usage.jsonl*)을 하루 단위로 센다. 원문이 없는 기록만 읽어서 보고서에 써도 안전하다.

실행: `uv run python -m app.chaesan.local.usage_report [--days 7] [--save]`  (backend/ 에서)
- 기본: 표로 출력. 어느 하루에 몇 건, 결과별 건수, 갈래별 건수, 사용자 수(가명), 평균·95% 지연, LLM 호출·토큰 합계.
- --save: 같은 요약을 `data/usage.sqlite`(공개 데이터 DB와 **별도 파일**)의 usage_daily 표에 날짜별로 덮어 쓴다.
  로그는 30일 뒤 지워지지만 이 집계는 원문·개인 식별 값이 없어서 오래 두고 결과 보고에 쓸 수 있다.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final

from app.chaesan.ingest.load import BACKEND_DIR
from app.chaesan.local.usage_log import USAGE_LOG_DIR, USAGE_LOG_NAME

USAGE_DB: Final = BACKEND_DIR / "data" / "usage.sqlite"
ASK_PATH: Final = "/api/chaesan/ask"


def read_events(directory: Path = USAGE_LOG_DIR) -> list[dict[str, Any]]:
    """usage.jsonl과 자정마다 넘긴 usage.jsonl.날짜 파일을 모두 읽는다. 깨진 줄은 건너뛴다(한 줄 때문에 멈추지 않게)."""
    events: list[dict[str, Any]] = []
    for path in sorted(directory.glob(f"{USAGE_LOG_NAME}*")):
        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict) and isinstance(item.get("ts"), str):
                    events.append(item)
    return events


def percentile(values: list[int], pct: float) -> int:
    """값 목록의 pct 백분위(가장 가까운 순위 방식). 빈 목록은 0."""
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, -(-int(pct * len(ordered)) // 100) - 1))
    return ordered[index]


def summarize(events: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """날짜(YYYY-MM-DD, KST)별 요약. 질문 처리(ask) 요청만 질문 수로 세고, 다른 /api/ 요청과 오류 코드는 따로 센다."""
    days: dict[str, dict[str, Any]] = {}
    for ev in events:
        day = str(ev["ts"])[:10]
        d = days.setdefault(
            day,
            {"requests": 0, "asks": 0, "users": set(), "results": Counter(), "intents": Counter(), "codes": Counter(),
             "latency": [], "llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "rows_read": 0, "repeat": Counter()},
        )  # fmt: skip
        d["requests"] += 1
        d["codes"][str(ev.get("status_code"))] += 1
        if isinstance(ev.get("ip"), str):
            d["users"].add(ev["ip"])
        if ev.get("path") != ASK_PATH or ev.get("method") != "POST":
            continue
        d["asks"] += 1
        if isinstance(ev.get("elapsed_ms"), int):
            d["latency"].append(ev["elapsed_ms"])
        if "result" in ev:  # 질문이 처리까지 간 요청(요청 제한·검증 실패는 result가 없다)
            d["results"][str(ev["result"])] += 1
            d["intents"][str(ev.get("intent"))] += 1
            for key in ("llm_calls", "input_tokens", "output_tokens", "rows_read"):
                if isinstance(ev.get(key), int):
                    d[key] += ev[key]
            if isinstance(ev.get("q_hash"), str):
                d["repeat"][ev["q_hash"]] += 1
    out: dict[str, dict[str, Any]] = {}
    for day, d in sorted(days.items()):
        handled = sum(d["results"].values())
        out[day] = {
            "requests": d["requests"],
            "asks": d["asks"],
            "handled": handled,
            "users": len(d["users"]),
            "results": dict(d["results"]),
            "intents": dict(d["intents"]),
            "status_codes": dict(d["codes"]),
            "p50_ms": percentile(d["latency"], 50),
            "p95_ms": percentile(d["latency"], 95),
            "llm_calls": d["llm_calls"],
            "input_tokens": d["input_tokens"],
            "output_tokens": d["output_tokens"],
            "rows_read": d["rows_read"],
            "repeated_questions": sum(1 for n in d["repeat"].values() if n > 1),
        }
    return out


def format_report(summary: dict[str, dict[str, Any]]) -> str:
    if not summary:
        return "기록이 없습니다."
    lines = ["날짜        질문  처리  사용자  p50ms  p95ms  LLM호출  입력토큰  출력토큰  결과"]
    for day, s in summary.items():
        results = ", ".join(f"{k} {v}" for k, v in sorted(s["results"].items())) or "-"
        lines.append(
            f"{day}  {s['asks']:>4}  {s['handled']:>4}  {s['users']:>6}  {s['p50_ms']:>5}  {s['p95_ms']:>5}  "
            f"{s['llm_calls']:>7}  {s['input_tokens']:>8}  {s['output_tokens']:>8}  {results}"
        )
    return "\n".join(lines)


def save_daily(summary: dict[str, dict[str, Any]], path: Path = USAGE_DB) -> int:
    """날짜별 요약을 별도 DB(usage_daily)에 덮어 쓴다. 이미 있는 날짜는 최신 값으로 바뀐다. 쓴 날짜 수를 돌려준다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE IF NOT EXISTS usage_daily (day TEXT PRIMARY KEY, summary TEXT NOT NULL)")
        con.executemany(
            "INSERT OR REPLACE INTO usage_daily(day, summary) VALUES (?, ?)",
            [(day, json.dumps(s, ensure_ascii=False, sort_keys=True)) for day, s in summary.items()],
        )
    return len(summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="최근 며칠만 보기(기본 7)")
    parser.add_argument("--save", action="store_true", help="요약을 data/usage.sqlite(usage_daily)에 저장")
    args = parser.parse_args()
    summary = summarize(read_events())
    recent = dict(list(summary.items())[-max(1, args.days) :])
    print(format_report(recent))
    if args.save:
        print(f"저장: {save_daily(summary)}일치 → {USAGE_DB.relative_to(BACKEND_DIR)}")


if __name__ == "__main__":
    main()
