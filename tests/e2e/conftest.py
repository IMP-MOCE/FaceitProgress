"""Сквозные тесты интерфейса: настоящий API на uvicorn + Chromium (Playwright)

Запуск: pytest -m e2e tests/e2e
Нужны: PostgreSQL (как для API-тестов) и браузер: python -m playwright install chromium
"""

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from sqlalchemy import text

from app.db.session import get_engine
from app.main import create_app
from tests.conftest import TABLES

playwright_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS = ROOT / "reports" / "screenshots"
PASSWORD = "correct-horse-battery"

pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@pytest.fixture(scope="session")
def live_server(migrated_db: None) -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:  # pragma: no cover - диагностика окружения
            raise RuntimeError("uvicorn не запустился за 15 секунд")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(autouse=True)
def clean_tables(live_server: str) -> Iterator[None]:
    yield
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def browser() -> Iterator[Any]:
    with playwright_api.sync_playwright() as pw:
        instance = pw.chromium.launch()
        yield instance
        instance.close()


class Ui:
    """Тонкая обёртка над страницей: ошибки JS, скриншоты, общие шаги"""

    def __init__(self, page: Any, base_url: str, name: str) -> None:
        self.page = page
        self.base_url = base_url
        self.name = name
        self.js_errors: list[str] = []
        page.on("pageerror", lambda error: self.js_errors.append(str(error)))
        page.on(
            "console",
            lambda msg: (
                self.js_errors.append(msg.text)
                if msg.type == "error" and "Content Security Policy" in msg.text
                else None
            ),
        )

    def open(self, hash_path: str = "") -> None:
        self.page.goto(f"{self.base_url}/{hash_path}")

    def shot(self, step: str) -> None:
        SCREENSHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SCREENSHOTS / f"{self.name}-{step}.png"), full_page=True)

    def register(self, email: str) -> None:
        self.open("#/register")
        self.page.fill("#auth-email", email)
        self.page.fill("#auth-password", PASSWORD)
        self.page.click("button[type=submit]")
        self.page.wait_for_selector("#player-query")

    def add_player(self, query: str) -> None:
        self.page.fill("#player-query", query)
        self.page.click("text=Найти и добавить")

    def token(self) -> str:
        value: str = self.page.evaluate("sessionStorage.getItem('fp.token')")
        return value

    def no_horizontal_scroll(self) -> bool:
        scroll, inner = self.page.evaluate(
            "[document.documentElement.scrollWidth, window.innerWidth]"
        )
        return bool(scroll <= inner)


@pytest.fixture
def ui_factory(browser: Any, live_server: str, request: pytest.FixtureRequest) -> Iterator[Any]:
    contexts = []

    def make(width: int = 1440, height: int = 900, name: str | None = None) -> Ui:
        context = browser.new_context(
            viewport={"width": width, "height": height},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )
        contexts.append(context)
        return Ui(context.new_page(), live_server, name or request.node.name)

    yield make
    for context in contexts:
        context.close()
