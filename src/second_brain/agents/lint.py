from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

import structlog

from ..storage.frontmatter import WikiPage
from ..storage.vault import Vault

log = structlog.get_logger(__name__)

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]")
_STALE_DAYS = 30


def _extract_wikilinks(text: str) -> list[str]:
    """Return all wikilink targets (stem or path) from markdown text."""
    return _WIKILINK_RE.findall(text)


def _stems(vault: Vault) -> dict[str, str]:
    """Map page stem → vault-relative path for all wiki pages."""
    result: dict[str, str] = {}
    for p in vault.list_pages():
        rel = str(p.relative_to(vault.path)).replace("\\", "/")
        result[p.stem] = rel
    return result


@dataclass
class LintIssue:
    kind: str  # broken_wikilink | orphan | stale_draft | provenance_drift
    page: str  # vault-relative path
    detail: str = ""


@dataclass
class LintReport:
    generated: date = field(default_factory=date.today)
    issues: list[LintIssue] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"# Lint Report — {self.generated}", ""]
        if not self.issues:
            lines.append("No issues found. Vault is healthy.")
            return "\n".join(lines)
        by_kind: dict[str, list[LintIssue]] = {}
        for issue in self.issues:
            by_kind.setdefault(issue.kind, []).append(issue)
        for kind, items in sorted(by_kind.items()):
            title = kind.replace("_", " ").title()
            lines += [f"## {title} ({len(items)})", ""]
            for i in items:
                lines.append(f"- `{i.page}` — {i.detail}")
            lines.append("")
        return "\n".join(lines)


class LintAgent:
    def __init__(self, vault: Vault) -> None:
        self._vault = vault

    def run(self) -> LintReport:
        """Run all lint checks and write journal/lint-YYYY-MM-DD.md."""
        report = LintReport()
        pages = self._vault.list_pages()

        if not pages:
            self._write_report(report)
            return report

        stem_map = _stems(self._vault)

        # Track which pages are referenced by wikilinks (for orphan detection)
        referenced_stems: set[str] = set()
        page_outlinks: dict[str, list[str]] = {}

        for page_path in pages:
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            try:
                content = page_path.read_text(encoding="utf-8")
                page_obj = WikiPage.from_markdown(content)
            except Exception as exc:
                report.issues.append(LintIssue(kind="parse_error", page=rel, detail=str(exc)))
                page_outlinks[rel] = []
                continue

            links = _extract_wikilinks(content)
            page_outlinks[rel] = links
            for stem in links:
                referenced_stems.add(stem)

            # 1. Broken wikilinks
            for stem in links:
                if stem not in stem_map:
                    report.issues.append(
                        LintIssue(
                            kind="broken_wikilink",
                            page=rel,
                            detail=f"[[{stem}]] has no matching page",
                        )
                    )

            # 3. Stale drafts
            if page_obj.status == "draft" and (date.today() - page_obj.updated) > timedelta(
                days=_STALE_DAYS
            ):
                report.issues.append(
                    LintIssue(
                        kind="stale_draft",
                        page=rel,
                        detail=(
                            f"draft since {page_obj.updated}"
                            f" ({(date.today() - page_obj.updated).days}d ago)"
                        ),
                    )
                )

            # 4. Provenance drift
            if page_obj.provenance.inferred > 70:
                report.issues.append(
                    LintIssue(
                        kind="provenance_drift",
                        page=rel,
                        detail=(
                            f"inferred={page_obj.provenance.inferred}%"
                            " (>70%, possible hallucination)"
                        ),
                    )
                )

        # 2. Orphan pages — no other page links to them AND they have no outgoing links
        for page_path in pages:
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            stem = page_path.stem
            has_outlinks = bool(page_outlinks.get(rel))
            has_inlinks = stem in referenced_stems
            if not has_outlinks and not has_inlinks:
                report.issues.append(
                    LintIssue(kind="orphan", page=rel, detail="no incoming or outgoing wikilinks")
                )

        log.info("lint.complete", issues=len(report.issues))
        self._write_report(report)
        return report

    def _write_report(self, report: LintReport) -> None:
        journal_dir = self._vault.path / "journal"
        journal_dir.mkdir(parents=True, exist_ok=True)
        filename = f"lint-{report.generated}.md"
        (journal_dir / filename).write_text(report.to_markdown(), encoding="utf-8")
