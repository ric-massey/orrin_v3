# brain/symbolic/pattern_scorer.py
# Sub-symbolic pattern scoring layer — runs before any symbolic or LLM step.
#
# Five fast components, all local and updatable, no LLM required:
#   1. Pattern familiarity  — token-weighted "have I seen this?" score
#   2. World-model grounding — statistical success rates per domain/event-type
#   3. Emotional valence     — positive/negative/activation_level from state
#   4. Abstraction level     — tactic vs strategy vs principle classifier
#   5. Pattern confidence   — holistic mastery confidence score
#
# Main entry: score_signal(query, context) → signal score dict
# Called from reasoning_router Stage -1, before self_assess() or any rule.
#
# Update hooks (called by other modules after outcomes):
#   update_pattern_weights(domain, tokens, outcome)
#   update_world_model(domain, event_type, success)
#   decay_patterns()   ← called from rule_forgetting.run_forgetting_cycle()
from __future__ import annotations
from brain.core.runtime_log import get_logger

import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from brain.utils.log import log_activity
from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

PATTERN_FILE  = DATA_DIR / "intuition_patterns.json"
WORLD_FILE    = DATA_DIR / "world_model_stats.json"

_DECAY_ALPHA  = 0.995    # per-call weight decay applied during forgetting cycle
_UPDATE_ALPHA = 0.10     # learning rate for pattern weight updates
_MIN_WEIGHT   = 0.005    # prune weights below this threshold
_CACHE_TTL    = 120.0    # seconds before re-reading from disk

_STOPWORDS = frozenset(
    "a an the is are was were be been have has do does did will would "
    "could should may might shall can i me my we our you your it its "
    "this that these those of in on at to for with from by and or not "
    "what how why when where who which".split()
)

_TACTIC_WORDS   = frozenset(
    "fix debug implement run call use apply create add remove update change "
    "set get check load save parse build test deploy execute handle".split()
)
_STRATEGY_WORDS = frozenset(
    "approach plan design structure organize optimize improve balance trade "
    "decide consider prioritize refactor review evaluate compare choose select".split()
)
_PRINCIPLE_WORDS = frozenset(
    "why value belief meaning purpose worth trust principle always never core "
    "fundamental important essential underlying meta abstract general universal".split()
)

# Domains whose pattern weights transfer into each other (bidirectional knowledge sharing)
_DOMAIN_NEIGHBORS: Dict[str, List[str]] = {
    "COGNITIVE":  ["PLANNING", "SYMBOLIC"],
    "PLANNING":   ["COGNITIVE", "TECHNICAL"],
    "TECHNICAL":  ["PLANNING", "SYMBOLIC"],
    "EMOTIONAL":  ["SOCIAL", "COGNITIVE"],
    "SOCIAL":     ["EMOTIONAL", "PLANNING"],
    "SYMBOLIC":   ["COGNITIVE", "TECHNICAL"],
}

_DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "COGNITIVE":  ["think", "reason", "memory", "learning", "cognition", "attention", "pattern", "predict"],
    "PLANNING":   ["goal", "plan", "strategy", "task", "achieve", "objective", "priority", "decompose"],
    "TECHNICAL":  ["code", "error", "debug", "import", "function", "run", "process", "file", "system"],
    "EMOTIONAL":  ["feel", "emotion", "mood", "impasse_signal", "exploration_drive", "motivation", "valence", "affect"],
    "SOCIAL":     ["user", "human", "conversation", "respond", "communicate", "message", "help", "ask"],
    "SYMBOLIC":   ["rule", "analogy", "symbolic", "causal", "graph", "concept", "inference", "router"],
}


# ─── Module-level caches ─────────────────────────────────────────────────────

_patterns:  Optional[Dict[str, Dict[str, float]]] = None
_world:     Optional[Dict[str, Any]] = None
_cache_ts:  float = 0.0


def _load_cache() -> None:
    global _patterns, _world, _cache_ts
    now = time.monotonic()
    if now - _cache_ts < _CACHE_TTL and _patterns is not None:
        return
    try:
        from brain.utils.json_utils import load_json
        _patterns = load_json(PATTERN_FILE, default_type=dict) or {}
        _world    = load_json(WORLD_FILE,   default_type=dict) or {}
    except Exception:
        _patterns = _patterns or {}
        _world    = _world    or {}
    _cache_ts = now


def _save_patterns() -> None:
    global _cache_ts
    try:
        from brain.utils.json_utils import save_json
        save_json(PATTERN_FILE, _patterns)
        _cache_ts = 0.0   # invalidate cache so next read picks up fresh data
    except Exception as _e:
        record_failure("pattern_scorer._save_patterns", _e)


def _save_world() -> None:
    global _cache_ts
    try:
        from brain.utils.json_utils import save_json
        save_json(WORLD_FILE, _world)
        _cache_ts = 0.0
    except Exception as _e:
        record_failure("pattern_scorer._save_world", _e)


# ─── Token utilities (also used by integrating modules via tokenize_query) ───

def _tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-z]{3,}", text.lower())
    return [w for w in words if w not in _STOPWORDS]


def _infer_domain(tokens: List[str]) -> str:
    token_set = set(tokens)
    best_domain, best_score = "GENERAL", 0
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        score = sum(1 for k in keywords if k in token_set)
        if score > best_score:
            best_score  = score
            best_domain = domain
    return best_domain


def tokenize_query(query: str) -> Tuple[List[str], str]:
    """Public helper: tokenize query and infer domain. Used by integrating modules."""
    tokens = _tokenize(query)
    return tokens, _infer_domain(tokens)


# ─── Component 1: Pattern familiarity ────────────────────────────────────────

def _pattern_familiarity(tokens: List[str], domain: str) -> float:
    if not tokens or not _patterns:
        return 0.0

    domain_weights  = _patterns.get(domain, {})
    general_weights = _patterns.get("GENERAL", {})

    # Cross-domain transfer: borrow a fraction of weight from related domains
    neighbor_weights: Dict[str, float] = {}
    for neighbor in _DOMAIN_NEIGHBORS.get(domain, []):
        nbr_dw = _patterns.get(neighbor, {})
        for tok, w in nbr_dw.items():
            if w > neighbor_weights.get(tok, 0.0):
                neighbor_weights[tok] = w

    matched = 0.0
    for tok in tokens:
        d_w = domain_weights.get(tok, 0.0)
        g_w = general_weights.get(tok, 0.0)
        n_w = neighbor_weights.get(tok, 0.0) * 0.25  # neighbors contribute at 25%
        matched += min(d_w + 0.5 * g_w + n_w, 1.0)

    raw = matched / len(tokens)
    # Sigmoid: 0.35 maps to ~0.5 so mid-coverage feels moderate
    return 1.0 / (1.0 + math.exp(-8.0 * (raw - 0.35)))


# ─── Component 2: World-model grounding ──────────────────────────────────────

def _grounding_score(domain: str) -> float:
    if not _world:
        return 0.5

    stats = _world.get(domain, {})
    if not isinstance(stats, dict):
        return 0.5

    rule_hits    = float(stats.get("rule_hits",    0))
    rule_total   = float(stats.get("rule_total",   1))
    pred_correct = float(stats.get("pred_correct", 0))
    pred_total   = float(stats.get("pred_total",   1))
    exp_success  = float(stats.get("exp_success",  0))
    exp_total    = float(stats.get("exp_total",    1))

    rule_rate = rule_hits    / max(rule_total, 1)
    pred_rate = pred_correct / max(pred_total, 1)
    exp_rate  = exp_success  / max(exp_total,  1)

    # Weighted score; shrinks toward 0.5 until we accumulate enough data
    data_weight = min((rule_total + pred_total + exp_total) / 20.0, 1.0)
    score = 0.50 * rule_rate + 0.30 * pred_rate + 0.20 * exp_rate
    return 0.5 + (score - 0.5) * data_weight


# ─── Component 3: Emotional valence ──────────────────────────────────────────

def _signal_valence(query: str, context: Dict) -> Tuple[float, float]:
    """
    Fast valence and activation_level from current emotional state.
    valence: -1.0 (aversive) → +1.0 (appetitive)
    activation_level:  0.0 (calm)     → +1.0 (high activation)
    """
    valence = 0.0
    activation_level = 0.0
    try:
        emo  = context.get("affect_state") or {}
        core = emo.get("core_signals", {}) if isinstance(emo, dict) else {}
        if isinstance(core, dict):
            exploration_drive   = float(core.get("exploration_drive",   0.0))
            impasse_signal = float(core.get("impasse_signal", 0.0))
            motivation  = float(core.get("motivation",  0.5))
            excitement  = float(core.get("excitement",  0.0))
            valence = exploration_drive * 0.4 + motivation * 0.3 + excitement * 0.2 - impasse_signal * 0.5
            activation_level = exploration_drive * 0.3 + excitement * 0.4 + impasse_signal * 0.3

        # Goal-proximity bonus: query overlap with current goal → positive valence
        focus = context.get("focus_goal") or context.get("committed_goal")
        if isinstance(focus, dict):
            goal_text = str(focus.get("intent", "") or focus.get("name", "")).lower()
            overlap = sum(1 for w in goal_text.split() if len(w) > 3 and w in query.lower())
            if overlap:
                valence += 0.15 * min(overlap, 3)

        valence = max(-1.0, min(1.0, valence))
        activation_level = max(0.0,  min(1.0, activation_level))
    except Exception as _e:
        record_failure("pattern_scorer._signal_valence", _e)

    return valence, activation_level


# ─── Component 4: Abstraction level ──────────────────────────────────────────

def _classify_abstraction(query: str, tokens: List[str]) -> str:
    token_set = set(tokens)

    tactic_s    = sum(1 for w in _TACTIC_WORDS   if w in token_set)
    strategy_s  = sum(1 for w in _STRATEGY_WORDS if w in token_set)
    principle_s = sum(1 for w in _PRINCIPLE_WORDS if w in token_set)

    q = query.lower()
    # Question-word heuristics carry strong weight (3 pts) — checked before length bias
    if any(q.startswith(p) for p in ("why", "what does it mean", "what is the purpose", "is it worth", "does it matter")):
        principle_s += 3
    elif any(q.startswith(p) for p in ("when", "should i", "which approach", "what approach", "best way")):
        strategy_s  += 3
    elif any(q.startswith(p) for p in ("how", "fix", "debug", "create", "add", "run", "implement")):
        tactic_s    += 3

    # Length bias only kicks in when no question-word heuristic fired (2 pts, weaker)
    length = len(tokens)
    if principle_s == 0 and strategy_s == 0 and tactic_s == 0:
        if length <= 4:
            tactic_s    += 2
        elif length >= 12:
            principle_s += 2

    scores = {"tactic": tactic_s, "strategy": strategy_s, "principle": principle_s}
    return max(scores, key=lambda k: scores[k])


# ─── Component 5: Pattern confidence ────────────────────────────────────────────

def _compute_pattern_confidence(familiarity: float, grounding: float, domain: str, context: Dict) -> float:
    """
    Holistic pattern mastery confidence — computed from familiarity + grounding data.
    """
    base = 0.55 * familiarity + 0.45 * grounding

    # Boost from recent successful firings in this domain
    recent_firings = context.get("_recent_rule_firings", [])
    if isinstance(recent_firings, list):
        domain_hits = sum(
            1 for f in recent_firings
            if isinstance(f, dict) and domain in str(f.get("rule_id", "")).upper()
        )
        base += 0.05 * min(domain_hits, 4)

    # Shrink toward 0.5 when pattern data is sparse
    domain_tokens  = (_patterns or {}).get(domain, {})
    data_confidence = min(len(domain_tokens) / 30.0, 1.0)
    intuited = 0.5 + (base - 0.5) * data_confidence

    return max(0.0, min(1.0, intuited))


# ─── Main entry point ─────────────────────────────────────────────────────────

def score_signal(query: str, context: Optional[Dict] = None) -> Dict:
    """
    Run all five pattern scoring components and return a consolidated result dict.

    Returns:
        familiarity_score  float  0-1    how pattern-familiar the query is
        grounding_score    float  0-1    world-model statistical reliability
        valence            float  -1..1  valence from emotional state
        activation_level            float  0-1    activation level
        abstraction_level  str          "tactic" | "strategy" | "principle"
        reasoning_depth    str          "fast" | "medium" | "deep"
        pattern_confidence float  0-1    computed mastery confidence
        domain             str          inferred domain label
        label              str          classification label
    """
    ctx = context if context is not None else {}
    _load_cache()

    tokens      = _tokenize(query)
    domain      = _infer_domain(tokens)
    familiarity = _pattern_familiarity(tokens, domain)
    grounding   = _grounding_score(domain)
    valence, activation_level = _signal_valence(query, ctx)
    abstraction = _classify_abstraction(query, tokens)
    confidence  = _compute_pattern_confidence(familiarity, grounding, domain, ctx)

    depth_map = {"tactic": "fast", "strategy": "medium", "principle": "deep"}
    depth = depth_map[abstraction]

    if confidence >= 0.70 and familiarity >= 0.60:
        label = "pattern_recognized"
    elif confidence < 0.30 and familiarity < 0.25:
        label = "pattern_unrecognized"
    elif valence < -0.20:
        label = "aversive_query"
    elif activation_level > 0.60:
        label = "high_engagement"
    else:
        label = "moderate_familiarity"

    result = {
        "familiarity_score": round(familiarity, 3),
        "grounding_score":   round(grounding,   3),
        "valence":           round(valence,     3),
        "activation_level":           round(activation_level,     3),
        "abstraction_level": abstraction,
        "reasoning_depth":   depth,
        "pattern_confidence":   round(confidence,  3),
        "domain":            domain,
        "label":             label,
    }

    log_activity(
        f"[pattern_scorer] {domain}/{abstraction}/{label} "
        f"fam={familiarity:.2f} grd={grounding:.2f} "
        f"val={valence:+.2f} conf={confidence:.2f}"
    )
    return result


# ─── Update functions ─────────────────────────────────────────────────────────

def update_pattern_weights(domain: str, tokens: List[str], outcome: float) -> None:
    """
    Reinforce (outcome→1.0) or weaken (outcome→0.0) pattern token weights.
    Called from rule_verifier.apply_outcome() and autonomous_experiment.
    """
    global _patterns
    _load_cache()
    if _patterns is None:
        _patterns = {}

    dw = _patterns.setdefault(domain,    {})
    gw = _patterns.setdefault("GENERAL", {})

    for tok in tokens:
        if not tok:
            continue
        old_d = dw.get(tok, 0.0)
        new_d = old_d + _UPDATE_ALPHA * (outcome - old_d)
        if new_d < _MIN_WEIGHT:
            dw.pop(tok, None)
        else:
            dw[tok] = round(new_d, 4)

        old_g = gw.get(tok, 0.0)
        new_g = old_g + (_UPDATE_ALPHA * 0.3) * (outcome - old_g)
        if new_g < _MIN_WEIGHT:
            gw.pop(tok, None)
        else:
            gw[tok] = round(new_g, 4)

    _patterns[domain]    = dw
    _patterns["GENERAL"] = gw
    _save_patterns()


def update_world_model(domain: str, event_type: str, success: bool) -> None:
    """
    Record an outcome event in world-model stats.
    event_type: "rule" | "prediction" | "experiment"
    """
    global _world
    _load_cache()
    if _world is None:
        _world = {}

    stats = _world.setdefault(domain, {})
    if event_type == "rule":
        stats["rule_total"] = stats.get("rule_total", 0) + 1
        if success:
            stats["rule_hits"] = stats.get("rule_hits", 0) + 1
    elif event_type == "prediction":
        stats["pred_total"] = stats.get("pred_total", 0) + 1
        if success:
            stats["pred_correct"] = stats.get("pred_correct", 0) + 1
    elif event_type == "experiment":
        stats["exp_total"] = stats.get("exp_total", 0) + 1
        if success:
            stats["exp_success"] = stats.get("exp_success", 0) + 1

    _world[domain] = stats
    _save_world()


def decay_patterns(alpha: float = _DECAY_ALPHA) -> int:
    """
    Apply multiplicative weight decay to all pattern tokens.
    Called from rule_forgetting.run_forgetting_cycle(). Returns pruned count.
    """
    global _patterns
    _load_cache()
    if not _patterns:
        return 0

    pruned = 0
    for domain in list(_patterns.keys()):
        dw = _patterns[domain]
        for tok in list(dw.keys()):
            new_w = dw[tok] * alpha
            if new_w < _MIN_WEIGHT:
                del dw[tok]
                pruned += 1
            else:
                dw[tok] = round(new_w, 4)

    _save_patterns()
    return pruned


def get_pattern_stats() -> Dict:
    """Return a summary suitable for progress_tracker and logs."""
    _load_cache()
    pat  = _patterns or {}
    wld  = _world    or {}
    total_tokens = sum(len(v) for v in pat.values() if isinstance(v, dict))
    grounded = [
        d for d, s in wld.items()
        if isinstance(s, dict)
        and s.get("rule_total", 0) + s.get("pred_total", 0) + s.get("exp_total", 0) > 5
    ]
    return {
        "pattern_domains":      list(pat.keys()),
        "total_pattern_tokens": total_tokens,
        "world_model_domains":  list(wld.keys()),
        "grounded_domains":     grounded,
    }
