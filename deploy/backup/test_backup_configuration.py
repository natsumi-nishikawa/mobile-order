import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]


class BackupScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = (ROOT / "mobile-order-postgresql-backup").read_text(
            encoding="utf-8"
        )

    def test_shell_syntax_when_bash_is_available(self) -> None:
        candidates = [
            shutil.which("bash"),
            r"C:\Program Files\Git\bin\bash.exe",
        ]
        bash = next((item for item in candidates if item and Path(item).is_file()), None)
        if bash is None:
            self.skipTest("bash is unavailable")
        subprocess.run(
            [bash, "-n", str(ROOT / "mobile-order-postgresql-backup")],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_missing_required_tools_returns_failure_when_bash_is_available(self) -> None:
        candidates = [shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe"]
        bash = next((item for item in candidates if item and Path(item).is_file()), None)
        if bash is None:
            self.skipTest("bash is unavailable")
        result = subprocess.run(
            [bash, str(ROOT / "mobile-order-postgresql-backup")],
            env={"PATH": ""},
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("completed successfully", result.stdout.lower())

    def test_dump_is_custom_format_and_every_failure_propagates(self) -> None:
        self.assertIn("set -Eeuo pipefail", self.script)
        self.assertIn("pg_dump --format=custom --no-password", self.script)
        self.assertIn('[[ -s "$dump_file" ]]', self.script)
        self.assertIn('pg_restore --list "$dump_file" >/dev/null', self.script)
        self.assertNotIn("|| true", self.script)

    def test_upload_is_verified_and_does_not_delete_s3_objects(self) -> None:
        self.assertIn("aws s3api put-object", self.script)
        self.assertIn("aws s3api head-object", self.script)
        self.assertIn('[[ "$remote_size" == "$local_size" ]]', self.script)
        self.assertIn('[[ "$remote_sha256" == "$local_sha256" ]]', self.script)
        self.assertNotRegex(self.script, r"aws\s+s3(?:api)?\s+(?:rm|delete-object)")

    def test_local_files_and_concurrency_are_protected(self) -> None:
        self.assertIn("umask 077", self.script)
        self.assertIn("mktemp --directory", self.script)
        self.assertIn("trap cleanup EXIT INT TERM", self.script)
        self.assertIn("flock --nonblock", self.script)
        self.assertIn('PGHOST" == "127.0.0.1"', self.script)

    def test_retention_classes_have_unambiguous_calendar_rules(self) -> None:
        self.assertIn("upload_and_verify daily", self.script)
        self.assertIn("date --utc '+%u'", self.script)
        self.assertIn("upload_and_verify weekly", self.script)
        self.assertIn("date --utc '+%d'", self.script)
        self.assertIn("upload_and_verify monthly", self.script)

    def test_environment_template_has_no_embedded_credentials(self) -> None:
        env = (ROOT / "backup.env.example").read_text(encoding="utf-8")
        self.assertIn("PGPASSFILE=/var/lib/mobile-order-backup/.pgpass", env)
        self.assertNotRegex(env, r"(?m)^PGPASSWORD=")
        self.assertNotRegex(env, r"(?m)^AWS_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN)=")
        values = re.findall(r"(?m)^[A-Z0-9_]+=(.+)$", env)
        self.assertTrue(all("example.com" not in value for value in values))


class BackupIamAndLifecycleTests(unittest.TestCase):
    def test_writer_and_restore_policies_are_prefix_limited(self) -> None:
        writer = json.loads((ROOT / "backup-writer-policy.example.json").read_text())
        reader = json.loads((ROOT / "restore-reader-policy.example.json").read_text())
        writer_statement = writer["Statement"][0]
        reader_statement = reader["Statement"][0]

        self.assertEqual(set(writer_statement["Action"]), {"s3:PutObject", "s3:GetObject"})
        self.assertEqual(reader_statement["Action"], "s3:GetObject")
        for statement in (writer_statement, reader_statement):
            self.assertEqual(
                statement["Resource"],
                "arn:aws:s3:::REPLACE_WITH_BACKUP_BUCKET/postgresql/*",
            )
            self.assertNotEqual(statement["Resource"], "*")
        self.assertNotIn("s3:DeleteObject", writer_statement["Action"])
        self.assertNotIn("s3:ListBucket", writer_statement["Action"])

    def test_bucket_is_private_and_uses_sse_s3(self) -> None:
        public_block = json.loads((ROOT / "s3-public-access-block.example.json").read_text())
        encryption = json.loads((ROOT / "s3-default-encryption.example.json").read_text())
        self.assertTrue(all(public_block.values()))
        self.assertEqual(
            encryption["Rules"][0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"],
            "AES256",
        )

    def test_lifecycle_matches_daily_weekly_monthly_plan(self) -> None:
        lifecycle = json.loads((ROOT / "s3-lifecycle.example.json").read_text())
        rules = {rule["Filter"]["Prefix"]: rule for rule in lifecycle["Rules"]}
        self.assertEqual(
            {prefix: rule["Expiration"]["Days"] for prefix, rule in rules.items()},
            {
                "postgresql/daily/": 7,
                "postgresql/weekly/": 28,
                "postgresql/monthly/": 92,
            },
        )
        for rule in rules.values():
            self.assertEqual(rule["Status"], "Enabled")
            self.assertIn("NoncurrentVersionExpiration", rule)
            self.assertEqual(rule["AbortIncompleteMultipartUpload"]["DaysAfterInitiation"], 1)


class BackupSystemdAndDatabaseTests(unittest.TestCase):
    def test_timer_is_daily_persistent_and_targets_backup_service(self) -> None:
        timer = (ROOT / "mobile-order-postgresql-backup.timer.example").read_text()
        self.assertIn("OnCalendar=*-*-* 03:20:00", timer)
        self.assertIn("RandomizedDelaySec=30m", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("Unit=mobile-order-postgresql-backup.service", timer)

    def test_service_is_separate_limited_and_journalled(self) -> None:
        service = (ROOT / "mobile-order-postgresql-backup.service.example").read_text()
        self.assertIn("Type=oneshot", service)
        self.assertIn("User=mobile-order-backup", service)
        self.assertNotIn("User=root", service)
        self.assertIn("StandardOutput=journal", service)
        self.assertIn("StandardError=journal", service)
        self.assertIn("CPUQuota=25%", service)
        self.assertIn("MemoryMax=256M", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertNotIn("mobile-order-api.service", service)

    def test_backup_database_role_is_read_only_and_non_privileged(self) -> None:
        sql = (
            REPOSITORY / "deploy/postgresql/create_backup_role.sql.example"
        ).read_text(encoding="utf-8")
        for attribute in (
            "NOSUPERUSER",
            "NOCREATEDB",
            "NOCREATEROLE",
            "NOREPLICATION",
            "NOBYPASSRLS",
        ):
            self.assertIn(attribute, sql)
        self.assertIn("GRANT SELECT ON ALL TABLES", sql)
        self.assertIn("GRANT SELECT ON ALL SEQUENCES", sql)
        self.assertIn("REVOKE CREATE ON SCHEMA public", sql)
        self.assertNotRegex(sql, r"GRANT\s+(?:INSERT|UPDATE|DELETE|CREATE).*BACKUP_ROLE")

    def test_hba_limits_backup_role_to_loopback_scram(self) -> None:
        hba = (REPOSITORY / "deploy/postgresql/pg_hba.conf.snippet.example").read_text()
        backup_lines = [line for line in hba.splitlines() if "REPLACE_WITH_BACKUP_ROLE" in line]
        self.assertEqual(len(backup_lines), 2)
        self.assertTrue(all("scram-sha-256" in line for line in backup_lines))
        self.assertTrue(any("127.0.0.1/32" in line for line in backup_lines))
        self.assertTrue(any("::1/128" in line for line in backup_lines))


class LoggingAndRestoreSafetyTests(unittest.TestCase):
    def test_nginx_access_log_omits_sensitive_request_fields(self) -> None:
        nginx = (REPOSITORY / "deploy/nginx/mobile-order.conf.example").read_text()
        log_block = nginx[nginx.index("log_format mobile_order_safe") : nginx.index("upstream")]
        self.assertIn("$request_method $uri $server_protocol", log_block)
        for forbidden in ("$request ", "$args", "$query_string", "$http_authorization", "$http_cookie", "$http_referer"):
            self.assertNotIn(forbidden, log_block)
        self.assertIn("error_log /var/log/nginx/mobile-order-error.log error;", log_block)

    def test_uvicorn_access_log_is_disabled_in_production_unit(self) -> None:
        unit = (
            REPOSITORY / "deploy/systemd/mobile-order-api.service.example"
        ).read_text()
        self.assertIn("--no-access-log", unit)

    def test_postgresql_does_not_log_statements_or_parameters(self) -> None:
        config = (
            REPOSITORY / "deploy/logging/postgresql-logging.conf.snippet.example"
        ).read_text()
        self.assertIn("log_statement = 'none'", config)
        self.assertIn("log_duration = off", config)
        self.assertIn("log_parameter_max_length = 0", config)
        self.assertIn("log_parameter_max_length_on_error = 0", config)

    def test_restore_runbook_requires_isolation_and_exit_on_error(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("REPLACE_WITH_ISOLATED_RESTORE_DB", readme)
        self.assertIn("pg_restore --exit-on-error --no-owner --no-privileges", readme)
        self.assertIn("本番DB名と同じ名前を復元先に指定しません", readme)
        self.assertIn("復元試験未完了", readme)


if __name__ == "__main__":
    unittest.main()
