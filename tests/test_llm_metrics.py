from __future__ import annotations

from datetime import datetime

from second_brain.llm.metrics import LLMCallMetrics, MetricsRecorder


def test_metrics_records_are_stored() -> None:
    recorder = MetricsRecorder()
    m = LLMCallMetrics(
        task_type="ingest_summary",
        sensitivity="normal",
        model="bulk",
        latency_ms=123.4,
        prompt_tokens=50,
        completion_tokens=200,
    )
    recorder.record(m)
    assert len(recorder.all()) == 1
    assert recorder.all()[0].model == "bulk"


def test_metrics_clear() -> None:
    recorder = MetricsRecorder()
    recorder.record(
        LLMCallMetrics(
            task_type="lint_check",
            sensitivity="normal",
            model="bulk",
            latency_ms=50.0,
            prompt_tokens=10,
            completion_tokens=5,
        )
    )
    recorder.clear()
    assert recorder.all() == []


def test_metrics_error_field_defaults_none() -> None:
    m = LLMCallMetrics(
        task_type="vision",
        sensitivity="private",
        model="local-fast",
        latency_ms=200.0,
        prompt_tokens=100,
        completion_tokens=80,
    )
    assert m.error is None


def test_metrics_timestamp_is_recent() -> None:
    before = datetime.now()
    m = LLMCallMetrics(
        task_type="synthesis_complex",
        sensitivity="normal",
        model="smart-cloud",
        latency_ms=1800.0,
        prompt_tokens=500,
        completion_tokens=300,
    )
    after = datetime.now()
    assert before <= m.timestamp <= after


def test_metrics_all_returns_copy() -> None:
    recorder = MetricsRecorder()
    snapshot = recorder.all()
    snapshot.append(  # type: ignore[arg-type]
        LLMCallMetrics(
            task_type="ingest_summary",
            sensitivity="normal",
            model="bulk",
            latency_ms=0.0,
            prompt_tokens=0,
            completion_tokens=0,
        )
    )
    assert recorder.all() == []
