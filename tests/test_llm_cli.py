from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from second_brain.cli import app

runner = CliRunner()


def test_llm_route_ingest_normal() -> None:
    result = runner.invoke(
        app, ["llm", "route", "--task", "ingest_summary", "--sensitivity", "normal"]
    )
    assert result.exit_code == 0
    assert "bulk" in result.output


def test_llm_route_synthesis_private() -> None:
    result = runner.invoke(
        app, ["llm", "route", "--task", "synthesis_complex", "--sensitivity", "private"]
    )
    assert result.exit_code == 0
    assert "local-fast" in result.output


def test_llm_route_invalid_task() -> None:
    result = runner.invoke(
        app, ["llm", "route", "--task", "nonexistent", "--sensitivity", "normal"]
    )
    assert result.exit_code != 0


def test_llm_route_invalid_sensitivity() -> None:
    result = runner.invoke(
        app, ["llm", "route", "--task", "ingest_summary", "--sensitivity", "secret"]
    )
    assert result.exit_code != 0


def test_llm_test_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_router = MagicMock()
    mock_router.complete.return_value = "pong"
    with patch("second_brain.cli.LLMRouter", return_value=mock_router):
        result = runner.invoke(app, ["llm", "test"])
    assert result.exit_code == 0
    assert "pong" in result.output or "ok" in result.output.lower()


def test_llm_test_router_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from second_brain.llm.errors import RouterError

    mock_router = MagicMock()
    mock_router.complete.side_effect = RouterError("proxy not running")
    with patch("second_brain.cli.LLMRouter", return_value=mock_router):
        result = runner.invoke(app, ["llm", "test"])
    assert result.exit_code == 1
    assert "proxy not running" in result.output
