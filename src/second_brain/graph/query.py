from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GraphNode:
    id: str
    label: str
    source_file: str
    source_location: str = ""


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str
    confidence: str  # EXTRACTED | INFERRED | AMBIGUOUS


@dataclass
class GraphContext:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


class GraphQuery:
    def __init__(self, graph_json_path: Path) -> None:
        self._path = graph_json_path
        self._data: dict[str, Any] | None = None

    @property
    def available(self) -> bool:
        return self._path.exists()

    def _load(self) -> dict[str, Any]:
        if self._data is None:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
        return self._data

    def _node_map(self) -> dict[str, dict[str, Any]]:
        return {n["id"]: n for n in self._load().get("nodes", [])}

    def _adj(self) -> dict[str, list[GraphEdge]]:
        adj: dict[str, list[GraphEdge]] = {}
        for e in self._load().get("edges", []):
            edge = GraphEdge(
                source=e["source"],
                target=e["target"],
                relation=e["relation"],
                confidence=e.get("confidence", "EXTRACTED"),
            )
            adj.setdefault(e["source"], []).append(edge)
            adj.setdefault(e["target"], []).append(edge)
        return adj

    def _make_node(self, raw: dict[str, Any]) -> GraphNode:
        return GraphNode(
            id=raw["id"],
            label=raw["label"],
            source_file=raw.get("source_file", ""),
            source_location=raw.get("source_location", ""),
        )

    def search_nodes(self, query: str) -> list[GraphNode]:
        """Return nodes whose label contains query (case-insensitive)."""
        if not self.available:
            return []
        q = query.lower()
        return [
            self._make_node(n) for n in self._load().get("nodes", []) if q in n["label"].lower()
        ]

    def find_node(self, name: str) -> GraphNode | None:
        """Return first node whose label exactly matches name."""
        if not self.available:
            return None
        for n in self._load().get("nodes", []):
            if n["label"] == name:
                return self._make_node(n)
        return None

    def get_neighbors(self, node_id: str, depth: int = 1) -> GraphContext:
        """BFS from node_id out to `depth` hops."""
        if not self.available:
            return GraphContext()
        node_map = self._node_map()
        adj = self._adj()

        visited: set[str] = {node_id}
        frontier: set[str] = {node_id}
        collected_edges: list[GraphEdge] = []
        seen_edge_keys: set[tuple[str, str, str]] = set()

        for _ in range(depth):
            next_frontier: set[str] = set()
            for nid in frontier:
                for edge in adj.get(nid, []):
                    key = (edge.source, edge.target, edge.relation)
                    if key not in seen_edge_keys:
                        seen_edge_keys.add(key)
                        collected_edges.append(edge)
                    neighbor = edge.target if edge.source == nid else edge.source
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
            frontier = next_frontier

        nodes = [self._make_node(node_map[nid]) for nid in visited if nid in node_map]
        return GraphContext(nodes=nodes, edges=collected_edges)

    def shortest_path(self, from_id: str, to_id: str) -> list[str]:
        """BFS shortest path between two node IDs. Returns [] if unreachable."""
        if not self.available:
            return []
        adj = self._adj()
        queue: deque[list[str]] = deque([[from_id]])
        visited: set[str] = {from_id}

        while queue:
            path = queue.popleft()
            current = path[-1]
            if current == to_id:
                return path
            for edge in adj.get(current, []):
                neighbor = edge.target if edge.source == current else edge.source
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return []

    def god_nodes(self, top_n: int = 10) -> list[GraphNode]:
        """Return the top_n highest-degree nodes (most connections)."""
        if not self.available:
            return []
        degree: dict[str, int] = {}
        for e in self._load().get("edges", []):
            degree[e["source"]] = degree.get(e["source"], 0) + 1
            degree[e["target"]] = degree.get(e["target"], 0) + 1

        node_map = self._node_map()
        ranked = sorted(degree.items(), key=lambda x: x[1], reverse=True)[:top_n]
        return [self._make_node(node_map[nid]) for nid, _ in ranked if nid in node_map]

    def search_and_expand(self, query: str, depth: int = 2) -> GraphContext:
        """Match nodes by query string then expand to their BFS neighborhood."""
        matched = self.search_nodes(query)
        if not matched:
            return GraphContext()

        combined_nodes: dict[str, GraphNode] = {}
        combined_edges: dict[tuple[str, str, str], GraphEdge] = {}

        for node in matched:
            ctx = self.get_neighbors(node.id, depth=depth)
            for n in ctx.nodes:
                combined_nodes[n.id] = n
            for e in ctx.edges:
                combined_edges[(e.source, e.target, e.relation)] = e

        return GraphContext(
            nodes=list(combined_nodes.values()),
            edges=list(combined_edges.values()),
        )
