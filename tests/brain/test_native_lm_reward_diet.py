"""P2a — reward-filter the native LM's diet.

The corpus is now a list of (text, weight) blocks: book/library prose gets a neutral
capped floor weight; experience-derived sources are weighted up and scaled by the
recent-reward channel. `train_on` samples each window's source block in proportion to
weight, and `status()` reports the realised mix.
"""
import pytest

import brain.cognition.language.native_lm as nlm
import brain.cognition.language.acquisition as acq


# ── reward channel ──────────────────────────────────────────────────────────────

def test_recent_reward_weight_maps_into_range(monkeypatch):
    # thin history → neutral 1.0
    monkeypatch.setattr(acq, "load_json", lambda *a, **k: [{"reward": 0.9}] * 3)
    assert acq._recent_reward_weight() == 1.0
    # high recent reward → toward 2.0
    monkeypatch.setattr(acq, "load_json", lambda *a, **k: [{"reward": 1.0}] * 20)
    assert acq._recent_reward_weight() == pytest.approx(2.0, abs=1e-6)
    # low recent reward → toward 1.0
    monkeypatch.setattr(acq, "load_json", lambda *a, **k: [{"reward": 0.0}] * 20)
    assert acq._recent_reward_weight() == pytest.approx(1.0, abs=1e-6)
    # mid
    monkeypatch.setattr(acq, "load_json", lambda *a, **k: [{"reward": 0.5}] * 20)
    assert acq._recent_reward_weight() == pytest.approx(1.5, abs=1e-6)


# ── corpus assembly builds weighted blocks ──────────────────────────────────────

def test_consolidate_language_builds_reward_weighted_blocks(monkeypatch):
    """Book prose gets the neutral floor weight; grounded/experience blocks are
    weighted higher and reward-scaled. Captured by stubbing train_on."""
    captured = {}

    def _cap(data, steps=60):
        captured["data"] = data
        return 1.0

    monkeypatch.setattr(nlm, "available", lambda: True)
    monkeypatch.setattr(acq.native_lm, "available", lambda: True)
    monkeypatch.setattr(acq.native_lm, "train_on", _cap)
    monkeypatch.setattr(acq.native_lm, "status",
                        lambda: {"train_steps": 1, "tokens_seen": 1})
    monkeypatch.setattr(acq, "_recent_reward_weight", lambda: 2.0)
    monkeypatch.setattr(acq, "_update_replay", lambda text: "")
    # sources: a big book block + a grounded experience block (each > _MAX slice)
    monkeypatch.setattr(acq.library, "read_text", lambda n: "book prose. " * 400)
    monkeypatch.setattr(acq, "_read_prose", lambda: "")
    monkeypatch.setattr(acq, "_conversations", lambda: "")
    monkeypatch.setattr(acq, "_signal_experience", lambda: "")
    monkeypatch.setattr(acq, "_felt_narrative", lambda: "")
    monkeypatch.setattr(acq, "_inner_monologue", lambda: "")
    monkeypatch.setattr(acq, "grounded_experience", lambda: "felt the cold and named it. " * 200)
    monkeypatch.setattr(acq, "_dialogue_experience", lambda: "")
    monkeypatch.setattr(acq, "_learned_words", lambda: "")

    acq.consolidate_language(steps=1)
    data = captured.get("data")
    assert isinstance(data, list) and data, "train_on must receive a list of (text, weight) blocks"
    weights = {}
    for text, w in data:
        if "book prose" in text:
            weights["book"] = w
        elif "felt the cold" in text:
            weights["grounded"] = w
    assert weights.get("book") == 1.0                       # neutral, capped floor
    assert weights.get("grounded") == pytest.approx(4.0)    # base 2.0 × reward 2.0
    assert weights["grounded"] > weights["book"]            # experience eats more of the diet


# ── train_on: weighted sampling + status mix ────────────────────────────────────

@pytest.fixture()
def _isolated_lm(monkeypatch, tmp_path):
    """Real train_on must NEVER touch Orrin's lifelong checkpoint: redirect the
    checkpoint path, drop the loaded model so _ensure() builds a fresh one, and
    swap _meta for a copy — otherwise these tests train junk into (and _save()
    to) the live brain/data/language/native_lm.pt, an isolation breach the
    session tripwire rightly flags."""
    monkeypatch.setattr(nlm, "_CKPT", tmp_path / "native_lm.pt")
    monkeypatch.setattr(nlm, "_model", None)
    monkeypatch.setattr(nlm, "_opt", None)
    monkeypatch.setattr(nlm, "_meta", dict(nlm._meta))
    monkeypatch.setattr(nlm, "_last_save", 0.0)
    yield


@pytest.mark.skipif(not nlm._TORCH, reason="torch unavailable")
def test_train_on_records_reward_weighted_mix(_isolated_lm):
    # long-enough blocks with distinct weights
    a = "alpha beta gamma delta epsilon zeta eta theta. " * 80
    b = "one two three four five six seven eight nine ten. " * 80
    loss = nlm.train_on([(a, 1.0), (b, 4.0)], steps=2, batch=2)
    assert loss is None or isinstance(loss, float)
    st = nlm.status()
    if st.get("available") and st.get("training_mix"):
        mix = st["training_mix"]
        assert mix["reward_weighted"] is True
        assert mix["blocks"] >= 1


@pytest.mark.skipif(not nlm._TORCH, reason="torch unavailable")
def test_train_on_legacy_str_is_unweighted(_isolated_lm):
    text = "the quick brown fox jumps over the lazy dog. " * 120
    nlm.train_on(text, steps=1, batch=2)
    st = nlm.status()
    if st.get("available") and st.get("training_mix"):
        assert st["training_mix"]["reward_weighted"] is False
