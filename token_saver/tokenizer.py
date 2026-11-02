"""Local counts are exact for the selected encoding, not for a billed request."""

from functools import lru_cache
from bisect import bisect_left, bisect_right
import math
import re

import tiktoken


class TokenizerUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=4)
def encoding(name: str):
    try:
        return tiktoken.get_encoding(name)
    except Exception as exc:
        raise TokenizerUnavailable(
            "Tokenizer vocabulary is unavailable. Connect once and run `python -m token_saver warmup`, then retry."
        ) from exc


def estimate_text(text: str) -> int:
    """Uncalibrated planning heuristic, intentionally not claimed as a vendor tokenizer.

    ASCII characters contribute 1/4 token; other UTF-8 bytes contribute 1/3.
    This avoids the worst English-only character-ratio failure for Unicode text.
    Actual vendor counts can fall outside the displayed sensitivity band.
    """
    if not text:
        return 0
    ascii_chars = sum(ord(c) < 128 for c in text)
    non_ascii_bytes = len(text.encode("utf-8", errors="replace")) - ascii_chars
    return max(1, math.ceil(ascii_chars / 4 + non_ascii_bytes / 3))


def count_text(text: str, encoding_name: str | None) -> int:
    if not encoding_name:
        return estimate_text(text)
    # Treat strings resembling special tokens as literal user text.
    return len(encoding(encoding_name).encode(text, disallowed_special=()))


def token_preview(text: str, encoding_name: str | None, limit: int = 400) -> dict:
    if not encoding_name:
        return {"available": False, "tokens": [], "truncated": False}
    enc = encoding(encoding_name)
    ids = enc.encode(text, disallowed_special=())
    tokens = []
    for token_id in ids[:limit]:
        raw = enc.decode_single_token_bytes(token_id)
        try:
            value = raw.decode("utf-8")
            byte_fragment = False
        except UnicodeDecodeError:
            value = " ".join(f"{b:02x}" for b in raw)
            byte_fragment = True
        tokens.append({"id": token_id, "text": value, "byte_fragment": byte_fragment})
    return {"available": True, "encoding": encoding_name, "tokens": tokens, "truncated": len(ids) > limit, "total": len(ids)}


def word_breakdown(text: str, encoding_name: str | None, *, offset: int = 0,
                   limit: int = 100, query: str = "", min_tokens: int = 0) -> dict:
    """Map non-whitespace spans to tokens in the ORIGINAL prompt, without retokenizing words.

    BPE tokens are byte spans, and can split a Unicode character or span more
    than one word. Intersection is therefore calculated using UTF-8 byte offsets.
    A token shared by words is counted in each affected row and marked explicitly.
    Whitespace-only tokens belong to no word and are reported separately.
    """
    words = list(re.finditer(r"\S+", text))
    if not encoding_name:
        return {"available": False, "total_words": len(words), "words": [],
                "reason": "This model has no tokenizer with token boundaries bundled here, so exact word-level counts are unavailable. Select an OpenAI API preset or a matching custom tokenizer to inspect words. Provider count endpoints, where supported, return totals rather than token boundaries."}
    enc = encoding(encoding_name)
    ids = enc.encode(text, disallowed_special=())
    raw_tokens = [enc.decode_single_token_bytes(token_id) for token_id in ids]
    byte_offsets = [0]
    for character in text:
        byte_offsets.append(byte_offsets[-1] + len(character.encode("utf-8")))
    token_starts, token_ends, cursor = [], [], 0
    for raw in raw_tokens:
        token_starts.append(cursor)
        cursor += len(raw)
        token_ends.append(cursor)
    usage = [0] * len(ids)
    spans = []
    for index, word in enumerate(words):
        start, end = byte_offsets[word.start()], byte_offsets[word.end()]
        first = bisect_right(token_ends, start)
        stop = bisect_left(token_starts, end)
        for token_index in range(first, stop):
            usage[token_index] += 1
        spans.append((index, word, first, stop))
    filtered = [span for span in spans if query.casefold() in span[1][0].casefold() and span[3] - span[2] >= min_tokens]
    rows = []
    for index, word, first, stop in filtered[offset:offset + limit]:
        pieces = []
        for token_index in range(first, min(stop, first + 64)):
            raw = raw_tokens[token_index]
            try:
                value, fragment = raw.decode("utf-8"), False
            except UnicodeDecodeError:
                value, fragment = " ".join(f"{byte:02x}" for byte in raw), True
            pieces.append({"id": ids[token_index], "text": value, "byte_fragment": fragment,
                           "position": token_index, "shared": usage[token_index] > 1})
        rows.append({"number": index + 1, "word": word[0], "start": word.start(), "end": word.end(),
                     "token_count": stop - first, "pieces": pieces,
                     "pieces_truncated": stop - first > len(pieces)})
    return {"available": True, "encoding": encoding_name, "total_words": len(words),
            "matching_words": len(filtered), "offset": offset, "limit": limit,
            "has_more": offset + limit < len(filtered), "words": rows,
            "prompt_tokens": len(ids), "whitespace_only_tokens": usage.count(0),
            "shared_tokens": sum(count > 1 for count in usage),
            "word_token_references": sum(usage),
            "note": "Words are whitespace-separated spans, including punctuation. Counts use each word's position in the original prompt. A shared token appears in every word it touches; whitespace-only tokens are separate. Row counts therefore may not sum to the prompt total."}
