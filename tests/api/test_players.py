from fastapi.testclient import TestClient

from tests.conftest import add_player

PLAYERS = "/api/v1/players"


def test_add_player_by_nickname(client: TestClient, user: dict[str, str]) -> None:
    response = client.post(PLAYERS, json={"query": "demo_player", "note": "мой"}, headers=user)
    assert response.status_code == 201
    body = response.json()
    assert response.headers["Location"] == f"{PLAYERS}/{body['id']}"
    assert body["nickname"] == "demo_player"
    assert body["elo"] == 1850
    assert body["note"] == "мой"
    assert body["synced_at"] is not None
    # У demo_player 120 матчей, API отдаёт 100 - история неполная
    assert body["history_complete"] is False


def test_add_player_by_profile_link(client: TestClient, user: dict[str, str]) -> None:
    link = "https://www.faceit.com/ru/players/newbie_player"
    response = client.post(PLAYERS, json={"query": link}, headers=user)
    assert response.status_code == 201
    assert response.json()["nickname"] == "newbie_player"
    assert response.json()["history_complete"] is True


def test_add_same_player_twice_is_conflict(client: TestClient, user: dict[str, str]) -> None:
    add_player(client, user)
    response = client.post(PLAYERS, json={"query": "DEMO_PLAYER"}, headers=user)
    assert response.status_code == 409


def test_unknown_player_is_not_found(client: TestClient, user: dict[str, str]) -> None:
    response = client.post(PLAYERS, json={"query": "nobody_here"}, headers=user)
    assert response.status_code == 404
    assert response.json()["type"] == "/problems/faceit-player-not-found"


def test_source_down_differs_from_not_found(client: TestClient, user: dict[str, str]) -> None:
    response = client.post(PLAYERS, json={"query": "source_down"}, headers=user)
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert response.json()["type"] == "/problems/source-unavailable"


def test_empty_and_invalid_queries(client: TestClient, user: dict[str, str]) -> None:
    for query in ("", "   ", "https://evil.example/players/x", "bad nick"):
        response = client.post(PLAYERS, json={"query": query}, headers=user)
        assert response.status_code == 422, query


def test_list_only_own_players(
    client: TestClient, user: dict[str, str], stranger: dict[str, str]
) -> None:
    add_player(client, user)
    add_player(client, user, "newbie_player")
    add_player(client, stranger, "patchy_player")
    body = client.get(PLAYERS, headers=user).json()
    assert body["total"] == 2
    assert {p["nickname"] for p in body["items"]} == {"demo_player", "newbie_player"}
    page = client.get(PLAYERS, params={"limit": 1, "offset": 1}, headers=user).json()
    assert len(page["items"]) == 1 and page["total"] == 2


def test_update_note_and_clear_it(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    response = client.patch(f"{PLAYERS}/{player_id}", json={"note": "основа"}, headers=user)
    assert response.json()["note"] == "основа"
    # Пустое тело не меняет заметку, явный null - очищает
    assert client.patch(f"{PLAYERS}/{player_id}", json={}, headers=user).json()["note"] == "основа"
    response = client.patch(f"{PLAYERS}/{player_id}", json={"note": None}, headers=user)
    assert response.json()["note"] is None


def test_sync_updates_timestamp(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    before = client.get(f"{PLAYERS}/{player_id}", headers=user).json()["synced_at"]
    after = client.post(f"{PLAYERS}/{player_id}/sync", headers=user).json()["synced_at"]
    assert after > before
    # Повторная загрузка тех же матчей не создаёт дублей
    matches = client.get(f"{PLAYERS}/{player_id}/matches", headers=user).json()
    assert matches["total"] == 100


def test_delete_player(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    assert client.delete(f"{PLAYERS}/{player_id}", headers=user).status_code == 204
    assert client.get(f"{PLAYERS}/{player_id}", headers=user).status_code == 404


def test_other_users_player_is_invisible(
    client: TestClient, user: dict[str, str], stranger: dict[str, str]
) -> None:
    player_id = add_player(client, user)
    url = f"{PLAYERS}/{player_id}"
    attempts = [
        client.get(url, headers=stranger),
        client.patch(url, json={"note": "x"}, headers=stranger),
        client.post(f"{url}/sync", headers=stranger),
        client.get(f"{url}/matches", headers=stranger),
        client.get(f"{url}/stats", headers=stranger),
        client.delete(url, headers=stranger),
    ]
    assert [r.status_code for r in attempts] == [404] * len(attempts)
    # Игрок владельца не пострадал.
    assert client.get(url, headers=user).json()["note"] is None


def test_requires_auth(client: TestClient) -> None:
    assert client.get(PLAYERS).status_code == 401
    assert client.post(PLAYERS, json={"query": "demo_player"}).status_code == 401


def test_invalid_path_id(client: TestClient, user: dict[str, str]) -> None:
    assert client.get(f"{PLAYERS}/0", headers=user).status_code == 422
    assert client.get(f"{PLAYERS}/abc", headers=user).status_code == 422
