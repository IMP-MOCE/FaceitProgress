"""Веб-интерфейс раздаётся тем же сервисом и защищён своей CSP"""

from fastapi.testclient import TestClient

from app.main import UI_CSP


def test_index_is_served_with_strict_csp(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "FACEIT Progress" in response.text
    csp = response.headers["Content-Security-Policy"]
    assert csp == UI_CSP
    # Ни inline-скриптов, ни сторонних источников
    assert "unsafe-inline" not in csp and "http" not in csp
    assert "frame-ancestors 'none'" in csp


def test_static_assets_are_served(client: TestClient) -> None:
    script = client.get("/js/main.js")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert client.get("/css/app.css").status_code == 200


def test_api_keeps_its_own_policy(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.headers["Content-Security-Policy"] == "default-src 'none'"
    assert response.headers["Cache-Control"] == "no-store"


def test_unknown_path_is_problem_json(client: TestClient) -> None:
    for path in ("/no-such-file.js", "/api/v1/no-such-endpoint"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.headers["content-type"] == "application/problem+json"


def test_index_has_no_inline_code(client: TestClient) -> None:
    html = client.get("/").text
    assert "<script>" not in html and "style=" not in html
    assert '<script type="module" src="js/main.js">' in html
