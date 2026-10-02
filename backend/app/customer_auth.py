from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import verify_customer_token
from app.database import get_db
from app.models.participant import Participant
from app.models.session import Session as SessionModel
from app.models.table import Table


security = HTTPBearer()


@dataclass
class CurrentCustomer:
    participant: Participant
    session: SessionModel
    table: Table


def get_current_customer(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> CurrentCustomer:
    payload = verify_customer_token(credentials.credentials)
    participant_id = payload.get("participant_id")
    session_id = payload.get("session_id")

    if not isinstance(participant_id, int) or not isinstance(session_id, int):
        raise HTTPException(status_code=401, detail="利用者情報を確認できません")

    row = db.execute(
        select(Participant, SessionModel, Table)
        .join(SessionModel, Participant.session_id == SessionModel.id)
        .join(Table, SessionModel.table_id == Table.id)
        .where(
            Participant.id == participant_id,
            Participant.session_id == session_id,
            SessionModel.id == session_id,
            SessionModel.status == "active",
        )
    ).first()

    if row is None:
        raise HTTPException(status_code=401, detail="現在の利用情報は終了しています")

    participant, session, table = row
    return CurrentCustomer(participant=participant, session=session, table=table)


def require_customer_session(
    session_id: int,
    customer: CurrentCustomer,
) -> None:
    if customer.session.id != session_id:
        raise HTTPException(status_code=403, detail="別の利用情報にはアクセスできません")
