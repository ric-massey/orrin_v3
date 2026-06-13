
from utils.load_utils import load_model_config
from utils.log import log_error  # optional: for diagnostic logging

model_roles = load_model_config()

# Ensure model_roles is a dict
if not isinstance(model_roles, dict):
    log_error("⚠️ load_model_config() returned a non-dict. Defaulting to empty config.")
    model_roles = {}

# Defaults match what's in model_config.json. fast = cheap calls, thinking = main reasoning,
# deep = escalation / judge paths only.
model_roles.setdefault("thinking", "gpt-4.1")
model_roles.setdefault("human_facing", "gpt-4.1")
model_roles.setdefault("fast", "gpt-4o-mini")
model_roles.setdefault("deep", "gpt-4.1")