from brain.core.runtime_log import get_logger
import re
import json
import logging
import tempfile
import os
import platform
from contextlib import contextmanager
from pathlib import Path, PurePath
from datetime import datetime, date, timezone
from typing import Any, Callable, Generator, TypeVar, Union, Optional
from brain.utils.log import log_model_issue
from brain.utils.failure_counter import record_failure

# fcntl is POSIX-only; make it optional
try:
    import fcntl  # type: ignore
except Exception:
    fcntl = None  # type: ignore
_log = get_logger(__name__)

T = TypeVar("T")


def cap_jsonl(path: Union[str, Path], max_lines: int = 2000, max_bytes: int = 2_000_000) -> None:
    """
    Keep an append-only JSONL telemetry file bounded.

    Cheap stat-gated: only rewrites when the file exceeds `max_bytes`, then keeps
    the last `max_lines` COMPLETE lines (line-safe, unlike a raw byte trim).
    Atomic via tmp+replace. Best-effort — never raises, because telemetry must
    not be able to crash the cognitive loop.
    """
    try:
        p = Path(path)
        if not p.exists() or p.stat().st_size <= max_bytes:
            return
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) <= max_lines:
            return
        keep = lines[-max_lines:]
        # Unique temp name (was a FIXED "<path>.tmp"): two processes trimming the
        # same file clobbered each other's temp and os.replace'd a half-written
        # file — a source of the truncated-JSON corruption. Unique per write =
        # safe under concurrency, like save_json.
        import os, tempfile
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=p.parent,
            prefix=p.name + ".", suffix=".tmp", delete=False,
        ) as tf:
            tf.write("\n".join(keep) + "\n")
            tf.flush()
            os.fsync(tf.fileno())
            tmp_name = tf.name
        os.replace(tmp_name, p)
    except Exception as _e:
        record_failure("json_utils.cap_jsonl", _e)


# ------------------------------
# JSON extraction (healing)
# ------------------------------

def extract_json(text: str) -> Optional[Union[dict, list]]:
    """
    Best-effort extraction of the first JSON object/array from messy LLM output.
    Order:
      1) ```json fenced block
      2) generic ``` fenced block
      3) first JSON fragment via scanner (try parse → heal → salvage-top-level-object)
      4) whole text heal → salvage-top-level-object
    Returns dict/list, else None.
    """
    try:
        s = text if isinstance(text, str) else str(text)

        # Fast reject: bail before the heal/salvage chain unless the text contains
        # a PLAUSIBLE JSON start — an opening brace/bracket actually followed by a
        # JSON token, not just a stray bracket from prose. Symbolic-gate output
        # like "[analogy/GENERAL] Similar situation…" has a "[" but no real JSON;
        # without this it churned through every heal/salvage step and (previously)
        # logged a DEBUG line per attempt, flooding the runtime log.
        if not _has_plausible_json_start(s):
            return None

        # NOTE: each json.loads below is a SPECULATIVE attempt in a try→heal→
        # salvage chain. Failures are expected control flow — the function returns
        # None gracefully and callers handle None — so the per-attempt failures are
        # swallowed silently (no per-attempt logging). Only a genuine *unexpected*
        # exception (outer except) is surfaced, once, via log_model_issue.
        # 1) fenced with json
        m = re.search(r"```(?:json|JSON)\s*([\s\S]*?)\s*```", s)
        if m:
            snippet = m.group(1).strip()
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                pass
            healed = _heal_json_fragment(snippet)
            try:
                return json.loads(healed)
            except Exception:
                salv = _salvage_top_level_object(snippet)
                if salv:
                    try:
                        return json.loads(salv)
                    except Exception:
                        pass

        # 2) any fenced block
        m = re.search(r"```+\s*([\s\S]*?)\s*```+", s)
        if m:
            snippet = m.group(1).strip()
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                healed = _heal_json_fragment(snippet)
                try:
                    return json.loads(healed)
                except Exception:
                    salv = _salvage_top_level_object(snippet)
                    if salv:
                        try:
                            return json.loads(salv)
                        except Exception:
                            pass

        # 3) scan for top-level {...} or [...]
        frag = _first_json_fragment(s)
        if frag:
            try:
                return json.loads(frag)
            except json.JSONDecodeError:
                pass
            healed = _heal_json_fragment(frag)
            try:
                return json.loads(healed)
            except Exception:
                pass
            # salvage top-level object specifically (handles cut off like "..., \"emerging_conflicts\": [")
            salv = _salvage_top_level_object(frag)
            if salv:
                try:
                    return json.loads(salv)
                except Exception:
                    pass

        # 4) whole text attempts
        healed_all = _heal_json_fragment(s)
        try:
            return json.loads(healed_all)
        except Exception:
            pass

        salv_all = _salvage_top_level_object(s)
        if salv_all:
            try:
                return json.loads(salv_all)
            except Exception:
                pass

    except Exception as e:
        preview = s if len(s) <= 600 else (s[:300] + " ... " + s[-200:])
        log_model_issue(f"[extract_json] Failed: {e}\nRaw: {preview}")

    return None


# Characters that can legitimately follow "[" as the first token of a JSON array:
# another container, a string, a number, true/false/null, or an empty array.
_JSON_ARRAY_VALUE_START = frozenset('{["-tfn]0123456789')


def _has_plausible_json_start(s: str) -> bool:
    """True if `s` contains an opening "{" or "[" that is actually followed by a
    JSON token — not just a stray bracket inside prose. Scans every bracket (not
    only the first) so mixed content like 'note: {"x": 1}' still parses, while
    prose like '[analogy/GENERAL] …' or '[metacog] thinking' is rejected cheaply.
    """
    if not s:
        return False
    for mt in re.finditer(r"[\{\[]", s):
        i = mt.start()
        # next non-whitespace char after the bracket
        j = i + 1
        n = len(s)
        while j < n and s[j] in " \t\r\n":
            j += 1
        if j >= n:
            continue
        nxt = s[j]
        if s[i] == "{":
            # object: a key string, or an empty object
            if nxt == '"' or nxt == "}":
                return True
        else:
            # array: any JSON value start, or an empty array
            if nxt in _JSON_ARRAY_VALUE_START:
                return True
    return False


def _first_json_fragment(s: str) -> Optional[str]:
    """Return the first candidate JSON {...} or [...] substring (may be unbalanced if truncated)."""
    i_obj, i_arr = s.find("{"), s.find("[")
    starts = [i for i in (i_obj, i_arr) if i != -1]
    if not starts:
        return None
    start = min(starts)

    open_ch = s[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch and depth > 0:
            depth -= 1
            if depth == 0:
                return s[start:i+1]
    # unbalanced (truncated) → return tail so we can heal it
    return s[start:]


def _heal_json_fragment(frag: str) -> str:
    """
    Light repairs for slightly invalid/truncated JSON:
    - remove trailing commas before } or ]
    - close open string
    - balance unmatched braces/brackets
    """
    t = frag.rstrip()
    t = t.replace(",}", "}").replace(",]", "]")

    in_str = False
    esc = False
    depth_obj = 0
    depth_arr = 0
    for ch in t:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth_obj += 1
            elif ch == "}":
                depth_obj = max(0, depth_obj - 1)
            elif ch == "[":
                depth_arr += 1
            elif ch == "]":
                depth_arr = max(0, depth_arr - 1)

    if in_str:
        t += '"'
    t += "}" * depth_obj
    t += "]" * depth_arr
    t = t.replace(",}", "}").replace(",]", "]")
    return t


def _salvage_top_level_object(text: str) -> Optional[str]:
    """
    Try to salvage a valid top-level JSON *object* from truncated text:
    - Find first '{'
    - Walk tracking quotes/escapes and nesting
    - If we close level 0, return slice
    - If truncated inside the object, cut at the last comma at level==1 and append '}'.
      If that fails, append enough '}' to close remaining depth.
    """
    s = text
    start = s.find("{")
    if start == -1:
        return None

    level = 0
    in_str = False
    esc = False
    last_top_level_comma: Optional[int] = None

    i = start
    while i < len(s):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                level += 1
            elif ch == "}":
                if level > 0:
                    level -= 1
                    if level == 0:
                        return s[start:i+1]
            elif ch == "," and level == 1:
                last_top_level_comma = i
        i += 1

    # Truncated before closing: try cutting at last full top-level pair
    if last_top_level_comma is not None:
        candidate = s[start:last_top_level_comma] + "}"
        try:
            json.loads(candidate)
            return candidate
        except Exception as _e:
            _log_salvage_miss(_e, s)

    # Blindly close remaining braces
    if level > 0:
        candidate = s[start:] + ("}" * level)
        try:
            json.loads(candidate)
            return candidate
        except Exception as _e:
            _log_salvage_miss(_e, s)

    return None


def _log_salvage_miss(exc: Exception, snippet: str) -> None:
    """A salvage attempt that still fails to parse is EXPECTED control flow in
    the try→heal→salvage chain (see extract_json's NOTE) — so it logs at DEBUG,
    not WARNING. Previously these two sites logged a bare WARNING ~38×/minute
    with neither the failing snippet nor the caller, making the source of the
    transient parse failure unidentifiable (RUN_ISSUES_2026-06-10 §secondary).
    With debug logging on, the snippet head + nearest non-json_utils caller are
    included so the producer can finally be traced."""
    if not _log.isEnabledFor(logging.DEBUG):
        return
    caller = "?"
    try:
        import inspect
        for frame in inspect.stack()[2:8]:
            fname = frame.filename
            if "json_utils" not in fname:
                caller = f"{fname.rsplit('/', 1)[-1]}:{frame.lineno} ({frame.function})"
                break
    except Exception:
        pass
    _log.debug("salvage failed: %s | caller=%s | snippet=%r", exc, caller, snippet[:160])


# ------------------------------
# JSON (de)serialization utils
# ------------------------------

def _json_default(o: Any):
    """Safe fallback serializer for non-JSON-native types."""
    if isinstance(o, (Path, PurePath)):
        return str(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, set):
        return list(o)
    if isinstance(o, bytes):
        return o.decode("utf-8", "ignore")
    # tuples, enums, custom objects, etc.
    return str(o)


def _lock_path_for(path: Path) -> Path:
    """Stable, persistent advisory-lock path for a data file."""
    return path.with_suffix(path.suffix + ".lock")


def save_json(filepath: Union[str, Path], data: Any) -> None:
    """
    Atomically write JSON to disk.
    - Write to a temp file in the same dir, fsync, then os.replace(...) atomically.
    - Serialize writers via a well-known .lock file on POSIX (advisory).

    The lock file is PERSISTENT — it is never unlinked. Unlinking it per write
    (the old behaviour) let two writers flock *different inodes*: writer A could
    create+lock the file, finish, and unlink it while writer B was opening a fresh
    inode of the same name, so neither blocked the other and the advisory lock
    failed to serialize. A stable lock inode makes flock actually mutually
    exclusive, and load_json takes a shared lock on the same inode so reads never
    observe a half-written read-modify-write window.
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    lock_fd = None
    tmp_name: Optional[str] = None
    lock_path = _lock_path_for(path)

    try:
        # Acquire inter-process advisory lock (POSIX only)
        if fcntl is not None:
            lock_fd = open(lock_path, "w")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

        # Write to temp in the same dir to guarantee atomic rename
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, dir=str(path.parent), encoding="utf-8"
        ) as tmp:
            tmp_name = tmp.name
            json.dump(data, tmp, indent=2, ensure_ascii=False, default=_json_default)
            tmp.flush()
            os.fsync(tmp.fileno())

        # Atomic replace (POSIX/Windows)
        os.replace(tmp_name, path)

    except Exception as e:
        # Clean up stray temp if we created one
        try:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception as _e:
            record_failure("json_utils.save_json", _e)
        log_model_issue(f"[save_json] Failed to save {filepath}: {e}")
    finally:
        # Release the lock but do NOT unlink the lock file — keeping the inode
        # stable is what makes the advisory lock reliably serialize writers.
        if fcntl is not None and lock_fd:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                lock_fd.close()


def load_json(filepath: Union[str, Path], default_type: Callable[[], T] = dict) -> T:
    """
    Load JSON from file, returning default_type() on error or missing/empty file.
    On JSONDecodeError, attempts ONE timestamped .corrupt backup before returning default.

    Disk-safety: backs up to the SAME directory using a flat stem (no chained suffixes),
    caps at one attempt, and catches OSError errno 28 (ENOSPC) so a full disk degrades
    gracefully instead of looping.

    Concurrency: takes a SHARED advisory lock on the file's persistent .lock inode
    for the duration of the read, so a load never observes the brief window between a
    writer's os.replace and its commit. Shared locks don't block other readers.
    """
    path = Path(filepath)
    lock_fd = None
    try:
        if not path.exists() or path.stat().st_size == 0:
            return default_type()
        if fcntl is not None:
            try:
                lock_fd = open(_lock_path_for(path), "w")
                fcntl.flock(lock_fd, fcntl.LOCK_SH)
            except Exception:
                lock_fd = None  # lock is best-effort; degrade to an unlocked read
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        log_model_issue(f"[load_json] Corrupt JSON in {filepath}: {e}")
        # ONE backup attempt only — use stem (strips all suffixes) to avoid
        # .corrupt.ts.corrupt.ts2... chaining on repeated calls.
        try:
            import shutil as _shutil
            _path = Path(filepath)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            bare_stem = _path.name.split(".")[0]
            # NEVER back up a file that is already a .corrupt backup, or a dotfile
            # whose stem is empty. Re-backing-up corrupt files (which something
            # then re-reads) is exactly the feedback loop that spawned 10k+
            # .corrupt.*.json files. Back up real files only, once.
            if ".corrupt." in _path.name or not bare_stem:
                log_model_issue(f"[load_json] Skipping backup of already-corrupt file {_path.name}")
            else:
                backup = _path.parent / f"{bare_stem}.corrupt.{stamp}.json"
                _shutil.copy2(str(_path), str(backup))
                log_model_issue(f"[load_json] Corrupt file backed up to {backup.name}")
        except OSError as backup_err:
            if backup_err.errno == 28:  # ENOSPC — disk full
                log_model_issue("[load_json] Backup skipped: disk full (ENOSPC)")
            else:
                log_model_issue(f"[load_json] Backup failed: {backup_err}")
        except Exception as backup_err:
            log_model_issue(f"[load_json] Backup failed: {backup_err}")
        return default_type()
    except Exception as e:
        log_model_issue(f"[load_json] Failed to load {filepath}: {e}")
        return default_type()
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                lock_fd.close()


class AbortModify(Exception):
    """Raise inside a modify_json block to exit cleanly without writing the file.

    Unlike other exceptions, this is expected control flow (e.g. a dedup check
    deciding not to append): modify_json skips the save, skips error logging,
    and re-raises so the caller can branch on it.
    """


@contextmanager
def modify_json(
    filepath: Union[str, Path],
    default_type: Callable[[], T] = dict,  # type: ignore[assignment]
) -> Generator[Any, None, None]:
    """
    Context manager for atomic read-modify-write.

    Holds the advisory lock across the full read → yield → write cycle so no
    concurrent writer can interleave between the read and the eventual write.

    Usage:
        with modify_json(path) as data:
            data["key"] = "new_value"
        # data is saved automatically on clean exit; not saved if an exception is raised

    Unlike calling load_json() + save_json() in sequence, this holds the lock
    throughout so two concurrent cycles cannot clobber each other's changes.
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _lock_path_for(path)
    lock_fd = None
    tmp_name: Optional[str] = None

    try:
        if fcntl is not None:
            lock_fd = open(lock_path, "w")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

        try:
            if not path.exists() or path.stat().st_size == 0:
                data: Any = default_type()
            else:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
        except Exception:
            data = default_type()

        yield data

        # Write while lock is still held
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, dir=str(path.parent), encoding="utf-8"
        ) as tmp:
            tmp_name = tmp.name
            json.dump(data, tmp, indent=2, ensure_ascii=False, default=_json_default)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
        tmp_name = None  # claimed by os.replace

    except Exception as e:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except Exception as _e:
                record_failure("json_utils.modify_json", _e)
        if not isinstance(e, AbortModify):
            log_model_issue(f"[modify_json] failed for {filepath}: {e}")
        raise
    finally:
        # Release but never unlink — the lock inode must stay stable so writers
        # and readers reliably serialize on it (see save_json).
        if fcntl is not None and lock_fd:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                lock_fd.close()


def safe_extract_json(s: Any, default: Any = None, *, dict_only: bool = False) -> Any:
    """
    Best-effort JSON parse for LLM output or already-parsed values.
    - Pass-through if s is already dict/list (unless dict_only blocks lists).
    - Falls back to json.loads() after extract_json().
    - Returns default on failure or type mismatch.
    """
    if isinstance(s, dict):
        return s
    if isinstance(s, list):
        return default if dict_only else s
    if not isinstance(s, str) or not s.strip():
        return default
    try:
        val = extract_json(s)
        if val is None:
            val = json.loads(s)
        if dict_only and not isinstance(val, dict):
            return default
        return val if val is not None else default
    except Exception:
        return default


def extract_code_block(raw: str) -> str:
    """Strip markdown fences from LLM output. Trims text before 'def think' if present."""
    if not raw:
        return ""
    s = raw.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    idx = s.find("def think")
    if idx > 0:
        s = s[idx:]
    return s


def append_jsonl(filepath: Union[str, Path], obj: Any) -> None:
    """
    Append one JSON-serialized line to a .jsonl file.
    - Ensures parent directory exists.
    - Uses advisory flock on Unix to avoid interleaved writes.
    - fsyncs to reduce data loss on crash.
    """
    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(obj, ensure_ascii=False, default=_json_default) + "\n"

        # Open in append mode; create if missing
        with open(path, "a", encoding="utf-8") as f:
            if fcntl is not None and platform.system() != "Windows":
                try:
                    fcntl.flock(f, fcntl.LOCK_EX)  # type: ignore[name-defined]
                except Exception as _e:
                    record_failure("json_utils.append_jsonl", _e)
            f.write(line)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception as _e:
                record_failure("json_utils.append_jsonl.2", _e)
            if fcntl is not None and platform.system() != "Windows":
                try:
                    fcntl.flock(f, fcntl.LOCK_UN)  # type: ignore[name-defined]
                except Exception as _e:
                    record_failure("json_utils.append_jsonl.3", _e)
    except Exception as e:
        log_model_issue(f"[append_jsonl] Failed to append to {filepath}: {e}")
