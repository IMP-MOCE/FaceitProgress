from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import RevokedToken


def revoke(db: Session, jti: str, user_id: int, expires_at: datetime) -> None:
    # Повторный выход тем же токеном не ошибка
    stmt = insert(RevokedToken).values(jti=jti, user_id=user_id, expires_at=expires_at)
    db.execute(stmt.on_conflict_do_nothing(index_elements=["jti"]))


def is_revoked(db: Session, jti: str) -> bool:
    return db.get(RevokedToken, jti) is not None


def purge_expired(db: Session, now: datetime) -> None:
    db.execute(delete(RevokedToken).where(RevokedToken.expires_at < now))
