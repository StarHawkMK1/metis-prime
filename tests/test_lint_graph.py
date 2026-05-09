from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from second_brain.storage import Vault, WikiPage


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    import pygit2

    repo = pygit2.init_repository(str(tmp_path))
    sig = pygit2.Signature("Test", "t@t.com")
    tree = repo.TreeBuilder().write()
    repo.create_commit("refs/heads/main", sig, sig, "init", tree, [])
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    return tmp_path


def test_lint_graph_detects_broken_wikilink(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.lint_graph import LintGraph

    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/note.md",
        WikiPage(title="Note", type="concept", body="See [[nonexistent-page]] for details."),
    )

    mock_router = MagicMock()
    mock_router.complete.return_value = '{"contradictions": []}'
    mock_router.get_last_cost.return_value = 0.0

    graph = LintGraph(vault=vault, router=mock_router)
    report = graph.run()

    kinds = {i.kind for i in report.issues}
    assert "broken_wikilink" in kinds


def test_lint_graph_detects_orphan(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.lint_graph import LintGraph

    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/lonely.md",
        WikiPage(title="Lonely Page", type="concept", body="No links here."),
    )

    mock_router = MagicMock()
    mock_router.complete.return_value = '{"contradictions": []}'
    mock_router.get_last_cost.return_value = 0.0

    graph = LintGraph(vault=vault, router=mock_router)
    report = graph.run()

    kinds = {i.kind for i in report.issues}
    assert "orphan" in kinds


def test_lint_graph_detects_stale_draft(tmp_vault: Path) -> None:
    from datetime import date, timedelta

    from second_brain.agents.graphs.lint_graph import LintGraph
    from second_brain.storage.frontmatter import WikiPage

    vault = Vault(tmp_vault)
    old_date = date.today() - timedelta(days=40)
    page = WikiPage(
        title="Old Draft",
        type="concept",
        body="Some content.",
        status="draft",
        created=old_date,
        updated=old_date,
    )
    # Vault.write_page unconditionally sets updated=today, bypassing stale detection.
    # Write directly to disk to preserve the old date, mirroring test_lint.py.
    (tmp_vault / "wiki" / "concepts" / "old-draft.md").write_text(
        page.to_markdown(), encoding="utf-8"
    )

    mock_router = MagicMock()
    mock_router.complete.return_value = '{"contradictions": []}'
    mock_router.get_last_cost.return_value = 0.0

    graph = LintGraph(vault=vault, router=mock_router)
    report = graph.run()

    kinds = {i.kind for i in report.issues}
    assert "stale_draft" in kinds


def test_lint_graph_writes_report_file(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.lint_graph import LintGraph

    vault = Vault(tmp_vault)
    mock_router = MagicMock()
    mock_router.complete.return_value = '{"contradictions": []}'
    mock_router.get_last_cost.return_value = 0.0

    graph = LintGraph(vault=vault, router=mock_router)
    graph.run()

    from datetime import date

    report_path = tmp_vault / "journal" / f"lint-{date.today()}.md"
    assert report_path.exists()
