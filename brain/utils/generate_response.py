# utils/generate_response.py
from __future__ import annotations
from brain.core.runtime_log import get_logger

import hashlib as _gr_hashlib
import os
import threading as _threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, List

import json as _json_emo
_log = get_logger(__name__)

# ── API circuit breaker — prevents blocking the loop when API is unreachable ───
# Opens for _CB_OPEN_S seconds after any network/connection failure.
# All callers check _cb_is_open() and return an error immediately.
_cb_lock       = _threading.Lock()
_cb_open_until: float = 0.0
_CB_OPEN_S     = 90.0  # stay open 90s after a network failure

# Auth failures (401 / invalid key) never fix themselves within a session, so
# they open a much longer breaker — otherwise a dead key gets hammered in
# multi-call bursts on every utterance (seen in model_failures.txt).
_cb_auth_open_until: float = 0.0
_CB_AUTH_OPEN_S    = 3600.0

def _cb_is_open() -> bool:
    return time.time() < max(_cb_open_until, _cb_auth_open_until)

def _cb_trip() -> None:
    global _cb_open_until
    with _cb_lock:
        _cb_open_until = time.time() + _CB_OPEN_S

def _cb_trip_auth() -> None:
    global _cb_auth_open_until
    with _cb_lock:
        _cb_auth_open_until = time.time() + _CB_AUTH_OPEN_S

def _is_auth_error(exc_or_msg) -> bool:
    msg = str(exc_or_msg).lower()
    return ("401" in msg or "invalid_api_key" in msg or "incorrect api key" in msg
            or "authentication" in msg)

_CB_NETWORK_KEYWORDS = frozenset({
    "connection", "connect", "unreachable", "network", "refused",
    "name or service", "nodename", "errno", "socket", "ssl", "timed out",
    "timeout", "reset by peer", "broken pipe",
})

def _is_network_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in _CB_NETWORK_KEYWORDS)

# ── Response cache (avoids redundant API calls for identical prompts) ──────────
_GR_CACHE: Dict[str, tuple] = {}  # sha256 → (timestamp, content)
_GR_CACHE_TTL = 270               # 4.5 min — stays warm across typical loop cycles
_GR_CACHE_MAX = 200
_GR_VOLATILE  = frozenset({"now", "current", "today", "just", "latest", "recently"})


def _gr_cache_key(model: str, prompt_text: str) -> str:
    return _gr_hashlib.sha256(f"{model}||{prompt_text}".encode()).hexdigest()


def _gr_cache_get(key: str) -> Optional[str]:
    entry = _GR_CACHE.get(key)
    if entry and (time.time() - entry[0]) < _GR_CACHE_TTL:
        return entry[1]
    _GR_CACHE.pop(key, None)
    return None


def _gr_cache_put(key: str, content: str) -> None:
    if len(_GR_CACHE) >= _GR_CACHE_MAX:
        oldest = min(_GR_CACHE, key=lambda k: _GR_CACHE[k][0])
        _GR_CACHE.pop(oldest, None)
    _GR_CACHE[key] = (time.time(), content)

from openai import OpenAI
from dotenv import load_dotenv

from brain.utils.json_utils import load_json, save_json
from brain.utils.coerce_to_string import coerce_to_string
from brain.utils.env import env_bool
# build_system_prompt is imported deferred at its call site (see below) to keep
# this L1 utils module free of a load-time utils→cognition (L1→L3) import cycle —
# the same pattern utils/response_utils.py uses.
from brain.utils.log import log_model_issue
from brain.core.config.settings import model_roles
from brain.paths import MODEL_CONFIG_FILE, LLM_PROMPT, DATA_DIR
from brain.utils.self_model import get_self_model
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure

# LLM-as-tool-only is the DEFAULT (set ORRIN_LLM_TOOL_ONLY=0 to disable).
# The LLM is one tool in the registry — same standing as Wikipedia or web
# search. Background cognition (reflection, planning, behavior generation,
# escalation, dreams, per-cycle speech) never reaches the API; it is served by
# the symbolic gate inside generate_response() and gets "tool unavailable: llm"
# past that point. Only these explicitly-invoked tool entry points may make a
# real API call:
_LLM_TOOL_CALLERS: frozenset = frozenset({
    "ask_llm",          # cognition/tools/ask_llm.py — the registered LLM tool
    "ask_llm_for_research",
    "ask_llm_about_conversation",
    "user_chat",        # direct replies to a real user utterance
})

def _llm_tool_only() -> bool:
    return env_bool("ORRIN_LLM_TOOL_ONLY", True)

# --- Client singleton (lazy) ---
_client: Optional[OpenAI] = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        load_dotenv(override=True)
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is missing. Set it in your .env.")
        try:
            _client = OpenAI(api_key=key)
        except TypeError:
            os.environ["OPENAI_API_KEY"] = key
            _client = OpenAI()
    return _client

def reinit_client() -> None:
    """Drop the cached OpenAI client so a newly-saved key takes effect on the next
    call WITHOUT a restart (Phase 4 / §4 — keys are pasted in Settings, not files).

    Also clears the auth circuit breaker: a previously-dead key trips a long auth
    breaker (_cb_trip_auth) that would otherwise keep refusing calls even after the
    user fixes the key. The client rebuilds lazily on the next generate_response()."""
    global _client, _cb_auth_open_until
    with _cb_lock:
        _cb_auth_open_until = 0.0
    _client = None
    # Drop the response cache too: its key is the model_config model name, which is
    # provider-INDEPENDENT, so a switch (e.g. OpenAI→Anthropic) would otherwise serve the
    # old provider's cached reply for the same prompt within the TTL (Part 11).
    _GR_CACHE.clear()
    # Also drop the cached pluggable provider (Part 11) so a newly-saved key, provider,
    # or model takes effect on the next call without a restart.
    try:
        from brain.utils import llm_providers as _providers
        _providers.reinit()
    except Exception as _e:  # best-effort provider-cache reset — never block key reset
        record_failure("generate_response.reset.provider_reinit", _e)

def get_thinking_model() -> str:
    val = model_roles.get("thinking", "gpt-4.1")
    if isinstance(val, dict):
        return str(val.get("model") or val.get("name") or "gpt-4.1")
    return str(val) if val else "gpt-4.1"

def _clamp(v: float, lo: float, hi: float) -> float:
    try:
        v = float(v)
    except (ValueError, TypeError):  # intentional: non-numeric → clamp floor
        return lo
    return max(lo, min(hi, v))

def _retry(fn, tries: int = 2, backoff: float = 0.5) -> Any:
    last_err: Optional[Exception] = None
    for i in range(tries + 1):
        try:
            return fn()
        except Exception as e:
            msg = str(e).lower()
            transient = any(k in msg for k in ("timeout", "timed out", "rate limit", "429", "server error", "5"))
            if i == tries or not transient:
                last_err = e
                break
            time.sleep(backoff * (2 ** i))
            last_err = e
    if last_err:
        raise last_err
    raise RuntimeError("Retry loop exited without result.")

def _build_messages(system_prompt: str, prompt: Any) -> List[Dict[str, str]]:
    if isinstance(prompt, list) and all(isinstance(m, dict) and "role" in m and "content" in m for m in prompt):
        msgs: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for m in prompt:
            msgs.append({"role": str(m["role"]), "content": coerce_to_string(m["content"])})
        return msgs
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": coerce_to_string(prompt)},
    ]


# ---------- failure counter (never contaminates cognition logs) ----------

def _record_llm_failure(caller: str, error: str) -> None:
    """Increment per-caller failure count in llm_failure_counts.json only."""
    try:
        _path = DATA_DIR / "llm_failure_counts.json"
        counts: Dict[str, int] = load_json(_path, default_type=dict) or {}
        counts[caller] = int(counts.get(caller, 0)) + 1
        save_json(_path, counts)
    except Exception as _e:
        record_failure("generate_response._record_llm_failure", _e)


# ---------- tagged-result helpers ----------

def _ok(content: str) -> Dict[str, Any]:
    return {"status": "ok", "content": content, "error": None}

def _err(error: str) -> Dict[str, Any]:
    return {"status": "error", "content": None, "error": error}


def llm_ok(result: Optional[Dict[str, Any]], caller: str) -> Optional[str]:
    """
    Extract content from a tagged generate_response() result.
    Returns the content string on success; records the failure and returns None on error.
    Safe to call with None (treats as error).
    """
    if isinstance(result, dict) and result.get("status") == "ok":
        return result.get("content")
    error = (result or {}).get("error", "null response") if isinstance(result, dict) else "null response"
    # Tool absence is normal (config-disabled, no key, circuit open) — note it
    # and route around, don't count it as a failure to escalate or diagnose.
    if isinstance(error, str) and error.startswith("tool unavailable"):
        return None
    _record_llm_failure(caller, error)
    return None


# ---------- main entry ----------

def generate_response(
    prompt: Any,
    model: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    caller: str = "",
) -> Dict[str, Any]:
    """
    Generate a chat completion.

    Returns a tagged dict:
      {"status": "ok",    "content": str,  "error": None}  — success
      {"status": "error", "content": None, "error": str}   — any failure

    Error messages are NEVER returned as content. Use llm_ok(result, caller) to
    safely extract content and track per-caller failure rates.
    """
    load_dotenv()

    selected_cfg: Dict[str, Any] = {}
    try:
        file_cfg = load_json(MODEL_CONFIG_FILE, default_type=dict) or {}
        default_key = (file_cfg or {}).get("default", "thinking")
        base_block = (file_cfg.get(default_key)
                      or file_cfg.get("thinking")
                      or {})

        # model_config.json may store plain model-name strings rather than dicts
        if isinstance(base_block, str):
            base_block = {"model": base_block}

        if isinstance(config, dict):
            selected_cfg = {**base_block, **config}
        else:
            selected_cfg = dict(base_block)

        if model is not None:
            selected_cfg["model"] = model

        mfield = selected_cfg.get("model")
        if isinstance(mfield, dict):
            nested = mfield
            for k in ("model", "temperature", "max_tokens", "system_prompt"):
                if k in nested and k not in selected_cfg:
                    selected_cfg[k] = nested[k]
            selected_cfg["model"] = nested.get("model") or nested.get("name") or "gpt-4.1"

        _emo_state: Dict[str, Any] = {}
        try:
            from brain.paths import AFFECT_STATE_FILE
            # Was reading the legacy emotion_state.json (renamed to affect_state.json
            # in the affect rename) → it silently read nothing.
            _raw_emo = load_json(AFFECT_STATE_FILE, default_type=dict)
            _core = _raw_emo.get("core_signals")
            _emo_state = {**_raw_emo, **_core} if isinstance(_core, dict) else _raw_emo
        except Exception as _e:
            record_failure("generate_response.generate_response", _e)

        from brain.cognition.selfhood.identity import build_system_prompt  # deferred: avoid L1→L3 load cycle
        sys_prompt_raw = selected_cfg.get(
            "system_prompt",
            build_system_prompt(get_self_model(), affect_state=_emo_state or None),
        )
        system_prompt = coerce_to_string(sys_prompt_raw)

        raw_model = selected_cfg.get("model", "gpt-4.1")
        if isinstance(raw_model, dict):
            raw_model = raw_model.get("model") or raw_model.get("name") or "gpt-4.1"
        model_name = coerce_to_string(raw_model).strip()
        if not model_name or "{" in model_name or "}" in model_name:
            raise TypeError(f"model must be a non-empty model id string, got: {raw_model!r}")

        max_tokens  = int(_clamp(selected_cfg.get("max_tokens", 2048), 16, 8192))
        expect_json = bool(selected_cfg.get("expect_json", False))
        require_user_tail = bool(selected_cfg.get("require_user_tail", False))

        messages = _build_messages(system_prompt, prompt)

        if require_user_tail and messages[-1]["role"] != "user":
            last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
            if last_user:
                messages.append({"role": "user", "content": last_user["content"]})
            else:
                raise RuntimeError("No user message available to prompt the model.")

        # Cache check: skip volatile prompts (time-sensitive content shouldn't be cached)
        _prompt_str  = coerce_to_string(prompt)
        _is_vol      = any(kw in _prompt_str.lower() for kw in _GR_VOLATILE)
        _gr_cache_k  = _gr_cache_key(model_name, _prompt_str) if not _is_vol else None
        if _gr_cache_k:
            _cached_reply = _gr_cache_get(_gr_cache_k)
            if _cached_reply:
                return _ok(_cached_reply)

        # Symbolic gate — try to answer without LLM using local knowledge.
        # Skipped for system/meta callers (identity, config, dream sub-cycles)
        # and for multi-turn message lists (context too complex for symbolic match).
        _sym_skip_callers = frozenset({
            "idle_consolidation_cycle/consolidation", "idle_consolidation_cycle/recombination", "idle_consolidation_cycle/processing",
            "identity", "build_system_prompt", "build_response",
        })
        if (caller not in _sym_skip_callers
                and not isinstance(prompt, list)
                and len(_prompt_str) < 1200):
            try:
                from brain.symbolic.reasoning_router import route as _sym_route
                _sym_result = _sym_route(_prompt_str)
                if _sym_result.get("resolved") and _sym_result.get("answer"):
                    # Render the structured answer as natural language
                    _sym_answer = _sym_result["answer"]
                    try:
                        from brain.symbolic.symbolic_fluency import generate_symbolic_response as _gsr
                        _fluent = _gsr(_sym_result, _prompt_str).strip()
                        if _fluent:
                            _sym_answer = _fluent
                    except Exception as _e:
                        record_failure("generate_response.generate_response.2", _e)
                    if _gr_cache_k:
                        _gr_cache_put(_gr_cache_k, _sym_answer)
                    return _ok(_sym_answer)
            except Exception as _e:
                record_failure("generate_response.generate_response.3", _e)

        # LLM-as-tool gate: past this point we need the actual API. The symbolic
        # gate above still runs with the LLM disabled — the architecture stays
        # fully functional; only the external tool call is skipped. An
        # unavailable tool is a normal result (like a dead Wikipedia fetch),
        # not an error: no log_model_issue, no failure count (see llm_ok).
        #
        # Tool-only enforcement (default ON): cognition callers never reach the
        # API at all — the symbolic gate above is their whole path. Only
        # explicit tool entry points (_LLM_TOOL_CALLERS) may call out.
        if _llm_tool_only() and caller not in _LLM_TOOL_CALLERS:
            return _err("tool unavailable: llm (tool-only: cognition uses the symbolic path)")
        from brain.utils.llm_gate import llm_available
        if not llm_available():
            return _err("tool unavailable: llm")

        # Resolve the user-selected provider (Part 11). "none" ⇒ symbolic-only; an
        # unconfigured provider (no key / no endpoint) is a normal "tool unavailable",
        # not an error. For OpenAI this resolves to today's path verbatim.
        from brain.utils import llm_providers as _providers
        provider = _providers.resolve(default_model=model_name)
        if provider is None:
            return _err("tool unavailable: llm (provider: none — symbolic-only)")
        if not provider.is_configured():
            return _err("tool unavailable: llm (no API key)")

        lp = Path(LLM_PROMPT)
        lp.parent.mkdir(parents=True, exist_ok=True)
        # Cap log at 10 MB — keep the most recent 5 MB to avoid unbounded growth.
        try:
            if lp.exists() and lp.stat().st_size > 10 * 1024 * 1024:
                _text = lp.read_text(encoding="utf-8", errors="replace")
                lp.write_text(_text[-5 * 1024 * 1024:], encoding="utf-8")
        except Exception as _e:
            record_failure("generate_response.generate_response.4", _e)

        try:
            import fcntl as _fcntl_gr
        except ImportError:
            _fcntl_gr = None  # type: ignore[assignment]

        with lp.open("a", encoding="utf-8") as f:
            if _fcntl_gr is not None:
                try:
                    _fcntl_gr.flock(f, _fcntl_gr.LOCK_EX)
                except Exception as _e:
                    record_failure("generate_response.generate_response.5", _e)
            f.write(f"\n\n=== {now_iso_z()} ===\n")
            f.write("SYSTEM PROMPT:\n" + system_prompt + "\n\n")
            f.write("MESSAGES:\n")
            for m in messages:
                f.write(f"[{m.get('role','?').upper()}] {m.get('content','')}\n")
            if _fcntl_gr is not None:
                try:
                    _fcntl_gr.flock(f, _fcntl_gr.LOCK_UN)
                except Exception as _e:
                    record_failure("generate_response.generate_response.6", _e)

        # The model to actually request: OpenAI keeps per-call routing (model_config /
        # the `model` arg) verbatim; other providers use the model the user chose for
        # them in Settings (model_config's gpt-* default is meaningless for Claude/Gemini).
        _eff_model = model_name if provider.id == "openai" else (provider.model or model_name)

        # Fast-fail if circuit is open (API recently unreachable)
        if _cb_is_open():
            return _err("LLM circuit open — API unreachable, skipping call")

        def _call():
            return provider.generate(
                messages, model=_eff_model, max_tokens=max_tokens, expect_json=expect_json, timeout=8
            )

        try:
            pr = _retry(_call, tries=1, backoff=0.0)
        except Exception as _api_exc:
            if _is_network_error(_api_exc):
                _cb_trip()
            raise
        reply = (pr.get("content") or "").strip()
        if _gr_cache_k and reply:
            _gr_cache_put(_gr_cache_k, reply)
        if not reply:
            return _err("LLM returned empty response")

        try:
            from brain.utils.token_meter import record_call as _record_tokens
            _usage = pr.get("usage") or {}
            _in = int(_usage.get("input", 0) or 0)
            _out = int(_usage.get("output", 0) or 0)
            if _in or _out:
                _record_tokens(caller or "unknown", _eff_model, _in, _out)
            # Egress ledger (§9.4): one outbound call, tagged by the active provider
            # (§11.1 — "Nothing leaves your machine" for none/local). Counts/tokens
            # only — never the prompt or response.
            from brain.utils.egress import record as _egress
            if not provider.local:
                _egress(provider.egress_name, approx_tokens=(_in + _out) or None)
        except Exception as _e:
            record_failure("generate_response.generate_response.7", _e)

        with lp.open("a", encoding="utf-8") as f:
            if _fcntl_gr is not None:
                try:
                    _fcntl_gr.flock(f, _fcntl_gr.LOCK_EX)
                except Exception as _e:
                    record_failure("generate_response.generate_response.8", _e)
            f.write("\nLLM RESPONSE:\n" + reply + "\n")
            if _fcntl_gr is not None:
                try:
                    _fcntl_gr.flock(f, _fcntl_gr.LOCK_UN)
                except Exception as _e:
                    record_failure("generate_response.generate_response.9", _e)

        # Crystallize successful responses into symbolic rules (async-safe, best-effort)
        _cryst_skip = frozenset({
            "idle_consolidation_cycle/consolidation", "idle_consolidation_cycle/recombination", "idle_consolidation_cycle/processing",
            "identity", "build_system_prompt",
        })
        if caller not in _cryst_skip and not isinstance(prompt, list) and reply:
            try:
                from brain.symbolic.crystallization import crystallize as _cryst
                _cryst(_prompt_str, reply, outcome=0.65, caller=caller)
            except Exception as _e:
                record_failure("generate_response.generate_response.10", _e)

        return _ok(reply)

    except Exception as e:

        global _client
        if _is_auth_error(e):
            _client = None
            _cb_trip_auth()  # dead key won't heal mid-session; stop hammering it
        try:
            cfg_repr = repr(selected_cfg)
        except Exception:
            cfg_repr = "{}"
        error_msg = str(e)
        log_model_issue(f"[generate_response] API failure: {error_msg} | config: {cfg_repr}")
        return _err(error_msg)


def generate_reasoning_chain(
    topic: str,
    context_text: str,
    caller: str,
    model: Optional[str] = None,
    identity: str = "Orrin, an evolving autonomous AI",
) -> Dict[str, Any]:
    """
    Single-call structured reasoning: one API call that returns questions + reasoning + plan
    as a JSON object. Equivalent depth to a 3-step chain at 1/3 the cost and latency.

    Returns:
      {"status": "ok", "content": plan_str,
       "scratchpad": {"questions": str, "reasoning": str}}
    on success, or {"status": "error", ...} on failure.
    """
    prompt = (
        f"You are {identity}.\n\n"
        f"Topic / goal: {topic}\n\n"
        f"Context:\n{context_text}\n\n"
        "Think through this goal in three stages. Respond ONLY with valid JSON:\n"
        "{\n"
        '  "questions": "The 2-4 most important questions to answer before acting. One per line.",\n'
        '  "reasoning": "Work through each question using the context. Be honest about gaps. 3-6 sentences.",\n'
        '  "plan": "The single most concrete actionable next step. One sentence starting with an action verb."\n'
        "}"
    )

    result = generate_response(prompt, model=model, config={"expect_json": True}, caller=caller)
    raw    = llm_ok(result, caller)

    if not raw:
        return _err(f"reasoning chain produced no response (caller={caller})")

    try:
        parsed    = _json_emo.loads(raw)
        plan      = str(parsed.get("plan", "")).strip()
        questions = str(parsed.get("questions", "")).strip()
        reasoning = str(parsed.get("reasoning", "")).strip()
        if not plan:
            return _err(f"reasoning chain JSON missing 'plan' (caller={caller})")
    except Exception:
        # Model returned text instead of JSON — use raw output as the plan
        plan      = raw.strip()[:300]
        questions = ""
        reasoning = ""

    return {
        "status": "ok",
        "content": plan,
        "scratchpad": {"questions": questions, "reasoning": reasoning},
        "error": None,
    }
