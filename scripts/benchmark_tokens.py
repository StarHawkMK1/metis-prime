#!/usr/bin/env python3
"""
Benchmark: compare prompt tokens for wiki-only vs graph-augmented QueryAgent.

Usage:
    SECOND_BRAIN_VAULT_PATH=/path/to/vault python scripts/benchmark_tokens.py

Writes results to journal/benchmark.md in the vault.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

BENCHMARK_QUESTIONS = [
    "What is machine learning?",
    "How does Python handle memory management?",
    "What is the difference between supervised and unsupervised learning?",
    "What are the key principles of data science?",
    "How do neural networks learn?",
    "What is gradient descent?",
    "How does version control work?",
    "What is a REST API?",
    "Explain the concept of recursion.",
    "What is the CAP theorem?",
]


@dataclass
class BenchmarkEntry:
    question: str
    wiki_tokens: int
    graph_tokens: int

    @property
    def reduction_pct(self) -> float:
        if self.wiki_tokens == 0:
            return 0.0
        return (self.wiki_tokens - self.graph_tokens) / self.wiki_tokens * 100


def _count_tokens(text: str) -> int:
    """Approximate token count (1 token ~= 4 chars)."""
    return max(1, len(text) // 4)


def run_wiki_only(vault_path: Path, question: str) -> int:
    """Return estimated prompt tokens for BM25-only context."""
    from second_brain.agents.search import WikiSearcher
    from second_brain.storage.vault import Vault

    vault = Vault(vault_path)
    searcher = WikiSearcher(vault)
    results = searcher.search(question, top_k=5)
    context = "\n\n".join(r.content[:800] for r in results)
    prompt = f"Question: {question}\n\nRelevant wiki pages:\n\n{context}"
    return _count_tokens(prompt)


def run_graph_augmented(vault_path: Path, question: str) -> int:
    """Return estimated prompt tokens for graph-augmented context."""
    from second_brain.graph.query import GraphQuery

    graph_path = vault_path / "graph" / "graphify-out" / "graph.json"
    gq = GraphQuery(graph_path)

    if not gq.available:
        print("  [warn] graph.json not found -- using wiki-only fallback")
        return run_wiki_only(vault_path, question)

    ctx = gq.search_and_expand(question, depth=2)
    parts: list[str] = []
    seen: set[str] = set()
    for node in ctx.nodes:
        if not node.source_file or node.source_file in seen:
            continue
        seen.add(node.source_file)
        p = vault_path / node.source_file
        if p.exists():
            parts.append(p.read_text(encoding="utf-8")[:800])

    context = "\n\n".join(parts)
    prompt = f"Question: {question}\n\nRelevant wiki pages:\n\n{context}"
    return _count_tokens(prompt)


def write_report(vault_path: Path, entries: list[BenchmarkEntry]) -> Path:
    if not entries:
        return vault_path / "journal" / "benchmark.md"

    avg_wiki = sum(e.wiki_tokens for e in entries) / len(entries)
    avg_graph = sum(e.graph_tokens for e in entries) / len(entries)
    avg_reduction = sum(e.reduction_pct for e in entries) / len(entries)

    lines = [
        f"# Token Benchmark -- {date.today().isoformat()}",
        "",
        "## Summary",
        f"- Questions tested: {len(entries)}",
        f"- Avg wiki-only tokens: {avg_wiki:.0f}",
        f"- Avg graph-augmented tokens: {avg_graph:.0f}",
        f"- Avg token reduction: {avg_reduction:.1f}%",
        "- **Target**: >= 30% reduction",
        f"- **Result**: {'PASS' if avg_reduction >= 30 else 'FAIL'}",
        "",
        "## Per-Question Results",
        "",
        "| Question | Wiki tokens | Graph tokens | Reduction |",
        "|----------|-------------|--------------|-----------|",
    ]
    for e in entries:
        q = e.question[:50]
        lines.append(f"| {q} | {e.wiki_tokens} | {e.graph_tokens} | {e.reduction_pct:.1f}% |")

    journal = vault_path / "journal"
    journal.mkdir(exist_ok=True)
    report_path = journal / "benchmark.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    vault_path_str = os.environ.get("SECOND_BRAIN_VAULT_PATH", "")
    if not vault_path_str:
        print("Error: SECOND_BRAIN_VAULT_PATH not set")
        raise SystemExit(1)

    vault_path = Path(vault_path_str).expanduser().resolve()
    print(f"Vault: {vault_path}")
    print(f"Running {len(BENCHMARK_QUESTIONS)} benchmark questions...\n")

    entries: list[BenchmarkEntry] = []
    for i, question in enumerate(BENCHMARK_QUESTIONS, 1):
        print(f"[{i}/{len(BENCHMARK_QUESTIONS)}] {question[:60]}")
        wiki_tokens = run_wiki_only(vault_path, question)
        graph_tokens = run_graph_augmented(vault_path, question)
        entry = BenchmarkEntry(question, wiki_tokens, graph_tokens)
        entries.append(entry)
        print(f"  wiki={wiki_tokens} graph={graph_tokens} reduction={entry.reduction_pct:.1f}%")

    report_path = write_report(vault_path, entries)
    avg_reduction = sum(e.reduction_pct for e in entries) / len(entries)
    print(f"\nBenchmark complete. Avg reduction: {avg_reduction:.1f}%")
    print(f"Report: {report_path}")

    if avg_reduction < 30:
        print("WARNING: reduction < 30% -- tune graph_depth or expand wiki coverage")


if __name__ == "__main__":
    main()
