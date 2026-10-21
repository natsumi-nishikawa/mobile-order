import pytest

from app.origin_config import get_allowed_origins, parse_allowed_origins


def test_origin_parser_accepts_and_normalizes_explicit_origins():
    assert parse_allowed_origins(
        "https://demo.example.com/,http://localhost:5173",
        "TEST_ORIGINS",
    ) == frozenset({"https://demo.example.com", "http://localhost:5173"})


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "demo.example.com",
        "ftp://demo.example.com",
        "https://user:password@demo.example.com",
        "https://demo.example.com/path",
        "https://demo.example.com?query=true",
        "https://demo.example.com/#fragment",
        "https://demo.example.com:invalid",
    ],
)
def test_origin_parser_rejects_wildcards_and_invalid_origins(value):
    with pytest.raises(RuntimeError):
        parse_allowed_origins(value, "TEST_ORIGINS")


def test_development_has_localhost_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("TEST_ORIGINS", raising=False)
    assert get_allowed_origins("TEST_ORIGINS") == frozenset({"http://localhost:5173"})


def test_production_requires_explicit_https_non_local_origin(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("TEST_ORIGINS", raising=False)
    with pytest.raises(RuntimeError):
        get_allowed_origins("TEST_ORIGINS")

    for invalid in ("http://demo.example.com", "https://localhost"):
        monkeypatch.setenv("TEST_ORIGINS", invalid)
        with pytest.raises(RuntimeError):
            get_allowed_origins("TEST_ORIGINS")

    monkeypatch.setenv("TEST_ORIGINS", "https://demo.example.com")
    assert get_allowed_origins("TEST_ORIGINS") == frozenset({"https://demo.example.com"})
