# E6 — the bridge rebinds the live telemetry stream when the view re-attaches (F1:
# window hidden then re-shown, or a freshly created window). Built with __new__ so we
# don't spin up the FastAPI app's TestClient (its lifespan boots cognition). The hub
# is the module singleton; we only assert on what reaches the (fake) window.
from backend.server import bridge as br_mod


class _FakeWindow:
    def __init__(self):
        self.pushes = []

    def evaluate_js(self, s):
        self.pushes.append(s)


def _make():
    b = br_mod.OrrinBridge.__new__(br_mod.OrrinBridge)
    b._window = None
    b._subscribed = False
    return b


def test_reattach_pushes_fresh_snapshot_to_new_window():
    b = _make()
    b._subscribed = True  # stream already live (this is a re-attach, not a first subscribe)
    w = _FakeWindow()
    b.attach_window(w)
    assert len(w.pushes) == 1  # a fresh snapshot, so the re-shown view is current at once
    assert "__orrinPush" in w.pushes[0]


def test_attach_without_subscription_does_not_push():
    b = _make()
    w = _FakeWindow()
    b.attach_window(w)  # no stream yet → nothing to re-point
    assert w.pushes == []


def test_detach_makes_push_a_noop():
    b = _make()
    b._subscribed = True
    w = _FakeWindow()
    b.attach_window(w)  # 1 snapshot
    b.detach_window()
    # A later hub delta must not blow up and must not reach the detached window.
    b._push({"type": "delta", "frame": {}})
    assert len(w.pushes) == 1  # only the attach-time snapshot; nothing after detach
