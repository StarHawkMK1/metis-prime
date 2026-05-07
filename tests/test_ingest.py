from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from second_brain.agents.ingest import IngestAgent
from second_brain.storage import Vault, WikiPage


def _make_llm_response(
    decision: str = "create",
    title: str = "Test Concept",
    page_type: str = "concept",
    body: str = "A one-sentence definition.\n\nMore detail here.",
    target_page: str = "",
) -> str:
    return json.dumps(
        {
            "decision": decision,
            "title": title,
            "type": page_type,
            "body": body,
            "sources": ["raw/inbox/source.md"],
            "provenance": {"extracted": 70, "inferred": 25, "ambiguous": 5},
            "wikilinks": [],
            "tags": ["ai"],
            "target_page": target_page,
        }
    )


def test_ingest_creates_new_page(tmp_vault: Path) -> None:
    source = tmp_vault / "raw" / "inbox" / "source.md"
    source.write_text("# AI Basics\n\nArticle about AI.", encoding="utf-8")
    _stage_file(tmp_vault, "raw/inbox/source.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _make_llm_response()

    vault = Vault(tmp_vault)
    agent = IngestAgent(vault=vault, router=mock_router)
    result = agent.run("raw/inbox/source.md")

    assert result.decision == "create"
    assert result.wiki_path is not None
    assert vault.page_exists(result.wiki_path)


def test_ingest_archives_source(tmp_vault: Path) -> None:
    source = tmp_vault / "raw" / "inbox" / "clip.md"
    source.write_text("# Clip\n\nSome content.", encoding="utf-8")
    _stage_file(tmp_vault, "raw/inbox/clip.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _make_llm_response(title="Clip Content")

    vault = Vault(tmp_vault)
    result = IngestAgent(vault=vault, router=mock_router).run("raw/inbox/clip.md")

    assert not source.exists()
    assert result.archived_path.exists()
    assert "archived" in str(result.archived_path)


def test_ingest_commits_to_git(tmp_vault: Path) -> None:
    import pygit2

    source = tmp_vault / "raw" / "inbox" / "note.md"
    source.write_text("# Note\n\nContent.", encoding="utf-8")
    _stage_file(tmp_vault, "raw/inbox/note.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _make_llm_response(title="Note Concept")

    vault = Vault(tmp_vault)
    IngestAgent(vault=vault, router=mock_router).run("raw/inbox/note.md")

    repo = pygit2.Repository(str(tmp_vault))
    messages = [c.message for c in repo.walk(repo.head.target)]
    assert any("ingest:" in m for m in messages)


def test_ingest_skip_decision_no_wiki_page(tmp_vault: Path) -> None:
    source = tmp_vault / "raw" / "inbox" / "dup.md"
    source.write_text("# Dup\n\nDuplicate content.", encoding="utf-8")
    _stage_file(tmp_vault, "raw/inbox/dup.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _make_llm_response(decision="skip", title="Dup")

    vault = Vault(tmp_vault)
    result = IngestAgent(vault=vault, router=mock_router).run("raw/inbox/dup.md")

    assert result.decision == "skip"
    assert result.wiki_path is None
    # source still archived even on skip
    assert result.archived_path.exists()


def test_ingest_merge_decision_updates_page(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    existing = vault.write_page(
        "wiki/concepts/ai.md",
        WikiPage(title="Artificial Intelligence", type="concept", body="Initial content."),
    )
    assert existing.exists()

    source = tmp_vault / "raw" / "inbox" / "ai-update.md"
    source.write_text("# AI Update\n\nNew info about AI.", encoding="utf-8")
    _stage_file(tmp_vault, "raw/inbox/ai-update.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _make_llm_response(
        decision="merge",
        title="Artificial Intelligence",
        body="Initial content.\n\nNew info about AI.",
        target_page="ai",
    )

    result = IngestAgent(vault=vault, router=mock_router).run("raw/inbox/ai-update.md")
    assert result.decision == "merge"
    assert result.wiki_path == "wiki/concepts/ai.md"
    updated = vault.read_page("wiki/concepts/ai.md")
    assert "New info about AI." in updated.body


def test_ingest_invalid_json_raises(tmp_vault: Path) -> None:
    from second_brain.agents.ingest import IngestError

    source = tmp_vault / "raw" / "inbox" / "bad.md"
    source.write_text("content", encoding="utf-8")
    _stage_file(tmp_vault, "raw/inbox/bad.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = "NOT VALID JSON AT ALL"

    vault = Vault(tmp_vault)
    with pytest.raises(IngestError, match="[Ff]ailed to parse"):
        IngestAgent(vault=vault, router=mock_router).run("raw/inbox/bad.md")


# ── helpers ──────────────────────────────────────────────────────────────────


def _stage_file(vault_path: Path, rel: str) -> None:
    """Stage a newly written raw file so pygit2 can track its removal."""
    import pygit2

    repo = pygit2.Repository(str(vault_path))
    idx = repo.index
    idx.read()
    idx.add(rel)
    idx.write()
    sig = pygit2.Signature("Test", "t@t.com")
    tree = idx.write_tree()
    repo.create_commit("refs/heads/main", sig, sig, f"add {rel}", tree, [repo.head.target])
