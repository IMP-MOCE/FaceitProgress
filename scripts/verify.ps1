# Полная проверка проекта на Windows одной командой:
#   powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
# Нужны: Docker Desktop (контейнер БД) и Python 3.12+ (лаунчер py).
# Результаты: reports\summary.md, reports\summary.json, reports\screenshots\

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "== База данных" -ForegroundColor Cyan
docker compose up -d db
if ($LASTEXITCODE -ne 0) { throw "Не удалось запустить контейнер db (Docker Desktop запущен?)" }

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "== Виртуальное окружение" -ForegroundColor Cyan
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Python не найден: установите Python 3.12+ (winget install Python.Python.3.13)" }
}

Write-Host "== Зависимости" -ForegroundColor Cyan
& $python -m pip install --upgrade pip
& $python -m pip install -e ".[dev,e2e]"
if ($LASTEXITCODE -ne 0) { throw "pip install завершился с ошибкой" }

Write-Host "== Браузер для e2e" -ForegroundColor Cyan
& $python -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Не удалось установить Chromium для Playwright" }

Write-Host "== Проверки" -ForegroundColor Cyan
& $python scripts\collect_reports.py --load-local
Write-Host "Готово: reports\summary.md" -ForegroundColor Green
