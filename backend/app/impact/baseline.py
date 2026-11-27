"""행사 효과 계산: 기준값 → 증가분(점수) → 위약 검정.

용어: 기준값(baseline)=행사가 없었다면 그 시각에 있었을 사람 수의 추정치.
      증가분(excess)=실제값 − 기준값.  위약 검정(placebo)=행사 없는 날을 행사일인 척 계산해
      우연히 나오는 크기를 재는 방법.

계산 규칙은 결과를 보기 전에 고정했다(CLAUDE.md의 D단계). 값은 config.py에 있다.
시계열(series)은 한 구역의 시간별 합계로, 정시(분=0) datetime → 사람 수 매핑이다.
`*`(비식별) 처리는 이 모듈 밖에서 0 또는 3으로 채워 두 번 호출하는 방식으로 비교한다.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence, Set
from datetime import date, datetime, time, timedelta
from statistics import median

from app.impact import config


def _floor_hour(t: datetime) -> datetime:
    """분·초를 버려 정시로 맞춘다(19:30 → 19:00). 시계열 키가 정시라서 필요하다."""
    return t.replace(minute=0, second=0, microsecond=0)


def _valid(v: float | None) -> bool:
    """값이 있고 NaN이 아닌지. 결측을 0으로 착각해 기준값이 내려가는 걸 막는다."""
    return v is not None and not math.isnan(v)


def compute_baseline(
    values_by_date: Mapping[date, float],
    target: date,
    excluded_dates: Set[date],
    window_days: int = config.BASELINE_WINDOW_DAYS,
    min_days: int = config.BASELINE_MIN_DAYS,
) -> float | None:
    """한 구역·한 시각(예: park 19시)의 기준값.

    target 앞뒤 window_days일(양 끝 포함) 안에서 target과 **같은 요일**이고,
    excluded_dates(행사일·공휴일)에 없으며 값이 있는 날들의 **중앙값**.
    그런 날이 min_days 미만이면 None("판정 불가").
    target 자신은 값이 있어도 쓰지 않는다. 자기 값으로 자기 기준을 만들면 증가분이 줄어든다.
    """
    values: list[float] = []
    # 같은 요일은 7일 간격이라 7, 14, 21, 28일 전후만 보면 된다.
    for k in range(7, window_days + 1, 7):
        for sign in (-1, 1):
            d = target + timedelta(days=sign * k)
            v = values_by_date.get(d)
            if d in excluded_dates or not _valid(v):
                continue
            values.append(float(v))  # type: ignore[arg-type]  # _valid가 None을 걸렀다
    return median(values) if len(values) >= min_days else None


def compute_excess(
    actual: Mapping[datetime, float],
    baseline: Mapping[datetime, float | None],
    start: datetime,
    hours_before: int = config.SCORE_HOURS_BEFORE,
    hours_after: int = config.SCORE_HOURS_AFTER,
) -> float | None:
    """행사 점수 = 시작 시각 전후 창의 (실제값 − 기준값) 합.

    창은 시작 시(hour) 기준 [−hours_before, +hours_after]시간, **양 끝 포함**(기본 7칸).
    자정을 넘으면 다음 날 칸을 쓴다. 창 안에 실제값이나 기준값이 없는 칸이 하나라도 있으면
    합이 일부만 더해진 값이 되어 믿을 수 없으므로 None을 돌려준다.
    """
    t0 = _floor_hour(start)
    total = 0.0
    for k in range(-hours_before, hours_after + 1):
        t = t0 + timedelta(hours=k)
        a, b = actual.get(t), baseline.get(t)
        if not _valid(a) or not _valid(b):
            return None
        total += float(a) - float(b)  # type: ignore[arg-type]
    return total


def placebo_test(
    event_score: float,
    placebo_scores: Sequence[float],
    percentile: float = config.PLACEBO_PERCENTILE,
) -> tuple[bool, float]:
    """행사 점수가 위약 점수들의 percentile 백분위 문턱값을 **엄격히 넘는지** 판정한다.

    백분위는 선형 보간(numpy 기본값과 같은 방식)이다. 정렬한 n개 값에서
    위치 p=(n−1)×percentile/100, 문턱값 = v[lo] + (v[hi]−v[lo])×(p−lo).
    numpy를 직접 의존하지 않으려고 직접 구현했다. 반환은 (넘었는가, 문턱값).
    """
    if not placebo_scores:
        raise ValueError("위약 점수가 없습니다. 비행사일 표본이 필요합니다.")
    if not 0.0 <= percentile <= 100.0:
        raise ValueError(f"percentile은 0~100 사이여야 합니다: {percentile}")
    v = sorted(placebo_scores)
    p = (len(v) - 1) * percentile / 100.0
    lo = math.floor(p)
    hi = lo + 1
    threshold = v[lo] if hi >= len(v) else v[lo] + (v[hi] - v[lo]) * (p - lo)
    return event_score > threshold, threshold


# --- 위 3개를 시계열에 적용하는 연결 함수 -------------------------------------


def is_weekend(d: date) -> bool:
    """토·일이면 True. 위약 문턱값을 평일/주말 유형별로 따로 구하는 데 쓴다(변동폭이 다르다)."""
    return d.weekday() >= 5


def baseline_at(
    series: Mapping[datetime, float],
    t: datetime,
    excluded_dates: Set[date],
    window_days: int = config.BASELINE_WINDOW_DAYS,
    min_days: int = config.BASELINE_MIN_DAYS,
) -> float | None:
    """시각 t(정시)의 기준값. 같은 시(hour)의 값만 날짜별로 모아 compute_baseline에 넘긴다."""
    h = time(t.hour)
    values_by_date: dict[date, float] = {}
    for k in range(7, window_days + 1, 7):
        for sign in (-1, 1):
            d = t.date() + timedelta(days=sign * k)
            v = series.get(datetime.combine(d, h))
            if v is not None:
                values_by_date[d] = v
    return compute_baseline(values_by_date, t.date(), excluded_dates, window_days, min_days)


def score_start(
    series: Mapping[datetime, float],
    start: datetime,
    excluded_dates: Set[date],
    hours_before: int = config.SCORE_HOURS_BEFORE,
    hours_after: int = config.SCORE_HOURS_AFTER,
) -> float | None:
    """시작 시각 start에 행사가 있었다고 보고 점수를 낸다. 창의 시각마다 기준값을 구해 합친다.

    창이 자정을 넘으면 다음 날 칸의 기준값은 **그 칸의 날짜** 기준으로 구한다.
    기준값을 하나라도 못 구하면(표본 4일 미만 등) None = 판정 불가.
    """
    t0 = _floor_hour(start)
    baseline: dict[datetime, float | None] = {}
    for k in range(-hours_before, hours_after + 1):
        t = t0 + timedelta(hours=k)
        baseline[t] = baseline_at(series, t, excluded_dates)
    return compute_excess(series, baseline, start, hours_before, hours_after)


def placebo_scores(
    series: Mapping[datetime, float],
    candidate_days: Iterable[date],
    start_hours: Iterable[int],
    excluded_dates: Set[date],
) -> list[float]:
    """행사 없는 날들을 행사일인 척 채점한 점수 목록(위약 표본).

    candidate_days: 행사도 공휴일도 아닌 날(호출 쪽에서 평일/주말로 나눠 넘긴다).
    start_hours: 실제 행사들의 시작 시(hour) 분포. 각 후보일을 시작 시각마다 한 번씩 채점한다.
    행사 없는 날에는 시작 시각이 없으므로 실제 행사와 같은 시간 창을 쓰려는 것이다.
    판정 불가(None)인 조합은 표본에서 뺀다.
    """
    hours = sorted(set(start_hours))
    out: list[float] = []
    for d in candidate_days:
        for h in hours:
            s = score_start(series, datetime.combine(d, time(h)), excluded_dates)
            if s is not None:
                out.append(s)
    return out
