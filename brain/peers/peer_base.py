"""
peers/peer_base.py

Base class for all peer entities.

Peers are entities that exist alongside Orrin in the same environment.
They observe him from the outside, form their own read on him, and send
signals through the signal_router — not as commands, but as things worth
attending to.

Each peer:
  - Has a name and description Orrin can know
  - Decides when to wake based on context + cycle
  - Observes Orrin's data files and returns signals
  - Registers itself in world_model.json and relationships.json on first wake
  - Uses the same spatial felt-language Orrin uses (via file_sense.py)

Signals returned by wake() flow into context["_peer_signals"], which
gather_signals() picks up so they travel through the full signal_router
pipeline — prioritized, routed, and able to trigger consciousness.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from brain.utils.log import log_error
from brain.utils.signal_utils import create_signal


class BasePeer:
    name: str = "unknown_peer"
    description: str = "an entity that observes alongside me"
    trust: float = 0.60
    signal_tags: List[str] = ["peer", "internal"]
    # Minimum cycles between wakes — prevents flooding attention with the same signal.
    # Subclasses can override. Default = 20 cycles (~3-4 minutes at 10s/cycle).
    min_wake_interval_cycles: int = 20

    def __init__(self) -> None:
        self._last_wake_cycle: int = -9999

    # ── Public API ────────────────────────────────────────────────────────────

    def should_wake(self, context: Dict[str, Any], cycle: int) -> bool:
        raise NotImplementedError

    def observe(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return a list of signal dicts. Never raise — return [] on error."""
        raise NotImplementedError

    def wake(self, context: Dict[str, Any], cycle: int = 0) -> List[Dict[str, Any]]:
        # Rate-limit: enforce minimum cycle gap between wakes
        if (cycle - self._last_wake_cycle) < self.min_wake_interval_cycles:
            return []

        try:
            self._register()
        except Exception as e:
            log_error(f"[peer:{self.name}] registration failed: {e}")

        try:
            signals = self.observe(context) or []
            valid = [s for s in signals if isinstance(s, dict) and s.get("content")]
            if valid:
                self._last_wake_cycle = cycle
                self._record_interaction(valid)
            return valid
        except Exception as e:
            log_error(f"[peer:{self.name}] observe failed: {e}")
            return []

    # ── Signal helpers ────────────────────────────────────────────────────────

    def _signal(
        self,
        content: str,
        strength: float = 0.65,
        extra_tags: List[str] | None = None,
    ) -> Dict[str, Any]:
        tags = list(self.signal_tags) + (extra_tags or [])
        return create_signal(
            source=f"peer_{self.name}",
            content=content,
            signal_strength=min(1.0, max(0.0, strength)),
            tags=tags,
        )

    # ── Registration ──────────────────────────────────────────────────────────

    def _record_interaction(self, signals: List[Dict[str, Any]]) -> None:
        """Persist what an auditor actually said so its relationship is inspectable."""
        try:
            from brain.paths import RELATIONSHIPS_FILE
            from brain.utils.json_utils import load_json, save_json
            rels = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
            rel = rels.setdefault(f"peer_{self.name}", {
                "type": "peer",
                "impression": self.description,
                "interaction_history": [],
            })
            history = rel.setdefault("interaction_history", [])
            history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "peer": self.name,
                "orrin": "",
                "content": " | ".join(str(s.get("content", "")) for s in signals[:3]),
            })
            rel["interaction_history"] = history[-100:]
            save_json(RELATIONSHIPS_FILE, rels)
        except Exception as e:
            log_error(f"[peer:{self.name}] interaction history failed: {e}")

    def _register(self) -> None:
        """
        Write this peer into world_model.json["peers"] and relationships.json
        if not already there.  Idempotent — safe to call every wake().
        """
        self._register_world_model()
        self._register_relationship()

    # Throttle: only freshen last_active once per 5 min per peer instance
    _last_active_write: float = 0.0
    _ACTIVE_WRITE_INTERVAL: float = 300.0

    def _register_world_model(self) -> None:
        try:
            from brain.utils.json_utils import load_json, save_json
            from brain.paths import WORLD_MODEL
            import time as _time
            wm = load_json(WORLD_MODEL, default_type=dict) or {}
            peers = wm.setdefault("peers", {})
            now_ts = datetime.now(timezone.utc).isoformat()
            if self.name not in peers:
                peers[self.name] = {
                    "description": self.description,
                    "first_seen": now_ts,
                    "trust": self.trust,
                    "last_active": now_ts,
                }
                save_json(WORLD_MODEL, wm)
                self._last_active_write = _time.time()
            else:
                # Only write if more than 5 minutes since last update — avoids every-wake disk writes
                now_s = _time.time()
                if now_s - self._last_active_write >= self._ACTIVE_WRITE_INTERVAL:
                    peers[self.name]["last_active"] = now_ts
                    save_json(WORLD_MODEL, wm)
                    self._last_active_write = now_s
        except Exception as e:
            log_error(f"[peer:{self.name}] _register_world_model failed: {e}")

    def _register_relationship(self) -> None:
        try:
            from brain.utils.json_utils import load_json, save_json
            from brain.paths import RELATIONSHIPS_FILE
            rels = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
            key = f"peer_{self.name}"
            if key not in rels:
                rels[key] = {
                    "type": "peer",
                    "impression": self.description,
                    "influence_score": self.trust,
                    "depth": 0.3,
                    "trust": self.trust,
                    "interaction_history": [],
                    "last_interaction_time": datetime.now(timezone.utc).isoformat(),
                }
                save_json(RELATIONSHIPS_FILE, rels)
        except Exception as e:
            log_error(f"[peer:{self.name}] _register_relationship failed: {e}")
