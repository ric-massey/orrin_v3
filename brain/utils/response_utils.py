def generate_response_from_context(context: dict) -> str:
    try:
        from utils.generate_response import generate_response, llm_ok
        from utils.coerce_to_string import coerce_to_string
        from cognition.selfhood.identity import build_system_prompt
        from utils.json_utils import load_json
        from utils.log import log_model_issue
        from paths import MODEL_CONFIG_FILE
        from utils.self_model import get_self_model

        ctx = context or {}

        instructions = ctx.get("instructions", "Think based on the following context.")
        prompt = coerce_to_string(instructions)

        system_prompt = ctx.get("system_prompt")
        if not isinstance(system_prompt, str):
            try:
                system_prompt = build_system_prompt(get_self_model())
            except Exception as e:
                log_model_issue(f"[generate_response_from_context] Failed to build system prompt: {e}")
                system_prompt = "You are a thoughtful, reflective intelligence."
        system_prompt = coerce_to_string(system_prompt)

        cfg = load_json(MODEL_CONFIG_FILE, default_type=dict) or {}
        default_key = cfg.get("default", "thinking")
        base_role_cfg = cfg.get(default_key, {}) if isinstance(cfg.get(default_key), dict) else {}

        inline_role = {
            "model":       base_role_cfg.get("model", "gpt-4.1"),
            "temperature": base_role_cfg.get("temperature", 0.85),
            "max_tokens":  base_role_cfg.get("max_tokens", 32000),
            "system_prompt": system_prompt,
        }
        inline_cfg = {"default": "inline", "inline": inline_role}

        result = generate_response(prompt, config=inline_cfg)
        content = llm_ok(result, "response_utils.generate_response_from_context")
        return content or ""

    except Exception as e:
        from utils.log import log_model_issue
        log_model_issue(f"[generate_response_from_context] Failed: {e}")
        return ""
