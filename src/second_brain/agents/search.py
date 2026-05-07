from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from ..storage.vault import Vault


@dataclass
class SearchResult:
    path: Path
    relative_path: str
    content: str
    score: float


class WikiSearcher:
    """BM25-based full-text search over wiki pages."""

    def __init__(self, vault: Vault) -> None:
        self._vault = vault

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Return up to top_k wiki pages most relevant to query."""
        pages = self._vault.list_pages()
        if not pages:
            return []

        contents: list[str] = []
        for p in pages:
            try:
                contents.append(p.read_text(encoding="utf-8"))
            except OSError:
                contents.append("")

        tokenized = [doc.lower().split() for doc in contents]
        bm25: Any = BM25Okapi(tokenized)
        scores: Any = bm25.get_scores(query.lower().split())

        ranked = sorted(
            zip(scores, pages, contents, strict=False),
            key=lambda x: float(x[0]),
            reverse=True,
        )

        results: list[SearchResult] = []
        for score, path, content in ranked[:top_k]:
            score_f = float(score)
            if score_f <= 0:
                continue
            rel = str(path.relative_to(self._vault.path)).replace("\\", "/")
            results.append(
                SearchResult(path=path, relative_path=rel, content=content, score=score_f)
            )
        return results
