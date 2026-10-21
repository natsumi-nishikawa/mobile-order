from typing import Annotated

from app.demo_auth import (
    DemoAuthSettings,
    DemoSession,
    clear_demo_cookie,
    client_key,
    create_demo_session,
    login_rate_limiter,
    require_demo_csrf,
    require_demo_session,
    require_demo_settings,
    set_demo_cookie,
    verify_password,
    verify_request_origin,
)
from app.schemas.demo_auth import (
    DemoLoginRequest,
    DemoLogoutResponse,
    DemoSessionResponse,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Response

router = APIRouter(prefix="/api/demo-auth", tags=["Demo authentication"])


@router.post("/login", response_model=DemoSessionResponse)
def login(
    data: DemoLoginRequest,
    request: Request,
    response: Response,
    settings: Annotated[DemoAuthSettings, Depends(require_demo_settings)],
):
    verify_request_origin(request, settings)
    key = client_key(request)
    login_rate_limiter.check(key, settings)
    if not verify_password(data.password, settings):
        login_rate_limiter.record_failure(key, settings)
        raise HTTPException(status_code=401, detail="パスワードが正しくありません")

    login_rate_limiter.clear(key)
    token, session = create_demo_session(settings)
    set_demo_cookie(response, token, settings)
    return DemoSessionResponse(
        authenticated=True,
        expires_at=session.expires_at,
        csrf_token=session.csrf_token,
    )


@router.get("/session", response_model=DemoSessionResponse)
def get_session(
    session: Annotated[DemoSession, Depends(require_demo_session)],
):
    return DemoSessionResponse(
        authenticated=True,
        expires_at=session.expires_at,
        csrf_token=session.csrf_token,
    )


@router.post("/logout", response_model=DemoLogoutResponse)
def logout(
    response: Response,
    _session: Annotated[DemoSession, Depends(require_demo_csrf)],
    settings: Annotated[DemoAuthSettings, Depends(require_demo_settings)],
):
    clear_demo_cookie(response, settings)
    return DemoLogoutResponse()
