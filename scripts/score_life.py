"""Score a life against the Run 14 gate's read-side rows (NEXT_RUN_TESTS.md):
feed (B11, B20, B6, B5, B13), memory (B1, B3), selection (R1, monopoly, F1, B7)
and the learning contract (F2, F3, F4, A1).

    python3 scripts/score_life.py <life dir>     # the dir holding data/ and state/

Built for the 2026-11-02 smoke life, which ran with ORRIN_DATA_DIR / ORRIN_STATE_DIR
pointed at <life dir>/data and <life dir>/state. For a life run in place, pass a
dir with data -> brain/data and state -> the daemon tree. Reads only.
"""
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

L = Path(sys.argv[1])
D, ST = L / "data", L / "state"
repo = Path.home() / "orrin_v3"


def j(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default


def ts(s):
    return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))


act = (D / "activity_log.txt").read_text(errors="replace")
priv = (D / "private_thoughts.txt").read_text(errors="replace") if (D / "private_thoughts.txt").exists() else ""
out = {}

# ── shape ────────────────────────────────────────────────────────────────
out["cycles"] = (j(D / "cycle_count.json") or {}).get("count")
out["llm_blocked_lines"] = len(re.findall(r"\[ask_llm\] Blocked", act + priv))

# ── daemon WAL (B11, B20, B6, B5) ────────────────────────────────────────
rows = [json.loads(l) for l in (ST / "goals" / "wal.log").read_text().splitlines() if l.strip()]
goals = {}
times = []
for r in rows:
    if r.get("ts"):
        times.append(ts(r["ts"]))
    if r.get("type") == "goal_upsert":
        goals[r["goal"]["id"]] = r["goal"]
kinds = collections.Counter(g.get("kind") for g in goals.values())
status = collections.Counter(g.get("status") for g in goals.values())
goal_rows = [r for r in rows if r.get("type") == "goal_upsert"]
char_rows = sum(1 for r in goal_rows if r["goal"].get("kind") == "characterize")
out["daemon_goals"] = len(goals)
out["daemon_kinds"] = dict(kinds)
out["daemon_status"] = dict(status)
out["daemon_errors"] = dict(collections.Counter(g.get("last_error") for g in goals.values() if g.get("last_error")))
out["B11_characterize_share_of_goal_rows"] = round(char_rows / max(1, len(goal_rows)), 3)
# the repair line, not check_orphaned_commitments (a function name that matches "orphan")
out["B11_orphan_running_repairs"] = sum(
    1 for line in (act + priv).splitlines()
    if re.search(r"orphan.*(RUNNING|repair)|(repair|reset).*orphan", line, re.I)
    and "check_orphaned" not in line)
answers = [g for g in goals.values() if str(g.get("title", "")).startswith("Answer:")]
out["B20_answer_goals"] = len(answers)
out["B20_answer_goals_failed_unreachable"] = sum(1 for g in answers if g.get("status") == "FAILED" and "unreachable" in str(g.get("last_error", "")).lower())
times.sort()
gaps = [(b - a).total_seconds() / 60 for a, b in zip(times, times[1:])]
out["B6_longest_wal_silence_min"] = round(max(gaps), 1) if gaps else None
rounds = [int(m) for m in re.findall(r"round (\d+)", " ".join(str(g.get("title", "")) for g in goals.values()))]
out["B5_max_follow_on_round"] = max(rounds) if rounds else 0
out["B6_neighbour_topic_lines"] = len(re.findall(r"neighbou?r", act + priv, re.I))

# ── selection (R1, monopoly, F1, B7) ─────────────────────────────────────
ds = j(D / "decision_stats.json", {}) or {}
total = sum(int(v.get("count", 0)) for v in ds.values() if isinstance(v, dict))
top = sorted(((v.get("count", 0), k) for k, v in ds.items() if isinstance(v, dict)), reverse=True)[:6]
out["picks_total"] = total
out["top_picks"] = [(k, c, round(c / max(1, total), 3)) for c, k in top]
sys.path.insert(0, str(repo))
manifest = set(json.loads((repo / "brain/data/capability_descriptions.json").read_text()))
src = (repo / "brain/think/think_utils/selection/candidates.py").read_text()
blk = src[src.index("_DECLARED_WITHOUT_DESCRIPTION: frozenset[str] = frozenset({"):]
extra = set(re.findall(r'"([a-z_]+)"', blk[: blk.index("})")]))
undeclared = {k: v.get("count") for k, v in ds.items() if isinstance(v, dict) and k not in manifest | extra}
out["R1_undeclared_picks"] = undeclared
ema = j(D / "action_reward_ema.json", {}) or {}
out["F1_ema_assess_goal_progress"] = ema.get("assess_goal_progress")
out["F1_ema_top"] = sorted(((round(v, 3), k) for k, v in ema.items() if isinstance(v, (int, float)) and k != "cycle"), reverse=True)[:5]
rt = ds.get("research_topic") or {}
out["B7_research_topic"] = {"count": rt.get("count"), "avg_reward": round(rt.get("avg_reward", 0), 3)}

# ── F2: history rows carry their own reward ──────────────────────────────
ch = j(D / "cognition_history.json", []) or []
delib = [r for r in ch if r.get("lane") == "deliberate"]
out["F2_history_rows"] = len(delib)
out["F2_rows_with_executed_override"] = sum(1 for r in delib if r.get("executed"))
out["F2_rows_satisfaction_fallback"] = sum(1 for r in delib if r.get("reward_source") == "satisfaction")
out["F2_rows_missing_reward"] = sum(1 for r in delib if r.get("reward") is None)

# ── F3: the signal map holds values ──────────────────────────────────────
sfm = {k: v for k, v in (j(D / "signal_function_map.json", {}) or {}).items() if isinstance(v, dict)}
out["F3_functions_per_signal"] = {k: len(v) for k, v in sfm.items()}
out["F3_negative_values"] = sum(1 for v in sfm.values() for x in v.values() if isinstance(x, (int, float)) and x < 0)

# ── F4 / A1: answers ─────────────────────────────────────────────────────
aq = j(D / "answered_questions.json", []) or []
out["answered_questions"] = len(aq)
out["F4_topic_recurrences"] = sum(int(r.get("topic_recurrences", 0) or 0) for r in aq)
out["A1_informed"] = sum(int(r.get("informed", 0) or 0) for r in aq)
out["A1_decisions_changed"] = sum(int(r.get("decisions_changed", 0) or 0) for r in aq)
out["A1_rows"] = [{k: r.get(k) for k in ("question", "answer", "informed", "decisions_changed")} for r in aq if r.get("informed")]

# ── B3: memory about his world ───────────────────────────────────────────
ltm = j(D / "long_memory.json", []) or []
et = collections.Counter(str(e.get("event_type")) for e in ltm if isinstance(e, dict))
out["ltm_rows"] = len(ltm)
out["ltm_event_types_top"] = et.most_common(8)
summ = sum(1 for e in ltm if isinstance(e, dict) and "Working memory summary" in str(e.get("content", "")))
out["B1_B3_selflog_summary_share"] = round(summ / max(1, len(ltm)), 3)
out["B1_chose_rows"] = sum(1 for e in ltm if isinstance(e, dict) and "🧠 Chose:" in str(e.get("content", "")))
try:  # the code's own test for "about his world" (needs brain importable)
    from brain.cog_memory.long_memory import is_world_finding
    out["B3_world_finding_share"] = round(sum(1 for e in ltm if isinstance(e, dict) and is_world_finding(e)) / max(1, len(ltm)), 3)
except Exception as exc:
    out["B3_world_finding_share"] = f"unavailable: {exc}"
out["B13_generation_skip_lines"] = len(re.findall(r"open action debt|intrinsic.*skip", act + priv, re.I))
out["B13_generation_batches"] = act.count("Symbolic goals proposed")

# ── crash / health ───────────────────────────────────────────────────────
stdout = (L / "stdout.txt").read_text(errors="replace") if (L / "stdout.txt").exists() else ""
out["tracebacks_stdout"] = stdout.count("Traceback")
fj = D / "failures.jsonl"
if fj.exists():
    fc = collections.Counter(json.loads(l).get("where") or json.loads(l).get("site") or "?" for l in fj.read_text().splitlines() if l.strip())
    out["failure_sites_top"] = fc.most_common(8)

print(json.dumps(out, indent=1, default=str))
