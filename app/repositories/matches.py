from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.clients.faceit import FaceitMatch
from app.models import Match


def upsert_many(db: Session, player_id: int, matches: Sequence[FaceitMatch]) -> None:
    """Добавляет матчи; уже известные обновляет. Дубли исключены ограничением БД"""
    if not matches:
        return
    rows = [
        {
            "player_id": player_id,
            "faceit_match_id": m.match_id,
            "finished_at": m.finished_at,
            "map": m.map,
            "won": m.won,
            "kills": m.kills,
            "deaths": m.deaths,
        }
        for m in {m.match_id: m for m in matches}.values()
    ]
    stmt = insert(Match).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_matches_player_match",
        set_={col: stmt.excluded[col] for col in ("finished_at", "map", "won", "kills", "deaths")},
    )
    db.execute(stmt)


def latest_finished_at(db: Session, player_id: int) -> datetime | None:
    return db.scalar(select(func.max(Match.finished_at)).where(Match.player_id == player_id))


def _filtered(
    player_id: int,
    map_name: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> Select[Match]:
    query = select(Match).where(Match.player_id == player_id)
    if map_name:
        query = query.where(Match.map == map_name)
    # Границы периода включены (S04, критерий 2)
    if date_from:
        query = query.where(Match.finished_at >= date_from)
    if date_to:
        query = query.where(Match.finished_at <= date_to)
    return query


def list_filtered(
    db: Session,
    player_id: int,
    *,
    map_name: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[Match], int]:
    """Матчи от новых к старым и общее число подходящих под фильтр"""
    query = _filtered(player_id, map_name, date_from, date_to)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    ordered = query.order_by(Match.finished_at.desc(), Match.id.desc()).offset(offset)
    if limit is not None:
        ordered = ordered.limit(limit)
    return list(db.scalars(ordered).all()), total


def before(
    db: Session, player_id: int, moment: datetime, map_name: str | None, limit: int
) -> list[Match]:
    """Последние матчи, завершённые не позже moment (исходная выборка цели)."""
    query = _filtered(player_id, map_name, None, moment)
    return list(db.scalars(query.order_by(Match.finished_at.desc()).limit(limit)).all())


def after(
    db: Session, player_id: int, moment: datetime, map_name: str | None, limit: int
) -> list[Match]:
    """Первые матчи, завершённые строго после moment (новая выборка цели)"""
    query = _filtered(player_id, map_name, None, None).where(Match.finished_at > moment)
    return list(db.scalars(query.order_by(Match.finished_at.asc()).limit(limit)).all())
