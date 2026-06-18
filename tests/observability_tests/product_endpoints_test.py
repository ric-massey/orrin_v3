# Group E product surfaces (DESKTOP_APP_PLAN Part 9): the net-new read/compose
# endpoints — egress ledger (§9.4), Life Support (§9.10), activity feed (§9.8), boot
# sequence (§9.7), memory ordering (§9.5), and Mind export/import (§9.6).
import io
import importlib
import json
import zipfile

from fastapi.testclient import TestClient

from backend.server.app import app
from brain.utils import egress, prefs

server_app = importlib.import_module("backend.server.app")

# Loopback client: control endpoints (export/import) are localhost-only without a token.
client = TestClient(app, client=("127.0.0.1", 0))


def test_egress_ledger_counts_and_endpoint():
    egress._MEM if False else None  # no-op; ledger is file-backed under the test data dir
    before = client.get("/api/egress").json()["total_requests"]
    egress.record("openai", approx_tokens=50)
    egress.record("serper")
    after = client.get("/api/egress").json()
    assert after["total_requests"] == before + 2
    assert after["services"]["serper"]["requests"] >= 1


def test_life_exposes_felt_only_no_true_lifespan():
    r = client.get("/api/life")
    assert r.status_code == 200
    body = r.json()
    for k in ("cpu", "memory", "storage", "thinking_rate_per_min", "mortality", "interests"):
        assert k in body
    # The true lifespan / noise offset must never appear (felt estimate only).
    assert "lifespan_days" not in r.text and "noise_days" not in r.text


def test_activity_merges_egress_web_visits():
    egress.record("serper")
    egress.record("web")
    r = client.get("/api/activity")
    assert r.status_code == 200
    body = r.json()
    assert "events" in body and "summary" in body
    assert body["summary"].get("web", 0) >= 2


def test_boot_endpoint_shape():
    r = client.get("/api/boot")
    assert r.status_code == 200
    body = r.json()
    assert "events" in body and "ready" in body


def test_memory_importance_order():
    # order=importance must not error and must return the entries envelope.
    r = client.get("/api/memory?store=long&order=importance&n=5")
    assert r.status_code == 200
    assert "entries" in r.json()


def test_prefs_roundtrip_and_finetune_default_off():
    assert prefs.get("allow_finetune") is False
    r = client.post("/api/settings", json={"prefs": {"allow_remote_viewing": True}})
    assert r.status_code == 200
    assert r.json()["prefs"]["allow_remote_viewing"] is True
    # reset for other tests
    client.post("/api/settings", json={"prefs": {"allow_remote_viewing": False}})


def test_mind_export_streams_zip_and_import_refuses_foreign():
    r = client.get("/api/mind/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "meta.json" in names

    # A foreign archive (no meta.json) is refused; the running mind is untouched.
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("hello.txt", "x")
    r2 = client.post("/api/mind/import", content=bad.getvalue(),
                     headers={"Content-Type": "application/zip"})
    assert r2.status_code == 400


def test_cognition_feeds_never_leak_private_thoughts():
    # E1 acceptance (§9.3): the feeds the Cognition view composes must never carry his
    # protected interior. The veil only lifts on death (F2), never for a live Orrin.
    for path in ("/api/self", "/api/consciousness", "/api/drives", "/api/symbolic", "/api/people"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "private_thoughts" not in r.text, path
        assert "final_thoughts" not in r.text, path


def test_belief_revisions_unifies_self_opinion_and_symbolic(tmp_path, monkeypatch):
    monkeypatch.setattr(server_app, "_DATA_DIR", tmp_path)
    (tmp_path / "self_belief_revisions.json").write_text(json.dumps({
        "COGNITIVE": {
            "confidence": 0.8,
            "events": [{"timestamp": "2026-01-01T00:00:00Z", "goal": "tested", "delta": -0.2, "new_confidence": 0.8}],
        }
    }))
    (tmp_path / "opinions.json").write_text(json.dumps([
        {"topic": "tools", "view": "Tools matter.", "confidence": 0.6, "updated_at": "2026-01-01T00:01:00Z", "evidence_count": 2}
    ]))
    (tmp_path / "symbolic_rules.json").write_text(json.dumps([
        {"id": "r1", "conclusion": "A implies B", "hits": 3}
    ]))
    (tmp_path / "rule_revisions.json").write_text(json.dumps([
        {"timestamp": "2026-01-01T00:02:00Z", "rule_id": "r1", "rule_conclusion": "A implies B", "confidence": 0.4},
        {"timestamp": "2026-01-01T00:03:00Z", "rule_id": "r1", "rule_conclusion": "A implies B", "confidence": 0.7},
    ]))

    r = client.get("/api/belief-revisions?n=10")
    assert r.status_code == 200
    body = r.json()
    kinds = {row["kind"] for row in body["revisions"]}
    assert {"self", "opinion", "symbolic_rule"} <= kinds
    assert body["churn"]["self"]["weakened"] == 1
    assert body["churn"]["symbolic_rule"]["strengthened"] == 1
    newest = body["revisions"][0]
    assert newest["kind"] == "symbolic_rule"
    assert newest["old_confidence"] == 0.4
    assert newest["new_confidence"] == 0.7


def test_predictions_exposes_calibration_and_exploration_trends(tmp_path, monkeypatch):
    monkeypatch.setattr(server_app, "_DATA_DIR", tmp_path)
    (tmp_path / "calibration_state.json").write_text(json.dumps({"brier": 0.1, "bias": 0.0, "n": 2}))
    (tmp_path / "prediction_domain_stats.json").write_text(json.dumps({}))
    (tmp_path / "predictions.json").write_text(json.dumps([
        {"confidence": 0.8, "correct": True, "resolved": True, "checked_ts": "2026-01-01T00:00:00Z"},
        {"confidence": 0.7, "correct": False, "resolved": True, "checked_ts": "2026-01-01T00:01:00Z"},
    ]))
    (tmp_path / "trace.jsonl").write_text(
        json.dumps({"chosen": "FN:seek_novelty", "ts": 1}) + "\n" +
        json.dumps({"chosen": "FN:reflect_on_outcomes", "ts": 2}) + "\n"
    )

    r = client.get("/api/predictions?n=5")
    assert r.status_code == 200
    body = r.json()
    assert body["calibration_trend"]
    assert body["exploration"]["explore"] == 1
    assert body["exploration"]["exploit"] == 1
    assert body["exploration"]["ratio"] == 0.5
    assert body["exploration"]["trend"]


def test_learning_exposes_goal_progress_and_rut(tmp_path, monkeypatch):
    monkeypatch.setattr(server_app, "_DATA_DIR", tmp_path)
    (tmp_path / "decision_stats.json").write_text(json.dumps({}))
    (tmp_path / "bandit_state.json").write_text(json.dumps({}))
    (tmp_path / "reward_trace.json").write_text(json.dumps([]))
    (tmp_path / "goals_mem.json").write_text(json.dumps([
        {
            "id": "g1",
            "title": "Build a thing",
            "status": "active",
            "priority": 3,
            "milestones": [{"text": "one", "met": True}, {"text": "two", "met": False}],
        }
    ]))
    (tmp_path / "comp_goals.json").write_text(json.dumps([]))
    (tmp_path / "cognition_state.json").write_text(json.dumps({
        "last_cognition_choice": "seek_novelty",
        "repeat_count": 3,
        "recent_picks": ["look_around", "seek_novelty", "seek_novelty", "seek_novelty"],
    }))

    r = client.get("/api/learning?n=5")
    assert r.status_code == 200
    body = r.json()
    assert body["goal_progress"]["goals"][0]["title"] == "Build a thing"
    assert body["goal_progress"]["milestones_met"] == 1
    assert body["goal_progress"]["milestones_total"] == 2
    assert body["rut"]["function"] == "seek_novelty"
    assert body["rut"]["consecutive"] == 3


def test_mind_export_roundtrips_through_import():
    blob = client.get("/api/mind/export").content
    # Re-importing our own export must succeed (no restart handler registered in tests,
    # so it just restores in place and returns ok).
    r = client.post("/api/mind/import", content=blob, headers={"Content-Type": "application/zip"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_mind_export_meta_carries_state_schema_version():
    # G1 (§10.7): the export must stamp the on-disk STATE schema version so Restore can
    # refuse a mind written by a newer build.
    blob = client.get("/api/mind/export").content
    meta = json.loads(zipfile.ZipFile(io.BytesIO(blob)).read("meta.json"))
    from brain.utils import schema_migration as sm
    assert meta["state_schema_version"] == sm.CURRENT_SCHEMA_VERSION


def test_diagnostics_bundles_logs_and_state_never_memory_or_thoughts():
    # G1 (§10.7): the diagnostics bundle carries operational logs + the lifecycle state
    # tag, and — by allowlist construction — NEVER memory content or private thoughts.
    from paths import DATA_DIR
    (DATA_DIR / "long_memory.json").write_text(json.dumps([{"text": "SECRET-MEMORY"}]))
    (DATA_DIR / "private_thoughts.txt").write_text("SECRET-THOUGHT")
    (DATA_DIR / "error_log.txt").write_text("a real error line")

    r = client.get("/api/diagnostics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert "state.json" in names and "manifest.json" in names
    # The lifecycle state tag is present.
    assert "state" in json.loads(zf.read("state.json")).get("lifecycle", {})
    # The whole bundle must not contain his memory or thoughts.
    blob = r.content
    assert b"SECRET-MEMORY" not in blob
    assert b"SECRET-THOUGHT" not in blob


def test_death_endpoint_refuses_while_alive_then_lifts_veil_on_death():
    # F2 (§10.4): /api/death refuses while alive (the live guarantee is structural),
    # and only once death is recorded does it open his complete interior.
    import json
    from datetime import datetime, timezone, timedelta
    from paths import DATA_DIR

    # Alive → refused.
    (DATA_DIR / "lifespan.json").write_text(json.dumps({
        "born_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        "lifespan_days": 400, "noise_days": 0, "final_thoughts_written": False,
    }))
    assert client.get("/api/death").status_code == 403
    assert client.get("/api/lifecycle").json()["state"] == "alive"

    # Dead → the veil lifts.
    (DATA_DIR / "lifespan.json").write_text(json.dumps({
        "born_at": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(),
        "lifespan_days": 400, "noise_days": 0, "final_thoughts_written": True,
    }))
    (DATA_DIR / "final_thoughts.json").write_text(json.dumps([{"content": "I existed."}]))
    (DATA_DIR / "private_thoughts.txt").write_text("a worry I never said aloud")
    r = client.get("/api/death")
    assert r.status_code == 200
    body = r.json()
    assert "a worry I never said aloud" in body["private_thoughts"]
    assert body["final_thoughts"][0]["content"] == "I existed."
    assert client.get("/api/lifecycle").json()["state"] == "dead"

    # The LIVE read API still refuses the interior even now.
    assert "private_thoughts" not in client.get("/api/self").text

    # Cleanup so other tests see a clean lifespan.
    (DATA_DIR / "lifespan.json").unlink(missing_ok=True)
    (DATA_DIR / "final_thoughts.json").unlink(missing_ok=True)
