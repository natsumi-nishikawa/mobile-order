from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.customer_auth import CurrentCustomer, get_current_customer
from app.demo_auth import DemoSession, require_demo_session
from app.rate_limit import (
    ApiRateLimitSettings,
    api_rate_limiter,
    get_api_rate_limit_settings,
)
from app.store_auth import StoreUser, require_staff


def require_api_rate_limit_settings() -> ApiRateLimitSettings:
    try:
        return get_api_rate_limit_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="レート制限を利用できません") from exc


def limit_customer_join(
    request: Request,
    session: Annotated[DemoSession, Depends(require_demo_session)],
    settings: Annotated[ApiRateLimitSettings, Depends(require_api_rate_limit_settings)],
) -> None:
    client_ip = request.client.host if request.client else "unknown"
    api_rate_limiter.check_and_record(
        f"customer_join:{session.session_id}:{client_ip}",
        settings.customer_join_limit,
        settings.customer_join_window_seconds,
        settings.max_keys,
    )


def limit_customer_order(
    customer: Annotated[CurrentCustomer, Depends(get_current_customer)],
    settings: Annotated[ApiRateLimitSettings, Depends(require_api_rate_limit_settings)],
) -> None:
    api_rate_limiter.check_and_record(
        f"customer_order:{customer.participant.id}",
        settings.customer_order_limit,
        settings.customer_order_window_seconds,
        settings.max_keys,
    )


def limit_customer_selection(
    customer: Annotated[CurrentCustomer, Depends(get_current_customer)],
    settings: Annotated[ApiRateLimitSettings, Depends(require_api_rate_limit_settings)],
) -> None:
    api_rate_limiter.check_and_record(
        f"customer_selection:{customer.participant.id}",
        settings.customer_selection_limit,
        settings.customer_selection_window_seconds,
        settings.max_keys,
    )


def limit_staff_order(
    user: Annotated[StoreUser, Depends(require_staff)],
    settings: Annotated[ApiRateLimitSettings, Depends(require_api_rate_limit_settings)],
) -> None:
    api_rate_limiter.check_and_record(
        f"staff_order:{user.subject}",
        settings.staff_order_limit,
        settings.staff_order_window_seconds,
        settings.max_keys,
    )
