from fastapi.testclient import TestClient

from app.main import app


def test_json_responses_declare_utf8_charset():
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    assert "charset=utf-8" in response.headers["content-type"].lower()
