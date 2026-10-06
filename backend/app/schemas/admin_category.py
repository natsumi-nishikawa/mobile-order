from pydantic import BaseModel, Field


class AdminCategoryWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    display_order: int = Field(ge=0, strict=True)


class AdminCategoryResponse(AdminCategoryWrite):
    id: int
