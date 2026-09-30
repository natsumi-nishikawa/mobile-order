from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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

    nickname = data.nickname.strip()

    if not nickname:
        raise HTTPException(
            status_code=400,
            detail="ニックネームを入力してください",
        )

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

    return ParticipantResponse(
        participant_id=participant.id,
        session_id=participant.session_id,
        nickname=participant.nickname,
    )