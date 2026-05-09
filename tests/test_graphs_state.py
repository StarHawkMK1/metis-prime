from __future__ import annotations

import operator


def test_ingest_state_instantiates() -> None:
    from second_brain.agents.graphs.state import IngestState

    state: IngestState = {
        "source_rel_path": "raw/inbox/note.md",
        "sensitivity": "normal",
        "raw_text": "",
        "similar_pages": [],
        "decision": "",
        "decision_data": {},
        "wiki_path": None,
        "archived_path": "",
        "validation_passed": True,
        "cost_usd": 0.0,
        "errors": [],
    }
    assert state["source_rel_path"] == "raw/inbox/note.md"


def test_lint_state_issues_uses_operator_add_reducer() -> None:
    from typing import get_args, get_type_hints

    from second_brain.agents.graphs.state import LintState

    hints = get_type_hints(LintState, include_extras=True)
    args = get_args(hints["issues"])
    assert args[1] is operator.add


def test_query_state_instantiates() -> None:
    from second_brain.agents.graphs.state import QueryState

    state: QueryState = {
        "question": "What is RAG?",
        "sensitivity": "normal",
        "intent": "",
        "context_parts": [],
        "sources": [],
        "answer": "",
        "archive": False,
        "cost_usd": 0.0,
    }
    assert state["question"] == "What is RAG?"


def test_task_state_instantiates() -> None:
    from second_brain.agents.graphs.state import TaskState

    state: TaskState = {
        "source_text": "TODO: finish report",
        "sensitivity": "normal",
        "actionables": [],
        "existing_tasks": [],
        "new_tasks": [],
        "tasks_file_path": "wiki/tasks.md",
        "cost_usd": 0.0,
    }
    assert state["source_text"] == "TODO: finish report"
