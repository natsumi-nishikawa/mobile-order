from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import create_customer_token
from app.customer_auth import CurrentCustomer, get_current_customer
from app.database import get_db
from app.models.participant import Participant
from app.models.session import Session as SessionModel
from app.schemas.customer import ParticipantCreate, ParticipantResponse


router = APIRouter(
    prefix="/api/customer",
    tags=["Customer"],
)


@router.post(
    "/sessions/{session_id}/participants",
    response_model=ParticipantResponse,
)
def create_participant(
    session_id: int,
    data: ParticipantCreate,
    db: Session = Depends(get_db),
):
    # 利用中のSessionか確認
    active_session = db.scalar(
        select(SessionModel).where(
            SessionModel.id == session_id,
            SessionModel.status == "active",
        )
    )

    if active_session is None:
        raise HTTPException(
            status_code=404,
            detail="現在利用できません",
        )

    # ニックネームの前後の空白を削除
    nickname = data.nickname.strip()

    if not nickname:
        raise HTTPException(
            status_code=400,
            detail="ニックネームを入力してください",
        )

    # 利用者を作成
    participant = Participant(
        session_id=session_id,
        nickname=nickname,
    )

    db.add(participant)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="このニックネームは既に使用されています",
        )

    db.refresh(participant)

    # Customer用JWTを発行
    token = create_customer_token(
        participant_id=participant.id,
        session_id=participant.session_id,
    )

    return ParticipantResponse(
        participant_id=participant.id,
        session_id=participant.session_id,
        nickname=participant.nickname,
        access_token=token,
    )


@router.get("/me")
def get_current_participant(
    customer: CurrentCustomer = Depends(get_current_customer),
):
    return {
        "participant_id": customer.participant.id,
        "session_id": customer.session.id,
        "table_id": customer.table.id,
        "table_name": customer.table.table_name,
        "nickname": customer.participant.nickname,
    }
