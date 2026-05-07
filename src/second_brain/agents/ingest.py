from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pygit2
import structlog
from pydantic import BaseModel, Field, ValidationError

from ..llm.router import LLMRouter
from ..llm.types import Sensitivity
from ..storage.frontmatter import PageType, ProvenanceBreakdown, WikiPage
from ..storage.vault import Vault
from .extractors import extract_text
from .search import WikiSearcher

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a wiki maintainer for a personal second brain knowledge base.
Analyze the incoming source material and decide how to incorporate it into the wiki.

You will receive:
1. The source text
2. A list of similar existing wiki pages (for deduplication context)

Respond with ONLY a JSON object — no markdown fences, no explanation:

{
  "decision": "create" | "merge" | "skip",
  "title": "Title Case Title",
  "type": "concept" | "project" | "person" | "place" | "ref" | "map",
  "body": "Markdown body (no frontmatter). First line = one-sentence definition.",
  "provenance": {"extracted": <0-100>, "inferred": <0-100>, "ambiguous": <0-100>},
  "wikilinks": ["stem-of-page-1", "stem-of-page-2"],
  "tags": ["tag1"],
  "target_page": "stem-of-existing-page-to-merge-into"
}

Decision rules:
- "create" — topic is new, no sufficiently similar wiki page exists.
- "merge"  — a very similar page already exists; merge this content into it.
             Set target_page to the stem (filename without extension) of that page.
- "skip"   — source adds nothing new to the wiki.

Constraints:
- provenance values must sum to exactly 100.
- wikilinks: only stems of pages shown in the "Existing similar pages" section.
- target_page: only required for "merge"; set to empty string otherwise.
- Return ONLY the JSON object.
"""


class _IngestDecision(BaseModel):
    decision: Literal["create", "merge", "skip"]
    title: str
    type: PageType
    body: str
    provenance: ProvenanceBreakdown
    wikilinks: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    target_page: str = ""


@dataclass
class IngestResult:
    decision: str
    wiki_path: str | None
    archived_path: Path
    source_name: str


class IngestError(Exception):
    """Raised when ingest fails (e.g. invalid LLM response)."""


def _get_signature(repo: Any) -> Any:
    try:
        return repo.default_signature
    except KeyError:
        return pygit2.Signature("Second Brain", "second-brain@local")


class IngestAgent:
    def __init__(
        self,
        vault: Vault,
        router: LLMRouter | None = None,
        sensitivity: Sensitivity = "normal",
    ) -> None:
        self._vault = vault
        self._router = router or LLMRouter()
        self._sensitivity = sensitivity
        self._searcher = WikiSearcher(vault)

    def run(self, source_rel_path: str, sensitivity: Sensitivity | None = None) -> IngestResult:
        """Ingest a single raw source file into the wiki."""
        sens = sensitivity or self._sensitivity
        source_path = self._vault.path / source_rel_path

        raw_text = extract_text(source_path)
        similar = self._searcher.search(raw_text[:2000], top_k=3)

        similar_context = ""
        if similar:
            parts = []
            for r in similar:
                parts.append(f"[[{r.path.stem}]] (score: {r.score:.2f})\n{r.content[:400]}")
            similar_context = "\n\n---\n\n".join(parts)

        user_msg = (
            f"Source file: {source_path.name}\n\nSource text:\n---\n{raw_text[:3000]}\n---\n\n"
        )
        if similar_context:
            user_msg += f"Existing similar pages ({len(similar)} found):\n\n{similar_context}\n\n"
        else:
            user_msg += "Existing similar pages: none\n\n"
        user_msg += "Make your decision."

        raw_response = self._router.complete(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            task_type="ingest_summary",
            sensitivity=sens,
        )

        decision = _parse_decision(raw_response)

        wiki_path: str | None = None
        if decision.decision == "create":
            wiki_path = _default_wiki_path(decision.title)
            page = WikiPage(
                title=decision.title,
                type=decision.type,
                body=_body_with_related(decision.body, decision.wikilinks),
                tags=decision.tags,
                sources=[source_rel_path],
                provenance=decision.provenance,
            )
            self._vault.write_page(wiki_path, page)
            log.info("ingest.created", page=wiki_path)
        elif decision.decision == "merge":
            wiki_path = _resolve_merge_target(decision.target_page, self._vault)
            if wiki_path:
                existing = self._vault.read_page(wiki_path)
                merged_body = existing.body.rstrip() + "\n\n" + decision.body
                merged_sources = list(dict.fromkeys(existing.sources + [source_rel_path]))
                updated = existing.model_copy(
                    update={
                        "body": _body_with_related(merged_body, decision.wikilinks),
                        "sources": merged_sources,
                    }
                )
                self._vault.write_page(wiki_path, updated)
                log.info("ingest.merged", page=wiki_path)
            else:
                wiki_path = _default_wiki_path(decision.title)
                page = WikiPage(
                    title=decision.title,
                    type=decision.type,
                    body=_body_with_related(decision.body, decision.wikilinks),
                    tags=decision.tags,
                    sources=[source_rel_path],
                    provenance=decision.provenance,
                )
                self._vault.write_page(wiki_path, page)
                log.info("ingest.merge_fallback_created", page=wiki_path)
        else:
            log.info("ingest.skipped", source=source_rel_path)

        archived = self._vault.archive_raw(source_rel_path)

        # Emit a single ingest-level summary commit so history is traceable.
        _commit_ingest_marker(
            self._vault.path,
            f"ingest: {decision.decision} {source_path.name}",
        )

        return IngestResult(
            decision=decision.decision,
            wiki_path=wiki_path,
            archived_path=archived,
            source_name=source_path.name,
        )


# ── helpers ──────────────────────────────────────────────────────────────────


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text[text.find("\n") + 1 :]
        end = text.rfind("```")
        if end != -1:
            text = text[:end]
    return text.strip()


def _parse_decision(raw: str) -> _IngestDecision:
    cleaned = _strip_json_fences(raw)
    try:
        data: Any = json.loads(cleaned)
        return _IngestDecision.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise IngestError(f"Failed to parse LLM response as IngestDecision: {exc}") from exc


def _default_wiki_path(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"wiki/concepts/{slug}.md"


def _resolve_merge_target(stem: str, vault: Vault) -> str | None:
    """Find the relative vault path of a wiki page by its stem."""
    if not stem:
        return None
    for page_path in vault.list_pages():
        if page_path.stem == stem:
            return str(page_path.relative_to(vault.path)).replace("\\", "/")
    return None


def _body_with_related(body: str, wikilinks: list[str]) -> str:
    if not wikilinks:
        return body
    links = "\n".join(f"[[{stem}]]" for stem in wikilinks)
    return body.rstrip() + "\n\n## Related\n\n" + links


def _commit_ingest_marker(repo_path: Path, message: str) -> None:
    """Create a no-tree-change commit to mark the ingest operation in git history."""
    repo = pygit2.Repository(str(repo_path))
    sig = _get_signature(repo)
    # Re-use the current HEAD tree (no new file changes; write/archive commits already recorded)
    head_commit = repo.get(repo.head.target)
    if head_commit is None:
        raise RuntimeError("Repository has no HEAD commit")
    tree = head_commit.tree
    repo.create_commit(
        "refs/heads/main",
        sig,
        sig,
        message,
        tree.id,
        [repo.head.target],
    )
