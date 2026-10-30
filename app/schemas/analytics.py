from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel
from app.schemas.stats import MetricValue


class MatchBrief(ApiModel):
    faceit_match_id: str
    finished_at: datetime
    map: str | None
    won: bool | None
    kills: int | None
    deaths: int | None


class GroupOut(ApiModel):
    matches_count: int
    period_from: datetime
    period_to: datetime
    win_rate: MetricValue
    kd: MetricValue
    match_ids: list[str]


class MetricChange(ApiModel):
    change: float | None = Field(description="win_rate - в процентных пунктах, kd - числом")
    unit: Literal["pp", "ratio"]
    complete: bool = Field(
        description="Метрика известна во всех 20 матчах каждой группы; "
        "иначе значения показаны с фактическим покрытием, но вывод о динамике не делается"
    )


class CompareOut(ApiModel):
    player_id: int
    formula_version: str
    map: str | None
    status: Literal["ready", "insufficient_data"]
    message: str | None
    required: int = Field(description="Нужно матчей для сравнения (2 × 20)")
    available: int = Field(description="Подходящих матчей в загруженной истории")
    recent: GroupOut | None = Field(description="Последние 20 матчей")
    previous: GroupOut | None = Field(description="Предыдущие 20 матчей")
    win_rate: MetricChange | None
    kd: MetricChange | None


class MapStatsOut(ApiModel):
    map: str
    matches: int
    win_rate: MetricValue
    kd: MetricValue
    enough_data: bool = Field(description="Матчей с известным результатом не меньше порога")


class MapsOut(ApiModel):
    player_id: int
    matches_total: int
    min_matches: int
    unknown_map_matches: int = Field(description="Матчи без карты в разбивку не входят")
    items: list[MapStatsOut]


class InsightOut(ApiModel):
    rule_id: Literal["A01", "A02", "A03"]
    metric: Literal["win_rate", "kd"]
    map: str | None
    title: str = Field(description="Наблюдение со значениями")
    limitation: str = Field(description="Ограничение вывода")
    action: str = Field(description="Действие для самостоятельной работы")
    before: float | None = Field(description="Значение в предыдущей группе; null для A03")
    after: float | None
    change: float | None
    unit: Literal["pp", "ratio"]
    period_from: datetime
    period_to: datetime
    sample_size: int
    review_match_ids: list[str] = Field(description="Матчи, с которых начать разбор")
    evidence: list[MatchBrief] = Field(description="Исходные матчи основания")


class InsightsOut(ApiModel):
    player_id: int
    rules_version: str
    status: Literal["ready", "no_signals", "insufficient_data"]
    message: str | None
    items: list[InsightOut] = Field(max_length=3)
