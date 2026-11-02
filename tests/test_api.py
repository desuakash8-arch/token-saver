from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from token_saver.app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "history.sqlite3")) as test_client:
        yield test_client


def test_health_static_and_openapi(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert "Token Saver" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert "/api/analyze" in client.get("/openapi.json").json()["paths"]


def test_analyze_does_not_save_and_history_round_trip(client):
    request = {"prompt": "Write a short welcome email."}
    result = client.post("/api/analyze", json=request)
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert client.get("/api/history").json()["items"] == []
    saved = client.post("/api/history", json={"title": "My welcome prompt", "request": request})
    assert saved.status_code == 201
    analysis_id = saved.json()["id"]
    assert len(client.get("/api/history?q=welcome").json()["items"]) == 1
    assert client.get("/api/history?q=no-match").json()["items"] == []
    restored = client.get(f"/api/history/{analysis_id}").json()
    assert restored["request"]["prompt"] == request["prompt"]
    assert restored["result"]["counting"]["input_tokens"] == result.json()["counting"]["input_tokens"]
    assert client.delete(f"/api/history/{analysis_id}").status_code == 204
    assert client.get(f"/api/history/{analysis_id}").status_code == 404


def test_history_survives_app_restart(tmp_path):
    path = tmp_path / "persistent.sqlite3"
    with TestClient(create_app(path)) as first:
        saved = first.post("/api/history", json={"title":"Persistent","request":{"prompt":"Hello"}}).json()
    with TestClient(create_app(path)) as second:
        assert second.get(f"/api/history/{saved['id']}").status_code == 200


def test_unknown_model_and_malformed_request(client):
    assert client.post("/api/analyze", json={"prompt":"Hello","model_id":"nonexistent"}).status_code == 422
    assert client.post("/api/analyze", json={"prompt":""}).status_code == 422
    assert client.post("/api/analyze", content="not json", headers={"content-type":"application/json"}).status_code == 422


def test_invalid_unicode_is_rejected_without_echoing_content(client):
    result = client.post("/api/analyze", content='{"prompt":"private \\ud800 text"}', headers={"content-type":"application/json"})
    assert result.status_code == 422
    assert "private" not in result.text


def test_invalid_unicode_in_history_is_rejected(client):
    result = client.post("/api/analyze", content='{"prompt":"Hi","history":[{"role":"user","content":"\\ud800"}]}', headers={"content-type":"application/json"})
    assert result.status_code == 422


def test_cross_origin_mutation_rejected(client):
    assert client.post("/api/analyze", json={"prompt":"Hi"}, headers={"origin":"https://untrusted.example"}).status_code == 403
    assert client.post("/api/analyze", json={"prompt":"Hi"}, headers={"origin":"http://testserver"}).status_code == 200


def test_missing_provider_key_reported(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = client.post("/api/analyze", json={"prompt":"Hi","model_id":"gemini-3.8-flash","count_mode":"provider"})
    assert result.status_code == 502
    assert "GEMINI_API_KEY" in result.json()["detail"]


def test_pagination_and_search_parameters_validated(client):
    assert client.get("/api/history?limit=0").status_code == 422
    assert client.get("/api/history?offset=-1").status_code == 422
    assert client.get("/api/history?q=%27%20OR%201=1--").json()["items"] == []
