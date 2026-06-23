"""
brain/utils/env.py — environment-variable parsing helpers.

A single home for the boolean-flag idiom that was hand-rolled ~17 times across
the tree as ``os.getenv(name, default).strip().lower() in (...)`` /
``not in (...)``. Those call sites used several slightly different token tuples
(some listed ``"off"``, some didn't; some ``"on"``, some didn't), but every one
shared the same fall-through rule: an unset, empty, or unrecognized value yields
the caller's default. ``env_bool`` canonicalizes that on the full standard token
set so the meaning lives in one place.
"""
from __future__ import annotations

import os

# The conventional truthy / falsy spellings, recognized everywhere.
_TRUE_TOKENS = ("1", "true", "yes", "on")
_FALSE_TOKENS = ("0", "false", "no", "off")


def env_bool(name: str, default: bool = False) -> bool:
    """Interpret environment variable ``name`` as a boolean.

    Returns ``True`` for ``1/true/yes/on`` and ``False`` for ``0/false/no/off``
    (case-insensitive, surrounding whitespace ignored). An unset, empty, or
    unrecognized value returns ``default`` — matching the behavior of the
    per-call-site idioms this replaces, where ``""`` appeared in neither the
    truthy nor falsy tuple and therefore fell through to the default.

    Compose the *meaning* at the call site:

        if env_bool("ORRIN_FEATURE", True):  ...   # default-on flag
        if env_bool("ORRIN_FEATURE"):        ...   # default-off flag
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in _TRUE_TOKENS:
        return True
    if v in _FALSE_TOKENS:
        return False
    return default
