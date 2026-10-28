from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, EmailStr, Field, field_validator

from app.schemas.common import ApiModel

# Пароль передаётся как есть: обрезка пробелов изменила бы его
_NO_STRIP = ConfigDict(str_strip_whitespace=False)


class RegisterRequest(ApiModel):
    model_config = _NO_STRIP

    email: EmailStr
    # Длина важнее состава символов (OWASP ASVS 2.1); верхняя граница защищает от DoS хешированием
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower()


class LoginRequest(ApiModel):
    model_config = _NO_STRIP

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower()


class TokenResponse(ApiModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - схема авторизации, не секрет
    expires_in: int = Field(description="Срок жизни токена в секундах")


class UserOut(ApiModel):
    id: int
    email: str
    created_at: datetime
