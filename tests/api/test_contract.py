"""Спецификация и схема БД соответствуют реализации."""

import json
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import get_engine

ROOT = Path(__file__).resolve().parents[2]


def test_published_openapi_matches_code(app: FastAPI) -> None:
    published = json.loads((ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
    assert published == app.openapi(), (
        "docs/openapi.json устарел — выполните: python scripts/export_openapi.py"
    )


def test_openapi_declares_bearer_auth_and_problem_responses(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    assert spec["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    goal_post = spec["paths"]["/api/v1/goals"]["post"]
    assert {"401", "404", "409", "422"} <= set(goal_post["responses"])
    assert goal_post["security"] == [{"HTTPBearer": []}]


def test_migrations_match_models(migrated_db: None) -> None:
    with get_engine().connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == [], diff
