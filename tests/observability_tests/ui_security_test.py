# tests/observability_tests/ui_security_test.py
#
# Security regression tests for the UI telemetry backend (UI_AUDIT remediation,
# findings H1–H4). These lock in the guards so the fixes can't silently regress:
#
#   H1 — /api/source must not serve secrets/dotfiles (e.g. .env at repo root).
#   H2 — /api/control/* must reject a hostile browser Origin (CSRF shutdown).
#   H3 — /ingest and /api/agent/* must reject a hostile browser Origin, while
#        still accepting native (no-Origin) callers like the cognitive loop.
#
# NOTE: we never POST /api/control/shutdown with a trusted/absent Origin — that
# path fires SIGINT into the test process. We only assert the rejection path.
from __future__ import annotations


from fastapi.testclient import TestClient

from backend.server.app import app
from backend.server.config import trusted_origins

client = TestClient(app)

EVIL = {"Origin": "https://evil.example"}
TRUSTED = {"Origin": "http://localhost:5173"}  # the Vite UI origin


# ── H1: /api/source secret-file lockdown ─────────────────────────────────────

def test_source_rejects_dotfile_env():
    r = client.get("/api/source", params={"file": ".env"})
    assert r.status_code == 403, r.text


def test_source_rejects_gitignore_dotfile():
    r = client.get("/api/source", params={"file": ".gitignore"})
    assert r.status_code == 403


def test_source_rejects_unsupported_type():
    # Dockerfile has no suffix → not a permitted source type.
    r = client.get("/api/source", params={"file": "Dockerfile"})
    assert r.status_code == 403


def test_source_allows_real_source_file():
    r = client.get("/api/source", params={"file": "README.md", "start": 1, "end": 1})
    assert r.status_code == 200
    assert "source" in r.json()


# ── H2: control endpoint CSRF protection ─────────────────────────────────────

def test_control_shutdown_rejects_foreign_origin():
    # _reject_untrusted_origin runs FIRST, so a hostile Origin is rejected with
    # this specific detail — proving the CSRF guard fired (not merely the
    # loopback check). We never POST with a trusted/absent Origin here: that path
    # fires SIGINT into the test process.
    r = client.post("/api/control/shutdown", headers=EVIL)
    assert r.status_code == 403, r.text
    assert r.json().get("detail") == "untrusted origin", r.text


# ── H3: ingest + agent endpoints reject hostile origins, allow native ────────

def test_ingest_rejects_foreign_origin():
    r = client.post("/ingest", json={"narrative": "spoof"}, headers=EVIL)
    assert r.status_code == 403


def test_ingest_allows_no_origin_native_caller():
    # The in-process cognitive loop sends no Origin header → must be accepted.
    r = client.post("/ingest", json={"narrative": "ok"})
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_ingest_allows_trusted_ui_origin():
    r = client.post("/ingest", json={"narrative": "ok"}, headers=TRUSTED)
    assert r.status_code == 200


def test_agent_input_rejects_foreign_origin():
    r = client.post("/api/agent/input", json={"message": "hi"}, headers=EVIL)
    assert r.status_code == 403


def test_agent_input_allows_trusted_ui_origin():
    r = client.post("/api/agent/input", json={"message": "hi"}, headers=TRUSTED)
    assert r.status_code == 200
    assert r.json().get("ok") is True


# ── trusted_origins() shape ──────────────────────────────────────────────────

def test_trusted_origins_includes_vite_ui_and_excludes_evil():
    origins = set(trusted_origins())
    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:5173" in origins
    assert "https://evil.example" not in origins
