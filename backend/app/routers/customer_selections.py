from fastapi import APIRouter, Depends, HTTPException
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.customer_auth import CurrentCustomer, get_current_customer, require_customer_session
from app.models.participant import Participant
from app.models.product import Product
from app.models.selection import Selection
from app.schemas.customer import (
    SelectionListItem,
    SelectionResponse,
    SelectionUpdate,
)


router = APIRouter(
    prefix="/api/customer",
    tags=["Customer"],
)


def remove_expired_selections(db: Session, session_id: int) -> None:
    participant_ids = select(Participant.id).where(Participant.session_id == session_id)
    db.execute(
        delete(Selection).where(
            Selection.participant_id.in_(participant_ids),
            Selection.last_selected_at < func.now() - timedelta(minutes=10),
        )
    )


@router.get(
    "/sessions/{session_id}/selections",
    response_model=list[SelectionListItem],
)
def get_selections(
    session_id: int,
    db: Session = Depends(get_db),
    customer: CurrentCustomer = Depends(get_current_customer),
):
    require_customer_session(session_id, customer)
    remove_expired_selections(db, session_id)
    db.commit()
    rows = db.execute(
        select(Selection, Participant, Product)
        .join(
            Participant,
            Selection.participant_id == Participant.id,
        )
        .join(
            Product,
            Selection.product_id == Product.id,
        )
        .where(Participant.session_id == session_id)
    ).all()

    return [
        SelectionListItem(
            participant_id=participant.id,
            nickname=participant.nickname,
            product_id=product.id,
            product_name=product.name,
            quantity=selection.quantity,
        )
        for selection, participant, product in rows
    ]


@router.put(
    "/selections/{product_id}",
    response_model=SelectionResponse,
)
def update_selection(
    product_id: int,
    data: SelectionUpdate,
    db: Session = Depends(get_db),
    customer: CurrentCustomer = Depends(get_current_customer),
):
    participant = customer.participant
    remove_expired_selections(db, customer.session.id)

    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="商品が見つかりません",
        )

    if product.is_deleted or not product.is_visible:
        raise HTTPException(
            status_code=409,
            detail="この商品は現在販売されていません",
        )

    if product.is_sold_out:
        raise HTTPException(
            status_code=409,
            detail="この商品は売り切れです",
        )

    selection = db.scalar(
        select(Selection).where(
            Selection.participant_id == participant.id,
            Selection.product_id == product_id,
        )
    )

    if selection is None:
        selection = Selection(
            participant_id=participant.id,
            product_id=product_id,
            quantity=data.quantity,
        )
        db.add(selection)
    else:
        selection.quantity = data.quantity
        selection.last_selected_at = func.now()

    db.commit()

    total_selected_quantity = db.scalar(
        select(func.coalesce(func.sum(Selection.quantity), 0))
        .join(
            Participant,
            Selection.participant_id == Participant.id,
        )
        .where(
            Participant.session_id == participant.session_id,
            Selection.product_id == product_id,
        )
    )

    return SelectionResponse(
        product_id=product_id,
        quantity=data.quantity,
        total_selected_quantity=total_selected_quantity,
    )


@router.delete("/selections/{product_id}")
def delete_selection(
    product_id: int,
    db: Session = Depends(get_db),
    customer: CurrentCustomer = Depends(get_current_customer),
):
    selection = db.scalar(
        select(Selection).where(
            Selection.participant_id == customer.participant.id,
            Selection.product_id == product_id,
        )
    )

    if selection is None:
        raise HTTPException(
            status_code=404,
            detail="選択中の商品が見つかりません",
        )

    db.delete(selection)
    db.commit()

    return {"message": "選択を削除しました"}
