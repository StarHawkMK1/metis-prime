from __future__ import annotations

import json
from pathlib import Path

import pytest

from second_brain.graph.query import GraphQuery

SAMPLE_GRAPH = {
    "nodes": [
        {
            "id": "n1",
            "label": "Machine Learning",
            "source_file": "wiki/ml.md",
            "source_location": "",
        },
        {"id": "n2", "label": "Python", "source_file": "wiki/python.md", "source_location": ""},
        {
            "id": "n3",
            "label": "Data Science",
            "source_file": "wiki/ds.md",
            "source_location": "",
        },
        {
            "id": "n4",
            "label": "Statistics",
            "source_file": "wiki/stats.md",
            "source_location": "",
        },
    ],
    "edges": [
        {"source": "n1", "target": "n2", "relation": "uses", "confidence": "EXTRACTED"},
        {"source": "n2", "target": "n3", "relation": "applied_in", "confidence": "INFERRED"},
        {"source": "n3", "target": "n4", "relation": "requires", "confidence": "AMBIGUOUS"},
    ],
    "hyperedges": [],
}


@pytest.fixture
def graph_path(tmp_path: Path) -> Path:
    path = tmp_path / "graph" / "graphify-out" / "graph.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(SAMPLE_GRAPH), encoding="utf-8")
    return path


def test_available_true_when_file_exists(graph_path):
    assert GraphQuery(graph_path).available is True


def test_available_false_when_missing(tmp_path):
    assert GraphQuery(tmp_path / "no" / "graph.json").available is False


def test_search_nodes_case_insensitive(graph_path):
    results = GraphQuery(graph_path).search_nodes("machine")
    assert len(results) == 1
    assert results[0].label == "Machine Learning"
    assert results[0].source_file == "wiki/ml.md"


def test_search_nodes_no_match(graph_path):
    assert GraphQuery(graph_path).search_nodes("nonexistent") == []


def test_search_nodes_unavailable(tmp_path):
    assert GraphQuery(tmp_path / "nope.json").search_nodes("x") == []


def test_get_neighbors_depth_1(graph_path):
    ctx = GraphQuery(graph_path).get_neighbors("n1", depth=1)
    ids = {n.id for n in ctx.nodes}
    assert "n1" in ids
    assert "n2" in ids
    assert "n3" not in ids


def test_get_neighbors_depth_2(graph_path):
    ctx = GraphQuery(graph_path).get_neighbors("n1", depth=2)
    ids = {n.id for n in ctx.nodes}
    assert "n3" in ids
    assert "n4" not in ids


def test_get_neighbors_depth_3(graph_path):
    ctx = GraphQuery(graph_path).get_neighbors("n1", depth=3)
    ids = {n.id for n in ctx.nodes}
    assert "n4" in ids


def test_edge_confidence_preserved(graph_path):
    ctx = GraphQuery(graph_path).get_neighbors("n1", depth=1)
    edge = next(e for e in ctx.edges if e.source == "n1" and e.target == "n2")
    assert edge.confidence == "EXTRACTED"


def test_inferred_edge_preserved(graph_path):
    ctx = GraphQuery(graph_path).get_neighbors("n2", depth=1)
    edge = next(e for e in ctx.edges if e.relation == "applied_in")
    assert edge.confidence == "INFERRED"


def test_get_neighbors_unavailable(tmp_path):
    ctx = GraphQuery(tmp_path / "nope.json").get_neighbors("n1")
    assert ctx.nodes == []
    assert ctx.edges == []


def test_find_node_by_label(graph_path):
    node = GraphQuery(graph_path).find_node("Python")
    assert node is not None
    assert node.id == "n2"


def test_find_node_not_found(graph_path):
    assert GraphQuery(graph_path).find_node("Haskell") is None


def test_god_nodes_ordering(graph_path):
    gods = GraphQuery(graph_path).god_nodes(top_n=3)
    assert len(gods) >= 1
    # n2 connects to n1 and n3 — highest degree
    assert gods[0].id == "n2"


def test_search_and_expand_returns_matched_and_neighbors(graph_path):
    ctx = GraphQuery(graph_path).search_and_expand("machine", depth=1)
    ids = {n.id for n in ctx.nodes}
    assert "n1" in ids
    assert "n2" in ids


def test_shortest_path_direct(graph_path):
    path = GraphQuery(graph_path).shortest_path("n1", "n2")
    assert path == ["n1", "n2"]


def test_shortest_path_multi_hop(graph_path):
    path = GraphQuery(graph_path).shortest_path("n1", "n3")
    assert path == ["n1", "n2", "n3"]


def test_shortest_path_not_found(graph_path):
    assert GraphQuery(graph_path).shortest_path("n1", "n99") == []
