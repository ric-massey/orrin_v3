# Track R relationship views (Companion & Presence plan): the theory-of-mind
# projection (R1), the joined real-world action ledger (R2), and the
# body↔machine bridge (R3). All are read-only GET projections and must render
# honest-empty on a fresh instance — the rooms' empty states depend on that.
import json

from fastapi.testclient import TestClient

from backend.server.app import app
from backend.server import state as server_state
from brain.utils import egress
from brain.utils.json_utils import save_json

client = TestClient(app, client=("127.0.0.1", 0))


def test_theory_of_mind_honest_empty():
    save_json(server_state._DATA_DIR / "relationships.json", {})
    r = client.get("/api/theory_of_mind")
    assert r.status_code == 200
    assert r.json() == {"people": []}


def test_theory_of_mind_projects_tom_state_and_excludes_peers():
    save_json(server_state._DATA_DIR / "relationships.json", {
        "Ric": {
            "tom_state": {
                "state_history": [
                    {"state": "curious", "cognitive_state": "task_oriented",
                     "intention": "seeking_information", "ts": "2026-07-09T10:00:00Z"},
                ],
                "belief_model": {"feels_understood": True, "in_alignment": True,
                                 "satisfied_last": None, "consecutive_misalignments": 0,
                                 "belief_discordance": False, "preference_alignment": 0.2},
                "last_prediction": {"intention": "exploring", "family": "explore"},
                "prediction_hits": 3, "prediction_total": 4,
                "prediction_accuracy": 0.75, "synchrony_score": 0.62,
                "misalignment_streak": 0,
            },
        },
        "inner-critic": {"type": "peer", "tom_state": {"state_history": []}},
        "no-model-yet": {"depth": 0.1},
    })
    body = client.get("/api/theory_of_mind").json()
    names = [p["name"] for p in body["people"]]
    assert names == ["Ric"]  # peers and model-less people excluded
    ric = body["people"][0]
    assert ric["current"]["affective_state"] == "curious"
    assert ric["current"]["as_of"] == "2026-07-09T10:00:00Z"  # provenance
    assert ric["belief_model"]["feels_understood"] is True
    assert ric["prediction"]["hits"] == 3 and ric["prediction"]["total"] == 4
    assert ric["synchrony"] == 0.62
    assert len(ric["history"]) == 1


def test_actions_honest_empty():
    for f in ("effect_ledger.jsonl", "egress_log.jsonl"):
        p = server_state._DATA_DIR / f
        if p.exists():
            p.unlink()
    save_json(server_state._DATA_DIR / "presence_notifications.json", [])
    body = client.get("/api/actions").json()
    assert body["actions"] == [] and body["total"] == 0


def test_actions_joins_three_ledgers_time_ordered():
    (server_state._DATA_DIR / "effect_ledger.jsonl").write_text(
        json.dumps({
            "ts": "2026-07-09T10:00:00Z", "cycle": 5, "kind": "note_novel",
            "content_hash": "abc", "novelty": 1.0, "significance": 0.8,
            "goal_id": "g1", "char_len": 300, "dedupe": False,
            "metadata": {"path": "notes/finding.md"},
        }) + "\n",
        encoding="utf-8",
    )
    egress.record("serper")  # now — newest
    save_json(server_state._DATA_DIR / "presence_notifications.json",
              [1751980800.0])  # 2025-07-08T…Z — oldest
    body = client.get("/api/actions").json()
    sources = [a["source"] for a in body["actions"]]
    assert sources == ["egress", "effect", "notification"]  # newest → oldest
    effect = body["actions"][1]
    assert effect["kind"] == "note_novel"
    assert effect["detail"] == "notes/finding.md"
    assert effect["goal_id"] == "g1"
    assert all(a["iso"] for a in body["actions"])


def test_reunion_honest_empty():
    p = server_state._DATA_DIR / "reunion.json"
    if p.exists():
        p.unlink()
    assert client.get("/api/reunion").json() == {}


def test_reunion_returns_the_registered_line():
    save_json(server_state._DATA_DIR / "reunion.json",
              {"text": "I was closed for 3 hours — time passed for me too.",
               "gap_s": 10800.0, "ts": 1752000000.0})
    body = client.get("/api/reunion").json()
    assert body["text"].startswith("I was closed")
    assert body["gap_s"] == 10800.0


def test_body_bridge_honest_empty():
    for f in ("resource_self_monitor.json", "resource_bands.json"):
        p = server_state._DATA_DIR / f
        if p.exists():
            p.unlink()
    body = client.get("/api/body_bridge").json()
    assert body["felt"] == []
    assert body["situations"] == []  # sensory stream not running in tests


def test_body_bridge_joins_felt_state_to_metric_and_band():
    save_json(server_state._DATA_DIR / "resource_self_monitor.json", {
        "body_states": ["heavy", "clear"],
        "vitals": {"rss_mb": 912.0, "cpu_util": 0.12, "fd_pct": 0.02},
        "dominant": "heavy",
        "phase": "wake",
        "somatic_infancy": False,
        "body_converged": 1.0,
    })
    save_json(server_state._DATA_DIR / "resource_bands.json", {
        "fingerprint": "test",
        "bands": {"rss_mb": {"lo": 640.0, "hi": 820.0, "center": 730.0, "_converged": True}},
    })
    body = client.get("/api/body_bridge").json()
    heavy = body["felt"][0]
    assert heavy["state"] == "heavy"
    assert heavy["metric"]["name"] == "rss_mb"
    assert heavy["metric"]["value"] == 912.0
    assert heavy["band"] == {"lo": 640.0, "hi": 820.0, "center": 730.0}
    assert "912" in heavy["because"]  # the join: felt word never ships alone
    clear = body["felt"][1]
    assert clear["state"] == "clear"
    assert clear["because"] == "every vital is inside its learned band"
