from datetime import datetime

from pydantic import BaseModel, Field

from app.order_limits import MAX_CUSTOMER_ITEM_QUANTITY

# ---------- ニックネーム ----------

class ParticipantCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=20)


class ParticipantResponse(BaseModel):
    participant_id: int
    session_id: int
    nickname: str
    access_token: str


class CustomerTableResponse(BaseModel):
    id: int
    table_name: str
    is_in_use: bool


# ---------- カテゴリ ----------

class CategoryResponse(BaseModel):
    id: int
    name: str
    display_order: int


# ---------- 商品 ----------

class ProductResponse(BaseModel):
    id: int
    name: str
    price: int
    description: str | None
    image_url: str | None
    is_sold_out: bool
    display_order: int | None
    category_ids: list[int]


# ---------- 選択中商品 ----------

class SelectionUpdate(BaseModel):
    quantity: int = Field(ge=1, le=MAX_CUSTOMER_ITEM_QUANTITY)


class SelectionResponse(BaseModel):
    product_id: int
    quantity: int
    total_selected_quantity: int


class SelectionListItem(BaseModel):
    participant_id: int
    nickname: str
    product_id: int
    product_name: str
    quantity: int


# ---------- 注文 ----------

class OrderCreate(BaseModel):
    pass


class OrderCreateResponse(BaseModel):
    order_id: int
    ordered_at: datetime
    total_amount: int


class OrderItemResponse(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price: int
    canceled_quantity: int
    served_quantity: int
    effective_quantity: int
    line_total: int
    is_served: bool


class OrderResponse(BaseModel):
    order_id: int
    ordered_at: datetime
    order_type: str
    items: list[OrderItemResponse]


# ---------- 会計 ----------

class BillResponse(BaseModel):
    session_id: int
    total_amount: int
