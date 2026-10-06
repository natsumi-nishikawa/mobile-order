from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.session import Session as SessionModel
from app.models.table import Table
from app.schemas.admin_accounting import (
    AdminAccountingDetail,
    AdminAccountingHistoryItem,
    AdminAccountingOrder,
    AdminAccountingOrderItem,
    AdminSessionReopenResponse,
)


router = APIRouter(prefix="/api/admin/accounting", tags=["Admin accounting"])


def _total_subquery():
    return (
        select(
            Order.session_id.label("session_id"),
            func.coalesce(func.sum(
                func.greatest(OrderItem.quantity - OrderItem.canceled_quantity, 0)
                * OrderItem.unit_price
            ), 0).label("total_amount"),
        )
        .join(OrderItem, OrderItem.order_id == Order.id)
        .group_by(Order.session_id)
        .subquery()
    )


def _history_statement(session_id: int | None = None):
    totals = _total_subquery()
    statement = (
        select(SessionModel, Table, func.coalesce(totals.c.total_amount, 0))
        .join(Table, Table.id == SessionModel.table_id)
        .outerjoin(totals, totals.c.session_id == SessionModel.id)
        .where(SessionModel.status == "completed", SessionModel.completed_at.is_not(None))
    )
    if session_id is not None:
        statement = statement.where(SessionModel.id == session_id)
    return statement


def _history_response(session: SessionModel, table: Table, total: int):
    return AdminAccountingHistoryItem(
        session_id=session.id,
        table_id=table.id,
        table_name=table.table_name,
        started_at=session.started_at,
        completed_at=session.completed_at,
        total_amount=total,
    )


@router.get("/history", response_model=list[AdminAccountingHistoryItem])
def get_accounting_history(db: Session = Depends(get_db)):
    rows = db.execute(_history_statement().order_by(SessionModel.completed_at.desc())).all()
    return [_history_response(session, table, total) for session, table, total in rows]


@router.get("/history/{session_id}", response_model=AdminAccountingDetail)
def get_accounting_detail(session_id: int, db: Session = Depends(get_db)):
    row = db.execute(_history_statement(session_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="会計履歴が見つかりません")
    session, table, total = row
    orders = db.scalars(
        select(Order).where(Order.session_id == session_id).order_by(Order.ordered_at, Order.id)
    ).all()
    order_responses = []
    for order in orders:
        items = db.execute(
            select(OrderItem, Product)
            .join(Product, Product.id == OrderItem.product_id)
            .where(OrderItem.order_id == order.id)
            .order_by(OrderItem.id)
        ).all()
        order_responses.append(AdminAccountingOrder(
            order_id=order.id,
            ordered_at=order.ordered_at,
            items=[AdminAccountingOrderItem(
                product_id=product.id,
                product_name=product.name,
                quantity=item.quantity,
                canceled_quantity=item.canceled_quantity,
                unit_price=item.unit_price,
                amount=max(item.quantity - item.canceled_quantity, 0) * item.unit_price,
            ) for item, product in items],
        ))
    history = _history_response(session, table, total)
    return AdminAccountingDetail(**history.model_dump(), orders=order_responses)


@router.post("/history/{session_id}/reopen", response_model=AdminSessionReopenResponse)
def reopen_completed_session(session_id: int, db: Session = Depends(get_db)):
    session = db.scalar(
        select(SessionModel).where(SessionModel.id == session_id).with_for_update()
    )
    if session is None or session.status != "completed":
        raise HTTPException(status_code=404, detail="会計完了済みの利用情報が見つかりません")

    table = db.scalar(select(Table).where(Table.id == session.table_id).with_for_update())
    active_session_id = db.scalar(
        select(SessionModel.id).where(
            SessionModel.table_id == session.table_id,
            SessionModel.status == "active",
            SessionModel.id != session.id,
        ).limit(1)
    )
    if active_session_id is not None:
        raise HTTPException(status_code=409, detail="同じテーブルに利用中のSessionがあるため取消できません")

    session.status = "active"
    session.completed_at = None
    db.commit()
    db.refresh(session)
    return AdminSessionReopenResponse(
        session_id=session.id,
        status=session.status,
        completed_at=session.completed_at,
    )
