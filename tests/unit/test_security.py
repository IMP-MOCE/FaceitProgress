from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

SETTINGS = get_settings()
SECRET = SETTINGS.jwt_secret.get_secret_value()


def test_password_hash_is_argon2_and_verifies() -> None:
    hashed = hash_password("s3cret-pass")
    assert hashed.startswith("$argon2id$")
    assert "s3cret-pass" not in hashed
    assert verify_password("s3cret-pass", hashed)
    assert not verify_password("wrong-pass", hashed)


def test_verify_without_hash_is_false() -> None:
    assert not verify_password("anything", None)
    assert not verify_password("anything", "not-a-hash")


def test_token_roundtrip() -> None:
    token, expires_in = create_access_token(42, SETTINGS)
    assert expires_in == SETTINGS.jwt_ttl_minutes * 60
    assert decode_access_token(token, SETTINGS) == 42


def _encode(
    payload: dict[str, object], secret: str = SECRET, algorithm: str = JWT_ALGORITHM
) -> str:
    return jwt.encode(payload, secret, algorithm=algorithm)


def _claims(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": "1",
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return claims


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(_encode(_claims(exp=datetime.now(UTC) - timedelta(seconds=1))), id="expired"),
        pytest.param(_encode(_claims(), secret="another-secret-" + "x" * 32), id="foreign-secret"),
        pytest.param(_encode(_claims(), algorithm="HS512"), id="other-algorithm"),
        pytest.param(jwt.encode(_claims(), None, algorithm="none"), id="alg-none"),
        pytest.param(_encode(_claims(type="refresh")), id="wrong-type"),
        pytest.param(_encode(_claims(sub="admin")), id="non-numeric-sub"),
        pytest.param(_encode({"sub": "1", "type": "access"}), id="no-exp"),
        pytest.param("not.a.jwt", id="garbage"),
    ],
)
def test_invalid_tokens_are_rejected(token: str) -> None:
    assert decode_access_token(token, SETTINGS) is None


def test_rate_limiter_blocks_after_limit_and_resets() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    assert limiter.hit("k") is None
    assert limiter.hit("k") is None
    retry_after = limiter.hit("k")
    assert retry_after is not None and 1 <= retry_after <= 60
    assert limiter.hit("other") is None
    limiter.reset("k")
    assert limiter.hit("k") is None
    limiter.reset()
    assert limiter.hit("other") is None
