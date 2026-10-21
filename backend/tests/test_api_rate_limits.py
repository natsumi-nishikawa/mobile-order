import os
from concurrent.futures import ThreadPoolExecutor

os.environ["ENV_FILE"] = ".env.test"

from dotenv import load_dotenv

load_dotenv(".env.test", override=True)

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
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
from app.rate_limit import SlidingWindowRateLimiter, api_rate_limiter
from app.store_auth import StoreUser, require_staff
from tests.demo_auth_helper import DEMO_ORIGIN, authenticate_demo


TEST_DATABASE_URL = os.environ["DATABASE_URL"]
assert TEST_DATABASE_URL.endswith("/mobile_order_test")
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    with TestingSessionLocal() as db:
        yield db


app.dependency_overrides[get_db] = override_get_db
staff_user = StoreUser("rate-staff", "rate-staff", frozenset({"staff"}))
app.dependency_overrides[require_staff] = lambda: staff_user


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


def create_active_session():
    with TestingSessionLocal() as db:
        table = Table(table_name="rate-table")
        product = Product(name="rate-product", price=100, is_sold_out=False)
        db.add_all([table, product])
        db.flush()
        session = Session(table_id=table.id, status="active")
        db.add(session)
        db.commit()
        return session.id, product.id


def join(client: TestClient, session_id: int, nickname: str):
    response = client.post(
        f"/api/customer/sessions/{session_id}/participants",
        json={"nickname": nickname},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_customer_join_allows_10_and_rejects_11_with_retry_after():
    clear_data()
    session_id, _ = create_active_session()
    with TestClient(app) as client:
        authenticate_demo(client)
        for index in range(10):
            assert join(client, session_id, f"join-{index}")
        response = client.post(
            f"/api/customer/sessions/{session_id}/participants",
            json={"nickname": "join-11"},
        )
        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) >= 1
    clear_data()


def test_customer_order_allows_5_attempts_and_rejects_6():
    clear_data()
    session_id, product_id = create_active_session()
    with TestClient(app) as client:
        authenticate_demo(client)
        headers = join(client, session_id, "order-limit")
        for _ in range(5):
            assert client.put(
                f"/api/customer/selections/{product_id}",
                json={"quantity": 1},
                headers=headers,
            ).status_code == 200
            assert client.post("/api/customer/orders", json={}, headers=headers).status_code == 200
        response = client.post("/api/customer/orders", json={}, headers=headers)
        assert response.status_code == 429
        assert "Retry-After" in response.headers
    clear_data()


def test_staff_order_allows_10_and_rejects_11():
    clear_data()
    session_id, product_id = create_active_session()
    with TestClient(app) as client:
        authenticate_demo(client)
        payload = {"session_id": session_id, "items": [{"product_id": product_id, "quantity": 1}]}
        for _ in range(10):
            assert client.post("/api/staff/orders", json=payload).status_code == 201
        response = client.post("/api/staff/orders", json=payload)
        assert response.status_code == 429
        assert "Retry-After" in response.headers
    clear_data()


def test_customer_selection_allows_60_and_rejects_61():
    clear_data()
    session_id, product_id = create_active_session()
    with TestClient(app) as client:
        authenticate_demo(client)
        headers = join(client, session_id, "selection-limit")
        for _ in range(60):
            assert client.put(
                f"/api/customer/selections/{product_id}",
                json={"quantity": 1},
                headers=headers,
            ).status_code == 200
        response = client.put(
            f"/api/customer/selections/{product_id}",
            json={"quantity": 1},
            headers=headers,
        )
        assert response.status_code == 429
        assert "Retry-After" in response.headers
    clear_data()


def test_window_expiry_and_different_keys_are_independent():
    now = [100.0]
    limiter = SlidingWindowRateLimiter(clock=lambda: now[0])
    limiter.check_and_record("customer:1", 1, 60, 100)
    try:
        limiter.check_and_record("customer:1", 1, 60, 100)
        raise AssertionError("same key should be limited")
    except HTTPException as exc:
        assert exc.status_code == 429
        assert exc.headers and exc.headers["Retry-After"] == "61"
    limiter.check_and_record("customer:2", 1, 60, 100)
    now[0] += 61
    limiter.check_and_record("customer:1", 1, 60, 100)


def test_concurrent_requests_do_not_exceed_limit():
    limiter = SlidingWindowRateLimiter(clock=lambda: 100.0)

    def attempt(_index: int) -> int:
        try:
            limiter.check_and_record("parallel", 10, 60, 100)
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=20) as pool:
        statuses = list(pool.map(attempt, range(20)))
    assert statuses.count(200) == 10
    assert statuses.count(429) == 10


def test_authentication_and_csrf_are_still_required():
    clear_data()
    session_id, product_id = create_active_session()
    with TestClient(app) as unauthenticated:
        assert unauthenticated.post(
            f"/api/customer/sessions/{session_id}/participants",
            json={"nickname": "unauthenticated"},
            headers={"Origin": DEMO_ORIGIN},
        ).status_code == 401

    with TestClient(app) as client:
        csrf = authenticate_demo(client)
        headers = join(client, session_id, "csrf-user")
        client.headers.pop("X-CSRF-Token")
        response = client.put(
            f"/api/customer/selections/{product_id}",
            json={"quantity": 1},
            headers=headers,
        )
        assert response.status_code == 403
        client.headers.update({"X-CSRF-Token": csrf})
        assert client.put(
            f"/api/customer/selections/{product_id}",
            json={"quantity": 1},
            headers=headers,
        ).status_code == 200
    clear_data()


def test_limiter_key_storage_is_bounded():
    limiter = SlidingWindowRateLimiter(clock=lambda: 100.0)
    for index in range(20):
        limiter.check_and_record(f"key-{index}", 1, 60, 5)
    assert len(limiter._attempts) == 5
