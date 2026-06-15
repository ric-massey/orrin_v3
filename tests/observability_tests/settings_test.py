# D1 (DESKTOP_APP_PLAN Phase 4): API keys live in the OS keychain, set via a small
# guarded write surface (POST /api/settings) that never returns or logs the value;
# Reset Orrin is a guarded control action. conftest forces ORRIN_KEYRING=0 so these
# exercise the in-memory secrets backend and never touch the real Keychain.
import pytest
from fastapi.testclient import TestClient

from backend.server.app import app, set_reset_handler
from brain.utils import secrets

# Loopback client: control endpoints are localhost-only without a token, and the
# native window / bridge present as 127.0.0.1.
client = TestClient(app, client=("127.0.0.1", 0))
EVIL = {"Origin": "http://evil.com"}


@pytest.fixture(autouse=True)
def _clean_keys(monkeypatch):
    """Start each test with no keys set anywhere (env or memory backend)."""
    for env in secrets.ENV_VARS.values():
        monkeypatch.delenv(env, raising=False)
    secrets._MEM.clear()
    yield
    secrets._MEM.clear()


def test_secrets_round_trip_memory_backend():
    cfg = secrets.configured()
    assert cfg["openai"] is False and cfg["serper"] is False
    secrets.set_key("openai", "sk-abc")
    assert secrets.get_key("openai") == "sk-abc"
    assert secrets.configured()["openai"] is True
    secrets.set_key("openai", "")  # clear
    assert secrets.get_key("openai") is None
    assert secrets.configured()["openai"] is False


def test_get_settings_reports_symbolic_only_with_no_keys():
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"]["openai"] is False and body["configured"]["serper"] is False
    assert body["symbolic_only"] is True
    # Part 11: the provider menu ships with the request (no secret values).
    assert body["llm"]["selected"] == "openai"
    assert any(p["id"] == "anthropic" for p in body["llm"]["providers"])


def test_post_settings_sets_key_and_never_returns_value():
    r = client.post("/api/settings", json={"openai_api_key": "sk-secret-xyz"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["configured"]["openai"] is True
    assert body["symbolic_only"] is False
    assert "sk-secret-xyz" not in r.text  # the value is never echoed back
    # Stored, and live in the env for immediate effect this session.
    assert secrets.get_key("openai") == "sk-secret-xyz"

    # Clearing it returns to symbolic-only.
    r = client.post("/api/settings", json={"openai_api_key": ""})
    assert r.json()["configured"]["openai"] is False
    assert r.json()["symbolic_only"] is True


def test_settings_rejects_foreign_origin():
    assert client.get("/api/settings", headers=EVIL).status_code == 403
    assert client.post("/api/settings", json={"openai_api_key": "x"}, headers=EVIL).status_code == 403


def test_reset_requires_registered_handler():
    set_reset_handler(None)  # no orchestrator handler → reset is unavailable
    assert client.post("/api/control/reset").status_code == 503


def test_reset_invokes_handler_and_rejects_foreign_origin():
    hits = {"n": 0}
    set_reset_handler(lambda: hits.__setitem__("n", hits["n"] + 1))
    try:
        assert client.post("/api/control/reset", headers=EVIL).status_code == 403
        r = client.post("/api/control/reset")
        assert r.status_code == 200 and r.json()["resetting"] is True
        # The handler fires on a short timer, off the response — give it a beat.
        import time
        time.sleep(0.5)
        assert hits["n"] == 1
    finally:
        set_reset_handler(None)
