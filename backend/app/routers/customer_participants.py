from app.auth import create_customer_token
from app.customer_auth import CurrentCustomer, get_current_customer
from app.database import get_db
from app.demo_auth import require_demo_csrf, require_demo_session
from app.models.participant import Participant
from app.models.session import Session as SessionModel
from app.models.table import Table
from app.order_limits import MAX_SESSION_PARTICIPANTS
from app.rate_limit_dependencies import limit_customer_join
from app.schemas.customer import ParticipantCreate, ParticipantResponse
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/api/customer",
    tags=["Customer"],
    dependencies=[Depends(require_demo_session)],
)


@router.post(
    "/sessions/{session_id}/participants",
    response_model=ParticipantResponse,
    dependencies=[Depends(require_demo_csrf), Depends(limit_customer_join)],
)
def create_participant(
    session_id: int,
    data: ParticipantCreate,
    db: Session = Depends(get_db),
):
    # 利用中のSessionか確認
    active_session = db.scalar(
        select(SessionModel)
        .join(Table, SessionModel.table_id == Table.id)
        .where(
            SessionModel.id == session_id,
            SessionModel.status == "active",
        )
        .with_for_update(of=SessionModel)
    )

    if active_session is None:
        raise HTTPException(
            status_code=404,
            detail="現在利用できません",
        )

    participant_count = db.scalar(
        select(func.count(Participant.id)).where(Participant.session_id == session_id)
    ) or 0
    if participant_count >= MAX_SESSION_PARTICIPANTS:
        raise HTTPException(
            status_code=409,
            detail=f"このセッションでは参加者数の上限（{MAX_SESSION_PARTICIPANTS}人）に達しています",
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
