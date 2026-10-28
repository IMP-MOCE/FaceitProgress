import pytest

from app.core.errors import InvalidInput
from app.services.players import parse_query


@pytest.mark.parametrize(
    ("query", "nickname"),
    [
        ("demo_player", "demo_player"),
        ("  Some-Nick.1  ", "Some-Nick.1"),
        ("https://www.faceit.com/ru/players/demo_player", "demo_player"),
        ("https://faceit.com/en/players/demo_player/stats/cs2", "demo_player"),
    ],
)
def test_accepts_nickname_or_profile_link(query: str, nickname: str) -> None:
    assert parse_query(query) == nickname


@pytest.mark.parametrize(
    "query",
    [
        "https://evil.example.com/players/demo_player",
        "https://faceit.com.evil.example/players/demo_player",
        "https://www.faceit.com/ru/teams/abc",
        "https://www.faceit.com/ru/players/",
        "nick name",
        "<script>",
        "x",
        "a" * 33,
    ],
)
def test_rejects_foreign_links_and_bad_nicknames(query: str) -> None:
    with pytest.raises(InvalidInput):
        parse_query(query)
