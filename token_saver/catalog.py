"""Versioned, editable model rates. No silent network updates."""

from datetime import date, datetime, timezone
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def _catalog() -> dict:
    return json.loads(Path(__file__).with_name("models.json").read_text(encoding="utf-8"))


def catalog(today: date | None = None) -> dict:
    result = json.loads(json.dumps(_catalog()))
    today = today or datetime.now(timezone.utc).date()
    for model in result["models"]:
        scheduled = model.get("scheduled_prices")
        if scheduled and today >= date.fromisoformat(scheduled["effective_on"]):
            model.update({k: v for k, v in scheduled.items() if k != "effective_on"})
            model["effective_on"] = scheduled["effective_on"]
        model["supports_provider_count"] = model["provider"] in {"anthropic", "google"}
        model["counting_method"] = ("local tokenizer" if model["encoding"] else
                                    "approximate locally / optional provider API" if model["supports_provider_count"] else
                                    "approximate locally only")
    result["age_days"] = max(0, (today - date.fromisoformat(result["verified_on"])).days)
    return result


def get_model(model_id: str) -> dict:
    for model in catalog()["models"]:
        if model["id"] == model_id:
            return model
    raise ValueError("Unknown model. Choose a model from the catalog or use Custom.")
