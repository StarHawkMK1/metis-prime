from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ...llm.metrics import MetricsRecorder
from ...llm.router import LLMRouter
from ...storage.frontmatter import WikiPage
from ...storage.vault import Vault
from ..lint import LintIssue, LintReport, _extract_wikilinks, _stems
from ..search import WikiSearcher
from .state import LintState

log = structlog.get_logger(__name__)

_STALE_DAYS = 30
_MAX_CONTRADICTION_PAIRS = 3

_CONTRADICTION_PROMPT = """\
Compare these two wiki pages and identify any contradictory claims.
Respond with ONLY JSON: {"contradictions": [{"detail": "description of contradiction"}]}
If no contradictions, return {"contradictions": []}.
"""


def _make_router(vault_path: Path) -> LLMRouter:
    month_str = date.today().strftime("%Y-%m")
    log_path = vault_path / "journal" / ".metrics" / f"{month_str}.jsonl"
    recorder = MetricsRecorder(log_path=log_path)
    return LLMRouter(metrics_recorder=recorder)


class LintGraph:
    def __init__(self, vault: Vault, router: LLMRouter | None = None) -> None:
        self._vault = vault
        self._router = router or _make_router(vault.path)
        self._searcher = WikiSearcher(vault)
        self._compiled = self._build()

    def _build(self) -> Any:
        g = StateGraph(LintState)
        g.add_node("scan_links", self._scan_links)
        g.add_node("scan_orphans", self._scan_orphans)
        g.add_node("scan_provenance", self._scan_provenance)
        g.add_node("scan_contradictions", self._scan_contradictions)
        g.add_node("aggregate", self._aggregate)
        g.add_node("report", self._report)

        g.add_conditional_edges(
            START,
            self._dispatch,
            ["scan_links", "scan_orphans", "scan_provenance", "scan_contradictions"],
        )
        g.add_edge("scan_links", "aggregate")
        g.add_edge("scan_orphans", "aggregate")
        g.add_edge("scan_provenance", "aggregate")
        g.add_edge("scan_contradictions", "aggregate")
        g.add_edge("aggregate", "report")
        g.add_edge("report", END)
        return g.compile()

    def run(self) -> LintReport:
        initial: LintState = {"issues": [], "report_path": "", "cost_usd": 0.0}
        final = self._compiled.invoke(initial)
        report = LintReport(
            issues=[LintIssue(**i) for i in final["issues"]],
        )
        log.info("lint_graph.complete", issues=len(report.issues))
        return report

    # ── dispatch ──────────────────────────────────────────────────────────────

    def _dispatch(self, state: LintState) -> list[Send]:
        return [
            Send("scan_links", state),
            Send("scan_orphans", state),
            Send("scan_provenance", state),
            Send("scan_contradictions", state),
        ]

    # ── scan nodes ────────────────────────────────────────────────────────────

    def _scan_links(self, state: LintState) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        stem_map = _stems(self._vault)
        for page_path in self._vault.list_pages():
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            try:
                content = page_path.read_text(encoding="utf-8")
            except OSError:
                continue
            for stem in _extract_wikilinks(content):
                if stem not in stem_map:
                    issues.append(
                        {
                            "kind": "broken_wikilink",
                            "page": rel,
                            "detail": f"[[{stem}]] has no matching page",
                        }
                    )
        return {"issues": issues}

    def _scan_orphans(self, state: LintState) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        pages = self._vault.list_pages()
        referenced_stems: set[str] = set()
        page_outlinks: dict[str, list[str]] = {}

        for page_path in pages:
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            try:
                content = page_path.read_text(encoding="utf-8")
            except OSError:
                page_outlinks[rel] = []
                continue
            links = _extract_wikilinks(content)
            page_outlinks[rel] = links
            for stem in links:
                referenced_stems.add(stem)

        for page_path in pages:
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            stem = page_path.stem
            if not page_outlinks.get(rel) and stem not in referenced_stems:
                issues.append(
                    {"kind": "orphan", "page": rel, "detail": "no incoming or outgoing wikilinks"}
                )
        return {"issues": issues}

    def _scan_provenance(self, state: LintState) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        for page_path in self._vault.list_pages():
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            try:
                content = page_path.read_text(encoding="utf-8")
                page_obj = WikiPage.from_markdown(content)
            except Exception:
                continue

            if page_obj.status == "draft" and (date.today() - page_obj.updated) > timedelta(
                days=_STALE_DAYS
            ):
                days_old = (date.today() - page_obj.updated).days
                issues.append(
                    {
                        "kind": "stale_draft",
                        "page": rel,
                        "detail": f"draft since {page_obj.updated} ({days_old}d ago)",
                    }
                )
            if page_obj.provenance.inferred > 70:
                pct = page_obj.provenance.inferred
                issues.append(
                    {
                        "kind": "provenance_drift",
                        "page": rel,
                        "detail": f"inferred={pct}% (>70%, possible hallucination)",
                    }
                )
        return {"issues": issues}

    def _scan_contradictions(self, state: LintState) -> dict[str, Any]:
        """LLM-based contradiction detection across similar page pairs."""
        issues: list[dict[str, Any]] = []
        pages = self._vault.list_pages()
        if len(pages) < 2:
            return {"issues": issues, "cost_usd": 0.0}

        checked: set[frozenset[str]] = set()
        pairs_checked = 0
        total_cost = 0.0

        for page_path in pages:
            if pairs_checked >= _MAX_CONTRADICTION_PAIRS:
                break
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            try:
                content_a = page_path.read_text(encoding="utf-8")
            except OSError:
                continue

            results = self._searcher.search(content_a[:1000], top_k=2)
            for result in results:
                pair_key = frozenset([rel, result.relative_path])
                if pair_key in checked or result.relative_path == rel:
                    continue
                checked.add(pair_key)
                pairs_checked += 1

                try:
                    content_b = self._vault.read_raw_text(result.relative_path)
                    user_msg = (
                        f"Page A ({page_path.stem}):\n{content_a[:600]}\n\n"
                        f"Page B ({result.path.stem}):\n{content_b[:600]}"
                    )
                    raw = self._router.complete(
                        [
                            {"role": "system", "content": _CONTRADICTION_PROMPT},
                            {"role": "user", "content": user_msg},
                        ],
                        task_type="lint_contradiction",
                        sensitivity="normal",
                    )
                    total_cost += self._router.get_last_cost()
                    data = json.loads(raw.strip())
                    for c in data.get("contradictions", []):
                        issues.append(
                            {
                                "kind": "contradiction",
                                "page": rel,
                                "detail": f"vs [[{result.path.stem}]]: {c.get('detail', '')}",
                            }
                        )
                except Exception:
                    continue

        return {"issues": issues, "cost_usd": total_cost}

    def _aggregate(self, state: LintState) -> dict[str, Any]:
        return {}

    def _report(self, state: LintState) -> dict[str, Any]:
        report = LintReport(issues=[LintIssue(**i) for i in state["issues"]])  # type: ignore[arg-type]
        journal_dir = self._vault.path / "journal"
        journal_dir.mkdir(parents=True, exist_ok=True)
        filename = f"lint-{report.generated}.md"
        report_path = journal_dir / filename
        report_path.write_text(report.to_markdown(), encoding="utf-8")
        return {"report_path": str(report_path)}
