import pytest
from second_brain.config import Settings


def test_settings_defaults() -> None:
    s = Settings()
    assert s.log_level == "INFO"
    assert s.local_only is False


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("SECOND_BRAIN_LOCAL_ONLY", "true")
    s = Settings()
    assert s.log_level == "DEBUG"
    assert s.local_only is True


def test_settings_vault_path_default() -> None:
    s = Settings()
    assert "second-brain-vault" in str(s.vault_path)
