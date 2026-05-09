from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from second_brain.storage import Vault, WikiPage


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    import pygit2

    repo = pygit2.init_repository(str(tmp_path))
    sig = pygit2.Signature("Test", "t@t.com")
    tree = repo.TreeBuilder().write()
    repo.create_commit("refs/heads/main", sig, sig, "init", tree, [])
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    return tmp_path


def test_query_graph_returns_answer(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.query_graph import QueryGraph

    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/rag.md",
        WikiPage(
            title="RAG", type="concept", body="Retrieval Augmented Generation is a technique."
        ),
    )

    mock_router = MagicMock()
    # First call: classify intent → "factual"
    # Second call: answer
    mock_router.complete.side_effect = [
        '{"intent": "factual"}',
        "RAG stands for Retrieval Augmented Generation.",
    ]
    mock_router.get_last_cost.return_value = 0.001

    graph = QueryGraph(vault=vault, router=mock_router)
    result = graph.ask("What is RAG?")

    assert "RAG" in result.answer or len(result.answer) > 0


def test_query_graph_synthesis_intent(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.query_graph import QueryGraph

    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/ml.md",
        WikiPage(title="ML", type="concept", body="Machine learning uses data."),
    )

    mock_router = MagicMock()
    mock_router.complete.side_effect = ['{"intent": "synthesis"}', "Synthesis answer here."]
    mock_router.get_last_cost.return_value = 0.002

    graph = QueryGraph(vault=vault, router=mock_router)
    result = graph.ask("Explain how ML and AI relate?")

    assert len(result.answer) > 0


def test_query_graph_no_context_still_answers(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.query_graph import QueryGraph

    vault = Vault(tmp_vault)
    mock_router = MagicMock()
    mock_router.complete.side_effect = ['{"intent": "factual"}', "I don't have relevant pages."]
    mock_router.get_last_cost.return_value = 0.0

    graph = QueryGraph(vault=vault, router=mock_router)
    result = graph.ask("What is the capital of France?")

    assert len(result.answer) > 0
