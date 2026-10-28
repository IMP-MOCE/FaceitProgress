from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Goal


def get_owned(
    db: Session, user_id: int, goal_id: int, *, with_matches: bool = False
) -> Goal | None:
    query = select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    if with_matches:
        query = query.options(selectinload(Goal.snapshot_matches))
    return db.scalar(query)


def get_active(db: Session, user_id: int) -> Goal | None:
    return db.scalar(select(Goal).where(Goal.user_id == user_id, Goal.status == "active"))


def list_owned(
    db: Session, user_id: int, status: str | None, limit: int, offset: int
) -> tuple[list[Goal], int]:
    query = select(Goal).where(Goal.user_id == user_id)
    if status:
        query = query.where(Goal.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Goal.id.desc()).limit(limit).offset(offset)).all()
    return list(items), total
