import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).with_name("validate_deployment_config.py")
REPOSITORY = SCRIPT.parents[2]


def run_preflight(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(path) for path in paths)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_unresolved_rendered_files_fail_without_printing_values(tmp_path):
    secret_value = "do-not-print-this-resolved-secret"
    environment = tmp_path / "backend.env"
    nginx = tmp_path / "mobile-order.conf"
    policy = tmp_path / "policy.json"
    environment.write_text(
        "CUSTOMER_JWT_SECRET=REPLACE_WITH_CUSTOMER_JWT_SECRET\n"
        f"ALREADY_RESOLVED_SECRET={secret_value}\n",
        encoding="utf-8",
    )
    nginx.write_text(
        "server_name CHANGE_ME.example.com;\n",
        encoding="utf-8",
    )
    policy.write_text(
        json.dumps({"Resource": "arn:aws:s3:::REPLACE_WITH_BUCKET/data/*"}),
        encoding="utf-8",
    )

    result = run_preflight(environment, nginx, policy)

    assert result.returncode != 0
    assert "backend.env:1" in result.stderr
    assert "mobile-order.conf:1" in result.stderr
    assert "policy.json:1" in result.stderr
    assert "REPLACE_WITH" in result.stderr
    assert "CHANGE_ME" in result.stderr
    assert secret_value not in result.stdout
    assert secret_value not in result.stderr


def test_known_development_template_value_fails(tmp_path):
    rendered = tmp_path / "backend.env"
    rendered.write_text(
        "AWS_S3_BUCKET_NAME=your-product-image-bucket\n",
        encoding="utf-8",
    )

    result = run_preflight(rendered)

    assert result.returncode != 0
    assert "KNOWN_TEMPLATE_VALUE" in result.stderr


def test_resolved_dummy_files_pass(tmp_path):
    environment = tmp_path / "backend.env"
    nginx = tmp_path / "mobile-order.conf"
    policy = tmp_path / "policy.json"
    sql = tmp_path / "roles.sql"
    unit = tmp_path / "mobile-order.service"
    environment.write_text(
        "APP_ENV=production\n"
        "DATABASE_URL=postgresql+psycopg://app:dummy@127.0.0.1:5432/appdb\n",
        encoding="utf-8",
    )
    nginx.write_text("server_name orders.example.test;\n", encoding="utf-8")
    policy.write_text(
        json.dumps({"Resource": "arn:aws:s3:::demo-backup/postgresql/*"}),
        encoding="utf-8",
    )
    sql.write_text("GRANT SELECT ON TABLE app.orders TO backup_role;\n", encoding="utf-8")
    unit.write_text("EnvironmentFile=/etc/mobile-order/backend.env\n", encoding="utf-8")

    result = run_preflight(environment, nginx, policy, sql, unit)

    assert result.returncode == 0, result.stderr
    assert "passed for 5 file(s)" in result.stdout


def test_invalid_json_and_missing_file_fail(tmp_path):
    invalid_json = tmp_path / "policy.json"
    invalid_json.write_text("{not-json}", encoding="utf-8")

    result = run_preflight(invalid_json, tmp_path / "missing.conf")

    assert result.returncode != 0
    assert "invalid JSON" in result.stderr
    assert "file does not exist" in result.stderr


def test_example_templates_remain_repository_candidates():
    examples = [
        REPOSITORY / "deploy/systemd/backend.env.example",
        REPOSITORY / "deploy/nginx/mobile-order.conf.example",
        REPOSITORY / "deploy/aws/ec2-app-permissions-policy.example.json",
        REPOSITORY / "deploy/postgresql/create_roles_and_privileges.sql.example",
        REPOSITORY / "deploy/backup/backup.env.example",
    ]
    assert all(path.is_file() for path in examples)
    assert any("REPLACE_WITH_" in path.read_text(encoding="utf-8") for path in examples)
    for path in examples:
        relative = path.relative_to(REPOSITORY)
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", str(relative)],
            cwd=REPOSITORY,
            check=False,
        )
        assert result.returncode == 1, f"example template is ignored: {relative}"
