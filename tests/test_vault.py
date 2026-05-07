from pathlib import Path

import pygit2
import pytest

from second_brain.config import Settings
from second_brain.storage.frontmatter import ProvenanceBreakdown, WikiPage
from second_brain.storage.git_ops import auto_commit, init_repo


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


def test_wiki_page_defaults() -> None:
    page = WikiPage(title="Test", type="concept")
    assert page.status == "draft"
    assert page.tags == []
    assert page.body == ""
    assert page.provenance.extracted == 70


def test_wiki_page_to_markdown_has_frontmatter() -> None:
    page = WikiPage(title="Python Basics", type="concept", body="Python is a language.")
    md = page.to_markdown()
    assert "title: Python Basics" in md
    assert "type: concept" in md
    assert "Python is a language." in md


def test_wiki_page_roundtrip() -> None:
    original = WikiPage(
        title="Machine Learning",
        type="concept",
        tags=["ai", "learning"],
        sources=["raw/clips/ml-intro.md"],
        body="ML is a subfield of AI.",
    )
    md = original.to_markdown()
    loaded = WikiPage.from_markdown(md)
    assert loaded.title == "Machine Learning"
    assert loaded.type == "concept"
    assert loaded.tags == ["ai", "learning"]
    assert loaded.sources == ["raw/clips/ml-intro.md"]
    assert loaded.body == "ML is a subfield of AI."


def test_provenance_breakdown_defaults() -> None:
    p = ProvenanceBreakdown()
    assert p.extracted + p.inferred + p.ambiguous == 100


def test_init_repo_creates_git_directory(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    init_repo(target)
    assert (target / ".git").is_dir()


def test_init_repo_head_is_born(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    init_repo(target)
    repo = pygit2.Repository(str(target))
    assert not repo.head_is_unborn


def test_init_repo_creates_initial_commit(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    init_repo(target)
    repo = pygit2.Repository(str(target))
    commits = list(repo.walk(repo.head.target))
    assert len(commits) == 1
    assert "init" in commits[0].message


def test_auto_commit_stages_file_and_commits(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    init_repo(target)

    test_file = target / "note.md"
    test_file.write_text("hello", encoding="utf-8")
    auto_commit(target, "test: add note", [test_file])

    repo = pygit2.Repository(str(target))
    commits = list(repo.walk(repo.head.target))
    assert len(commits) == 2
    assert commits[0].message == "test: add note"


def test_auto_commit_noop_on_empty_paths(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    init_repo(target)
    # Should not raise and not create an extra commit
    auto_commit(target, "noop", [])
    repo = pygit2.Repository(str(target))
    commits = list(repo.walk(repo.head.target))
    assert len(commits) == 1
