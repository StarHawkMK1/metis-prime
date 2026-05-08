from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import structlog

from ..graph.query import GraphContext, GraphQuery
from ..llm.router import LLMRouter
from ..llm.types import Sensitivity
from ..storage.vault import Vault
from .search import WikiSearcher

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a knowledgeable assistant with access to the user's personal wiki.
Answer questions concisely, citing the wiki pages you used.

Use inline citation format: [[page-stem]] after each claim.
If no wiki pages are relevant, say so clearly.
"""


@dataclass
class QueryResult:
    answer: str
    sources: list[str] = field(default_factory=list)


class QueryAgent:
    def __init__(
        self,
        vault: Vault,
        router: LLMRouter | None = None,
        top_k: int = 5,
        sensitivity: Sensitivity = "normal",
        graph_depth: int = 2,
    ) -> None:
        self._vault = vault
        self._router = router or LLMRouter()
        self._top_k = top_k
        self._sensitivity = sensitivity
        self._graph_depth = graph_depth
        self._searcher = WikiSearcher(vault)
        self._graph_query = GraphQuery(vault.path / "graph" / "graphify-out" / "graph.json")

    def ask(self, question: str, sensitivity: Sensitivity | None = None) -> QueryResult:
        """Answer a natural language question using graph-first, BM25 fallback."""
        sens = sensitivity or self._sensitivity

        graph_ctx = self._graph_query.search_and_expand(question, depth=self._graph_depth)

        if graph_ctx.nodes:
            context_parts = self._build_graph_context(graph_ctx)
            sources = list({n.source_file for n in graph_ctx.nodes if n.source_file})
            graph_used = True
        else:
            similar = self._searcher.search(question, top_k=self._top_k)
            context_parts = [
                f"[[{r.path.stem}]] (relevance: {r.score:.2f})\n{r.content[:800]}" for r in similar
            ]
            sources = [r.relative_path for r in similar]
            graph_used = False

        if not context_parts:
            answer = self._router.complete(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"Question: {question}\n\nWiki context: none"},
                ],
                task_type="synthesis_complex",
                sensitivity=sens,
            )
            return QueryResult(answer=answer, sources=[])

        user_msg = f"Question: {question}\n\nRelevant wiki pages:\n\n" + "\n\n---\n\n".join(
            context_parts
        )
        answer = self._router.complete(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            task_type="synthesis_complex",
            sensitivity=sens,
        )

        log.info(
            "query.answered",
            question=question[:80],
            sources_used=len(sources),
            graph_used=graph_used,
        )
        return QueryResult(answer=answer, sources=sources)

    def _build_graph_context(self, ctx: GraphContext) -> list[str]:
        """Read vault pages referenced by graph nodes."""
        parts: list[str] = []
        seen: set[str] = set()
        for node in ctx.nodes:
            if not node.source_file or node.source_file in seen:
                continue
            seen.add(node.source_file)
            if self._vault.page_exists(node.source_file):
                try:
                    content = self._vault.read_raw_text(node.source_file)
                    stem = Path(node.source_file).stem
                    parts.append(f"[[{stem}]] (graph: {node.label})\n{content[:800]}")
                except OSError:
                    continue
        return parts
