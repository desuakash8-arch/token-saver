"""Groq presets must remain local, honest estimates with host-specific rates."""

import pytest
from fastapi.testclient import TestClient

from token_saver.analyzer import analyze, calculate_cost, compare
from token_saver.app import create_app
from token_saver.catalog import get_model
from token_saver.providers import ProviderError
from token_saver.schemas import AnalysisRequest


MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]


@pytest.mark.parametrize("model_id,total", list(zip(MODELS, [.10125, .2025])))
def test_groq_host_rates_include_half_price_cached_input(model_id, total):
    # One million input tokens, half cached, and 150,000 output tokens.
    cost = calculate_cost(1_000_000, 150_000, 500_000, get_model(model_id))
    assert cost["total_usd"] == pytest.approx(total)


@pytest.mark.parametrize("model_id", MODELS)
def test_groq_local_analysis_and_comparison_never_call_provider(model_id, monkeypatch):
    def unexpected_call(*args, **kwargs):
        pytest.fail("Local Groq analysis must not contact a provider")

    monkeypatch.setattr("token_saver.analyzer.count_with_provider", unexpected_call)
    request = AnalysisRequest(prompt="Explain photosynthesis in three bullet points. नमस्ते 🌱", model_id=model_id)
    result = analyze(request)
    assert result["model"]["provider"] == "groq"
    assert result["counting"]["method"] == "heuristic"
    assert result["counting"]["input_tokens"] > 0
    assert result["word_preview"]["available"] is False
    assert any("actual counts can differ" in warning for warning in result["warnings"])
    assert any("not integrated" in warning for warning in result["warnings"])
    rows = compare(request.model_copy(update={"count_mode": "provider"}))
    groq_rows = [row for row in rows if row["model"]["provider"] == "groq"]
    assert {row["model"]["id"] for row in groq_rows} == set(MODELS)
    assert all(row["method"] == "heuristic" and row["cost_usd"] > 0 for row in groq_rows)


@pytest.mark.parametrize("model_id", MODELS)
def test_groq_generation_limits_and_unsupported_count_mode(model_id):
    request = AnalysisRequest(prompt="Hello", model_id=model_id, output_high=65_537)
    result = analyze(request)
    assert result["context"]["limit"] == 131_072
    assert result["context"]["max_output"] == 65_536
    assert result["context"]["fits"] is False
    with pytest.raises(ProviderError, match="Use local counting"):
        analyze(request.model_copy(update={"count_mode": "provider"}))


def test_groq_api_catalog_and_saved_analysis_round_trip(tmp_path):
    with TestClient(create_app(tmp_path / "groq.sqlite3")) as client:
        models = client.get("/api/models").json()["models"]
        groq = [model for model in models if model["provider"] == "groq"]
        assert len(groq) == 2
        assert all(model["supports_provider_count"] is False for model in groq)
        request = {"prompt": "Write a short welcome email.", "model_id": MODELS[0]}
        response = client.post("/api/analyze", json=request)
        assert response.status_code == 200
        assert response.json()["model"]["provider_name"] == "Groq"
        saved = client.post("/api/history", json={"title": "Groq example", "request": request})
        assert saved.status_code == 201
        restored = client.get(f"/api/history/{saved.json()['id']}").json()
        assert restored["request"]["model_id"] == MODELS[0]
        assert restored["result"]["counting"]["method"] == "heuristic"
