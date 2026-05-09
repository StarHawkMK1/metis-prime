from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict


class IngestState(TypedDict):
    source_rel_path: str
    sensitivity: str
    raw_text: str
    similar_pages: list[dict[str, object]]
    decision: str  # "create" | "merge" | "skip"
    decision_data: dict[str, object]  # parsed LLM response fields
    wiki_path: str | None
    archived_path: str
    validation_passed: bool
    cost_usd: float
    errors: list[str]


class QueryState(TypedDict):
    question: str
    sensitivity: str
    intent: str  # "factual" | "synthesis" | "task_command"
    context_parts: list[str]
    sources: list[str]
    answer: str
    archive: bool
    cost_usd: float


class LintState(TypedDict):
    issues: Annotated[list[dict[str, object]], operator.add]
    report_path: str
    cost_usd: Annotated[float, operator.add]


class TaskState(TypedDict):
    source_text: str
    sensitivity: str
    actionables: list[str]
    existing_tasks: list[str]
    new_tasks: list[str]
    tasks_file_path: str
    cost_usd: float
