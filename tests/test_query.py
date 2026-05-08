from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from second_brain.agents.query import QueryAgent, QueryResult
from second_brain.storage import Vault, WikiPage


@pytest.fixture()
def wiki_vault(tmp_vault: Path) -> Vault:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/transformers.md",
        WikiPage(
            title="Transformers",
            type="concept",
            body="Transformers are a neural network architecture using self-attention.",
        ),
    )
    vault.write_page(
        "wiki/concepts/bert.md",
        WikiPage(
            title="BERT",
            type="concept",
            body="BERT is a pre-trained transformer model for NLP tasks.",
        ),
    )
    return vault


def test_query_returns_answer(wiki_vault: Vault) -> None:
    mock_router = MagicMock()
    mock_router.complete.return_value = (
        "Transformers use self-attention [[transformers]]. BERT is a specific model [[bert]]."
    )
    agent = QueryAgent(vault=wiki_vault, router=mock_router)
    result = agent.ask("What are transformers?")
    assert isinstance(result, QueryResult)
    assert len(result.answer) > 0


def test_query_cites_sources(wiki_vault: Vault) -> None:
    mock_router = MagicMock()
    mock_router.complete.return_value = "Transformers use attention mechanisms."
    agent = QueryAgent(vault=wiki_vault, router=mock_router)
    result = agent.ask("explain transformers self-attention")
    assert len(result.sources) >= 1


def test_query_empty_wiki(tmp_vault: Path) -> None:
    mock_router = MagicMock()
    mock_router.complete.return_value = "I don't have enough information."
    vault = Vault(tmp_vault)
    agent = QueryAgent(vault=vault, router=mock_router)
    result = agent.ask("anything?")
    assert isinstance(result.answer, str)
    assert result.sources == []


def test_query_calls_llm_with_context(wiki_vault: Vault) -> None:
    mock_router = MagicMock()
    mock_router.complete.return_value = "Answer with citations."
    agent = QueryAgent(vault=wiki_vault, router=mock_router)
    agent.ask("transformer architecture")
    # verify LLM was called with a user message containing wiki context
    call_args = mock_router.complete.call_args
    messages = call_args[0][0]
    user_content = messages[-1]["content"]
    assert "transformer" in user_content.lower() or "bert" in user_content.lower()


def test_query_uses_synthesis_complex_task_type(wiki_vault: Vault) -> None:
    mock_router = MagicMock()
    mock_router.complete.return_value = "Some answer."
    agent = QueryAgent(vault=wiki_vault, router=mock_router)
    agent.ask("anything")
    call_kwargs = mock_router.complete.call_args[1]
    assert call_kwargs["task_type"] == "synthesis_complex"
