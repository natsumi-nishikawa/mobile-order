import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.runtime_config import (
    FORBIDDEN_PRODUCTION_AWS_CREDENTIAL_VARIABLES,
    FORBIDDEN_PRODUCTION_DATABASE_VARIABLES,
    PRODUCTION_REQUIRED_VARIABLES,
    api_documentation_urls,
    validate_production_environment,
)


def configure_valid_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    for name in PRODUCTION_REQUIRED_VARIABLES:
        monkeypatch.setenv(name, f"configured-{name.lower()}")
    monkeypatch.setenv("DEMO_AUTH_COOKIE_SECURE", "true")
    for name in FORBIDDEN_PRODUCTION_AWS_CREDENTIAL_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name in FORBIDDEN_PRODUCTION_DATABASE_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def test_production_disables_api_documentation(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    urls = {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }
    assert api_documentation_urls() == urls
    production_app = FastAPI(**urls)
    assert {route.path for route in production_app.routes}.isdisjoint(
        {"/docs", "/redoc", "/openapi.json"}
    )


def test_development_keeps_api_documentation(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    assert api_documentation_urls() == {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }


def test_test_environment_app_keeps_docs_and_has_minimal_health_response():
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert {"/docs", "/redoc", "/openapi.json"}.issubset(paths)
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_production_application_import_has_no_documentation_routes():
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://user:password@127.0.0.1/app",
            "CUSTOMER_JWT_SECRET": "customer-secret-placeholder-for-import-test",
            "CUSTOMER_WS_ALLOWED_ORIGINS": "https://app.example.test",
            "CORS_ALLOWED_ORIGINS": "https://app.example.test",
            "DEMO_AUTH_PASSWORD": "demo-password-placeholder",
            "DEMO_AUTH_SECRET": "demo-secret-placeholder-that-is-long-enough",
            "DEMO_AUTH_ALLOWED_ORIGINS": "https://app.example.test",
            "DEMO_AUTH_COOKIE_SECURE": "true",
            "AWS_REGION": "ap-northeast-1",
            "AWS_S3_BUCKET_NAME": "placeholder-product-images",
            "COGNITO_USER_POOL_ID": "ap-northeast-1_placeholder",
            "COGNITO_APP_CLIENT_ID": "placeholder-client-id",
        }
    )
    for name in FORBIDDEN_PRODUCTION_AWS_CREDENTIAL_VARIABLES:
        environment.pop(name, None)
    code = (
        "from app.main import app; "
        "paths={getattr(route, 'path', None) for route in app.routes}; "
        "assert not paths.intersection({'/docs','/redoc','/openapi.json'}); "
        "assert '/api/health' in paths"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_production_requires_all_runtime_configuration(monkeypatch):
    configure_valid_production(monkeypatch)
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        validate_production_environment()


def test_production_requires_secure_demo_cookie(monkeypatch):
    configure_valid_production(monkeypatch)
    monkeypatch.setenv("DEMO_AUTH_COOKIE_SECURE", "false")
    with pytest.raises(RuntimeError, match="DEMO_AUTH_COOKIE_SECURE"):
        validate_production_environment()


@pytest.mark.parametrize(
    ("variable", "placeholder"),
    [
        ("CUSTOMER_JWT_SECRET", "REPLACE_WITH_CUSTOMER_JWT_SECRET"),
        ("DEMO_AUTH_PASSWORD", "REPLACE_WITH_DEMO_AUTH_PASSWORD"),
        ("DEMO_AUTH_SECRET", "REPLACE_WITH_DEMO_AUTH_SECRET"),
        ("DATABASE_URL", "REPLACE_WITH_LOCAL_POSTGRESQL_URL"),
        ("CORS_ALLOWED_ORIGINS", "https://REPLACE_WITH_PUBLIC_DOMAIN"),
        ("CUSTOMER_WS_ALLOWED_ORIGINS", "https://CHANGE_ME.example.com"),
        ("DEMO_AUTH_ALLOWED_ORIGINS", "https://YOUR_PUBLIC_DOMAIN"),
        ("AWS_REGION", "REPLACE_WITH_AWS_REGION"),
        ("AWS_S3_BUCKET_NAME", "REPLACE_WITH_PRODUCT_IMAGE_BUCKET"),
        ("COGNITO_USER_POOL_ID", "REPLACE_WITH_USER_POOL_ID"),
        ("COGNITO_APP_CLIENT_ID", "REPLACE_WITH_APP_CLIENT_ID"),
        ("COGNITO_ISSUER", "https://CSP_CHANGE_ME_COGNITO_ORIGIN"),
    ],
)
def test_production_rejects_unresolved_placeholders(
    monkeypatch, variable, placeholder
):
    configure_valid_production(monkeypatch)
    monkeypatch.setenv(variable, placeholder)

    with pytest.raises(RuntimeError) as exc_info:
        validate_production_environment()

    message = str(exc_info.value)
    assert variable in message
    assert placeholder not in message


@pytest.mark.parametrize(
    ("variable", "known_template_value"),
    [
        ("AWS_S3_BUCKET_NAME", "your-product-image-bucket"),
        ("COGNITO_USER_POOL_ID", "your-user-pool-id"),
        ("COGNITO_APP_CLIENT_ID", "your-spa-app-client-id"),
    ],
)
def test_production_rejects_known_development_template_values(
    monkeypatch, variable, known_template_value
):
    configure_valid_production(monkeypatch)
    monkeypatch.setenv(variable, known_template_value)

    with pytest.raises(RuntimeError) as exc_info:
        validate_production_environment()

    message = str(exc_info.value)
    assert variable in message
    assert known_template_value not in message


def test_valid_production_configuration_passes(monkeypatch):
    configure_valid_production(monkeypatch)
    monkeypatch.setenv(
        "COGNITO_ISSUER",
        "https://cognito-idp.ap-northeast-1.amazonaws.com/ap-northeast-1_realpool",
    )
    validate_production_environment()


@pytest.mark.parametrize("variable", FORBIDDEN_PRODUCTION_AWS_CREDENTIAL_VARIABLES)
def test_production_rejects_aws_credential_overrides(monkeypatch, variable):
    configure_valid_production(monkeypatch)
    monkeypatch.setenv(variable, "configured-but-forbidden")
    with pytest.raises(RuntimeError, match=variable):
        validate_production_environment()


@pytest.mark.parametrize("variable", FORBIDDEN_PRODUCTION_DATABASE_VARIABLES)
def test_production_rejects_migration_credentials(monkeypatch, variable):
    configure_valid_production(monkeypatch)
    monkeypatch.setenv(variable, "postgresql+psycopg://migration:secret@127.0.0.1/db")
    with pytest.raises(RuntimeError, match=variable):
        validate_production_environment()


def test_non_production_does_not_require_production_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    for name in PRODUCTION_REQUIRED_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    validate_production_environment()
