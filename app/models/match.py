from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Match(Base):
    """Завершённый матч CS2 игрока - кэш данных FACEIT."""

    __tablename__ = "matches"
    __table_args__ = (
        # Один матч FACEIT не может попасть в историю игрока дважды (сбой S07 из ПР1)
        UniqueConstraint("player_id", "faceit_match_id", name="uq_matches_player_match"),
        Index("ix_matches_player_finished", "player_id", "finished_at"),
        CheckConstraint("kills IS NULL OR kills >= 0", name="kills_non_negative"),
        CheckConstraint("deaths IS NULL OR deaths >= 0", name="deaths_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    faceit_match_id: Mapped[str] = mapped_column(String(64))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    map: Mapped[str | None] = mapped_column(String(32))
    # NULL - результат неизвестен; такой матч не входит в знаменатель доли побед
    won: Mapped[bool | None] = mapped_column(Boolean)
    kills: Mapped[int | None] = mapped_column(Integer)
    deaths: Mapped[int | None] = mapped_column(Integer)
