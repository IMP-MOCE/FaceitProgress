from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import MAP_PATTERN, ApiModel
from app.schemas.stats import MetricValue

MetricName = Literal["win_rate", "kd"]
ProgressStatus = Literal["collecting", "incomplete_data", "unrecoverable", "ready"]


class GoalCreate(ApiModel):
    player_id: int = Field(gt=0)
    metric: MetricName
    map: str | None = Field(default=None, pattern=MAP_PATTERN, examples=["de_mirage"])
    action: str = Field(
        min_length=3,
        max_length=500,
        examples=["Пересмотреть 3 поражения на de_mirage и выписать повторяющиеся ситуации"],
    )
    replace_active: bool = Field(
        default=False,
        description="Явная замена текущей активной цели: старая переводится в archived",
    )


class GoalUpdate(ApiModel):
    action: str | None = Field(default=None, min_length=3, max_length=500)
    status: Literal["completed", "archived"] | None = Field(
        default=None, description="Закрыть активную цель"
    )


class SnapshotMatchOut(ApiModel):
    faceit_match_id: str
    finished_at: datetime
    map: str | None
    won: bool | None
    kills: int | None
    deaths: int | None


class GoalOut(ApiModel):
    id: int
    player_id: int
    metric: MetricName
    map: str | None
    action: str
    status: Literal["active", "completed", "archived"]
    started_at: datetime
    formula_version: str
    baseline: MetricValue
    created_at: datetime
    updated_at: datetime


class GoalDetail(GoalOut):
    baseline_matches: list[SnapshotMatchOut]


class GoalPage(ApiModel):
    items: list[GoalOut]
    total: int
    limit: int
    offset: int


class GoalProgressOut(ApiModel):
    goal_id: int
    status: ProgressStatus
    message: str
    required: int
    collected: int
    baseline: MetricValue
    followup: MetricValue | None
    change: float | None = Field(description="Для win_rate — в процентных пунктах, для kd — числом")
    change_unit: Literal["pp", "ratio"]
    followup_matches: list[SnapshotMatchOut]
    missing_match_ids: list[str]
