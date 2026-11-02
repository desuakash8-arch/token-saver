from datetime import datetime, timezone
from decimal import Decimal
import math
import re

from .catalog import catalog, get_model
from .providers import count_with_provider
from .schemas import AnalysisRequest
from .tokenizer import count_text, token_preview, word_breakdown


def resolve_model(request: AnalysisRequest) -> dict:
    if request.model_id != "custom":
        return get_model(request.model_id)
    custom = request.custom_model.model_dump(mode="json")
    return {**custom, "id": "custom", "provider": "custom", "provider_name": "Custom provider", "encoding": None if custom["encoding"] == "heuristic" else custom["encoding"], "context_kind": "combined", "status": "User-defined", "source": None}


def calculate_cost(input_tokens: int, output_tokens: int, cached: int, model: dict) -> dict:
    if cached > input_tokens:
        raise ValueError("Cached tokens cannot exceed the estimated input tokens.")
    if cached and model.get("cached_price") is None:
        raise ValueError("This custom model needs a cached-input rate before cache savings can be calculated.")
    long = input_tokens > model.get("long_context_threshold", math.inf)
    input_multiplier = Decimal(model.get("long_input_multiplier", "1")) if long else Decimal(1)
    output_multiplier = Decimal(model.get("long_output_multiplier", "1")) if long else Decimal(1)
    input_rate = Decimal(model["input_price"]) * input_multiplier
    output_rate = Decimal(model["output_price"]) * output_multiplier
    cached_rate = Decimal(model.get("cached_price") or model["input_price"]) * input_multiplier
    ordinary_cost = Decimal(input_tokens - cached) * input_rate / 1000000
    cache_cost = Decimal(cached) * cached_rate / 1000000
    output_cost = Decimal(output_tokens) * output_rate / 1000000
    return {"input_usd": float(ordinary_cost + cache_cost), "cached_usd": float(cache_cost), "output_usd": float(output_cost), "total_usd": float(ordinary_cost + cache_cost + output_cost), "long_context_pricing": long, "input_rate": str(input_rate), "output_rate": str(output_rate), "cached_rate": str(cached_rate)}


def analyze(request: AnalysisRequest, *, preview: bool = True) -> dict:
    model = resolve_model(request)
    enc = model["encoding"]
    parts = {
        "prompt": count_text(request.prompt, enc),
        "system": count_text(request.system_prompt, enc),
        "history": sum(count_text(m.content, enc) for m in request.history),
    }
    text_tokens = sum(parts.values())
    message_count = 1 + len(request.history) + bool(request.system_prompt)
    overhead = 3 + 4 * message_count
    method = "local_tokenizer" if enc else "heuristic"
    warnings = []
    if request.count_mode == "provider":
        base_input = count_with_provider(request, model)
        method = "provider_count"
        overhead = None
        warnings.append("Provider count covers the supplied system instruction and messages. The per-section breakdown remains a local estimate.")
    else:
        base_input = text_tokens + overhead
        warnings.append("Message formatting overhead is a planning allowance (4 per message + 3), not a guaranteed API count.")
    input_tokens = base_input + request.extra_input_tokens
    if method == "heuristic":
        warnings.append("This model has no supported tokenizer bundled here. Local counts use an uncalibrated Unicode heuristic; actual counts can differ substantially.")
        if model.get("supports_provider_count"):
            warnings.append("Use provider counting for a model-specific input count.")
        else:
            warnings.append("A provider token-count endpoint is not integrated for this model. Analysis stays local; exact billed counts require usage from an actual generation request.")
    if request.model_id == "custom" and enc:
        warnings.append("The selected encoding counts text exactly, but its match to your custom model has not been verified.")
    if request.reasoning_tokens == 0:
        warnings.append("Reasoning allowance is zero. Add a budget if your chosen model uses billed thinking or reasoning tokens.")
    warnings.append("Response lengths are your planning scenarios, not predictions. Tool loops, media, hidden platform instructions and subscription quotas are not inferred.")
    if request.cached_input_tokens:
        warnings.append("Cache hits are assumed, not guaranteed. Cache write and storage fees are excluded.")
    if model["status"] != "Available":
        warnings.append(model["status"] + ". Check the provider before using this preset.")
    cat = catalog()
    if cat["age_days"] > 30:
        warnings.append("The pricing catalog was verified more than 30 days ago. Check the linked sources or enter custom rates.")
    output = {"low": request.output_low, "expected": request.output_expected, "high": request.output_high}
    scenarios = {}
    for label, visible in output.items():
        billed_output = visible + request.reasoning_tokens
        cost = calculate_cost(input_tokens, billed_output, request.cached_input_tokens, model)
        scenarios[label] = {"visible_output_tokens": visible, "billed_output_tokens": billed_output, "total_tokens": input_tokens + billed_output, **cost}
    highest_output = request.output_high + request.reasoning_tokens
    context_used = input_tokens + highest_output if model["context_kind"] == "combined" else input_tokens
    fits = context_used <= model["context_window"] and highest_output <= model["max_output"]
    if not fits:
        warnings.insert(0, "Your high response scenario exceeds the model's input/context or output limit. Reduce the prompt or response budget.")
    expected = scenarios["expected"]
    sensitivity = None
    if method == "heuristic":
        # A what-if band, not an empirical confidence interval.
        sensitivity = {"low": max(0, math.floor(base_input * .65)) + request.extra_input_tokens, "high": math.ceil(base_input * 1.35) + request.extra_input_tokens, "label": "±35% input sensitivity; actual count may lie outside this band"}
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "counting": {"method": method, "text_tokens": text_tokens, "input_tokens": input_tokens, "base_input_tokens": base_input, "overhead_tokens": overhead, "extra_input_tokens": request.extra_input_tokens, "breakdown": parts, "sensitivity": sensitivity},
        "statistics": {"characters": len(request.prompt), "words": len(re.findall(r"\S+", request.prompt)), "lines": len(request.prompt.splitlines()), "utf8_bytes": len(request.prompt.encode("utf-8"))},
        "scenarios": scenarios,
        "reasoning_tokens": request.reasoning_tokens,
        "volume": {"calls": request.calls, "total_usd": expected["total_usd"] * request.calls, "budget_usd": float(request.budget_usd) if request.budget_usd else None, "calls_within_budget": math.floor(float(request.budget_usd) / expected["total_usd"]) if request.budget_usd and expected["total_usd"] > 0 else None},
        "context": {"used": context_used, "limit": model["context_window"], "kind": model["context_kind"], "percent": round(context_used / model["context_window"] * 100, 3), "remaining": max(0, model["context_window"] - context_used), "max_output": model["max_output"], "fits": fits},
        "pricing": {"verified_on": cat["verified_on"], "basis": cat["pricing_basis"], "currency": "USD"},
        "warnings": warnings,
        "token_preview": token_preview(request.prompt, enc) if preview else None,
        "word_preview": word_breakdown(request.prompt, enc) if preview else None,
    }


def compare(request: AnalysisRequest) -> list[dict]:
    """Comparison stays local: one explicit provider request never fans out externally."""
    results = []
    models = catalog()["models"]
    if request.model_id == "custom":
        models.append(resolve_model(request))
    for model in models:
        values = request.model_dump()
        values.update(model_id=model["id"], count_mode="local", custom_model=request.custom_model if model["id"] == "custom" else None)
        try:
            result = analyze(AnalysisRequest(**values), preview=False)
            results.append({"model": result["model"], "input_tokens": result["counting"]["input_tokens"], "method": result["counting"]["method"], "cost_usd": result["scenarios"]["expected"]["total_usd"], "volume_usd": result["volume"]["total_usd"], "fits": result["context"]["fits"]})
        except ValueError as exc:
            results.append({"model": model, "error": str(exc)})
    return sorted(results, key=lambda item: item.get("cost_usd", math.inf))
