from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    @field_validator("*", mode="before")
    @classmethod
    def valid_unicode(cls, value):
        if isinstance(value, str) and any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
            raise ValueError("Text must contain valid Unicode characters.")
        return value


class Message(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class CustomModel(StrictModel):
    name: str = Field(default="My model", min_length=1, max_length=80)
    encoding: Literal["heuristic", "o200k_base", "cl100k_base"] = "heuristic"
    input_price: Decimal = Field(default=Decimal("1"), ge=0, le=10000)
    output_price: Decimal = Field(default=Decimal("3"), ge=0, le=10000)
    cached_price: Decimal | None = Field(default=None, ge=0, le=10000)
    context_window: int = Field(default=128000, ge=1, le=10000000)
    max_output: int = Field(default=16384, ge=1, le=2000000)


class AnalysisRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=100000)
    model_id: str = "gpt-5.4-mini"
    system_prompt: str = Field(default="", max_length=50000)
    history: list[Message] = Field(default_factory=list, max_length=100)
    output_low: int = Field(default=256, ge=0, le=2000000)
    output_expected: int = Field(default=512, ge=0, le=2000000)
    output_high: int = Field(default=1024, ge=0, le=2000000)
    reasoning_tokens: int = Field(default=0, ge=0, le=2000000)
    extra_input_tokens: int = Field(default=0, ge=0, le=5000000)
    cached_input_tokens: int = Field(default=0, ge=0, le=5000000)
    calls: int = Field(default=1000, ge=1, le=10000000)
    budget_usd: Decimal | None = Field(default=None, gt=0, le=1000000000)
    count_mode: Literal["local", "provider"] = "local"
    custom_model: CustomModel | None = None

    @field_validator("prompt")
    @classmethod
    def meaningful_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a prompt before analyzing.")
        return value

    @model_validator(mode="after")
    def validate_request(self):
        if not self.output_low <= self.output_expected <= self.output_high:
            raise ValueError("Response budgets must satisfy low <= expected <= high.")
        total_chars = len(self.prompt) + len(self.system_prompt) + sum(len(m.content) for m in self.history)
        if total_chars > 200000:
            raise ValueError("Combined prompt, system instruction and history must be under 200,000 characters.")
        if self.model_id == "custom" and self.custom_model is None:
            raise ValueError("Custom model settings are required.")
        if self.model_id != "custom" and self.custom_model is not None:
            raise ValueError("Custom rates apply only when Custom model is selected.")
        return self


class HealRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=100000)
    model_id: str = "gpt-5.4-mini"
    custom_model: CustomModel | None = None
    shorten_phrases: bool = False

    @field_validator("prompt")
    @classmethod
    def meaningful_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a prompt before healing.")
        return value


class WordRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=100000)
    model_id: str = "gpt-5.4-mini"
    custom_model: CustomModel | None = None
    offset: int = Field(default=0, ge=0, le=100000)
    limit: int = Field(default=100, ge=1, le=200)
    query: str = Field(default="", max_length=100)
    min_tokens: int = Field(default=0, ge=0, le=100000)


class SaveRequest(StrictModel):
    title: str = Field(default="Untitled analysis", min_length=1, max_length=120)
    request: AnalysisRequest


class OptimizeRequest(StrictModel):
    request: AnalysisRequest
    optimizer_model: Literal["openai/gpt-oss-120b", "openai/gpt-oss-20b"] = "openai/gpt-oss-120b"
    keep_exact: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_optimizer(self):
        if len(self.request.prompt) > 20000:
            raise ValueError("AI optimization supports prompts up to 20,000 characters. Local analysis supports longer prompts.")
        lines = [line.strip() for line in self.keep_exact.splitlines() if line.strip()]
        if len(lines) > 40:
            raise ValueError("Use at most 40 protected text snippets.")
        if any(line not in self.request.prompt for line in lines):
            raise ValueError("Each protected snippet must already appear exactly in your prompt.")
        return self
