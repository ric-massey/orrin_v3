# brain/cognition/reflection/meta_reflect.py
from brain.core.runtime_log import get_logger
import json
from datetime import datetime, timezone

from brain.utils.load_utils import load_all_known_json
from brain.utils.log import log_error, log_private
from brain.cognition.self_state.self_model_conflicts import resolve_conflicts, update_self_model
from brain.cognition.maintenance.self_modeling import self_supervised_repair
from brain.utils.self_model import ensure_self_model_integrity, get_self_model
from brain.cognition.introspection.router import introspect

from brain.paths import PRIVATE_THOUGHTS_FILE, LOG_FILE
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# Reflection triggers handled by the router (ordered for dependency)
_ROUTED_STEPS: list[tuple[str, str]] = [
    ("Cognition Patterns",   "cognition"),
    ("Cognition Rhythm",     "repair"),
    ("Missed Goals",         "missed_goals"),
    ("Rules Used",           "rules"),
    ("Outcome Review",       "outcome"),
    ("Effectiveness",        "effectiveness"),
    ("World Model Update",   "world_model"),
    ("Self-Beliefs",         "self_belief"),
    ("Think Review",         "think"),
]

# Maintenance steps not in the router (no dedup needed — called only from here)
_MAINTENANCE_STEPS: list[tuple[str, object]] = [
    ("Conflict Resolution", resolve_conflicts),
    ("Self-Repair",         self_supervised_repair),
    ("Self-Model Update",   update_self_model),
]


def meta_reflect(context: dict = None):
    log_private("🧠 Running meta-reflection")
    context = context or {}
    reflection_log = []
    try:
        # === Load and merge memory ===
        # MEMORY-LEAK FIX: the old blanket `context.update(load_all_known_json())`
        # dumped EVERY data/*.json into the live context — including context.json
        # itself (→ recursive context["context"] nesting) and large append-only
        # logs/stores. The loop then persisted context each cycle, ballooning
        # context.json to 70 MB and (under the continuous Executive daemon loading
        # it every ~7s) tripping the reaper's memory-leak detector. Exclude those
        # stores; merging the small remainder is harmless and what meta_reflect needs.
        _LEAK_KEYS = {
            "context", "long_memory", "reflection_log", "habituation",
            "cognition_history", "attention_history", "speech_log", "causal_graph",
            "predictions", "knowledge_graph", "symbolic_dream_log",
            "self_improvement_log", "dream_log", "metacog_log", "chat_log",
            "memory_graph", "events", "trace", "telemetry_history",
        }
        full_memory = load_all_known_json()
        context.update({k: v for k, v in full_memory.items() if k not in _LEAK_KEYS})

        # --- Ensure self-model integrity ---
        if "self_model" in context and isinstance(context["self_model"], dict):
            context["self_model"] = ensure_self_model_integrity(context["self_model"])
        else:
            context["self_model"] = ensure_self_model_integrity(get_self_model())

        # === Context Preview ===
        if context:
            reflection_log.append("📥 Context received:")
            for k, v in context.items():
                preview = json.dumps(v, indent=2)[:300] if isinstance(v, (dict, list)) else str(v)
                reflection_log.append(f"- {k}: {preview}")

        # === Symbolic pre-pass (zero LLM) ===
        try:
            from brain.symbolic.symbolic_reflection import symbolic_first_reflection as _sfr, get_reflection_stats as _grs
            from brain.symbolic.symbolic_self_model import build_symbolic_self_model as _bssm
            from brain.symbolic.self_improvement import run_self_improvement as _rsi
            import brain.symbolic.self_improvement as _si_m; _si_m._last_run = 0.0  # allow run in meta
            _ssm = _bssm()
            _si  = _rsi(context)
            _stats = _grs()
            context["_symbolic_self_model"]    = _ssm
            context["_self_improvement"]       = _si
            context["_reflection_stats"]       = _stats
            _sym_summary = _sfr("meta", context=context, data=_ssm)
            if _sym_summary:
                reflection_log.append(f"[symbolic] Meta-insight: {_sym_summary['text'][:200]}")
                context["_symbolic_meta_insight"] = _sym_summary["text"]
        except Exception as _spe:
            reflection_log.append(f"[symbolic pre-pass] skipped: {_spe}")

        # === Routed reflection chain (dedup via router cooldowns) ===
        for label, trigger in _ROUTED_STEPS:
            res = introspect(trigger, context, force=True)
            if res["skipped"]:
                reflection_log.append(f"⏭️ {label}: {res['reason']}")
            else:
                outcome = "completed" if res["reason"] is None else f"error: {res['reason']}"
                reflection_log.append(f"✅ {label} {outcome}.")

        # === Maintenance steps (always run in meta, not in router) ===
        for label, func in _MAINTENANCE_STEPS:
            try:
                func()
                reflection_log.append(f"✅ {label} completed.")
            except Exception as sub_e:
                err_msg = f"⚠️ {label} failed: {sub_e}"
                log_error(err_msg)
                reflection_log.append(err_msg)

        # === Log Results ===
        now = datetime.now(timezone.utc).isoformat()
        with open(LOG_FILE, "a", encoding="utf-8") as f_log:
            f_log.write(f"\n[{now}] ✅ Meta-reflection complete.\n")

        with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f_private:
            f_private.write(f"\n[{now}] 🧠 Orrin meta-reflected:\n")
            f_private.write("\n".join(reflection_log) + "\n")

        log_private("✅ Meta-reflection done.")
        return "\n".join(reflection_log)

    except Exception as e:
        error_message = f"❌ Meta-reflection failed: {e}"
        log_error(error_message)
        try:
            with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now(timezone.utc)}] ⚠️ Meta-reflection failed:\n{error_message}\n")
        except Exception as _e:
            record_failure("meta_reflect.meta_reflect", _e)
        return error_message
