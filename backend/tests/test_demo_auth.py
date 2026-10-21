from datetime import datetime, timedelta, timezone

import jwt
import pytest
from app.demo_auth import ALGORITHM, COOKIE_NAME, login_rate_limiter
from app.main import app
from fastapi.testclient import TestClient

ORIGIN = "http://localhost:5173"
PASSWORD = "internal-demo-password"
SECRET = "test-demo-secret-that-is-longer-than-32-characters"


@pytest.fixture(autouse=True)
def demo_auth_environment(monkeypatch):
    values = {
        "APP_ENV": "test",
        "DEMO_AUTH_PASSWORD": PASSWORD,
        "DEMO_AUTH_SECRET": SECRET,
        "DEMO_AUTH_SESSION_MINUTES": "30",
        "DEMO_AUTH_ALLOWED_ORIGINS": ORIGIN,
        "DEMO_AUTH_COOKIE_SECURE": "false",
        "DEMO_AUTH_RATE_LIMIT_ATTEMPTS": "3",
        "DEMO_AUTH_RATE_LIMIT_WINDOW_SECONDS": "300",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    login_rate_limiter.reset()
    yield
    login_rate_limiter.reset()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, password: str = PASSWORD):
    return client.post(
        "/api/demo-auth/login",
        json={"password": password},
        headers={"Origin": ORIGIN},
    )


def test_login_sets_signed_httponly_cookie_and_returns_csrf(client):
    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["expires_at"] > int(datetime.now(timezone.utc).timestamp())
    assert len(body["csrf_token"]) >= 32
    set_cookie = response.headers["set-cookie"]
    assert f"{COOKIE_NAME}=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Secure" not in set_cookie

    payload = jwt.decode(response.cookies[COOKIE_NAME], SECRET, algorithms=[ALGORITHM])
    assert payload["type"] == "demo_session"
    assert payload["csrf"] == body["csrf_token"]
    assert "password" not in payload


def test_wrong_password_and_origin_are_rejected_without_cookie(client):
    wrong = login(client, "wrong-password")
    assert wrong.status_code == 401
    assert COOKIE_NAME not in wrong.cookies

    missing_origin = client.post(
        "/api/demo-auth/login", json={"password": PASSWORD}
    )
    assert missing_origin.status_code == 403

    invalid_origin = client.post(
        "/api/demo-auth/login",
        json={"password": PASSWORD},
        headers={"Origin": "https://attacker.example"},
    )
    assert invalid_origin.status_code == 403


def test_session_requires_valid_unexpired_cookie(client):
    assert client.get("/api/demo-auth/session").status_code == 401

    logged_in = login(client)
    csrf_token = logged_in.json()["csrf_token"]
    current = client.get("/api/demo-auth/session")
    assert current.status_code == 200
    assert current.json()["csrf_token"] == csrf_token

    client.cookies.set(COOKIE_NAME, "invalid-token")
    assert client.get("/api/demo-auth/session").status_code == 401

    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {
            "type": "demo_session",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "jti": "expired",
            "csrf": "expired-csrf-token",
        },
        SECRET,
        algorithm=ALGORITHM,
    )
    client.cookies.set(COOKIE_NAME, expired)
    assert client.get("/api/demo-auth/session").status_code == 401


def test_logout_requires_csrf_and_clears_browser_cookie(client):
    logged_in = login(client)
    csrf_token = logged_in.json()["csrf_token"]

    assert client.post("/api/demo-auth/logout").status_code == 403
    assert client.post(
        "/api/demo-auth/logout", headers={"X-CSRF-Token": "wrong"}
    ).status_code == 403
    assert client.post(
        "/api/demo-auth/logout",
        headers={
            "X-CSRF-Token": csrf_token,
            "Origin": "https://attacker.example",
        },
    ).status_code == 403

    response = client.post(
        "/api/demo-auth/logout",
        headers={"X-CSRF-Token": csrf_token, "Origin": ORIGIN},
    )
    assert response.status_code == 200
    assert response.json() == {"authenticated": False}
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/api/demo-auth/session").status_code == 401


def test_failed_login_attempts_are_rate_limited_per_process(client):
    for _ in range(3):
        assert login(client, "wrong-password").status_code == 401

    limited = login(client, PASSWORD)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0


def test_missing_configuration_fails_closed(client, monkeypatch):
    monkeypatch.delenv("DEMO_AUTH_PASSWORD")
    response = login(client)
    assert response.status_code == 503
    assert response.json() == {"detail": "デモ認証を利用できません"}


def test_insecure_cookie_setting_is_rejected_outside_development(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEMO_AUTH_COOKIE_SECURE", "false")
    response = login(client)
    assert response.status_code == 503


def test_production_cookie_is_secure(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEMO_AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("DEMO_AUTH_ALLOWED_ORIGINS", "https://demo.example.com")
    response = client.post(
        "/api/demo-auth/login",
        json={"password": PASSWORD},
        headers={"Origin": "https://demo.example.com"},
    )
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]
