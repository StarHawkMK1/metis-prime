from typing import get_args

from second_brain.llm import PrivacyViolationError, RouterError, Sensitivity, TaskType


def test_task_type_literals() -> None:
    args = get_args(TaskType)
    assert set(args) == {
        "ingest_summary",
        "synthesis_complex",
        "vision",
        "lint_check",
        "graph_traversal",
        "task_extract",
        "lint_contradiction",
    }


def test_sensitivity_literals() -> None:
    args = get_args(Sensitivity)
    assert set(args) == {"normal", "private"}


def test_privacy_violation_is_router_error() -> None:
    exc = PrivacyViolationError("test")
    assert isinstance(exc, RouterError)


def test_router_error_message() -> None:
    exc = RouterError("something went wrong")
    assert "something went wrong" in str(exc)


def test_graph_traversal_is_valid_task_type() -> None:
    import typing

    from second_brain.llm.types import TaskType

    args = typing.get_args(TaskType)
    assert "graph_traversal" in args
