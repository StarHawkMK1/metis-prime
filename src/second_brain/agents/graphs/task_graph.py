from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog
from langgraph.graph import END, START, StateGraph

from ...llm.router import LLMRouter
from ...llm.types import Sensitivity
from ...storage.vault import Vault
from .state import TaskState

log = structlog.get_logger(__name__)

_EXTRACT_PROMPT = """\
Extract all actionable TODO items from the source text.
Use Obsidian Tasks format: - [ ] task description @due(YYYY-MM-DD) #context

Respond with ONLY JSON: {"tasks": ["- [ ] task1", "- [ ] task2"]}
If no actionable items, return {"tasks": []}.
"""

_PRIORITY_PROMPT = """\
You are given a list of new tasks and a list of existing tasks already tracked.
Remove any new tasks that are semantically identical to existing tasks (deduplication).
Return the remaining new tasks with priority/context tags added where appropriate.

Respond with ONLY JSON: {"tasks": ["- [ ] task with #priority"]}
"""


@dataclass
class TaskResult:
    new_tasks_count: int
    tasks_file_path: str
    cost_usd: float = 0.0


class TaskGraph:
    def __init__(
        self,
        vault: Vault,
        router: LLMRouter | None = None,
        sensitivity: Sensitivity = "normal",
    ) -> None:
        self._vault = vault
        self._router = router or LLMRouter()
        self._sensitivity = sensitivity
        self._compiled = self._build()

    def _build(self) -> Any:
        g = StateGraph(TaskState)
        g.add_node("extract_actionables", self._extract_actionables)
        g.add_node("dedupe_with_existing", self._dedupe_with_existing)
        g.add_node("append_to_tasks", self._append_to_tasks)

        g.add_edge(START, "extract_actionables")
        g.add_edge("extract_actionables", "dedupe_with_existing")
        g.add_edge("dedupe_with_existing", "append_to_tasks")
        g.add_edge("append_to_tasks", END)
        return g.compile()

    def run(self, source_text: str, sensitivity: Sensitivity | None = None) -> TaskResult:
        sens = sensitivity or self._sensitivity
        tasks_file = "wiki/tasks.md"
        initial: TaskState = {
            "source_text": source_text,
            "sensitivity": sens,
            "actionables": [],
            "existing_tasks": [],
            "new_tasks": [],
            "tasks_file_path": tasks_file,
            "cost_usd": 0.0,
        }
        final = self._compiled.invoke(initial)
        return TaskResult(
            new_tasks_count=len(final["new_tasks"]),
            tasks_file_path=final["tasks_file_path"],
            cost_usd=final.get("cost_usd", 0.0),
        )

    # ── nodes ─────────────────────────────────────────────────────────────────

    def _extract_actionables(self, state: TaskState) -> dict[str, Any]:
        raw = self._router.complete(
            [
                {"role": "system", "content": _EXTRACT_PROMPT},
                {"role": "user", "content": state["source_text"][:4000]},
            ],
            task_type="task_extract",
            sensitivity=state["sensitivity"],  # type: ignore[arg-type]
        )
        try:
            tasks = json.loads(raw.strip()).get("tasks", [])
        except (json.JSONDecodeError, AttributeError):
            tasks = []
        return {
            "actionables": tasks,
            "cost_usd": state["cost_usd"] + self._router.get_last_cost(),
        }

    def _dedupe_with_existing(self, state: TaskState) -> dict[str, Any]:
        tasks_path = self._vault.path / state["tasks_file_path"]
        existing: list[str] = []
        if tasks_path.exists():
            existing = [
                line.strip()
                for line in tasks_path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith("- [ ]") or line.strip().startswith("- [x]")
            ]

        if not state["actionables"]:
            return {"existing_tasks": existing, "new_tasks": []}

        user_msg = (
            "Existing tasks:\n" + "\n".join(existing[:50]) + "\n\n"
            "New tasks to deduplicate:\n" + "\n".join(state["actionables"])
        )
        raw = self._router.complete(
            [
                {"role": "system", "content": _PRIORITY_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            task_type="task_extract",
            sensitivity=state["sensitivity"],  # type: ignore[arg-type]
        )
        try:
            new_tasks = json.loads(raw.strip()).get("tasks", [])
        except (json.JSONDecodeError, AttributeError):
            new_tasks = state["actionables"]

        return {
            "existing_tasks": existing,
            "new_tasks": new_tasks,
            "cost_usd": state["cost_usd"] + self._router.get_last_cost(),
        }

    def _append_to_tasks(self, state: TaskState) -> dict[str, Any]:
        if not state["new_tasks"]:
            return {}
        tasks_path = self._vault.path / state["tasks_file_path"]
        tasks_path.parent.mkdir(parents=True, exist_ok=True)
        if not tasks_path.exists():
            tasks_path.write_text("# Tasks\n\n", encoding="utf-8")

        additions = "\n".join(state["new_tasks"]) + "\n"
        with tasks_path.open("a", encoding="utf-8") as f:
            f.write(additions)

        log.info("task_graph.appended", count=len(state["new_tasks"]))
        return {}
