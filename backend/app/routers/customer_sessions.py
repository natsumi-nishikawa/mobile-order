from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.business_hour import BusinessHour
from app.models.session import Session as SessionModel
from app.models.table import Table
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
    from datetime import datetime

    now = datetime.now()
    business_hour = db.scalar(
        select(BusinessHour).where(BusinessHour.day_of_week == now.weekday())
    )

    if business_hour is not None:
        is_outside = not business_hour.is_open
        if business_hour.opening_time and business_hour.closing_time:
            current_time = now.time()
            if business_hour.opening_time <= business_hour.closing_time:
                is_outside = is_outside or not (
                    business_hour.opening_time <= current_time < business_hour.closing_time
                )
            else:
                is_outside = is_outside or not (
                    current_time >= business_hour.opening_time
                    or current_time < business_hour.closing_time
                )
        if is_outside:
            raise HTTPException(status_code=403, detail="現在は営業時間外です")

    statement = (
        select(SessionModel, Table)
        .join(Table, SessionModel.table_id == Table.id)
        .where(
            SessionModel.table_id == table_id,
            SessionModel.status == "active",
        )
        .order_by(SessionModel.started_at.desc())
    )

    row = db.execute(statement).first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="現在利用できません",
        )

    active_session, table = row
    return ActiveSessionResponse(
        table_id=table_id,
        table_name=table.table_name,
        session_id=active_session.id,
        status=active_session.status,
    )
