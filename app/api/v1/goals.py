from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core.errors import NotFound
from app.models import Goal, User
from app.repositories import goals as goals_repo
from app.repositories import players as players_repo
from app.schemas.common import problem_responses
from app.schemas.goals import (
    GoalCreate,
    GoalDetail,
    GoalPage,
    GoalProgressOut,
    GoalUpdate,
)
from app.services import goals as goals_service

router = APIRouter(prefix="/goals", tags=["goals"])

GoalId = Annotated[int, Path(gt=0)]


def _owned_goal(db: DbSession, user: User, goal_id: int) -> Goal:
    goal = goals_repo.get_owned(db, user.id, goal_id, with_matches=True)
    if goal is None:
        raise NotFound("Цель не найдена")
    return goal


@router.get("", summary="Цели пользователя", responses=problem_responses(401, 422))
def list_goals(
    user: CurrentUser,
    db: DbSession,
    status_filter: Annotated[
        Literal["active", "completed", "archived"] | None, Query(alias="status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GoalPage:
    items, total = goals_repo.list_owned(db, user.id, status_filter, limit, offset)
    return GoalPage(
        items=[goals_service.to_out(g) for g in items], total=total, limit=limit, offset=offset
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Поставить цель: сохраняет снимок 20 последних матчей",
    responses=problem_responses(401, 404, 409, 422),
)
def create_goal(
    body: GoalCreate, user: CurrentUser, db: DbSession, response: Response
) -> GoalDetail:
    player = players_repo.get_owned(db, user.id, body.player_id)
    if player is None:
        raise NotFound("Игрок не найден")
    goal = goals_service.create(
        db,
        user,
        player,
        metric=body.metric,
        map_name=body.map,
        action=body.action,
        replace_active=body.replace_active,
    )
    response.headers["Location"] = f"/api/v1/goals/{goal.id}"
    return goals_service.to_detail(goal)


@router.get(
    "/{goal_id}",
    summary="Цель с исходной выборкой",
    responses=problem_responses(401, 404),
)
def get_goal(goal_id: GoalId, user: CurrentUser, db: DbSession) -> GoalDetail:
    return goals_service.to_detail(_owned_goal(db, user, goal_id))


@router.patch(
    "/{goal_id}",
    summary="Изменить действие или закрыть цель",
    responses=problem_responses(401, 404, 409, 422),
)
def update_goal(goal_id: GoalId, body: GoalUpdate, user: CurrentUser, db: DbSession) -> GoalDetail:
    goal = _owned_goal(db, user, goal_id)
    goals_service.update(db, goal, body.action, body.status)
    return goals_service.to_detail(goal)


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить цель вместе со снимками",
    responses=problem_responses(401, 404),
)
def delete_goal(goal_id: GoalId, user: CurrentUser, db: DbSession) -> Response:
    goals_service.delete(db, _owned_goal(db, user, goal_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{goal_id}/progress",
    summary="Сравнить исходную выборку с первыми 20 матчами после постановки цели",
    description=(
        "Когда набраны 20 матчей с полными данными, новая выборка сохраняется как снимок; "
        "повторные запросы возвращают то же сравнение (идемпотентно)."
    ),
    responses=problem_responses(401, 404),
)
def goal_progress(goal_id: GoalId, user: CurrentUser, db: DbSession) -> GoalProgressOut:
    goal = _owned_goal(db, user, goal_id)
    player = players_repo.get_owned(db, user.id, goal.player_id)
    if player is None:  # pragma: no cover — цель удаляется каскадом вместе с игроком
        raise NotFound("Игрок не найден")
    return goals_service.progress(db, goal, player)
