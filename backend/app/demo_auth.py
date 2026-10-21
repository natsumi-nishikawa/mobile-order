import hmac
import os
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request, Response

from app.origin_config import get_allowed_origins

COOKIE_NAME = "demo_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
ALGORITHM = "HS256"


@dataclass(frozen=True)
class DemoAuthSettings:
    password: str
    secret: str
    session_seconds: int
    cookie_secure: bool
    allowed_origins: frozenset[str]
    rate_limit_attempts: int
    rate_limit_window_seconds: int


@dataclass(frozen=True)
class DemoSession:
    session_id: str
    expires_at: int
    csrf_token: str


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


def get_demo_auth_settings() -> DemoAuthSettings:
    password = os.getenv("DEMO_AUTH_PASSWORD")
    secret = os.getenv("DEMO_AUTH_SECRET")
    origins = get_allowed_origins("DEMO_AUTH_ALLOWED_ORIGINS")
    if not password or not secret or not origins:
        raise RuntimeError("Demo authentication is not configured")
    if len(secret) < 32:
        raise RuntimeError("DEMO_AUTH_SECRET must be at least 32 characters")

    environment = os.getenv("APP_ENV", "production").lower()
    secure_value = os.getenv("DEMO_AUTH_COOKIE_SECURE", "true").lower()
    if secure_value not in {"true", "false"}:
        raise RuntimeError("DEMO_AUTH_COOKIE_SECURE must be true or false")
    cookie_secure = secure_value == "true"
    if not cookie_secure and environment not in {"development", "test"}:
        raise RuntimeError("Insecure demo cookies are only allowed in development or test")

    session_minutes = _positive_int("DEMO_AUTH_SESSION_MINUTES", 30)
    if session_minutes > 120:
        raise RuntimeError("DEMO_AUTH_SESSION_MINUTES must not exceed 120")
    return DemoAuthSettings(
        password=password,
        secret=secret,
        session_seconds=session_minutes * 60,
        cookie_secure=cookie_secure,
        allowed_origins=origins,
        rate_limit_attempts=_positive_int("DEMO_AUTH_RATE_LIMIT_ATTEMPTS", 5),
        rate_limit_window_seconds=_positive_int("DEMO_AUTH_RATE_LIMIT_WINDOW_SECONDS", 300),
    )


def require_demo_settings() -> DemoAuthSettings:
    try:
        return get_demo_auth_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="デモ認証を利用できません") from exc


class LoginRateLimiter:
    """Process-local failed-login limiter for the internal demo deployment."""

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()

    def check(self, key: str, settings: DemoAuthSettings) -> None:
        now = time.monotonic()
        cutoff = now - settings.rate_limit_window_seconds
        with self._lock:
            attempts = self._attempts.setdefault(key, deque())
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= settings.rate_limit_attempts:
                retry_after = max(1, int(attempts[0] + settings.rate_limit_window_seconds - now) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="ログイン試行回数が上限に達しました。しばらくしてから再試行してください",
                    headers={"Retry-After": str(retry_after)},
                )

    def record_failure(self, key: str, settings: DemoAuthSettings) -> None:
        now = time.monotonic()
        cutoff = now - settings.rate_limit_window_seconds
        with self._lock:
            attempts = self._attempts.setdefault(key, deque())
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= settings.rate_limit_attempts:
                retry_after = max(1, int(attempts[0] + settings.rate_limit_window_seconds - now) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="ログイン試行回数が上限に達しました。しばらくしてから再試行してください",
                    headers={"Retry-After": str(retry_after)},
                )
            attempts.append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


login_rate_limiter = LoginRateLimiter()


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def verify_request_origin(request: Request, settings: DemoAuthSettings) -> None:
    origin = request.headers.get("origin", "").rstrip("/")
    if not origin or origin not in settings.allowed_origins:
        raise HTTPException(status_code=403, detail="リクエストを許可できません")


def verify_password(candidate: str, settings: DemoAuthSettings) -> bool:
    return hmac.compare_digest(
        candidate.encode("utf-8"),
        settings.password.encode("utf-8"),
    )


def create_demo_session(settings: DemoAuthSettings) -> tuple[str, DemoSession]:
    now = int(time.time())
    expires_at = now + settings.session_seconds
    csrf_token = secrets.token_urlsafe(32)
    payload = {
        "type": "demo_session",
        "iat": now,
        "exp": expires_at,
        "jti": secrets.token_urlsafe(16),
        "csrf": csrf_token,
    }
    token = jwt.encode(payload, settings.secret, algorithm=ALGORITHM)
    return token, DemoSession(session_id=payload["jti"], expires_at=expires_at, csrf_token=csrf_token)


def decode_demo_session(token: str, settings: DemoAuthSettings) -> DemoSession:
    try:
        payload = jwt.decode(
            token,
            settings.secret,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "jti", "csrf", "type"]},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="デモ認証が必要です") from exc
    if payload.get("type") != "demo_session":
        raise HTTPException(status_code=401, detail="デモ認証が必要です")
    csrf_token = payload.get("csrf")
    expires_at = payload.get("exp")
    session_id = payload.get("jti")
    if not isinstance(csrf_token, str) or not isinstance(expires_at, int) or not isinstance(session_id, str):
        raise HTTPException(status_code=401, detail="デモ認証が必要です")
    return DemoSession(session_id=session_id, expires_at=expires_at, csrf_token=csrf_token)


def require_demo_session(
    demo_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> DemoSession:
    settings = require_demo_settings()
    if not demo_session:
        raise HTTPException(status_code=401, detail="デモ認証が必要です")
    return decode_demo_session(demo_session, settings)


def require_demo_csrf(
    request: Request,
    session: Annotated[DemoSession, Depends(require_demo_session)],
    settings: Annotated[DemoAuthSettings, Depends(require_demo_settings)],
    csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
) -> DemoSession:
    verify_request_origin(request, settings)
    if not csrf_token or not hmac.compare_digest(csrf_token, session.csrf_token):
        raise HTTPException(status_code=403, detail="リクエストを許可できません")
    return session


def set_demo_cookie(response: Response, token: str, settings: DemoAuthSettings) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.session_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_demo_cookie(response: Response, settings: DemoAuthSettings) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
