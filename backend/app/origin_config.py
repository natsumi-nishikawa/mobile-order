import os
from urllib.parse import urlsplit


def parse_allowed_origins(raw_value: str, variable_name: str) -> frozenset[str]:
    origins: set[str] = set()
    for candidate in raw_value.split(","):
        origin = candidate.strip().rstrip("/")
        if not origin:
            continue
        parsed = urlsplit(origin)
        if (
            origin == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError(f"{variable_name} contains an invalid origin")
        try:
            port = parsed.port
        except ValueError as exc:
            raise RuntimeError(f"{variable_name} contains an invalid origin") from exc
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        normalized = f"{parsed.scheme}://{host}"
        if port is not None and not (
            (parsed.scheme == "http" and port == 80)
            or (parsed.scheme == "https" and port == 443)
        ):
            normalized += f":{port}"
        origins.add(normalized)
    if not origins:
        raise RuntimeError(f"{variable_name} must contain at least one origin")
    return frozenset(origins)


def get_allowed_origins(variable_name: str) -> frozenset[str]:
    raw_value = os.getenv(variable_name)
    environment = os.getenv("APP_ENV", "production").lower()
    if not raw_value:
        if environment in {"development", "test"}:
            raw_value = "http://localhost:5173"
        else:
            raise RuntimeError(f"{variable_name} is required in production")
    origins = parse_allowed_origins(raw_value, variable_name)
    if environment == "production" and any(
        urlsplit(origin).hostname in {"localhost", "127.0.0.1", "::1"}
        for origin in origins
    ):
        raise RuntimeError(f"{variable_name} must not allow localhost in production")
    if environment == "production" and any(
        not origin.startswith("https://") for origin in origins
    ):
        raise RuntimeError(f"{variable_name} must use HTTPS origins in production")
    return origins
