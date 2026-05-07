from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from second_brain.config import Settings
from second_brain.llm.errors import RouterError
from second_brain.llm.metrics import MetricsRecorder
from second_brain.llm.router import LLMRouter


def _make_mock_response(
    content: str = "hello", prompt_tokens: int = 10, completion_tokens: int = 5
) -> MagicMock:
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


@pytest.fixture()
def mock_openai_create() -> MagicMock:
    with patch("second_brain.llm.router.OpenAI") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.chat.completions.create.return_value = _make_mock_response("ok")
        yield instance.chat.completions.create


@pytest.fixture()
def recorder() -> MetricsRecorder:
    return MetricsRecorder()


@pytest.fixture()
def router(mock_openai_create: MagicMock, recorder: MetricsRecorder) -> LLMRouter:
    settings = Settings()
    return LLMRouter(settings=settings, metrics_recorder=recorder)


def test_complete_returns_content(router: LLMRouter, mock_openai_create: MagicMock) -> None:
    result = router.complete(
        [{"role": "user", "content": "ping"}],
        task_type="ingest_summary",
        sensitivity="normal",
    )
    assert result == "ok"


def test_complete_calls_correct_model_for_ingest_summary(
    router: LLMRouter, mock_openai_create: MagicMock
) -> None:
    router.complete(
        [{"role": "user", "content": "summarize"}],
        task_type="ingest_summary",
        sensitivity="normal",
    )
    call_kwargs = mock_openai_create.call_args
    assert call_kwargs.kwargs["model"] == "bulk"


def test_complete_calls_local_fast_for_private(
    router: LLMRouter, mock_openai_create: MagicMock
) -> None:
    router.complete(
        [{"role": "user", "content": "secret"}],
        task_type="ingest_summary",
        sensitivity="private",
    )
    call_kwargs = mock_openai_create.call_args
    assert call_kwargs.kwargs["model"] == "local-fast"


def test_complete_records_metrics(
    router: LLMRouter, mock_openai_create: MagicMock, recorder: MetricsRecorder
) -> None:
    router.complete(
        [{"role": "user", "content": "ping"}],
        task_type="lint_check",
        sensitivity="normal",
    )
    records = recorder.all()
    assert len(records) == 1
    assert records[0].task_type == "lint_check"
    assert records[0].model == "bulk"
    assert records[0].latency_ms >= 0
    assert records[0].error is None


def test_complete_records_error_on_exception(
    router: LLMRouter, mock_openai_create: MagicMock, recorder: MetricsRecorder
) -> None:
    mock_openai_create.side_effect = RuntimeError("connection refused")
    with pytest.raises(RuntimeError):
        router.complete(
            [{"role": "user", "content": "ping"}],
            task_type="ingest_summary",
            sensitivity="normal",
        )
    records = recorder.all()
    assert records[0].error == "connection refused"


def test_local_only_raises_for_cloud_task() -> None:
    settings = Settings()
    settings.local_only = True  # type: ignore[misc]
    with patch("second_brain.llm.router.OpenAI"):
        router = LLMRouter(settings=settings)
    with pytest.raises(RouterError, match="local_only"):
        router.complete(
            [{"role": "user", "content": "synthesize"}],
            task_type="synthesis_complex",
            sensitivity="normal",
        )


def test_local_only_does_not_raise_for_local_task() -> None:
    settings = Settings()
    settings.local_only = True  # type: ignore[misc]
    with patch("second_brain.llm.router.OpenAI") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.chat.completions.create.return_value = _make_mock_response("local ok")
        router = LLMRouter(settings=settings)
        result = router.complete(
            [{"role": "user", "content": "classify"}],
            task_type="ingest_summary",
            sensitivity="private",
        )
    assert result == "local ok"
