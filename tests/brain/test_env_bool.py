"""Unit tests for brain.utils.env.env_bool — the consolidated env-flag helper."""
import pytest

from brain.utils.env import env_bool

_VAR = "ORRIN_TEST_ENV_BOOL_FLAG"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(_VAR, raising=False)


def test_unset_returns_default(monkeypatch):
    assert env_bool(_VAR) is False
    assert env_bool(_VAR, default=True) is True


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on", " On ", "Y\tES".replace("\t", "")])
def test_truthy_tokens(monkeypatch, raw):
    monkeypatch.setenv(_VAR, raw)
    assert env_bool(_VAR, default=False) is True


@pytest.mark.parametrize("raw", ["0", "false", "FALSE", "no", "off", " Off "])
def test_falsy_tokens(monkeypatch, raw):
    monkeypatch.setenv(_VAR, raw)
    assert env_bool(_VAR, default=True) is False


@pytest.mark.parametrize("raw", ["", "   ", "maybe", "2", "garbage"])
def test_empty_or_unrecognized_falls_through_to_default(monkeypatch, raw):
    """The behavior the per-call-site idioms shared: "" / unknown → default."""
    monkeypatch.setenv(_VAR, raw)
    assert env_bool(_VAR, default=True) is True
    assert env_bool(_VAR, default=False) is False
