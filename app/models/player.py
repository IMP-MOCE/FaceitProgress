from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Player(TimestampMixin, Base):
    """FACEIT-профиль, который отслеживает пользователь сервиса"""

    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("user_id", "faceit_id", name="uq_players_user_faceit"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    faceit_id: Mapped[str] = mapped_column(String(64))
    nickname: Mapped[str] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(8))
    faceit_url: Mapped[str | None] = mapped_column(String(255))
    # Текущий ELO и уровень есть не у всех профилей (нет CS2) - тогда NULL, а не 0.
    elo: Mapped[int | None] = mapped_column(Integer)
    skill_level: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(500))

    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Покрытие истории: все матчи, завершённые не раньше coverage_from, есть в БД
    # history_complete=True - загружена вся история игрока от первого матча
    coverage_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    history_complete: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    def covers(self, moment: datetime) -> bool:
        """Есть ли в БД все матчи, завершённые после moment."""
        if self.history_complete:
            return True
        return self.coverage_from is not None and self.coverage_from <= moment
