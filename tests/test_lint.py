from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from second_brain.agents.lint import LintAgent
from second_brain.storage import Vault, WikiPage
from second_brain.storage.frontmatter import ProvenanceBreakdown


def test_lint_detects_broken_wikilink(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/page-a.md",
        WikiPage(title="Page A", type="concept", body="See [[nonexistent-page]] for details."),
    )
    report = LintAgent(vault).run()
    assert any(i.kind == "broken_wikilink" for i in report.issues)


def test_lint_clean_page_no_broken_link(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/alpha.md",
        WikiPage(title="Alpha", type="concept", body="No wikilinks here."),
    )
    report = LintAgent(vault).run()
    broken = [i for i in report.issues if i.kind == "broken_wikilink"]
    assert broken == []


def test_lint_detects_orphan_page(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/lonely.md",
        WikiPage(title="Lonely", type="concept", body="No links in or out."),
    )
    report = LintAgent(vault).run()
    assert any(i.kind == "orphan" for i in report.issues)


def test_lint_linked_pages_not_orphan(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/hub.md",
        WikiPage(title="Hub", type="concept", body="See [[spoke]] for more."),
    )
    vault.write_page(
        "wiki/concepts/spoke.md",
        WikiPage(title="Spoke", type="concept", body="Back to [[hub]]."),
    )
    report = LintAgent(vault).run()
    orphans = [i for i in report.issues if i.kind == "orphan"]
    orphan_pages = {i.page for i in orphans}
    assert "wiki/concepts/hub.md" not in orphan_pages
    assert "wiki/concepts/spoke.md" not in orphan_pages


def test_lint_detects_stale_draft(tmp_vault: Path) -> None:
    old_date = date.today() - timedelta(days=45)
    # Vault.write_page unconditionally sets `updated = date.today()`, which
    # would make the page look fresh. Write directly to disk instead.
    page = WikiPage(
        title="Stale",
        type="concept",
        status="draft",
        body="Old content.",
        created=old_date,
        updated=old_date,
    )
    (tmp_vault / "wiki" / "concepts" / "stale.md").write_text(page.to_markdown(), encoding="utf-8")
    vault = Vault(tmp_vault)
    report = LintAgent(vault).run()
    assert any(i.kind == "stale_draft" for i in report.issues)


def test_lint_active_page_not_stale(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/fresh.md",
        WikiPage(title="Fresh", type="concept", status="active", body="Up to date."),
    )
    report = LintAgent(vault).run()
    stale = [i for i in report.issues if i.kind == "stale_draft"]
    assert stale == []


def test_lint_detects_provenance_drift(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/speculative.md",
        WikiPage(
            title="Speculative",
            type="concept",
            body="Mostly inferred.",
            provenance=ProvenanceBreakdown(extracted=20, inferred=75, ambiguous=5),
        ),
    )
    report = LintAgent(vault).run()
    assert any(i.kind == "provenance_drift" for i in report.issues)


def test_lint_empty_vault_no_issues(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    report = LintAgent(vault).run()
    assert report.issues == []


def test_lint_writes_report_file(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/x.md",
        WikiPage(title="X", type="concept", body="[[ghost]] link."),
    )
    LintAgent(vault).run()
    journal_dir = tmp_vault / "journal"
    assert journal_dir.exists()
    reports = list(journal_dir.glob("lint-*.md"))
    assert len(reports) >= 1
    content = reports[0].read_text(encoding="utf-8")
    assert "broken_wikilink" in content or "Broken" in content
