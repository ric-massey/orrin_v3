"""
backend/server/schema.py

The canonical shape of a telemetry frame exchanged between the cognitive
architecture (producer, via TelemetryBridge) and the UI (consumers, via the
/ws/telemetry WebSocket).

This module is the SINGLE SOURCE OF TRUTH for the wire contract (Phase 5.2):
  * The pydantic models below define every well-specified frame field.
  * `frontend/src/lib/telemetry.gen.ts` (zod schemas + inferred TS types) is
    GENERATED from these models by `backend/server/generate_telemetry_ts.py`
    (`make telemetry-types`); a drift test fails CI if the committed file is
    stale, so the FE types can no longer be hand-mirrored and silently drift.
  * Both boundaries validate at runtime: the backend producer via
    `validate_frame()` (below, in hub.merge), the frontend consumer via the
    generated zod schema in telemetry.ts.

Everything is optional and merged into a single rolling "latest state" on the
server, so producers can send partial updates (just an affect tick, just a log
line, just the active node) without resending the whole world each time. Models
allow unknown keys (`extra="allow"`) so a new producer field is never rejected
outright — only a genuine TYPE error (a string where a float belongs) trips the
validator.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError
    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover - pydantic always present with fastapi
    BaseModel = object  # type: ignore[assignment,misc]
    ValidationError = Exception  # type: ignore[assignment,misc]
    _HAS_PYDANTIC = False

    def Field(default: Any = None, **_kwargs: Any) -> Any:  # type: ignore[no-redef]
        return default

    def ConfigDict(**_kwargs: Any) -> Any:  # type: ignore[no-redef]
        return {}


# Tolerant config shared by every wire model: unknown keys pass through (a new
# producer field never hard-fails validation), so the validator catches only
# genuine type mismatches.
_WIRE_CONFIG = ConfigDict(extra="allow")


LogLevel = Literal["debug", "info", "warn", "error", "critical"]

# The four canonical loop stages the Brain graph renders.
LOOP_NODES = ("perceive", "reflect", "plan", "act")


class AffectFrame(BaseModel):
    """Real-time affect telemetry, all nominally 0..1."""
    model_config = _WIRE_CONFIG
    valence: Optional[float] = None       # circumplex valence (0 = negative, 1 = positive)
    arousal: Optional[float] = None       # activation level
    homeostasis: Optional[float] = None   # how close the system is to its setpoints (1 = balanced)
    # Free-form extras (e.g. motivation, threat_level) the Brain can also ring.
    extra: Dict[str, float] = Field(default_factory=dict)


class MemoryRecord(BaseModel):
    """One memory read/write the Memory Inspector table displays."""
    model_config = _WIRE_CONFIG
    id: Optional[str] = None
    op: Literal["read", "write"] = "read"
    store: str = "working"                # working | long | episodic | semantic | ...
    key: str = ""
    summary: str = ""
    salience: Optional[float] = None
    ts: Optional[float] = None            # epoch seconds


class LogLine(BaseModel):
    """One console line."""
    model_config = _WIRE_CONFIG
    level: LogLevel = "info"
    source: str = ""
    message: str = ""
    ts: Optional[float] = None


class Goal(BaseModel):
    """One goal row the Goals panel renders (the loop's current goal set)."""
    model_config = _WIRE_CONFIG
    id: Optional[str] = None
    title: str = ""
    status: str = ""
    tier: Optional[str] = None
    priority: Optional[Union[float, str]] = None
    tags: Optional[List[str]] = None
    steps_done: Optional[int] = None
    steps_total: Optional[int] = None
    current_step: Optional[str] = None
    active: Optional[bool] = None
    serves: Optional[str] = None
    aspiration: Optional[bool] = None


class FnEvent(BaseModel):
    """A recent firing of a cognitive function (drives the map's active light)."""
    model_config = _WIRE_CONFIG
    fn: str = ""
    cycle: Optional[int] = None
    reward: Optional[float] = None
    lane: Optional[str] = None             # deliberate | executive


class LlmCost(BaseModel):
    """LLM-cost telemetry: reasoning-cache health + symbolic-vs-LLM gate ratio.

    Producer: brain.loop.telemetry._emit_llm_cost, fed by
    llm_router.cache_stats() (cache_*) and llm_gate.gate_stats() (the gate_*/
    symbolic_ratio counters). Surfaces how much thinking runs cheaply/offline.
    """
    model_config = _WIRE_CONFIG
    # reasoning cache (llm_router.cache_stats)
    cache_entries: Optional[int] = None
    cache_live: Optional[int] = None
    cache_stale: Optional[int] = None
    cache_ttl_s: Optional[float] = None
    # symbolic-vs-LLM gate (llm_gate.gate_stats), session-cumulative
    llm_calls: Optional[int] = None
    symbolic_hits: Optional[int] = None
    total_calls: Optional[int] = None
    symbolic_ratio: Optional[float] = None     # 0..1; fraction answered symbolically


class TelemetryFrame(BaseModel):
    """A partial or full telemetry update. All fields optional.

    This IS the contract (UI_FIXES Fix 7 + Phase 5.2): the hub's latest-wins
    forward list is derived from LATEST_WINS_KEYS below, and
    tests/observability_tests/telemetry_contract_test.py asserts every producer
    keyword in brain/ appears here — so a key can no longer be emitted and
    silently dropped one hop from the browser. The strongly-specified value
    types (affect/memory/logs/goals/fn_recent) are validated and code-generated;
    the free-form blocks (executive/monitor/workspace/interoception) stay
    `Dict[str, Any]` because the producer genuinely does not constrain them.
    """
    model_config = _WIRE_CONFIG
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
    fn_recent: List[FnEvent] = Field(default_factory=list)     # recent function firings
    catalog: Optional[Dict[str, Any]] = None      # function map (pushed once at boot)
    goals: List[Goal] = Field(default_factory=list)            # latest goal set
    executive: Optional[Dict[str, Any]] = None    # §19.1 Executive lane summary (free-form)
    monitor: Optional[Dict[str, Any]] = None      # Monitor breakthroughs + watchdog (free-form)
    workspace: Optional[Dict[str, Any]] = None    # Global Workspace winner (free-form)
    interoception: Optional[Dict[str, Any]] = None  # live per-act cost model (free-form)
    llm_cost: Optional[LlmCost] = None            # reasoning-cache health + symbolic-vs-LLM ratio


# Every wire model, in dependency order — the single list the codegen walks and
# the validator references. (TelemetryFrame last; it references the rest.)
WIRE_MODELS = (AffectFrame, MemoryRecord, LogLine, Goal, FnEvent, LlmCost, TelemetryFrame)


def validate_frame(frame: Dict[str, Any]) -> List[str]:
    """Validate a producer frame against the wire contract WITHOUT mutating or
    rejecting it. Returns a list of human-readable error strings ([] when valid).

    Non-fatal by design: telemetry must never crash the loop, so callers log the
    errors (and may raise under a strict flag) but still forward the raw frame.
    """
    if not _HAS_PYDANTIC or not isinstance(frame, dict):
        return []
    try:
        TelemetryFrame.model_validate(frame)
        return []
    except ValidationError as exc:
        return [
            f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg', '')}"
            for e in exc.errors()
        ]


# The keys the hub treats as latest-wins blobs (overwrite on merge + forward in
# the delta). Single source of truth shared by hub.merge(), the hub's seed
# state, and the contract test. Keys with bespoke merge semantics (goals,
# affect, metrics, memory, logs, extra, node_status, active_node) are handled
# explicitly in hub.merge and are NOT in this tuple.
LATEST_WINS_KEYS = (
    "narrative", "cycle", "active_fn", "active_lane", "fn_recent", "catalog",
    "executive", "monitor", "workspace", "interoception", "llm_cost",
)
