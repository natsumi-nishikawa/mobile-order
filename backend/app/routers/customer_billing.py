from app.customer_auth import (
    CurrentCustomer,
    get_current_customer,
    require_customer_session,
)
from app.database import get_db
from app.demo_auth import require_demo_session
from app.models.order import Order
from app.models.order_item import OrderItem
from app.schemas.customer import BillResponse
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/api/customer",
    tags=["Customer"],
    dependencies=[Depends(require_demo_session)],
)


@router.get(
    "/sessions/{session_id}/bill",
    response_model=BillResponse,
)
def get_bill(
    session_id: int,
    db: Session = Depends(get_db),
    customer: CurrentCustomer = Depends(get_current_customer),
):
    require_customer_session(session_id, customer)
    total_amount = db.scalar(
        select(
            func.coalesce(
                func.sum(
                    (OrderItem.quantity - OrderItem.canceled_quantity)
                    * OrderItem.unit_price
                ),
                0,
            )
        )
        .join(
            Order,
            OrderItem.order_id == Order.id,
        )
        .where(Order.session_id == session_id)
    )

    return BillResponse(
        session_id=session_id,
        total_amount=total_amount,
    )
