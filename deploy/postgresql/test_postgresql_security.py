import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_postgresql_listens_only_on_localhost_and_creates_scram_passwords():
    config = read("postgresql.conf.snippet.example")
    assert re.search(r"^listen_addresses\s*=\s*'localhost'\s*$", config, re.M)
    assert re.search(r"^password_encryption\s*=\s*'scram-sha-256'\s*$", config, re.M)
    assert "'*'" not in config


def test_hba_allows_only_exact_loopback_roles_with_scram():
    hba = read("pg_hba.conf.snippet.example")
    active = [line.split() for line in hba.splitlines() if line and not line.startswith("#")]

    assert ["local", "all", "postgres", "peer"] in active
    assert ["local", "REPLACE_WITH_DATABASE_NAME", "all", "reject"] in active
    allows = [row for row in active if row[0] == "host" and row[-1] != "reject"]
    assert len(allows) == 6
    assert {row[1] for row in allows} == {"REPLACE_WITH_DATABASE_NAME"}
    assert {row[2] for row in allows} == {
        "REPLACE_WITH_APP_ROLE",
        "REPLACE_WITH_MIGRATION_ROLE",
        "REPLACE_WITH_BACKUP_ROLE",
    }
    assert {row[3] for row in allows} == {"127.0.0.1/32", "::1/128"}
    assert {row[4] for row in allows} == {"scram-sha-256"}
    assert "trust" not in {row[-1] for row in active}
    assert ["host", "REPLACE_WITH_DATABASE_NAME", "all", "0.0.0.0/0", "reject"] in active
    assert ["host", "REPLACE_WITH_DATABASE_NAME", "all", "::0/0", "reject"] in active


def test_application_role_has_dml_but_no_schema_ddl_or_role_escalation():
    sql = read("create_roles_and_privileges.sql.example")
    app_block = re.search(
        r"CREATE ROLE REPLACE_WITH_APP_ROLE(?P<body>.*?);", sql, re.S
    ).group("body")
    for attribute in (
        "NOSUPERUSER",
        "NOCREATEDB",
        "NOCREATEROLE",
        "NOINHERIT",
        "NOREPLICATION",
        "NOBYPASSRLS",
    ):
        assert attribute in app_block
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES" in sql
    assert "GRANT USAGE, SELECT ON ALL SEQUENCES" in sql
    assert "REVOKE CREATE ON SCHEMA public FROM REPLACE_WITH_APP_ROLE" in sql
    assert "GRANT CREATE ON SCHEMA public TO REPLACE_WITH_APP_ROLE" not in sql


def test_migration_role_owns_future_privilege_flow():
    sql = read("create_roles_and_privileges.sql.example")
    migration_block = re.search(
        r"CREATE ROLE REPLACE_WITH_MIGRATION_ROLE(?P<body>.*?);", sql, re.S
    ).group("body")
    assert "NOSUPERUSER" in migration_block
    assert "NOCREATEDB" in migration_block
    assert "NOCREATEROLE" in migration_block
    assert sql.count("ALTER DEFAULT PRIVILEGES FOR ROLE REPLACE_WITH_MIGRATION_ROLE") == 2
    assert "GRANT USAGE, CREATE ON SCHEMA public TO REPLACE_WITH_MIGRATION_ROLE" in sql
    assert "\\connect REPLACE_WITH_DATABASE_NAME" in sql


def test_runtime_and_migration_credentials_are_separated():
    migration_env = read("migration.env.example")
    backend_env = (REPOSITORY / "deploy" / "systemd" / "backend.env.example").read_text(
        encoding="utf-8"
    )
    alembic_env = (REPOSITORY / "backend" / "alembic" / "env.py").read_text(
        encoding="utf-8"
    )
    database_py = (REPOSITORY / "backend" / "app" / "database.py").read_text(
        encoding="utf-8"
    )

    assert "MIGRATION_DATABASE_URL=" in migration_env
    assert "MIGRATION_DATABASE_URL" not in backend_env
    assert 'os.getenv("MIGRATION_DATABASE_URL") or os.getenv("DATABASE_URL")' in alembic_env
    assert "MIGRATION_DATABASE_URL" not in database_py


def test_all_templates_retain_placeholders_and_no_password_literal():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.glob("*.example"))
    assert "REPLACE_WITH_DATABASE_NAME" in combined
    assert "REPLACE_WITH_APP_ROLE" in combined
    assert "REPLACE_WITH_MIGRATION_ROLE" in combined
    assert "PASSWORD '" not in combined


def test_existing_ownership_transfer_is_explicit_and_not_cluster_wide():
    sql = read("transfer_existing_ownership.sql.example")
    assert "ALTER DATABASE REPLACE_WITH_DATABASE_NAME OWNER TO REPLACE_WITH_MIGRATION_ROLE" in sql
    assert "ALTER SCHEMA public OWNER TO REPLACE_WITH_MIGRATION_ROLE" in sql
    assert "\\connect REPLACE_WITH_DATABASE_NAME" in sql
    assert "public.alembic_version" in sql
    assert sql.count("ALTER TABLE public.") == 11
    assert sql.count("ALTER SEQUENCE public.") == 10
    assert "REASSIGN OWNED" not in "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )


def test_five_existing_migrations_are_a_single_chain_and_use_schema_ddl():
    versions = REPOSITORY / "backend" / "alembic" / "versions"
    migrations = sorted(versions.glob("*.py"))
    assert len(migrations) == 5

    source = "\n".join(path.read_text(encoding="utf-8") for path in migrations)
    assert "op.create_table" in source
    assert "op.add_column" in source
    assert "op.create_check_constraint" in source

    revisions = set(re.findall(r"^revision:\s*str\s*=\s*['\"]([^'\"]+)", source, re.M))
    parents = re.findall(
        r"^down_revision:.*?=\s*['\"]([^'\"]+)", source, re.M
    )
    assert len(revisions) == 5
    assert len(parents) == 4
    assert set(parents).issubset(revisions)
