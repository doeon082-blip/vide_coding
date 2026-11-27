"""D단계 실행기: 저장된 표 → 판정 → data/report/effect.md (+ effect.svg).

사용: `uv run python -m app.impact.run_d` (공휴일 목록 승인 후 holidays.json 이 있어야 한다)
같은 입력이면 같은 결과가 나오며, 판정 기준은 config.py/evaluate.py 에 고정돼 있다.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from app.impact import config
from app.impact.baseline import excess_profile
from app.impact.evaluate import ImpactEvent, Verdict, changed_by_fill, evaluate_events
from app.impact.parse import parse_date, parse_time
from app.impact.series import load_series
from app.impact.store import read_table

logger = logging.getLogger(__name__)

HOLIDAYS_FILE = "holidays.json"
DEFAULT_SOURCES = ("kspo",)  # 올림픽공원 행사의 출처. 서울 문화행사는 공원 밖 행사가 섞여 있어 기본에서 뺀다.


def load_holidays(path: Path) -> set[date]:
    """공휴일 목록(JSON, ["2025-10-03", ...])을 읽는다.

    목록은 확인된 출처를 사용자에게 보여 주고 승인받은 뒤에 만든다. 없거나 비어 있으면
    추석 연휴 등이 기준값에 섞여 결과가 왜곡되므로 계산하지 않고 멈춘다.
    """
    if not path.exists():
        raise FileNotFoundError(f"공휴일 목록이 없습니다: {path} (확인된 목록을 승인받아 만든 뒤 실행하세요)")
    days = {parse_date(s) for s in json.loads(path.read_text(encoding="utf-8"))}
    days.discard(None)
    if not days:
        raise ValueError(f"공휴일 목록이 비어 있습니다: {path}")
    return days  # type: ignore[return-value]


def load_events(processed_dir: Path, sources: Sequence[str] = DEFAULT_SOURCES) -> tuple[list[ImpactEvent], set[date]]:
    """events 표 → (시작 시각이 있는 행사들, 시작 시각 없는 행사까지 포함한 모든 행사일)."""
    events: list[ImpactEvent] = []
    all_dates: set[date] = set()
    for r in read_table("events", processed_dir):
        if r["source"] not in sources or r["date"] is None:
            continue
        all_dates.add(r["date"])
        t = parse_time(r["start_time"])
        if t is not None:
            events.append(ImpactEvent(r["event_id"], r["name"], datetime.combine(r["date"], t)))
    return sorted(events, key=lambda e: e.start), all_dates


def _fmt(x: float | None, nd: int = 0) -> str:
    return "—" if x is None else f"{x:,.{nd}f}"


def render_report(v0: Verdict, v3: Verdict, flipped: list[str], profile: dict[str, dict[int, float]]) -> str:
    """효과 확인 보고서(마크다운). v0/v3: `*`를 0/3으로 채운 판정. profile: 구역·offset별 평균 증가분."""
    L = ["# 효과 확인 (D단계)\n", f"판정 기간 {config.JUDGE_START} ~ {config.JUDGE_END}, 기준은 사전에 고정됨.\n"]
    L.append(f"## 결과: {'통과' if v0.passed else '통과하지 못함'}\n")
    L += [f"- {r}" for r in v0.reasons]
    L.append(f"- 판정 기간 행사 {v0.n_judged_period}건 중 판정 불가 {v0.n_unjudgeable}건 "
             f"({v0.n_unjudgeable / v0.n_judged_period:.0%})" if v0.n_judged_period else "- 판정 기간에 행사 없음")
    L.append(f"- `*`를 0/3으로 채웠을 때 통과 여부가 달라진 행사: {len(flipped)}건"
             + (f" ({', '.join(flipped)})" if flipped else " (판정에 영향 없음)"))
    L.append("- park 또는 ring1 중 하나만 넘어도 통과이므로 우연 통과 확률이 단일 구역(약 5%)보다 커서 약 10%다. "
             "통과 기준 50%는 이보다 훨씬 높다.")
    L.append("- 통과하지 못해도 기준을 낮추지 않는다.\n")
    L.append("## 행사별 (`*`=0 기준)\n")
    L.append("| 날짜 | 행사 | 시작 | 휴일 | park 점수 | park 문턱 | ring1 점수 | ring1 문턱 | ring2 점수 | 통과 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in v0.results:
        s, t = r.scores, r.thresholds
        verdict = "통과" if r.passed else ("미달" if r.judgeable else "판정 불가")
        L.append(f"| {r.event.start.date()} | {r.event.name} | {r.event.start:%H:%M} | {'휴일' if r.on_holiday else ''} | "
                 f"{_fmt(s.get('park'))} | {_fmt(t.get('park'))} | {_fmt(s.get('ring1'))} | {_fmt(t.get('ring1'))} | "
                 f"{_fmt(s.get('ring2'))} | {verdict} |")
    L.append("\n## 구역별 시간대 평균 증가분 (시작 시각 기준 −3h ~ +3h, 판정 가능한 행사 평균)\n")
    L.append("| 구역 | " + " | ".join(f"{k:+d}h" for k in range(-config.SCORE_HOURS_BEFORE, config.SCORE_HOURS_AFTER + 1)) + " |")
    L.append("|---|" + "---|" * (config.SCORE_HOURS_BEFORE + config.SCORE_HOURS_AFTER + 1))
    for z, prof in profile.items():
        L.append(f"| {z} | " + " | ".join(_fmt(prof.get(k), 1) for k in sorted(prof)) + " |")
    L.append("\n그래프: effect.svg\n")
    L.append("## 확인하지 못한 것\n- 같은 날 입차 증가와 방향 일치 여부: 입차 표 구조 확인 전이라 이번 실행에는 포함하지 않았다.\n"
             "- 비 오는 날 표시: 날씨 표 확인 전.\n")
    return "\n".join(L)


def render_svg(profile: dict[str, dict[int, float]]) -> str:
    """구역별 평균 증가분 꺾은선 그래프(외부 라이브러리 없이 SVG 직접 작성)."""
    W, H, M = 560, 320, 50
    colors = {"park": "#d62728", "ring1": "#1f77b4", "ring2": "#7f7f7f"}
    xs = sorted({k for p in profile.values() for k in p})
    vals = [v for p in profile.values() for v in p.values()] or [0.0]
    lo, hi = min(min(vals), 0.0), max(max(vals), 0.0)
    span = (hi - lo) or 1.0

    def px(k: int) -> float:
        return M + (k - xs[0]) / ((xs[-1] - xs[0]) or 1) * (W - 2 * M)

    def py(v: float) -> float:
        return H - M - (v - lo) / span * (H - 2 * M)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="sans-serif" font-size="11">',
           f'<rect width="{W}" height="{H}" fill="white"/>',
           f'<line x1="{M}" y1="{py(0):.1f}" x2="{W - M}" y2="{py(0):.1f}" stroke="#999" stroke-dasharray="4"/>',
           f'<text x="{W / 2}" y="18" text-anchor="middle" font-size="13">행사 시작 기준 시간대별 평균 증가분(명)</text>']
    for k in xs:
        out.append(f'<text x="{px(k):.1f}" y="{H - M + 18}" text-anchor="middle">{k:+d}h</text>')
    out.append(f'<text x="{M - 6}" y="{py(hi):.1f}" text-anchor="end">{hi:,.0f}</text>')
    out.append(f'<text x="{M - 6}" y="{py(lo):.1f}" text-anchor="end">{lo:,.0f}</text>')
    for i, (z, p) in enumerate(profile.items()):
        pts = " ".join(f"{px(k):.1f},{py(p[k]):.1f}" for k in sorted(p))
        c = colors.get(z, "#000")
        out.append(f'<polyline fill="none" stroke="{c}" stroke-width="2" points="{pts}"/>')
        out.append(f'<text x="{W - M + 4}" y="{M + 14 * i}" fill="{c}">{z}</text>')
    out.append("</svg>")
    return "\n".join(out)


def run(processed_dir: Path | None = None, report_dir: Path | None = None, sources: Sequence[str] = DEFAULT_SOURCES) -> Verdict:
    """D단계를 실행해 보고서 파일을 쓰고 `*`=0 기준 판정을 돌려준다."""
    proc = processed_dir or config.PROCESSED_DIR
    out_dir = report_dir or config.REPORT_DIR
    holidays = load_holidays(proc / HOLIDAYS_FILE)
    events, all_dates = load_events(proc, sources)
    s0 = load_series(proc, suppressed_fill=config.SUPPRESSED_FILL_VALUES[0])
    s3 = load_series(proc, suppressed_fill=config.SUPPRESSED_FILL_VALUES[1])
    v0 = evaluate_events(s0, events, all_dates, holidays)
    v3 = evaluate_events(s3, events, all_dates, holidays)
    flipped = changed_by_fill(v0, v3)

    excluded = set(all_dates) | holidays
    offsets = range(-config.SCORE_HOURS_BEFORE, config.SCORE_HOURS_AFTER + 1)
    profile: dict[str, dict[int, float]] = {}
    for z in config.ZONES:
        acc: dict[int, list[float]] = {k: [] for k in offsets}
        for r in v0.results:
            if not r.judgeable:
                continue
            for k, val in excess_profile(s0[z], r.event.start, excluded).items():
                if val is not None:
                    acc[k].append(val)
        profile[z] = {k: sum(x) / len(x) for k, x in acc.items() if x}

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "effect.md").write_text(render_report(v0, v3, flipped, profile), encoding="utf-8")
    (out_dir / "effect.svg").write_text(render_svg(profile), encoding="utf-8")
    logger.info("효과 확인 보고서 저장: %s (통과=%s)", out_dir / "effect.md", v0.passed)
    return v0


if __name__ == "__main__":
    v = run()
    print("\n".join(v.reasons))
    print("최종:", "통과" if v.passed else "통과하지 못함")
