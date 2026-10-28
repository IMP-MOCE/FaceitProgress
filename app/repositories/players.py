from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Player


def get_owned(db: Session, user_id: int, player_id: int) -> Player | None:
    # Фильтр по владельцу в самом запросе: чужой игрок неотличим от несуществующего
    return db.scalar(select(Player).where(Player.id == player_id, Player.user_id == user_id))


def get_by_faceit_id(db: Session, user_id: int, faceit_id: str) -> Player | None:
    return db.scalar(select(Player).where(Player.user_id == user_id, Player.faceit_id == faceit_id))


def list_owned(db: Session, user_id: int, limit: int, offset: int) -> tuple[list[Player], int]:
    query = select(Player).where(Player.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Player.id).limit(limit).offset(offset)).all()
    return list(items), total
