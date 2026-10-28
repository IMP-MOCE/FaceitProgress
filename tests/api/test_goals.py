from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Match, Player
from tests.conftest import add_player

GOALS = "/api/v1/goals"


def create_goal(
    client: TestClient, headers: dict[str, str], player_id: int, **fields: Any
) -> dict[str, Any]:
    payload = {"player_id": player_id, "metric": "win_rate", "action": "Пересмотреть 3 поражения"}
    payload.update(fields)
    response = client.post(GOALS, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def add_matches_after(
    db: Session,
    player_id: int,
    started_at: str,
    count: int,
    *,
    won: bool | None = True,
    kills: int = 20,
    deaths: int = 10,
) -> None:
    start = datetime.fromisoformat(started_at)
    for i in range(count):
        db.add(
            Match(
                player_id=player_id,
                faceit_match_id=f"after-{i}",
                finished_at=start + timedelta(hours=i + 1),
                map="de_mirage",
                won=won,
                kills=kills,
                deaths=deaths,
            )
        )
    db.commit()


def test_create_goal_saves_baseline_snapshot(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    goal = create_goal(client, user, player_id)
    assert goal["status"] == "active"
    assert goal["formula_version"] == "1"
    assert len(goal["baseline_matches"]) == 20
    stats = client.get(f"/api/v1/players/{player_id}/stats", headers=user).json()
    # Исходная точка цели совпадает с обзором последних 20 матчей
    assert goal["baseline"] == stats["win_rate"]


def test_baseline_respects_map_context(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    goal = create_goal(client, user, player_id, metric="kd", map="de_mirage")
    assert {m["map"] for m in goal["baseline_matches"]} == {"de_mirage"}


def test_only_one_active_goal(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    first = create_goal(client, user, player_id)
    response = client.post(
        GOALS, json={"player_id": player_id, "metric": "kd", "action": "Другая цель"}, headers=user
    )
    assert response.status_code == 409
    assert response.json()["active_goal_id"] == first["id"]

    second = create_goal(client, user, player_id, metric="kd", replace_active=True)
    assert client.get(f"{GOALS}/{first['id']}", headers=user).json()["status"] == "archived"
    active = client.get(GOALS, params={"status": "active"}, headers=user).json()
    assert [g["id"] for g in active["items"]] == [second["id"]]


def test_not_enough_matches(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user, "newbie_player")
    response = client.post(
        GOALS, json={"player_id": player_id, "metric": "win_rate", "action": "Цель"}, headers=user
    )
    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "/problems/insufficient-data"
    assert (body["required"], body["available"]) == (20, 8)


def test_incomplete_metric_data_blocks_goal(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user, "patchy_player")
    response = client.post(
        GOALS, json={"player_id": player_id, "metric": "kd", "action": "Цель"}, headers=user
    )
    assert response.status_code == 422
    assert len(response.json()["missing_match_ids"]) == 2


def test_goal_validation(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    bad = [
        {"player_id": player_id, "metric": "elo", "action": "Цель"},
        {"player_id": player_id, "metric": "kd", "action": ""},
        {"player_id": player_id, "metric": "kd", "action": "Цель", "map": "Mirage!"},
        {"player_id": 0, "metric": "kd", "action": "Цель"},
    ]
    for payload in bad:
        assert client.post(GOALS, json=payload, headers=user).status_code == 422, payload


def test_update_and_close_goal(client: TestClient, user: dict[str, str]) -> None:
    goal = create_goal(client, user, add_player(client, user))
    url = f"{GOALS}/{goal['id']}"
    response = client.patch(url, json={"action": "Новое действие"}, headers=user)
    assert response.json()["action"] == "Новое действие"
    assert client.patch(url, json={"status": "completed"}, headers=user).json()["status"] == (
        "completed"
    )
    # Закрытую цель нельзя закрыть повторно
    assert client.patch(url, json={"status": "archived"}, headers=user).status_code == 409
    assert client.patch(url, json={"status": "active"}, headers=user).status_code == 422


def test_delete_goal(client: TestClient, user: dict[str, str]) -> None:
    goal = create_goal(client, user, add_player(client, user))
    assert client.delete(f"{GOALS}/{goal['id']}", headers=user).status_code == 204
    assert client.get(f"{GOALS}/{goal['id']}", headers=user).status_code == 404
    # После удаления активной цели можно поставить новую
    create_goal(client, user, goal["player_id"])


def test_other_users_goal_is_invisible(
    client: TestClient, user: dict[str, str], stranger: dict[str, str]
) -> None:
    player_id = add_player(client, user)
    goal = create_goal(client, user, player_id)
    url = f"{GOALS}/{goal['id']}"
    attempts = [
        client.get(url, headers=stranger),
        client.patch(url, json={"action": "взлом"}, headers=stranger),
        client.get(f"{url}/progress", headers=stranger),
        client.delete(url, headers=stranger),
        # Чужого игрока нельзя использовать для своей цели
        client.post(
            GOALS,
            json={"player_id": player_id, "metric": "kd", "action": "Цель"},
            headers=stranger,
        ),
    ]
    assert [r.status_code for r in attempts] == [404] * len(attempts)
    assert client.get(GOALS, headers=stranger).json()["total"] == 0


def test_progress_collecting(client: TestClient, user: dict[str, str], db: Session) -> None:
    player_id = add_player(client, user)
    goal = create_goal(client, user, player_id)
    add_matches_after(db, player_id, goal["started_at"], 5)
    body = client.get(f"{GOALS}/{goal['id']}/progress", headers=user).json()
    assert body["status"] == "collecting"
    assert (body["collected"], body["required"]) == (5, 20)
    assert body["followup"] is None and body["change"] is None


def test_progress_ready_and_frozen(client: TestClient, user: dict[str, str], db: Session) -> None:
    player_id = add_player(client, user)
    goal = create_goal(client, user, player_id)
    add_matches_after(db, player_id, goal["started_at"], 20, won=True)
    url = f"{GOALS}/{goal['id']}/progress"

    body = client.get(url, headers=user).json()
    assert body["status"] == "ready"
    assert body["followup"]["value"] == 100.0
    assert body["change_unit"] == "pp"
    assert body["change"] == round(100.0 - goal["baseline"]["value"], 2)
    assert len(body["followup_matches"]) == 20

    # Последующие изменения истории не меняют готовое сравнение
    db.execute(update(Match).where(Match.player_id == player_id).values(won=False))
    db.commit()
    assert client.get(url, headers=user).json() == body


def test_progress_does_not_replace_incomplete_matches(
    client: TestClient, user: dict[str, str], db: Session
) -> None:
    player_id = add_player(client, user)
    goal = create_goal(client, user, player_id)
    add_matches_after(db, player_id, goal["started_at"], 20)
    first_after = db.query(Match).filter_by(player_id=player_id, faceit_match_id="after-0").one()
    first_after.won = None
    db.commit()
    body = client.get(f"{GOALS}/{goal['id']}/progress", headers=user).json()
    assert body["status"] == "incomplete_data"
    assert body["missing_match_ids"] == ["after-0"]


def test_progress_unrecoverable_after_history_gap(
    client: TestClient, user: dict[str, str], db: Session
) -> None:
    player_id = add_player(client, user)
    goal = create_goal(client, user, player_id)
    # Имитация разрыва: загруженная история начинается позже постановки цели
    gap_start = datetime.fromisoformat(goal["started_at"]) + timedelta(days=3)
    db.execute(
        update(Player)
        .where(Player.id == player_id)
        .values(coverage_from=gap_start, history_complete=False)
    )
    db.commit()
    body = client.get(f"{GOALS}/{goal['id']}/progress", headers=user).json()
    assert body["status"] == "unrecoverable"
    assert "Невозможно восстановить" in body["message"]
    assert body["baseline"]["sample_size"] == 20


def test_kd_goal_change_is_ratio(client: TestClient, user: dict[str, str], db: Session) -> None:
    player_id = add_player(client, user)
    goal = create_goal(client, user, player_id, metric="kd")
    add_matches_after(db, player_id, goal["started_at"], 20, kills=30, deaths=10)
    body = client.get(f"{GOALS}/{goal['id']}/progress", headers=user).json()
    assert body["status"] == "ready"
    assert body["change_unit"] == "ratio"
    assert body["followup"]["value"] == 3.0
