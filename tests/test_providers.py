import httpx
import pytest

from token_saver.analyzer import analyze
from token_saver.catalog import get_model
from token_saver.providers import ProviderError, count_with_provider
from token_saver.schemas import AnalysisRequest


def mock_provider(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr("token_saver.providers.httpx.Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


def test_anthropic_adapter_counts_without_generating(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test-key")
    def handler(request):
        import json
        assert request.url.path == "/v1/messages/count_tokens"
        body = json.loads(request.content)
        assert body["model"] == "claude-sonnet-5-5"
        assert body["system"] == "Be brief"
        assert len(body["messages"]) == 2
        assert request.headers["x-api-key"] == "fake-test-key"
        return httpx.Response(200, json={"input_tokens": 42})
    mock_provider(monkeypatch, handler)
    request = AnalysisRequest(prompt="Hello", system_prompt="Be brief", history=[{"role":"user","content":"Earlier"}], model_id="claude-sonnet-5-5", count_mode="provider", extra_input_tokens=10)
    result = analyze(request)
    assert result["counting"]["input_tokens"] == 52
    assert result["counting"]["overhead_tokens"] is None
    assert result["counting"]["method"] == "provider_count"


def test_google_adapter_includes_system_instruction(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")
    def handler(request):
        import json
        assert str(request.url) == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:countTokens"
        assert "key=" not in str(request.url)
        body = json.loads(request.content)["generateContentRequest"]
        assert body["systemInstruction"]["parts"][0]["text"] == "Be brief"
        assert body["contents"][0]["role"] == "model"
        return httpx.Response(200, json={"totalTokens": 21})
    mock_provider(monkeypatch, handler)
    request = AnalysisRequest(prompt="Hello", system_prompt="Be brief", history=[{"role":"assistant","content":"Hi"}], model_id="gemini-3.8-flash")
    assert count_with_provider(request, get_model(request.model_id)) == 21


def test_missing_key_does_not_silently_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        analyze(AnalysisRequest(prompt="Hello", model_id="claude-sonnet-5-5", count_mode="provider"))


def test_provider_error_is_sanitized(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test-key")
    mock_provider(monkeypatch, lambda request: httpx.Response(401, json={"error":"secret response contents"}))
    with pytest.raises(ProviderError) as error:
        count_with_provider(AnalysisRequest(prompt="Hi"), get_model("claude-sonnet-5-5"))
    assert "401" in str(error.value)
    assert "secret" not in str(error.value)
    assert "fake-test-key" not in str(error.value)


def test_invalid_provider_count_rejected(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")
    mock_provider(monkeypatch, lambda request: httpx.Response(200, json={"totalTokens": -1}))
    with pytest.raises(ProviderError):
        count_with_provider(AnalysisRequest(prompt="Hi"), get_model("gemini-3.8-flash"))
