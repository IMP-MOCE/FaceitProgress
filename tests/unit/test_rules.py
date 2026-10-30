"""Сравнение 20/20 и правила A01–A03 на контрольных примерах ПР1 (раздел 2.1)"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from itertools import count

import pytest

from app.services import rules

_ids = count()
START = datetime(2026, 10, 20, 18, 0, tzinfo=UTC)


@dataclass
class M:
    won: bool | None = True
    kills: int | None = 12
    deaths: int | None = 10
    map: str | None = "de_mirage"
    finished_at: datetime = START
    faceit_match_id: str = field(default_factory=lambda: f"m-{next(_ids)}")


def timeline(*groups: list[M]) -> list[M]:
    """Склеивает группы от новых к старым и проставляет убывающее время"""
    matches = [m for group in groups for m in group]
    for index, match in enumerate(matches):
        match.finished_at = START - timedelta(hours=9 * index)
    return matches


def results(wins: int, losses: int, map: str = "de_mirage") -> list[M]:
    return [M(won=True, map=map) for _ in range(wins)] + [
        M(won=False, map=map) for _ in range(losses)
    ]


def kd_group(kills: int, deaths: int, size: int = 20) -> list[M]:
    """Группа из size матчей с суммами kills/deaths (остаток - в первом матче)"""
    group = [M(kills=kills // size, deaths=deaths // size) for _ in range(size)]
    group[0].kills = kills - (kills // size) * (size - 1)
    group[0].deaths = deaths - (deaths // size) * (size - 1)
    return group


# --- S07: разбиение на группы -------------------------------------------------


def test_split_needs_forty_matches() -> None:
    assert rules.split_groups(timeline(results(20, 19))) is None
    split = rules.split_groups(timeline(results(20, 20)))
    assert split is not None
    assert len(split.recent.matches) == len(split.previous.matches) == 20


def test_split_groups_do_not_overlap_even_with_duplicate_rows() -> None:
    # Сбой 10.2 из ПР1: повтор матча при загрузке не должен попасть в обе группы
    matches = timeline(results(25, 20))
    duplicated = [*matches[:20], matches[19], *matches[20:]]
    split = rules.split_groups(duplicated)
    assert split is not None
    recent = {m.faceit_match_id for m in split.recent.matches}
    previous = {m.faceit_match_id for m in split.previous.matches}
    assert recent.isdisjoint(previous)
    assert split.recent.period_from > split.previous.period_to


def test_group_completeness_per_metric() -> None:
    group = rules.Group(timeline(results(19, 0), [M(won=None)]))
    assert not group.complete("win_rate")
    assert group.complete("kd")


# --- A01: доля побед ------------------------------------------------------------


@pytest.mark.parametrize(
    ("previous_wins", "recent_wins", "fires"),
    [
        (12, 8, True),  # 60% → 40%: пример из каталога
        (12, 9, True),  # 60% → 45%: ровно на пороге 15 п.п. - срабатывает
        (12, 10, False),  # 60% → 50%: ниже порога
        (8, 12, False),  # рост не является сигналом
    ],
)
def test_a01_threshold(previous_wins: int, recent_wins: int, fires: bool) -> None:
    matches = timeline(
        results(recent_wins, 20 - recent_wins), results(previous_wins, 20 - previous_wins)
    )
    split = rules.split_groups(matches)
    assert split is not None
    insight = rules.rule_a01(split)
    assert (insight is not None) is fires
    if insight:
        assert insight.before == Fraction(previous_wins * 5)
        assert insight.after == Fraction(recent_wins * 5)
        assert insight.sample_size == 40
        assert len(insight.evidence) == 40


def test_a01_text_and_review_matches() -> None:
    matches = timeline(results(8, 12), results(12, 8))
    split = rules.split_groups(matches)
    assert split is not None
    insight = rules.rule_a01(split)
    assert insight is not None
    assert insight.title == ("Доля побед снизилась с 60% до 40% в двух сравниваемых выборках")
    # Три последних поражения из последней группы
    losses = [m.faceit_match_id for m in split.recent.matches if m.won is False]
    assert list(insight.review_match_ids) == losses[:3]


def test_a01_skips_incomplete_group() -> None:
    recent = [*results(8, 11), M(won=None)]
    split = rules.split_groups(timeline(recent, results(12, 8)))
    assert split is not None
    assert rules.rule_a01(split) is None


# --- A02: K/D -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("previous", "recent", "fires"),
    [
        ((240, 200), (200, 200), True),  # 1,20 → 1,00: пример из каталога
        ((240, 200), (210, 200), True),  # 1,20 → 1,05: ровно 0,15
        ((240, 200), (220, 200), False),  # 1,20 → 1,10
    ],
)
def test_a02_threshold(previous: tuple[int, int], recent: tuple[int, int], fires: bool) -> None:
    split = rules.split_groups(timeline(kd_group(*recent), kd_group(*previous)))
    assert split is not None
    insight = rules.rule_a02(split)
    assert (insight is not None) is fires


def test_a02_text() -> None:
    split = rules.split_groups(timeline(kd_group(200, 200), kd_group(240, 200)))
    assert split is not None
    insight = rules.rule_a02(split)
    assert insight is not None
    assert insight.title.startswith("K/D снизился с 1,20 до 1,00")
    assert len(insight.review_match_ids) == 3


def test_a02_requires_complete_fields_and_nonzero_deaths() -> None:
    recent = kd_group(200, 200)
    recent[5].kills = None
    split = rules.split_groups(timeline(recent, kd_group(240, 200)))
    assert split is not None
    assert rules.rule_a02(split) is None

    zero_deaths = [M(kills=10, deaths=0) for _ in range(20)]
    split = rules.split_groups(timeline(kd_group(100, 200), zero_deaths))
    assert split is not None
    assert rules.rule_a02(split) is None


# --- A03: карта -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("wins", "losses", "fires"),
    [
        (4, 8, True),  # 4 из 12 = 33,3%: пример из каталога
        (4, 6, True),  # 4 из 10 = 40%: ровно на пороге
        (3, 6, False),  # 3 из 9: доля низкая, но матчей меньше 10
        (5, 5, False),  # 50%
    ],
)
def test_a03_threshold(wins: int, losses: int, fires: bool) -> None:
    matches = timeline(results(wins, losses, map="de_nuke"))
    insight = rules.rule_a03(rules.by_map(matches))
    assert (insight is not None) is fires
    if insight:
        assert insight.map == "de_nuke"
        assert insight.sample_size == wins + losses


def test_a03_text_uses_russian_plurals() -> None:
    insight = rules.rule_a03(rules.by_map(timeline(results(4, 8, map="de_nuke"))))
    assert insight is not None
    assert insight.title == "На карте de_nuke в выбранной выборке 4 победы из 12 матчей"
    single = rules.rule_a03(rules.by_map(timeline(results(1, 20, map="de_nuke"))))
    assert single is not None
    assert single.title.endswith("1 победа из 21 матча")


def test_a03_tie_breaks() -> None:
    # Одинаковая доля 30%: выигрывает карта с бóльшим числом матчей
    matches = timeline(
        results(3, 7, map="de_anubis"),
        results(6, 14, map="de_train"),
        results(3, 7, map="de_ancient"),
    )
    insight = rules.rule_a03(rules.by_map(matches))
    assert insight is not None and insight.map == "de_train"
    # При полном равенстве - по названию карты
    matches = timeline(results(3, 7, map="de_nuke"), results(3, 7, map="de_ancient"))
    insight = rules.rule_a03(rules.by_map(matches))
    assert insight is not None and insight.map == "de_ancient"


def test_a03_picks_lowest_win_rate() -> None:
    matches = timeline(results(4, 6, map="de_nuke"), results(2, 8, map="de_inferno"))
    insight = rules.rule_a03(rules.by_map(matches))
    assert insight is not None and insight.map == "de_inferno"


def test_unknown_results_do_not_count_toward_map_minimum() -> None:
    matches = timeline(results(3, 6, map="de_nuke"), [M(won=None, map="de_nuke") for _ in range(3)])
    summary = rules.by_map(matches)[0]
    assert (len(summary.matches), summary.known) == (12, 9)
    assert rules.rule_a03([summary]) is None


# --- S09: сводка ----------------------------------------------------------------


def test_evaluate_orders_a01_a02_a03() -> None:
    recent = results(8, 12, map="de_nuke")
    for match, kd in zip(recent, kd_group(200, 200), strict=True):
        match.kills, match.deaths = kd.kills, kd.deaths
    previous = results(12, 8, map="de_mirage")
    for match, kd in zip(previous, kd_group(240, 200), strict=True):
        match.kills, match.deaths = kd.kills, kd.deaths
    result = rules.evaluate(timeline(recent, previous))
    assert result.status == "ready"
    assert [i.rule_id for i in result.items] == ["A01", "A02", "A03"]


def test_evaluate_is_deterministic() -> None:
    matches = timeline(results(8, 12), results(12, 8))
    assert rules.evaluate(matches) == rules.evaluate(list(matches))


def test_evaluate_without_signals() -> None:
    result = rules.evaluate(timeline(results(10, 10), results(10, 10)))
    assert result.status == "no_signals"
    assert result.message == rules.NO_SIGNALS
    assert result.items == []


def test_evaluate_with_too_few_matches() -> None:
    result = rules.evaluate(timeline(results(3, 5)))
    assert result.status == "insufficient_data"
    assert result.message == "Недостаточно данных для сводки"


def test_map_rule_works_without_forty_matches() -> None:
    result = rules.evaluate(timeline(results(2, 10, map="de_nuke")))
    assert [i.rule_id for i in result.items] == ["A03"]


def test_formatting() -> None:
    assert rules.format_pct(Fraction(60)) == "60%"
    assert rules.format_pct(Fraction(100, 3)) == "33,3%"
    assert rules.format_kd(Fraction(6, 5)) == "1,20"
