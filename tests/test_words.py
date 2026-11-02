import pytest
from fastapi.testclient import TestClient

from token_saver.app import create_app
from token_saver.tokenizer import encoding, word_breakdown


def test_simple_word_counts_are_in_original_context():
    result = word_breakdown("Hello world!", "o200k_base")
    assert [(row["word"], row["token_count"]) for row in result["words"]] == [("Hello", 1), ("world!", 2)]
    assert result["words"][1]["pieces"][0]["text"] == " world"
    assert result["prompt_tokens"] == 3
    assert result["whitespace_only_tokens"] == 0


@pytest.mark.parametrize("text", ["नमस्ते दुनिया 🌏", "你好 世界", "مرحبا بالعالم", "🧑🏽‍💻 café", "\tHello  world!\n\n", "<|endoftext|> literal"])
def test_unicode_and_whitespace_alignment(text):
    result = word_breakdown(text, "o200k_base")
    raw = text.encode("utf-8")
    enc = encoding("o200k_base")
    ids = enc.encode(text, disallowed_special=())
    for row in result["words"]:
        assert text[row["start"]:row["end"]] == row["word"]
        joined = b"".join(enc.decode_single_token_bytes(piece["id"]) for piece in row["pieces"])
        assert row["word"].encode("utf-8") in joined
    positions = {piece["position"] for row in result["words"] for piece in row["pieces"]}
    assert len(positions) + result["whitespace_only_tokens"] == len(ids)
    assert b"".join(enc.decode_single_token_bytes(token_id) for token_id in ids) == raw


def test_shared_token_is_explicit_not_silently_double_counted(monkeypatch):
    class ExampleEncoding:
        def encode(self, text, **kwargs):
            return [77]

        def decode_single_token_bytes(self, token_id):
            return b"one two"
    monkeypatch.setattr("token_saver.tokenizer.encoding", lambda name: ExampleEncoding())
    result = word_breakdown("one two", "example")
    assert result["prompt_tokens"] == 1
    assert result["word_token_references"] == 2
    assert result["shared_tokens"] == 1
    assert all(row["pieces"][0]["shared"] for row in result["words"])


def test_search_filter_and_pagination_cover_all_words():
    text = " ".join(["Hello", "antidisestablishmentarianism"] * 130)
    first = word_breakdown(text, "o200k_base", limit=100)
    last = word_breakdown(text, "o200k_base", offset=200, limit=100)
    assert first["total_words"] == 260
    assert first["has_more"]
    assert len(last["words"]) == 60
    assert last["words"][0]["number"] == 201
    assert not last["has_more"]
    filtered = word_breakdown(text, "o200k_base", query="ANTIDIS", min_tokens=2)
    assert filtered["matching_words"] == 130
    assert all(row["token_count"] >= 2 for row in filtered["words"])


def test_no_fake_word_tokenization_for_unsupported_provider():
    result = word_breakdown("Hello world", None)
    assert not result["available"]
    assert result["words"] == []


def test_extremely_long_word_has_bounded_piece_preview():
    result = word_breakdown("x" * 10000, "o200k_base")
    row = result["words"][0]
    assert row["token_count"] > 64
    assert len(row["pieces"]) == 64
    assert row["pieces_truncated"]
    assert row["token_count"] == result["prompt_tokens"]


def test_word_endpoint_validation_and_pagination(tmp_path):
    with TestClient(create_app(tmp_path / "words.sqlite3")) as client:
        response = client.post("/api/words", json={"prompt":"Hello world!", "limit":1, "offset":1})
        assert response.status_code == 200
        assert response.json()["words"][0]["word"] == "world!"
        assert client.post("/api/words", json={"prompt":"Hi", "limit":201}).status_code == 422
        assert client.post("/api/words", json={"prompt":"  "}).status_code == 422
        response = client.post("/api/words", json={"prompt":"Hi", "model_id":"claude-sonnet-5-5"})
        assert not response.json()["available"]
        result = client.post("/api/analyze", json={"prompt":"Hello world!"}).json()
        assert result["word_preview"]["prompt_tokens"] == result["counting"]["breakdown"]["prompt"]
