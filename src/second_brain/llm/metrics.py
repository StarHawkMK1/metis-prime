from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LLMCallMetrics:
    task_type: str
    sensitivity: str
    model: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    timestamp: datetime = field(default_factory=datetime.now)
    error: str | None = None


class MetricsRecorder:
    def __init__(self) -> None:
        self._records: list[LLMCallMetrics] = []

    def record(self, metrics: LLMCallMetrics) -> None:
        self._records.append(metrics)

    def all(self) -> list[LLMCallMetrics]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()
