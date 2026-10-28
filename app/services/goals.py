"""Цели игрока и проверка динамики (S11, S12; ПР1, раздел 2.2)"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, InsufficientData
from app.models import Goal, GoalSnapshotMatch, Match, Player, User
from app.repositories import goals, matches
from app.schemas.goals import (
    GoalDetail,
    GoalOut,
    GoalProgressOut,
    ProgressStatus,
    SnapshotMatchOut,
)
from app.services import metrics
from app.services.stats import metric_value

ACTIVE_EXISTS = "У пользователя уже есть активная цель. Закройте её или передайте replace_active"
# Наблюдение, а не вывод о причине: изменение не доказывает эффект тренировки (S12, критерий 7)
READY_MESSAGE = (
    "Сравнение готово. Изменение показателя - наблюдение, а не доказательство эффекта цели"
)


def _snapshot(kind: str, source: Sequence[Match]) -> list[GoalSnapshotMatch]:
    return [
        GoalSnapshotMatch(
            kind=kind,
            faceit_match_id=m.faceit_match_id,
            finished_at=m.finished_at,
            map=m.map,
            won=m.won,
            kills=m.kills,
            deaths=m.deaths,
        )
        for m in source
    ]


def _ratio(goal: Goal, kind: str) -> metrics.Ratio | None:
    if kind == "baseline":
        numerator, denominator = goal.baseline_numerator, goal.baseline_denominator
    else:
        if goal.followup_numerator is None or goal.followup_denominator is None:
            return None
        numerator, denominator = goal.followup_numerator, goal.followup_denominator
    return metrics.Ratio(
        numerator=numerator,
        denominator=denominator,
        sample_size=metrics.GOAL_SAMPLE_SIZE,
        scale=100 if goal.metric == "win_rate" else 1,
    )


def to_out(goal: Goal) -> GoalOut:
    baseline = cast(metrics.Ratio, _ratio(goal, "baseline"))
    return GoalOut.model_validate(
        {
            **{key: getattr(goal, key) for key in GoalOut.model_fields if key != "baseline"},
            "baseline": metric_value(cast(metrics.Metric, goal.metric), baseline),
        }
    )


def to_detail(goal: Goal) -> GoalDetail:
    baseline_matches = [
        SnapshotMatchOut.model_validate(s) for s in goal.snapshot_matches if s.kind == "baseline"
    ]
    return GoalDetail(**to_out(goal).model_dump(), baseline_matches=baseline_matches)


def create(
    db: Session,
    user: User,
    player: Player,
    *,
    metric: metrics.Metric,
    map_name: str | None,
    action: str,
    replace_active: bool,
    started_at: datetime | None = None,
) -> Goal:
    """Сохраняет цель и неизменяемый снимок 20 последних матчей в выбранном контексте

    started_at задаётся только скриптом подготовки демо-данных; API всегда берёт текущее время
    """
    started_at = started_at or datetime.now(UTC)
    active = goals.get_active(db, user.id)
    if active is not None and not replace_active:
        raise Conflict(ACTIVE_EXISTS, extra={"active_goal_id": active.id})

    baseline = matches.before(db, player.id, started_at, map_name, metrics.GOAL_SAMPLE_SIZE)
    if len(baseline) < metrics.GOAL_SAMPLE_SIZE:
        context = f" на карте {map_name}" if map_name else ""
        raise InsufficientData(
            f"Для цели нужно {metrics.GOAL_SAMPLE_SIZE} завершённых матчей{context}, "
            f"доступно {len(baseline)}",
            extra={"required": metrics.GOAL_SAMPLE_SIZE, "available": len(baseline)},
        )
    missing = [m.faceit_match_id for m in baseline if not metrics.has_metric_data(m, metric)]
    if missing:
        raise InsufficientData(
            "В исходных матчах нет данных для выбранной метрики",
            extra={"missing_match_ids": missing},
        )
    ratio = metrics.compute(metric, baseline)
    if ratio.value is None:
        raise InsufficientData("Метрика не определена: в исходной выборке 0 смертей")

    if active is not None:
        active.status = "archived"
        db.flush()

    goal = Goal(
        user_id=user.id,
        player_id=player.id,
        metric=metric,
        map=map_name,
        action=action,
        status="active",
        started_at=started_at,
        formula_version=metrics.FORMULA_VERSION,
        baseline_numerator=ratio.numerator,
        baseline_denominator=ratio.denominator,
    )
    goal.snapshot_matches = _snapshot("baseline", baseline)
    db.add(goal)
    try:
        db.commit()
    except IntegrityError as exc:
        # Две параллельные цели: частичный уникальный индекс пропустил только одну
        db.rollback()
        raise Conflict(ACTIVE_EXISTS) from exc
    return goal


def update(db: Session, goal: Goal, action: str | None, status: str | None) -> Goal:
    if status is not None:
        if goal.status != "active":
            raise Conflict("Закрыть можно только активную цель")
        goal.status = status
    if action is not None:
        goal.action = action
    db.commit()
    return goal


def delete(db: Session, goal: Goal) -> None:
    db.delete(goal)
    db.commit()


def progress(db: Session, goal: Goal, player: Player) -> GoalProgressOut:
    metric = cast(metrics.Metric, goal.metric)
    baseline = cast(metrics.Ratio, _ratio(goal, "baseline"))
    required = metrics.GOAL_SAMPLE_SIZE

    def result(
        status: ProgressStatus,
        message: str,
        collected: int,
        followup: Sequence[Match | GoalSnapshotMatch] = (),
        missing: Sequence[str] = (),
    ) -> GoalProgressOut:
        followup_ratio = _ratio(goal, "followup") if status == "ready" else None
        return GoalProgressOut(
            goal_id=goal.id,
            status=status,
            message=message,
            required=required,
            collected=collected,
            baseline=metric_value(metric, baseline),
            followup=None if followup_ratio is None else metric_value(metric, followup_ratio),
            change=(
                None
                if followup_ratio is None
                else metrics.rounded(metrics.change(baseline, followup_ratio))
            ),
            change_unit="pp" if metric == "win_rate" else "ratio",
            followup_matches=[SnapshotMatchOut.model_validate(m) for m in followup],
            missing_match_ids=list(missing),
        )

    saved = [s for s in goal.snapshot_matches if s.kind == "followup"]
    if saved:
        # Готовое сравнение не меняется при дальнейших обновлениях истории
        return result("ready", READY_MESSAGE, len(saved), saved)

    if not player.covers(goal.started_at):
        return result(
            "unrecoverable",
            "Невозможно восстановить первые матчи после постановки цели. "
            "Сохранённая исходная выборка доступна; цель можно заменить с новой исходной точкой",
            0,
        )

    candidates = matches.after(db, player.id, goal.started_at, goal.map, required)
    if len(candidates) < required:
        return result(
            "collecting",
            f"Сыграно {len(candidates)} из {required} матчей после постановки цели",
            len(candidates),
            candidates,
        )

    missing = [m.faceit_match_id for m in candidates if not metrics.has_metric_data(m, metric)]
    if missing:
        # Более поздние матчи не подставляются вместо неполных (ПР1, 2.2).
        return result(
            "incomplete_data",
            "В первых матчах после постановки цели нет данных метрики - сравнение недоступно",
            len(candidates),
            candidates,
            missing,
        )

    ratio = metrics.compute(metric, candidates)
    goal.followup_numerator = ratio.numerator
    goal.followup_denominator = ratio.denominator
    goal.snapshot_matches.extend(_snapshot("followup", candidates))
    db.commit()
    return result("ready", READY_MESSAGE, len(candidates), candidates)
