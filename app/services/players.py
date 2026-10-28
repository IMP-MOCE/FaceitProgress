import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clients.faceit import (
    FaceitClient,
    FaceitPlayer,
    FaceitPlayerNotFoundError,
    FaceitUnavailableError,
    MatchHistory,
)
from app.core.errors import Conflict, InvalidInput, PlayerNotFoundInSource, SourceUnavailable
from app.models import Player, User
from app.repositories import matches, players

NICKNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{2,32}$")
RETRY_AFTER_SECONDS = "30"
ALREADY_TRACKED = "Этот игрок уже добавлен"


def parse_query(query: str) -> str:
    """Ник из строки поиска: принимает ник или ссылку на профиль FACEIT (S01)"""
    query = query.strip()
    if query.startswith(("http://", "https://")):
        url = urlparse(query)
        host = (url.hostname or "").lower()
        if host != "faceit.com" and not host.endswith(".faceit.com"):
            raise InvalidInput("Ссылка должна вести на профиль faceit.com")
        parts = [part for part in url.path.split("/") if part]
        if "players" not in parts or parts.index("players") + 1 >= len(parts):
            raise InvalidInput("В ссылке нет ника игрока: ожидается …/players/<ник>")
        query = parts[parts.index("players") + 1]
    if not NICKNAME_RE.fullmatch(query):
        raise InvalidInput("Ник может содержать латиницу, цифры, «_», «-», «.» (2–32 символа)")
    return query


def _source_unavailable() -> SourceUnavailable:
    return SourceUnavailable(
        "Не удалось получить данные FACEIT. Повторите запрос позже",
        headers={"Retry-After": RETRY_AFTER_SECONDS},
    )


def _apply_profile(player: Player, profile: FaceitPlayer) -> None:
    player.nickname = profile.nickname
    player.country = profile.country
    player.faceit_url = profile.faceit_url
    player.elo = profile.elo
    player.skill_level = profile.skill_level


def _apply_history(db: Session, player: Player, history: MatchHistory) -> None:
    previous_latest = matches.latest_finished_at(db, player.id)
    matches.upsert_many(db, player.id, history.matches)

    oldest = min((m.finished_at for m in history.matches), default=None)
    if history.reached_end:
        player.history_complete = True
        player.coverage_from = oldest
    elif previous_latest is not None and oldest is not None and oldest <= previous_latest:
        # Новая порция пересекается с сохранённой - история непрерывна, покрытие прежнее
        player.coverage_from = player.coverage_from or oldest
    else:
        # Разрыв: между сохранёнными и новыми матчами могли быть пропущенные игры
        player.history_complete = False
        player.coverage_from = oldest
    player.synced_at = datetime.now(UTC)


def create(db: Session, client: FaceitClient, user: User, query: str, note: str | None) -> Player:
    nickname = parse_query(query)
    try:
        profile = client.find_player(nickname)
        if players.get_by_faceit_id(db, user.id, profile.faceit_id) is not None:
            raise Conflict(ALREADY_TRACKED)
        history = client.get_match_history(profile.faceit_id)
    except FaceitPlayerNotFoundError as exc:
        raise PlayerNotFoundInSource(f"Игрок «{nickname}» не найден на FACEIT") from exc
    except FaceitUnavailableError as exc:
        raise _source_unavailable() from exc

    player = Player(user_id=user.id, faceit_id=profile.faceit_id, note=note)
    _apply_profile(player, profile)
    db.add(player)
    db.flush()
    _apply_history(db, player, history)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(ALREADY_TRACKED) from exc
    return player


def sync(db: Session, client: FaceitClient, player: Player) -> Player:
    try:
        profile = client.get_player(player.faceit_id)
        history = client.get_match_history(player.faceit_id)
    except FaceitPlayerNotFoundError as exc:
        raise PlayerNotFoundInSource("Профиль больше не найден на FACEIT") from exc
    except FaceitUnavailableError as exc:
        # Сохранённые данные остаются с прежней отметкой synced_at (NFR06)
        raise _source_unavailable() from exc
    _apply_profile(player, profile)
    _apply_history(db, player, history)
    db.commit()
    return player


def update_note(db: Session, player: Player, note: str | None) -> Player:
    player.note = note
    db.commit()
    return player


def delete(db: Session, player: Player) -> None:
    db.delete(player)
    db.commit()
