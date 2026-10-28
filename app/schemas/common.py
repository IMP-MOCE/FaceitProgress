from typing import Any

from pydantic import BaseModel, ConfigDict, Field

MAP_PATTERN = r"^[a-z0-9_]{2,32}$"


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class ProblemDetail(BaseModel):
    """Тело ошибки по RFC 9457"""

    type: str = Field(examples=["/problems/not-found"])
    title: str
    status: int
    detail: str
    instance: str
    errors: list[dict[str, Any]] | None = None


_DESCRIPTIONS = {
    401: "Нет токена, токен истёк или подделан",
    404: "Ресурс не найден или принадлежит другому пользователю",
    409: "Конфликт с текущим состоянием",
    422: "Ошибка валидации или недостаточно данных",
    429: "Превышен лимит попыток",
    503: "Источник данных FACEIT недоступен",
}


def problem_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {
        code: {
            "model": ProblemDetail,
            "description": _DESCRIPTIONS[code],
            "content": {"application/problem+json": {}},
        }
        for code in codes
    }
