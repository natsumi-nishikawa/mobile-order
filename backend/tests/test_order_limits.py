import os
from concurrent.futures import ThreadPoolExecutor

os.environ["ENV_FILE"] = ".env.test"

from dotenv import load_dotenv

load_dotenv(".env.test", override=True)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app
from app.models.category import Category
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.participant import Participant
from app.models.product import Product
from app.models.product_category import ProductCategory
from app.models.selection import Selection
from app.models.session import Session
from app.models.table import Table
from app.rate_limit import api_rate_limiter
from app.store_auth import StoreUser, require_admin, require_staff
from tests.demo_auth_helper import authenticate_demo


TEST_DATABASE_URL = os.environ["DATABASE_URL"]
assert TEST_DATABASE_URL.endswith("/mobile_order_test")
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    with TestingSessionLocal() as db:
        yield db


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[require_admin] = lambda: StoreUser(
    "limit-admin", "admin", frozenset({"admin"})
)
app.dependency_overrides[require_staff] = lambda: StoreUser(
    "limit-staff", "staff", frozenset({"staff"})
)
client = TestClient(app)
authenticate_demo(client)


def clear_data():
    with TestingSessionLocal() as db:
        for model in (
            OrderItem,
            Order,
            Selection,
            ProductCategory,
            Participant,
            Product,
            Category,
            Session,
            Table,
        ):
            db.execute(delete(model))
        db.commit()


def create_session_and_products(count: int = 1):
    with TestingSessionLocal() as db:
        table = Table(table_name="limit-table")
        db.add(table)
        db.flush()
        session = Session(table_id=table.id, status="active")
        products = [
            Product(
                name=f"product-{index}",
                price=100,
                description=None,
                image_url=None,
                is_sold_out=False,
                display_order=index,
            )
            for index in range(count)
        ]
        db.add(session)
        db.add_all(products)
        db.commit()
        return session.id, [product.id for product in products]


def join_customer(session_id: int, nickname: str, test_client: TestClient = client):
    response = test_client.post(
        f"/api/customer/sessions/{session_id}/participants",
        json={"nickname": nickname},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def seed_order_quantity(session_id: int, product_id: int, quantity: int, *, canceled: bool = False):
    with TestingSessionLocal() as db:
        order = Order(session_id=session_id, participant_id=None, order_type="staff")
        db.add(order)
        db.flush()
        remaining = quantity
        while remaining:
            item_quantity = min(50, remaining)
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product_id,
                    quantity=item_quantity,
                    unit_price=100,
                    canceled_quantity=item_quantity if canceled else 0,
                    served_quantity=0,
                )
            )
            remaining -= item_quantity
        db.commit()


def test_customer_item_quantity_20_succeeds_and_21_is_rejected():
    clear_data()
    session_id, [product_id] = create_session_and_products()
    headers = join_customer(session_id, "quantity-boundary")
    assert client.put(
        f"/api/customer/selections/{product_id}",
        json={"quantity": 20},
        headers=headers,
    ).status_code == 200
    assert client.put(
        f"/api/customer/selections/{product_id}",
        json={"quantity": 21},
        headers=headers,
    ).status_code == 422
    clear_data()


def test_customer_order_total_100_succeeds_and_101_is_atomic_rejection():
    clear_data()
    session_id, product_ids = create_session_and_products(11)
    headers = join_customer(session_id, "customer-total")
    for product_id in product_ids[:5]:
        assert client.put(
            f"/api/customer/selections/{product_id}", json={"quantity": 20}, headers=headers
        ).status_code == 200
    assert client.post("/api/customer/orders", json={}, headers=headers).status_code == 200

    for product_id in product_ids[5:10]:
        client.put(
            f"/api/customer/selections/{product_id}", json={"quantity": 20}, headers=headers
        )
    client.put(
        f"/api/customer/selections/{product_ids[10]}", json={"quantity": 1}, headers=headers
    )
    rejected = client.post("/api/customer/orders", json={}, headers=headers)
    assert rejected.status_code == 422
    with TestingSessionLocal() as db:
        assert db.scalar(select(func.count(Order.id)).where(Order.session_id == session_id)) == 1
    clear_data()


def test_customer_product_types_30_succeeds_and_31_is_rejected():
    clear_data()
    session_id, product_ids = create_session_and_products(61)
    headers = join_customer(session_id, "type-boundary")
    for product_id in product_ids[:30]:
        client.put(f"/api/customer/selections/{product_id}", json={"quantity": 1}, headers=headers)
    assert client.post("/api/customer/orders", json={}, headers=headers).status_code == 200
    api_rate_limiter.reset()
    for product_id in product_ids[30:]:
        client.put(f"/api/customer/selections/{product_id}", json={"quantity": 1}, headers=headers)
    assert client.post("/api/customer/orders", json={}, headers=headers).status_code == 422
    clear_data()


def test_staff_quantity_and_order_total_boundaries():
    clear_data()
    session_id, product_ids = create_session_and_products(5)
    assert client.post(
        "/api/staff/orders",
        json={"session_id": session_id, "items": [{"product_id": product_ids[0], "quantity": 50}]},
    ).status_code == 201
    assert client.post(
        "/api/staff/orders",
        json={"session_id": session_id, "items": [{"product_id": product_ids[0], "quantity": 51}]},
    ).status_code == 422
    assert client.post(
        "/api/staff/orders",
        json={"session_id": session_id, "items": [
            {"product_id": product_id, "quantity": 50} for product_id in product_ids[:4]
        ]},
    ).status_code == 201
    assert client.post(
        "/api/staff/orders",
        json={"session_id": session_id, "items": [
            *[{"product_id": product_id, "quantity": 50} for product_id in product_ids[:4]],
            {"product_id": product_ids[4], "quantity": 1},
        ]},
    ).status_code == 422
    clear_data()


def test_staff_product_types_30_succeeds_and_31_is_rejected():
    clear_data()
    session_id, product_ids = create_session_and_products(31)
    assert client.post(
        "/api/staff/orders",
        json={
            "session_id": session_id,
            "items": [
                {"product_id": product_id, "quantity": 1}
                for product_id in product_ids[:30]
            ],
        },
    ).status_code == 201
    assert client.post(
        "/api/staff/orders",
        json={
            "session_id": session_id,
            "items": [
                {"product_id": product_id, "quantity": 1}
                for product_id in product_ids
            ],
        },
    ).status_code == 422
    clear_data()


def test_session_quantity_500_succeeds_501_fails_and_cancellation_does_not_restore_capacity():
    clear_data()
    session_id, [product_id] = create_session_and_products()
    seed_order_quantity(session_id, product_id, 499)
    assert client.post(
        "/api/staff/orders",
        json={"session_id": session_id, "items": [{"product_id": product_id, "quantity": 1}]},
    ).status_code == 201
    assert client.post(
        "/api/staff/orders",
        json={"session_id": session_id, "items": [{"product_id": product_id, "quantity": 1}]},
    ).status_code == 409

    clear_data()
    session_id, [product_id] = create_session_and_products()
    seed_order_quantity(session_id, product_id, 500, canceled=True)
    assert client.post(
        "/api/staff/orders",
        json={"session_id": session_id, "items": [{"product_id": product_id, "quantity": 1}]},
    ).status_code == 409
    clear_data()


def test_session_order_count_200_succeeds_and_201_fails():
    clear_data()
    session_id, [product_id] = create_session_and_products()
    with TestingSessionLocal() as db:
        db.add_all([
            Order(session_id=session_id, participant_id=None, order_type="staff")
            for _ in range(199)
        ])
        db.commit()
    payload = {"session_id": session_id, "items": [{"product_id": product_id, "quantity": 1}]}
    assert client.post("/api/staff/orders", json=payload).status_code == 201
    assert client.post("/api/staff/orders", json=payload).status_code == 409
    clear_data()


def test_session_participants_50_succeeds_and_51_fails():
    clear_data()
    session_id, _ = create_session_and_products()
    with TestingSessionLocal() as db:
        db.add_all([
            Participant(session_id=session_id, nickname=f"participant-{index}")
            for index in range(49)
        ])
        db.commit()
    assert client.post(
        f"/api/customer/sessions/{session_id}/participants",
        json={"nickname": "participant-50"},
    ).status_code == 200
    assert client.post(
        f"/api/customer/sessions/{session_id}/participants",
        json={"nickname": "participant-51"},
    ).status_code == 409
    clear_data()


def test_product_description_and_category_count_boundaries():
    clear_data()
    with TestingSessionLocal() as db:
        categories = [Category(name=f"category-{index}", display_order=index) for index in range(21)]
        db.add_all(categories)
        db.commit()
        category_ids = [category.id for category in categories]
    base = {
        "name": "boundary-product",
        "price": 1_000_000,
        "description": "x" * 2_000,
        "image_url": None,
        "is_sold_out": False,
        "display_order": 1_000_000,
        "category_ids": category_ids[:20],
    }
    assert client.post("/api/admin/products", json=base).status_code == 201
    assert client.post(
        "/api/admin/products", json={**base, "name": "description-too-long", "description": "x" * 2_001}
    ).status_code == 422
    assert client.post(
        "/api/admin/products", json={**base, "name": "categories-too-many", "category_ids": category_ids}
    ).status_code == 422
    clear_data()


def test_concurrent_orders_cannot_exceed_session_quantity_limit():
    clear_data()
    session_id, product_ids = create_session_and_products(3)
    seed_order_quantity(session_id, product_ids[0], 499)

    clients = [TestClient(app), TestClient(app)]
    headers = []
    for index, test_client in enumerate(clients):
        authenticate_demo(test_client)
        customer_headers = join_customer(session_id, f"concurrent-{index}", test_client)
        headers.append(customer_headers)
        assert test_client.put(
            f"/api/customer/selections/{product_ids[index + 1]}",
            json={"quantity": 1},
            headers=customer_headers,
        ).status_code == 200

    def submit(index: int):
        return clients[index].post("/api/customer/orders", json={}, headers=headers[index]).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(submit, range(2)))
    assert statuses == [200, 409]
    with TestingSessionLocal() as db:
        total = db.scalar(
            select(func.sum(OrderItem.quantity))
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.session_id == session_id)
        )
        assert total == 500
    clear_data()
