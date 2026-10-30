"""Нагрузочная проверка NFR02 из ПР1: 20 одновременных пользователей открывают сохранённый обзор

Запуск (сервис должен быть запущен, например docker compose up -d):
    python scripts/load_test.py --url http://localhost:8000 --users 20 --seconds 20

Порог NFR02: 95-й процентиль открытия обзора не больше 2 секунд.
Первый импорт игрока (POST /players) измеряется отдельно, как требует ПР1.
Результат печатается и сохраняется в reports/load.json.
"""

import argparse
import json
import statistics
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
P95_LIMIT_SECONDS = 2.0


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(share * len(ordered) + 0.5) - 1))
    return ordered[index]


def prepare(client: httpx.Client) -> tuple[dict[str, str], int, float]:
    email = f"load-{uuid.uuid4().hex[:8]}@example.com"
    password = "load-test-password"  # noqa: S105 - временный пользователь стенда
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token.raise_for_status()
    headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
    started = time.perf_counter()
    player = client.post("/api/v1/players", json={"query": "demo_player"}, headers=headers)
    first_import = time.perf_counter() - started
    player.raise_for_status()
    return headers, player.json()["id"], first_import


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--seconds", type=float, default=20.0)
    args = parser.parse_args()

    with httpx.Client(base_url=args.url, timeout=30) as client:
        headers, player_id, first_import = prepare(client)

    latencies: list[float] = []
    errors: list[str] = []
    lock = threading.Lock()
    stop_at = time.perf_counter() + args.seconds

    def worker() -> None:
        with httpx.Client(base_url=args.url, timeout=30, headers=headers) as client:
            while time.perf_counter() < stop_at:
                started = time.perf_counter()
                try:
                    response = client.get(f"/api/v1/players/{player_id}/stats")
                    elapsed = time.perf_counter() - started
                    with lock:
                        if response.status_code == 200:
                            latencies.append(elapsed)
                        else:
                            errors.append(str(response.status_code))
                except httpx.HTTPError as exc:
                    with lock:
                        errors.append(type(exc).__name__)

    threads = [threading.Thread(target=worker) for _ in range(args.users)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    duration = time.perf_counter() - started

    if not latencies:
        print("Нет успешных запросов:", errors[:5])
        return 1
    result = {
        "url": args.url,
        "users": args.users,
        "duration_s": round(duration, 1),
        "requests": len(latencies),
        "errors": len(errors),
        "rps": round(len(latencies) / duration, 1),
        "p50_ms": round(statistics.median(latencies) * 1000, 1),
        "p95_ms": round(percentile(latencies, 0.95) * 1000, 1),
        "p99_ms": round(percentile(latencies, 0.99) * 1000, 1),
        "max_ms": round(max(latencies) * 1000, 1),
        "first_import_ms": round(first_import * 1000, 1),
        "p95_limit_ms": P95_LIMIT_SECONDS * 1000,
    }
    result["passed"] = result["p95_ms"] <= result["p95_limit_ms"] and not errors
    out = ROOT / "reports" / "load.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("NFR02:", "выполнено" if result["passed"] else "НЕ выполнено")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
