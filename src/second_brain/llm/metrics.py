from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class LLMCallMetrics(BaseModel):
    task_type: str
    sensitivity: str
    model: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.now)
    error: str | None = None


class MetricsRecorder:
    def __init__(self, log_path: Path | None = None) -> None:
        self._records: list[LLMCallMetrics] = []
        self._log_path = log_path

    def record(self, metrics: LLMCallMetrics) -> None:
        self._records.append(metrics)
        if self._log_path:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(metrics.model_dump_json() + "\n")

    def all(self) -> list[LLMCallMetrics]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()

    @classmethod
    def from_jsonl(cls, log_path: Path) -> MetricsRecorder:
        """Load records from a JSONL log file into a new in-memory recorder."""
        recorder = cls()
        if not log_path.exists():
            return recorder
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    recorder._records.append(LLMCallMetrics.model_validate_json(line))
                except Exception:
                    continue
        return recorder
