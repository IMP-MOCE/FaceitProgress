from datetime import datetime

from pydantic import Field

from app.schemas.common import ApiModel


class PlayerCreate(ApiModel):
    query: str = Field(
        min_length=1,
        max_length=255,
        description="Ник FACEIT или ссылка на профиль",
        examples=["demo_player", "https://www.faceit.com/ru/players/demo_player"],
    )
    note: str | None = Field(default=None, max_length=500)


class PlayerUpdate(ApiModel):
    note: str | None = Field(default=None, max_length=500)


class CoverageOut(ApiModel):
    history_complete: bool = Field(description="Загружена вся история игрока")
    coverage_from: datetime | None = Field(
        description="Все матчи, завершённые с этого момента, есть в загруженной истории"
    )


class PlayerOut(ApiModel):
    id: int
    faceit_id: str
    nickname: str
    country: str | None
    faceit_url: str | None
    elo: int | None = Field(description="Текущий ELO в CS2; null, если данных нет")
    skill_level: int | None
    note: str | None
    synced_at: datetime | None = Field(description="Время последнего успешного обновления")
    history_complete: bool
    coverage_from: datetime | None
    created_at: datetime


class PlayerPage(ApiModel):
    items: list[PlayerOut]
    total: int
    limit: int
    offset: int
