from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pygit2
import pytest

from second_brain.storage import Vault, WikiPage


def _llm_response(
    decision: str = "create",
    title: str = "Test Concept",
    page_type: str = "concept",
    body: str = "A one-sentence definition.",
    target_page: str = "",
    inferred: int = 20,
) -> str:
    extracted = 100 - inferred - 5
    return json.dumps(
        {
            "decision": decision,
            "title": title,
            "type": page_type,
            "body": body,
            "provenance": {"extracted": extracted, "inferred": inferred, "ambiguous": 5},
            "wikilinks": [],
            "tags": [],
            "target_page": target_page,
        }
    )


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    repo = pygit2.init_repository(str(tmp_path))
    sig = pygit2.Signature("Test", "t@t.com")
    tree = repo.TreeBuilder().write()
    repo.create_commit("refs/heads/main", sig, sig, "init", tree, [])
    (tmp_path / "raw" / "inbox").mkdir(parents=True)
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    return tmp_path


def _stage(vault_path: Path, rel: str) -> None:
    repo = pygit2.Repository(str(vault_path))
    idx = repo.index
    idx.read()
    idx.add(rel)
    idx.write()
    sig = pygit2.Signature("Test", "t@t.com")
    tree = idx.write_tree()
    repo.create_commit("refs/heads/main", sig, sig, f"add {rel}", tree, [repo.head.target])


def test_ingest_graph_creates_page(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.ingest_graph import IngestGraph

    source = tmp_vault / "raw" / "inbox" / "note.md"
    source.write_text("# Note\n\nContent.", encoding="utf-8")
    _stage(tmp_vault, "raw/inbox/note.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _llm_response()
    mock_router.get_last_cost.return_value = 0.001

    vault = Vault(tmp_vault)
    result = IngestGraph(vault=vault, router=mock_router).run("raw/inbox/note.md")

    assert result.decision == "create"
    assert result.wiki_path is not None
    assert vault.page_exists(result.wiki_path)


def test_ingest_graph_archives_source(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.ingest_graph import IngestGraph

    source = tmp_vault / "raw" / "inbox" / "clip.md"
    source.write_text("# Clip\n\nContent.", encoding="utf-8")
    _stage(tmp_vault, "raw/inbox/clip.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _llm_response(title="Clip")
    mock_router.get_last_cost.return_value = 0.0

    vault = Vault(tmp_vault)
    result = IngestGraph(vault=vault, router=mock_router).run("raw/inbox/clip.md")

    assert not source.exists()
    assert result.archived_path.exists()


def test_ingest_graph_routes_high_inferred_to_review(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.ingest_graph import IngestGraph

    source = tmp_vault / "raw" / "inbox" / "risky.md"
    source.write_text("# Risky\n\nSpeculative content.", encoding="utf-8")
    _stage(tmp_vault, "raw/inbox/risky.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _llm_response(inferred=80)
    mock_router.get_last_cost.return_value = 0.0

    vault = Vault(tmp_vault)
    result = IngestGraph(vault=vault, router=mock_router).run("raw/inbox/risky.md")

    review_dir = tmp_vault / "human_review" / "pending"
    assert result.wiki_path is None
    assert not vault.page_exists("wiki/concepts/risky.md")
    assert review_dir.exists() and any(review_dir.iterdir())


def test_ingest_graph_skip_no_wiki_page(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.ingest_graph import IngestGraph

    source = tmp_vault / "raw" / "inbox" / "dup.md"
    source.write_text("# Dup\n\nDuplicate.", encoding="utf-8")
    _stage(tmp_vault, "raw/inbox/dup.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _llm_response(decision="skip")
    mock_router.get_last_cost.return_value = 0.0

    vault = Vault(tmp_vault)
    result = IngestGraph(vault=vault, router=mock_router).run("raw/inbox/dup.md")

    assert result.decision == "skip"
    assert result.wiki_path is None
    assert result.archived_path.exists()


def test_ingest_graph_cross_links_referenced_page(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.ingest_graph import IngestGraph

    # Create a target page that the new page will link to
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/existing-topic.md",
        WikiPage(title="Existing Topic", type="concept", body="Existing content."),
    )

    source = tmp_vault / "raw" / "inbox" / "new.md"
    source.write_text("# New\n\nRefs existing.", encoding="utf-8")
    _stage(tmp_vault, "raw/inbox/new.md")

    response = json.dumps(
        {
            "decision": "create",
            "title": "New Topic",
            "type": "concept",
            "body": "Links to existing.",
            "provenance": {"extracted": 75, "inferred": 20, "ambiguous": 5},
            "wikilinks": ["existing-topic"],
            "tags": [],
            "target_page": "",
        }
    )
    mock_router = MagicMock()
    mock_router.complete.return_value = response
    mock_router.get_last_cost.return_value = 0.0

    IngestGraph(vault=vault, router=mock_router).run("raw/inbox/new.md")

    existing_content = vault.read_raw_text("wiki/concepts/existing-topic.md")
    assert "[[new-topic]]" in existing_content
