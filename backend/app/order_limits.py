from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.session import Session as SessionModel


MAX_CUSTOMER_ITEM_QUANTITY = 20
MAX_ORDER_PRODUCT_TYPES = 30
MAX_CUSTOMER_ORDER_QUANTITY = 100
MAX_STAFF_ITEM_QUANTITY = 50
MAX_STAFF_ORDER_QUANTITY = 200
MAX_SESSION_ORDER_QUANTITY = 500
MAX_SESSION_ORDER_COUNT = 200
MAX_SESSION_PARTICIPANTS = 50


def lock_active_session(db: Session, session_id: int) -> SessionModel:
    session = db.scalar(
        select(SessionModel)
        .where(SessionModel.id == session_id, SessionModel.status == "active")
        .with_for_update()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="現在利用中のセッションが見つかりません")
    return session


def validate_session_order_capacity(
    db: Session,
    session_id: int,
    incoming_quantity: int,
) -> None:
    order_count = db.scalar(
        select(func.count(Order.id)).where(Order.session_id == session_id)
    ) or 0
    if order_count >= MAX_SESSION_ORDER_COUNT:
        raise HTTPException(
            status_code=409,
            detail=f"このセッションでは注文回数の上限（{MAX_SESSION_ORDER_COUNT}回）に達しています",
        )

    ordered_quantity = db.scalar(
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.session_id == session_id)
    ) or 0
    if ordered_quantity + incoming_quantity > MAX_SESSION_ORDER_QUANTITY:
        raise HTTPException(
            status_code=409,
            detail=f"このセッションでは累計注文数量の上限（{MAX_SESSION_ORDER_QUANTITY}個）を超えます",
        )
