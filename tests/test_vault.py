from pathlib import Path

import pygit2
import pytest
from second_brain.config import Settings
from second_brain.storage.frontmatter import ProvenanceBreakdown, WikiPage
from second_brain.storage.git_ops import auto_commit, init_repo
from second_brain.storage.vault import Vault


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


def test_write_page_creates_file(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    page = WikiPage(title="Test Concept", type="concept")
    path = vault.write_page("wiki/concepts/test.md", page)
    assert path.exists()


def test_write_page_roundtrip_via_read(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    page = WikiPage(title="Hello World", type="concept", body="Content here.")
    vault.write_page("wiki/concepts/hello.md", page)
    loaded = vault.read_page("wiki/concepts/hello.md")
    assert loaded.title == "Hello World"
    assert loaded.body == "Content here."


def test_list_pages_returns_md_files(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page("wiki/concepts/a.md", WikiPage(title="A", type="concept"))
    vault.write_page("wiki/concepts/b.md", WikiPage(title="B", type="ref"))
    pages = vault.list_pages()
    assert len(pages) == 2


def test_list_pages_empty_returns_empty_list(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    assert vault.list_pages() == []


def test_write_to_raw_raises_runtime_error(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    page = WikiPage(title="Forbidden", type="concept")
    with pytest.raises(RuntimeError, match="Cannot write to raw/"):
        vault.write_page("raw/inbox/forbidden.md", page)


def test_write_page_auto_commits(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page("wiki/concepts/test.md", WikiPage(title="T", type="concept"))
    repo = pygit2.Repository(str(tmp_vault))
    commits = list(repo.walk(repo.head.target))
    # init commit + write commit = 2
    assert len(commits) >= 2
    assert "write:" in commits[0].message
