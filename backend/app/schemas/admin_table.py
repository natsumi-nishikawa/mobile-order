from pydantic import BaseModel, Field


class AdminTableWrite(BaseModel):
    table_name: str = Field(min_length=1, max_length=100)


class AdminTableResponse(AdminTableWrite):
    id: int
