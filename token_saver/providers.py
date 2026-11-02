"""Opt-in input counting only. These adapters never generate a completion."""

import os

import httpx

from .schemas import AnalysisRequest


class ProviderError(RuntimeError):
    pass


def provider_status() -> dict:
    return {"anthropic": bool(os.getenv("ANTHROPIC_API_KEY")), "google": bool(os.getenv("GEMINI_API_KEY"))}


def count_with_provider(request: AnalysisRequest, model: dict) -> int:
    provider = model["provider"]
    messages = [m.model_dump() for m in request.history] + [{"role": "user", "content": request.prompt}]
    if provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError("Set ANTHROPIC_API_KEY on the server to enable Anthropic token counting.")
        url = "https://api.anthropic.com/v1/messages/count_tokens"
        headers = {"x-api-key": key, "anthropic-version": "2026-10-21"}
        body = {"model": model["id"], "messages": messages}
        if request.system_prompt:
            body["system"] = request.system_prompt
        result_key = "input_tokens"
    elif provider == "google":
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ProviderError("Set GEMINI_API_KEY on the server to enable Gemini token counting.")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model['id']}:countTokens"
        headers = {"x-goog-api-key": key}
        generation_request = {
            "model": f"models/{model['id']}",
            "contents": [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in messages],
        }
        if request.system_prompt:
            generation_request["systemInstruction"] = {"parts": [{"text": request.system_prompt}]}
        body = {"generateContentRequest": generation_request}
        result_key = "totalTokens"
    else:
        raise ProviderError("Provider counting is available for Anthropic and Google. Use local counting for this model.")
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            count = response.json()[result_key]
        if type(count) is not int or count < 0:
            raise ValueError("Invalid token count")
        return count
    except httpx.HTTPStatusError as exc:
        # Never return raw provider bodies or credentials to the browser.
        raise ProviderError(f"Provider rejected token counting (HTTP {exc.response.status_code}). Check the API key, model access and limits, or switch to local mode.") from exc
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise ProviderError("Provider counting failed or timed out. Retry or switch to local mode.") from exc
