from __future__ import annotations
from brain.core.runtime_log import get_logger
from pathlib import Path
from typing import Any, Dict, Callable, Mapping, Tuple, List
from brain.paths import TRACE_FILE
import time
import json

from brain.utils.log import log_model_issue
from brain.utils.json_utils import load_json  # ⬅️ read-only
from brain.paths import COGNITIVE_FUNCTIONS_LIST_FILE, BEHAVIORAL_FUNCTIONS_LIST_FILE

# Registries hold the real callables; we only FILTER by what's in the files.
from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
from brain.registry.behavior_registry import BEHAVIORAL_FUNCTIONS

# Behavior executor
from brain.think.think_utils.action_gate import take_action

# Bandit + features
from brain.think.bandit import contextual_bandit as bandit
from brain.think.think_utils.select_function import extract_features  # NOTE: adds __bias__=1.0
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

Context = Dict[str, Any]
Registry = Dict[str, Callable[..., Any]]
Result = Dict[str, Any]


def emit_trace(**payload) -> None:
    """Append a single JSON line of telemetry to trace.jsonl (never crash)."""
    try:
        payload.setdefault("ts", time.time())
        with open(TRACE_FILE, "a", encoding="utf-8") as _f:
            _f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        from brain.utils.json_utils import cap_jsonl
        cap_jsonl(TRACE_FILE, max_lines=3000)
    except Exception as _e:
        log_model_issue(f"Trace emit failed: {_e}")


def emotional_delta_reward(pre: dict, post: dict) -> float:
    """
    Derive a [0, 1] reward from the change in emotional state caused by a function.
    Positive delta on exploration_drive/confidence/positive_valence/motivation → higher reward.
    Positive delta on impasse_signal/negative_valence/threat_level/social_penalty → lower reward.
    Returns 0.5 when there is no emotional change (neutral signal, not penalty).
    """
    def _get(d: dict, k: str) -> float:
        core = d.get("core_signals") or d
        return float(core.get(k) or 0.0)

    delta_pos = (
        (_get(post, "exploration_drive")   - _get(pre, "exploration_drive"))
      + (_get(post, "confidence")  - _get(pre, "confidence"))
      + (_get(post, "positive_valence")         - _get(pre, "positive_valence"))
      + (_get(post, "motivation")  - _get(pre, "motivation"))
    )
    delta_neg = (
        (_get(post, "impasse_signal") - _get(pre, "impasse_signal"))
      + (_get(post, "negative_valence")     - _get(pre, "negative_valence"))
      + (_get(post, "threat_level")        - _get(pre, "threat_level"))
      + (_get(post, "social_penalty")       - _get(pre, "social_penalty"))
    )
    raw = delta_pos - delta_neg  # roughly [-4, 4]
    return max(0.0, min(1.0, 0.5 + raw * 0.2))


def blend_reward(status_reward: float, emo_reward: float, emo_weight: float = 0.40) -> float:
    """
    Blend outcome-quality reward with emotional delta reward.
    emo_weight lowered from 0.50 → 0.40 now that status_reward is more
    discriminating — the two signals are roughly equal quality, so a slight
    lean toward the observable outcome is appropriate.
    """
    return (1.0 - emo_weight) * status_reward + emo_weight * emo_reward


def compute_reward(result: Any, default_success: bool = False) -> float:
    """
    Map heterogeneous results to a discriminating reward for the bandit.

    The old version returned 1.0 for any status="ok", collapsing all non-crash
    outcomes into the same signal so the bandit could never distinguish a
    productive call from a vacuous one.

    Now:
      - success/ok AND content produced AND something changed  -> 0.85
      - success/ok AND content produced (output-bearing)       -> 0.70
      - success/ok AND explicitly changed=False                -> 0.40
      - success/ok, no further signal                          -> 0.55
      - warning / partial                                      -> 0.35
      - explicit error / failure                               -> 0.05  (not 0.0:
          tiny positive so the bandit doesn't over-penalize exploratory failures)
      - None with default_success                              -> 0.55
    """
    if isinstance(result, Mapping):
        is_ok = result.get("success") is True or result.get("status") == "ok"

        if is_ok:
            # Penalise explicitly no-op results
            if result.get("changed") is False or result.get("no_change") is True:
                return 0.40

            # Check for substantive output in common keys
            content_keys = ("output", "summary", "content", "result", "data", "text", "details", "finding", "observation")
            for ck in content_keys:
                val = result.get(ck)
                if isinstance(val, str) and len(val.strip()) > 40:
                    # Something was actually produced; reward whether it changed state too
                    if result.get("changed") is True or result.get("items_added") or result.get("saved"):
                        return 0.85
                    return 0.70
                if isinstance(val, (list, dict)) and val:
                    return 0.70

            return 0.55  # generic ok, no additional signal

        if result.get("warning") or result.get("partial"):
            return 0.35
        if "error" in result or result.get("success") is False:
            return 0.05
        return 0.30  # unknown shape but not explicitly ok

    if result is None and default_success:
        return 0.55
    if isinstance(result, str):
        # String returns: common for cognition functions
        s = result.strip()
        if s.startswith("❌") or s.startswith("Failed") or "ERROR" in s[:30]:
            return 0.05
        if len(s) > 60:
            return 0.70   # substantive string output
        if len(s) > 10:
            return 0.55
        return 0.30       # trivial / empty string
    return 0.0


def reason_string(result: Any, reward: float, feats: Any, tag: str) -> str:
    """Human-readable reason text for record_decision(). Robust to tuples/non-mappings."""
    if not isinstance(result, Mapping):
        if isinstance(result, tuple):
            result = {"data": list(result), "status": "tuple"}
        else:
            result = {"data": result}

    if result.get("reason"):
        return str(result["reason"])

    status = ""
    if "status" in result:
        status += f" status={result.get('status')!r}"
    if "error" in result:
        status += f" err={result.get('error')!r}"

    feat_hint = ""
    try:
        if isinstance(feats, Mapping):
            keys = list(feats.keys())[:3]
            if keys:
                feat_hint = " " + " ".join(f"{k}={feats[k]!r}" for k in keys)
        else:
            feat_hint = f" feats={type(feats).__name__}"
    except Exception as _e:
        record_failure("loop_helpers.reason_string", _e)
    return f"{tag} reward={reward:.2f}{status}{feat_hint}".strip()


def _extract_callable_from_meta(meta: Any, name: str) -> Callable[..., Any] | None:
    """
    Strict extraction: accept either a callable, or a dict with a callable under 'function'.
    Everything else is logged and ignored.
    """
    if callable(meta):
        return meta
    if isinstance(meta, dict):
        fn = meta.get("function")
        if callable(fn):
            return fn
    if meta is not None:
        log_model_issue(f"Registry entry for '{name}' has invalid shape: {type(meta).__name__}")
    return None


def _load_name_list(path: str) -> List[str]:
    """Load a list of names from JSON; return [] on any problem. Accepts ['name', ...] or [{'name':..., ...}, ...]."""
    try:
        data = load_json(path, default_type=list)
        if not isinstance(data, list):
            return []
        out: List[str] = []
        for x in data:
            if isinstance(x, dict) and "name" in x:
                out.append(str(x["name"]))
            else:
                out.append(str(x))
        return out
    except Exception as exc:  # unexpected read/shape error — record, empty list
        record_failure("loop_helpers.load_names", exc)
        return []


def names(src) -> List[str]:
    """
    Back-compat helper:
      - if src is a registry dict: return sorted keys
      - if src is a path (str/Path): read JSON list (strings or {name,...}) and return names
      - if src is a list: coerce items to names
    """
    # registry mapping
    if isinstance(src, dict):
        return sorted(src.keys())

    # persisted list path or in-memory list
    try:
        if isinstance(src, (str, Path)):
            data = load_json(src, default_type=list)
        else:
            data = src
    except Exception:
        data = []

    out: List[str] = []
    if isinstance(data, list):
        for x in data:
            if isinstance(x, dict) and "name" in x:
                out.append(str(x["name"]))
            else:
                out.append(str(x))
    return sorted(out)


def discover_callable_maps() -> Tuple[Registry, Registry]:
    """
    Read the persisted name lists (JSON) and return {name->callable} maps filtered to those names.
    ⚠️ This function is READ-ONLY with respect to the JSON files; it never writes.
    """
    wanted_cog = set(_load_name_list(COGNITIVE_FUNCTIONS_LIST_FILE))
    wanted_beh = set(_load_name_list(BEHAVIORAL_FUNCTIONS_LIST_FILE))

    cog_map: Registry = {}
    beh_map: Registry = {}

    # Filter cognition callables by persisted list
    if isinstance(COGNITIVE_FUNCTIONS, dict) and wanted_cog:
        for name in wanted_cog:
            meta = COGNITIVE_FUNCTIONS.get(name)
            fn = _extract_callable_from_meta(meta, name)
            if callable(fn):
                cog_map[name] = fn

    # Filter behavior callables by persisted list
    if isinstance(BEHAVIORAL_FUNCTIONS, dict) and wanted_beh:
        for name in wanted_beh:
            meta = BEHAVIORAL_FUNCTIONS.get(name)
            fn = _extract_callable_from_meta(meta, name)
            if callable(fn):
                beh_map[name] = fn

    return cog_map, beh_map


def _call_cognition(fn: Callable[..., Any], name: str, ctx: Context) -> Result:
    """
    Call cognition functions robustly:
      1) If ctx contains explicit __invoke_args / __invoke_kwargs, use them.
      2) Otherwise, auto-fill parameters by name from context (with a few synonyms).
      3) Otherwise, fall back to legacy attempts: fn(ctx), fn(event, ctx), fn(event, ctx, None), fn().
    Returns a dict result; never raises here.
    """
    try:
        import inspect  # local to avoid any import-cycle edge cases
    except Exception:
        inspect = None  # type: ignore[assignment]

    # 0) Explicit args/kwargs provided by the selector/think()
    try:
        if isinstance(ctx.get("__invoke_args"), (list, tuple)) or isinstance(ctx.get("__invoke_kwargs"), dict):
            args = ctx.get("__invoke_args") or ()
            kwargs = ctx.get("__invoke_kwargs") or {}
            out = fn(*args, **kwargs)
            return out if isinstance(out, dict) else {"success": True, "data": out, "status": "ok"}
    except TypeError as _e:
        # signature mismatch; proceed to smart kwargs / legacy attempts
        record_failure("loop_helpers._call_cognition", _e)
    except Exception as e:
        record_failure("loop_helpers._call_cognition.direct", e)
        return {"success": False, "error": str(e), "where": "cognition-call"}

    # 1) Smart keyword auto-fill from context (only if we can inspect the signature)
    if inspect is not None:
        try:
            sig = inspect.signature(fn)
            kw: Dict[str, Any] = {}
            missing_required: List[str] = []

            event = {"type": name, "name": name}

            # common synonyms to help match context keys to parameter names
            synonyms = {
                "tree": ["tree", "goal_tree", "plan_tree"],
                "updated": ["updated", "updated_goal", "goal_updated", "patch", "delta"],
                "goal": ["goal", "committed_goal", "active_goal"],
                "context": ["context", "ctx"],
            }

            def lookup_param(pname: str) -> Any:
                # direct
                if pname in ("ctx", "context"):
                    return ctx
                if pname == "event":
                    return event

                # exact in context
                if pname in ctx:
                    return ctx[pname]

                # look in common subdicts
                for key in ("committed_goal", "goal"):
                    sub = ctx.get(key)
                    if isinstance(sub, dict) and pname in sub:
                        return sub[pname]

                # synonym lookups
                for canon, keys in synonyms.items():
                    if pname == canon:
                        for k in keys:
                            if k in ctx:
                                return ctx[k]
                            for subkey in ("committed_goal", "goal"):
                                sub = ctx.get(subkey)
                                if isinstance(sub, dict) and k in sub:
                                    return sub[k]
                return None

            for p in sig.parameters.values():
                if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                    continue
                val = lookup_param(p.name)
                if val is not None:
                    kw[p.name] = val
                elif p.default is inspect.Parameter.empty:
                    missing_required.append(p.name)

            if not missing_required:
                out = fn(**kw)
                return out if isinstance(out, dict) else {"success": True, "data": out, "status": "ok"}
        except Exception as _e:
            # fall through to legacy attempts
            record_failure("loop_helpers._call_cognition.2", _e)

    # 2) Legacy attempts (back-compat)
    for attempt in (
        lambda: fn(ctx),
        lambda: fn({"type": name, "name": name}, ctx),
        lambda: fn({"type": name, "name": name}, ctx, None),
        lambda: fn(),
    ):
        try:
            out = attempt()
            return out if isinstance(out, dict) else {"success": True, "data": out, "status": "ok"}
        except TypeError:
            continue
        except Exception as e:
            record_failure("loop_helpers._call_cognition.kwargs", e)
            return {"success": False, "error": str(e), "where": "cognition-call"}

    return {"success": False, "error": "no_matching_signature", "where": "cognition-call"}


def execute_action_via_registries(
    action_name: str,
    ctx: Context,
    cog_reg: Registry,
) -> Result:
    """
    Execute a named action:
      - cognitive: call the function (try common signatures)
      - behavior: validate against persisted list, then execute via take_action
    Only accepts a string action_name; anything else is considered a caller bug.
    """
    if not isinstance(action_name, str) or not action_name:
        log_model_issue(f"Invalid selector type for execute_action_via_registries: {type(action_name).__name__}")
        return {"success": False, "error": "invalid selector", "where": "dispatch"}

    if not isinstance(ctx, dict):
        ctx = {}

    # Cognitive path (from provided cog_reg)
    fn = cog_reg.get(action_name)
    if callable(fn):
        res = _call_cognition(fn, action_name, ctx)
        # Tier-3 re-use: a successfully-dispatched cognitive function MAY be one
        # Orrin authored. We only record the name here (no agency import — that
        # would couple think→agency into a cycle); the loop resolves authored
        # artifacts and pays the re-use bonus post-cycle (brain/loop/finalize.py).
        try:
            if isinstance(res, dict) and res.get("success"):
                ctx.setdefault("_dispatched_cog_fns", []).append(action_name)
        except Exception as e:
            record_failure("loop_helpers.note_reuse", e)
        return res

    # Behavior path: validate by the persisted behavior name list only
    behavior_names = set(_load_name_list(BEHAVIORAL_FUNCTIONS_LIST_FILE))
    if action_name in behavior_names:
        try:
            ok = take_action({"type": action_name, "name": action_name}, ctx, ctx.get("speaker"))
            return {"success": bool(ok), "status": "ok" if ok else "fail"}
        except Exception as e:
            record_failure("loop_helpers._call_behavior", e)
            return {"success": False, "error": str(e), "where": "behavior-call"}

    return {"success": False, "error": f"Unknown action '{action_name}'", "where": "dispatch"}


def bandit_learn(
    tag: str,
    ctx: Context,
    reward: float,
    *,
    features: Dict[str, float] | None = None,
    decision_id: str | None = None
) -> Any:
    """
    Update the bandit with extracted features and the reward.
    Returns the features so callers can log them with record_decision.

    Per-cycle prediction error: BEFORE applying the standard TD update we
    snapshot the bandit's current value estimate for `tag` given these
    features, compute pe = actual_reward - expected_reward, then nudge the
    weights by lr*pe*x after the normal update. This is the missing TD
    error term — without it the bandit was learning toward raw reward
    rather than toward the surprise signal.
    """
    feats = features or extract_features(ctx)
    pe = 0.0
    expected = 0.0
    try:
        # === learning-rate gain gate (Yu & Dayan 2005) ===
        # Expected uncertainty raises plasticity — novel/uncertain contexts learn
        # faster. High uncertainty + exploration_drive = "encode deeply" mode.
        # Routine/certain contexts = slow learning (don't overwrite stable knowledge).
        # lr range: 0.06 (certain/routine) → 0.16 (novel/uncertain).
        _lr_gain = 0.10  # default
        try:
            _ue  = ctx.get("affect_state") if ctx else {}
            _uc  = _ue.get("core_signals", _ue) if isinstance(_ue, dict) else {}
            _uncertainty = min(1.0,
                float(_uc.get("uncertainty", 0.05) or 0.05) * 0.55 +
                float(_uc.get("exploration_drive",   0.25) or 0.25) * 0.35
            )
            _lr_gain = round(0.06 + _uncertainty * 0.10, 4)
        except Exception as _e:
            record_failure("loop_helpers.bandit_learn", _e)

        # Use combined update_with_pe: ONE load+save instead of 3 loads + 2 saves.
        # Falls back to separate calls if the method isn't available.
        pe = float(bandit.update_with_pe(tag, feats, reward, lr=_lr_gain))
        expected = float(reward) - pe  # recover expected = reward - pe
        emit_trace(
            type="BANDIT_UPDATE",
            action=tag,
            reward=reward,
            decision_id=decision_id,
            features_on={k: v for k, v in feats.items() if v},
            expected_reward=round(expected, 4),
            prediction_error=round(pe, 4),
            lr_gain=_lr_gain,
        )

        # === Prediction Error → Emotion (Schultz, Dayan & Montague 1997) ===
        # The reward_signal IS the prediction error — not raw reward.
        # reward_signal is NOT "feel good" — it is drive, wanting, incentive salience:
        # the willingness to move toward something (Berridge & Robinson 1998).
        # Positive PE → phasic reward_signal burst → motivation + exploration_drive (more seeking).
        # Negative PE → reward_signal dip → loss of drive + impasse_signal at blocked goal.
        # stability_signal, not reward_signal, underlies hedonic contentment and "feel good."
        # Near-zero PE (as expected) → no signal. Predictable 0.26 rewards teach
        # nothing emotionally — the signal is the SURPRISE, not the value.
        if abs(pe) > 0.05:  # dead-zone: only signal meaningful surprises
            try:
                _emo = ctx.get("affect_state") if ctx else None
                if isinstance(_emo, dict):
                    _core = _emo.get("core_signals") or _emo
                    from brain.affect.homeostasis import pump_signal
                    if pe > 0:
                        # Positive surprise: reward_signal burst → motivation + exploration_drive (wanting more)
                        _mag = min(0.20, pe * 0.4)
                        pump_signal(_core, "motivation",        _mag,        default=0.3)
                        pump_signal(_core, "exploration_drive", _mag * 0.7,  default=0.25)
                        # Confidence as a small downstream effect of successful prediction
                        pump_signal(_core, "confidence",        _mag * 0.25, default=0.45)
                    else:
                        # Negative surprise: reward_signal dip → reduced drive + impasse_signal
                        _mag = min(0.15, abs(pe) * 0.35)
                        pump_signal(_core, "impasse_signal", _mag, default=0.05)
                        pump_signal(_core, "motivation",    -_mag * 0.5, default=0.3)
                    if "core_signals" in _emo:
                        _emo["core_signals"] = _core
                    else:
                        _emo.update(_core)
                    if ctx is not None:
                        ctx["affect_state"] = _emo
            except Exception as _e:
                record_failure("loop_helpers.bandit_learn.2", _e)
    except Exception as _primary_e:
        # AttributeError → legacy bandit fallback (expected on first run).
        # Any other exception (JSONDecodeError, KeyError, etc.) is a real failure
        # and must be surfaced in the trace rather than silently swallowed.
        if isinstance(_primary_e, AttributeError):
            try:
                from brain.utils.context_key import context_key
                from brain.utils.bandit import record_outcome_ctx
                record_outcome_ctx(context_key(ctx), tag, reward)
                emit_trace(type="BANDIT_UPDATE_FALLBACK", action=tag, reward=reward, decision_id=decision_id)
            except Exception as _e:
                emit_trace(
                    type="BANDIT_UPDATE_FAILED",
                    action=tag,
                    reward=reward,
                    decision_id=decision_id,
                    error=str(_e),
                )
        else:
            log_model_issue(f"bandit_learn: unexpected error updating '{tag}': {_primary_e}")
            emit_trace(
                type="BANDIT_UPDATE_FAILED",
                action=tag,
                reward=reward,
                decision_id=decision_id,
                error=str(_primary_e),
            )
    return feats
