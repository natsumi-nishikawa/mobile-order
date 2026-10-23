import os
import re

from dotenv import load_dotenv


PRODUCTION_REQUIRED_VARIABLES = (
    "DATABASE_URL",
    "CUSTOMER_JWT_SECRET",
    "CUSTOMER_WS_ALLOWED_ORIGINS",
    "CORS_ALLOWED_ORIGINS",
    "DEMO_AUTH_PASSWORD",
    "DEMO_AUTH_SECRET",
    "DEMO_AUTH_ALLOWED_ORIGINS",
    "AWS_REGION",
    "AWS_S3_BUCKET_NAME",
    "COGNITO_USER_POOL_ID",
    "COGNITO_APP_CLIENT_ID",
)

FORBIDDEN_PRODUCTION_AWS_CREDENTIAL_VARIABLES = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_SHARED_CREDENTIALS_FILE",
    "AWS_CONFIG_FILE",
)

FORBIDDEN_PRODUCTION_DATABASE_VARIABLES = (
    "MIGRATION_DATABASE_URL",
)

PRODUCTION_OPTIONAL_TEMPLATE_VARIABLES = (
    "COGNITO_ISSUER",
)

PLACEHOLDER_MARKER_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:REPLACE_WITH_[A-Z0-9_]+|CHANGE_ME(?:_[A-Z0-9_]+)?|YOUR_[A-Z0-9_]+)(?![A-Z0-9])"
)

KNOWN_TEMPLATE_VALUES = {
    "AWS_S3_BUCKET_NAME": {"your-product-image-bucket"},
    "COGNITO_USER_POOL_ID": {"your-user-pool-id"},
    "COGNITO_APP_CLIENT_ID": {"your-spa-app-client-id"},
    "COGNITO_ISSUER": {
        "https://cognito-idp.ap-northeast-1.amazonaws.com/your-user-pool-id"
    },
}


def _contains_unresolved_placeholder(name: str, value: str) -> bool:
    if PLACEHOLDER_MARKER_PATTERN.search(value):
        return True
    return value.strip() in KNOWN_TEMPLATE_VALUES.get(name, set())


def environment_name() -> str:
    return os.getenv("APP_ENV", "development").strip().lower()


def load_local_environment() -> None:
    """Load a local .env file only outside production.

    Production receives its environment from the process manager. This avoids
    silently mixing a deployment EnvironmentFile with a checkout-local .env.
    """
    if environment_name() != "production":
        load_dotenv()


def validate_production_environment() -> None:
    if environment_name() != "production":
        return

    missing = [name for name in PRODUCTION_REQUIRED_VARIABLES if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing required production environment variables: " + ", ".join(missing)
        )

    placeholder_variables = [
        name
        for name in (*PRODUCTION_REQUIRED_VARIABLES, *PRODUCTION_OPTIONAL_TEMPLATE_VARIABLES)
        if (value := os.getenv(name)) and _contains_unresolved_placeholder(name, value)
    ]
    if placeholder_variables:
        raise RuntimeError(
            "Unresolved deployment placeholder in production variables: "
            + ", ".join(placeholder_variables)
        )

    if os.getenv("DEMO_AUTH_COOKIE_SECURE", "").strip().lower() != "true":
        raise RuntimeError("DEMO_AUTH_COOKIE_SECURE must be true in production")

    configured_credentials = [
        name
        for name in FORBIDDEN_PRODUCTION_AWS_CREDENTIAL_VARIABLES
        if os.getenv(name)
    ]
    if configured_credentials:
        raise RuntimeError(
            "Production must use the EC2 IAM role; remove AWS credential overrides: "
            + ", ".join(configured_credentials)
        )

    configured_database_credentials = [
        name
        for name in FORBIDDEN_PRODUCTION_DATABASE_VARIABLES
        if os.getenv(name)
    ]
    if configured_database_credentials:
        raise RuntimeError(
            "The API service must not receive migration credentials; remove: "
            + ", ".join(configured_database_credentials)
        )


def api_documentation_urls() -> dict[str, str | None]:
    if environment_name() == "production":
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }
