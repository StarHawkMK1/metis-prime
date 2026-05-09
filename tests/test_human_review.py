from __future__ import annotations

from pathlib import Path

import pytest

from second_brain.storage import Vault


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    import pygit2

    repo = pygit2.init_repository(str(tmp_path))
    sig = pygit2.Signature("Test", "t@t.com")
    tree = repo.TreeBuilder().write()
    repo.create_commit("refs/heads/main", sig, sig, "init", tree, [])
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    return tmp_path


def test_process_review_moves_accepted_to_wiki(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.human_review import process_review

    vault = Vault(tmp_vault)
    pending = tmp_vault / "human_review" / "pending"
    accepted = tmp_vault / "human_review" / "accepted"
    pending.mkdir(parents=True)
    accepted.mkdir(parents=True)

    # Write a draft page to accepted/
    (accepted / "my-concept.md").write_text(
        "# Review Required: My Concept\n\n**Reason:** inferred provenance > 70%\n\n"
        "**Source:** raw/inbox/source.md\n\nSome body content.",
        encoding="utf-8",
    )

    result = process_review(vault)
    assert result.accepted == 1
    assert result.rejected == 0
    assert not (accepted / "my-concept.md").exists()
    # File moved to wiki
    wiki_page = tmp_vault / "wiki" / "concepts" / "my-concept.md"
    assert wiki_page.exists()


def test_process_review_deletes_rejected(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.human_review import process_review

    vault = Vault(tmp_vault)
    rejected = tmp_vault / "human_review" / "rejected"
    rejected.mkdir(parents=True)
    (rejected / "bad-page.md").write_text("# Bad\n\nContent.", encoding="utf-8")

    result = process_review(vault)
    assert result.rejected == 1
    assert not (rejected / "bad-page.md").exists()
