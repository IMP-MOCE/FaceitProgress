"""Хеширование паролей (Argon2id) и выпуск/проверка JWT."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings

JWT_ALGORITHM = "HS256"
TOKEN_TYPE = "access"  # noqa: S105 - тип токена, не секрет

_hasher = PasswordHasher()
# Хеш для несуществующего пользователя: проверка занимает столько же времени,
# и по задержке ответа нельзя понять, зарегистрирован ли email
_DUMMY_HASH = _hasher.hash("timing-attack-protection")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: int, settings: Settings) -> tuple[str, int]:
    """Возвращает токен и срок его жизни в секундах."""
    now = datetime.now(UTC)
    ttl = timedelta(minutes=settings.jwt_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "type": TOKEN_TYPE,
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)
    return token, int(ttl.total_seconds())


def decode_access_token(token: str, settings: Settings) -> int | None:
    """Возвращает id пользователя или None, если токен невалиден."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            # Алгоритм задан явно: токены с alg=none или другим алгоритмом отклоняются
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != TOKEN_TYPE:
        return None
    try:
        return int(payload["sub"])
    except (TypeError, ValueError):
        return None
