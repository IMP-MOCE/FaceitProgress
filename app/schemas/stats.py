from datetime import datetime

from pydantic import Field

from app.schemas.common import ApiModel
from app.schemas.players import CoverageOut


class MatchOut(ApiModel):
    id: int
    faceit_match_id: str
    finished_at: datetime
    map: str | None
    won: bool | None = Field(description="null — результат неизвестен")
    kills: int | None
    deaths: int | None


class MatchPage(ApiModel):
    items: list[MatchOut]
    total: int
    limit: int
    offset: int
    coverage: CoverageOut
    partial_coverage: bool = Field(
        description="Запрошенный период выходит за пределы загруженной истории"
    )


class MetricValue(ApiModel):
    value: float | None = Field(description="Округлено до 2 знаков; null — не определено")
    numerator: int
    denominator: int
    sample_size: int = Field(description="Число матчей, по которым посчитана метрика")
    note: str | None = None


class StatsFilters(ApiModel):
    map: str | None
    date_from: datetime | None
    date_to: datetime | None


class StatsOut(ApiModel):
    player_id: int
    formula_version: str
    filters: StatsFilters
    matches_count: int = Field(description="Матчей в обзоре (не больше 20)")
    matches_available: int = Field(description="Всего матчей под фильтром в загруженной истории")
    period_from: datetime | None
    period_to: datetime | None
    win_rate: MetricValue = Field(description="Доля побед, %: победы / матчи с результатом")
    kd: MetricValue = Field(description="K/D: сумма убийств / сумма смертей")
    synced_at: datetime | None
    coverage: CoverageOut
    partial_coverage: bool
    message: str | None
