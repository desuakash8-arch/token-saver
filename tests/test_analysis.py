from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from token_saver.analyzer import analyze, calculate_cost, compare
from token_saver.catalog import catalog, get_model
from token_saver.schemas import AnalysisRequest, CustomModel
from token_saver.tokenizer import count_text, encoding, estimate_text, token_preview


def test_known_text_count_and_literal_special_tokens():
    assert count_text("Hello world!", "o200k_base") == 3
    assert count_text("<|endoftext|>", "o200k_base") > 1
    assert count_text("", "o200k_base") == 0


@pytest.mark.parametrize("text", ["Hello, world!", "नमस्ते दुनिया 🌏", "你好世界", "🧑🏽‍💻", "مرحبا بالعالم", "a\n\tb", "<script>alert('x')</script>"])
def test_preview_is_lossless_at_token_id_level(text):
    preview = token_preview(text, "o200k_base")
    assert encoding("o200k_base").decode([t["id"] for t in preview["tokens"]]) == text
    assert preview["total"] == count_text(text, "o200k_base")


def test_full_input_includes_system_history_and_overhead():
    request = AnalysisRequest(prompt="Hello world!", system_prompt="Be brief.", history=[{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}], extra_input_tokens=100)
    result = analyze(request)
    counting = result["counting"]
    assert counting["text_tokens"] == 3 + count_text("Be brief.", "o200k_base") + 2
    assert counting["overhead_tokens"] == 19
    assert counting["input_tokens"] == counting["text_tokens"] + 119
    assert result["scenarios"]["expected"]["total_tokens"] == counting["input_tokens"] + 512


def test_decimal_cost_and_cache_arithmetic():
    model = get_model("gpt-5.4-mini")
    result = calculate_cost(1000000, 100000, 200000, model)
    assert result["input_usd"] == pytest.approx(.8 * .75 + .2 * .075)
    assert result["output_usd"] == pytest.approx(.45)
    assert result["total_usd"] == pytest.approx(1.065)


def test_long_context_pricing_boundary():
    model = get_model("gpt-5.4")
    assert not calculate_cost(272000, 10, 0, model)["long_context_pricing"]
    result = calculate_cost(272001, 10, 0, model)
    assert result["long_context_pricing"]
    assert Decimal(result["input_rate"]) == 5
    assert Decimal(result["output_rate"]) == Decimal("22.5")


def test_scheduled_price_change_is_not_applied_early():
    old = next(m for m in catalog(date(2026, 12, 31))["models"] if m["id"] == "gemini-3.8-flash")
    new = next(m for m in catalog(date(2027, 1, 1))["models"] if m["id"] == "gemini-3.8-flash")
    assert old["input_price"] == "0.75"
    assert new["input_price"] == "1.50"


def test_reasoning_added_to_output_and_cost():
    result = analyze(AnalysisRequest(prompt="Hello", reasoning_tokens=200, calls=500, budget_usd="10"))
    assert result["scenarios"]["expected"]["billed_output_tokens"] == 712
    assert result["volume"]["total_usd"] == pytest.approx(result["scenarios"]["expected"]["total_usd"] * 500)
    assert result["volume"]["calls_within_budget"] > 0


def test_heuristics_are_honestly_labelled():
    result = analyze(AnalysisRequest(prompt="你好世界 hello", model_id="claude-sonnet-5-5"))
    assert result["counting"]["method"] == "heuristic"
    assert result["counting"]["sensitivity"] is not None
    assert not result["token_preview"]["available"]
    assert estimate_text("你好世界") >= 4
    assert estimate_text("") == 0


def test_output_limit_and_combined_context_limit():
    custom = CustomModel(context_window=100, max_output=50)
    result = analyze(AnalysisRequest(prompt="Hello", model_id="custom", custom_model=custom, output_low=10, output_expected=20, output_high=40, reasoning_tokens=20))
    assert not result["context"]["fits"]
    assert any("exceeds" in warning for warning in result["warnings"])


def test_google_checks_input_and_output_separately():
    result = analyze(AnalysisRequest(prompt="Hello", model_id="gemini-2.5-flash", extra_input_tokens=1048000, output_low=100, output_expected=200, output_high=1000))
    assert result["context"]["fits"]
    assert result["context"]["used"] == result["counting"]["input_tokens"]


def test_cache_over_input_rejected():
    with pytest.raises(ValueError, match="Cached tokens"):
        analyze(AnalysisRequest(prompt="Hi", cached_input_tokens=1000))


def test_zero_cost_custom_model_has_no_finite_budget_limit():
    result = analyze(AnalysisRequest(prompt="Hello", model_id="custom", custom_model=CustomModel(input_price=0, output_price=0), budget_usd="10"))
    assert result["scenarios"]["expected"]["total_usd"] == 0
    assert result["volume"]["calls_within_budget"] is None


@pytest.mark.parametrize("values", [
    {"prompt": " "}, {"prompt": "a" * 100001}, {"prompt": "Hi", "output_low": 513},
    {"prompt": "Hi", "output_expected": -1}, {"prompt": "Hi", "calls": 0},
    {"prompt": "Hi", "model_id": "custom"}, {"prompt": "Hi", "budget_usd": "NaN"},
    {"prompt": "Hi", "unknown": "field"}, {"prompt": "Hi", "history": [{"role":"system","content":"x"}]}
])
def test_invalid_requests_rejected(values):
    with pytest.raises(ValidationError):
        AnalysisRequest(**values)


def test_comparison_does_not_call_provider(monkeypatch):
    def unexpected(*args):
        pytest.fail("Comparison must stay local")
    monkeypatch.setattr("token_saver.analyzer.count_with_provider", unexpected)
    rows = compare(AnalysisRequest(prompt="Hello", model_id="claude-sonnet-5-5", count_mode="provider"))
    assert len(rows) == 9
    assert [r["cost_usd"] for r in rows] == sorted(r["cost_usd"] for r in rows)
    assert {r["model"]["provider"] for r in rows} == {"openai", "anthropic", "google", "groq"}
