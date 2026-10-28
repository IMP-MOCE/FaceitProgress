from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.clients.faceit import (
    FaceitPlayerNotFoundError,
    FaceitUnavailableError,
    HttpFaceitClient,
    parse_match,
)
from app.clients.fixtures import FixtureFaceitClient

BASE = "https://faceit.test/data/v4"
API_KEY = "test-api-key-should-never-leak"


@pytest.fixture
def client() -> HttpFaceitClient:
    return HttpFaceitClient(API_KEY, BASE, timeout=1)


@respx.mock
def test_find_player_parses_cs2_profile(client: HttpFaceitClient) -> None:
    route = respx.get(f"{BASE}/players", params={"nickname": "nick"}).respond(
        json={
            "player_id": "abc-123",
            "nickname": "nick",
            "country": "ru",
            "faceit_url": "https://www.faceit.com/{lang}/players/nick",
            "games": {"cs2": {"faceit_elo": 2010, "skill_level": 10}},
        }
    )
    player = client.find_player("nick")
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert player.faceit_id == "abc-123"
    assert player.elo == 2010
    assert player.faceit_url == "https://www.faceit.com/en/players/nick"


@respx.mock
def test_profile_without_cs2_has_no_elo(client: HttpFaceitClient) -> None:
    respx.get(f"{BASE}/players/abc").respond(
        json={"player_id": "abc", "nickname": "n", "games": {"csgo": {"faceit_elo": 1000}}}
    )
    player = client.get_player("abc")
    assert player.elo is None and player.skill_level is None


@respx.mock
def test_404_means_player_not_found(client: HttpFaceitClient) -> None:
    respx.get(f"{BASE}/players").respond(404)
    with pytest.raises(FaceitPlayerNotFoundError):
        client.find_player("ghost")


@pytest.mark.parametrize("status", [401, 429, 500, 503])
@respx.mock
def test_errors_mean_source_unavailable(client: HttpFaceitClient, status: int) -> None:
    respx.get(f"{BASE}/players").respond(status)
    with pytest.raises(FaceitUnavailableError):
        client.find_player("nick")


@respx.mock
def test_network_error_does_not_leak_api_key(client: HttpFaceitClient) -> None:
    respx.get(f"{BASE}/players").mock(side_effect=httpx.ConnectTimeout("timeout"))
    with pytest.raises(FaceitUnavailableError) as info:
        client.find_player("nick")
    assert API_KEY not in str(info.value)


@respx.mock
def test_history_parsing_and_end_detection(client: HttpFaceitClient) -> None:
    items = [
        {
            "stats": {
                "Match Id": "m1",
                "Match Finished At": 1760000000000,
                "Map": "de_nuke",
                "Result": "1",
                "Kills": "21",
                "Deaths": "14",
            }
        },
        {
            "stats": {
                "Match Id": "m2",
                "Match Finished At": 1759990000,
                "Result": "0",
                "Kills": "",
                "Deaths": "17",
            }
        },
        {"stats": {"Map": "de_nuke"}},  # нет id и времени — пропускается
    ]
    respx.get(f"{BASE}/players/p1/games/cs2/stats").respond(json={"items": items})
    history = client.get_match_history("p1", limit=100)
    assert history.reached_end is True
    first, second = history.matches
    assert first.finished_at == datetime.fromtimestamp(1760000000, tz=UTC)
    assert (first.map, first.won, first.kills, first.deaths) == ("de_nuke", True, 21, 14)
    assert (second.map, second.won, second.kills, second.deaths) == (None, False, None, 17)


@respx.mock
def test_full_page_means_history_may_continue(client: HttpFaceitClient) -> None:
    items = [
        {"stats": {"Match Id": f"m{i}", "Match Finished At": 1760000000 - i}} for i in range(3)
    ]
    respx.get(f"{BASE}/players/p1/games/cs2/stats").respond(json={"items": items})
    assert client.get_match_history("p1", limit=3).reached_end is False


@pytest.mark.parametrize(("raw", "won"), [("1", True), ("0", False), ("?", None), (None, None)])
def test_result_parsing(raw: str | None, won: bool | None) -> None:
    match = parse_match({"Match Id": "x", "Match Finished At": 1760000000, "Result": raw})
    assert match is not None and match.won is won


def test_fixture_client_is_deterministic() -> None:
    fixtures = FixtureFaceitClient()
    first = fixtures.get_match_history("demo-demo_player")
    second = fixtures.get_match_history("demo-demo_player")
    assert first == second
    assert len(first.matches) == 100 and first.reached_end is False
    assert len({m.match_id for m in first.matches}) == 100


def test_fixture_client_errors() -> None:
    fixtures = FixtureFaceitClient()
    with pytest.raises(FaceitPlayerNotFoundError):
        fixtures.find_player("nobody_here")
    with pytest.raises(FaceitUnavailableError):
        fixtures.find_player("source_down")
    with pytest.raises(FaceitPlayerNotFoundError):
        fixtures.get_match_history("demo-nobody_here")
    assert fixtures.get_player("demo-no_cs2_player").elo is None
