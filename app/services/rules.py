"""Сравнение выборок и правила рекомендаций A01–A03 (S07–S10; ПР1, раздел 2.1)

Модуль не обращается к БД: на вход - матчи от новых к старым, на выход - неизменяемые
результаты. Пороги сравниваются в точной арифметике (Fraction), поэтому значение ровно
на пороге срабатывает предсказуемо: 60% → 45% - это ровно 15 п.п., а не 14,999…
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Literal, Protocol, cast

from app.services import metrics

RULES_VERSION = "1"
GROUP_SIZE = 20
MAP_MIN_MATCHES = 10
REVIEW_COUNT = 3
MAX_INSIGHTS = 3

# Пороги версии правил 1 (ПР1, раздел 2.1)
A01_WIN_RATE_DROP_PP = Fraction(15)
A02_KD_DROP = Fraction(15, 100)
A03_MAX_WIN_RATE_PCT = Fraction(40)

RuleId = Literal["A01", "A02", "A03"]


class RuleMatch(metrics.MatchLike, Protocol):
    @property
    def faceit_match_id(self) -> str: ...
    @property
    def map(self) -> str | None: ...


@dataclass(frozen=True)
class Group:
    """Группа сравнения: матчи от новых к старым"""

    matches: Sequence[RuleMatch]

    @property
    def period_from(self) -> datetime:
        return self.matches[-1].finished_at

    @property
    def period_to(self) -> datetime:
        return self.matches[0].finished_at

    def complete(self, metric: metrics.Metric) -> bool:
        """Метрика известна во всех матчах группы"""
        return len(self.matches) == GROUP_SIZE and all(
            metrics.has_metric_data(m, metric) for m in self.matches
        )


@dataclass(frozen=True)
class Split:
    recent: Group
    previous: Group


def split_groups(matches: Sequence[RuleMatch]) -> Split | None:
    """Последние 20 и предыдущие 20 матчей без пересечения (S07, критерий 1)

    Повтор одного матча в истории не должен попасть в обе группы (сбой 10.2 из ПР1),
    поэтому дубликаты по faceit_match_id отбрасываются до разбиения.
    """
    unique: list[RuleMatch] = []
    seen: set[str] = set()
    for match in matches:
        if match.faceit_match_id not in seen:
            seen.add(match.faceit_match_id)
            unique.append(match)
    if len(unique) < 2 * GROUP_SIZE:
        return None
    return Split(
        recent=Group(unique[:GROUP_SIZE]),
        previous=Group(unique[GROUP_SIZE : 2 * GROUP_SIZE]),
    )


def exact_win_rate(group: Sequence[RuleMatch]) -> Fraction | None:
    ratio = metrics.win_rate(group)
    return None if ratio.denominator == 0 else Fraction(ratio.numerator * 100, ratio.denominator)


def exact_kd(group: Sequence[RuleMatch]) -> Fraction | None:
    ratio = metrics.kill_death(group)
    return None if ratio.denominator == 0 else Fraction(ratio.numerator, ratio.denominator)


@dataclass(frozen=True)
class MapSummary:
    map: str
    matches: Sequence[RuleMatch]
    known: int
    wins: int

    @property
    def win_rate(self) -> Fraction | None:
        return None if self.known == 0 else Fraction(self.wins * 100, self.known)

    @property
    def enough_data(self) -> bool:
        return self.known >= MAP_MIN_MATCHES


def by_map(matches: Sequence[RuleMatch]) -> list[MapSummary]:
    """Матчи по картам (S08). Матчи без карты в разбивку не входят"""
    groups: dict[str, list[RuleMatch]] = defaultdict(list)
    for match in matches:
        if match.map:
            groups[match.map].append(match)
    summaries = []
    for name, items in groups.items():
        known = [m for m in items if m.won is not None]
        summaries.append(
            MapSummary(
                map=name, matches=items, known=len(known), wins=sum(1 for m in known if m.won)
            )
        )
    return sorted(summaries, key=lambda s: (-len(s.matches), s.map))


@dataclass(frozen=True)
class Insight:
    rule_id: RuleId
    metric: metrics.Metric
    title: str
    limitation: str
    action: str
    before: Fraction | None
    after: Fraction | None
    period_from: datetime
    period_to: datetime
    sample_size: int
    map: str | None
    evidence: Sequence[RuleMatch]
    review_match_ids: Sequence[str]


def format_pct(value: Fraction) -> str:
    """60 → «60%», 100/3 → «33,3%»"""
    if value.denominator == 1:
        return f"{value.numerator}%"
    return f"{float(value):.1f}%".replace(".", ",")


def format_kd(value: Fraction) -> str:
    return f"{float(value):.2f}".replace(".", ",")


def _latest_losses(matches: Sequence[RuleMatch], count: int = REVIEW_COUNT) -> list[str]:
    return [m.faceit_match_id for m in matches if m.won is False][:count]


def rule_a01(split: Split) -> Insight | None:
    """Доля побед снизилась на 15 п.п. или более между полными группами"""
    if not (split.recent.complete("win_rate") and split.previous.complete("win_rate")):
        return None
    before = exact_win_rate(split.previous.matches)
    after = exact_win_rate(split.recent.matches)
    if before is None or after is None or before - after < A01_WIN_RATE_DROP_PP:
        return None
    return Insight(
        rule_id="A01",
        metric="win_rate",
        title=(
            f"Доля побед снизилась с {format_pct(before)} до {format_pct(after)} "
            "в двух сравниваемых выборках"
        ),
        limitation=(
            "Наблюдение по общей статистике: сервис не определяет причину поражений "
            "и не утверждает конкретную ошибку"
        ),
        action=(
            "Выбрать и самостоятельно пересмотреть 3 поражения из последней группы; "
            "записать повторяющиеся ситуации, которые требуют проверки"
        ),
        before=before,
        after=after,
        period_from=split.previous.period_from,
        period_to=split.recent.period_to,
        sample_size=2 * GROUP_SIZE,
        map=None,
        evidence=[*split.recent.matches, *split.previous.matches],
        review_match_ids=_latest_losses(split.recent.matches),
    )


def rule_a02(split: Split) -> Insight | None:
    """K/D снизился на 0,15 или более; в каждой группе полные данные и смертей больше нуля"""
    if not (split.recent.complete("kd") and split.previous.complete("kd")):
        return None
    before = exact_kd(split.previous.matches)
    after = exact_kd(split.recent.matches)
    if before is None or after is None or before - after < A02_KD_DROP:
        return None
    return Insight(
        rule_id="A02",
        metric="kd",
        title=(
            f"K/D снизился с {format_kd(before)} до {format_kd(after)}; "
            "причина изменения по общей статистике неизвестна"
        ),
        limitation=(
            "Сервис не видит эпизодов матча: вывод о позиционировании, гранатах "
            "или решениях по этим данным сделать нельзя"
        ),
        action=(
            "Пересмотреть эпизоды смертей в 3 последних матчах и составить список "
            "повторяющихся ситуаций для дальнейшего разбора"
        ),
        before=before,
        after=after,
        period_from=split.previous.period_from,
        period_to=split.recent.period_to,
        sample_size=2 * GROUP_SIZE,
        map=None,
        evidence=[*split.recent.matches, *split.previous.matches],
        review_match_ids=[m.faceit_match_id for m in split.recent.matches[:REVIEW_COUNT]],
    )


def rule_a03(maps: Sequence[MapSummary]) -> Insight | None:
    """Карта с минимум 10 матчами и долей побед не выше 40%

    Из подходящих карт выбирается самая низкая доля побед, затем больше матчей,
    затем название по алфавиту
    """
    candidates = [
        s
        for s in maps
        if s.enough_data and s.win_rate is not None and s.win_rate <= A03_MAX_WIN_RATE_PCT
    ]
    if not candidates:
        return None
    chosen = min(candidates, key=lambda s: (cast(Fraction, s.win_rate), -s.known, s.map))
    known = [m for m in chosen.matches if m.won is not None]
    return Insight(
        rule_id="A03",
        metric="win_rate",
        title=(
            f"На карте {chosen.map} в выбранной выборке {chosen.wins} "
            f"{_plural(chosen.wins, 'победа', 'победы', 'побед')} "
            f"из {chosen.known} {_plural(chosen.known, 'матча', 'матчей', 'матчей')}"
        ),
        limitation=(
            f"Порог {MAP_MIN_MATCHES} матчей - рабочее правило продукта, "
            "а не гарантия статистической значимости"
        ),
        action=(
            "Начать самостоятельный разбор с 3 поражений на этой карте; "
            "сравнить свои действия в выбранных играх"
        ),
        before=None,
        after=chosen.win_rate,
        period_from=known[-1].finished_at,
        period_to=known[0].finished_at,
        sample_size=chosen.known,
        map=chosen.map,
        evidence=known,
        review_match_ids=_latest_losses(known),
    )


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Согласование: 1 победа из 21 матча, 4 победы из 12 матчей, 5 побед"""
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


@dataclass(frozen=True)
class InsightsResult:
    status: Literal["ready", "no_signals", "insufficient_data"]
    message: str | None
    items: Sequence[Insight]


NO_SIGNALS = "По выбранным правилам выраженных сигналов не найдено"
INSUFFICIENT = "Недостаточно данных для сводки"


def evaluate(matches: Sequence[RuleMatch]) -> InsightsResult:
    """Сводка: A01, затем A02, затем одно наблюдение A03 - не более трёх (S09)

    При одинаковых данных и версии правил результат одинаков (S09, критерий 6)
    """
    split = split_groups(matches)
    maps = by_map(matches)
    if split is None and not any(s.enough_data for s in maps):
        return InsightsResult(status="insufficient_data", message=INSUFFICIENT, items=[])
    items: list[Insight] = []
    if split is not None:
        items += [i for i in (rule_a01(split), rule_a02(split)) if i is not None]
    a03 = rule_a03(maps)
    if a03 is not None:
        items.append(a03)
    if not items:
        return InsightsResult(status="no_signals", message=NO_SIGNALS, items=[])
    return InsightsResult(status="ready", message=None, items=items[:MAX_INSIGHTS])
