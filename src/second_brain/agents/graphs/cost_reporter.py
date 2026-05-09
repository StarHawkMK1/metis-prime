from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

import structlog

from ...llm.metrics import MetricsRecorder
from ...storage.vault import Vault

log = structlog.get_logger(__name__)


class CostReporter:
    def __init__(self, vault: Vault, recorder: MetricsRecorder) -> None:
        self._vault = vault
        self._recorder = recorder

    def write_monthly_report(self, month: date | None = None) -> Path:
        """Write journal/cost-YYYY-MM.md and return the path."""
        target = month or date.today()
        month_str = target.strftime("%Y-%m")

        records = [
            r
            for r in self._recorder.all()
            if r.timestamp.strftime("%Y-%m") == month_str and r.error is None
        ]

        total_cost = sum(r.cost_usd for r in records)
        total_calls = len(records)
        by_model: dict[str, float] = defaultdict(float)
        by_task: dict[str, float] = defaultdict(float)
        for r in records:
            by_model[r.model] += r.cost_usd
            by_task[r.task_type] += r.cost_usd

        lines = [
            f"# LLM Cost Report — {month_str}",
            "",
            f"**Total calls:** {total_calls}",
            f"**Total cost:** ${total_cost:.6f} USD",
            "",
            "## By Model",
            "",
        ]
        for model, cost in sorted(by_model.items(), key=lambda x: -x[1]):
            lines.append(f"- `{model}`: ${cost:.6f}")
        lines += ["", "## By Task Type", ""]
        for task, cost in sorted(by_task.items(), key=lambda x: -x[1]):
            lines.append(f"- `{task}`: ${cost:.6f}")
        lines.append("")

        journal_dir = self._vault.path / "journal"
        journal_dir.mkdir(parents=True, exist_ok=True)
        report_path = journal_dir / f"cost-{month_str}.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        log.info("cost_reporter.wrote", path=str(report_path), total_cost=total_cost)
        return report_path
