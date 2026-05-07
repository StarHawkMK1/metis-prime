from __future__ import annotations

from pathlib import Path

import pytest

from second_brain.agents.search import SearchResult, WikiSearcher
from second_brain.storage import Vault, WikiPage


@pytest.fixture()
def wiki_vault(tmp_vault: Path) -> Vault:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/machine-learning.md",
        WikiPage(
            title="Machine Learning", type="concept", body="ML is a subset of AI. Neural networks."
        ),
    )
    vault.write_page(
        "wiki/concepts/python.md",
        WikiPage(
            title="Python",
            type="concept",
            body="Python is a programming language used in data science.",
        ),
    )
    vault.write_page(
        "wiki/concepts/databases.md",
        WikiPage(
            title="Databases", type="concept", body="Relational databases store data in tables."
        ),
    )
    return vault


def test_search_returns_results(wiki_vault: Vault) -> None:
    searcher = WikiSearcher(wiki_vault)
    results = searcher.search("machine learning neural")
    assert len(results) >= 1
    assert all(isinstance(r, SearchResult) for r in results)


def test_search_relevant_first(wiki_vault: Vault) -> None:
    searcher = WikiSearcher(wiki_vault)
    results = searcher.search("machine learning neural networks")
    assert len(results) >= 1
    # machine-learning page should rank highest
    assert "machine-learning" in results[0].relative_path


def test_search_top_k_limit(wiki_vault: Vault) -> None:
    searcher = WikiSearcher(wiki_vault)
    results = searcher.search("data", top_k=2)
    assert len(results) <= 2


def test_search_empty_vault(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    searcher = WikiSearcher(vault)
    results = searcher.search("anything")
    assert results == []


def test_search_result_fields(wiki_vault: Vault) -> None:
    searcher = WikiSearcher(wiki_vault)
    results = searcher.search("python programming")
    assert len(results) >= 1
    r = results[0]
    assert r.path.exists()
    assert r.score > 0
    assert "wiki/" in r.relative_path
    assert len(r.content) > 0
