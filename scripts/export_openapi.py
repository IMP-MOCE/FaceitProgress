"""Выгружает OpenAPI-спецификацию в docs/openapi.json

Запуск: python scripts/export_openapi.py
Тест tests/api/test_contract.py падает, если файл расходится с кодом.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# Для генерации схемы не нужны ни БД, ни настоящий секрет.
os.environ.setdefault("JWT_SECRET", "openapi-export-only-" + "x" * 32)
os.environ["DOCS_ENABLED"] = "true"

from app.main import create_app  # noqa: E402

spec = create_app().openapi()
target = ROOT / "docs" / "openapi.json"
target.parent.mkdir(exist_ok=True)
target.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"OpenAPI {spec['info']['version']}: {len(spec['paths'])} путей → {target}")
