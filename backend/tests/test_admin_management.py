import os
from datetime import datetime, time

os.environ["ENV_FILE"] = ".env.test"

from dotenv import load_dotenv

load_dotenv(".env.test", override=True)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app
from app.models.business_hour import BusinessHour
from app.models.category import Category
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.participant import Participant
from app.models.product import Product
from app.models.product_category import ProductCategory
from app.models.selection import Selection
from app.models.session import Session
from app.models.table import Table
from app.store_auth import StoreUser, require_admin


TEST_DATABASE_URL = os.getenv("DATABASE_URL")
assert TEST_DATABASE_URL is not None
assert TEST_DATABASE_URL.endswith("/mobile_order_test")

test_engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[require_admin] = lambda: StoreUser("test-admin", "admin", frozenset({"admin"}))
client = TestClient(app)


def clear_test_data():
    with TestingSessionLocal() as db:
        db.execute(delete(OrderItem))
        db.execute(delete(Order))
        db.execute(delete(Selection))
        db.execute(delete(ProductCategory))
        db.execute(delete(Participant))
        db.execute(delete(Product))
        db.execute(delete(Category))
        db.execute(delete(Session))
        db.execute(delete(BusinessHour))
        db.execute(delete(Table))
        db.commit()


def test_category_crud_and_product_reference_protection():
    clear_test_data()

    response = client.post(
        "/api/admin/categories",
        json={"name": " ドリンク ", "display_order": 2},
    )
    assert response.status_code == 201
    category_id = response.json()["id"]
    assert response.json()["name"] == "ドリンク"

    response = client.put(
        f"/api/admin/categories/{category_id}",
        json={"name": "ソフトドリンク", "display_order": 1},
    )
    assert response.status_code == 200
    assert response.json()["display_order"] == 1

    with TestingSessionLocal() as db:
        product = Product(name="コーラ", price=400, is_sold_out=False)
        db.add(product)
        db.flush()
        db.add(ProductCategory(product_id=product.id, category_id=category_id))
        db.commit()
        product_id = product.id

    assert client.delete(f"/api/admin/categories/{category_id}").status_code == 409
    with TestingSessionLocal() as db:
        assert db.get(Product, product_id) is not None
        assert db.get(Category, category_id) is not None

    response = client.post(
        "/api/admin/categories",
        json={"name": "未使用", "display_order": 3},
    )
    unused_id = response.json()["id"]
    assert client.delete(f"/api/admin/categories/{unused_id}").status_code == 204
    clear_test_data()


def test_table_crud_and_session_reference_protection():
    clear_test_data()

    response = client.post("/api/admin/tables", json={"table_name": " A-1 "})
    assert response.status_code == 201
    table_id = response.json()["id"]
    assert response.json()["table_name"] == "A-1"

    response = client.put(f"/api/admin/tables/{table_id}", json={"table_name": "A-2"})
    assert response.status_code == 200
    assert response.json()["table_name"] == "A-2"

    with TestingSessionLocal() as db:
        db.add(Session(table_id=table_id, status="completed", completed_at=datetime.now()))
        db.commit()
    assert client.delete(f"/api/admin/tables/{table_id}").status_code == 409

    unused_id = client.post("/api/admin/tables", json={"table_name": "B-1"}).json()["id"]
    assert client.delete(f"/api/admin/tables/{unused_id}").status_code == 204
    clear_test_data()


def test_business_hours_get_and_update_all_weekdays():
    clear_test_data()
    assert client.get("/api/admin/business-hours").json() == []

    hours = [
        {
            "day_of_week": day,
            "is_open": day != 2,
            "opening_time": "10:00" if day != 2 else None,
            "closing_time": "23:00" if day != 2 else None,
        }
        for day in range(7)
    ]
    response = client.put("/api/admin/business-hours", json=hours)
    assert response.status_code == 200
    assert len(response.json()) == 7
    assert response.json()[2]["is_open"] is False
    assert response.json()[2]["opening_time"] is None

    hours[0]["opening_time"] = "11:30"
    response = client.put("/api/admin/business-hours", json=hours)
    assert response.status_code == 200
    assert response.json()[0]["opening_time"] == "11:30:00"
    with TestingSessionLocal() as db:
        assert db.scalar(select(BusinessHour).where(BusinessHour.day_of_week == 0)).opening_time == time(11, 30)
    clear_test_data()


def create_accounting_data(*, with_active_session: bool = False):
    with TestingSessionLocal() as db:
        table = Table(table_name="会計テーブル")
        product = Product(name="ランチ", price=1200, is_sold_out=False)
        db.add_all([table, product])
        db.flush()
        completed = Session(
            table_id=table.id,
            status="completed",
            started_at=datetime(2026, 10, 1, 11, 0),
            completed_at=datetime(2026, 10, 1, 12, 30),
        )
        db.add(completed)
        db.flush()
        order = Order(
            session_id=completed.id,
            order_type="customer",
            ordered_at=datetime(2026, 10, 1, 11, 15),
        )
        db.add(order)
        db.flush()
        db.add(OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=3,
            canceled_quantity=1,
            served_quantity=2,
            unit_price=500,
        ))
        product.price = 1200
        if with_active_session:
            db.add(Session(table_id=table.id, status="active"))
        db.commit()
        return completed.id


def test_accounting_history_detail_uses_order_price_and_excludes_canceled_quantity():
    clear_test_data()
    session_id = create_accounting_data()

    response = client.get("/api/admin/accounting/history")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["table_name"] == "会計テーブル"
    assert response.json()[0]["total_amount"] == 1000

    response = client.get(f"/api/admin/accounting/history/{session_id}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["total_amount"] == 1000
    assert detail["orders"][0]["items"][0]["quantity"] == 3
    assert detail["orders"][0]["items"][0]["canceled_quantity"] == 1
    assert detail["orders"][0]["items"][0]["unit_price"] == 500
    assert detail["orders"][0]["items"][0]["amount"] == 1000
    clear_test_data()


def test_reopen_completed_session():
    clear_test_data()
    session_id = create_accounting_data()

    response = client.post(f"/api/admin/accounting/history/{session_id}/reopen")
    assert response.status_code == 200
    assert response.json() == {"session_id": session_id, "status": "active", "completed_at": None}
    with TestingSessionLocal() as db:
        session = db.get(Session, session_id)
        assert session.status == "active"
        assert session.completed_at is None
    clear_test_data()


def test_reopen_rejected_when_another_active_session_exists():
    clear_test_data()
    session_id = create_accounting_data(with_active_session=True)

    response = client.post(f"/api/admin/accounting/history/{session_id}/reopen")
    assert response.status_code == 409
    with TestingSessionLocal() as db:
        session = db.get(Session, session_id)
        assert session.status == "completed"
        assert session.completed_at is not None
    clear_test_data()
