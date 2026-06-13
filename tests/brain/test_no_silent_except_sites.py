# Finding 2: the 646 `_log.warning("silent except: %s", _e)` sites in brain/
# were converted to named `record_failure("module.function[.N]", _e)`
# handlers (utils.failure_counter). This guards against the anti-pattern
# creeping back in. brain/utils/failure_counter.py itself is exempt — its
# own internal IO failures can't call record_failure recursively.
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXEMPT = {_REPO_ROOT / "brain" / "utils" / "failure_counter.py"}


def test_no_leftover_silent_except_sites_in_brain():
    offenders = []
    for path in (_REPO_ROOT / "brain").rglob("*.py"):
        if path in _EXEMPT:
            continue
        if '"silent except: %s"' in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert offenders == []
