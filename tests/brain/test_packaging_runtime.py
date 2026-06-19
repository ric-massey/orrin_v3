"""Group I freeze-prep: the embedded-interpreter resolver (I1, §10.2) and the bundled
ML-weights wiring (I2, Part 4). Both must be no-ops in a dev checkout and honor explicit
overrides — that's what lets the SAME code run from source and survive freezing.

Runs under conftest's ORRIN_DATA_DIR isolation.
"""
import sys


from utils import runtime_python as rp
from utils import model_assets as ma


# ── I1: embedded interpreter resolver ────────────────────────────────────────
def test_interpreter_is_sys_executable_in_dev(monkeypatch):
    monkeypatch.delenv("ORRIN_EMBEDDED_PYTHON", raising=False)
    # Dev checkout: not frozen, no bundle → the real interpreter.
    assert rp.interpreter() == sys.executable
    assert rp.using_embedded() is False
    assert rp.is_frozen() is False


def test_embedded_python_override_respected(monkeypatch, tmp_path):
    fake = tmp_path / "python3"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setenv("ORRIN_EMBEDDED_PYTHON", str(fake))
    assert rp.embedded_python() == fake
    assert rp.interpreter() == str(fake)
    assert rp.using_embedded() is True


def test_embedded_python_override_ignored_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("ORRIN_EMBEDDED_PYTHON", str(tmp_path / "does-not-exist"))
    assert rp.embedded_python() is None
    assert rp.interpreter() == sys.executable  # falls back, never breaks


def test_sandbox_uses_resolved_interpreter():
    # The sandbox actually runs code through the resolver — a trivial snippet returns ok.
    from behavior.tools.sandbox import run_python_sandboxed
    out = run_python_sandboxed("print(1 + 1)", timeout_s=10)
    assert out["status"] == "ok"
    assert out["stdout"].strip() == "2"


# ── I2: bundled ML weights wiring ────────────────────────────────────────────
def test_models_dir_none_in_dev(monkeypatch):
    monkeypatch.delenv("ORRIN_MODELS_DIR", raising=False)
    assert ma.models_dir() is None
    assert ma.apply_offline_env() is False
    # spaCy loads the pip-installed package by NAME in dev (no bundled path).
    assert ma.spacy_model("en_core_web_sm") == "en_core_web_sm"


def test_models_dir_override_and_offline_env(monkeypatch, tmp_path):
    (tmp_path / "hf").mkdir()
    (tmp_path / "sentence_transformers").mkdir()
    (tmp_path / "spacy" / "en_core_web_sm").mkdir(parents=True)
    monkeypatch.setenv("ORRIN_MODELS_DIR", str(tmp_path))
    # Clear any inherited HF env so setdefault actually writes our bundled paths.
    for k in ("HF_HOME", "SENTENCE_TRANSFORMERS_HOME", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        monkeypatch.delenv(k, raising=False)

    assert ma.models_dir() == tmp_path
    assert ma.apply_offline_env() is True

    import os
    assert os.environ["SENTENCE_TRANSFORMERS_HOME"] == str(tmp_path / "sentence_transformers")
    assert os.environ["HF_HOME"] == str(tmp_path / "hf")
    assert os.environ["HF_HUB_OFFLINE"] == "1" and os.environ["TRANSFORMERS_OFFLINE"] == "1"
    # spaCy now resolves to the BUNDLED model path, not the package name.
    assert ma.spacy_model("en_core_web_sm") == str(tmp_path / "spacy" / "en_core_web_sm")
