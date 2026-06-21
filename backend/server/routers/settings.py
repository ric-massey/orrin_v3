"""Settings / secrets / LLM-provider control routes.

Split out of app.py (Phase 4C). Owner-only control surfaces — each handler
self-authorizes via auth.authorize_control and is mounted directly on the app
(not under the read-token api router). Brain modules are imported lazily inside
the handlers, exactly as in app.py.
"""
from __future__ import annotations

import contextlib
from typing import Any, Dict

from fastapi import APIRouter, Request

from ..auth import authorize_control

router = APIRouter()


@router.get("/api/settings")
async def get_settings(request: Request) -> Dict[str, Any]:
    authorize_control(request)
    from brain.utils import secrets as _secrets
    from brain.utils import prefs as _prefs
    cfg = _secrets.configured()
    try:
        from brain.cognition.mortality import lifespan_rolled as _rolled
        rolled = _rolled()
    except Exception:
        rolled = False
    # Pluggable LLM providers (Part 11): the menu + the current selection, so Settings
    # can render the single-select. Never exposes a key value — only which are set.
    try:
        from brain.utils import llm_providers as _providers
        _prov_catalog = _providers.catalog()
        _selected = _providers.selected_id()
    except Exception:
        _prov_catalog, _selected = [], "openai"
    try:
        from version import current_version as _ver
        _version = _ver()
    except Exception:
        _version = ""
    # Embodiment (§11): the budget/floor the slider renders against, plus the resulting
    # metabolic tier and where Orrin is in infancy — so the UI can explain what the
    # grant means (his body size, his metabolism, the non-overridable host floor).
    embodiment: Dict[str, Any] = {}
    try:
        from brain.cognition.body_budget import budget_status as _bs
        from brain.cognition.metabolism import metabolism_status as _ms
        from brain.cognition.infancy import infancy_status as _is
        embodiment = {"budget": _bs(), "metabolism": _ms(), "infancy": _is()}
    except Exception:
        embodiment = {}
    return {
        "configured": cfg,
        "symbolic_only": not cfg.get("openai", False),
        "prefs": _prefs.all_prefs(),
        "lifespan_rolled": rolled,
        "version": _version,
        "embodiment": embodiment,
        "llm": {
            "providers": _prov_catalog,
            "selected": _selected,
        },
    }


@router.post("/api/settings")
async def update_settings(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Store/clear API keys in the OS keychain. Body keys (all optional):
    `openai_api_key`, `serper_api_key` — an empty string clears that key. Saving the
    OpenAI key re-inits the cached client so it takes effect without a restart."""
    authorize_control(request)
    from brain.utils import secrets as _secrets

    payload = payload or {}
    changed: list[str] = []
    needs_reinit = False

    # API keys (any provider) — `<name>_api_key`; an empty string clears it.
    for _name in _secrets.ENV_VARS:
        _field = f"{_name}_api_key"
        if _field in payload:
            _secrets.set_key(_name, payload.get(_field))
            changed.append(_name)
            if _name != "serper":  # serper is read per-call from env; needs no re-init
                needs_reinit = True

    # Non-secret toggles + LLM provider selection → config.json.
    from brain.utils import prefs as _prefs
    incoming_prefs = payload.get("prefs")
    budget_result: Dict[str, Any] | None = None
    if isinstance(incoming_prefs, dict):
        for k, v in incoming_prefs.items():
            # The body budget (§11) routes through its validating setter, NOT a raw
            # prefs.set: it refuses an unviable grant loudly (§11.4.3) and a meaningful
            # resize re-enters a partial somatic infancy (§11.4.2). Skip the generic path.
            if k == "body_budget_fraction":
                from brain.cognition.body_budget import set_budget_fraction
                budget_result = set_budget_fraction(v)
                if budget_result.get("ok"):
                    changed.append("pref:body_budget_fraction")
                continue
            if k in _prefs.DEFAULTS:
                _prefs.set(k, bool(v) if isinstance(_prefs.DEFAULTS[k], bool) else v)
                changed.append(f"pref:{k}")
                if k in ("llm_provider", "llm_model", "llm_base_url"):
                    needs_reinit = True

    if needs_reinit:
        # A new key / provider / model takes effect without a restart: drop the cached
        # provider (Part 11) and flip the master LLM switch on when a real provider is
        # now selected, so the tool becomes reachable (llm_gate).
        with contextlib.suppress(Exception):
            from brain.utils.generate_response import reinit_client
            reinit_client()
        with contextlib.suppress(Exception):
            from brain.utils import llm_providers as _providers
            from brain.utils.json_utils import load_json as _lj, save_json as _sj
            from brain.paths import MODEL_CONFIG_FILE as _mcf
            _mc = _lj(_mcf, default_type=dict) or {}
            _mc["llm_enabled"] = _providers.selected_id() != "none"
            _sj(_mcf, _mc)

    cfg = _secrets.configured()
    resp = {
        "ok": True,
        "changed": changed,
        "configured": cfg,
        "symbolic_only": not cfg.get("openai", False),
        "prefs": _prefs.all_prefs(),
    }
    # Surface a budget refusal (or applied resize) so the slider can show it (§11.4.3).
    if budget_result is not None:
        resp["body_budget"] = budget_result
        if not budget_result.get("ok"):
            resp["ok"] = False
            resp["body_budget_error"] = budget_result.get("reason")
    return resp


@router.post("/api/llm/test")
async def llm_test(request: Request) -> Dict[str, Any]:
    """Test connection (§11.1): a cheap round-trip with the currently-selected provider
    so the user can confirm a key/endpoint/model works before relying on it."""
    authorize_control(request)
    from brain.utils import llm_providers as _providers
    provider = _providers.resolve()
    if provider is None:
        return {"ok": False, "message": "No provider selected (symbolic-only)."}
    if not provider.is_configured():
        return {"ok": False, "message": "This provider isn't configured yet (add a key or endpoint)."}
    ok, message = provider.test_connection()
    return {"ok": bool(ok), "message": message, "provider": provider.id, "model": provider.model}
