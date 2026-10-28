from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbSession, Faceit, OwnedPlayer
from app.core.errors import InvalidInput
from app.repositories import matches as matches_repo
from app.repositories import players as players_repo
from app.schemas.common import MAP_PATTERN, problem_responses
from app.schemas.players import PlayerCreate, PlayerOut, PlayerPage, PlayerUpdate
from app.schemas.stats import MatchOut, MatchPage, StatsOut
from app.services import players as players_service
from app.services import stats as stats_service

router = APIRouter(prefix="/players", tags=["players"])

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]
MapFilter = Annotated[str | None, Query(alias="map", pattern=MAP_PATTERN)]
DateFrom = Annotated[datetime | None, Query(description="Включительно, ISO 8601 с поясом")]
DateTo = Annotated[datetime | None, Query(description="Включительно, ISO 8601 с поясом")]


def _check_period(date_from: datetime | None, date_to: datetime | None) -> None:
    for value in (date_from, date_to):
        if value is not None and value.tzinfo is None:
            raise InvalidInput("Дата должна содержать часовой пояс, например 2026-10-01T00:00:00Z")
    if date_from and date_to and date_from > date_to:
        raise InvalidInput("date_from не может быть позже date_to")


@router.get("", summary="Отслеживаемые игроки", responses=problem_responses(401))
def list_players(
    user: CurrentUser, db: DbSession, limit: Limit = 20, offset: Offset = 0
) -> PlayerPage:
    items, total = players_repo.list_owned(db, user.id, limit, offset)
    return PlayerPage(
        items=[PlayerOut.model_validate(p) for p in items], total=total, limit=limit, offset=offset
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Найти игрока на FACEIT по нику или ссылке и загрузить историю",
    responses=problem_responses(401, 404, 409, 422, 503),
)
def create_player(
    body: PlayerCreate, user: CurrentUser, db: DbSession, faceit: Faceit, response: Response
) -> PlayerOut:
    player = players_service.create(db, faceit, user, body.query, body.note)
    response.headers["Location"] = f"/api/v1/players/{player.id}"
    return PlayerOut.model_validate(player)


@router.get("/{player_id}", summary="Игрок", responses=problem_responses(401, 404))
def get_player(player: OwnedPlayer) -> PlayerOut:
    return PlayerOut.model_validate(player)


@router.patch(
    "/{player_id}", summary="Изменить заметку", responses=problem_responses(401, 404, 422)
)
def update_player(body: PlayerUpdate, player: OwnedPlayer, db: DbSession) -> PlayerOut:
    if "note" in body.model_fields_set:
        players_service.update_note(db, player, body.note)
    return PlayerOut.model_validate(player)


@router.delete(
    "/{player_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Перестать отслеживать игрока (удаляет его матчи и цели)",
    responses=problem_responses(401, 404),
)
def delete_player(player: OwnedPlayer, db: DbSession) -> Response:
    players_service.delete(db, player)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{player_id}/sync",
    summary="Обновить профиль и историю матчей из FACEIT",
    responses=problem_responses(401, 404, 503),
)
def sync_player(player: OwnedPlayer, db: DbSession, faceit: Faceit) -> PlayerOut:
    return PlayerOut.model_validate(players_service.sync(db, faceit, player))


@router.get(
    "/{player_id}/matches",
    summary="История матчей с фильтрами по карте и периоду",
    responses=problem_responses(401, 404, 422),
)
def list_matches(
    player: OwnedPlayer,
    db: DbSession,
    map_name: MapFilter = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> MatchPage:
    _check_period(date_from, date_to)
    items, total = matches_repo.list_filtered(
        db,
        player.id,
        map_name=map_name,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return MatchPage(
        items=[MatchOut.model_validate(m) for m in items],
        total=total,
        limit=limit,
        offset=offset,
        coverage=stats_service.coverage(player),
        partial_coverage=stats_service.is_partial(player, date_from, date_to),
    )


@router.get(
    "/{player_id}/stats",
    summary="Обзор последних 20 матчей: доля побед и K/D с размером выборки",
    responses=problem_responses(401, 404, 422),
)
def player_stats(
    player: OwnedPlayer,
    db: DbSession,
    map_name: MapFilter = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
) -> StatsOut:
    _check_period(date_from, date_to)
    return stats_service.overview(db, player, map_name, date_from, date_to)
