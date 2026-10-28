import os
from collections.abc import Iterator
from pathlib import Path

# Окружение задаётся до импорта приложения: настройки читаются при создании app
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://faceit:faceit@localhost:15432/faceit_test"
)
os.environ.setdefault("JWT_SECRET", "test-only-secret-0123456789abcdefghijklmnopqrstuvwxyz")
os.environ["FACEIT_API_KEY"] = ""
os.environ["LOGIN_RATE_LIMIT"] = "5"

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_engine, get_sessionmaker
from app.main import create_app

ROOT = Path(__file__).resolve().parent.parent
TABLES = "goal_snapshot_matches, goals, matches, players, users"
PASSWORD = "correct-horse-battery"


def alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_url"] = os.environ["DATABASE_URL"]
    return config


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[None]:
    config = alembic_config()
    # Полный цикл миграций: применяется, откатывается и применяется снова
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield
    get_engine().dispose()


@pytest.fixture
def app(migrated_db: None) -> Iterator[FastAPI]:
    yield create_app()
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db(app: FastAPI) -> Iterator[Session]:
    session = get_sessionmaker()()
    yield session
    session.close()


def register(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    """Регистрирует пользователя и возвращает заголовок авторизации"""
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def user(client: TestClient) -> dict[str, str]:
    return register(client, "alice@example.com")


@pytest.fixture
def stranger(client: TestClient) -> dict[str, str]:
    return register(client, "mallory@example.com")


def add_player(client: TestClient, headers: dict[str, str], query: str = "demo_player") -> int:
    response = client.post("/api/v1/players", json={"query": query}, headers=headers)
    assert response.status_code == 201, response.text
    player_id: int = response.json()["id"]
    return player_id
