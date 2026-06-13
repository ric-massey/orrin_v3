# tests/observability_tests/telemetry_contract_test.py
#
# The telemetry contract test (UI_FIXES Fix 7).
#
# Three times the same bug shipped: a producer in brain/ emitted a key via
# tb.update(...) and the hub (or the client mapper) silently dropped it one hop
# from the browser (`active_lane`, `interoception`, `extra`/awareness). This
# test makes a fourth instance impossible to merge quietly:
#
#   1. every keyword passed to a bridge .update(...) anywhere in brain/ must be
#      handled by the hub — either in schema.LATEST_WINS_KEYS (latest-wins
#      forward) or in the explicit bespoke-merge set;
#   2. the hub actually forwards every LATEST_WINS_KEYS key in its delta;
#   3. the client mapper (frontend/src/lib/telemetry.ts) references every
#      LATEST_WINS_KEYS key, so nothing dies in the browser either.
from __future__ import annotations

import ast
import re
from pathlib import Path

from backend.server.schema import LATEST_WINS_KEYS

REPO = Path(__file__).resolve().parents[2]
BRAIN = REPO / "brain"

# Keys hub.merge() handles with bespoke semantics (append rings, merged dicts,
# derived node status) rather than the latest-wins loop.
BESPOKE_KEYS = {
    "goals", "extra", "logs", "memory", "affect", "metrics",
    "node_status", "active_node", "narrative", "cycle",
}
HANDLED = set(LATEST_WINS_KEYS) | BESPOKE_KEYS

# Receivers that are telemetry bridges in brain/ code: `tb`, `_tb_exec`,
# `_tb_mon`, `_tb_io`, … plus direct `get_bridge().update(...)` chains.
_BRIDGE_NAME = re.compile(r"^_*tb(_|\d|$)")


def _bridge_update_keywords() -> dict[str, set[str]]:
    """Scan brain/ for bridge .update(...) calls; return {kwarg: {files}}."""
    found: dict[str, set[str]] = {}
    for py in BRAIN.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text("utf-8"), filename=str(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "update"):
                continue
            recv = node.func.value
            is_bridge = (
                (isinstance(recv, ast.Name) and _BRIDGE_NAME.match(recv.id))
                or (isinstance(recv, ast.Call) and isinstance(recv.func, ast.Name)
                    and recv.func.id in ("get_bridge", "_bridge"))
            )
            if not is_bridge:
                continue
            for kw in node.keywords:
                if kw.arg:  # skip **kwargs splats
                    found.setdefault(kw.arg, set()).add(str(py.relative_to(REPO)))
    return found


def test_every_producer_keyword_is_handled_by_the_hub():
    found = _bridge_update_keywords()
    assert found, "scanner found no bridge .update() calls — receiver pattern broke?"
    dropped = {k: sorted(v) for k, v in found.items() if k not in HANDLED}
    assert not dropped, (
        "These telemetry keys are emitted in brain/ but NOT handled by the hub "
        "(add them to backend/server/schema.py LATEST_WINS_KEYS or hub.merge's "
        f"bespoke handling, and map them in frontend/src/lib/telemetry.ts): {dropped}"
    )


def test_hub_forwards_every_latest_wins_key():
    from backend.server.hub import Hub
    hub = Hub()
    for key in LATEST_WINS_KEYS:
        sentinel = {"probe": key} if key not in ("narrative", "cycle") else key
        delta = hub.merge({key: sentinel})
        assert key in delta, f"hub.merge dropped latest-wins key {key!r}"
        assert hub.state.get(key) == sentinel, f"hub.state not updated for {key!r}"


def test_hub_seeds_every_latest_wins_key():
    from backend.server.hub import Hub
    hub = Hub()
    missing = [k for k in LATEST_WINS_KEYS if k not in hub.state]
    assert not missing, f"hub seed state is missing latest-wins keys: {missing}"


def test_client_mapper_references_every_latest_wins_key():
    ts = (REPO / "frontend" / "src" / "lib" / "telemetry.ts").read_text("utf-8")
    # `catalog` is deliberately NOT consumed over the socket: the Sphere fetches
    # /api/catalog via REST (with live decision-stats merged in) and re-polls it.
    ws_keys = [k for k in LATEST_WINS_KEYS if k != "catalog"]
    missing = [k for k in ws_keys
               if f"f.{k}" not in ts and f"st.{k}" not in ts]
    assert not missing, (
        f"frontend/src/lib/telemetry.ts never maps these forwarded keys "
        f"(they'd be dead on arrival in the browser): {missing}"
    )
