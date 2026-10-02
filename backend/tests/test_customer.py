import os
from datetime import datetime, timedelta

os.environ["ENV_FILE"] = ".env.test"

from dotenv import load_dotenv

load_dotenv(".env.test", override=True)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
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
    assert response.json()["table_name"] == "テストテーブル"

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
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert response.json()["nickname"] == "たろう"

    # 同じSessionでは同じニックネームを登録できない
    response = client.post(
        f"/api/customer/sessions/{session_id}/participants",
        json={"nickname": "  たろう  "},
    )
    assert response.status_code == 409

    response = client.get("/api/customer/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["participant_id"] == participant_id
    assert response.json()["table_name"] == "テストテーブル"

    assert client.get("/api/customer/me", headers={"Authorization": "Bearer invalid"}).status_code == 401

    # --------------------------------
    # 3. カテゴリ取得
    # --------------------------------

    response = client.get(
        "/api/customer/categories", headers=headers
    )

    assert response.status_code == 200

    categories = response.json()

    assert len(categories) == 1
    assert categories[0]["name"] == "ドリンク"

    # --------------------------------
    # 4. 商品取得
    # --------------------------------

    response = client.get(
        "/api/customer/products", headers=headers
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
            "quantity": 2,
        },
        headers=headers,
    )

    assert response.status_code == 200

    assert response.json()["quantity"] == 2
    assert response.json()["total_selected_quantity"] == 2

    # --------------------------------
    # 6. 選択状態取得
    # --------------------------------

    response = client.get(
        f"/api/customer/sessions/{session_id}/selections", headers=headers
    )

    assert response.status_code == 200

    selections = response.json()

    assert len(selections) == 1
    assert selections[0]["nickname"] == "たろう"
    assert selections[0]["quantity"] == 2

    # 売り切れ商品はサーバー側でも選択できない
    with TestingSessionLocal() as db:
        product = db.get(Product, product_id)
        product.is_sold_out = True
        db.commit()
    assert client.put(
        f"/api/customer/selections/{product_id}", json={"quantity": 3}, headers=headers
    ).status_code == 409
    with TestingSessionLocal() as db:
        product = db.get(Product, product_id)
        product.is_sold_out = False
        db.commit()

    # 別の利用者は、たろうの選択を削除できない
    second = client.post(
        f"/api/customer/sessions/{session_id}/participants", json={"nickname": "じろう"}
    ).json()
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}
    assert client.delete(
        f"/api/customer/selections/{product_id}", headers=second_headers
    ).status_code == 404

    # 本人は選択を解除し、再び選択できる
    assert client.delete(
        f"/api/customer/selections/{product_id}", headers=headers
    ).status_code == 200
    assert client.put(
        f"/api/customer/selections/{product_id}", json={"quantity": 2}, headers=headers
    ).status_code == 200

    # Bodyを書き換えても他人として操作できない
    response = client.put(
        f"/api/customer/selections/{product_id}",
        json={"participant_id": 999999, "quantity": 3},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 3

    # --------------------------------
    # 7. 注文確定
    # --------------------------------

    response = client.post(
        "/api/customer/orders",
        json={
        },
        headers=headers,
    )

    assert response.status_code == 200

    assert response.json()["total_amount"] == 1500

    order_id = response.json()["order_id"]

    assert order_id is not None

    # --------------------------------
    # 8. 注文後、選択中が空になったか
    # --------------------------------

    response = client.get(
        f"/api/customer/sessions/{session_id}/selections", headers=headers
    )

    assert response.status_code == 200
    assert response.json() == []

    # --------------------------------
    # 9. 注文履歴
    # --------------------------------

    response = client.get(
        f"/api/customer/sessions/{session_id}/orders", headers=headers
    )

    assert response.status_code == 200

    orders = response.json()

    assert len(orders) == 1
    assert orders[0]["order_id"] == order_id

    assert orders[0]["items"][0]["product_name"] == "テストドリンク"
    assert orders[0]["items"][0]["quantity"] == 3
    assert orders[0]["items"][0]["unit_price"] == 500

    # 注文後の商品価格変更は過去注文へ影響しない。キャンセル分は会計から除く
    with TestingSessionLocal() as db:
        product = db.get(Product, product_id)
        product.price = 900
        item = db.scalar(select(OrderItem).where(OrderItem.order_id == order_id))
        item.canceled_quantity = 1
        item.served_quantity = 2
        db.commit()

    # --------------------------------
    # 10. 会計金額
    # --------------------------------

    response = client.get(
        f"/api/customer/sessions/{session_id}/bill", headers=headers
    )

    assert response.status_code == 200

    assert response.json()["total_amount"] == 1000

    response = client.get(f"/api/customer/sessions/{session_id}/orders", headers=headers)
    item = response.json()[0]["items"][0]
    assert item["unit_price"] == 500
    assert item["effective_quantity"] == 2
    assert item["is_served"] is True

    # 10分間操作されていない選択は自動解除される
    assert client.put(
        f"/api/customer/selections/{product_id}", json={"quantity": 1}, headers=headers
    ).status_code == 200
    with TestingSessionLocal() as db:
        selection = db.scalar(select(Selection).where(Selection.participant_id == participant_id))
        selection.last_selected_at = datetime.now() - timedelta(minutes=11)
        db.commit()
    response = client.get(f"/api/customer/sessions/{session_id}/selections", headers=headers)
    assert response.status_code == 200
    assert response.json() == []

    # Session終了後は復帰・操作できない
    with TestingSessionLocal() as db:
        session = db.get(Session, session_id)
        session.status = "completed"
        db.commit()
    assert client.get("/api/customer/me", headers=headers).status_code == 401
    assert client.put(
        f"/api/customer/selections/{product_id}",
        json={"quantity": 1},
        headers=headers,
    ).status_code == 401

    # --------------------------------
    # 後片付け
    # --------------------------------

    clear_test_data()


def test_product_image_upload_validation_and_customer_response(monkeypatch):
    clear_test_data()

    class FakeS3Client:
        def __init__(self):
            self.uploaded = []
            self.deleted = []

        def upload_fileobj(self, file_object, bucket, key, ExtraArgs):
            self.uploaded.append((bucket, key, file_object.read(), ExtraArgs))

        def generate_presigned_url(self, operation, Params, ExpiresIn):
            return f"https://signed.example/{Params['Key']}?expires={ExpiresIn}"

        def delete_object(self, Bucket, Key):
            self.deleted.append((Bucket, Key))

    fake_s3 = FakeS3Client()
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    monkeypatch.setenv("AWS_S3_BUCKET_NAME", "test-product-images")
    monkeypatch.setattr("app.services.product_images._client", lambda: fake_s3)

    with TestingSessionLocal() as db:
        table = Table(table_name="画像テストテーブル")
        category = Category(name="画像カテゴリ", display_order=1)
        db.add_all([table, category])
        db.flush()
        session = Session(table_id=table.id, status="active")
        db.add(session)
        db.commit()
        db.refresh(category)
        db.refresh(session)
        category_id = category.id
        session_id = session.id

    product_data = {
        "name": "画像商品",
        "price": 300,
        "description": None,
        "image_url": None,
        "is_sold_out": False,
        "display_order": 1,
        "category_ids": [category_id],
    }
    response = client.post("/api/admin/products", json=product_data)
    assert response.status_code == 201
    assert response.json()["image_url"] is None
    product_id = response.json()["id"]

    response = client.post(
        f"/api/admin/products/{product_id}/image",
        files={"image": ("menu.png", b"\x89PNG\r\n\x1a\nimage-data", "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["image_url"].startswith("https://signed.example/products/")
    assert len(fake_s3.uploaded) == 1
    first_key = fake_s3.uploaded[0][1]
    assert first_key.startswith("products/")
    assert first_key.endswith(".png")

    participant = client.post(
        f"/api/customer/sessions/{session_id}/participants",
        json={"nickname": "画像確認"},
    ).json()
    headers = {"Authorization": f"Bearer {participant['access_token']}"}
    customer_product = client.get("/api/customer/products", headers=headers).json()[0]
    assert customer_product["image_url"].startswith("https://signed.example/products/")

    response = client.post(
        f"/api/admin/products/{product_id}/image",
        files={"image": ("menu.webp", b"RIFF\x04\x00\x00\x00WEBPdata", "image/webp")},
    )
    assert response.status_code == 200
    assert fake_s3.deleted == [("test-product-images", first_key)]

    response = client.post(
        f"/api/admin/products/{product_id}/image",
        files={"image": ("memo.txt", b"not-an-image", "text/plain")},
    )
    assert response.status_code == 422

    response = client.post(
        f"/api/admin/products/{product_id}/image",
        files={"image": ("large.png", b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024), "image/png")},
    )
    assert response.status_code == 413

    clear_test_data()


def test_admin_product_management_and_customer_integration():
    clear_test_data()
    with TestingSessionLocal() as db:
        table = Table(table_name="管理テストテーブル")
        db.add(table)
        db.flush()
        session = Session(table_id=table.id, status="active")
        categories = [
            Category(name="フード", display_order=1),
            Category(name="おすすめ", display_order=2),
        ]
        db.add(session)
        db.add_all(categories)
        db.commit()
        db.refresh(session)
        for category in categories:
            db.refresh(category)
        session_id = session.id
        category_ids = [category.id for category in categories]

    assert client.get("/api/admin/products").json() == []

    base_data = {
        "name": " 管理画面の商品 ",
        "price": 500,
        "description": "登録テスト",
        "image_url": None,
        "is_sold_out": False,
        "display_order": 3,
        "category_ids": category_ids,
    }
    assert client.post("/api/admin/products", json={**base_data, "name": "  "}).status_code == 422
    assert client.post("/api/admin/products", json={**base_data, "price": -1}).status_code == 422
    assert client.post("/api/admin/products", json={**base_data, "price": "500"}).status_code == 422
    assert client.post("/api/admin/products", json={**base_data, "category_ids": []}).status_code == 422
    assert client.post("/api/admin/products", json={**base_data, "category_ids": [999999]}).status_code == 422

    response = client.post("/api/admin/products", json=base_data)
    assert response.status_code == 201
    product = response.json()
    product_id = product["id"]
    assert product["name"] == "管理画面の商品"
    assert product["category_ids"] == category_ids
    assert len(product["category_names"]) == 2

    assert client.get(f"/api/admin/products/{product_id}").status_code == 200
    assert len(client.get("/api/admin/products").json()) == 1
    assert client.get("/api/admin/products/999999").status_code == 404

    participant_response = client.post(
        f"/api/customer/sessions/{session_id}/participants",
        json={"nickname": "admin連携確認"},
    )
    token = participant_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    customer_products = client.get("/api/customer/products", headers=headers).json()
    assert customer_products[0]["name"] == "管理画面の商品"
    assert customer_products[0]["category_ids"] == category_ids

    assert client.put(
        f"/api/customer/selections/{product_id}", json={"quantity": 2}, headers=headers
    ).status_code == 200
    order_response = client.post("/api/customer/orders", json={}, headers=headers)
    assert order_response.status_code == 200

    updated_data = {
        **base_data,
        "name": "更新した商品",
        "price": 700,
        "description": "更新済み",
        "is_sold_out": True,
        "display_order": 1,
        "category_ids": [category_ids[1]],
    }
    response = client.put(f"/api/admin/products/{product_id}", json=updated_data)
    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "更新した商品"
    assert updated["is_sold_out"] is True
    assert updated["category_ids"] == [category_ids[1]]

    customer_product = client.get("/api/customer/products", headers=headers).json()[0]
    assert customer_product["name"] == "更新した商品"
    assert customer_product["price"] == 700
    assert customer_product["is_sold_out"] is True
    orders = client.get(f"/api/customer/sessions/{session_id}/orders", headers=headers).json()
    assert orders[0]["items"][0]["unit_price"] == 500

    # 注文履歴がある商品は安全のため削除しない
    response = client.delete(f"/api/admin/products/{product_id}")
    assert response.status_code == 409

    unused_response = client.post(
        "/api/admin/products",
        json={**base_data, "name": "未使用商品", "category_ids": [category_ids[0]]},
    )
    unused_id = unused_response.json()["id"]
    assert client.delete(f"/api/admin/products/{unused_id}").status_code == 204
    assert client.get(f"/api/admin/products/{unused_id}").status_code == 404

    clear_test_data()
