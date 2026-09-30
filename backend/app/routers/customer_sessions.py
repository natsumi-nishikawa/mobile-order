from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.session import Session as SessionModel
from app.schemas.customer_session import ActiveSessionResponse


router = APIRouter(
    prefix="/api/customer",
    tags=["Customer"],
)


@router.get(
    "/tables/{table_id}/session",
    response_model=ActiveSessionResponse,
)
def get_active_session(
    table_id: int,
    db: Session = Depends(get_db),
):
    statement = select(SessionModel).where(
        SessionModel.table_id == table_id,
        SessionModel.status == "active",
    )

    active_session = db.scalar(statement)

    if active_session is None:
        raise HTTPException(
            status_code=404,
            detail="現在利用できません",
        )

    return ActiveSessionResponse(
        table_id=table_id,
        session_id=active_session.id,
        status=active_session.status,
    )