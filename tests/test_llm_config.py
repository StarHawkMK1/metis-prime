import pytest

from second_brain.config import Settings


def test_settings_has_litellm_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_LITELLM_BASE_URL", "http://localhost:4000")
    s = Settings()
    assert str(s.litellm_base_url) == "http://localhost:4000/"


def test_settings_litellm_master_key_default_is_none() -> None:
    s = Settings()
    assert s.litellm_master_key is None


def test_settings_litellm_master_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_LITELLM_MASTER_KEY", "sk-test-key")
    s = Settings()
    assert s.litellm_master_key is not None
    assert s.litellm_master_key.get_secret_value() == "sk-test-key"
