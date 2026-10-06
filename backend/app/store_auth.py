import os
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


store_security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class StoreUser:
    subject: str
    username: str
    groups: frozenset[str]


def _settings() -> tuple[str, str]:
    region = os.getenv("AWS_REGION")
    pool_id = os.getenv("COGNITO_USER_POOL_ID")
    client_id = os.getenv("COGNITO_APP_CLIENT_ID")
    if not region or not pool_id or not client_id:
        raise HTTPException(status_code=503, detail="店舗認証の設定が完了していません")
    issuer = os.getenv("COGNITO_ISSUER") or f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
    return issuer.rstrip("/"), client_id


@lru_cache(maxsize=4)
def _jwks_client(issuer: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{issuer}/.well-known/jwks.json", cache_keys=True)


def verify_store_token(token: str) -> StoreUser:
    issuer, client_id = _settings()
    try:
        signing_key = _jwks_client(issuer).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False, "require": ["exp", "iss", "sub", "token_use"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="ログインの有効期限が切れています") from exc
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        raise HTTPException(status_code=401, detail="店舗認証トークンを確認できません") from exc

    if payload.get("token_use") != "access" or payload.get("client_id") != client_id:
        raise HTTPException(status_code=401, detail="店舗認証トークンを確認できません")
    groups = payload.get("cognito:groups", [])
    if not isinstance(groups, list) or not all(isinstance(group, str) for group in groups):
        raise HTTPException(status_code=401, detail="店舗権限を確認できません")
    username = payload.get("username") or payload.get("cognito:username") or payload["sub"]
    return StoreUser(subject=payload["sub"], username=username, groups=frozenset(groups))


def get_store_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(store_security),
) -> StoreUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="ログインしてください")
    user = verify_store_token(credentials.credentials)
    from app.services.cognito_users import ensure_cognito_user_enabled
    ensure_cognito_user_enabled(user.username)
    return user


def require_admin(user: StoreUser = Depends(get_store_user)) -> StoreUser:
    if "admin" not in user.groups:
        raise HTTPException(status_code=403, detail="管理者権限が必要です")
    return user


def require_staff(user: StoreUser = Depends(get_store_user)) -> StoreUser:
    if not user.groups.intersection({"staff", "admin"}):
        raise HTTPException(status_code=403, detail="スタッフ権限が必要です")
    return user
