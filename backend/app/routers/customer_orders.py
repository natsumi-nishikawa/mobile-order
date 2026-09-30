from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.participant import Participant
from app.models.product import Product
from app.models.selection import Selection
from app.schemas.customer import (
    OrderCreate,
    OrderCreateResponse,
    OrderItemResponse,
    OrderResponse,
)


router = APIRouter(
    prefix="/api/customer",
    tags=["Customer"],
)


@router.post(
    "/orders",
    response_model=OrderCreateResponse,
)
def create_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
):
    participant = db.get(Participant, data.participant_id)

    if participant is None:
        raise HTTPException(
            status_code=404,
            detail="利用者が見つかりません",
        )

    selections = db.scalars(
        select(Selection).where(
            Selection.participant_id == data.participant_id
        )
    ).all()

    if not selections:
        raise HTTPException(
            status_code=400,
            detail="商品が選択されていません",
        )

    order = Order(
        session_id=participant.session_id,
        participant_id=participant.id,
        order_type="customer",
    )

    db.add(order)
    db.flush()

    total_amount = 0

    for selection in selections:
        product = db.get(Product, selection.product_id)

        if product is None:
            db.rollback()
            raise HTTPException(
                status_code=404,
                detail="商品が見つかりません",
            )

        if product.is_sold_out:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"{product.name}は売り切れです",
            )

        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=selection.quantity,
            unit_price=product.price,
            canceled_quantity=0,
            served_quantity=0,
        )

        db.add(order_item)

        total_amount += product.price * selection.quantity

        db.delete(selection)

    db.commit()
    db.refresh(order)

    return OrderCreateResponse(
        order_id=order.id,
        ordered_at=order.ordered_at,
        total_amount=total_amount,
    )


@router.get(
    "/sessions/{session_id}/orders",
    response_model=list[OrderResponse],
)
def get_orders(
    session_id: int,
    db: Session = Depends(get_db),
):
    orders = db.scalars(
        select(Order)
        .where(Order.session_id == session_id)
        .order_by(Order.ordered_at)
    ).all()

    result = []

    for order in orders:
        rows = db.execute(
            select(OrderItem, Product)
            .join(
                Product,
                OrderItem.product_id == Product.id,
            )
            .where(OrderItem.order_id == order.id)
        ).all()

        items = [
            OrderItemResponse(
                product_id=product.id,
                product_name=product.name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                canceled_quantity=item.canceled_quantity,
                served_quantity=item.served_quantity,
            )
            for item, product in rows
        ]

        result.append(
            OrderResponse(
                order_id=order.id,
                ordered_at=order.ordered_at,
                order_type=order.order_type,
                items=items,
            )
        )

    return result