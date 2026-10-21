import os

import pytest

# Test-only demo authentication configuration. Production configuration is
# intentionally never given a fallback by the application.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEMO_AUTH_PASSWORD", "test-demo-password")
os.environ.setdefault(
    "DEMO_AUTH_SECRET", "test-demo-secret-that-is-longer-than-32-characters"
)
os.environ.setdefault("DEMO_AUTH_SESSION_MINUTES", "30")
os.environ.setdefault("DEMO_AUTH_ALLOWED_ORIGINS", "http://localhost:5173")
os.environ.setdefault("DEMO_AUTH_COOKIE_SECURE", "false")
os.environ.setdefault("DEMO_AUTH_RATE_LIMIT_ATTEMPTS", "5")
os.environ.setdefault("DEMO_AUTH_RATE_LIMIT_WINDOW_SECONDS", "300")


@pytest.fixture(autouse=True)
def reset_api_rate_limiter():
    from app.rate_limit import api_rate_limiter

    api_rate_limiter.reset()
    yield
    api_rate_limiter.reset()
