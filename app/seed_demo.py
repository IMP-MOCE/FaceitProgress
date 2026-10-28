"""Подготовка демонстрационного аккаунта для защиты.

Запуск: python -m app.seed_demo   (в контейнере: docker compose exec api python -m app.seed_demo)

Создаёт пользователя с игроком demo_player и целью, поставленной «в прошлом»,
чтобы показать готовое сравнение прогресса без 20 реально сыгранных матчей.
Данные помечены как демонстрационные (ПР1, раздел 11) и не выдаются за эффект тренировок.
Повторный запуск пересоздаёт аккаунт с нуля
"""

from datetime import timedelta

from app.clients.fixtures import FixtureFaceitClient
from app.db.session import get_sessionmaker
from app.repositories import matches, users
from app.services import auth, goals, players

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password-2026"  # noqa: S105 - учётная запись только для локального демо


def main() -> None:
    db = get_sessionmaker()()
    try:
        existing = users.get_by_email(db, DEMO_EMAIL)
        if existing is not None:
            auth.delete_account(db, existing)
        user = auth.register(db, DEMO_EMAIL, DEMO_PASSWORD)
        player = players.create(db, FixtureFaceitClient(), user, "demo_player", "Демо-профиль")

        history, _ = matches.list_filtered(db, player.id)
        # Цель «поставлена» между 26-м и 25-м матчами с конца: до неё 20+ матчей исходной
        # выборки, после - ровно 25 матчей, из которых первые 20 образуют новую выборку
        started_at = history[25].finished_at + timedelta(minutes=1)
        goal = goals.create(
            db,
            user,
            player,
            metric="win_rate",
            map_name=None,
            action="[ДЕМО] Пересмотреть 3 последних поражения и выписать повторяющиеся ситуации",
            replace_active=False,
            started_at=started_at,
        )
        result = goals.progress(db, goal, player)
        print(f"Пользователь: {DEMO_EMAIL} (пароль - в app/seed_demo.py)")
        print(f"Игрок id={player.id}, цель id={goal.id}, статус прогресса: {result.status}")
        print(
            f"Доля побед: {result.baseline.value}% → "
            f"{result.followup.value if result.followup else '-'}% "
            f"(изменение {result.change} п.п.)"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
