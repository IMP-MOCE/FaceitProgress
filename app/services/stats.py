from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Player
from app.repositories import matches
from app.schemas.players import CoverageOut
from app.schemas.stats import MetricValue, StatsFilters, StatsOut
from app.services import metrics


def metric_value(metric: metrics.Metric, ratio: metrics.Ratio) -> MetricValue:
    note = None
    if ratio.sample_size == 0:
        note = "Нет матчей с данными для этой метрики"
    elif ratio.value is None and metric == "kd":
        note = "Смертей 0 - K/D не определён, показаны исходные числа"
    return MetricValue(
        value=metrics.rounded(ratio.value),
        numerator=ratio.numerator,
        denominator=ratio.denominator,
        sample_size=ratio.sample_size,
        note=note,
    )


def coverage(player: Player) -> CoverageOut:
    return CoverageOut(history_complete=player.history_complete, coverage_from=player.coverage_from)


def is_partial(player: Player, date_from: datetime | None, date_to: datetime | None) -> bool:
    """Запрошенный период начинается раньше, чем гарантированно загруженная история"""
    if date_from is None and date_to is None:
        return False
    if date_from is None:
        return not player.history_complete
    return not player.covers(date_from)


def overview(
    db: Session,
    player: Player,
    map_name: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> StatsOut:
    recent, available = matches.list_filtered(
        db,
        player.id,
        map_name=map_name,
        date_from=date_from,
        date_to=date_to,
        limit=metrics.OVERVIEW_SIZE,
    )
    filtered = any(v is not None for v in (map_name, date_from, date_to))
    message = None
    if available == 0:
        message = (
            "Под выбранные фильтры не подошёл ни один матч"
            if filtered
            else "У игрока нет завершённых матчей CS2 - статистики пока нет"
        )
    elif len(recent) < metrics.OVERVIEW_SIZE:
        message = f"Доступно {len(recent)} из {metrics.OVERVIEW_SIZE} матчей обзора"

    return StatsOut(
        player_id=player.id,
        formula_version=metrics.FORMULA_VERSION,
        filters=StatsFilters(map=map_name, date_from=date_from, date_to=date_to),
        matches_count=len(recent),
        matches_available=available,
        period_from=recent[-1].finished_at if recent else None,
        period_to=recent[0].finished_at if recent else None,
        win_rate=metric_value("win_rate", metrics.win_rate(recent)),
        kd=metric_value("kd", metrics.kill_death(recent)),
        synced_at=player.synced_at,
        coverage=coverage(player),
        partial_coverage=is_partial(player, date_from, date_to),
        message=message,
    )
