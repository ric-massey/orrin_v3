# brain/cognition/planning/reflection.py
from brain.core.runtime_log import get_logger
import json
from statistics import mean
from datetime import datetime, timezone
from typing import Any, Dict, List

import time as _time

from brain.utils.json_utils import extract_json, load_json  # <-- use helper to read FOCUS_GOAL safely
from brain.utils.log import log_error, log_private
from brain.utils.load_utils import load_all_known_json
from brain.cog_memory.working_memory import update_working_memory
from brain.paths import LOG_FILE, PRIVATE_THOUGHTS_FILE, FOCUS_GOAL
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_underperformer_last_written: dict = {}  # fn_name -> epoch seconds of last LM write
_UNDERPERFORMER_RATE_LIMIT_S = 3600.0   # write at most once per hour per function


def reflect_on_growth_history():
    try:
        data = load_all_known_json() or {}
        evolution_history = data.get("evolution_roadmaps", [])
        next_actions = data.get("next_actions", {})
        self_model = data.get("self_model", {})

        # Load focus goals via helper (path-safe + shape-safe)
        focus_goals = load_json(FOCUS_GOAL, default_type=dict)
        if not isinstance(focus_goals, dict):
            focus_goals = {}

        focus_goal_names: List[str] = []
        som = focus_goals.get("short_or_mid")
        if isinstance(som, dict):
            focus_goal_names.append(som.get("name"))
        lt = focus_goals.get("long_term")
        if isinstance(lt, dict):
            focus_goal_names.append(lt.get("name"))
        focus_goal_text = ", ".join([n for n in focus_goal_names if n]) or "None"

        if not isinstance(evolution_history, list) or not evolution_history:
            update_working_memory("No evolution roadmaps to reflect on yet.")
            return "⚠️ No past evolution roadmaps found."

        # Normalize next_actions to a list of goal dicts
        goals_lists: List[List[Dict[str, Any]]] = []
        if isinstance(next_actions, dict):
            for v in next_actions.values():
                if isinstance(v, list):
                    goals_lists.append([g for g in v if isinstance(g, dict)])
        elif isinstance(next_actions, list):
            goals_lists.append([g for g in next_actions if isinstance(g, dict)])

        # Buckets
        completed: List[str] = []
        still_pending: List[str] = []
        skipped: List[str] = []

        # Quick lookup of active goal names (optional, useful for diagnostics)

        for roadmap in evolution_history:
            if not isinstance(roadmap, dict):
                continue
            steps: List[str] = []
            st = roadmap.get("short_term", [])
            lg = roadmap.get("long_term", [])
            if isinstance(st, list):
                steps.extend(s for s in st if isinstance(s, str))
            if isinstance(lg, list):
                steps.extend(s for s in lg if isinstance(s, str))

            for step in steps:
                matched = False
                for gl in goals_lists:
                    for goal in gl:
                        if goal.get("name") == step:
                            matched = True
                            status = str(goal.get("status", "")).lower()
                            if status == "completed":
                                completed.append(step)
                            elif status == "pending":
                                still_pending.append(step)
                            # other statuses (in_progress/blocked/etc.) aren’t counted here
                            break
                    if matched:
                        break
                if not matched:
                    skipped.append(step)

        agents = self_model.get("internal_agents", [])
        agent_descriptions = "\n".join(
            f"- {a.get('name', 'Unnamed')} ({a.get('role', 'unknown')}, "
            f"values: {', '.join(a.get('values', []) if isinstance(a.get('values'), list) else [])}, "
            f"influence: {a.get('influence_score', 0.5)})"
            for a in agents if isinstance(a, dict)
        ) or "No internal agents defined."

        prompt = (
            f"I am Orrin, a self-evolving AI. I've reviewed {len(evolution_history)} roadmaps.\n\n"
            f"Current focus goals: {focus_goal_text}\n\n"
            f"✅ Completed steps:\n{json.dumps(sorted(set(completed)), ensure_ascii=False, indent=2)}\n\n"
            f"🕒 Still pending:\n{json.dumps(sorted(set(still_pending)), ensure_ascii=False, indent=2)}\n\n"
            f"❌ Skipped:\n{json.dumps(sorted(set(skipped)), ensure_ascii=False, indent=2)}\n\n"
            f"Internal agents:\n{agent_descriptions}\n\n"
            "Why are some goals completed, others abandoned? Which agents influence which outcomes? "
            "Reflect deeply, especially in relation to the current focus goals.\n"
            'Return JSON: { "agent_responses": [], "synthesis": "" }'
        )

        from brain.symbolic.llm_gate import gated_generate
        raw_response = gated_generate(prompt, caller="reflect_on_growth_history", outcome=0.65)
        try:
            result = extract_json(raw_response or "")
            if not isinstance(result, dict) or "synthesis" not in result:
                raise ValueError("Malformed JSON structure from model.")
        except Exception as parse_error:
            log_error(f"[reflect_on_growth_history] Failed to extract JSON: {parse_error}")
            result = {"agent_responses": [], "synthesis": "⚠️ Failed to parse reflection."}

        summary = (
            "🧠 Evolution Summary:\n"
            f"- Completed: {len(set(completed))}\n"
            f"- Pending: {len(set(still_pending))}\n"
            f"- Skipped: {len(set(skipped))}"
        )

        update_working_memory("🪞 Growth history reflection:\n" + (result.get("synthesis") or summary))

        # Write to private thoughts (keep your existing multi-line style if you prefer;
        # otherwise switch to one-line entries to be parser-friendly)
        with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now(timezone.utc)}] Orrin reviewed his growth history:\n")
            f.write(summary + "\n" + json.dumps(result, ensure_ascii=False, indent=2))

        return "✅ Advanced growth reflection complete."

    except Exception as e:
        log_error(f"reflect_on_growth_history ERROR: {e}")
        update_working_memory("❌ Growth reflection failed due to internal error.")
        return "❌ Failed to reflect on growth history."


def reflect_on_missed_goals():
    try:
        data = load_all_known_json() or {}
        goals = data.get("next_actions", {})
        short_term_goals = goals.get("short_term", []) if isinstance(goals, dict) else []

        missed_goals = [
            g for g in short_term_goals
            if isinstance(g, dict) and g.get("status") == "missed"
        ]

        if not missed_goals:
            update_working_memory("No missed goals to reflect on.")
            return "✅ No missed goals found."

        instructions = (
            "I have missed the following short-term goals:\n"
            f"{json.dumps(missed_goals, ensure_ascii=False, indent=2)}\n\n"
            "Reflect on why they were missed:\n"
            "- Were they vague, overreaching, emotionally avoided?\n"
            "- Did other agents sabotage them or did I lack clarity/motivation?\n"
            "Be honest. Suggest changes in planning, mindset, or structure.\n"
        )

        from brain.symbolic.llm_gate import gated_generate
        response = gated_generate(instructions, caller="reflect_on_missed_goals", outcome=0.65)

        if not response or not isinstance(response, str) or len(response.strip()) < 5:
            update_working_memory("⚠️ No valid reflection received on missed goals.")
            log_error("reflect_on_missed_goals: Model response was empty or malformed.")
            return "❌ No useful response from model."

        timestamp = datetime.now(timezone.utc)
        log_entry = f"[{timestamp}] Missed goal reflection:\n{response.strip()}\n"

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + log_entry)
        with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + log_entry)

        update_working_memory("🧩 Missed goal reflection complete.")
        return "✅ Missed goal reflection saved."

    except Exception as e:
        log_error(f"reflect_on_missed_goals ERROR: {e}")
        update_working_memory("⚠️ Missed goal reflection failed.")
        return "❌ Error reflecting on missed goals."


def reflect_on_effectiveness(log: bool = True):
    try:
        data = load_all_known_json() or {}
        long_memory = data.get("long_memory", [])
        if not isinstance(long_memory, list):
            log_error("⚠️ Invalid long_memory structure in data.")
            return {}

        scores: Dict[str, List[float]] = {}
        for entry in long_memory:
            if not isinstance(entry, dict):
                continue
            ref = entry.get("goal_ref")
            score = entry.get("effectiveness_score", 5)
            if isinstance(ref, str) and isinstance(score, (int, float)):
                scores.setdefault(ref, []).append(float(score))

        avg_scores = {ref: round(mean(vals), 2) for ref, vals in scores.items() if len(vals) >= 3}
        if not avg_scores:
            if log:
                log_private("📉 No goals had 3+ effectiveness scores. Skipping reflection.")
                update_working_memory("⚠️ Not enough data for goal effectiveness reflection.")
            return {}

        sorted_scores = dict(sorted(avg_scores.items(), key=lambda x: x[1], reverse=True))
        if log:
            log_lines = [f"- {ref}: {score}" for ref, score in sorted_scores.items()]
            log_private("📈 Effectiveness reflection:\n" + "\n".join(log_lines))
            update_working_memory("🧮 Orrin reflected on goal effectiveness.")
        return sorted_scores

    except Exception as e:
        log_error(f"reflect_on_effectiveness ERROR: {e}")
        update_working_memory("❌ Goal effectiveness reflection failed.")
        return {}


def record_decision(fn_name, reason, *, reward=None, context=None):
    log_private(f"decision: {fn_name} — {reason}")

    if reward is None:
        return

    try:
        from brain.paths import DECISION_STATS_FILE
        from brain.utils.json_utils import load_json as _lj, save_json as _sj
        from brain.cog_memory.working_memory import update_working_memory as _uwm

        stats = _lj(DECISION_STATS_FILE, default_type=dict) or {}
        entry = stats.get(fn_name) or {"count": 0, "total_reward": 0.0, "avg_reward": 0.0}
        entry["count"] += 1
        entry["total_reward"] = float(entry.get("total_reward", 0.0)) + float(reward)
        entry["avg_reward"] = entry["total_reward"] / entry["count"]
        stats[fn_name] = entry
        _sj(DECISION_STATS_FILE, stats)

        # Flag consistent underperformers so Orrin can notice and deprioritise them
        if entry["count"] >= 10 and entry["avg_reward"] < 0.25:
            _now = _time.monotonic()
            _last = _underperformer_last_written.get(fn_name, 0.0)
            if _now - _last >= _UNDERPERFORMER_RATE_LIMIT_S:
                _underperformer_last_written[fn_name] = _now
                insight = (
                    f"⚠️ '{fn_name}' is underperforming: "
                    f"avg reward {entry['avg_reward']:.2f} over {entry['count']} uses."
                )
                log_private(insight)
                _uwm({"content": insight, "event_type": "decision_insight", "importance": 3, "priority": 2})
                try:
                    from brain.cog_memory.long_memory import update_long_memory as _ulm
                    _ulm(insight, emotion="concern", event_type="decision_underperformer", importance=3)
                except Exception as _e:
                    record_failure("reflection.record_decision", _e)
    except Exception as _e:
        log_error(f"record_decision stats failed: {_e}")