import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.request_size_limit import (
    IMAGE_UPLOAD_REQUEST_LIMIT,
    JSON_REQUEST_LIMIT,
    RequestSizeLimitMiddleware,
)
from tests.demo_auth_helper import authenticate_demo


def run_asgi_request(*, path: str, method: str, chunks: list[bytes], headers=None):
    received_body = bytearray()
    sent = []
    incoming = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]

    async def downstream(scope, receive, send):
        while True:
            message = await receive()
            received_body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return incoming.pop(0)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }
    asyncio.run(RequestSizeLimitMiddleware(downstream)(scope, receive, send))
    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    return status, bytes(received_body), sent


def test_json_body_at_64_kib_is_forwarded_unchanged_without_content_length():
    body = b"x" * JSON_REQUEST_LIMIT
    status, forwarded, _ = run_asgi_request(
        path="/api/test",
        method="POST",
        chunks=[body[:1000], body[1000:]],
    )
    assert status == 204
    assert forwarded == body


def test_json_body_over_64_kib_without_content_length_is_rejected():
    status, forwarded, _ = run_asgi_request(
        path="/api/test",
        method="POST",
        chunks=[b"x" * JSON_REQUEST_LIMIT, b"x"],
    )
    assert status == 413
    assert len(forwarded) == JSON_REQUEST_LIMIT


def test_oversized_content_length_is_rejected_before_body_is_received():
    status, forwarded, _ = run_asgi_request(
        path="/api/test",
        method="POST",
        chunks=[b"small"],
        headers=[(b"content-length", str(JSON_REQUEST_LIMIT + 1).encode())],
    )
    assert status == 413
    assert forwarded == b""


def test_only_exact_image_upload_route_gets_6_mib_limit():
    upload_body = b"x" * (JSON_REQUEST_LIMIT + 1)
    status, forwarded, _ = run_asgi_request(
        path="/api/admin/products/123/image",
        method="POST",
        chunks=[upload_body],
    )
    assert status == 204
    assert forwarded == upload_body

    status, _, _ = run_asgi_request(
        path="/api/admin/products/not-an-id/image",
        method="POST",
        chunks=[upload_body],
    )
    assert status == 413


def test_image_upload_request_over_6_mib_is_rejected():
    status, _, _ = run_asgi_request(
        path="/api/admin/products/1/image",
        method="POST",
        chunks=[b"x" * IMAGE_UPLOAD_REQUEST_LIMIT, b"x"],
    )
    assert status == 413


def test_middleware_does_not_intercept_websocket_scope():
    called = []

    async def websocket_app(scope, receive, send):
        called.append(scope["type"])

    async def run():
        await RequestSizeLimitMiddleware(websocket_app)(
            {"type": "websocket", "path": "/ws/customer/selections"},
            lambda: None,
            lambda message: None,
        )

    asyncio.run(run())
    assert called == ["websocket"]


def test_existing_demo_auth_request_still_passes_through_middleware():
    with TestClient(app) as client:
        csrf_token = authenticate_demo(client)
        assert csrf_token
        assert client.get("/api/demo-auth/session").status_code == 200


def test_installed_middleware_rejects_large_json_and_preserves_cors_headers():
    with TestClient(app) as client:
        response = client.post(
            "/api/demo-auth/login",
            content=b"x" * (JSON_REQUEST_LIMIT + 1),
            headers={"Origin": "http://localhost:5173", "Content-Type": "application/json"},
        )
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_installed_middleware_rejects_image_request_over_6_mib_before_auth():
    with TestClient(app) as client:
        response = client.post(
            "/api/admin/products/1/image",
            content=b"x" * (IMAGE_UPLOAD_REQUEST_LIMIT + 1),
            headers={"Origin": "http://localhost:5173"},
        )
    assert response.status_code == 413
