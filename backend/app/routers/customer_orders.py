from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.customer_auth import CurrentCustomer, get_current_customer, require_customer_session
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.selection import Selection
from app.schemas.customer import (
    OrderCreate,
    OrderCreateResponse,
    OrderItemResponse,
    OrderResponse,
)
from app.routers.customer_selections import remove_expired_selections


router = APIRouter(
    prefix="/api/customer",
    tags=["Customer"],
)


@router.post(
    "/orders",
    response_model=OrderCreateResponse,
)
def create_order(
    _data: OrderCreate,
    db: Session = Depends(get_db),
    customer: CurrentCustomer = Depends(get_current_customer),
):
    participant = customer.participant
    remove_expired_selections(db, customer.session.id)

    selections = db.scalars(
        select(Selection).where(
            Selection.participant_id == participant.id
        ).with_for_update()
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

        if product.is_deleted or not product.is_visible:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"{product.name}は現在販売されていません")
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
    customer: CurrentCustomer = Depends(get_current_customer),
):
    require_customer_session(session_id, customer)
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

        items = []
        for item, product in rows:
            effective_quantity = max(item.quantity - item.canceled_quantity, 0)
            items.append(OrderItemResponse(
                product_id=product.id,
                product_name=product.name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                canceled_quantity=item.canceled_quantity,
                served_quantity=item.served_quantity,
                effective_quantity=effective_quantity,
                line_total=effective_quantity * item.unit_price,
                is_served=(
                    effective_quantity > 0
                    and item.served_quantity >= effective_quantity
                ),
            ))

        result.append(
            OrderResponse(
                order_id=order.id,
                ordered_at=order.ordered_at,
                order_type=order.order_type,
                items=items,
            )
        )

    return result
