"""Клиент FACEIT Data API v4.

Названия полей статистики проверяются на реальных ответах (ПР1, недели 1–2),
поэтому разбор сделан терпимым: отсутствующее или нечисловое поле даёт None, а не 0
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

HISTORY_LIMIT = 100
GAME_ID = "cs2"


@dataclass(frozen=True)
class FaceitPlayer:
    faceit_id: str
    nickname: str
    country: str | None
    faceit_url: str | None
    elo: int | None
    skill_level: int | None


@dataclass(frozen=True)
class FaceitMatch:
    match_id: str
    finished_at: datetime
    map: str | None
    won: bool | None
    kills: int | None
    deaths: int | None


@dataclass(frozen=True)
class MatchHistory:
    matches: list[FaceitMatch]
    # True - получена вся история игрока (матчей меньше лимита страницы)
    reached_end: bool


class FaceitPlayerNotFoundError(Exception):
    pass


class FaceitUnavailableError(Exception):
    pass


class FaceitClient(Protocol):
    def find_player(self, nickname: str) -> FaceitPlayer: ...

    def get_player(self, faceit_id: str) -> FaceitPlayer: ...

    def get_match_history(self, faceit_id: str, limit: int = HISTORY_LIMIT) -> MatchHistory: ...


def _to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _to_won(value: Any) -> bool | None:
    raw = str(value).strip().lower() if value is not None else ""
    if raw in {"1", "win", "true"}:
        return True
    if raw in {"0", "loss", "lose", "false"}:
        return False
    return None


def _to_datetime(value: Any) -> datetime | None:
    stamp = _to_int(value)
    if stamp is None:
        return None
    # FACEIT отдаёт время то в секундах, то в миллисекундах
    if stamp > 10**11:
        stamp //= 1000
    return datetime.fromtimestamp(stamp, tz=UTC)


def parse_player(data: dict[str, Any]) -> FaceitPlayer:
    cs2 = (data.get("games") or {}).get(GAME_ID) or {}
    url = data.get("faceit_url")
    return FaceitPlayer(
        faceit_id=str(data["player_id"]),
        nickname=str(data["nickname"]),
        country=data.get("country"),
        faceit_url=url.replace("{lang}", "en") if isinstance(url, str) else None,
        elo=_to_int(cs2.get("faceit_elo")),
        skill_level=_to_int(cs2.get("skill_level")),
    )


def parse_match(stats: dict[str, Any]) -> FaceitMatch | None:
    match_id = stats.get("Match Id")
    finished_at = _to_datetime(stats.get("Match Finished At") or stats.get("Updated At"))
    # Без идентификатора и времени завершения матч нельзя ни дедуплицировать, ни упорядочить
    if not match_id or finished_at is None:
        return None
    return FaceitMatch(
        match_id=str(match_id),
        finished_at=finished_at,
        map=stats.get("Map") or None,
        won=_to_won(stats.get("Result")),
        kills=_to_int(stats.get("Kills")),
        deaths=_to_int(stats.get("Deaths")),
    )


class HttpFaceitClient:
    def __init__(self, api_key: str, base_url: str, timeout: float = 10.0) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        )

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            # В текст исключения не попадают заголовки, а значит и ключ API
            raise FaceitUnavailableError(type(exc).__name__) from exc
        if response.status_code == 404:
            raise FaceitPlayerNotFoundError(path)
        if response.status_code >= 400:
            raise FaceitUnavailableError(f"FACEIT responded {response.status_code}")
        payload: dict[str, Any] = response.json()
        return payload

    def find_player(self, nickname: str) -> FaceitPlayer:
        return parse_player(self._get("/players", {"nickname": nickname}))

    def get_player(self, faceit_id: str) -> FaceitPlayer:
        # По id, а не по нику: ник на FACEIT можно сменить
        return parse_player(self._get(f"/players/{faceit_id}", {}))

    def get_match_history(self, faceit_id: str, limit: int = HISTORY_LIMIT) -> MatchHistory:
        payload = self._get(
            f"/players/{faceit_id}/games/{GAME_ID}/stats", {"offset": 0, "limit": limit}
        )
        items = payload.get("items") or []
        parsed = (parse_match(item.get("stats") or {}) for item in items)
        matches = [m for m in parsed if m is not None]
        return MatchHistory(matches=matches, reached_end=len(items) < limit)
