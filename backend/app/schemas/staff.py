from datetime import datetime

from pydantic import BaseModel, Field


class StaffSessionSummary(BaseModel):
    id: int
    status: str
    started_at: datetime


class StaffTableResponse(BaseModel):
    id: int
    table_name: str
    is_in_use: bool
    active_session: StaffSessionSummary | None


class StaffSessionResponse(BaseModel):
    id: int
    table_id: int
    status: str
    started_at: datetime
    completed_at: datetime | None


class StaffOrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    canceled_quantity: int
    served_quantity: int
    effective_quantity: int
    unit_price: int


class StaffOrderResponse(BaseModel):
    id: int
    session_id: int
    table_id: int
    table_name: str
    order_type: str
    ordered_at: datetime
    items: list[StaffOrderItemResponse]


class StaffAccountingItem(BaseModel):
    order_item_id: int
    product_name: str
    unit_price: int
    quantity: int
    canceled_quantity: int
    billable_quantity: int
    subtotal: int


class StaffAccountingDetail(BaseModel):
    session_id: int
    table_id: int
    table_name: str
    items: list[StaffAccountingItem]
    total_item_count: int
    total_amount: int


class QuantityUpdate(BaseModel):
    quantity: int = Field(ge=0)


class StaffProductResponse(BaseModel):
    id: int
    name: str
    price: int
    is_sold_out: bool
    category_ids: list[int]


class StaffCategoryResponse(BaseModel):
    id: int
    name: str
    display_order: int


class StaffOrderCreateItem(BaseModel):
    product_id: int
    quantity: int = Field(ge=1)


class StaffOrderCreate(BaseModel):
    session_id: int
    items: list[StaffOrderCreateItem] = Field(min_length=1)
