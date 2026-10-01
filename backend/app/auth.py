import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException
from dotenv import load_dotenv


load_dotenv()

CUSTOMER_JWT_SECRET = os.getenv("CUSTOMER_JWT_SECRET")
ALGORITHM = "HS256"


def create_customer_token(
    participant_id: int,
    session_id: int,
) -> str:
    if not CUSTOMER_JWT_SECRET:
        raise RuntimeError("CUSTOMER_JWT_SECRETが設定されていません")

    payload = {
        "participant_id": participant_id,
        "session_id": session_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
    }

    return jwt.encode(
        payload,
        CUSTOMER_JWT_SECRET,
        algorithm=ALGORITHM,
    )


def verify_customer_token(token: str) -> dict:
    if not CUSTOMER_JWT_SECRET:
        raise RuntimeError("CUSTOMER_JWT_SECRETが設定されていません")

    try:
        return jwt.decode(
            token,
            CUSTOMER_JWT_SECRET,
            algorithms=[ALGORITHM],
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="利用情報の有効期限が切れています",
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="利用情報を確認できません",
        )