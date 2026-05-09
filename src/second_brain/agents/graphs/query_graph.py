from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import structlog
from langgraph.graph import END, START, StateGraph

from ...graph.query import GraphQuery
from ...llm.metrics import MetricsRecorder
from ...llm.router import LLMRouter
from ...llm.types import Sensitivity
from ...storage.vault import Vault
from ..search import WikiSearcher
from .state import QueryState

log = structlog.get_logger(__name__)

_CLASSIFY_PROMPT = """\
Classify the user's question into one of three intents.

Respond with ONLY a JSON object:
{"intent": "factual" | "synthesis" | "task_command"}

- "factual": single specific fact or definition
- "synthesis": requires combining multiple sources or explaining relationships
- "task_command": action request (extract tasks, remind me, schedule something)
"""

_ANSWER_PROMPT = """\
You are a knowledgeable assistant with access to the user's personal wiki.
Answer concisely, citing wiki pages with [[page-stem]] inline citations.
If no wiki pages are relevant, say so clearly.
"""


def _make_router(vault_path: Path) -> LLMRouter:
    month_str = date.today().strftime("%Y-%m")
    log_path = vault_path / "journal" / ".metrics" / f"{month_str}.jsonl"
    recorder = MetricsRecorder(log_path=log_path)
    return LLMRouter(metrics_recorder=recorder)


@dataclass
class QueryResult:
    answer: str
    sources: list[str] = field(default_factory=list)
    cost_usd: float = 0.0


class QueryGraph:
    def __init__(
        self,
        vault: Vault,
        router: LLMRouter | None = None,
        top_k: int = 5,
        sensitivity: Sensitivity = "normal",
        graph_depth: int = 2,
    ) -> None:
        self._vault = vault
        self._router = router or _make_router(vault.path)
        self._top_k = top_k
        self._sensitivity = sensitivity
        self._searcher = WikiSearcher(vault)
        self._graph_query = GraphQuery(vault.path / "graph" / "graphify-out" / "graph.json")
        self._compiled = self._build()

    def _build(self) -> Any:  # noqa: ANN401
        g = StateGraph(QueryState)
        g.add_node("classify_intent", self._classify_intent)
        g.add_node("graph_lookup", self._graph_lookup)
        g.add_node("multi_page_fetch", self._multi_page_fetch)
        g.add_node("answer", self._answer)
        g.add_node("record", self._record)

        g.add_edge(START, "classify_intent")
        g.add_conditional_edges(
            "classify_intent",
            lambda s: s["intent"] if s["intent"] in ("factual", "synthesis") else "factual",
            {"factual": "graph_lookup", "synthesis": "multi_page_fetch"},
        )
        g.add_edge("graph_lookup", "answer")
        g.add_edge("multi_page_fetch", "answer")
        g.add_edge("answer", "record")
        g.add_edge("record", END)
        return g.compile()

    def ask(
        self, question: str, sensitivity: Sensitivity | None = None, archive: bool = False
    ) -> QueryResult:
        sens = sensitivity or self._sensitivity
        initial: QueryState = {
            "question": question,
            "sensitivity": sens,
            "intent": "",
            "context_parts": [],
            "sources": [],
            "answer": "",
            "archive": archive,
            "cost_usd": 0.0,
        }
        final = self._compiled.invoke(initial)
        return QueryResult(
            answer=final["answer"],
            sources=final["sources"],
            cost_usd=final.get("cost_usd", 0.0),
        )

    # ── nodes ─────────────────────────────────────────────────────────────────

    def _classify_intent(self, state: QueryState) -> dict[str, object]:
        raw = self._router.complete(
            [
                {"role": "system", "content": _CLASSIFY_PROMPT},
                {"role": "user", "content": state["question"]},
            ],
            task_type="synthesis_complex",
            sensitivity=state["sensitivity"],  # type: ignore[arg-type]
        )
        try:
            intent = json.loads(raw.strip()).get("intent", "factual")
        except (json.JSONDecodeError, AttributeError):
            intent = "factual"
        return {
            "intent": intent,
            "cost_usd": state["cost_usd"] + self._router.get_last_cost(),
        }

    def _graph_lookup(self, state: QueryState) -> dict[str, object]:
        """Graph-first retrieval, BM25 fallback."""
        try:
            graph_ctx = self._graph_query.search_and_expand(state["question"], depth=2)
        except Exception as exc:
            log.debug("query_graph.graph_lookup_failed", error=str(exc))
            graph_ctx = None

        if graph_ctx and graph_ctx.nodes:
            parts: list[str] = []
            sources: list[str] = []
            seen: set[str] = set()
            for node in graph_ctx.nodes:
                if not node.source_file or node.source_file in seen:
                    continue
                seen.add(node.source_file)
                if self._vault.page_exists(node.source_file):
                    try:
                        content = self._vault.read_raw_text(node.source_file)
                        stem = Path(node.source_file).stem
                        parts.append(f"[[{stem}]] (graph: {node.label})\n{content[:800]}")
                        sources.append(node.source_file)
                    except OSError:
                        continue
            if parts:
                return {"context_parts": parts, "sources": sources}

        # BM25 fallback
        results = self._searcher.search(state["question"], top_k=self._top_k)
        return {
            "context_parts": [
                f"[[{r.path.stem}]] (relevance: {r.score:.2f})\n{r.content[:800]}" for r in results
            ],
            "sources": [r.relative_path for r in results],
        }

    def _multi_page_fetch(self, state: QueryState) -> dict[str, object]:
        """Broader BM25 retrieval for synthesis questions."""
        results = self._searcher.search(state["question"], top_k=self._top_k)
        return {
            "context_parts": [
                f"[[{r.path.stem}]] (relevance: {r.score:.2f})\n{r.content[:1200]}" for r in results
            ],
            "sources": [r.relative_path for r in results],
        }

    def _answer(self, state: QueryState) -> dict[str, object]:
        context = state["context_parts"]
        if context:
            user_msg = (
                f"Question: {state['question']}\n\nRelevant wiki pages:\n\n"
                + "\n\n---\n\n".join(context)
            )
        else:
            user_msg = f"Question: {state['question']}\n\nWiki context: none"

        answer = self._router.complete(
            [{"role": "system", "content": _ANSWER_PROMPT}, {"role": "user", "content": user_msg}],
            task_type="synthesis_complex",
            sensitivity=state["sensitivity"],  # type: ignore[arg-type]
        )
        return {
            "answer": answer,
            "cost_usd": state["cost_usd"] + self._router.get_last_cost(),
        }

    def _record(self, state: QueryState) -> dict[str, object]:
        """Append Q&A to journal/queries.md when archive=True."""
        if not state.get("archive"):
            return {}
        journal_dir = self._vault.path / "journal"
        journal_dir.mkdir(parents=True, exist_ok=True)
        queries_file = journal_dir / "queries.md"
        from datetime import date as _date

        entry = (
            f"\n## {_date.today()} — {state['question'][:80]}\n\n"
            f"{state['answer']}\n\n"
            f"*Sources: {', '.join(f'[[{s}]]' for s in state['sources']) or 'none'}*\n"
        )
        with queries_file.open("a", encoding="utf-8") as f:
            f.write(entry)
        log.info("query_graph.recorded", question=state["question"][:80])
        return {}
