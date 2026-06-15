# tests/llm/test_no_error_leakage.py
# Verifies that LLM errors never appear in cognition/reflection outputs.

from __future__ import annotations

import json
import os
import sys
import time
import pytest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure brain/ is on the path
BRAIN_DIR = Path(__file__).resolve().parent.parent.parent / "brain"
REPO_ROOT  = Path(__file__).resolve().parent.parent.parent
if str(BRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BRAIN_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# NOTE: the root conftest points utils.generate_response.DATA_DIR at a per-test
# tmp dir, so failure counts land there — never in live brain/data state.


def _failure_counts_path() -> Path:
    import utils.generate_response as gr
    return gr.DATA_DIR / "llm_failure_counts.json"

# Strings that must never appear in cognition outputs
_LEAK_PATTERNS = [
    "currently unavailable",
    "Error code: 401",
    "Incorrect API key",
    "sk-proj-",
    "invalid_api_key",
]


def _make_401_client():
    """Return a mock OpenAI client that raises a 401-like exception."""
    from openai import AuthenticationError
    import httpx

    mock_client = MagicMock()
    mock_client.responses.create.side_effect = AuthenticationError(
        message="Incorrect API key provided: invalid-key",
        response=httpx.Response(401, request=httpx.Request("POST", "https://api.openai.com")),
        body={"error": {"message": "Incorrect API key", "type": "invalid_request_error"}},
    )
    return mock_client


def _read_failure_counts() -> dict:
    path = _failure_counts_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


@contextmanager
def _force_api_path(mock_client, key: str = "invalid-key"):
    """
    Route generate_response through the real (mocked) API path.

    generate_response has two local-answer shortcuts that skip the API: tool-only
    mode (ORRIN_LLM_TOOL_ONLY → llm_stub) and the symbolic gate. These tests verify
    the API *error-handling* path, so we disable both (and clear the response
    cache), ensuring the mocked client is actually reached.
    """
    import utils.generate_response as _gr
    _gr._GR_CACHE.clear()
    # Reset circuit breakers: the auth breaker (tripped by the 401 tests) stays
    # open for an hour and would fail-fast every later test in the module.
    _gr._cb_open_until = 0.0
    _gr._cb_auth_open_until = 0.0
    # llm_available() (LLM-as-tool gate) would short-circuit before the API when
    # llm_enabled is false in model_config.json — these tests simulate a LIVE
    # tool whose API call fails, so force the gate open.
    # The vendor call now goes through the pluggable provider (Part 11): the OpenAI
    # provider builds its OWN client, so patch _get_client at the provider boundary too
    # (and reset the resolver cache so a fresh, configured OpenAIProvider is built).
    import utils.llm_providers as _providers
    _providers.reinit()
    with patch("utils.generate_response._get_client", return_value=mock_client), \
         patch("utils.llm_providers.openai_provider.OpenAIProvider._get_client", return_value=mock_client), \
         patch("symbolic.reasoning_router.route", return_value={"resolved": False, "answer": None}), \
         patch("utils.llm_gate.llm_available", return_value=True), \
         patch.dict(os.environ, {"OPENAI_API_KEY": key, "ORRIN_LLM_TOOL_ONLY": "0"}):
        yield
    _providers.reinit()


def test_generate_response_returns_error_dict_on_401():
    """generate_response must return status=error, not leak the error as content."""
    from utils.generate_response import generate_response

    mock_client = _make_401_client()
    with _force_api_path(mock_client):
        result = generate_response("test prompt")

    assert isinstance(result, dict), "must return a dict"
    assert result["status"] == "error", f"expected error, got: {result}"
    assert result["content"] is None, "content must be None on error"
    assert result["error"] is not None, "error field must be set"
    # Error string is in the result dict, not injected into cognition
    for pattern in _LEAK_PATTERNS:
        assert pattern not in (result.get("content") or ""), \
            f"leak pattern {pattern!r} found in content"


def test_llm_ok_returns_none_and_increments_counter_on_error():
    """llm_ok must return None and increment per-caller failure count."""
    from utils.generate_response import generate_response, llm_ok

    counts_before = _read_failure_counts()
    caller = "test_no_error_leakage.test_caller"

    mock_client = _make_401_client()
    with _force_api_path(mock_client):
        result = generate_response("test prompt")

    content = llm_ok(result, caller)
    assert content is None

    counts_after = _read_failure_counts()
    assert counts_after.get(caller, 0) > counts_before.get(caller, 0), \
        "llm_failure_counts.json counter must have incremented"


def test_no_leak_patterns_in_data_files_after_error(tmp_path):
    """
    After a 401 error, no brain/data file created after test start may contain
    leak patterns like 'unavailable', '401', 'Incorrect API key', or 'sk-proj-'.
    """
    from utils.generate_response import generate_response, llm_ok

    test_start = time.time()

    mock_client = _make_401_client()
    with _force_api_path(mock_client):
        result = generate_response("What should I reflect on?")

    # Simulate a caller that would write to memory
    content = llm_ok(result, "test_leakage_caller")
    # content must be None — caller must NOT write it
    assert content is None

    # Cognition-facing files that must never contain LLM error strings.
    # Diagnostic ops logs (model_failures.txt, llm_prompt.txt) are excluded —
    # they exist precisely to record errors for operators.
    _COGNITION_FILES = [
        BRAIN_DIR / "data" / "reflection_log.json",
        BRAIN_DIR / "data" / "private_thoughts.txt",
        BRAIN_DIR / "data" / "long_memory.json",
        BRAIN_DIR / "data" / "working_memory.json",
        BRAIN_DIR / "data" / "activity_log.txt",
    ]
    violations = []
    for path in _COGNITION_FILES:
        if not path.exists():
            continue
        try:
            mtime = path.stat().st_mtime
        except Exception:
            continue
        if mtime < test_start:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern in _LEAK_PATTERNS:
            if pattern in text:
                violations.append((str(path.relative_to(BRAIN_DIR)), pattern))

    assert violations == [], (
        "Leak patterns found in files written after test start:\n"
        + "\n".join(f"  {p}: {pat!r}" for p, pat in violations)
    )


def test_generate_response_returns_ok_dict_on_success():
    """On a successful call, result must have status=ok and a non-empty content string."""
    from utils.generate_response import generate_response

    mock_response = MagicMock()
    mock_response.output_text = "I am thinking carefully."
    mock_client = MagicMock()
    mock_client.responses.create.return_value = mock_response

    with _force_api_path(mock_client, key="valid-key"):
        result = generate_response("test prompt")

    assert isinstance(result, dict)
    assert result["status"] == "ok"
    assert result["content"] == "I am thinking carefully."
    assert result["error"] is None


def test_cycle_completes_without_raising_on_401():
    """
    A minimal invocation of generate_response with a 401 must not raise —
    the error is captured in the result dict.
    """
    from utils.generate_response import generate_response

    mock_client = _make_401_client()
    with _force_api_path(mock_client):
        try:
            result = generate_response("any prompt")
        except Exception as e:
            pytest.fail(f"generate_response raised unexpectedly: {e}")

    assert result["status"] == "error"
