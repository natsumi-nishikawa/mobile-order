from pydantic import BaseModel, Field


class AdminCategoryResponse(BaseModel):
    id: int
    name: str
    display_order: int


class AdminProductWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: int = Field(ge=0, strict=True)
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=500)
    is_visible: bool = True
    is_deleted: bool = False
    is_sold_out: bool = False
    display_order: int | None = Field(default=None, ge=0, strict=True)
    category_ids: list[int] = Field(min_length=1)


class AdminProductResponse(AdminProductWrite):
    id: int
    category_names: list[str]
