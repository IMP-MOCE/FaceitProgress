from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, register

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/users/me"


def test_register_returns_user_without_password(client: TestClient) -> None:
    response = client.post(REGISTER, json={"email": "Bob@Example.com", "password": PASSWORD})
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "bob@example.com"
    assert set(body) == {"id", "email", "created_at"}


def test_duplicate_email_is_conflict_case_insensitive(client: TestClient) -> None:
    client.post(REGISTER, json={"email": "bob@example.com", "password": PASSWORD})
    response = client.post(REGISTER, json={"email": "BOB@example.com", "password": PASSWORD})
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "/problems/conflict"


def test_validation_error_does_not_echo_password(client: TestClient) -> None:
    response = client.post(REGISTER, json={"email": "bob@example.com", "password": "short7!"})
    assert response.status_code == 422
    assert "short7!" not in response.text
    assert response.json()["errors"][0]["loc"] == ["body", "password"]


def test_invalid_email_rejected(client: TestClient) -> None:
    response = client.post(REGISTER, json={"email": "not-an-email", "password": PASSWORD})
    assert response.status_code == 422


def test_login_and_me(client: TestClient) -> None:
    headers = register(client, "carol@example.com")
    response = client.get(ME, headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == "carol@example.com"


def test_login_response_shape(client: TestClient) -> None:
    register(client, "dave@example.com")
    body = client.post(LOGIN, json={"email": "dave@example.com", "password": PASSWORD}).json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 30 * 60


def test_wrong_password_and_unknown_email_look_the_same(client: TestClient) -> None:
    register(client, "erin@example.com")
    wrong = client.post(LOGIN, json={"email": "erin@example.com", "password": "bad-password"})
    unknown = client.post(LOGIN, json={"email": "nobody@example.com", "password": "bad-password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_password_is_not_trimmed(client: TestClient) -> None:
    register(client, "frank@example.com", password="  padded-password  ")
    response = client.post(
        LOGIN, json={"email": "frank@example.com", "password": "padded-password"}
    )
    assert response.status_code == 401


def test_login_rate_limit(client: TestClient) -> None:
    register(client, "grace@example.com")
    for _ in range(4):  # одна попытка уже потрачена на вход в register()
        client.post(LOGIN, json={"email": "grace@example.com", "password": "wrong-password"})
    response = client.post(LOGIN, json={"email": "grace@example.com", "password": PASSWORD})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1


def test_protected_endpoint_requires_token(client: TestClient) -> None:
    response = client.get(ME)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_forged_and_expired_tokens_rejected(client: TestClient) -> None:
    register(client, "heidi@example.com")
    now = datetime.now(UTC)
    forged = jwt.encode(
        {"sub": "1", "type": "access", "iat": now, "exp": now + timedelta(minutes=5)},
        "attacker-secret-" + "x" * 32,
        algorithm="HS256",
    )
    for token in (forged, "garbage", ""):
        response = client.get(ME, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, token


def test_deleted_user_token_stops_working(client: TestClient) -> None:
    headers = register(client, "ivan@example.com")
    assert client.delete(ME, headers=headers).status_code == 204
    assert client.get(ME, headers=headers).status_code == 401
    # Email освобождается — можно зарегистрироваться заново.
    register(client, "ivan@example.com")


def test_security_headers(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Content-Security-Policy"] == "default-src 'none'"


def test_cors_allows_only_configured_origin(client: TestClient) -> None:
    allowed = client.options(
        ME,
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    denied = client.options(
        ME,
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in denied.headers
