"""Формулы показателей из раздела 2 ПР1.

Одни и те же функции используются в обзоре, сравнении и целях (NFR08).
Пропуск данных никогда не превращается в ноль: матч просто не входит в выборку метрики
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

FORMULA_VERSION = "1"
OVERVIEW_SIZE = 20
GOAL_SAMPLE_SIZE = 20

Metric = Literal["win_rate", "kd"]


class MatchLike(Protocol):
    @property
    def finished_at(self) -> datetime: ...
    @property
    def won(self) -> bool | None: ...
    @property
    def kills(self) -> int | None: ...
    @property
    def deaths(self) -> int | None: ...


@dataclass(frozen=True)
class Ratio:
    """Точный итог метрики: числитель, знаменатель и размер выборки"""

    numerator: int
    denominator: int
    sample_size: int
    scale: int = 1

    @property
    def value(self) -> float | None:
        # Деление на ноль не даёт бесконечность: значение отсутствует (ПР1, K/D)
        if self.denominator == 0:
            return None
        return self.numerator * self.scale / self.denominator


def has_metric_data(match: MatchLike, metric: Metric) -> bool:
    if metric == "win_rate":
        return match.won is not None
    return match.kills is not None and match.deaths is not None


def win_rate(matches: Sequence[MatchLike]) -> Ratio:
    """Победы / матчи с известным результатом × 100%"""
    known = [m for m in matches if m.won is not None]
    wins = sum(1 for m in known if m.won)
    return Ratio(numerator=wins, denominator=len(known), sample_size=len(known), scale=100)


def kill_death(matches: Sequence[MatchLike]) -> Ratio:
    """Сумма убийств / сумма смертей по матчам, где известны оба поля"""
    complete = [m for m in matches if m.kills is not None and m.deaths is not None]
    kills = sum(m.kills for m in complete if m.kills is not None)
    deaths = sum(m.deaths for m in complete if m.deaths is not None)
    return Ratio(numerator=kills, denominator=deaths, sample_size=len(complete))


def compute(metric: Metric, matches: Sequence[MatchLike]) -> Ratio:
    return win_rate(matches) if metric == "win_rate" else kill_death(matches)


def change(before: Ratio, after: Ratio) -> float | None:
    """Изменение: для доли побед - в процентных пунктах, для K/D - числом"""
    if before.value is None or after.value is None:
        return None
    return after.value - before.value


def rounded(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)
