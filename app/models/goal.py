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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

GOAL_METRICS = ("win_rate", "kd")
GOAL_STATUSES = ("active", "completed", "archived")
SNAPSHOT_KINDS = ("baseline", "followup")


class Goal(TimestampMixin, Base):
    """Цель игрока: выбранное действие, метрика и неизменяемая исходная выборка"""

    __tablename__ = "goals"
    __table_args__ = (
        CheckConstraint(f"metric IN {GOAL_METRICS}", name="metric_allowed"),
        CheckConstraint(f"status IN {GOAL_STATUSES}", name="status_allowed"),
        # Одновременно активна только одна цель пользователя (S11).
        Index(
            "uq_goals_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    metric: Mapped[str] = mapped_column(String(16))
    map: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    formula_version: Mapped[str] = mapped_column(String(16))

    # Итог исходной выборки без округления: значение = numerator / denominator
    # win_rate: победы / матчи с известным результатом; kd: убийства / смерти
    baseline_numerator: Mapped[int] = mapped_column(Integer)
    baseline_denominator: Mapped[int] = mapped_column(Integer)
    followup_numerator: Mapped[int | None] = mapped_column(Integer)
    followup_denominator: Mapped[int | None] = mapped_column(Integer)

    snapshot_matches: Mapped[list["GoalSnapshotMatch"]] = relationship(
        back_populates="goal",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="GoalSnapshotMatch.finished_at",
    )


class GoalSnapshotMatch(Base):
    """Копия матча в снимке цели. Не меняется при обновлении истории игрока"""

    __tablename__ = "goal_snapshot_matches"
    __table_args__ = (
        UniqueConstraint("goal_id", "kind", "faceit_match_id", name="uq_goal_snapshot_match"),
        CheckConstraint(f"kind IN {SNAPSHOT_KINDS}", name="kind_allowed"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    faceit_match_id: Mapped[str] = mapped_column(String(64))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    map: Mapped[str | None] = mapped_column(String(32))
    won: Mapped[bool | None] = mapped_column(Boolean)
    kills: Mapped[int | None] = mapped_column(Integer)
    deaths: Mapped[int | None] = mapped_column(Integer)

    goal: Mapped[Goal] = relationship(back_populates="snapshot_matches")
