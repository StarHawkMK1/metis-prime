from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from second_brain.agents.ingest import IngestResult
from second_brain.agents.lint import LintIssue, LintReport
from second_brain.agents.query import QueryResult
from second_brain.cli import app

runner = CliRunner()


def test_ingest_cli_single_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    mock_graph = MagicMock()
    mock_graph.run.return_value = IngestResult(
        decision="create",
        wiki_path="wiki/concepts/test.md",
        archived_path=tmp_path / "raw" / "archived" / "test.md",
        source_name="test.md",
    )
    with patch("second_brain.agents.graphs.ingest_graph.IngestGraph", return_value=mock_graph):
        result = runner.invoke(app, ["ingest", "raw/inbox/test.md"])
    assert result.exit_code == 0
    assert "create" in result.output


def test_ingest_cli_inbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inbox = tmp_path / "raw" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "a.md").write_text("content a", encoding="utf-8")
    (inbox / "b.md").write_text("content b", encoding="utf-8")
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))

    mock_graph = MagicMock()
    mock_graph.run.return_value = IngestResult(
        decision="create",
        wiki_path="wiki/concepts/x.md",
        archived_path=tmp_path / "raw" / "archived" / "a.md",
        source_name="a.md",
    )
    with patch("second_brain.agents.graphs.ingest_graph.IngestGraph", return_value=mock_graph):
        result = runner.invoke(app, ["ingest", "--inbox"])
    assert result.exit_code == 0
    assert mock_graph.run.call_count == 2


def test_ingest_cli_no_args_exits_nonzero() -> None:
    result = runner.invoke(app, ["ingest"])
    assert result.exit_code != 0


def test_query_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    mock_graph = MagicMock()
    mock_graph.ask.return_value = QueryResult(
        answer="Transformers use attention.", sources=["wiki/concepts/transformers.md"]
    )
    with patch("second_brain.agents.graphs.query_graph.QueryGraph", return_value=mock_graph):
        result = runner.invoke(app, ["query", "What are transformers?"])
    assert result.exit_code == 0
    assert "Transformers use attention." in result.output


def test_lint_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    mock_graph = MagicMock()
    mock_graph.run.return_value = LintReport(
        issues=[LintIssue(kind="broken_wikilink", page="wiki/concepts/a.md", detail="test")]
    )
    with patch("second_brain.agents.graphs.lint_graph.LintGraph", return_value=mock_graph):
        result = runner.invoke(app, ["lint"])
    assert result.exit_code == 0
    assert "1" in result.output or "broken" in result.output.lower()


def test_lint_cli_clean_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    mock_graph = MagicMock()
    mock_graph.run.return_value = LintReport(issues=[])
    with patch("second_brain.agents.graphs.lint_graph.LintGraph", return_value=mock_graph):
        result = runner.invoke(app, ["lint"])
    assert result.exit_code == 0
    assert "0" in result.output or "no issues" in result.output.lower()


def test_graph_build_command(mocker, tmp_path):
    from typer.testing import CliRunner

    from second_brain.cli import app

    mock_builder = mocker.MagicMock()
    mock_builder.build.return_value = tmp_path / "graph" / "graphify-out" / "graph.json"
    mocker.patch("second_brain.graph.builder.GraphBuilder", return_value=mock_builder)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["graph", "build", "--vault", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "graph.json" in result.output


def test_graph_build_update_flag(mocker, tmp_path):
    from typer.testing import CliRunner

    from second_brain.cli import app

    mock_builder = mocker.MagicMock()
    mock_builder.update.return_value = tmp_path / "graph" / "graphify-out" / "graph.json"
    mocker.patch("second_brain.graph.builder.GraphBuilder", return_value=mock_builder)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["graph", "build", "--vault", str(tmp_path), "--update"],
    )
    assert result.exit_code == 0, result.output
    mock_builder.update.assert_called_once()


def test_graph_query_command(mocker, tmp_path):
    from typer.testing import CliRunner

    from second_brain.agents.query import QueryResult
    from second_brain.cli import app

    mock_agent = mocker.MagicMock()
    mock_agent.ask.return_value = QueryResult(answer="Graph answer.", sources=["wiki/ml.md"])
    mocker.patch("second_brain.agents.query.QueryAgent", return_value=mock_agent)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["graph", "query", "What is ML?", "--vault", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "Graph answer." in result.output


def test_task_extract_command_exists(tmp_vault: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from second_brain.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["task", "--help"])
    assert result.exit_code == 0
    assert "extract" in result.output


def test_ingest_command_uses_ingest_graph(tmp_vault: Path, monkeypatch) -> None:
    """ingest command should invoke IngestGraph.run(), not IngestAgent.run()."""
    from unittest.mock import MagicMock, patch

    from typer.testing import CliRunner

    from second_brain.cli import app

    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_vault))

    source = tmp_vault / "raw" / "inbox" / "test.md"
    source.write_text("# Test\n\nContent.", encoding="utf-8")

    mock_result = MagicMock()
    mock_result.decision = "create"
    mock_result.wiki_path = "wiki/concepts/test.md"

    runner = CliRunner()
    with patch("second_brain.agents.graphs.ingest_graph.IngestGraph.run", return_value=mock_result):
        result = runner.invoke(app, ["ingest", "raw/inbox/test.md"])
    assert result.exit_code == 0
