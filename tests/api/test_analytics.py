"""Сравнение 20/20, карты и сводка A01–A03 через API (S07–S10)"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.clients.fixtures import ANCHOR
from app.models import Match
from tests.conftest import add_player

PLAYERS = "/api/v1/players"


def add_newer_matches(
    db: Session,
    player_id: int,
    results: list[bool | None],
    *,
    map_name: str = "de_dust2",
    kills: int | None = 10,
    deaths: int | None = 10,
) -> list[str]:
    """Добавляет матчи новее демо-истории. results - от новых к старым. Возвращает id"""
    ids = []
    for index, won in enumerate(results):
        match_id = f"ctl-{index:03d}"
        db.add(
            Match(
                player_id=player_id,
                faceit_match_id=match_id,
                finished_at=ANCHOR + timedelta(days=30) - timedelta(hours=index),
                map=map_name,
                won=won,
                kills=kills,
                deaths=deaths,
            )
        )
        ids.append(match_id)
    db.commit()
    return ids


def wins_losses(wins: int, losses: int) -> list[bool | None]:
    return [True] * wins + [False] * losses


def test_compare_groups_are_disjoint_and_match_independent_calculation(
    client: TestClient, user: dict[str, str]
) -> None:
    player_id = add_player(client, user)
    body = client.get(f"{PLAYERS}/{player_id}/compare", headers=user).json()
    assert body["status"] == "ready"
    recent, previous = body["recent"], body["previous"]
    assert recent["matches_count"] == previous["matches_count"] == 20
    assert set(recent["match_ids"]).isdisjoint(previous["match_ids"])
    assert recent["period_from"] > previous["period_to"]

    # Контрольный расчёт без app.services: прямой подсчёт по истории из API
    history = client.get(
        f"{PLAYERS}/{player_id}/matches", params={"limit": 40}, headers=user
    ).json()["items"]
    assert [m["faceit_match_id"] for m in history[:20]] == recent["match_ids"]
    recent_wins = sum(1 for m in history[:20] if m["won"])
    previous_wins = sum(1 for m in history[20:40] if m["won"])
    assert recent["win_rate"]["numerator"] == recent_wins
    assert previous["win_rate"]["numerator"] == previous_wins
    assert body["win_rate"]["unit"] == "pp"
    assert body["win_rate"]["change"] == round((recent_wins - previous_wins) * 5, 2)
    assert body["kd"]["unit"] == "ratio"
    assert body["win_rate"]["complete"] and body["kd"]["complete"]


def test_compare_with_too_few_matches(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user, "newbie_player")
    body = client.get(f"{PLAYERS}/{player_id}/compare", headers=user).json()
    assert body["status"] == "insufficient_data"
    assert (body["required"], body["available"]) == (40, 8)
    assert "доступно 8" in body["message"]
    assert body["recent"] is None and body["win_rate"] is None


def test_compare_applies_map_filter_before_split(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    params = {"map": "de_mirage"}
    body = client.get(f"{PLAYERS}/{player_id}/compare", params=params, headers=user).json()
    on_map = client.get(
        f"{PLAYERS}/{player_id}/matches", params={**params, "limit": 100}, headers=user
    ).json()
    assert body["available"] == on_map["total"]
    assert body["map"] == "de_mirage"
    if body["status"] == "ready":
        mirage_ids = {m["faceit_match_id"] for m in on_map["items"]}
        assert set(body["recent"]["match_ids"]) <= mirage_ids
        assert set(body["previous"]["match_ids"]) <= mirage_ids
    else:
        assert on_map["total"] < 40


def test_compare_marks_incomplete_metric(
    client: TestClient, user: dict[str, str], db: Session
) -> None:
    player_id = add_player(client, user, "newbie_player")
    add_newer_matches(db, player_id, wins_losses(20, 20))
    gap = db.query(Match).filter_by(player_id=player_id, faceit_match_id="ctl-005").one()
    gap.kills = None
    db.commit()
    body = client.get(f"{PLAYERS}/{player_id}/compare", headers=user).json()
    assert body["status"] == "ready"
    assert body["win_rate"]["complete"] is True
    # Значение K/D показано с фактическим покрытием, но вывод о динамике не допускается
    assert body["kd"]["complete"] is False
    assert body["recent"]["kd"]["sample_size"] == 19


def test_maps_breakdown(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    body = client.get(f"{PLAYERS}/{player_id}/maps", headers=user).json()
    assert body["min_matches"] == 10
    assert (
        sum(i["matches"] for i in body["items"]) + body["unknown_map_matches"]
        == (body["matches_total"])
    )
    for item in body["items"]:
        assert item["enough_data"] is (item["win_rate"]["denominator"] >= 10)
        assert item["win_rate"]["sample_size"] <= item["matches"]
    # Отсортировано по числу матчей
    counts = [i["matches"] for i in body["items"]]
    assert counts == sorted(counts, reverse=True)


def test_maps_period_filter(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    date_from = (ANCHOR - timedelta(days=5)).isoformat()
    body = client.get(
        f"{PLAYERS}/{player_id}/maps", params={"date_from": date_from}, headers=user
    ).json()
    # 9 часов между матчами: за 5 суток включительно - 14 матчей
    assert body["matches_total"] == 14


def test_insights_a01_control_example(
    client: TestClient, user: dict[str, str], db: Session
) -> None:
    player_id = add_player(client, user, "newbie_player")
    # Последние 20: 8 побед (40%); предыдущие 20: 12 побед (60%)
    ids = add_newer_matches(db, player_id, wins_losses(8, 12) + wins_losses(12, 8))
    body = client.get(f"{PLAYERS}/{player_id}/insights", headers=user).json()
    assert body["status"] == "ready"
    assert body["rules_version"] == "1"
    assert [i["rule_id"] for i in body["items"]] == ["A01"]
    insight = body["items"][0]
    assert insight["title"] == "Доля побед снизилась с 60% до 40% в двух сравниваемых выборках"
    assert (insight["before"], insight["after"], insight["change"]) == (60.0, 40.0, -20.0)
    assert insight["sample_size"] == 40
    assert len(insight["evidence"]) == 40
    # Три последних поражения последней группы: матчи 8, 9, 10 (0-7 - победы)
    assert insight["review_match_ids"] == ids[8:11]
    assert "причину" in insight["limitation"]


def test_insights_a03_on_weak_map(client: TestClient, user: dict[str, str], db: Session) -> None:
    player_id = add_player(client, user, "newbie_player")
    add_newer_matches(db, player_id, wins_losses(4, 8), map_name="de_vertigo")
    body = client.get(f"{PLAYERS}/{player_id}/insights", headers=user).json()
    assert [i["rule_id"] for i in body["items"]] == ["A03"]
    insight = body["items"][0]
    assert insight["map"] == "de_vertigo"
    assert insight["title"] == "На карте de_vertigo в выбранной выборке 4 победы из 12 матчей"
    assert insight["after"] == 33.33
    assert insight["before"] is None and insight["change"] is None
    assert {m["map"] for m in insight["evidence"]} == {"de_vertigo"}


def test_insights_without_signals(client: TestClient, user: dict[str, str], db: Session) -> None:
    player_id = add_player(client, user, "newbie_player")
    add_newer_matches(db, player_id, [True, False] * 20)
    body = client.get(f"{PLAYERS}/{player_id}/insights", headers=user).json()
    assert body["status"] == "no_signals"
    assert body["message"] == "По выбранным правилам выраженных сигналов не найдено"
    assert body["items"] == []


def test_insights_with_insufficient_data(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user, "newbie_player")
    body = client.get(f"{PLAYERS}/{player_id}/insights", headers=user).json()
    assert body["status"] == "insufficient_data"
    assert body["message"] == "Недостаточно данных для сводки"


def test_insights_are_deterministic(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    url = f"{PLAYERS}/{player_id}/insights"
    assert client.get(url, headers=user).json() == client.get(url, headers=user).json()


def test_analytics_of_other_users_player_is_invisible(
    client: TestClient, user: dict[str, str], stranger: dict[str, str]
) -> None:
    player_id = add_player(client, user)
    for resource in ("compare", "maps", "insights"):
        response = client.get(f"{PLAYERS}/{player_id}/{resource}", headers=stranger)
        assert response.status_code == 404, resource


def test_analytics_validation(client: TestClient, user: dict[str, str]) -> None:
    player_id = add_player(client, user)
    naive = datetime(2026, 10, 1).isoformat()
    aware = datetime(2026, 10, 1, tzinfo=UTC).isoformat()
    checks = [
        client.get(f"{PLAYERS}/{player_id}/compare", params={"map": "Mirage!"}, headers=user),
        client.get(f"{PLAYERS}/{player_id}/maps", params={"date_from": naive}, headers=user),
        client.get(
            f"{PLAYERS}/{player_id}/maps",
            params={"date_from": aware, "date_to": "2026-09-01T00:00:00Z"},
            headers=user,
        ),
    ]
    assert [r.status_code for r in checks] == [422, 422, 422]
