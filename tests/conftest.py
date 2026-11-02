import pytest


@pytest.fixture(autouse=True)
def test_client_hosts(monkeypatch):
    """Keep TestClient independent of the user's local .env host allowlist."""
    monkeypatch.setenv("TOKEN_SAVER_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1],testserver")
