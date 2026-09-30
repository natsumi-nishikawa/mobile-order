from pydantic import BaseModel


class ActiveSessionResponse(BaseModel):
    table_id: int
    session_id: int
    status: str