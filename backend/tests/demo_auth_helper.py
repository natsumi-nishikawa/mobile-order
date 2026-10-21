from fastapi.testclient import TestClient

DEMO_ORIGIN = "http://localhost:5173"


def authenticate_demo(client: TestClient) -> str:
    response = client.post(
        "/api/demo-auth/login",
        json={"password": "test-demo-password"},
        headers={"Origin": DEMO_ORIGIN},
    )
    assert response.status_code == 200
    csrf_token = response.json()["csrf_token"]
    client.headers.update(
        {"Origin": DEMO_ORIGIN, "X-CSRF-Token": csrf_token}
    )
    return csrf_token
