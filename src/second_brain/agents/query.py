from __future__ import annotations

from dataclasses import dataclass, field

import structlog

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
    ) -> None:
        self._vault = vault
        self._router = router or LLMRouter()
        self._top_k = top_k
        self._sensitivity = sensitivity
        self._searcher = WikiSearcher(vault)

    def ask(self, question: str, sensitivity: Sensitivity | None = None) -> QueryResult:
        """Answer a natural language question using the wiki as context."""
        sens = sensitivity or self._sensitivity
        similar = self._searcher.search(question, top_k=self._top_k)

        if not similar:
            answer = self._router.complete(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"Question: {question}\n\nWiki context: none"},
                ],
                task_type="synthesis_complex",
                sensitivity=sens,
            )
            return QueryResult(answer=answer, sources=[])

        context_parts = []
        for r in similar:
            context_parts.append(f"[[{r.path.stem}]] (relevance: {r.score:.2f})\n{r.content[:800]}")

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

        sources = [r.relative_path for r in similar]
        log.info("query.answered", question=question[:80], sources_used=len(sources))
        return QueryResult(answer=answer, sources=sources)
