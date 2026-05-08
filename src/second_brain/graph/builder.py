from __future__ import annotations

import json
import os
import subprocess
from datetime import date
from pathlib import Path

from ..config import Settings

_SCOPE_TARGETS: dict[str, str] = {
    "wiki": "../wiki",
    "raw": "../raw",
    "all": "..",
}


class GraphBuilder:
    def __init__(self, vault_path: Path, settings: Settings | None = None) -> None:
        self.vault_path = vault_path.expanduser().resolve()
        self._settings = settings or Settings()
        self._graph_dir = self.vault_path / "graph"

    @property
    def graph_json_path(self) -> Path:
        return self._graph_dir / "graphify-out" / "graph.json"

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["ANTHROPIC_BASE_URL"] = str(self._settings.litellm_base_url)
        if self._settings.litellm_master_key:
            env["ANTHROPIC_API_KEY"] = self._settings.litellm_master_key.get_secret_value()
        return env

    def _run(self, target: str, extra_flags: list[str]) -> None:
        self._graph_dir.mkdir(parents=True, exist_ok=True)
        cmd = ["graphify", target, "--wiki"] + extra_flags
        result = subprocess.run(
            cmd,
            cwd=str(self._graph_dir),
            capture_output=True,
            text=True,
            env=self._env(),
        )
        if result.returncode != 0:
            raise RuntimeError(f"graphify build failed:\n{result.stderr}")

    def build(self, scope: str = "wiki") -> Path:
        """Full build. scope: 'wiki' | 'raw' | 'all'."""
        target = _SCOPE_TARGETS.get(scope, "../wiki")
        self._run(target, [])
        self._write_report()
        return self.graph_json_path

    def update(self, scope: str = "wiki") -> Path:
        """Incremental update (re-extracts only changed files)."""
        target = _SCOPE_TARGETS.get(scope, "../wiki")
        self._run(target, ["--update", "--no-viz"])
        return self.graph_json_path

    def _write_report(self) -> Path:
        report_path = self.vault_path / "GRAPH_REPORT.md"
        if not self.graph_json_path.exists():
            return report_path

        data = json.loads(self.graph_json_path.read_text(encoding="utf-8"))
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        conf_counts: dict[str, int] = {}
        for e in edges:
            conf = e.get("confidence", "EXTRACTED")
            conf_counts[conf] = conf_counts.get(conf, 0) + 1

        degree: dict[str, int] = {}
        for e in edges:
            degree[e["source"]] = degree.get(e["source"], 0) + 1
            degree[e["target"]] = degree.get(e["target"], 0) + 1

        node_labels = {n["id"]: n["label"] for n in nodes}
        top_nodes = sorted(degree.items(), key=lambda x: x[1], reverse=True)[:10]

        today = date.today().isoformat()
        lines = [
            f"# Graph Report - {today}",
            "",
            "## Statistics",
            f"- Nodes: {len(nodes)}",
            f"- Edges: {len(edges)}",
            "- Confidence breakdown:",
        ]
        for conf, count in sorted(conf_counts.items()):
            lines.append(f"  - {conf}: {count}")

        lines += ["", "## Top Connected Nodes", ""]
        for i, (nid, deg) in enumerate(top_nodes, 1):
            label = node_labels.get(nid, nid)
            lines.append(f"{i}. [[{label}]] - {deg} connections")

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path
