"""Формулы раздела 2 ПР1 на контрольных примерах"""

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.services import metrics


@dataclass
class M:
    won: bool | None = True
    kills: int | None = 10
    deaths: int | None = 10
    finished_at: datetime = datetime(2026, 10, 1, tzinfo=UTC)


def games(wins: int, losses: int) -> list[M]:
    return [M(won=True)] * wins + [M(won=False)] * losses


def test_win_rate_shows_numerator_and_denominator() -> None:
    ratio = metrics.win_rate(games(12, 8))
    assert (ratio.numerator, ratio.denominator, ratio.sample_size) == (12, 20, 20)
    assert ratio.value == 60.0


def test_unknown_result_is_excluded_not_counted_as_loss() -> None:
    ratio = metrics.win_rate([*games(9, 9), M(won=None), M(won=None)])
    assert ratio.denominator == 18
    assert ratio.value == 50.0


def test_win_rate_without_known_results_is_undefined() -> None:
    ratio = metrics.win_rate([M(won=None)])
    assert ratio.value is None
    assert ratio.sample_size == 0


def test_kd_sums_kills_and_deaths_over_complete_matches() -> None:
    matches = [M(kills=20, deaths=10), M(kills=10, deaths=15), M(kills=None, deaths=5)]
    ratio = metrics.kill_death(matches)
    assert (ratio.numerator, ratio.denominator, ratio.sample_size) == (30, 25, 2)
    assert ratio.value == pytest.approx(1.2)


def test_kd_sample_size_reflects_missing_fields() -> None:
    # S02, критерий 4: 20 матчей, но K/D считается по 18.
    matches = [M()] * 18 + [M(kills=None), M(deaths=None)]
    assert metrics.kill_death(matches).sample_size == 18


def test_kd_with_zero_deaths_is_undefined_not_infinite() -> None:
    ratio = metrics.kill_death([M(kills=7, deaths=0)])
    assert ratio.value is None
    assert (ratio.numerator, ratio.denominator) == (7, 0)


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        # Контрольный пример A01 из ПР1: 12/20 (60%) → 8/20 (40%) = −20 п.п.
        (games(12, 8), games(8, 12), -20.0),
        (games(10, 10), games(10, 10), 0.0),
    ],
)
def test_win_rate_change_in_percentage_points(
    before: list[M], after: list[M], expected: float
) -> None:
    change = metrics.change(metrics.win_rate(before), metrics.win_rate(after))
    assert change == pytest.approx(expected)


def test_kd_change_is_absolute_number() -> None:
    # Контрольный пример A02: 1,20 → 1,00 - снижение на 0,20.
    before = metrics.kill_death([M(kills=120, deaths=100)])
    after = metrics.kill_death([M(kills=100, deaths=100)])
    assert metrics.change(before, after) == pytest.approx(-0.2)


def test_change_is_none_when_any_value_undefined() -> None:
    defined = metrics.kill_death([M(kills=10, deaths=10)])
    undefined = metrics.kill_death([M(kills=10, deaths=0)])
    assert metrics.change(defined, undefined) is None
    assert metrics.change(undefined, defined) is None


@pytest.mark.parametrize(
    ("match", "metric", "expected"),
    [
        (M(won=None), "win_rate", False),
        (M(won=False), "win_rate", True),
        (M(kills=None), "kd", False),
        (M(deaths=None), "kd", False),
        (M(kills=0, deaths=0), "kd", True),
    ],
)
def test_has_metric_data(match: M, metric: metrics.Metric, expected: bool) -> None:
    assert metrics.has_metric_data(match, metric) is expected


def test_compute_dispatches_by_metric() -> None:
    matches = [M(won=True, kills=3, deaths=1)]
    assert metrics.compute("win_rate", matches).value == 100.0
    assert metrics.compute("kd", matches).value == 3.0


def test_rounded() -> None:
    assert metrics.rounded(1.23456) == 1.23
    assert metrics.rounded(None) is None
