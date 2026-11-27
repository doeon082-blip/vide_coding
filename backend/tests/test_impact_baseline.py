"""핵심 계산 3개의 테스트. 기대값은 손으로 계산한 값이다.

compute_baseline / compute_excess / placebo_test와, 이를 시계열에 적용하는 연결 함수를 검증한다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.impact.baseline import (
    baseline_at, compute_baseline, compute_excess, is_weekend, placebo_scores, placebo_test, score_start,
)

TARGET = date(2025, 10, 18)  # 토요일


def _sat_values() -> dict[date, float]:
    # 같은 요일(토) ±28일: 9/20, 9/27, 10/4, 10/11, 10/25, 11/1, 11/8, 11/15
    days = [date(2025, 9, 20), date(2025, 9, 27), date(2025, 10, 4), date(2025, 10, 11),
            date(2025, 10, 25), date(2025, 11, 1), date(2025, 11, 8), date(2025, 11, 15)]
    return dict(zip(days, [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0]))


def test_baseline_median_excluding_event_and_holiday_days() -> None:
    # 10/4(공휴일)와 10/11(행사일)을 빼면 100,110,140,150,160,170 → 중앙값 (140+150)/2
    got = compute_baseline(_sat_values(), TARGET, {date(2025, 10, 4), date(2025, 10, 11)})
    assert got == 145.0


def test_baseline_ignores_other_weekdays_and_target_itself() -> None:
    vals = _sat_values()
    vals[date(2025, 10, 19)] = 9999.0  # 일요일: 다른 요일이라 무시
    vals[TARGET] = 9999.0  # 자기 자신도 무시
    got = compute_baseline(vals, TARGET, set())
    assert got == 135.0  # 8개 100..170 의 중앙값 (130+140)/2


def test_baseline_window_includes_both_ends_exactly_28_days() -> None:
    vals = {TARGET - timedelta(days=28): 10.0, TARGET + timedelta(days=28): 20.0,
            TARGET - timedelta(days=14): 30.0, TARGET + timedelta(days=14): 40.0}
    assert compute_baseline(vals, TARGET, set()) == 25.0  # 정렬 10,20,30,40 → (20+30)/2


def test_baseline_returns_none_when_fewer_than_4_days() -> None:
    vals = _sat_values()
    excluded = {date(2025, 9, 20), date(2025, 9, 27), date(2025, 10, 4), date(2025, 10, 11), date(2025, 10, 25)}
    assert compute_baseline(vals, TARGET, excluded) is None  # 남은 3일


def test_baseline_skips_missing_dates() -> None:
    vals = {d: v for d, v in _sat_values().items() if d.month == 11}  # 11월 3일만 남음
    assert compute_baseline(vals, TARGET, set()) is None


def _hours(center: datetime, n_before: int, n_after: int, value: float) -> dict[datetime, float]:
    return {center + timedelta(hours=k): value for k in range(-n_before, n_after + 1)}


def test_excess_sums_seven_hour_window() -> None:
    start = datetime(2025, 10, 18, 19, 30)  # 분은 무시 → 19시
    center = datetime(2025, 10, 18, 19)
    actual = _hours(center, 3, 3, 110.0)
    baseline = _hours(center, 3, 3, 100.0)
    assert compute_excess(actual, baseline, start) == 70.0  # 7칸 × 10


def test_excess_ignores_hours_outside_window() -> None:
    t = datetime(2025, 10, 18, 19)
    actual = _hours(t, 6, 6, 110.0)
    baseline = _hours(t, 6, 6, 100.0)
    actual[t + timedelta(hours=4)] = 99999.0  # 창 밖
    assert compute_excess(actual, baseline, t) == 70.0


def test_excess_crosses_midnight() -> None:
    t = datetime(2025, 10, 18, 22)  # 창: 19시 ~ 다음 날 1시
    actual = _hours(t, 3, 3, 105.0)
    baseline = _hours(t, 3, 3, 100.0)
    assert compute_excess(actual, baseline, t) == 35.0


def test_excess_none_when_baseline_missing_in_window() -> None:
    t = datetime(2025, 10, 18, 19)
    actual = _hours(t, 3, 3, 110.0)
    baseline: dict[datetime, float | None] = dict(_hours(t, 3, 3, 100.0))
    baseline[t] = None
    assert compute_excess(actual, baseline, t) is None


def test_excess_none_when_actual_missing_in_window() -> None:
    t = datetime(2025, 10, 18, 19)
    actual = _hours(t, 3, 3, 110.0)
    del actual[t + timedelta(hours=2)]
    assert compute_excess(actual, _hours(t, 3, 3, 100.0), t) is None


def test_placebo_threshold_linear_interpolation() -> None:
    scores = [float(i) for i in range(1, 101)]  # 1..100, 위치 99×0.95=94.05 → 95 + 0.05×1
    exceeds, thr = placebo_test(96.0, scores)
    assert thr == pytest.approx(95.05)
    assert exceeds is True


def test_placebo_strictly_greater_not_equal() -> None:
    scores = [float(i) for i in range(1, 102)]  # 1..101, 위치 100×0.95=95.0 → 정확히 96.0
    exceeds, thr = placebo_test(96.0, scores)
    assert thr == pytest.approx(96.0)
    assert exceeds is False


def test_placebo_unsorted_input_and_empty() -> None:
    assert placebo_test(10.0, [5.0, 1.0, 3.0, 2.0, 4.0])[1] == pytest.approx(4.8)  # 위치 4×0.95=3.8
    with pytest.raises(ValueError):
        placebo_test(1.0, [])


def test_baseline_nan_is_treated_as_missing() -> None:
    vals = _sat_values()
    vals[date(2025, 9, 20)] = float("nan")
    vals[date(2025, 9, 27)] = float("nan")
    # 남은 6일: 120,130,140,150,160,170 → 중앙값 145
    assert compute_baseline(vals, TARGET, set()) == 145.0


def test_baseline_custom_window_and_min_days() -> None:
    vals = {TARGET - timedelta(days=7): 10.0, TARGET + timedelta(days=7): 30.0}
    assert compute_baseline(vals, TARGET, set(), window_days=7, min_days=2) == 20.0
    assert compute_baseline(vals, TARGET, set(), window_days=7, min_days=3) is None


def test_placebo_percentile_bounds() -> None:
    assert placebo_test(5.0, [1.0, 2.0, 3.0], percentile=100.0) == (True, 3.0)
    assert placebo_test(0.0, [1.0, 2.0, 3.0], percentile=0.0) == (False, 1.0)
    with pytest.raises(ValueError):
        placebo_test(1.0, [1.0], percentile=101.0)


def _series(days: list[date], base: float = 100.0) -> dict[datetime, float]:
    return {datetime(d.year, d.month, d.day, h): base for d in days for h in range(24)}


def _sat_days() -> list[date]:
    return [TARGET + timedelta(days=7 * k) for k in range(-4, 5)]  # 9/20 ~ 11/15


def test_is_weekend() -> None:
    assert is_weekend(date(2025, 10, 18)) and is_weekend(date(2025, 10, 19))
    assert not is_weekend(date(2025, 10, 17))


def test_score_start_detects_planted_increase() -> None:
    series = _series(_sat_days())
    for h in range(16, 23):  # 19시 시작 창(16~22시)에 +10씩
        series[datetime(2025, 10, 18, h)] = 110.0
    assert score_start(series, datetime(2025, 10, 18, 19), set()) == 70.0


def test_score_start_none_when_baseline_unavailable() -> None:
    series = _series([TARGET, TARGET + timedelta(days=7)])  # 같은 요일 이웃이 1일뿐
    assert score_start(series, datetime(2025, 10, 18, 19), set()) is None


def test_score_start_across_midnight_uses_next_day_baseline() -> None:
    days = _sat_days() + [d + timedelta(days=1) for d in _sat_days()]  # 토·일 모두
    series = _series(days)
    series[datetime(2025, 10, 19, 0)] = 150.0  # 일요일 0시: 같은 요일(일) 이웃 기준 100 → +50
    assert score_start(series, datetime(2025, 10, 18, 22), set()) == 50.0


def test_placebo_scores_skip_unscorable_and_cover_each_hour() -> None:
    series = _series(_sat_days())
    series[datetime(2025, 10, 11, 19)] = 107.0  # 10/11을 후보로 채점 시 19시 칸만 +7
    got = placebo_scores(series, [date(2025, 10, 11), date(2025, 10, 18)], [19, 20], set())
    # 10/11 19시 창(16~22시)에는 19시 칸 포함 → +7, 10/11 20시 창도 19시 칸 포함 → +7
    # 10/18 쪽은 이웃인 10/11의 19시가 107이라 기준값(중앙값)은 100 그대로 → 0, 0
    assert sorted(got) == [0.0, 0.0, 7.0, 7.0]
    assert placebo_scores(series, [date(2025, 10, 12)], [19], set()) == []  # 일요일은 이웃 없음
