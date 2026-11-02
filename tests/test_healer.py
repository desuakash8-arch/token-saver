import pytest

from token_saver.healer import heal
from token_saver.schemas import HealRequest


def test_healing_is_preview_only_and_saves_tokens():
    prompt = " Please    explain gravity in order to help a beginner.\n\n\n\nKeep it short.   "
    result = heal(HealRequest(prompt=prompt, shorten_phrases=True))
    assert result["original"] == prompt
    assert result["saved_tokens"] > 0
    assert "in order to" not in result["healed"]
    assert "Keep it short." in result["healed"]
    assert result["healed"].startswith("Explain")


def test_shorter_phrases_preserve_sentence_case():
    result = heal(HealRequest(prompt="Due to the fact that time is limited, be brief. In order to help, add an example.", shorten_phrases=True))
    assert result["healed"].startswith("Because")
    assert ". To help" in result["healed"]


@pytest.mark.parametrize("prompt", [
    "```python\nif True:\n    print('hello')\n```",
    '{"instruction": "Please  preserve spacing"}',
    'Repeat exactly: "Please    help"',
    "def square(x):\n    return x * x",
    "# Title\n\n- Keep this\n- Keep that",
    "<div>please  help</div>",
])
def test_structured_and_quoted_content_unchanged(prompt):
    result = heal(HealRequest(prompt=prompt, shorten_phrases=True))
    assert result["protected"]
    assert result["healed"] == prompt
    assert result["saved_tokens"] == 0


def test_no_negative_savings():
    for prompt in ["Hi", "Write a poem.", "Explain quantum mechanics."]:
        result = heal(HealRequest(prompt=prompt))
        assert result["after_tokens"] <= result["before_tokens"]


@pytest.mark.parametrize("prompt", [
    "Please return exactly 'in order to' without changing the quoted text.",
    "Please repeat “due to the fact that” exactly as written.",
    "Please repeat ‘in order to’.",
    "select 'in order to' as phrase;",
    "Please reproduce the following text verbatim: in order to learn.",
    "Do not change spacing: Please    explain this.",
])
def test_exact_text_and_single_or_curly_quotes_are_preserved(prompt):
    result = heal(HealRequest(prompt=prompt, shorten_phrases=True))
    assert result["protected"]
    assert result["healed"] == prompt
    assert result["saved_tokens"] == 0


def test_whitespace_only_heal_request_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        HealRequest(prompt="  ")
