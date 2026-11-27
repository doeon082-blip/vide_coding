"""D단계: 행사별 점수·문턱값을 구하고 "효과가 있다"의 통과 여부를 판정한다.

통과 기준(결과를 보기 전에 고정):
  1) 판정 가능한 행사일 중 절반 이상이 park 또는 ring1에서 위약 문턱값을 넘는다.
  2) 증가분(점수)의 중앙값이 park 또는 ring1 중 한 곳에서 양수다.
     (기준 문구 "증가분의 중앙값이 양수"를 "park 또는 ring1"과 같은 방식으로 해석한 것이다.)
통과하지 못해도 기준을 낮추지 않는다. "판정 불가" 비율은 항상 함께 보고한다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass, field
from datetime import date, datetime
from statistics import median

from app.impact import config
from app.impact.baseline import is_weekend, placebo_scores, placebo_test, score_start

Series = Mapping[datetime, float]  # 한 구역의 시간별 합계(정시 → 사람 수)


@dataclass(frozen=True)
class ImpactEvent:
    """판정할 행사 한 건. 시작 시각이 없는 행사는 판정할 수 없으므로 호출 쪽에서 뺀다."""

    event_id: str
    name: str
    start: datetime


@dataclass
class EventResult:
    event: ImpactEvent
    on_holiday: bool  # 공휴일에 열린 행사(기준값이 평일 위주라 편향 가능, 표시만 하고 판정은 같다)
    scores: dict[str, float | None] = field(default_factory=dict)  # 구역 → 점수(None=판정 불가)
    thresholds: dict[str, float | None] = field(default_factory=dict)  # 구역 → 위약 문턱값
    exceeded: dict[str, bool] = field(default_factory=dict)  # 구역 → 문턱값 초과 여부
    judgeable: bool = False  # PASS_ZONES 중 하나라도 점수와 문턱값이 있으면 True
    passed: bool = False  # PASS_ZONES 중 하나라도 초과하면 True


@dataclass
class Verdict:
    results: list[EventResult]
    n_judged_period: int  # 판정 기간 안의 행사 수
    n_judgeable: int
    n_unjudgeable: int
    n_pass: int
    pass_ratio: float | None  # 판정 가능한 행사 중 통과 비율(없으면 None)
    median_excess: dict[str, float | None]  # PASS_ZONES별 점수 중앙값
    passed: bool  # 최종 통과 여부
    reasons: list[str]  # 통과/탈락 이유(사람이 읽는 한 줄들)


def evaluate_events(
    series_by_zone: Mapping[str, Series],
    events: Sequence[ImpactEvent],
    all_event_dates: Set[date],
    holidays: Set[date],
    judge_start: date | None = None,
    judge_end: date | None = None,
) -> Verdict:
    """모든 구역·행사에 대해 점수와 문턱값을 구하고 최종 판정을 낸다.

    all_event_dates: 시작 시각이 없는 행사까지 포함한 **공원의 모든 행사일**(기준값에서 제외).
    holidays: 확인된 공휴일(기준값에서 제외). 값은 호출 쪽에서 승인받은 목록을 넘긴다.
    위약 표본은 구역별·평일/주말별로 따로 모은다(변동폭이 달라 한꺼번에 섞으면 문턱값이 어긋난다).
    """
    lo = judge_start or date.fromisoformat(config.JUDGE_START)
    hi = judge_end or date.fromisoformat(config.JUDGE_END)
    excluded = set(all_event_dates) | set(holidays)
    in_period = [e for e in events if lo <= e.start.date() <= hi]
    start_hours = sorted({e.start.hour for e in events})

    # 위약 표본은 (구역, 주말 여부)마다 한 번만 만들어 재사용한다(계산량이 크다).
    placebo_cache: dict[tuple[str, bool], list[float]] = {}

    def placebo_for(zone: str, weekend: bool) -> list[float]:
        key = (zone, weekend)
        if key not in placebo_cache:
            days = sorted({t.date() for t in series_by_zone[zone]})
            candidates = [d for d in days if d not in excluded and is_weekend(d) == weekend]
            placebo_cache[key] = placebo_scores(series_by_zone[zone], candidates, start_hours, excluded)
        return placebo_cache[key]

    results: list[EventResult] = []
    for ev in in_period:
        res = EventResult(event=ev, on_holiday=ev.start.date() in holidays)
        weekend = is_weekend(ev.start.date())
        for zone, series in series_by_zone.items():
            score = score_start(series, ev.start, excluded)
            res.scores[zone] = score
            samples = placebo_for(zone, weekend)
            if score is None or not samples:
                res.thresholds[zone] = None
                res.exceeded[zone] = False
                continue
            exceeds, thr = placebo_test(score, samples)
            res.thresholds[zone] = thr
            res.exceeded[zone] = exceeds
        usable = [z for z in config.PASS_ZONES if res.thresholds.get(z) is not None]
        res.judgeable = bool(usable)
        res.passed = any(res.exceeded.get(z, False) for z in usable)
        results.append(res)

    judgeable = [r for r in results if r.judgeable]
    n_pass = sum(r.passed for r in judgeable)
    ratio = n_pass / len(judgeable) if judgeable else None
    med: dict[str, float | None] = {}
    for z in config.PASS_ZONES:
        vals = [r.scores[z] for r in judgeable if r.scores.get(z) is not None]
        med[z] = median(vals) if vals else None  # type: ignore[type-var]

    reasons: list[str] = []
    ratio_ok = ratio is not None and ratio >= config.PASS_RATIO
    median_ok = any(m is not None and m > 0 for m in med.values())
    reasons.append(
        f"판정 가능 {len(judgeable)}건 중 {n_pass}건 통과"
        + (f" ({ratio:.0%}, 기준 {config.PASS_RATIO:.0%} 이상)" if ratio is not None else " (판정 가능한 행사 없음)")
    )
    reasons.append("증가분 중앙값 " + ", ".join(f"{z}={m if m is None else round(m, 1)}" for z, m in med.items()))
    if len(results) - len(judgeable):
        reasons.append(f"판정 불가 {len(results) - len(judgeable)}건 (기준값 표본 4일 미만 또는 결측)")
    return Verdict(
        results=results,
        n_judged_period=len(in_period),
        n_judgeable=len(judgeable),
        n_unjudgeable=len(results) - len(judgeable),
        n_pass=n_pass,
        pass_ratio=ratio,
        median_excess=med,
        passed=bool(ratio_ok and median_ok),
        reasons=reasons,
    )


def changed_by_fill(a: Verdict, b: Verdict) -> list[str]:
    """`*`를 0으로 채운 결과(a)와 3으로 채운 결과(b)에서 통과 여부가 달라진 행사 id 목록.

    비어 있으면 `*` 처리 방식이 판정에 영향을 주지 않는다는 뜻이다.
    """
    pb = {r.event.event_id: r.passed for r in b.results}
    return [r.event.event_id for r in a.results if r.event.event_id in pb and pb[r.event.event_id] != r.passed]
