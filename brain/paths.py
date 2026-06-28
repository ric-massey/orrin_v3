# paths.py
import os
from pathlib import Path
from typing import Iterable

# ===== Base directories =====
# This is the ONE resolver for the "mind" tree (brain/data, brain/logs,
# brain/think) — env-overridable so tests, tooling, and the packaged desktop app
# can repoint all live state away from the program folder. Every override must be
# set BEFORE this module is imported. Defaults keep the in-repo layout.
ROOT_DIR  = Path(__file__).resolve().parent
_REPO_ROOT = ROOT_DIR.parent
_env_data = os.environ.get("ORRIN_DATA_DIR")
_env_logs = os.environ.get("ORRIN_LOGS_DIR")
_env_think = os.environ.get("ORRIN_THINK_DIR")
DATA_DIR  = Path(_env_data).resolve() if _env_data else ROOT_DIR / "data"
THINK_DIR = Path(_env_think).resolve() if _env_think else ROOT_DIR / "think"
LOGS_DIR  = Path(_env_logs).resolve() if _env_logs else ROOT_DIR / "logs"
TESTS_DIR = ROOT_DIR / "tests"

# The daemon-durability tree (the repo-root `data/` dir: goals WAL, memory WAL,
# media). Distinct from the "mind" above by design (README "Two state trees"), but
# it must relocate together with it. `memory/config.py` and main.py's GOALS dir
# read this same ORRIN_STATE_DIR so all three stay co-located.
_env_state = os.environ.get("ORRIN_STATE_DIR")
STATE_DIR = Path(_env_state).resolve() if _env_state else _REPO_ROOT / "data"
GOALS_DIR = Path(os.environ.get("ORRIN_GOALS_DIR")).resolve() if os.environ.get("ORRIN_GOALS_DIR") else STATE_DIR / "goals"
MEMORY_DIR = STATE_DIR / "memory"
MEDIA_DIR = STATE_DIR / "media"

# Orrin's self-written code (custom cognition + skills) lives WITH the mind in the
# writable data dir, never in the read-only program bundle (§10.1) — so it travels
# with him on export and is reset with the rest of his state. The two subtrees mirror
# the bundled package layout (cognition/custom_cognition, agency/skills); the loader
# in agency/self_code.py creates them, marks them as packages, and wires them onto
# the import path. Creation/markers live in that loader (not the mkdir loop below)
# so import-order and namespace wiring stay in one place.
SELF_CODE_DIR = DATA_DIR / "self_code"
SELF_COGNITION_DIR = SELF_CODE_DIR / "custom_cognition"
SELF_SKILLS_DIR = SELF_CODE_DIR / "skills"

# Ensure folders exist
for d in (DATA_DIR, THINK_DIR, LOGS_DIR, TESTS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def state_roots() -> "dict[str, Path]":
    """The full set of on-disk state roots as one coherent bundle — the single
    place export/import (§9.6), Reset, and first-launch seeding enumerate so no
    tree is ever missed or left inconsistent (§13.3). Program-relative roots
    (inbox/outbox) are included for completeness."""
    return {
        "data": DATA_DIR,        # the mind
        "logs": LOGS_DIR,        # brain logs
        "think": THINK_DIR,      # generated think_module.py
        "self_code": SELF_CODE_DIR,
        "goals": GOALS_DIR,      # goals daemon WAL + snapshots
        "memory": MEMORY_DIR,    # memory daemon WAL
        "media": MEDIA_DIR,      # ingested media
        "inbox": INBOX_DIR,
        "outbox": OUTBOX_DIR,
    }

# ===== Events & Outcome Log =====
EVENTS_FILE = DATA_DIR / "events.jsonl"
TRACE_FILE  = DATA_DIR / "trace.jsonl"
# NOTE: original code had a typo "evnets.json". We keep it for compatibility and add a fixed variant.
EVENTS_LOG = DATA_DIR / "evnets.json"     # legacy filename (typo preserved for compat)

# ===== General/System Files =====
THINK_MODULE_PATH = DATA_DIR / "think_module_text.txt"
PROMPT_FILE = DATA_DIR / "prompt.txt"
LOG_FILE = DATA_DIR / "log.txt"
ERROR_FILE = DATA_DIR / "error_log.txt"
ACTION_FILE = DATA_DIR / "action.json"
PRIVATE_THOUGHTS_FILE = DATA_DIR / "private_thoughts.txt"
ACTIVITY_LOG = DATA_DIR / "activity_log.txt"
MODEL_FAILURE = DATA_DIR / "model_failures.txt"
LAST_ACTIVE_FILE = DATA_DIR / "last_active.json"
REJECTED_THINK_FILE = DATA_DIR / "rejected_think_versions.txt"
CASUAL_RULES = DATA_DIR / "casual_rules.txt"
SANDBOX_LOG = DATA_DIR / "sandbox_log.json"
USER_INPUT = DATA_DIR / "user_input.txt"
LAST_SEEN_USER_INPUT = DATA_DIR / "last_seen_user_input.txt"
LLM_PROMPT = DATA_DIR / "llm_prompt.txt"
BEHAVIORAL_FUNCTIONS_LIST_FILE = DATA_DIR / "behavioral_functions_list.json"
CONTRADICTIONS_FILE = DATA_DIR / "contradictions.json"

# ===== Model/Config/Concepts =====
SELF_MODEL_FILE = DATA_DIR / "identity_state.json"
RELATIONSHIPS_FILE = DATA_DIR / "relationships.json"
MODEL_CONFIG_FILE = DATA_DIR / "model_config.json"
CONCEPTS_FILE = DATA_DIR / "concepts.json"
KNOWLEDGE = DATA_DIR / "knowledge_base.json"

# ===== Cognition =====
THINK_MODULE_PY = THINK_DIR / "think_module.py"
COGNITION_STATE_FILE = DATA_DIR / "cognition_state.json"
COGNITION_HISTORY_FILE = DATA_DIR / "cognition_history.json"
COGN_SCHEDULE_FILE = DATA_DIR / "cognition_schedule.json"
CURIOUS_GEORGE = DATA_DIR / "exploration_drive_threads.json"
WORLD_MODEL_RAW = DATA_DIR / "world_model_raw_response.txt"
WORLD_MODEL_BACKUP = DATA_DIR / "world_model_backup.txt"
WORLD_MODEL = DATA_DIR / "world_model.json"            # embodiment: env perception (CPU, circadian, social)
WORLD_MODEL_ARCHIVE = DATA_DIR / "world_model_archive.json"
SYMBOLIC_WORLD_MODEL = DATA_DIR / "symbolic_world_model.json"  # cognition: entities, relations, facts, beliefs
REFLECTION = DATA_DIR / "reflection_log.json"
ATTENTION_HISTORY = DATA_DIR / "attention_history.json"
COGNITIVE_FUNCTIONS_LIST_FILE = DATA_DIR / "cognitive_functions.json"

# ===== Tools =====
TOOLS_FILE = DATA_DIR / "tools_catalog.json"
TOOL_REQUESTS_FILE = DATA_DIR / "tool_requests.json"

# ===== Memory =====
CORE_MEMORY_FILE = DATA_DIR / "core_memory.json"
LONG_MEMORY_FILE   = DATA_DIR / "long_memory.json"
MEMORY_GRAPH_FILE  = DATA_DIR / "memory_graph.jsonl"
WORKING_MEMORY_FILE = DATA_DIR / "working_memory.json"
CHAT_LOG_FILE = DATA_DIR / "chat_log.json"

# ===== Prompts/Context =====
REF_PROMPTS = DATA_DIR / "prompts.json"
CONTEXT = DATA_DIR / "context.json"

# ===== Goals =====
GOALS_FILE = DATA_DIR / "goals_mem.json"
COMPLETED_GOALS_FILE = DATA_DIR / "comp_goals.json"
RECENTLY_COMPLETED_FILE = DATA_DIR / "recently_completed.json"   # dict {title: ts} cooldown
FOCUS_GOAL = DATA_DIR / "focus_goals.json"
PROPOSED_GOALS = DATA_DIR / "proposed_goals.json"
LIFETIME_GOALS_FILE = DATA_DIR / "lifetime_goals.json"
EVOLUTION_FUTURES = DATA_DIR / "evolution_futures.json"
EVOLUTION_ROADMAPS = DATA_DIR / "evolution_roadmaps.json"

# ===== Feedback/Reward =====
FEEDBACK_LOG = DATA_DIR / "feedback_log.json"
REWARD_TRACE = DATA_DIR / "reward_trace.json"

# ===== Affect =====
SIGNAL_STATE_FILE = DATA_DIR / "control_signals_state.json"
EMOTIONAL_SENSITIVITY_FILE = DATA_DIR / "signal_sensitivity.json"
AFFECT_MODEL_FILE = DATA_DIR / "control_signals_model.json"
AFFECT_DRIFT_FILE = DATA_DIR / "control_signals_drift.json"
CUSTOM_EMOTION = DATA_DIR / "custom_signal.json"
MODE_FILE = DATA_DIR / "mode.json"
SPEAKER_STATE_FILE = DATA_DIR / "speaker_state.json"
AFFECT_FUNCTION_MAP_FILE = DATA_DIR / "control_signals_function_map.json"
SIGNAL_FUNCTION_MAP_FILE = DATA_DIR / "signal_function_map.json"
EMOTION_DRIFT = DATA_DIR / "signal_drift.json"
SANDBOX_TMP_DIR = DATA_DIR / "sandbox_tmp"

# ===== Cycle/Meta =====
CYCLE_COUNT_FILE = DATA_DIR / "cycle_count.json"

# ===== Dreams =====
DREAM_LOG         = DATA_DIR / "idle_consolidation_log.json"

# ===== Death / Continuity =====
FINAL_THOUGHTS    = DATA_DIR / "final_thoughts.json"

# ===== Autobiography =====
AUTOBIOGRAPHY            = DATA_DIR / "run_history.json"
NARRATIVE_PRESSURE_FILE  = DATA_DIR / "narrative_pressure.json"

# ===== Threads of attention =====
THREADS_FILE      = DATA_DIR / "threads.json"

# ===== stagnation_signal log =====
STAGNATION_SIGNAL_LOG       = DATA_DIR / "stagnation_signal_log.json"

# ===== Value revisions =====
VALUE_REVISIONS   = DATA_DIR / "value_revisions.json"

# ===== Known persons (multi-person identity) =====
KNOWN_PERSONS_FILE = DATA_DIR / "known_persons.json"

# ===== Ambient / background thought fragments (DMN equivalent) =====
AMBIENT_FRAGMENTS_FILE = DATA_DIR / "ambient_fragments.json"

# ===== Ruminative thought loops =====
RUMINATION_FILE = DATA_DIR / "rumination_loops.json"

# ===== Felt passage of time =====
TEMPORAL_STATE_FILE  = DATA_DIR / "temporal_state.json"

# ===== Energy mode (activation_level/engagement level with EMA smoothing) =====
ENERGY_MODE_FILE = DATA_DIR / "energy_mode.json"

# ===== Formative tensions =====
TENSIONS_FILE     = DATA_DIR / "tensions.json"

# ===== Temporal pressure =====
SCHEDULED_TASKS_FILE = DATA_DIR / "scheduled_tasks.json"

# ===== Habituation =====
HABITUATION_FILE = DATA_DIR / "habituation.json"

# ===== Opinions =====
OPINIONS_FILE = DATA_DIR / "opinions.json"

# ===== Mood =====
MOOD_FILE = DATA_DIR / "smoothed_state.json"

# ===== Body sense =====
BODY_SENSE_FILE   = DATA_DIR / "resource_self_monitor.json"

# ===== Predictions / surprise =====
PREDICTIONS_FILE  = DATA_DIR / "predictions.json"

# ===== World perception =====
WORLD_PERCEPTION_FILE = DATA_DIR / "world_perception.json"

# ===== Metacognition trace =====
METACOG_LOG       = DATA_DIR / "metacog_log.json"

# ===== Knowledge graph (symbolic + keyword-vector world model) =====
KNOWLEDGE_GRAPH_FILE = DATA_DIR / "knowledge_graph.json"

# ===== Skill synthesis (gap detection + verified skill generation) =====
SKILL_SYNTHESIS_FILE = DATA_DIR / "skill_synthesis.json"

# ===== Active experimentation (hypothesis → test → consolidate) =====
EXPERIMENTS_FILE = DATA_DIR / "experiments.json"

# ===== Symbolic reasoning layer =====
SYMBOLIC_RULES_FILE    = DATA_DIR / "symbolic_rules.json"
CRYSTALLIZED_SKILLS_FILE = DATA_DIR / "crystallized_skills.json"

# ===== Bandit / Learning =====
BANDIT_STATE_FILE = DATA_DIR / "bandit_state.json"

# ===== Evaluator (delayed reward pipeline) =====
EVALUATOR_WAL = DATA_DIR / "evaluator_wal.jsonl"

# ===== Innovation tracking =====
IMPLEMENTED_TOOLS_FILE = DATA_DIR / "implemented_tools.json"

# ===== Decision stats ledger =====
DECISION_STATS_FILE = DATA_DIR / "decision_stats.json"

# ======= Additional paths from the os.path section (compat kept) =======
# Some use different names/casing; preserved to avoid breaking imports.
EMOTIONAL_STATE_JSON = DATA_DIR / "Emotional_state.json"     # note capital E as in original
COMPETENCE_JSON = DATA_DIR / "competence.json"
OUTCOMES_JSON = DATA_DIR / "Outcomes.json"
FEEDBACK_LOG_JSON = FEEDBACK_LOG          # alias — same file
NEUTRAL_REFLECTION_COUNT_JSON = DATA_DIR / "neutral_reflection_count.json"
REWARD_TRACE_JSON = REWARD_TRACE          # alias — same file
DEBUG_FAILED_GOAL_RESPONSE_JSON = ROOT_DIR / "debug_failed_goal_response.json"
FUNCTION_BANDIT_JSON = ROOT_DIR / "function_bandit.json"
GOAL_TRAJECTORY_LOG_JSON = DATA_DIR / "goal_trajectory_log.json"
LONG_JSON = ROOT_DIR / "long.json"
PROMPTS_BACKUP_JSON = ROOT_DIR / "prompts_backup.json"
PROPOSED_TOOLS_JSON = ROOT_DIR / "proposed_tools.json"
SELF_MODEL_BACKUP_JSON = ROOT_DIR / "identity_state_backup.json"
TOOL_CATALOG_JSON = ROOT_DIR / "tool_catalog.json"
TOOL_EVALUATIONS_JSON = ROOT_DIR / "tool_evaluations.json"
WORKING_JSON = ROOT_DIR / "working.json"
WORKING_TEST_JSON = TESTS_DIR / "working.json"
LONG_TEST_JSON = TESTS_DIR / "long.json"
BANDIT_STATE_JSON = DATA_DIR / "bandit_state.json"
CONTRADICTIONS_JSON = DATA_DIR / "contradictions.json"
EVOLUTION_ROADMAPS_JSON = DATA_DIR / "evolution_roadmaps.json"
CHAT_LOG_JSON = TESTS_DIR / "chat_log.json"
LONG_MEMORY_JSON = TESTS_DIR / "long_memory.json"
EMOTION_SENSITIVITY_JSON = DATA_DIR / "signal_sensitivity.json"
STATE_SNAPSHOT_FILE = DATA_DIR / "state_snapshot.json"
MODEL_FAILURES_FILE = DATA_DIR / "model_failures.jsonl"
INCIDENTS_FILE = DATA_DIR / "incidents.jsonl"

# ===== Back-compat aliases (fixes callers with older names) =====
USER_INPUT_FILE = USER_INPUT                      # talk_policy.py expects this name

# ===== Templates kept for format() call sites that expect strings =====
# If some legacy code does: BANDIT_JSON_TEMPLATE.format(ctx='x'), leave these as strings.
BANDIT_JSON_TEMPLATE = str(DATA_DIR / "bandit_{ctx}.json")
CACHE_JSON_TEMPLATE = str(DATA_DIR / "{k}.json")

# ===== Dynamic builders =====
def json_glob_path(pattern: str = "*.json") -> list[Path]:
    """Return all matching JSON files in DATA_DIR."""
    return list(DATA_DIR.glob(pattern))

def json_glob_all() -> list[Path]:
    """Convenience alias for all .json files in ROOT_DIR (legacy behavior used BASE_DIR)."""
    return list(ROOT_DIR.glob("*.json"))

def bandit_path(ctx: str) -> Path:
    """Path to bandit file for a given context."""
    return DATA_DIR / f"bandit_{ctx}.json"

def cache_file(k: str) -> Path:
    """Path to a cache file for a given key."""
    return DATA_DIR / f"{k}.json"

# ===== Inbox / Outbox / Notes =====
INBOX_DIR  = ROOT_DIR.parent / "inbox"
OUTBOX_DIR = ROOT_DIR.parent / "outbox"
NOTES_FILE = OUTBOX_DIR / "notes.json"

# ===== RSS =====
RSS_CACHE_FILE = DATA_DIR / "rss_cache.json"
RSS_FEEDS_FILE = DATA_DIR / "rss_feeds.json"

# ===== Self-belief revision ledger =====
SELF_BELIEF_REVISIONS_FILE = DATA_DIR / "identity_belief_revisions.json"

# ===== Speech learning =====
SPEECH_LOG_FILE    = DATA_DIR / "speech_log.json"       # scored reply history
SPEECH_SCORES_FILE = DATA_DIR / "speech_scores.json"    # construction score averages
SPEECH_SEEDS_FILE  = DATA_DIR / "speech_seeds.json"     # promoted + hand-crafted permanent exemplars

# Ensure inbox/outbox exist
for d in (INBOX_DIR, OUTBOX_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ===== Optional helpers =====
def ensure_files(paths: Iterable[Path]) -> None:
    """Create empty files if they don't exist."""
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.touch()
