"""
backend/server/schema.py

The canonical shape of a telemetry frame exchanged between the cognitive
architecture (producer, via TelemetryBridge) and the UI (consumers, via the
/ws/telemetry WebSocket).

Everything is optional and merged into a single rolling "latest state" on the
server, so producers can send partial updates (just an affect tick, just a log
line, just the active node) without resending the whole world each time.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

try:
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover - pydantic always present with fastapi
    BaseModel = object  # type: ignore

    def Field(default=None, **_kwargs):  # type: ignore
        return default


LogLevel = Literal["debug", "info", "warn", "error", "critical"]

# The four canonical loop stages the Brain graph renders.
LOOP_NODES = ("perceive", "reflect", "plan", "act")


class AffectFrame(BaseModel):
    """Real-time affect telemetry, all nominally 0..1."""
    valence: Optional[float] = None       # circumplex valence (0 = negative, 1 = positive)
    arousal: Optional[float] = None       # activation level
    homeostasis: Optional[float] = None   # how close the system is to its setpoints (1 = balanced)
    # Free-form extras (e.g. motivation, threat_level) the Brain can also ring.
    extra: Dict[str, float] = Field(default_factory=dict)


class MemoryRecord(BaseModel):
    """One memory read/write the Memory Inspector table displays."""
    id: Optional[str] = None
    op: Literal["read", "write"] = "read"
    store: str = "working"                # working | long | episodic | semantic | ...
    key: str = ""
    summary: str = ""
    salience: Optional[float] = None
    ts: Optional[float] = None            # epoch seconds


class LogLine(BaseModel):
    """One console line."""
    level: LogLevel = "info"
    source: str = ""
    message: str = ""
    ts: Optional[float] = None


class TelemetryFrame(BaseModel):
    """A partial or full telemetry update. All fields optional.

    This IS the contract (UI_FIXES Fix 7): the hub's latest-wins forward list is
    derived from LATEST_WINS_KEYS below, and tests/observability_tests/
    telemetry_contract_test.py asserts every producer keyword in brain/ appears
    here — so a key can no longer be emitted and silently dropped one hop from
    the browser (the active_lane / interoception / extra bug class).
    """
    active_node: Optional[str] = None             # one of LOOP_NODES
    node_status: Dict[str, str] = Field(default_factory=dict)  # node -> idle|active|done
    narrative: Optional[str] = None               # human-readable status for the Face
    affect: Optional[AffectFrame] = None
    memory: List[MemoryRecord] = Field(default_factory=list)   # appended to a rolling buffer
    logs: List[LogLine] = Field(default_factory=list)          # appended to a rolling buffer
    metrics: Dict[str, float] = Field(default_factory=dict)    # arbitrary recharts series points
    cycle: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
    # ── Cognitive Map / dual-process additions (post-original four) ──────────
    active_fn: Optional[str] = None               # cognitive function running right now
    active_lane: Optional[str] = None             # deliberate | executive (Gap 3)
    fn_recent: List[Dict[str, Any]] = Field(default_factory=list)  # [{fn, cycle, lane, reward}]
    catalog: Optional[Dict[str, Any]] = None      # function map (pushed once at boot)
    goals: List[Dict[str, Any]] = Field(default_factory=list)      # latest goal set
    executive: Optional[Dict[str, Any]] = None    # §19.1 Executive lane summary
    monitor: Optional[Dict[str, Any]] = None      # Monitor breakthroughs + watchdog
    workspace: Optional[Dict[str, Any]] = None    # Global Workspace winner (+candidates)
    interoception: Optional[Dict[str, Any]] = None  # live per-act cost model (Fix 7)


# The keys the hub treats as latest-wins blobs (overwrite on merge + forward in
# the delta). Single source of truth shared by hub.merge(), the hub's seed
# state, and the contract test. Keys with bespoke merge semantics (goals,
# affect, metrics, memory, logs, extra, node_status, active_node) are handled
# explicitly in hub.merge and are NOT in this tuple.
LATEST_WINS_KEYS = (
    "narrative", "cycle", "active_fn", "active_lane", "fn_recent", "catalog",
    "executive", "monitor", "workspace", "interoception",
)
