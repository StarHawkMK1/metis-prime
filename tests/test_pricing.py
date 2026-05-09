from __future__ import annotations

from pathlib import Path

import pytest


def test_compute_cost_haiku() -> None:
    from second_brain.llm.pricing import compute_cost

    # $0.25/M input + $1.25/M output = $1.50 for 1M + 1M tokens
    cost = compute_cost(
        "claude-3-haiku-20240307", prompt_tokens=1_000_000, completion_tokens=1_000_000
    )
    assert cost == pytest.approx(1.50)


def test_compute_cost_unknown_model_returns_zero() -> None:
    from second_brain.llm.pricing import compute_cost

    assert compute_cost("unknown-xyz", prompt_tokens=9999, completion_tokens=9999) == 0.0


def test_compute_cost_local_model_is_zero() -> None:
    from second_brain.llm.pricing import compute_cost

    assert compute_cost("qwen3:30b-a3b", prompt_tokens=50_000, completion_tokens=10_000) == 0.0


def test_llm_call_metrics_has_cost_usd() -> None:
    from second_brain.llm.metrics import LLMCallMetrics

    m = LLMCallMetrics(
        task_type="ingest_summary",
        sensitivity="normal",
        model="claude-3-haiku-20240307",
        latency_ms=42.0,
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.0000875,
    )
    assert m.cost_usd == pytest.approx(0.0000875)


def test_router_get_last_cost_returns_zero_when_no_calls() -> None:
    from unittest.mock import MagicMock, patch

    from second_brain.config import Settings
    from second_brain.llm.router import LLMRouter

    settings = MagicMock(spec=Settings)
    settings.litellm_base_url = "http://localhost:4000"
    settings.litellm_master_key = None
    settings.local_only = False
    with patch("second_brain.llm.router.OpenAI"):
        router = LLMRouter(settings=settings)
    assert router.get_last_cost() == 0.0


def test_metrics_recorder_persists_to_jsonl(tmp_path: Path) -> None:
    from second_brain.llm.metrics import LLMCallMetrics, MetricsRecorder

    log_path = tmp_path / "metrics" / "2026-05.jsonl"
    recorder = MetricsRecorder(log_path=log_path)
    recorder.record(
        LLMCallMetrics(
            task_type="ingest_summary",
            sensitivity="normal",
            model="claude-3-haiku-20240307",
            latency_ms=50.0,
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.0001,
        )
    )
    assert log_path.exists()
    loaded = MetricsRecorder.from_jsonl(log_path)
    assert len(loaded.all()) == 1
    assert loaded.all()[0].cost_usd == pytest.approx(0.0001)


def test_router_get_last_cost_returns_nonzero_after_call() -> None:
    from unittest.mock import MagicMock, patch

    from second_brain.config import Settings
    from second_brain.llm.router import LLMRouter

    settings = MagicMock(spec=Settings)
    settings.litellm_base_url = "http://localhost:4000"
    settings.litellm_master_key = None
    settings.local_only = False

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "test answer"
    mock_response.usage.prompt_tokens = 1_000_000
    mock_response.usage.completion_tokens = 1_000_000

    with patch("second_brain.llm.router.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client
        router = LLMRouter(settings=settings)

    router.complete(
        [{"role": "user", "content": "hello"}],
        task_type="ingest_summary",
        sensitivity="normal",
    )
    cost = router.get_last_cost()
    assert cost > 0.0, f"Expected non-zero cost, got {cost}"
