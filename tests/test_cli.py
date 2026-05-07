from pathlib import Path

import pytest
from typer.testing import CliRunner

runner = CliRunner()


def test_init_creates_vault_directory_structure(tmp_path: Path) -> None:
    from second_brain.cli import app

    vault = tmp_path / "test-vault"
    result = runner.invoke(app, ["init", str(vault)])

    assert result.exit_code == 0, result.output

    # SPEC §4: all required vault subdirectories
    for subdir in [
        "wiki/concepts",
        "wiki/projects",
        "wiki/people",
        "wiki/places",
        "wiki/refs",
        "wiki/maps",
        "raw/inbox",
        "raw/clips",
        "raw/transcripts",
        "raw/screenshots",
        "raw/archived",
        "tasks",
        "journal",
        "graph",
        "_meta",
    ]:
        assert (vault / subdir).is_dir(), f"Missing: {subdir}"

    # Meta files
    assert (vault / "_meta" / "schema.md").exists()
    assert (vault / "_meta" / "taxonomy.md").exists()
    assert (vault / "_meta" / "routing-policy.md").exists()
    assert (vault / "_meta" / "changelog.md").exists()

    # Vault gitignore
    assert (vault / ".gitignore").exists()

    # Git repo initialized
    assert (vault / ".git").is_dir()


def test_init_is_idempotent(tmp_path: Path) -> None:
    from second_brain.cli import app

    vault = tmp_path / "vault"
    runner.invoke(app, ["init", str(vault)])
    result = runner.invoke(app, ["init", str(vault)])
    assert result.exit_code == 0, result.output


def test_status_vault_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from second_brain.cli import app

    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path / "nonexistent"))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1


def test_status_shows_vault_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from second_brain.cli import app

    vault = tmp_path / "vault"
    runner.invoke(app, ["init", str(vault)])
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(vault))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Wiki pages" in result.output
    assert "Inbox items" in result.output


def test_note_add_creates_wiki_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from second_brain.cli import app

    vault = tmp_path / "vault"
    runner.invoke(app, ["init", str(vault)])
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(vault))

    result = runner.invoke(
        app,
        ["note", "add", "wiki/concepts/python.md", "--title", "Python"],
    )
    assert result.exit_code == 0, result.output
    assert (vault / "wiki" / "concepts" / "python.md").exists()


def test_note_add_raw_path_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from second_brain.cli import app

    vault = tmp_path / "vault"
    runner.invoke(app, ["init", str(vault)])
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(vault))

    result = runner.invoke(
        app,
        ["note", "add", "raw/inbox/bad.md", "--title", "Bad"],
    )
    assert result.exit_code != 0
