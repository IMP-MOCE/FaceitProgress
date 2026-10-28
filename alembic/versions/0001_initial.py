"""Начальная схема: пользователи, игроки, матчи, цели и снимки целей

Revision ID: 0001
Revises:
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("faceit_id", sa.String(64), nullable=False),
        sa.Column("nickname", sa.String(64), nullable=False),
        sa.Column("country", sa.String(8), nullable=True),
        sa.Column("faceit_url", sa.String(255), nullable=True),
        sa.Column("elo", sa.Integer(), nullable=True),
        sa.Column("skill_level", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("synced_at", TS, nullable=True),
        sa.Column("coverage_from", TS, nullable=True),
        sa.Column("history_complete", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_players"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_players_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", "faceit_id", name="uq_players_user_faceit"),
    )
    op.create_index("ix_players_user_id", "players", ["user_id"])

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("faceit_match_id", sa.String(64), nullable=False),
        sa.Column("finished_at", TS, nullable=False),
        sa.Column("map", sa.String(32), nullable=True),
        sa.Column("won", sa.Boolean(), nullable=True),
        sa.Column("kills", sa.Integer(), nullable=True),
        sa.Column("deaths", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_matches"),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name="fk_matches_player_id_players", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("player_id", "faceit_match_id", name="uq_matches_player_match"),
        sa.CheckConstraint("kills IS NULL OR kills >= 0", name="ck_matches_kills_non_negative"),
        sa.CheckConstraint("deaths IS NULL OR deaths >= 0", name="ck_matches_deaths_non_negative"),
    )
    op.create_index("ix_matches_player_finished", "matches", ["player_id", "finished_at"])

    op.create_table(
        "goals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(16), nullable=False),
        sa.Column("map", sa.String(32), nullable=True),
        sa.Column("action", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("started_at", TS, nullable=False),
        sa.Column("formula_version", sa.String(16), nullable=False),
        sa.Column("baseline_numerator", sa.Integer(), nullable=False),
        sa.Column("baseline_denominator", sa.Integer(), nullable=False),
        sa.Column("followup_numerator", sa.Integer(), nullable=True),
        sa.Column("followup_denominator", sa.Integer(), nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_goals"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_goals_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name="fk_goals_player_id_players", ondelete="CASCADE"
        ),
        sa.CheckConstraint("metric IN ('win_rate', 'kd')", name="ck_goals_metric_allowed"),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'archived')", name="ck_goals_status_allowed"
        ),
    )
    op.create_index("ix_goals_user_id", "goals", ["user_id"])
    op.create_index("ix_goals_player_id", "goals", ["player_id"])
    op.create_index(
        "uq_goals_one_active_per_user",
        "goals",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "goal_snapshot_matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("faceit_match_id", sa.String(64), nullable=False),
        sa.Column("finished_at", TS, nullable=False),
        sa.Column("map", sa.String(32), nullable=True),
        sa.Column("won", sa.Boolean(), nullable=True),
        sa.Column("kills", sa.Integer(), nullable=True),
        sa.Column("deaths", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_goal_snapshot_matches"),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["goals.id"],
            name="fk_goal_snapshot_matches_goal_id_goals",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("goal_id", "kind", "faceit_match_id", name="uq_goal_snapshot_match"),
        sa.CheckConstraint(
            "kind IN ('baseline', 'followup')", name="ck_goal_snapshot_matches_kind_allowed"
        ),
    )
    op.create_index("ix_goal_snapshot_matches_goal_id", "goal_snapshot_matches", ["goal_id"])


def downgrade() -> None:
    op.drop_table("goal_snapshot_matches")
    op.drop_table("goals")
    op.drop_table("matches")
    op.drop_table("players")
    op.drop_table("users")
