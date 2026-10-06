import os

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
from app.store_auth import StoreUser, require_staff


TEST_DATABASE_URL = os.getenv("DATABASE_URL")
assert TEST_DATABASE_URL is not None and TEST_DATABASE_URL.endswith("/mobile_order_test")
test_engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    with TestingSessionLocal() as db:
        yield db


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[require_staff] = lambda: StoreUser("test-staff", "staff", frozenset({"staff"}))
client = TestClient(app)


def clear_test_data():
    with TestingSessionLocal() as db:
        for model in (OrderItem, Order, Selection, ProductCategory, Participant, Product, Category, Session, BusinessHour, Table):
            db.execute(delete(model))
        db.commit()


def test_staff_full_flow_and_customer_consistency():
    clear_test_data()
    with TestingSessionLocal() as db:
        table = Table(table_name="S-1")
        product = Product(name="スタッフ商品", price=600, is_sold_out=False)
        db.add_all([table, product])
        db.commit()
        db.refresh(table)
        db.refresh(product)
        table_id, product_id = table.id, product.id

    tables = client.get("/api/staff/tables").json()
    assert tables[0]["is_in_use"] is False

    response = client.post(f"/api/staff/tables/{table_id}/sessions")
    assert response.status_code == 201
    session_id = response.json()["id"]
    assert client.post(f"/api/staff/tables/{table_id}/sessions").status_code == 409

    # 開始したSessionはCustomerのQR導線から利用できる
    assert client.get(f"/api/customer/tables/{table_id}/session").json()["session_id"] == session_id

    response = client.post("/api/staff/orders", json={
        "session_id": session_id,
        "items": [{"product_id": product_id, "quantity": 3}],
    })
    assert response.status_code == 201
    assert response.json()["order_type"] == "staff"
    assert response.json()["items"][0]["unit_price"] == 600
    item_id = response.json()["items"][0]["id"]

    assert client.patch(f"/api/staff/order-items/{item_id}/served", json={"quantity": 3}).status_code == 200
    assert client.patch(f"/api/staff/order-items/{item_id}/served", json={"quantity": 0}).json()["served_quantity"] == 0
    assert client.patch(f"/api/staff/order-items/{item_id}/served", json={"quantity": 4}).status_code == 422

    response = client.patch(f"/api/staff/order-items/{item_id}/canceled", json={"quantity": 1})
    assert response.status_code == 200
    assert response.json()["effective_quantity"] == 2
    assert client.patch(f"/api/staff/order-items/{item_id}/canceled", json={"quantity": 4}).status_code == 422

    participant = client.post(
        f"/api/customer/sessions/{session_id}/participants", json={"nickname": "会計確認"}
    ).json()
    headers = {"Authorization": f"Bearer {participant['access_token']}"}
    assert client.get(f"/api/customer/sessions/{session_id}/bill", headers=headers).json()["total_amount"] == 1200

    # 全キャンセルでも注文履歴は残り、金額だけが0になる
    assert client.patch(f"/api/staff/order-items/{item_id}/canceled", json={"quantity": 3}).status_code == 200
    assert client.get(f"/api/customer/sessions/{session_id}/bill", headers=headers).json()["total_amount"] == 0
    assert len(client.get(f"/api/customer/sessions/{session_id}/orders", headers=headers).json()) == 1

    response = client.post(f"/api/staff/sessions/{session_id}/complete")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["completed_at"] is not None
    assert client.get("/api/staff/tables").json()[0]["is_in_use"] is False
    assert client.get("/api/customer/me", headers=headers).status_code == 401

    next_response = client.post(f"/api/staff/tables/{table_id}/sessions")
    assert next_response.status_code == 201
    assert next_response.json()["id"] != session_id
    with TestingSessionLocal() as db:
        assert db.scalar(select(OrderItem).where(OrderItem.id == item_id)) is not None
    clear_test_data()


def test_staff_order_rejects_inactive_session_and_sold_out_product():
    clear_test_data()
    with TestingSessionLocal() as db:
        table = Table(table_name="S-2")
        product = Product(name="売り切れ", price=500, is_sold_out=True)
        db.add_all([table, product])
        db.flush()
        session = Session(table_id=table.id, status="active")
        db.add(session)
        db.commit()
        session_id, product_id = session.id, product.id
    payload = {"session_id": session_id, "items": [{"product_id": product_id, "quantity": 1}]}
    assert client.post("/api/staff/orders", json=payload).status_code == 409
    assert client.post(f"/api/staff/sessions/{session_id}/complete").status_code == 200
    assert client.post("/api/staff/orders", json=payload).status_code == 404
    clear_test_data()


def test_staff_catalog_categories_and_cross_category_proxy_order():
    clear_test_data()
    with TestingSessionLocal() as db:
        table = Table(table_name="カテゴリテーブル")
        food = Category(name="フード", display_order=2)
        recommended = Category(name="おすすめ", display_order=1)
        shared = Product(name="唐揚げ", price=700, is_sold_out=False, display_order=1)
        drink = Product(name="焼酎", price=900, is_sold_out=False, display_order=2)
        sold_out = Product(name="売り切れ商品", price=300, is_sold_out=True, display_order=3)
        db.add_all([table, food, recommended, shared, drink, sold_out])
        db.flush()
        db.add_all([
            ProductCategory(product_id=shared.id, category_id=recommended.id),
            ProductCategory(product_id=shared.id, category_id=food.id),
            ProductCategory(product_id=drink.id, category_id=food.id),
            ProductCategory(product_id=sold_out.id, category_id=food.id),
        ])
        session = Session(table_id=table.id, status="active")
        db.add(session)
        db.commit()
        session_id = session.id
        shared_id, drink_id, sold_out_id = shared.id, drink.id, sold_out.id
        recommended_id, food_id = recommended.id, food.id

    categories = client.get("/api/staff/categories")
    assert categories.status_code == 200
    assert [item["name"] for item in categories.json()] == ["おすすめ", "フード"]

    response = client.get("/api/staff/products")
    assert response.status_code == 200
    products = {item["id"]: item for item in response.json()}
    assert products[shared_id]["category_ids"] == [recommended_id, food_id]
    assert products[drink_id]["category_ids"] == [food_id]
    assert products[sold_out_id]["is_sold_out"] is True

    # 別カテゴリで選んだ商品を1回の既存代理注文APIへまとめて送信する
    response = client.post("/api/staff/orders", json={
        "session_id": session_id,
        "items": [
            {"product_id": shared_id, "quantity": 2},
            {"product_id": drink_id, "quantity": 1},
        ],
    })
    assert response.status_code == 201
    items = {item["product_id"]: item for item in response.json()["items"]}
    assert items[shared_id]["quantity"] == 2
    assert items[shared_id]["unit_price"] == 700
    assert items[drink_id]["quantity"] == 1
    assert items[drink_id]["unit_price"] == 900
    with TestingSessionLocal() as db:
        saved = db.scalars(select(OrderItem).join(Order).where(Order.session_id == session_id)).all()
        assert sorted((item.product_id, item.quantity, item.unit_price) for item in saved) == [
            (shared_id, 2, 700),
            (drink_id, 1, 900),
        ]
    clear_test_data()


def test_staff_accounting_normal_multiple_partial_and_full_cancellation():
    clear_test_data()
    with TestingSessionLocal() as db:
        table = Table(table_name="会計確認テーブル")
        first = Product(name="通常商品", price=9999, is_sold_out=False)
        second = Product(name="キャンセル商品", price=8888, is_sold_out=False)
        db.add_all([table, first, second])
        db.flush()
        session = Session(table_id=table.id, status="active")
        db.add(session)
        db.flush()
        order = Order(session_id=session.id, order_type="customer")
        db.add(order)
        db.flush()
        db.add_all([
            # 現在の商品価格ではなく、注文時単価を使う通常注文
            OrderItem(order_id=order.id, product_id=first.id, quantity=2, canceled_quantity=0, served_quantity=0, unit_price=500),
            # 一部キャンセル
            OrderItem(order_id=order.id, product_id=second.id, quantity=3, canceled_quantity=1, served_quantity=0, unit_price=700),
            # 全キャンセル（明細には残すが合計から除外）
            OrderItem(order_id=order.id, product_id=second.id, quantity=4, canceled_quantity=4, served_quantity=0, unit_price=700),
        ])
        db.commit()
        session_id = session.id

    response = client.get(f"/api/staff/sessions/{session_id}/accounting")
    assert response.status_code == 200
    detail = response.json()
    assert detail["table_name"] == "会計確認テーブル"
    assert len(detail["items"]) == 3
    assert detail["items"][0] == {
        "order_item_id": detail["items"][0]["order_item_id"],
        "product_name": "通常商品",
        "unit_price": 500,
        "quantity": 2,
        "canceled_quantity": 0,
        "billable_quantity": 2,
        "subtotal": 1000,
    }
    assert detail["items"][1]["billable_quantity"] == 2
    assert detail["items"][1]["subtotal"] == 1400
    assert detail["items"][2]["billable_quantity"] == 0
    assert detail["items"][2]["subtotal"] == 0
    assert detail["total_item_count"] == 4
    assert detail["total_amount"] == 2400

    participant = client.post(
        f"/api/customer/sessions/{session_id}/participants", json={"nickname": "金額照合"}
    ).json()
    headers = {"Authorization": f"Bearer {participant['access_token']}"}
    assert client.get(f"/api/customer/sessions/{session_id}/bill", headers=headers).json()["total_amount"] == detail["total_amount"]

    complete = client.post(f"/api/staff/sessions/{session_id}/complete")
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"
    assert client.get(f"/api/staff/sessions/{session_id}/accounting").status_code == 404
    with TestingSessionLocal() as db:
        assert len(db.scalars(select(OrderItem).join(Order).where(Order.session_id == session_id)).all()) == 3
    clear_test_data()
