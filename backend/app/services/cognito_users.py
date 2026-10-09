import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app.schemas.admin_staff import StaffAccountResponse


def _pool_id() -> str:
    pool_id = os.getenv("COGNITO_USER_POOL_ID")
    if not pool_id:
        raise HTTPException(status_code=503, detail="Cognito User Poolが設定されていません")
    return pool_id


def _client():
    return boto3.client("cognito-idp", region_name=os.getenv("AWS_REGION"))


def _attributes(user: dict) -> dict[str, str]:
    return {item["Name"]: item["Value"] for item in user.get("Attributes", [])}


def _response(user: dict) -> StaffAccountResponse:
    attributes = _attributes(user)
    return StaffAccountResponse(
        username=user["Username"],
        email=attributes.get("email", user["Username"]),
        display_name=attributes.get("name"),
        enabled=user.get("Enabled", True),
        status=user.get("UserStatus", "UNKNOWN"),
    )


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code")
        if code == "UsernameExistsException":
            raise HTTPException(status_code=409, detail="このメールアドレスはすでに登録されています") from exc
        if code == "UserNotFoundException":
            raise HTTPException(status_code=404, detail="スタッフが見つかりません") from exc
        if code in {"InvalidPasswordException", "InvalidParameterException"}:
            raise HTTPException(status_code=422, detail="パスワードまたは入力内容がCognitoの条件を満たしていません") from exc
    raise HTTPException(status_code=502, detail="Cognitoの操作に失敗しました") from exc


def list_staff_accounts() -> list[StaffAccountResponse]:
    client = _client()
    users: list[dict] = []
    token = None
    try:
        while True:
            args = {"UserPoolId": _pool_id(), "GroupName": "staff"}
            if token:
                args["NextToken"] = token
            result = client.list_users_in_group(**args)
            users.extend(result.get("Users", []))
            token = result.get("NextToken")
            if not token:
                break
    except (ClientError, BotoCoreError) as exc:
        _handle_error(exc)
    return [_response(user) for user in users]


def create_staff_account(email: str, temporary_password: str, display_name: str | None):
    client = _client()
    attributes = [
        {"Name": "email", "Value": email},
        {"Name": "email_verified", "Value": "true"},
    ]
    if display_name and display_name.strip():
        attributes.append({"Name": "name", "Value": display_name.strip()})
    try:
        result = client.admin_create_user(
            UserPoolId=_pool_id(), Username=email,
            TemporaryPassword=temporary_password, UserAttributes=attributes,
        )
        client.admin_add_user_to_group(
            UserPoolId=_pool_id(), Username=result["User"]["Username"], GroupName="staff",
        )
        return _response(result["User"])
    except (ClientError, BotoCoreError) as exc:
        _handle_error(exc)


def set_staff_enabled(username: str, enabled: bool) -> None:
    client = _client()
    try:
        method = client.admin_enable_user if enabled else client.admin_disable_user
        method(UserPoolId=_pool_id(), Username=username)
    except (ClientError, BotoCoreError) as exc:
        _handle_error(exc)


def reset_staff_password(username: str, temporary_password: str) -> None:
    try:
        _client().admin_set_user_password(
            UserPoolId=_pool_id(), Username=username,
            Password=temporary_password, Permanent=False,
        )
    except (ClientError, BotoCoreError) as exc:
        _handle_error(exc)


def _user_in_group(client, username: str, group_name: str) -> bool:
    token = None
    while True:
        args = {"UserPoolId": _pool_id(), "GroupName": group_name}
        if token:
            args["NextToken"] = token
        result = client.list_users_in_group(**args)
        if any(user.get("Username") == username for user in result.get("Users", [])):
            return True
        token = result.get("NextToken")
        if not token:
            return False


def delete_staff_account(username: str) -> None:
    client = _client()
    try:
        if _user_in_group(client, username, "admin"):
            raise HTTPException(status_code=403, detail="adminグループのユーザーは削除できません")
        if not _user_in_group(client, username, "staff"):
            raise HTTPException(status_code=403, detail="staffグループのユーザーだけ削除できます")
        client.admin_delete_user(UserPoolId=_pool_id(), Username=username)
    except HTTPException:
        raise
    except (ClientError, BotoCoreError) as exc:
        _handle_error(exc)


def ensure_cognito_user_enabled(username: str) -> None:
    try:
        user = _client().admin_get_user(UserPoolId=_pool_id(), Username=username)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"UserNotFoundException", "NotAuthorizedException"}:
            raise HTTPException(status_code=401, detail="このアカウントは利用できません") from exc
        _handle_error(exc)
    except BotoCoreError as exc:
        _handle_error(exc)
    if not user.get("Enabled", True):
        raise HTTPException(status_code=401, detail="このアカウントは無効化されています")
