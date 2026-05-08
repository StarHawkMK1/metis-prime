from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from second_brain.graph.builder import GraphBuilder

SAMPLE_GRAPH = {
    "nodes": [
        {
            "id": "n1",
            "label": "Machine Learning",
            "source_file": "wiki/ml.md",
            "source_location": "",
        },
        {
            "id": "n2",
            "label": "Python",
            "source_file": "wiki/python.md",
            "source_location": "",
        },
    ],
    "edges": [
        {"source": "n1", "target": "n2", "relation": "uses", "confidence": "EXTRACTED"},
    ],
    "hyperedges": [],
    "input_tokens": 100,
    "output_tokens": 50,
}


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "graph").mkdir()
    (tmp_path / "wiki").mkdir()
    return tmp_path


@pytest.fixture
def graph_output(vault: Path) -> Path:
    out = vault / "graph" / "graphify-out"
    out.mkdir(parents=True)
    (out / "graph.json").write_text(json.dumps(SAMPLE_GRAPH), encoding="utf-8")
    (out / "graph.html").write_text("<html></html>", encoding="utf-8")
    return out


def test_build_calls_graphify_with_wiki_flag(mocker, vault, graph_output):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stderr="")

    builder = GraphBuilder(vault)
    builder.build()

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "graphify" in cmd
    assert "--wiki" in cmd


def test_build_sets_anthropic_base_url_in_env(mocker, vault, graph_output):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stderr="")

    builder = GraphBuilder(vault)
    builder.build()

    call_kwargs = mock_run.call_args[1]
    env = call_kwargs.get("env", {})
    assert "ANTHROPIC_BASE_URL" in env


def test_build_raises_on_nonzero_returncode(mocker, vault):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=1, stderr="error: something failed")

    builder = GraphBuilder(vault)
    with pytest.raises(RuntimeError, match="graphify build failed"):
        builder.build()


def test_build_generates_graph_report(mocker, vault, graph_output):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stderr="")

    builder = GraphBuilder(vault)
    builder.build()

    report = vault / "GRAPH_REPORT.md"
    assert report.exists()
    text = report.read_text()
    assert "Nodes: 2" in text
    assert "Edges: 1" in text
    assert "EXTRACTED: 1" in text


def test_build_returns_graph_json_path(mocker, vault, graph_output):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stderr="")

    builder = GraphBuilder(vault)
    result = builder.build()

    assert result == vault / "graph" / "graphify-out" / "graph.json"


def test_update_passes_update_flag(mocker, vault, graph_output):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stderr="")

    builder = GraphBuilder(vault)
    builder.update()

    cmd = mock_run.call_args[0][0]
    assert "--update" in cmd


def test_graph_json_path_property(vault):
    builder = GraphBuilder(vault)
    assert builder.graph_json_path == vault / "graph" / "graphify-out" / "graph.json"
