import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UNIT_PATH = Path(__file__).with_name("mobile-order-api.service.example")
ENV_EXAMPLE_PATH = Path(__file__).with_name("backend.env.example")


class ProductionSystemdUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.unit = UNIT_PATH.read_text(encoding="utf-8")
        cls.env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    def test_service_uses_dedicated_non_root_user(self) -> None:
        self.assertIn("User=mobile-order", self.unit)
        self.assertIn("Group=mobile-order", self.unit)
        self.assertNotRegex(self.unit, r"(?m)^User=root$")

    def test_uvicorn_is_loopback_single_worker_without_reload(self) -> None:
        command = next(
            line for line in self.unit.splitlines() if line.startswith("ExecStart=")
        )
        self.assertIn("-m uvicorn app.main:app", command)
        self.assertIn("--host 127.0.0.1", command)
        self.assertIn("--port 8000", command)
        self.assertIn("--workers 1", command)
        self.assertNotIn("--reload", command)
        self.assertIn("--proxy-headers", command)
        self.assertIn("--forwarded-allow-ips 127.0.0.1", command)
        self.assertIn("--no-access-log", command)
        self.assertNotIn("0.0.0.0", command)

    def test_restart_logging_and_hardening_are_configured(self) -> None:
        required = (
            "Restart=on-failure",
            "RestartSec=5s",
            "StartLimitIntervalSec=60",
            "StartLimitBurst=5",
            "StandardOutput=journal",
            "StandardError=journal",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectSystem=full",
            "ProtectHome=true",
            "ReadOnlyPaths=/opt/mobile-order",
        )
        for setting in required:
            with self.subTest(setting=setting):
                self.assertIn(setting, self.unit)

    def test_paths_and_required_environment_file_are_explicit(self) -> None:
        self.assertIn("WorkingDirectory=/opt/mobile-order/backend", self.unit)
        self.assertIn("EnvironmentFile=/etc/mobile-order/backend.env", self.unit)
        self.assertIn("/opt/mobile-order/backend/.venv/bin/python", self.unit)
        self.assertNotIn("EnvironmentFile=-", self.unit)

    def test_environment_template_enforces_production_safety(self) -> None:
        self.assertRegex(self.env_example, r"(?m)^APP_ENV=production$")
        self.assertRegex(
            self.env_example, r"(?m)^DEMO_AUTH_COOKIE_SECURE=true$"
        )
        for name in (
            "CORS_ALLOWED_ORIGINS",
            "CUSTOMER_WS_ALLOWED_ORIGINS",
            "DEMO_AUTH_ALLOWED_ORIGINS",
        ):
            self.assertRegex(
                self.env_example,
                rf"(?m)^{name}=https://REPLACE_WITH_PUBLIC_DOMAIN$",
            )

    def test_environment_template_has_no_aws_credentials_or_real_secrets(self) -> None:
        assignment_names = {
            match.group(1)
            for match in re.finditer(
                r"(?m)^([A-Za-z_][A-Za-z0-9_]*)=", self.env_example
            )
        }
        forbidden = {
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_PROFILE",
            "AWS_SHARED_CREDENTIALS_FILE",
            "AWS_CONFIG_FILE",
        }
        self.assertTrue(assignment_names.isdisjoint(forbidden))
        secret_assignments = re.findall(
            r"(?m)^(?:CUSTOMER_JWT_SECRET|DEMO_AUTH_PASSWORD|DEMO_AUTH_SECRET)=(.+)$",
            self.env_example,
        )
        self.assertTrue(secret_assignments)
        self.assertTrue(all(value.startswith("REPLACE_WITH_") for value in secret_assignments))


if __name__ == "__main__":
    unittest.main()
