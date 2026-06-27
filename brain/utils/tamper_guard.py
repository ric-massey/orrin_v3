# utils/tamper_guard.py
from __future__ import annotations
from brain.core.runtime_log import get_logger
import hashlib
import inspect
import os
import threading
import time
from typing import Optional, Iterable
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_file(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return _sha256_bytes(f.read())
    except OSError:  # intentional: unreadable file → empty hash
        return ""


def _code_hash(func) -> str:
    try:
        code = getattr(func, "__code__", None)
        if code:
            # include bytecode + consts fingerprint
            return _sha256_bytes(code.co_code + repr(code.co_consts).encode("utf-8"))
    except Exception as _e:
        record_failure("tamper_guard._code_hash", _e)
    return ""


def _get_files_for(obj) -> list[str]:
    paths: list[str] = []
    # inspect.getsourcefile only accepts modules/classes/functions — calling it
    # on an INSTANCE (the Supervisor object) raised TypeError on every boot. Resolve
    # instances to their class first.
    candidates = []
    if inspect.ismodule(obj) or inspect.isclass(obj) or inspect.isroutine(obj):
        candidates.append(obj)
    cls = getattr(obj, "__class__", None)
    if cls is not None and cls is not type(None) and cls not in candidates:
        candidates.append(cls)
    for candidate in candidates:
        try:
            p = inspect.getsourcefile(candidate) or inspect.getfile(candidate)
            if p:
                paths.append(p)
        except TypeError:
            pass  # builtins have no source file — expected, not a warning
        except Exception as _e:
            record_failure("tamper_guard._get_files_for", _e)
    return list(dict.fromkeys([p for p in paths if p]))  # dedupe, keep order


def start_supervisor_tamper_guard(
    supervisor,
    *,
    period_s: float = 1.0,
    extra_files: Optional[Iterable[str]] = None,
    on_trip: str = "exit",  # "exit" | "raise"
) -> threading.Thread:
    """
    Monitors the supervisor object to ensure it isn't modified at runtime.
    If tampering is detected, invokes the ORIGINAL supervisor.trigger('tamper_detected')
    and then exits the process immediately (default).

    What we protect:
      - supervisor object identity
      - trigger bound to the same self (supervisor)
      - trigger function object identity
      - trigger function bytecode/consts
      - defining source files' hashes (best-effort)
    """
    if not hasattr(supervisor, "trigger") or not callable(getattr(supervisor, "trigger")):
        raise RuntimeError("supervisor object must expose a callable .trigger(reason)")

    # Capture originals
    supervisor_id = id(supervisor)
    original_trigger = supervisor.trigger
    orig_func = getattr(original_trigger, "__func__", original_trigger)
    trig_code_hash = _code_hash(orig_func)

    # Source files to watch
    file_paths = []
    file_paths += _get_files_for(supervisor)
    file_paths += _get_files_for(orig_func)
    if extra_files:
        for p in extra_files:
            if isinstance(p, str):
                file_paths.append(p)
    file_paths = list(dict.fromkeys([p for p in file_paths if p]))
    file_hashes = {p: _sha256_file(p) for p in file_paths}

    def _trip(reason: str):
        try:
            # Call the *original* trigger we captured
            original_trigger(f"tamper_detected: {reason}")
        except Exception as _e:
            record_failure("tamper_guard.start_supervisor_tamper_guard._trip", _e)
        if on_trip == "raise":
            raise SystemExit(3)
        else:
            os._exit(3)  # immediate hard-exit

    def _loop():
        while True:
            time.sleep(period_s)

            # Object replaced?
            if id(supervisor) != supervisor_id:
                _trip("supervisor_object_replaced")

            # Trigger presence
            curr_trigger = getattr(supervisor, "trigger", None)
            if not callable(curr_trigger):
                _trip("supervisor_trigger_missing")

            # Compare binding target (should still be this supervisor)
            curr_self = getattr(curr_trigger, "__self__", None)
            if curr_self is not None and curr_self is not supervisor:
                _trip("supervisor_trigger_bound_to_other_self")

            # Compare underlying function identity
            curr_func = getattr(curr_trigger, "__func__", curr_trigger)
            if curr_func is not orig_func:
                _trip("supervisor_trigger_function_replaced")

            # Compare bytecode/consts fingerprint
            if _code_hash(curr_func) != trig_code_hash:
                _trip("supervisor_trigger_code_modified")

            # Watch source files
            for p in file_paths:
                old = file_hashes.get(p, "")
                new = _sha256_file(p)
                if old and new and new != old:
                    _trip(f"source_file_modified:{p}")

    t = threading.Thread(target=_loop, name="supervisor-tamper-guard", daemon=True)
    t.start()
    return t
