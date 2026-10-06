from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.session import Session as SessionModel
from app.models.table import Table
from app.schemas.staff import (
    QuantityUpdate,
    StaffAccountingDetail,
    StaffAccountingItem,
    StaffCategoryResponse,
    StaffOrderCreate,
    StaffOrderItemResponse,
    StaffOrderResponse,
    StaffProductResponse,
    StaffSessionResponse,
    StaffSessionSummary,
    StaffTableResponse,
)
from app.services.menu_catalog import get_menu_categories, get_menu_products
from app.store_auth import require_staff


router = APIRouter(prefix="/api/staff", tags=["Staff"], dependencies=[Depends(require_staff)])


def _active_session(db: Session, table_id: int) -> SessionModel | None:
    return db.scalar(select(SessionModel).where(
        SessionModel.table_id == table_id,
        SessionModel.status == "active",
    ).order_by(SessionModel.started_at.desc(), SessionModel.id.desc()))


def _session_response(session: SessionModel) -> StaffSessionResponse:
    return StaffSessionResponse(
        id=session.id, table_id=session.table_id, status=session.status,
        started_at=session.started_at, completed_at=session.completed_at,
    )


@router.get("/tables", response_model=list[StaffTableResponse])
def get_tables(db: Session = Depends(get_db)):
    tables = db.scalars(select(Table).order_by(Table.id)).all()
    result = []
    for table in tables:
        active = _active_session(db, table.id)
        result.append(StaffTableResponse(
            id=table.id,
            table_name=table.table_name,
            is_in_use=active is not None,
            active_session=None if active is None else StaffSessionSummary(
                id=active.id, status=active.status, started_at=active.started_at,
            ),
        ))
    return result


@router.post(
    "/tables/{table_id}/sessions",
    response_model=StaffSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_session(table_id: int, db: Session = Depends(get_db)):
    table = db.scalar(select(Table).where(Table.id == table_id).with_for_update())
    if table is None:
        raise HTTPException(status_code=404, detail="テーブルが見つかりません")
    if _active_session(db, table_id) is not None:
        raise HTTPException(status_code=409, detail="このテーブルはすでに利用中です")
    session = SessionModel(table_id=table_id, status="active")
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_response(session)


@router.post("/sessions/{session_id}/complete", response_model=StaffSessionResponse)
def complete_session(session_id: int, db: Session = Depends(get_db)):
    session = db.scalar(select(SessionModel).where(
        SessionModel.id == session_id
    ).with_for_update())
    if session is None:
        raise HTTPException(status_code=404, detail="利用情報が見つかりません")
    if session.status != "active":
        raise HTTPException(status_code=409, detail="この利用情報はすでに終了しています")
    session.status = "completed"
    session.completed_at = datetime.now()
    db.commit()
    db.refresh(session)
    return _session_response(session)


@router.get("/sessions/{session_id}/accounting", response_model=StaffAccountingDetail)
def get_accounting(session_id: int, db: Session = Depends(get_db)):
    session_row = db.execute(
        select(SessionModel, Table)
        .join(Table, Table.id == SessionModel.table_id)
        .where(SessionModel.id == session_id, SessionModel.status == "active")
    ).first()
    if session_row is None:
        raise HTTPException(status_code=404, detail="利用中のSessionが見つかりません")
    session, table = session_row
    rows = db.execute(
        select(OrderItem, Product)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(Order.session_id == session_id)
        .order_by(Order.ordered_at, Order.id, OrderItem.id)
    ).all()
    items = []
    for item, product in rows:
        billable_quantity = max(item.quantity - item.canceled_quantity, 0)
        items.append(StaffAccountingItem(
            order_item_id=item.id, product_name=product.name,
            unit_price=item.unit_price, quantity=item.quantity,
            canceled_quantity=item.canceled_quantity,
            billable_quantity=billable_quantity,
            subtotal=item.unit_price * billable_quantity,
        ))
    return StaffAccountingDetail(
        session_id=session.id, table_id=table.id, table_name=table.table_name,
        items=items,
        total_item_count=sum(item.billable_quantity for item in items),
        total_amount=sum(item.subtotal for item in items),
    )


def _order_response(db: Session, order: Order, table: Table) -> StaffOrderResponse:
    rows = db.execute(
        select(OrderItem, Product)
        .join(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.order_id == order.id)
        .order_by(OrderItem.id)
    ).all()
    return StaffOrderResponse(
        id=order.id, session_id=order.session_id, table_id=table.id,
        table_name=table.table_name, order_type=order.order_type,
        ordered_at=order.ordered_at,
        items=[StaffOrderItemResponse(
            id=item.id, product_id=product.id, product_name=product.name,
            quantity=item.quantity, canceled_quantity=item.canceled_quantity,
            served_quantity=item.served_quantity,
            effective_quantity=max(item.quantity - item.canceled_quantity, 0),
            unit_price=item.unit_price,
        ) for item, product in rows],
    )


@router.get("/orders", response_model=list[StaffOrderResponse])
def get_orders(active_only: bool = True, db: Session = Depends(get_db)):
    statement = (
        select(Order, Table)
        .join(SessionModel, SessionModel.id == Order.session_id)
        .join(Table, Table.id == SessionModel.table_id)
    )
    if active_only:
        statement = statement.where(SessionModel.status == "active")
    rows = db.execute(statement.order_by(Order.ordered_at.desc(), Order.id.desc())).all()
    return [_order_response(db, order, table) for order, table in rows]


def _locked_active_item(db: Session, item_id: int) -> OrderItem:
    item = db.scalar(
        select(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(SessionModel, SessionModel.id == Order.session_id)
        .where(OrderItem.id == item_id, SessionModel.status == "active")
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="利用中の注文商品が見つかりません")
    return item


@router.patch("/order-items/{item_id}/served", response_model=StaffOrderItemResponse)
def update_served(item_id: int, data: QuantityUpdate, db: Session = Depends(get_db)):
    item = _locked_active_item(db, item_id)
    effective = item.quantity - item.canceled_quantity
    if data.quantity > effective:
        raise HTTPException(status_code=422, detail="提供済み数量は有効数量以下にしてください")
    item.served_quantity = data.quantity
    db.commit()
    product = db.get(Product, item.product_id)
    return StaffOrderItemResponse(
        id=item.id, product_id=product.id, product_name=product.name,
        quantity=item.quantity, canceled_quantity=item.canceled_quantity,
        served_quantity=item.served_quantity, effective_quantity=effective,
        unit_price=item.unit_price,
    )


@router.patch("/order-items/{item_id}/canceled", response_model=StaffOrderItemResponse)
def update_canceled(item_id: int, data: QuantityUpdate, db: Session = Depends(get_db)):
    item = _locked_active_item(db, item_id)
    if data.quantity > item.quantity:
        raise HTTPException(status_code=422, detail="キャンセル数量は注文数量以下にしてください")
    item.canceled_quantity = data.quantity
    effective = item.quantity - data.quantity
    item.served_quantity = min(item.served_quantity, effective)
    db.commit()
    product = db.get(Product, item.product_id)
    return StaffOrderItemResponse(
        id=item.id, product_id=product.id, product_name=product.name,
        quantity=item.quantity, canceled_quantity=item.canceled_quantity,
        served_quantity=item.served_quantity, effective_quantity=effective,
        unit_price=item.unit_price,
    )


@router.get("/products", response_model=list[StaffProductResponse])
def get_products(db: Session = Depends(get_db)):
    return [StaffProductResponse(
        id=product.id, name=product.name, price=product.price,
        is_sold_out=product.is_sold_out, category_ids=category_ids,
    ) for product, category_ids in get_menu_products(db)]


@router.get("/categories", response_model=list[StaffCategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    return get_menu_categories(db)


@router.post("/orders", response_model=StaffOrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(data: StaffOrderCreate, db: Session = Depends(get_db)):
    session = db.scalar(select(SessionModel).where(
        SessionModel.id == data.session_id, SessionModel.status == "active"
    ).with_for_update())
    if session is None:
        raise HTTPException(status_code=404, detail="利用中のSessionが見つかりません")
    product_ids = [item.product_id for item in data.items]
    if len(product_ids) != len(set(product_ids)):
        raise HTTPException(status_code=422, detail="同じ商品を重複して指定できません")
    products = {product.id: product for product in db.scalars(
        select(Product).where(Product.id.in_(product_ids))
    ).all()}
    if len(products) != len(product_ids):
        raise HTTPException(status_code=404, detail="商品が見つかりません")
    sold_out = [products[item.product_id].name for item in data.items if products[item.product_id].is_sold_out]
    if sold_out:
        raise HTTPException(status_code=409, detail=f"{sold_out[0]}は売り切れです")
    order = Order(session_id=session.id, participant_id=None, order_type="staff")
    db.add(order)
    db.flush()
    for requested in data.items:
        product = products[requested.product_id]
        db.add(OrderItem(
            order_id=order.id, product_id=product.id, quantity=requested.quantity,
            unit_price=product.price, canceled_quantity=0, served_quantity=0,
        ))
    db.commit()
    db.refresh(order)
    table = db.get(Table, session.table_id)
    return _order_response(db, order, table)
