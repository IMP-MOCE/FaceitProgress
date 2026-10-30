"""Сравнение выборок, статистика по картам и сводка (S07–S10, релиз R2 из ПР1)"""

from collections.abc import Sequence
from datetime import datetime
from fractions import Fraction

from sqlalchemy.orm import Session

from app.models import Player
from app.repositories import matches as matches_repo
from app.schemas.analytics import (
    CompareOut,
    GroupOut,
    InsightOut,
    InsightsOut,
    MapsOut,
    MapStatsOut,
    MatchBrief,
    MetricChange,
)
from app.services import metrics, rules
from app.services.stats import metric_value


def _group_out(group: rules.Group) -> GroupOut:
    return GroupOut(
        matches_count=len(group.matches),
        period_from=group.period_from,
        period_to=group.period_to,
        win_rate=metric_value("win_rate", metrics.win_rate(group.matches)),
        kd=metric_value("kd", metrics.kill_death(group.matches)),
        match_ids=[m.faceit_match_id for m in group.matches],
    )


def _change(split: rules.Split, metric: metrics.Metric) -> MetricChange:
    before = metrics.compute(metric, split.previous.matches)
    after = metrics.compute(metric, split.recent.matches)
    complete = split.recent.complete(metric) and split.previous.complete(metric)
    return MetricChange(
        change=metrics.rounded(metrics.change(before, after)),
        unit="pp" if metric == "win_rate" else "ratio",
        complete=complete,
    )


def compare(db: Session, player: Player, map_name: str | None) -> CompareOut:
    """Последние 20 матчей против предыдущих 20; фильтр карты - до разбиения (S07, крит. 4)"""
    required = 2 * rules.GROUP_SIZE
    recent, available = matches_repo.list_filtered(db, player.id, map_name=map_name, limit=required)
    split = rules.split_groups(recent)
    if split is None:
        context = f" на карте {map_name}" if map_name else ""
        return CompareOut(
            player_id=player.id,
            formula_version=metrics.FORMULA_VERSION,
            map=map_name,
            status="insufficient_data",
            message=(
                f"Для сравнения нужно {required} матчей{context}, доступно {available}. "
                "Обычный обзор остаётся доступен"
            ),
            required=required,
            available=available,
            recent=None,
            previous=None,
            win_rate=None,
            kd=None,
        )
    return CompareOut(
        player_id=player.id,
        formula_version=metrics.FORMULA_VERSION,
        map=map_name,
        status="ready",
        message=None,
        required=required,
        available=available,
        recent=_group_out(split.recent),
        previous=_group_out(split.previous),
        win_rate=_change(split, "win_rate"),
        kd=_change(split, "kd"),
    )


def maps(
    db: Session, player: Player, date_from: datetime | None, date_to: datetime | None
) -> MapsOut:
    history, total = matches_repo.list_filtered(db, player.id, date_from=date_from, date_to=date_to)
    summaries = rules.by_map(history)
    return MapsOut(
        player_id=player.id,
        matches_total=total,
        min_matches=rules.MAP_MIN_MATCHES,
        unknown_map_matches=sum(1 for m in history if not m.map),
        items=[
            MapStatsOut(
                map=s.map,
                matches=len(s.matches),
                win_rate=metric_value("win_rate", metrics.win_rate(s.matches)),
                kd=metric_value("kd", metrics.kill_death(s.matches)),
                enough_data=s.enough_data,
            )
            for s in summaries
        ],
    )


def _as_float(value: Fraction | None) -> float | None:
    return None if value is None else metrics.rounded(float(value))


def _brief(source: Sequence[rules.RuleMatch]) -> list[MatchBrief]:
    return [
        MatchBrief(
            faceit_match_id=m.faceit_match_id,
            finished_at=m.finished_at,
            map=m.map,
            won=m.won,
            kills=m.kills,
            deaths=m.deaths,
        )
        for m in source
    ]


def _insight_out(insight: rules.Insight) -> InsightOut:
    change = None
    if insight.before is not None and insight.after is not None:
        change = metrics.rounded(float(insight.after - insight.before))
    return InsightOut(
        rule_id=insight.rule_id,
        metric=insight.metric,
        map=insight.map,
        title=insight.title,
        limitation=insight.limitation,
        action=insight.action,
        before=_as_float(insight.before),
        after=_as_float(insight.after),
        change=change,
        unit="pp" if insight.metric == "win_rate" else "ratio",
        period_from=insight.period_from,
        period_to=insight.period_to,
        sample_size=insight.sample_size,
        review_match_ids=list(insight.review_match_ids),
        evidence=_brief(insight.evidence),
    )


def insights(db: Session, player: Player) -> InsightsOut:
    """Не более трёх наблюдений по каталогу правил; без сигнала - честное сообщение"""
    history, _ = matches_repo.list_filtered(db, player.id)
    result = rules.evaluate(history)
    return InsightsOut(
        player_id=player.id,
        rules_version=rules.RULES_VERSION,
        status=result.status,
        message=result.message,
        items=[_insight_out(i) for i in result.items],
    )
