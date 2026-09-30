import os

os.environ["ENV_FILE"] = ".env.test"

from dotenv import load_dotenv

load_dotenv(".env.test", override=True)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

from app.models.table import Table
from app.models.session import Session
from app.models.participant import Participant
from app.models.category import Category
from app.models.product import Product
from app.models.product_category import ProductCategory
from app.models.selection import Selection
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.business_hour import BusinessHour


TEST_DATABASE_URL = os.getenv("DATABASE_URL")

assert TEST_DATABASE_URL is not None
assert TEST_DATABASE_URL.endswith(
    "/mobile_order_test"
), "テストDB以外が指定されています"


test_engine = create_engine(TEST_DATABASE_URL)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


def override_get_db():
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

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


def create_test_data():
    with TestingSessionLocal() as db:
        table = Table(
            table_name="テストテーブル",
        )

        db.add(table)
        db.flush()

        session = Session(
            table_id=table.id,
            status="active",
        )

        db.add(session)

        category = Category(
            name="ドリンク",
            display_order=1,
        )

        db.add(category)
        db.flush()

        product = Product(
            name="テストドリンク",
            price=500,
            description="テスト用商品",
            image_url=None,
            is_sold_out=False,
            display_order=1,
        )

        db.add(product)
        db.flush()

        product_category = ProductCategory(
            product_id=product.id,
            category_id=category.id,
        )

        db.add(product_category)

        db.commit()

        return {
            "table_id": table.id,
            "session_id": session.id,
            "category_id": category.id,
            "product_id": product.id,
        }


def test_customer_flow():
    # --------------------------------
    # テストデータ準備
    # --------------------------------

    clear_test_data()

    test_data = create_test_data()

    table_id = test_data["table_id"]
    session_id = test_data["session_id"]
    product_id = test_data["product_id"]

    # --------------------------------
    # 1. 利用中Session取得
    # --------------------------------

    response = client.get(
        f"/api/customer/tables/{table_id}/session"
    )

    assert response.status_code == 200

    assert response.json()["session_id"] == session_id
    assert response.json()["status"] == "active"

    # --------------------------------
    # 2. ニックネーム登録
    # --------------------------------

    response = client.post(
        f"/api/customer/sessions/{session_id}/participants",
        json={
            "nickname": "たろう",
        },
    )

    assert response.status_code == 200

    participant_id = response.json()["participant_id"]

    assert response.json()["nickname"] == "たろう"

    # --------------------------------
    # 3. カテゴリ取得
    # --------------------------------

    response = client.get(
        "/api/customer/categories"
    )

    assert response.status_code == 200

    categories = response.json()

    assert len(categories) == 1
    assert categories[0]["name"] == "ドリンク"

    # --------------------------------
    # 4. 商品取得
    # --------------------------------

    response = client.get(
        "/api/customer/products"
    )

    assert response.status_code == 200

    products = response.json()

    assert len(products) == 1
    assert products[0]["name"] == "テストドリンク"
    assert products[0]["price"] == 500

    # --------------------------------
    # 5. 商品を2個選択
    # --------------------------------

    response = client.put(
        f"/api/customer/selections/{product_id}",
        json={
            "participant_id": participant_id,
            "quantity": 2,
        },
    )

    assert response.status_code == 200

    assert response.json()["quantity"] == 2
    assert response.json()["total_selected_quantity"] == 2

    # --------------------------------
    # 6. 選択状態取得
    # --------------------------------

    response = client.get(
        f"/api/customer/sessions/{session_id}/selections"
    )

    assert response.status_code == 200

    selections = response.json()

    assert len(selections) == 1
    assert selections[0]["nickname"] == "たろう"
    assert selections[0]["quantity"] == 2

    # --------------------------------
    # 7. 注文確定
    # --------------------------------

    response = client.post(
        "/api/customer/orders",
        json={
            "participant_id": participant_id,
        },
    )

    assert response.status_code == 200

    assert response.json()["total_amount"] == 1000

    order_id = response.json()["order_id"]

    assert order_id is not None

    # --------------------------------
    # 8. 注文後、選択中が空になったか
    # --------------------------------

    response = client.get(
        f"/api/customer/sessions/{session_id}/selections"
    )

    assert response.status_code == 200
    assert response.json() == []

    # --------------------------------
    # 9. 注文履歴
    # --------------------------------

    response = client.get(
        f"/api/customer/sessions/{session_id}/orders"
    )

    assert response.status_code == 200

    orders = response.json()

    assert len(orders) == 1
    assert orders[0]["order_id"] == order_id

    assert orders[0]["items"][0]["product_name"] == "テストドリンク"
    assert orders[0]["items"][0]["quantity"] == 2
    assert orders[0]["items"][0]["unit_price"] == 500

    # --------------------------------
    # 10. 会計金額
    # --------------------------------

    response = client.get(
        f"/api/customer/sessions/{session_id}/bill"
    )

    assert response.status_code == 200

    assert response.json()["total_amount"] == 1000

    # --------------------------------
    # 後片付け
    # --------------------------------

    clear_test_data()