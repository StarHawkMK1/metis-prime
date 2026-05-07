from __future__ import annotations

from .errors import PrivacyViolationError
from .types import Sensitivity, TaskType

LOCAL_MODELS: frozenset[str] = frozenset({"local-fast"})

_POLICY: dict[str, str] = {
    "ingest_summary": "bulk",
    "synthesis_complex": "smart-cloud",
    "vision": "vision-cheap",
    "lint_check": "bulk",
}


def select_model(task_type: TaskType, sensitivity: Sensitivity) -> str:
    if sensitivity == "private":
        return "local-fast"
    return _POLICY[task_type]


def assert_local_or_raise(model: str, sensitivity: Sensitivity) -> None:
    if sensitivity == "private" and model not in LOCAL_MODELS:
        raise PrivacyViolationError(
            f"privacy violation: '{model}' is not local but sensitivity=private"
        )
