from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_cors_preflight_allows_localhost_and_loopback_origins() -> None:
    client = TestClient(app)

    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        response = client.options(
            "/api/v1/memory/default-session",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == origin


def test_cors_preflight_allows_unknown_origin_when_permissive_mode_enabled() -> None:
    client = TestClient(app)

    response = client.options(
        "/api/v1/memory/default-session",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://evil.example"
