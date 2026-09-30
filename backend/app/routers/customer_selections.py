from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
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


@router.get(
    "/sessions/{session_id}/selections",
    response_model=list[SelectionListItem],
)
def get_selections(
    session_id: int,
    db: Session = Depends(get_db),
):
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
):
    participant = db.get(Participant, data.participant_id)

    if participant is None:
        raise HTTPException(
            status_code=404,
            detail="利用者が見つかりません",
        )

    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="商品が見つかりません",
        )

    if product.is_sold_out:
        raise HTTPException(
            status_code=409,
            detail="この商品は売り切れです",
        )

    selection = db.scalar(
        select(Selection).where(
            Selection.participant_id == data.participant_id,
            Selection.product_id == product_id,
        )
    )

    if selection is None:
        selection = Selection(
            participant_id=data.participant_id,
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
    participant_id: int,
    db: Session = Depends(get_db),
):
    selection = db.scalar(
        select(Selection).where(
            Selection.participant_id == participant_id,
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