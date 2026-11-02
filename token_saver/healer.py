"""Deterministic, reviewable editing. No claim of semantic equivalence."""

import re

from .catalog import get_model
from .schemas import HealRequest
from .tokenizer import count_text


def heal(request: HealRequest) -> dict:
    if request.model_id == "custom":
        if request.custom_model is None:
            raise ValueError("Custom model settings are required.")
        enc = request.custom_model.encoding
        enc = None if enc == "heuristic" else enc
    else:
        enc = get_model(request.model_id)["encoding"]
    original = request.prompt
    candidate = original
    changes = []
    # Structured prompts, code, quoted text and markdown can have significant whitespace.
    protected = bool(re.search(
        r"[`\"\u201c\u201d\u2018\u2019{}\[\]<>\t]"
        r"|(?<!\w)'[^'\n]+'(?!\w)"
        r"|(?m:^ {2,}\S)"
        r"|(?m:^\s*(?:[-*#>]|\d+\.)\s)"
        r"|(?im:^\s*(?:def |class |import |select |insert |update |delete |function ))"
        r"|(?i:\bverbatim\b|\bexactly as written\b|\b(?:do not|don't|without) chang(?:e|ing)\b)",
        original,
    ))
    if not protected:
        candidate = re.sub(r" {2,}", " ", original.strip())
        candidate = re.sub(r"\n(?:[ \r]*\n){2,}", "\n\n", candidate)
        if candidate != original:
            changes.append("Removed outer whitespace, repeated spaces and excessive blank lines.")
        if request.shorten_phrases:
            substitutions = [(r"(?i)^please\s+", "", "Opening 'please'"), (r"(?i)\bin order to\b", "to", "'in order to'"), (r"(?i)\bdue to the fact that\b", "because", "'due to the fact that'"), (r"(?i)\bat this point in time\b", "now", "'at this point in time'"), (r"(?i)\bfor the purpose of\b", "for", "'for the purpose of'")]
            for pattern, replacement, label in substitutions:
                def replace(match):
                    if not replacement:
                        return ""
                    if match[0].isupper():
                        return replacement.upper()
                    return replacement.capitalize() if match[0][0].isupper() else replacement

                shortened, number = re.subn(pattern, replace, candidate)
                if number:
                    changes.append(f"{label} → {replacement or '(removed)'} ({number} change(s)).")
                    if label == "Opening 'please'" and candidate[0].isupper() and shortened:
                        shortened = shortened[0].upper() + shortened[1:]
                    candidate = shortened
    before = count_text(original, enc)
    after = count_text(candidate, enc)
    if after >= before or not candidate.strip():
        candidate, after, changes = original, before, []
    suggestions = []
    if protected:
        suggestions.append("Structured, quoted or code-like content detected. Automatic edits were skipped to protect formatting; review manually.")
    if not changes:
        suggestions.append("No token-reducing edits found under the selected rules. A shorter character count does not always mean fewer tokens.")
    if len(original) > 3000:
        suggestions.append("Review long context for irrelevant passages. Keep the facts and constraints the answer needs.")
    sentences = [s.strip().casefold() for s in re.split(r"[.!?]\s+", original) if len(s.strip()) > 25]
    if len(set(sentences)) < len(sentences):
        suggestions.append("Repeated sentences detected. Remove them only if repetition is not intentional.")
    suggestions.append("Specify the desired response length to control output usage. Review every proposed edit before applying it.")
    return {"original": original, "healed": candidate, "before_tokens": before, "after_tokens": after, "saved_tokens": before - after, "saved_percent": round((before - after) / before * 100, 1) if before else 0, "method": "local_tokenizer" if enc else "heuristic", "changes": changes, "suggestions": suggestions, "protected": protected}
