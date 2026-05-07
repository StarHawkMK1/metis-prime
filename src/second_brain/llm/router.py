from __future__ import annotations

import time
from collections.abc import MutableMapping
from typing import Any

import structlog
from openai import OpenAI

from ..config import Settings
from .errors import RouterError
from .metrics import LLMCallMetrics, MetricsRecorder
from .policy import LOCAL_MODELS, assert_local_or_raise, select_model
from .types import Sensitivity, TaskType

log = structlog.get_logger(__name__)

_REDACT_KEYS = frozenset({"api_key", "master_key", "Authorization"})


def _redact_processor(
    logger: Any, method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in _REDACT_KEYS:
        if key in event_dict:
            event_dict[key] = "***"
    return event_dict


structlog.configure(
    processors=[
        _redact_processor,
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)


class LLMRouter:
    def __init__(
        self,
        settings: Settings | None = None,
        metrics_recorder: MetricsRecorder | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self._recorder = metrics_recorder or MetricsRecorder()
        master_key = (
            self._settings.litellm_master_key.get_secret_value()
            if self._settings.litellm_master_key
            else "sk-no-key"
        )
        self._client = OpenAI(
            base_url=str(self._settings.litellm_base_url),
            api_key=master_key,
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        task_type: TaskType,
        sensitivity: Sensitivity,
        **kwargs: Any,
    ) -> str:
        model = select_model(task_type, sensitivity)
        assert_local_or_raise(model, sensitivity)

        if self._settings.local_only and model not in LOCAL_MODELS:
            raise RouterError(
                f"local_only=True but policy selected cloud model '{model}' for {task_type!r}"
            )

        t0 = time.monotonic()
        error: str | None = None
        prompt_tokens = 0
        completion_tokens = 0

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                **kwargs,
            )
            content = response.choices[0].message.content or ""
            if response.usage:
                prompt_tokens = response.usage.prompt_tokens
                completion_tokens = response.usage.completion_tokens
            return content
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            latency_ms = (time.monotonic() - t0) * 1000
            self._recorder.record(
                LLMCallMetrics(
                    task_type=task_type,
                    sensitivity=sensitivity,
                    model=model,
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error=error,
                )
            )
            log.info(
                "llm.complete",
                task_type=task_type,
                sensitivity=sensitivity,
                model=model,
                latency_ms=round(latency_ms, 1),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                error=error,
            )
