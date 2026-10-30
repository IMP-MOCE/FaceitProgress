"""Один прогон всех проверок для отчёта: линтеры, тесты, покрытие, e2e, нагрузка

Запуск из корня репозитория (нужен PostgreSQL: docker compose up -d db):
    python scripts/collect_reports.py
    python scripts/collect_reports.py --load-url http://localhost:8000   # + нагрузка на сервис
    python scripts/collect_reports.py --load-local   # + нагрузка на локальный uvicorn

Результаты: reports/summary.md и reports/summary.json, JUnit XML, coverage.xml,
скриншоты интерфейса из e2e - reports/screenshots/.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
PY = sys.executable
TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://faceit:faceit@localhost:15432/faceit_test"
)
LOCAL_PORT = 8765


def run(name: str, command: list[str]) -> dict[str, object]:
    print(f"\n=== {name}: {' '.join(command)}", flush=True)
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=ROOT, check=False)  # noqa: S603 - фиксированные команды
    return {
        "name": name,
        "ok": completed.returncode == 0,
        "seconds": round(time.perf_counter() - started, 1),
    }


def run_local_load() -> dict[str, object]:
    """Поднимает API на тестовой БД (схема уже применена pytest) и запускает нагрузку"""
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DB,
        "FACEIT_API_KEY": "",
        "JWT_SECRET": os.environ.get("JWT_SECRET", "load-test-only-secret-" + "x" * 32),
    }
    server = subprocess.Popen(  # noqa: S603 - фиксированная команда
        [PY, "-m", "uvicorn", "app.main:app", "--port", str(LOCAL_PORT), "--log-level", "warning"],
        cwd=ROOT,
        env=env,
    )
    url = f"http://127.0.0.1:{LOCAL_PORT}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/api/v1/health", timeout=1)  # noqa: S310
                break
            except OSError:
                time.sleep(0.2)
        return run("load", [PY, "scripts/load_test.py", "--url", url])
    finally:
        server.terminate()
        server.wait(timeout=10)


def junit(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    root = ET.parse(path).getroot()  # noqa: S314 - собственный файл pytest
    suite = root if root.tag == "testsuite" else root[0]
    return {key: int(suite.get(key, 0)) for key in ("tests", "failures", "errors", "skipped")} | {
        "time_s": round(float(suite.get("time", 0)), 1)
    }


def coverage(path: Path) -> float | None:
    if not path.exists():
        return None
    rate = ET.parse(path).getroot().get("line-rate")  # noqa: S314
    return round(float(rate or 0) * 100, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--load-url", help="адрес запущенного сервиса для нагрузочного теста")
    parser.add_argument(
        "--load-local",
        action="store_true",
        help="запустить API локально на тестовой БД и выполнить нагрузочный тест",
    )
    parser.add_argument("--skip-e2e", action="store_true")
    args = parser.parse_args()
    REPORTS.mkdir(exist_ok=True)
    shutil.rmtree(REPORTS / "screenshots", ignore_errors=True)

    steps = [
        run("openapi", [PY, "scripts/export_openapi.py"]),
        run("ruff check", [PY, "-m", "ruff", "check", "."]),
        run("ruff format", [PY, "-m", "ruff", "format", "--check", "."]),
        run("mypy", [PY, "-m", "mypy"]),
        run(
            "pytest",
            [
                PY, "-m", "pytest",
                "--cov=app", "--cov-report=term-missing",
                f"--cov-report=xml:{REPORTS / 'coverage.xml'}",
                f"--junitxml={REPORTS / 'junit.xml'}",
            ],
        ),
    ]  # fmt: skip
    if not args.skip_e2e:
        steps.append(
            run(
                "e2e",
                [PY, "-m", "pytest", "-m", "e2e", "tests/e2e", f"--junitxml={REPORTS / 'e2e.xml'}"],
            )
        )
    if args.load_url:
        steps.append(run("load", [PY, "scripts/load_test.py", "--url", args.load_url]))
    elif args.load_local:
        steps.append(run_local_load())

    load_path = REPORTS / "load.json"
    summary = {
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "environment": (
            f"{platform.system()} {platform.release()}, Python {platform.python_version()}"
        ),
        "steps": steps,
        "tests": junit(REPORTS / "junit.xml"),
        "e2e": junit(REPORTS / "e2e.xml"),
        "coverage_percent": coverage(REPORTS / "coverage.xml"),
        "load": json.loads(load_path.read_text(encoding="utf-8"))
        if (args.load_url or args.load_local) and load_path.exists()
        else None,
        "screenshots": sorted(p.name for p in (REPORTS / "screenshots").glob("*.png")),
    }
    (REPORTS / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        f"# Прогон проверок {summary['date']}",
        "",
        f"Окружение: {summary['environment']}",
        "",
        "| Шаг | Результат | Время, с |",
        "|---|---|---|",
        *[f"| {s['name']} | {'OK' if s['ok'] else 'ОШИБКА'} | {s['seconds']} |" for s in steps],
        "",
        f"Тесты: {summary['tests']}",
        f"E2E: {summary['e2e']}",
        f"Покрытие строк: {summary['coverage_percent']}%",
        f"Нагрузка: {summary['load']}",
    ]
    (REPORTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if all(s["ok"] for s in steps) else 1


if __name__ == "__main__":
    sys.exit(main())
