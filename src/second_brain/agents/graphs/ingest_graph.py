from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import structlog
from langgraph.graph import END, START, StateGraph

from ...llm.metrics import MetricsRecorder
from ...llm.router import LLMRouter
from ...llm.types import Sensitivity
from ...storage.frontmatter import WikiPage
from ...storage.vault import Vault
from ..extractors import extract_text
from ..ingest import (
    IngestError,
    _body_with_related,
    _default_wiki_path,
    _IngestDecision,
    _parse_decision,
    _resolve_merge_target,
)
from ..search import WikiSearcher
from .state import IngestState

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a wiki maintainer for a personal second brain knowledge base.
Analyze the incoming source material and decide how to incorporate it into the wiki.

Respond with ONLY a JSON object:

{
  "decision": "create" | "merge" | "skip",
  "title": "Title Case Title",
  "type": "concept" | "project" | "person" | "place" | "ref" | "map",
  "body": "Markdown body (no frontmatter). First line = one-sentence definition.",
  "provenance": {"extracted": <0-100>, "inferred": <0-100>, "ambiguous": <0-100>},
  "wikilinks": ["stem-of-page-1"],
  "tags": ["tag1"],
  "target_page": "stem-of-existing-page-to-merge-into"
}

Rules: "create" if new topic; "merge" if very similar page exists (set target_page);
"skip" if source adds nothing new. provenance must sum to 100. Return ONLY JSON.
"""


def _make_router(vault_path: Path) -> LLMRouter:
    month_str = date.today().strftime("%Y-%m")
    log_path = vault_path / "journal" / ".metrics" / f"{month_str}.jsonl"
    recorder = MetricsRecorder(log_path=log_path)
    return LLMRouter(metrics_recorder=recorder)


@dataclass
class IngestResult:
    decision: str
    wiki_path: str | None
    archived_path: Path
    source_name: str
    cost_usd: float = 0.0


class IngestGraph:
    def __init__(
        self,
        vault: Vault,
        router: LLMRouter | None = None,
        sensitivity: Sensitivity = "normal",
    ) -> None:
        self._vault = vault
        self._router = router or _make_router(vault.path)
        self._sensitivity = sensitivity
        self._searcher = WikiSearcher(vault)
        self._compiled = self._build()

    def _build(self) -> Any:  # noqa: ANN401
        g = StateGraph(IngestState)
        g.add_node("extract", self._extract)
        g.add_node("search_similar", self._search_similar)
        g.add_node("decide", self._decide)
        g.add_node("validate", self._validate)
        g.add_node("generate_page", self._generate_page)
        g.add_node("merge_into_existing", self._merge_into_existing)
        g.add_node("skip_node", self._skip_node)
        g.add_node("cross_link", self._cross_link)
        g.add_node("commit_node", self._commit_node)
        g.add_node("queue_human_review", self._queue_human_review)

        g.add_edge(START, "extract")
        g.add_edge("extract", "search_similar")
        g.add_edge("search_similar", "decide")
        g.add_edge("decide", "validate")
        # validate runs BEFORE writing — routes to review if inferred > 70%
        g.add_conditional_edges(
            "validate",
            lambda s: s["decision"] if s["validation_passed"] else "queue_human_review",
            {
                "create": "generate_page",
                "merge": "merge_into_existing",
                "skip": "skip_node",
                "queue_human_review": "queue_human_review",
            },
        )
        g.add_edge("generate_page", "cross_link")
        g.add_edge("merge_into_existing", "cross_link")
        g.add_edge("cross_link", "commit_node")
        g.add_edge("skip_node", "commit_node")
        g.add_edge("commit_node", END)
        g.add_edge("queue_human_review", END)
        return g.compile()

    def run(self, source_rel_path: str, sensitivity: Sensitivity | None = None) -> IngestResult:
        sens = sensitivity or self._sensitivity
        initial: IngestState = {
            "source_rel_path": source_rel_path,
            "sensitivity": sens,
            "raw_text": "",
            "similar_pages": [],
            "decision": "",
            "decision_data": {},
            "wiki_path": None,
            "archived_path": "",
            "validation_passed": True,
            "cost_usd": 0.0,
            "errors": [],
        }
        final = self._compiled.invoke(initial)
        return IngestResult(
            decision=final["decision"],
            wiki_path=final.get("wiki_path"),
            archived_path=Path(final["archived_path"]) if final["archived_path"] else Path(""),
            source_name=Path(source_rel_path).name,
            cost_usd=final.get("cost_usd", 0.0),
        )

    # ── nodes ─────────────────────────────────────────────────────────────────

    def _extract(self, state: IngestState) -> dict[str, object]:
        source_path = self._vault.path / state["source_rel_path"]
        return {"raw_text": extract_text(source_path)}

    def _search_similar(self, state: IngestState) -> dict[str, object]:
        results = self._searcher.search(state["raw_text"][:2000], top_k=3)
        return {
            "similar_pages": [
                {"stem": r.path.stem, "score": r.score, "content": r.content[:400]} for r in results
            ]
        }

    def _decide(self, state: IngestState) -> dict[str, object]:
        source_path = self._vault.path / state["source_rel_path"]
        similar = state["similar_pages"]
        raw_text = state["raw_text"]
        user_msg = (
            f"Source file: {source_path.name}\n\nSource text:\n---\n{raw_text[:3000]}\n---\n\n"
        )
        if similar:
            parts = [f"[[{p['stem']}]] (score: {p['score']:.2f})\n{p['content']}" for p in similar]
            user_msg += (
                f"Existing similar pages ({len(similar)} found):\n\n"
                + "\n\n---\n\n".join(parts)
                + "\n\n"
            )
        else:
            user_msg += "Existing similar pages: none\n\n"
        user_msg += "Make your decision."

        raw = self._router.complete(
            [{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": user_msg}],
            task_type="ingest_summary",
            sensitivity=state["sensitivity"],  # type: ignore[arg-type]
        )
        dec = _parse_decision(raw)
        return {
            "decision": dec.decision,
            "decision_data": dec.model_dump(),
            "cost_usd": state["cost_usd"] + self._router.get_last_cost(),
        }

    def _validate(self, state: IngestState) -> dict[str, object]:
        if state["decision"] == "skip":
            return {"validation_passed": True}
        decision_data: dict[str, Any] = dict(state.get("decision_data") or {})
        provenance: dict[str, Any] = dict(decision_data.get("provenance") or {})
        inferred: int = int(provenance.get("inferred", 0))
        return {"validation_passed": inferred <= 70}

    def _generate_page(self, state: IngestState) -> dict[str, object]:
        dec = _IngestDecision.model_validate(state["decision_data"])
        wiki_path = _default_wiki_path(dec.title)
        self._vault.write_page(
            wiki_path,
            WikiPage(
                title=dec.title,
                type=dec.type,
                body=_body_with_related(dec.body, dec.wikilinks),
                tags=dec.tags,
                sources=[state["source_rel_path"]],
                provenance=dec.provenance,
            ),
        )
        log.info("ingest_graph.created", page=wiki_path)
        return {"wiki_path": wiki_path}

    def _merge_into_existing(self, state: IngestState) -> dict[str, object]:
        dec = _IngestDecision.model_validate(state["decision_data"])
        wiki_path = _resolve_merge_target(dec.target_page, self._vault)
        if wiki_path:
            existing = self._vault.read_page(wiki_path)
            merged_sources = list(dict.fromkeys(existing.sources + [state["source_rel_path"]]))
            self._vault.write_page(
                wiki_path,
                existing.model_copy(
                    update={
                        "body": _body_with_related(dec.body, dec.wikilinks),
                        "sources": merged_sources,
                    }
                ),
            )
            log.info("ingest_graph.merged", page=wiki_path)
        else:
            wiki_path = _default_wiki_path(dec.title)
            self._vault.write_page(
                wiki_path,
                WikiPage(
                    title=dec.title,
                    type=dec.type,
                    body=_body_with_related(dec.body, dec.wikilinks),
                    tags=dec.tags,
                    sources=[state["source_rel_path"]],
                    provenance=dec.provenance,
                ),
            )
            log.info("ingest_graph.merge_fallback_created", page=wiki_path)
        return {"wiki_path": wiki_path}

    def _skip_node(self, state: IngestState) -> dict[str, object]:
        log.info("ingest_graph.skipped", source=state["source_rel_path"])
        return {}

    def _cross_link(self, state: IngestState) -> dict[str, object]:
        """Append backlink to each page referenced by the new/updated page."""
        wiki_path = state.get("wiki_path")
        if not wiki_path:
            return {}
        decision_data: dict[str, Any] = dict(state.get("decision_data") or {})
        wikilinks: list[str] = [str(w) for w in (decision_data.get("wikilinks") or [])]
        new_stem = Path(wiki_path).stem
        for stem in wikilinks:
            target_path = _resolve_merge_target(stem, self._vault)
            if not target_path:
                continue
            try:
                page = self._vault.read_page(target_path)
                if f"[[{new_stem}]]" not in page.body:
                    self._vault.write_page(
                        target_path,
                        page.model_copy(
                            update={"body": page.body.rstrip() + f"\n\n[[{new_stem}]]"}
                        ),
                    )
            except Exception:
                continue
        return {}

    def _commit_node(self, state: IngestState) -> dict[str, object]:
        source_rel = state["source_rel_path"]
        source_path = self._vault.path / source_rel
        try:
            archived = self._vault.archive_raw(
                source_rel,
                commit_message=f"ingest: {state['decision']} {source_path.name}",
            )
            return {"archived_path": str(archived)}
        except FileExistsError as exc:
            raise IngestError(f"Cannot archive {source_rel}: {exc}") from exc

    def _queue_human_review(self, state: IngestState) -> dict[str, object]:
        """Write draft to human_review/pending/ and archive raw source."""
        review_dir = self._vault.path / "human_review" / "pending"
        review_dir.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = dict(state.get("decision_data") or {})
        title: str = str(data.get("title") or "unknown")
        stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "unknown"
        draft_path = review_dir / f"{stem}.md"
        draft_path.write_text(
            f"# Review Required: {title}\n\n"
            f"**Reason:** inferred provenance > 70%\n\n"
            f"**Source:** {state['source_rel_path']}\n\n"
            f"{data.get('body', '')}",
            encoding="utf-8",
        )
        log.info("ingest_graph.queued_for_review", stem=stem)

        source_rel = state["source_rel_path"]
        source_path = self._vault.path / source_rel
        try:
            archived = self._vault.archive_raw(
                source_rel,
                commit_message=f"ingest: pending-review {source_path.name}",
            )
            return {"wiki_path": None, "archived_path": str(archived)}
        except FileExistsError:
            return {"wiki_path": None, "archived_path": ""}
