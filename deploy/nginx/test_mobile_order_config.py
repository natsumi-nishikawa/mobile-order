import re
import unittest
from pathlib import Path


CONFIG_PATH = Path(__file__).with_name("mobile-order.conf.example")


class NginxSecurityHeaderConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = CONFIG_PATH.read_text(encoding="utf-8")
        servers = re.findall(r"server\s*\{(.*?)\n\}", cls.config, re.DOTALL)
        cls.assert_server_count(servers)
        cls.http_server = next(server for server in servers if "listen 80;" in server)
        cls.https_server = next(server for server in servers if "listen 443 ssl http2;" in server)

    @staticmethod
    def assert_server_count(servers: list[str]) -> None:
        if len(servers) != 2:
            raise AssertionError(f"expected two server blocks, found {len(servers)}")

    def header_value(self, name: str) -> str:
        match = re.search(
            rf'^\s*add_header\s+{re.escape(name)}\s+"([^"]*)"\s+always;',
            self.https_server,
            re.MULTILINE,
        )
        self.assertIsNotNone(match, f"{name} must be set with always")
        return match.group(1)

    def test_required_headers_are_on_https_server_with_always(self) -> None:
        expected = {
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "X-Frame-Options": "DENY",
            "Permissions-Policy": (
                "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
                "accelerometer=(), gyroscope=(), magnetometer=()"
            ),
        }
        for name, value in expected.items():
            with self.subTest(header=name):
                self.assertEqual(self.header_value(name), value)
        self.header_value("Content-Security-Policy-Report-Only")

    def test_headers_are_defined_only_at_https_server_scope(self) -> None:
        self.assertEqual(self.config.count("add_header "), 5)
        self.assertEqual(self.https_server.count("add_header "), 5)
        self.assertNotRegex(self.https_server, r"location\s+[^\{]+\{[^}]*add_header")

    def test_csp_is_report_only_and_restrictive(self) -> None:
        csp = self.header_value("Content-Security-Policy-Report-Only")
        directives = {
            "default-src": "'self'",
            "script-src": "'self'",
            "style-src": "'self'",
            "font-src": "'self'",
            "object-src": "'none'",
            "base-uri": "'none'",
            "frame-ancestors": "'none'",
            "form-action": "'self'",
            "frame-src": "'none'",
            "worker-src": "'none'",
            "media-src": "'none'",
        }
        for directive, sources in directives.items():
            with self.subTest(directive=directive):
                self.assertIn(f"{directive} {sources};", csp)
        self.assertNotIn("'unsafe-inline'", csp)
        self.assertNotIn("'unsafe-eval'", csp)
        self.assertNotRegex(csp, r"(?:^|\s)\*(?:\s|;|$)")
        self.assertNotIn("add_header Content-Security-Policy ", self.https_server)

    def test_csp_has_explicit_deployment_sources(self) -> None:
        csp = self.header_value("Content-Security-Policy-Report-Only")
        self.assertIn(
            "connect-src 'self' wss://$host CSP_CHANGE_ME_COGNITO_ORIGIN;", csp
        )
        self.assertIn(
            "img-src 'self' blob: CSP_CHANGE_ME_S3_IMAGE_ORIGIN;", csp
        )

    def test_clickjacking_policies_agree(self) -> None:
        self.assertEqual(self.header_value("X-Frame-Options"), "DENY")
        self.assertIn(
            "frame-ancestors 'none';",
            self.header_value("Content-Security-Policy-Report-Only"),
        )

    def test_existing_proxy_and_spa_behavior_is_preserved(self) -> None:
        required_fragments = (
            "location /api/ {",
            "location /ws/ {",
            "proxy_set_header Upgrade $http_upgrade;",
            "proxy_set_header Connection $connection_upgrade;",
            "limit_req zone=mobile_order_api burst=30 nodelay;",
            "limit_req zone=mobile_order_upload burst=5 nodelay;",
            "client_max_body_size 6m;",
            "try_files $uri $uri/ /index.html;",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.config)

    def test_hsts_is_not_enabled_and_http_only_redirects(self) -> None:
        self.assertNotRegex(
            self.config, r"(?m)^\s*add_header\s+Strict-Transport-Security\b"
        )
        self.assertIn("return 301 https://$host$request_uri;", self.http_server)
        self.assertNotIn("add_header", self.http_server)


if __name__ == "__main__":
    unittest.main()
