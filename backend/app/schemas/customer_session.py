from pydantic import BaseModel


class ActiveSessionResponse(BaseModel):
    table_id: int
    table_name: str
    session_id: int
    status: str
