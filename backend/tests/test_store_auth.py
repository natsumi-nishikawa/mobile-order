import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ["ENV_FILE"] = ".env.test"
os.environ["AWS_REGION"] = "ap-northeast-1"
os.environ["COGNITO_USER_POOL_ID"] = "ap-northeast-1_TestPool"
os.environ["COGNITO_APP_CLIENT_ID"] = "test-client-id"

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import store_auth
from app.main import app
from app.schemas.admin_staff import StaffAccountCreate
from app.services import cognito_users


PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ISSUER = "https://cognito-idp.ap-northeast-1.amazonaws.com/ap-northeast-1_TestPool"


class FakeJwksClient:
    def get_signing_key_from_jwt(self, _token):
        return SimpleNamespace(key=PRIVATE_KEY.public_key())


def token(*, groups, expires_delta=timedelta(minutes=5), token_use="access", client_id="test-client-id"):
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": "user-sub", "username": "user@example.com", "iss": ISSUER,
        "exp": now + expires_delta, "iat": now, "token_use": token_use,
        "client_id": client_id, "cognito:groups": groups,
    }, PRIVATE_KEY, algorithm="RS256", headers={"kid": "test-key"})


def test_cognito_jwt_signature_claims_and_roles(monkeypatch):
    monkeypatch.setattr(store_auth, "_jwks_client", lambda _issuer: FakeJwksClient())
    staff = store_auth.verify_store_token(token(groups=["staff"]))
    assert staff.username == "user@example.com"
    assert store_auth.require_staff(staff) == staff
    with pytest.raises(HTTPException) as forbidden:
        store_auth.require_admin(staff)
    assert forbidden.value.status_code == 403

    admin = store_auth.verify_store_token(token(groups=["admin"]))
    assert store_auth.require_admin(admin) == admin
    assert store_auth.require_staff(admin) == admin

    for invalid in (
        token(groups=["staff"], expires_delta=timedelta(minutes=-1)),
        token(groups=["staff"], token_use="id"),
        token(groups=["staff"], client_id="another-client"),
        "invalid.jwt.value",
    ):
        with pytest.raises(HTTPException) as rejected:
            store_auth.verify_store_token(invalid)
        assert rejected.value.status_code == 401


def test_admin_and_staff_api_authorization(monkeypatch):
    previous_admin = app.dependency_overrides.pop(store_auth.require_admin, None)
    previous_staff = app.dependency_overrides.pop(store_auth.require_staff, None)

    def fake_verify(value: str):
        if value == "staff-token":
            return store_auth.StoreUser("staff-sub", "staff", frozenset({"staff"}))
        if value == "admin-token":
            return store_auth.StoreUser("admin-sub", "admin", frozenset({"admin"}))
        raise HTTPException(status_code=401, detail="店舗認証トークンを確認できません")

    monkeypatch.setattr(store_auth, "verify_store_token", fake_verify)
    monkeypatch.setattr(cognito_users, "ensure_cognito_user_enabled", lambda _username: None)
    client = TestClient(app)
    try:
        assert client.get("/api/staff/categories").status_code == 401
        assert client.get("/api/admin/categories").status_code == 401
        staff_headers = {"Authorization": "Bearer staff-token"}
        admin_headers = {"Authorization": "Bearer admin-token"}
        assert client.get("/api/staff/categories", headers=staff_headers).status_code == 200
        assert client.get("/api/admin/categories", headers=staff_headers).status_code == 403
        assert client.get("/api/admin/categories", headers=admin_headers).status_code == 200
        assert client.get("/api/staff/categories", headers=admin_headers).status_code == 200
        assert client.get("/api/staff/categories", headers={"Authorization": "Bearer invalid"}).status_code == 401
        # Frontend logout後と同じくAuthorizationがなくなれば利用できない
        assert client.get("/api/staff/categories").status_code == 401
    finally:
        if previous_admin is not None:
            app.dependency_overrides[store_auth.require_admin] = previous_admin
        if previous_staff is not None:
            app.dependency_overrides[store_auth.require_staff] = previous_staff


class FakeCognito:
    def __init__(self):
        self.users = {}
        self.groups = {}
        self.calls = []

    def list_users_in_group(self, **kwargs):
        return {"Users": [user for name, user in self.users.items() if self.groups.get(name) == kwargs["GroupName"]]}

    def admin_create_user(self, **kwargs):
        user = {"Username": kwargs["Username"], "Attributes": kwargs["UserAttributes"], "Enabled": True, "UserStatus": "FORCE_CHANGE_PASSWORD"}
        self.users[user["Username"]] = user
        self.calls.append(("create", kwargs))
        return {"User": user}

    def admin_add_user_to_group(self, **kwargs):
        self.groups[kwargs["Username"]] = kwargs["GroupName"]
        self.calls.append(("group", kwargs))

    def admin_disable_user(self, **kwargs):
        self.users[kwargs["Username"]]["Enabled"] = False
        self.calls.append(("disable", kwargs))

    def admin_enable_user(self, **kwargs):
        self.users[kwargs["Username"]]["Enabled"] = True
        self.calls.append(("enable", kwargs))

    def admin_set_user_password(self, **kwargs):
        self.calls.append(("password", kwargs))

    def admin_delete_user(self, **kwargs):
        self.users.pop(kwargs["Username"])
        self.groups.pop(kwargs["Username"], None)
        self.calls.append(("delete", kwargs))

    def admin_get_user(self, **kwargs):
        return self.users[kwargs["Username"]]


def test_cognito_staff_management_create_group_disable_enable_reset_and_delete(monkeypatch):
    fake = FakeCognito()
    monkeypatch.setattr(cognito_users, "_client", lambda: fake)
    data = StaffAccountCreate(email="STAFF@example.com", display_name="店舗スタッフ", temporary_password="Temporary1!")
    created = cognito_users.create_staff_account(data.email, data.temporary_password, data.display_name)
    assert created.email == "staff@example.com"
    assert fake.groups[created.username] == "staff"
    assert cognito_users.list_staff_accounts()[0].status == "FORCE_CHANGE_PASSWORD"
    cognito_users.set_staff_enabled(created.username, False)
    assert cognito_users.list_staff_accounts()[0].enabled is False
    with pytest.raises(HTTPException) as disabled:
        cognito_users.ensure_cognito_user_enabled(created.username)
    assert disabled.value.status_code == 401
    cognito_users.set_staff_enabled(created.username, True)
    assert cognito_users.list_staff_accounts()[0].enabled is True
    cognito_users.ensure_cognito_user_enabled(created.username)
    cognito_users.reset_staff_password(created.username, "AnotherTemporary1!")
    password_call = next(call for call in fake.calls if call[0] == "password")
    assert password_call[1]["Permanent"] is False
    cognito_users.delete_staff_account(created.username)
    assert created.username not in fake.users
    assert next(call for call in fake.calls if call[0] == "delete")[1]["Username"] == created.username


def test_delete_staff_rejects_admin_and_non_staff(monkeypatch):
    fake = FakeCognito()
    fake.users["admin@example.com"] = {"Username": "admin@example.com", "Attributes": []}
    fake.groups["admin@example.com"] = "admin"
    fake.users["customer@example.com"] = {"Username": "customer@example.com", "Attributes": []}
    monkeypatch.setattr(cognito_users, "_client", lambda: fake)

    for username in ("admin@example.com", "customer@example.com"):
        with pytest.raises(HTTPException) as rejected:
            cognito_users.delete_staff_account(username)
        assert rejected.value.status_code == 403
    assert not any(call[0] == "delete" for call in fake.calls)
