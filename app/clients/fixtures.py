"""Встроенные демонстрационные данные вместо FACEIT API.

Используются, когда FACEIT_API_KEY не задан: локальная разработка, тесты, защита.
Данные детерминированы - один и тот же ник всегда даёт одни и те же матчи.
Все профили вымышленные и помечены префиксом в faceit_id
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.clients.faceit import (
    HISTORY_LIMIT,
    FaceitMatch,
    FaceitPlayer,
    FaceitPlayerNotFoundError,
    FaceitUnavailableError,
    MatchHistory,
)

MAPS = ("de_mirage", "de_inferno", "de_nuke", "de_ancient", "de_anubis", "de_dust2", "de_train")
# Как у реальных игроков, одна карта основная: на ней хватает матчей для цели в контексте карты
MAP_WEIGHTS = (35, 12, 11, 11, 11, 11, 9)
# Фиксированная точка отсчёта: последний матч каждого демо-игрока завершён в это время
ANCHOR = datetime(2026, 10, 20, 18, 0, tzinfo=UTC)
MATCH_INTERVAL = timedelta(hours=9)


@dataclass(frozen=True)
class _Spec:
    match_count: int
    win_chance: float
    elo: int | None
    # Индексы матчей (0 - самый свежий) без данных об убийствах/смертях и без результата
    missing_kd: frozenset[int] = frozenset()
    missing_result: frozenset[int] = frozenset()


SPECS: dict[str, _Spec] = {
    # 120 матчей: история длиннее лимита API в 100, покрытие неполное
    "demo_player": _Spec(match_count=120, win_chance=0.55, elo=1850),
    # Пропуски данных среди последних 20 матчей (S02, критерий 4)
    "patchy_player": _Spec(
        match_count=30,
        win_chance=0.5,
        elo=1320,
        missing_kd=frozenset({3, 11}),
        missing_result=frozenset({7}),
    ),
    # Меньше 20 матчей (S02, критерий 2)
    "newbie_player": _Spec(match_count=8, win_chance=0.4, elo=900),
    # Профиль без матчей CS2 (S01, критерий 5)
    "no_cs2_player": _Spec(match_count=0, win_chance=0.0, elo=None),
}
# Ник, на котором демонстрируется недоступность источника (S01, критерий 4)
UNAVAILABLE_NICKNAME = "source_down"


def _generate(nickname: str, spec: _Spec) -> list[FaceitMatch]:
    rng = random.Random(f"faceit-progress:{nickname}")  # noqa: S311 - не криптография
    matches = []
    for index in range(spec.match_count):
        won = rng.random() < spec.win_chance
        deaths = rng.randint(10, 24)
        kills = max(0, deaths + rng.randint(-6, 8) + (3 if won else -2))
        matches.append(
            FaceitMatch(
                match_id=f"demo-{nickname}-{spec.match_count - index:04d}",
                finished_at=ANCHOR - MATCH_INTERVAL * index,
                map=rng.choices(MAPS, weights=MAP_WEIGHTS)[0],
                won=None if index in spec.missing_result else won,
                kills=None if index in spec.missing_kd else kills,
                deaths=None if index in spec.missing_kd else deaths,
            )
        )
    return matches


class FixtureFaceitClient:
    def find_player(self, nickname: str) -> FaceitPlayer:
        key = nickname.lower()
        if key == UNAVAILABLE_NICKNAME:
            raise FaceitUnavailableError("fixture: source is down")
        spec = SPECS.get(key)
        if spec is None:
            raise FaceitPlayerNotFoundError(nickname)
        return FaceitPlayer(
            faceit_id=f"demo-{key}",
            nickname=key,
            country="ru",
            faceit_url=f"https://www.faceit.com/en/players/{key}",
            elo=spec.elo,
            skill_level=None if spec.elo is None else min(10, max(1, spec.elo // 200)),
        )

    def get_player(self, faceit_id: str) -> FaceitPlayer:
        return self.find_player(faceit_id.removeprefix("demo-"))

    def get_match_history(self, faceit_id: str, limit: int = HISTORY_LIMIT) -> MatchHistory:
        nickname = faceit_id.removeprefix("demo-")
        spec = SPECS.get(nickname)
        if spec is None:
            raise FaceitPlayerNotFoundError(faceit_id)
        matches = _generate(nickname, spec)
        return MatchHistory(matches=matches[:limit], reached_end=len(matches) <= limit)
