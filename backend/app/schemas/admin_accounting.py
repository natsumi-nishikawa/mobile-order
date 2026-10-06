from datetime import datetime

from pydantic import BaseModel


class AdminAccountingHistoryItem(BaseModel):
    session_id: int
    table_id: int
    table_name: str
    started_at: datetime
    completed_at: datetime
    total_amount: int


class AdminAccountingOrderItem(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    canceled_quantity: int
    unit_price: int
    amount: int


class AdminAccountingOrder(BaseModel):
    order_id: int
    ordered_at: datetime
    items: list[AdminAccountingOrderItem]


class AdminAccountingDetail(AdminAccountingHistoryItem):
    orders: list[AdminAccountingOrder]


class AdminSessionReopenResponse(BaseModel):
    session_id: int
    status: str
    completed_at: datetime | None
