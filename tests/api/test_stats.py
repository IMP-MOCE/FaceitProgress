"""Обзор и история матчей. Контрольный расчёт делается независимо от кода сервиса"""

from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient

from app.clients.fixtures import FixtureFaceitClient
from tests.conftest import add_player


def control(nickname: str, count: int = 20, map_name: str | None = None) -> dict[str, int]:
    """Эталон: прямой подсчёт по демо-данным, без функций app.services.metrics."""
    history = FixtureFaceitClient().get_match_history(f"demo-{nickname}").matches
    recent = [m for m in history if map_name is None or m.map == map_name][:count]
    wins = losses = kills = deaths = kd_games = 0
    for m in recent:
        if m.won is True:
            wins += 1
        elif m.won is False:
            losses += 1
        if m.kills is not None and m.deaths is not None:
            kills += m.kills
            deaths += m.deaths
            kd_games += 1
    return {
        "wins": wins,
        "known": wins + losses,
        "kills": kills,
        "deaths": deaths,
        "kd_games": kd_games,
        "count": len(recent),
    }


def stats(
    client: TestClient, headers: dict[str, str], player_id: int, **params: str
) -> dict[str, Any]:
    response = client.get(f"/api/v1/players/{player_id}/stats", params=params, headers=headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_overview_matches_control_calculation(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    body = stats(client, user, player_id)
    expected = control("demo_player")
    assert body["matches_count"] == 20
    assert body["matches_available"] == 100
    assert body["win_rate"]["numerator"] == expected["wins"]
    assert body["win_rate"]["denominator"] == expected["known"] == 20
    assert body["win_rate"]["value"] == round(expected["wins"] / 20 * 100, 2)
    assert body["kd"]["numerator"] == expected["kills"]
    assert body["kd"]["denominator"] == expected["deaths"]
    assert body["kd"]["value"] == round(expected["kills"] / expected["deaths"], 2)
    assert body["formula_version"] == "1"
    assert body["period_from"] <= body["period_to"]
    assert body["message"] is None


def test_missing_fields_reduce_sample_not_values(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user, "patchy_player")
    body = stats(client, user, player_id)
    expected = control("patchy_player")
    assert body["matches_count"] == 20
    assert body["kd"]["sample_size"] == expected["kd_games"] == 18
    assert body["win_rate"]["sample_size"] == expected["known"] == 19


def test_fewer_than_20_matches(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user, "newbie_player")
    body = stats(client, user, player_id)
    assert body["matches_count"] == 8
    assert body["message"] == "Доступно 8 из 20 матчей обзора"


def test_profile_without_cs2_matches(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user, "no_cs2_player")
    body = stats(client, user, player_id)
    assert body["matches_count"] == 0
    assert body["win_rate"]["value"] is None
    assert body["kd"]["value"] is None
    assert "нет завершённых матчей CS2" in body["message"]


def test_map_filter(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    body = stats(client, user, player_id, map="de_mirage")
    expected = control("demo_player", map_name="de_mirage")
    assert body["filters"]["map"] == "de_mirage"
    assert body["matches_count"] == expected["count"]
    assert body["win_rate"]["numerator"] == expected["wins"]

    matches = client.get(
        f"/api/v1/players/{player_id}/matches", params={"map": "de_mirage"}, headers=user
    ).json()
    assert {m["map"] for m in matches["items"]} == {"de_mirage"}


def test_empty_filter_result(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    body = stats(client, user, player_id, map="de_cache")
    assert body["matches_count"] == 0
    assert body["message"] == "Под выбранные фильтры не подошёл ни один матч"


def test_period_bounds_are_inclusive(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    url = f"/api/v1/players/{player_id}/matches"
    items = client.get(url, params={"limit": 5}, headers=user).json()["items"]
    newest, fifth = items[0]["finished_at"], items[4]["finished_at"]
    page = client.get(url, params={"date_from": fifth, "date_to": newest}, headers=user).json()
    assert page["total"] == 5
    assert page["partial_coverage"] is False


def test_period_beyond_loaded_history_is_marked_partial(
    client: TestClient, user: dict[str, str]
) -> None:
    player_id = add_player(client, user)
    player = client.get(f"/api/v1/players/{player_id}", headers=user).json()
    assert player["coverage_from"] is not None
    body = stats(client, user, player_id, date_from="2020-01-01T00:00:00Z")
    assert body["partial_coverage"] is True
    assert body["coverage"]["history_complete"] is False


def test_bad_filters(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    url = f"/api/v1/players/{player_id}/stats"
    bad = [
        {"map": "de mirage"},
        {"map": "DROP TABLE"},
        {"date_from": "2026-10-10T00:00:00Z", "date_to": "2026-10-01T00:00:00Z"},
        {"date_from": "2026-10-01T00:00:00"},  # без часового пояса
        {"date_from": "yesterday"},
    ]
    for params in bad:
        assert client.get(url, params=params, headers=user).status_code == 422, params


def test_matches_pagination(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    url = f"/api/v1/players/{player_id}/matches"
    first = client.get(url, params={"limit": 10}, headers=user).json()
    second = client.get(url, params={"limit": 10, "offset": 10}, headers=user).json()
    assert first["total"] == 100 and len(first["items"]) == 10
    assert first["items"][-1]["finished_at"] > second["items"][0]["finished_at"]
    times = [datetime.fromisoformat(m["finished_at"]) for m in first["items"]]
    assert times == sorted(times, reverse=True)
    assert client.get(url, params={"limit": 101}, headers=user).status_code == 422
