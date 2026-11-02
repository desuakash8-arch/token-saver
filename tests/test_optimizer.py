import json
import math

from fastapi.testclient import TestClient
import httpx
import pytest

from token_saver import optimizer
from token_saver.app import create_app
from token_saver.schemas import AnalysisRequest, OptimizeRequest
from token_saver.tokenizer import count_text

ORIGINAL = "Please write a friendly welcome email for students. In order to keep it brief, use under 150 words. Do not invent features."
SHORTER = "Write a friendly student welcome email under 150 words. Do not invent features."


def request(prompt=ORIGINAL, **kwargs):
    return OptimizeRequest(request=AnalysisRequest(prompt=prompt, **kwargs))


def reply(candidate=SHORTER, usage=None, finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {"content": json.dumps({
        "optimized_prompt": candidate, "changes": ["Removed redundant phrasing."],
        "requirements": ["Friendly welcome email for students, under 150 words; no invented features."], "warnings": []})}}],
        "usage": usage if usage is not None else {"prompt_tokens": 800, "completion_tokens": 200}}


def mock_groq(monkeypatch, response=None, handler=None):
    real_client = httpx.Client
    monkeypatch.setenv("GROQ_API_KEY", "test-only-secret")
    monkeypatch.setattr(optimizer.httpx, "Client", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler or (lambda r: httpx.Response(200, json=response or reply()))), **kwargs))


def test_cloud_payload_has_no_system_history_keys_or_target_provider_calls(monkeypatch):
    seen = []
    def handler(http_request):
        seen.append(http_request)
        assert str(http_request.url) == "https://api.groq.com/openai/v1/chat/completions"
        assert http_request.headers["authorization"] == "Bearer test-only-secret"
        body = json.loads(http_request.content)
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["max_completion_tokens"] == 8192
        assert "tools" not in body
        assert "local-system-private" not in http_request.content.decode()
        assert "local-history-private" not in http_request.content.decode()
        assert json.loads(body["messages"][1]["content"])["source_prompt"] == ORIGINAL
        return httpx.Response(200, json=reply())
    mock_groq(monkeypatch, handler=handler)
    result = optimizer.optimize(request(model_id="claude-sonnet-5-5", count_mode="provider",
        system_prompt="local-system-private", history=[{"role":"user","content":"local-history-private"}]))
    assert result["accepted"]
    assert result["method"] == "heuristic"
    assert len(seen) == 1


def test_real_token_savings_and_optimizer_cost_break_even(monkeypatch):
    mock_groq(monkeypatch)
    result = optimizer.optimize(request(calls=1000))
    saved = count_text(ORIGINAL, "o200k_base") - count_text(SHORTER, "o200k_base")
    assert result["original"] == ORIGINAL
    assert result["optimized_prompt"] == SHORTER
    assert result["saved_tokens"] == saved > 0
    assert result["optimizer"]["estimated_cost_usd"] == pytest.approx(.00024)
    assert result["economics"]["input_saving_per_call_usd"] == pytest.approx(saved * .75 / 1000000)
    assert result["economics"]["break_even_calls"] == math.ceil(.00024 / (saved * .75 / 1000000))
    assert result["economics"]["net_saving_usd"] == pytest.approx(saved * .75 / 1000 - .00024)


@pytest.mark.parametrize("original,candidate", [
    ('Please retain "exact text" and write a short email.', 'Write a short email.'),
    ("Please explain this code: ```python\nprint(1)\n``` very briefly.", "Explain print(1)."),
    ("Please visit https://example.com/docs and summarize it.", "Summarize the documentation."),
    (ORIGINAL, SHORTER.replace("150", "100")),
    (ORIGINAL, SHORTER + " Mention 99 features."),
    ("Please keep ‘Blue Moon’ unchanged in a short title.", "Make a short Blue Moon title."),
    ("Please keep `some_id` exactly when writing a brief summary.", "Summarize some_id."),
    ("Use 150 words for A and 150 words for B, please.", "Use 150 words in total."),
])
def test_rejects_loss_or_change_of_literals(monkeypatch, original, candidate):
    mock_groq(monkeypatch, reply(candidate))
    result = optimizer.optimize(request(original))
    assert not result["accepted"]
    assert not result["literal_checks_passed"]
    assert result["optimized_prompt"] == original
    assert result["saved_tokens"] == 0
    assert result["economics"]["net_saving_usd"] < 0


def test_user_protected_snippet_enforced(monkeypatch):
    mock_groq(monkeypatch)
    payload = request()
    payload.keep_exact = "welcome email for students"
    assert not optimizer.optimize(payload)["accepted"]


@pytest.mark.parametrize("candidate", [ORIGINAL, ORIGINAL + " Add extra information."])
def test_no_savings_keeps_original(monkeypatch, candidate):
    mock_groq(monkeypatch, reply(candidate))
    result = optimizer.optimize(request())
    assert not result["accepted"] and result["optimized_prompt"] == ORIGINAL
    assert result["economics"]["break_even_calls"] is None


def test_uncached_comparison_does_not_fail_on_existing_cache_assumption(monkeypatch):
    mock_groq(monkeypatch)
    assert optimizer.optimize(request(cached_input_tokens=1000))["accepted"]


def test_missing_usage_not_invented_as_zero(monkeypatch):
    data = reply()
    data.pop("usage")
    mock_groq(monkeypatch, data)
    result = optimizer.optimize(request())
    assert result["optimizer"]["estimated_cost_usd"] is None
    assert result["economics"]["net_saving_usd"] is None
    assert result["economics"]["break_even_calls"] is None


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_errors_sanitized_and_not_retried(monkeypatch, status):
    seen = []
    def handler(http_request):
        seen.append(1)
        return httpx.Response(status, json={"error":"private response test-only-secret"})
    mock_groq(monkeypatch, handler=handler)
    with pytest.raises(optimizer.OptimizerError) as error:
        optimizer.optimize(request())
    assert "private" not in str(error.value) and "test-only-secret" not in str(error.value)
    assert len(seen) == 1
    assert error.value.status_code == (429 if status == 429 else 502)


def test_timeout_has_no_retry(monkeypatch):
    seen = []
    def handler(http_request):
        seen.append(1)
        raise httpx.ReadTimeout("private debug detail", request=http_request)
    mock_groq(monkeypatch, handler=handler)
    with pytest.raises(optimizer.OptimizerError, match="timed out"):
        optimizer.optimize(request())
    assert len(seen) == 1


@pytest.mark.parametrize("data", [reply(finish="length"), {"choices": []}, {"choices": ["bad choice"]},
    {"choices": [{"finish_reason":"stop", "message":{"content":"not json"}}]}, reply("   ")])
def test_unusable_response_never_applied(monkeypatch, data):
    mock_groq(monkeypatch, data)
    with pytest.raises(optimizer.OptimizerError):
        optimizer.optimize(request())


def test_missing_key_and_status_never_leaks_secret(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(optimizer.OptimizerError) as error:
        optimizer.optimize(request())
    assert error.value.status_code == 503
    monkeypatch.setenv("GROQ_API_KEY", "secret-value")
    assert optimizer.optimizer_status()["configured"]
    assert "secret-value" not in json.dumps(optimizer.optimizer_status())


def test_concurrent_request_rejected(monkeypatch):
    optimizer._SLOT.acquire()
    try:
        with pytest.raises(optimizer.OptimizerError) as error:
            optimizer.optimize(request())
        assert error.value.status_code == 429
    finally:
        optimizer._SLOT.release()


def test_api_validation_origin_and_local_history(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path / "history.sqlite3")) as client:
        for body in [
            {"request":{"prompt":""}},
            {"request":{"prompt":"x" * 20001}},
            {"request":{"prompt":ORIGINAL},"keep_exact":"not in this prompt"},
            {"request":{"prompt":ORIGINAL},"optimizer_model":"unknown"},
            {"request":{"prompt":ORIGINAL},"api_key":"not allowed"},
        ]:
            assert client.post("/api/optimize", json=body).status_code == 422
        assert client.post("/api/optimize", json={"request":{"prompt":ORIGINAL}}, headers={"origin":"https://foreign.test"}).status_code == 403
        mock_groq(monkeypatch)
        result = client.post("/api/optimize", json={"request":{"prompt":ORIGINAL}})
        assert result.status_code == 200 and result.json()["accepted"]
        assert result.headers["cache-control"] == "no-store"
        assert client.get("/api/history").json()["items"] == []
        assert "test-only-secret" not in client.get("/api/optimizer").text
