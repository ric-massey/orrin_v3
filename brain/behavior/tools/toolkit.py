# tools.py
from __future__ import annotations
import importlib
import os
import json
from pathlib import Path
import time
import random
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from utils.json_utils import load_json, save_json, extract_json
from utils.log import log_activity, log_error, log_model_issue, log_private
from utils.core_utils import get_thinking_model
from utils.generate_response import generate_response, llm_ok
from utils.error_router import catch_and_route            # ← routing decorator
from think.sandbox_runner import run_python               # ← sandboxed exec

from paths import (
    DATA_DIR,
    LONG_MEMORY_FILE,
    TOOL_CATALOG_JSON,
    TOOL_REQUESTS_FILE,
    WORKING_MEMORY_FILE,
    ROOT_DIR,                                            # cwd for sandbox so imports resolve
    ensure_files,
)
from utils.timeutils import now_iso_z

# Set once after the first web_search call finds no SERPER_API_KEY, so the
# expected "key not set" state is noted a single time rather than per call.
_SERPER_KEY_NOTICED = False

# Helpers

def _normalize_target(path_like: str | Path) -> Path:
    """
    Normalize a caller-supplied path:
    - Absolute paths are honored (use cautiously).
    - Relative paths are *rooted under* DATA_DIR and are prevented from escaping via '..'.
    """
    p = Path(path_like)
    if p.is_absolute():
        return p
    combined = (DATA_DIR / p).resolve()
    base = DATA_DIR.resolve()
    try:
        # ensure combined lives under DATA_DIR
        combined.relative_to(base)
    except ValueError:
        raise ValueError("Path traversal outside DATA_DIR is not allowed.")
    return combined

def delay_between_requests() -> None:
    time.sleep(random.uniform(2, 5))

def _save_text_atomic(path: Path, content: str) -> None:
    """
    Atomic text write (temp file + os.replace). Avoids partial files on crash.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding="utf-8") as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name
    os.replace(tmp_name, path)

def _http_with_retries(
    method: str,
    url: str,
    *,
    retries: int = 2,
    backoff: float = 0.5,
    jitter: Tuple[float, float] = (0.0, 0.3),
    **kwargs: Any,
) -> requests.Response:
    """
    Minimal retry helper for flaky networks / 5xx / timeouts.
    """
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            resp = requests.request(method, url, timeout=kwargs.pop("timeout", 10), **kwargs)
            # retry on 5xx
            if 500 <= resp.status_code < 600:
                raise requests.HTTPError(f"{resp.status_code} server error", response=resp)
            return resp
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
            last_err = e
            if attempt == retries:
                break
            sleep_for = backoff * (2 ** attempt) + random.uniform(*jitter)
            time.sleep(sleep_for)
    if last_err:
        raise last_err
    raise RuntimeError("HTTP retry loop exited without response or exception.")

# File Tools (pathlib-only, DATA_DIR-rooted)

@catch_and_route("tool", return_on_error=lambda e: {"success": False, "error": str(e)})
def write_file(path: str | Path, content: str) -> Dict[str, Any]:
    """
    Write arbitrary text to a file (atomic). Relative paths resolve under DATA_DIR.
    """
    p = _normalize_target(path)
    _save_text_atomic(p, content)
    log_activity(f"✅ Wrote to {p}")
    return {"success": True, "path": str(p)}

@catch_and_route("tool", return_on_error=lambda e: {"success": False, "error": str(e)})
def read_file(path: str | Path) -> Dict[str, Any]:
    """
    Read a text file (utf-8). Relative paths resolve under DATA_DIR.
    """
    p = _normalize_target(path)
    content = p.read_text(encoding="utf-8")
    log_activity(f"✅ Read file {p}")
    return {"success": True, "content": content}

@catch_and_route(
    "tool",
    return_on_error=lambda e: {"success": False, "error": str(e), "output": "", "stderr": str(e), "returncode": -2},
)
def execute_python_code(code_string: str, *, timeout: float = 5.0, cwd: str | None = None) -> Dict[str, Any]:
    """
    Execute Python code in an *isolated subprocess* (sandbox).
    Returns:
      {
        "success": bool,
        "output": "<stdout>",
        "stderr": "<stderr>",
        "returncode": int
      }
    """
    # run in repo root so absolute/relative imports like `from think...` work
    res = run_python(code_string, timeout=timeout, cwd=cwd or str(ROOT_DIR))
    ok = bool(res.get("ok"))
    out = {
        "success": ok,
        "output": res.get("stdout", ""),
        "stderr": res.get("stderr", ""),
        "returncode": int(res.get("returncode", 0)),
    }
    if ok:
        log_activity("✅ Executed Python code in sandbox.")
    else:
        log_error(f"❌ Sandbox execution error (rc={out['returncode']}): {out['stderr'][:300]}")
    return out

# Catalog / Discovery

@catch_and_route("tool")  # errors are routed; function has no structured return
def add_tool_to_catalog(name: str, description: str, when_to_use: str) -> None:
    catalog_path = Path(TOOL_CATALOG_JSON)
    try:
        tool_catalog = load_json(catalog_path, default_type=list)
        if not isinstance(tool_catalog, list):
            log_model_issue("tool_catalog.json was not a list. Resetting.")
            tool_catalog = []
    except Exception:
        tool_catalog = []

    if any(isinstance(t, dict) and t.get("name") == name for t in tool_catalog):
        log_private(f"⚠️ Tool '{name}' already exists in the catalog.")
        return

    new_tool = {
        "name": name,
        "description": description,
        "when_to_use": when_to_use,
        "discovered": True,
        "timestamp": now_iso_z(),
    }
    tool_catalog.append(new_tool)
    ensure_files([catalog_path])
    save_json(catalog_path, tool_catalog)
    log_private(f"✅ Tool '{name}' added to catalog.")

# Web utilities

def is_scraping_allowed(url: str) -> bool:
    from urllib.robotparser import RobotFileParser
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False

    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        return rp.can_fetch("*", url)
    except Exception:
        return False

@catch_and_route("tool", return_on_error=lambda e: {"error": str(e)})
def web_search(query: str) -> Dict[str, Any]:
    """
    Uses Serper.dev (requires SERPER_API_KEY in env).
    Correct usage: POST with JSON body, not GET.
    """
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        # An unset key is an expected, documented config state (web search is
        # optional; Orrin falls back to searching its own files). Note it once
        # per process at activity level instead of spamming error_log.txt on
        # every call (run audit #6).
        global _SERPER_KEY_NOTICED
        if not _SERPER_KEY_NOTICED:
            _SERPER_KEY_NOTICED = True
            log_activity("[web_search] SERPER_API_KEY not set — web search disabled, using local files.")
        return {"error": "missing_api_key"}

    url = "https://api.serper.dev/search"
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query}

    resp = _http_with_retries("POST", url, headers=headers, data=json.dumps(payload), timeout=12)
    resp.raise_for_status()
    # Egress ledger (§9.4): one Serper search left the device. Query is never stored.
    try:
        from utils.egress import record as _egress
        _egress("serper")
    except Exception:
        pass
    return resp.json()

@catch_and_route("tool", return_on_error=lambda e: f"❌ Scrape failed: {e}")
def scrape_text(url: str) -> str:
    """
    Respect robots.txt, then fetch and return ~first 2000 chars of visible text.
    """
    if not is_scraping_allowed(url):
        return "⚠️ Scraping disallowed by robots.txt."
    delay_between_requests()
    resp = _http_with_retries(
        "GET",
        url,
        headers={"User-Agent": "OrrinBot/1.0 (ethical AGI; contact: ric.massey@gmail.com)"},
        timeout=12,
    )
    resp.raise_for_status()
    # Egress ledger (§9.4): a page fetch left the device (URL not stored).
    try:
        from utils.egress import record as _egress
        _egress("web")
    except Exception:
        pass
    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(separator="\n").strip()
    # light collapse of excessive blank lines
    lines = [ln.strip() for ln in text.splitlines()]
    collapsed = "\n".join([ln for ln in lines if ln])
    return collapsed[:2000]

# Tool suggestion / reasoning

@catch_and_route("tool")  # log & continue on errors
def evaluate_tool_use(memories: List[Dict[str, Any]]) -> None:
    """
    Very simple keyword-based suggester that appends to TOOL_REQUESTS_FILE.
    """
    keywords = {
        "search": ["look up", "google", "find info", "get data", "browse"],
        "run_python": ["calculate", "plot", "simulate", "compute", "graph"],
    }

    existing = load_json(TOOL_REQUESTS_FILE, default_type=list)
    if not isinstance(existing, list):
        existing = []

    existing_keys = {(e.get("tool"), e.get("reason")) for e in existing if isinstance(e, dict)}

    for m in memories:
        if not isinstance(m, dict):
            continue
        text = str(m.get("content", "")).lower()
        for tool, cues in keywords.items():
            if any(cue in text for cue in cues):
                entry = {
                    "tool": tool,
                    "reason": m.get("content", ""),
                    "timestamp": m.get("timestamp", now_iso_z()),
                }
                key = (entry["tool"], entry["reason"])
                if key not in existing_keys:
                    existing.append(entry)
                    existing_keys.add(key)

    ensure_files([Path(TOOL_REQUESTS_FILE)])
    save_json(TOOL_REQUESTS_FILE, existing)

@catch_and_route("tool")  # log model issues separately via router
def tool_thinking() -> None:
    """
    Ask the model to propose tool uses based on recent memories.
    Appends merged suggestions to TOOL_REQUESTS_FILE.
    """
    recent_long = load_json(LONG_MEMORY_FILE, default_type=list)
    recent_work = load_json(WORKING_MEMORY_FILE, default_type=list)

    recent_memories = (recent_long[-15:] if isinstance(recent_long, list) else []) + \
                      (recent_work[-5:] if isinstance(recent_work, list) else [])

    bullet_lines = [
        f"- {m['content']}"
        for m in recent_memories
        if isinstance(m, dict) and "content" in m
    ]

    prompt = (
        "I am a reflective AI.\n"
        "From the following thoughts, identify any that might benefit from tool use like web search, Python code, or visualization.\n"
        "If so, describe:\n"
        "- which tool I would use\n"
        "- what question or goal I would pursue with it\n"
        "- why it's useful\n\n"
        "Only respond with a JSON array of entries like:\n"
        '[{\"tool\": \"search\", \"reason\": \"Find background info on X\", \"timestamp\": \"\"}]\n\n'
        "Here are the recent thoughts:\n" + "\n".join(bullet_lines)
    )

    config = {"model": get_thinking_model()}
    response = llm_ok(generate_response(prompt, config=config), "toolkit")
    if not response:
        log_model_issue("tool_thinking() produced no response.")
        return

    suggestions = extract_json(response)
    if isinstance(suggestions, list):
        existing = load_json(TOOL_REQUESTS_FILE, default_type=list)
        if not isinstance(existing, list):
            log_error("tool_requests.json was not a list. Resetting.")
            existing = []
        merged = existing + [s for s in suggestions if isinstance(s, dict)]
        ensure_files([Path(TOOL_REQUESTS_FILE)])
        save_json(TOOL_REQUESTS_FILE, merged)

        log_activity(f"Orrin added {len(suggestions)} tool request(s).")
        try:
            log_private(f"Orrin reflected on tool use and added:\n{json.dumps(suggestions, indent=2)}")
        except Exception:
            log_private(f"Orrin reflected on tool use and added:\n{str(suggestions)[:1200]}")
    else:
        log_model_issue(f"tool_thinking() returned non-list structure:\n{response}")

# Universal tool registry

def _load_skill(module_name: str, fn_name: str):
    """Lazy-load a skill from agency/skills/ — fail silently if missing."""
    try:
        mod = importlib.import_module(f"agency.skills.{module_name}")
        return getattr(mod, fn_name, None)
    except Exception:
        return None


def _load_system_presence(fn_name: str):
    """Lazy-load a system-presence capability — fail silently if unavailable."""
    try:
        from embodiment import system_presence as _sp
        return getattr(_sp, fn_name, None)
    except Exception:
        return None


def ask_llm_tool(query: str = "", purpose: str = "question") -> str:
    """LLM as a registry tool — same standing as web_search or wikipedia.

    Invoked through the same dispatch path as every other tool; when the LLM
    is disabled/unreachable it returns a plain "tool unavailable" message,
    exactly like a dead web fetch — a result to route around, not an error."""
    try:
        from cognition.tools.ask_llm import ask_llm
        return ask_llm({}, query=query, purpose=purpose)
    except Exception as e:
        return f"LLM tool unavailable: {e}"


tool_registry = {
    # --- Core file / code tools ---
    "write_file":           write_file,
    "read_file":            read_file,
    "execute_python_code":  execute_python_code,
    # --- Web tools ---
    "web_search":           web_search,
    "scrape_text":          scrape_text,
    # --- LLM as a tool (same standing as the web tools) ---
    "ask_llm":              ask_llm_tool,
    # --- Agency skills (lazy-loaded) ---
    "notify_user":          _load_skill("notify_user",    "notify_user"),
    "list_directory":       _load_skill("list_directory", "list_directory"),
    "search_files":         _load_skill("search_files",   "search_files"),
    "grep_files":           _load_skill("grep_files",     "grep_files"),
    "save_note":            _load_skill("save_note",      "save_note"),
    # --- System presence (embodied macOS awareness) ---
    "survey_environment":   _load_system_presence("survey_environment"),
    "write_note_to_desktop": _load_system_presence("write_note_to_desktop"),
    "check_user_presence":  _load_system_presence("check_user_presence"),
    "announce":             _load_system_presence("announce"),
}

# Drop any skills that failed to load
tool_registry = {k: v for k, v in tool_registry.items() if callable(v)}
