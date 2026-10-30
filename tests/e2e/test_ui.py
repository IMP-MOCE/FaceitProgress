"""Пользовательские сценарии ПР1 в браузере: путь проходит, состояния обработаны"""

import re
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from app.db.session import get_sessionmaker
from app.models import Match

pytestmark = pytest.mark.e2e


def fmt_pct(value: float) -> str:
    """Как fmtPct в интерфейсе: 55 → «55%», 52.5 → «52,5%»"""
    rounded = round(value, 1)
    text = f"{rounded:.0f}" if rounded == int(rounded) else f"{rounded:.1f}".replace(".", ",")
    return f"{text}%"


def api_get(ui: Any, path: str) -> dict[str, Any]:
    response = httpx.get(
        f"{ui.base_url}/api/v1{path}", headers={"Authorization": f"Bearer {ui.token()}"}
    )
    response.raise_for_status()
    body: dict[str, Any] = response.json()
    return body


def test_main_scenario(ui_factory: Any) -> None:
    """Вход → игрок по ссылке → обзор → фильтр → сравнение → карты → сводка → цель → выход"""
    ui = ui_factory(name="desktop")
    page = ui.page
    ui.open()
    page.wait_for_selector("h1:has-text('Вход')")
    ui.shot("01-login")

    ui.register("e2e-main@example.com")
    ui.shot("02-players-empty")
    ui.add_player("https://www.faceit.com/ru/players/demo_player")
    page.wait_for_selector("#player-name:has-text('demo_player')")
    page.wait_for_selector("[data-testid=metric-win-rate] .metric__value")
    page.wait_for_selector("table.table--matches tbody tr")

    # Обзор совпадает с ответом API: тот же расчёт, без пересчёта в браузере
    player_id = int(re.search(r"#/players/(\d+)", page.url).group(1))  # type: ignore[union-attr]
    stats = api_get(ui, f"/players/{player_id}/stats")
    assert page.inner_text("[data-testid=metric-win-rate] .metric__value") == fmt_pct(
        stats["win_rate"]["value"]
    )
    assert page.inner_text("[data-testid=metric-matches] .metric__value") == "20"
    assert "Загружены последние матчи" in page.inner_text(".player-head")
    ui.shot("03-overview")

    # Фильтр карты применяется и к показателям, и к списку (S04)
    page.select_option("#filter-map", "de_mirage")
    page.click("text=Применить")
    page.wait_for_function(
        """() => {
            const sel = "table.table--matches td[data-label='Карта']";
            const cells = [...document.querySelectorAll(sel)];
            return cells.length > 0 && cells.every((c) => c.textContent === "de_mirage");
        }"""
    )
    maps = page.locator("table.table--matches tbody td[data-label='Карта']").all_inner_texts()
    assert maps and set(maps) == {"de_mirage"}
    ui.shot("04-filter-map")

    page.click("#tab-compare")
    page.select_option("#compare-map", "")
    page.wait_for_selector("[data-testid=compare-changes]")
    assert "Последние 20 матчей" in page.inner_text("#player-tabpanel")
    ui.shot("05-compare")

    page.click("#tab-maps")
    page.wait_for_selector("table.table--maps tbody tr")
    ui.shot("06-maps")

    page.click("#tab-insights")
    page.wait_for_selector("[data-testid=insight], .state--empty")
    ui.shot("07-insights")

    page.click("text=Поставить цель")
    page.wait_for_selector("[data-testid=goal-baseline]")
    page.fill("textarea[name=action]", "Пересмотреть 3 последних поражения")
    ui.shot("08-goal-form")
    page.click("text=Сохранить цель")
    page.wait_for_selector("[data-testid=goal-progress] .progress")
    assert "Сыграно 0 из 20" in page.inner_text("[data-testid=goal-progress]")
    assert page.inner_text("[data-testid=goal-baseline-value]") == fmt_pct(
        stats["win_rate"]["value"]
    )
    ui.shot("09-goal-collecting")

    page.click("text=Выйти")
    page.wait_for_selector("h1:has-text('Вход')")
    ui.open("#/goals")
    page.wait_for_url(re.compile(r"#/login"))
    assert ui.js_errors == []


def test_goal_from_recommendation_and_replace(ui_factory: Any) -> None:
    """Рекомендация → цель (S10 → S11); вторая цель требует явной замены (S11, крит. 3)"""
    ui = ui_factory()
    page = ui.page
    ui.register("e2e-goal@example.com")
    ui.add_player("demo_player")
    page.wait_for_selector("#player-name")
    page.click("text=Поставить цель")
    page.fill("textarea[name=action]", "Первая цель")
    page.click("text=Сохранить цель")
    page.wait_for_selector("[data-testid=goal-progress]")

    page.go_back()
    page.wait_for_selector("text=Поставить цель")
    page.click("text=Поставить цель")
    page.fill("textarea[name=action]", "Вторая цель")
    page.check("input[value=kd]")
    page.click("text=Сохранить цель")
    page.wait_for_selector("text=У вас уже есть активная цель")
    ui.shot("goal-409-replace")
    page.check("input[name=replace_active]")
    page.click("text=Сохранить цель")
    page.wait_for_selector("h1:has-text('Цель: K/D')")
    goals = api_get(ui, "/goals")
    assert sorted(g["status"] for g in goals["items"]) == ["active", "archived"]
    assert ui.js_errors == []


def test_goal_progress_ready(ui_factory: Any) -> None:
    """Готовое сравнение цели показывает было/стало и изменение словами (S12)"""
    ui = ui_factory(name="goal-ready")
    page = ui.page
    ui.register("e2e-ready@example.com")
    ui.add_player("demo_player")
    page.wait_for_selector("#player-name")
    player_id = int(re.search(r"#/players/(\d+)", page.url).group(1))  # type: ignore[union-attr]
    response = httpx.post(
        f"{ui.base_url}/api/v1/goals",
        json={"player_id": player_id, "metric": "win_rate", "action": "Разбор поражений"},
        headers={"Authorization": f"Bearer {ui.token()}"},
    )
    goal = response.json()
    started = datetime.fromisoformat(goal["started_at"])
    session: Session = get_sessionmaker()()
    for i in range(20):
        session.add(
            Match(
                player_id=player_id,
                faceit_match_id=f"e2e-after-{i}",
                finished_at=started + timedelta(hours=i + 1),
                map="de_mirage",
                won=i % 4 != 0,
                kills=20,
                deaths=15,
            )
        )
    session.commit()
    session.close()

    ui.open(f"#/goals/{goal['id']}")
    page.wait_for_selector("[data-testid=goal-change]")
    change = page.inner_text("[data-testid=goal-change]")
    assert re.search(r"(рост|снижение|без изменений)", change)
    assert "75%" in page.inner_text("[data-testid=goal-progress]")
    ui.shot("01-progress")
    assert ui.js_errors == []


def test_error_and_empty_states(ui_factory: Any) -> None:
    """Пустой ввод, «не найден», сбой источника, неверный пароль, нет матчей CS2 (S01)"""
    ui = ui_factory(name="states")
    page = ui.page
    ui.register("e2e-states@example.com")

    posts: list[str] = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    page.click("text=Найти и добавить")
    page.wait_for_selector("text=Введите ник или ссылку на профиль FACEIT")
    page.wait_for_timeout(300)
    # Пустой ввод не отправляет запрос (S01, критерий 2)
    assert posts == []
    ui.shot("01-empty-query")

    ui.add_player("nobody_here")
    page.wait_for_selector(".state--error[data-status='404']")
    assert "Игрок не найден" in page.inner_text(".state--error")

    ui.add_player("source_down")
    page.wait_for_selector(".state--error[data-status='503']")
    error = page.inner_text(".state--error")
    assert "временно недоступен" in error
    assert page.locator(".state--error button:has-text('Повторить')").count() == 1
    ui.shot("02-source-down")

    ui.add_player("no_cs2_player")
    page.wait_for_selector("#player-name")
    page.wait_for_selector("text=нет завершённых матчей CS2")
    ui.shot("03-no-cs2")

    page.click("text=Выйти")
    page.wait_for_selector("#auth-email")
    page.fill("#auth-email", "e2e-states@example.com")
    page.fill("#auth-password", "wrong-password")
    page.click("button[type=submit]")
    page.wait_for_selector("text=Неверный email или пароль")
    ui.shot("04-wrong-password")
    assert ui.js_errors == []


@pytest.mark.parametrize("width", [360, 768, 1440])
def test_responsive_layout(ui_factory: Any, width: int) -> None:
    """Основной путь без горизонтальной прокрутки; кнопки не меньше 44 px (S05, NFR01)"""
    ui = ui_factory(width=width, height=800, name=f"w{width}")
    page = ui.page
    ui.register(f"e2e-{width}@example.com")
    assert ui.no_horizontal_scroll()
    ui.add_player("demo_player")
    page.wait_for_selector("table.table--matches tbody tr")
    assert ui.no_horizontal_scroll()
    small = page.evaluate(
        """[...document.querySelectorAll('.btn, .tab, input, select')]
            .filter(el => el.offsetParent !== null)
            .map(el => el.getBoundingClientRect())
            .filter(r => r.height < 44).length"""
    )
    assert small == 0
    ui.shot("player")
    for tab in ("compare", "maps", "insights"):
        page.click(f"#tab-{tab}")
        page.wait_for_selector("#player-tabpanel:not(:has(.state--loading))")
        assert ui.no_horizontal_scroll(), tab
    assert ui.js_errors == []


def test_expired_session_returns_to_login(ui_factory: Any) -> None:
    ui = ui_factory()
    page = ui.page
    ui.register("e2e-expired@example.com")
    page.evaluate("sessionStorage.setItem('fp.token', 'forged.token.value')")
    ui.open("#/goals")
    page.wait_for_selector("text=Сессия завершена или истекла")
    assert "next=%2Fgoals" in page.url


def test_compare_with_too_few_matches(ui_factory: Any) -> None:
    ui = ui_factory()
    page = ui.page
    ui.register("e2e-newbie@example.com")
    ui.add_player("newbie_player")
    page.wait_for_selector("#player-name")
    page.wait_for_selector("text=Доступно 8 из 20 матчей обзора")
    page.click("#tab-compare")
    page.wait_for_selector("text=Недостаточно матчей для сравнения")
    assert "доступно 8" in page.inner_text("#player-tabpanel")
    page.click("#tab-insights")
    page.wait_for_selector("text=Недостаточно данных для сводки")
