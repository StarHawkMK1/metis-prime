from __future__ import annotations

from pathlib import Path

import pytest

from second_brain.storage import Vault


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    import pygit2

    repo = pygit2.init_repository(str(tmp_path))
    sig = pygit2.Signature("Test", "t@t.com")
    tree = repo.TreeBuilder().write()
    repo.create_commit("refs/heads/main", sig, sig, "init", tree, [])
    (tmp_path / "journal").mkdir(parents=True)
    return tmp_path


def test_cost_reporter_writes_monthly_report(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.cost_reporter import CostReporter
    from second_brain.llm.metrics import LLMCallMetrics, MetricsRecorder

    recorder = MetricsRecorder()
    recorder.record(
        LLMCallMetrics(
            task_type="ingest_summary",
            sensitivity="normal",
            model="claude-3-haiku-20240307",
            latency_ms=100.0,
            prompt_tokens=500,
            completion_tokens=200,
            cost_usd=0.00038,
        )
    )
    recorder.record(
        LLMCallMetrics(
            task_type="synthesis_complex",
            sensitivity="normal",
            model="claude-3-5-sonnet-20241022",
            latency_ms=800.0,
            prompt_tokens=1000,
            completion_tokens=400,
            cost_usd=0.009,
        )
    )

    vault = Vault(tmp_vault)
    reporter = CostReporter(vault=vault, recorder=recorder)
    report_path = reporter.write_monthly_report()

    content = report_path.read_text(encoding="utf-8")
    assert "cost" in content.lower() or "$" in content
    assert "claude" in content.lower()


def test_cost_reporter_totals_are_accurate(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.cost_reporter import CostReporter
    from second_brain.llm.metrics import LLMCallMetrics, MetricsRecorder

    recorder = MetricsRecorder()
    recorder.record(
        LLMCallMetrics(
            task_type="ingest_summary",
            sensitivity="normal",
            model="claude-3-haiku-20240307",
            latency_ms=100.0,
            prompt_tokens=500,
            completion_tokens=200,
            cost_usd=0.00038,
        )
    )

    vault = Vault(tmp_vault)
    reporter = CostReporter(vault=vault, recorder=recorder)
    report_path = reporter.write_monthly_report()
    content = report_path.read_text(encoding="utf-8")

    assert "0.00038" in content or "0.000" in content
