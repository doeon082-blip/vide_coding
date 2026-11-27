"""D단계 판정 테스트: 가짜 시계열에 증가분을 심어 통과/탈락/판정 불가를 확인한다."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.impact.evaluate import ImpactEvent, changed_by_fill, evaluate_events

ZONES = ("park", "ring1", "ring2")
HOLIDAYS = {date(2025, 10, 4)}
# 토요일 5개. 9~11월 판정 기간 안이고 서로 4주 안에 겹쳐도 기준 표본이 4일 이상 남는다.
EVENT_DAYS = [date(2025, 9, 20), date(2025, 10, 11), date(2025, 10, 25), date(2025, 11, 8), date(2025, 11, 22)]


def _flat(start: date = date(2025, 8, 1), end: date = date(2025, 12, 31), base: float = 100.0) -> dict[datetime, float]:
    out: dict[datetime, float] = {}
    d = start
    while d <= end:
        for h in range(24):
            out[datetime(d.year, d.month, d.day, h)] = base
        d += timedelta(days=1)
    return out


def _events() -> list[ImpactEvent]:
    return [ImpactEvent(f"e{i}", f"공연{i}", datetime(d.year, d.month, d.day, 19)) for i, d in enumerate(EVENT_DAYS)]


def _plant(series: dict[datetime, float], days: list[date], amount: float) -> None:
    for d in days:
        for h in range(16, 23):  # 19시 시작의 창(16~22시)
            series[datetime(d.year, d.month, d.day, h)] += amount


def _run(park_boost: float, days: list[date] | None = None):
    series = {z: _flat() for z in ZONES}
    _plant(series["park"], days or EVENT_DAYS, park_boost)
    return evaluate_events(series, _events(), set(EVENT_DAYS), HOLIDAYS)


def test_passes_when_increase_planted_in_park() -> None:
    v = _run(10.0)
    assert v.n_judgeable == 5 and v.n_pass == 5 and v.pass_ratio == 1.0
    assert v.median_excess["park"] == 70.0
    assert v.passed is True
    assert all(r.scores["ring1"] == 0.0 and not r.exceeded["ring1"] for r in v.results)


def test_fails_when_nothing_planted() -> None:
    v = _run(0.0)
    assert v.n_pass == 0 and v.passed is False  # 점수 0은 문턱값 0을 "초과"하지 못한다


def test_fails_when_only_minority_exceed() -> None:
    v = _run(10.0, EVENT_DAYS[:2])  # 5건 중 2건만 증가
    assert v.n_pass == 2 and v.pass_ratio == 0.4 and v.passed is False


def test_decrease_gives_negative_median_and_fails() -> None:
    v = _run(-10.0)
    assert v.median_excess["park"] == -70.0 and v.passed is False


def test_unjudgeable_when_data_missing() -> None:
    series = {z: _flat(date(2025, 10, 10), date(2025, 10, 12)) for z in ZONES}  # 이웃 요일 없음
    v = evaluate_events(series, _events(), set(EVENT_DAYS), HOLIDAYS)
    # 판정 기간 안의 행사 5건 모두 같은 요일 이웃이 없어 판정 불가
    assert v.n_judgeable == 0 and v.n_unjudgeable == 5 and v.pass_ratio is None and v.passed is False


def test_events_outside_judge_period_are_ignored() -> None:
    ev = [ImpactEvent("old", "8월 공연", datetime(2025, 8, 23, 19))]
    series = {z: _flat() for z in ZONES}
    v = evaluate_events(series, ev, {date(2025, 8, 23)}, set())
    assert v.n_judged_period == 0 and v.passed is False


def test_holiday_event_is_flagged() -> None:
    ev = [ImpactEvent("h", "휴일 공연", datetime(2025, 10, 4, 19))]
    series = {z: _flat() for z in ZONES}
    v = evaluate_events(series, ev, {date(2025, 10, 4)}, HOLIDAYS)
    assert v.results[0].on_holiday is True


def test_changed_by_fill_detects_flip() -> None:
    a, b = _run(10.0), _run(10.0)
    assert changed_by_fill(a, b) == []
    b.results[0].passed = False
    assert changed_by_fill(a, b) == ["e0"]
