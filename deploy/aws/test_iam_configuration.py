import ast
import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = Path(__file__).with_name("ec2-app-permissions-policy.example.json")
TRUST_PATH = Path(__file__).with_name("ec2-trust-policy.example.json")

EXPECTED_S3_ACTIONS = {
    "s3:GetObject",
    "s3:PutObject",
    "s3:DeleteObject",
}
EXPECTED_COGNITO_ACTIONS = {
    "cognito-idp:ListUsersInGroup",
    "cognito-idp:AdminCreateUser",
    "cognito-idp:AdminAddUserToGroup",
    "cognito-idp:AdminEnableUser",
    "cognito-idp:AdminDisableUser",
    "cognito-idp:AdminSetUserPassword",
    "cognito-idp:AdminDeleteUser",
    "cognito-idp:AdminGetUser",
}


class IamPolicyTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        cls.trust = json.loads(TRUST_PATH.read_text(encoding="utf-8"))
        cls.statements = {item["Sid"]: item for item in cls.policy["Statement"]}

    def test_permission_and_trust_templates_are_valid_json(self) -> None:
        self.assertEqual(self.policy["Version"], "2012-10-17")
        self.assertEqual(self.trust["Version"], "2012-10-17")

    def test_s3_permissions_are_exact_and_prefix_limited(self) -> None:
        statement = self.statements["ProductImageObjectsOnly"]
        self.assertEqual(statement["Effect"], "Allow")
        self.assertEqual(set(statement["Action"]), EXPECTED_S3_ACTIONS)
        self.assertEqual(
            statement["Resource"],
            "arn:aws:s3:::REPLACE_WITH_BUCKET_NAME/products/*",
        )

    def test_cognito_permissions_are_exact_and_pool_limited(self) -> None:
        statement = self.statements["ManageApplicationStaffOnly"]
        self.assertEqual(statement["Effect"], "Allow")
        self.assertEqual(set(statement["Action"]), EXPECTED_COGNITO_ACTIONS)
        self.assertEqual(
            statement["Resource"],
            "arn:aws:cognito-idp:REPLACE_WITH_REGION:REPLACE_WITH_AWS_ACCOUNT_ID:"
            "userpool/REPLACE_WITH_USER_POOL_ID",
        )

    def test_no_wildcard_actions_or_unscoped_resources(self) -> None:
        for statement in self.policy["Statement"]:
            actions = statement["Action"]
            actions = actions if isinstance(actions, list) else [actions]
            self.assertTrue(all("*" not in action for action in actions))
            self.assertNotEqual(statement["Resource"], "*")

    def test_trust_is_ec2_only(self) -> None:
        self.assertEqual(
            self.trust["Statement"],
            [
                {
                    "Sid": "AllowEC2ToAssumeRole",
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        )

    def test_policy_actions_match_current_aws_calls(self) -> None:
        image_service = (ROOT / "backend/app/services/product_images.py").read_text(
            encoding="utf-8"
        )
        cognito_service = (ROOT / "backend/app/services/cognito_users.py").read_text(
            encoding="utf-8"
        )
        for call in ("upload_fileobj(", '"get_object"', "delete_object("):
            self.assertIn(call, image_service)
        expected_cognito_calls = {
            "list_users_in_group",
            "admin_create_user",
            "admin_add_user_to_group",
            "admin_enable_user",
            "admin_disable_user",
            "admin_set_user_password",
            "admin_delete_user",
            "admin_get_user",
        }
        actual_cognito_calls = set(
            re.findall(
                r"(?:client|_client\(\))\."
                r"(list_users_in_group|admin_[a-z_]+)\b",
                cognito_service,
            )
        )
        self.assertEqual(actual_cognito_calls, expected_cognito_calls)


class AwsCredentialSafetyTests(unittest.TestCase):
    def test_boto3_clients_do_not_receive_fixed_credentials(self) -> None:
        service_paths = [
            ROOT / "backend/app/services/product_images.py",
            ROOT / "backend/app/services/cognito_users.py",
        ]
        forbidden_keywords = {
            "aws_access_key_id",
            "aws_secret_access_key",
            "aws_session_token",
        }
        for path in service_paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "boto3"
                    and node.func.attr == "client"
                ):
                    continue
                keywords = {keyword.arg for keyword in node.keywords}
                self.assertTrue(forbidden_keywords.isdisjoint(keywords), path)

    def test_repository_candidate_files_do_not_contain_fixed_aws_credentials(self) -> None:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        patterns = (
            re.compile(rb"(?m)^\s*AWS_ACCESS_KEY_ID\s*=\s*\S+"),
            re.compile(rb"(?m)^\s*AWS_SECRET_ACCESS_KEY\s*=\s*\S+"),
            re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        )
        findings: list[str] = []
        for raw_path in filter(None, result.stdout.split(b"\0")):
            relative = raw_path.decode("utf-8")
            content = (ROOT / relative).read_bytes()
            if any(pattern.search(content) for pattern in patterns):
                findings.append(relative)
        self.assertEqual(findings, [], "repository files contain AWS credential material")

    def test_gitignore_excludes_real_environment_files(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertRegex(gitignore, r"(?m)^\.env$")
        self.assertRegex(gitignore, r"(?m)^\.env\.\*$")
        self.assertRegex(gitignore, r"(?m)^!\.env\.example$")


if __name__ == "__main__":
    unittest.main()
