# brain/idea_service.py
# Optional LLM-based idea generator hook for AliveBrain.

import os
def make_idea_hook():
    if not os.environ.get("ORRIN_USE_LLM_IDEAS"):
        return None
    # plug your client here; keep it minimal and rate-limited
    def _ideas():
        # return [{"title":"Refactor startup to async", "kind":"generic", "priority":"LOW", "spec":{}, "tags":["idea"], "score":38}]
        return []
    return _ideas
