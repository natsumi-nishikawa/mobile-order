from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_alembic_prefers_dedicated_migration_database_url():
    env_source = (BACKEND_DIR / "alembic" / "env.py").read_text(encoding="utf-8")

    migration_lookup = 'os.getenv("MIGRATION_DATABASE_URL")'
    runtime_lookup = 'os.getenv("DATABASE_URL")'
    assert migration_lookup in env_source
    assert runtime_lookup in env_source
    assert env_source.index(migration_lookup) < env_source.index(runtime_lookup)


def test_application_runtime_uses_only_database_url():
    database_source = (BACKEND_DIR / "app" / "database.py").read_text(
        encoding="utf-8"
    )

    assert 'os.getenv("DATABASE_URL")' in database_source
    assert "MIGRATION_DATABASE_URL" not in database_source
