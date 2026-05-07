from __future__ import annotations

from itertools import product
from typing import get_args

import pytest

from second_brain.llm.errors import PrivacyViolationError
from second_brain.llm.policy import LOCAL_MODELS, assert_local_or_raise, select_model
from second_brain.llm.types import Sensitivity, TaskType

# ── Unit tests ────────────────────────────────────────────────────────────────


def test_ingest_summary_normal_routes_to_bulk() -> None:
    assert select_model("ingest_summary", "normal") == "bulk"


def test_synthesis_complex_normal_routes_to_smart_cloud() -> None:
    assert select_model("synthesis_complex", "normal") == "smart-cloud"


def test_vision_normal_routes_to_vision_cheap() -> None:
    assert select_model("vision", "normal") == "vision-cheap"


def test_lint_check_normal_routes_to_bulk() -> None:
    assert select_model("lint_check", "normal") == "bulk"


def test_private_always_overrides_to_local_fast() -> None:
    for task_type in get_args(TaskType):
        result = select_model(task_type, "private")  # type: ignore[arg-type]
        assert result == "local-fast", f"{task_type} + private should → local-fast, got {result}"


def test_assert_local_or_raise_passes_for_local_model() -> None:
    assert_local_or_raise("local-fast", "private")  # must not raise


def test_assert_local_or_raise_raises_for_cloud_model_with_private() -> None:
    with pytest.raises(PrivacyViolationError, match="privacy violation"):
        assert_local_or_raise("smart-cloud", "private")


def test_assert_local_or_raise_passes_cloud_model_for_normal() -> None:
    assert_local_or_raise("smart-cloud", "normal")  # must not raise


# ── PERMANENT PROPERTY TEST — DO NOT REMOVE ──────────────────────────────────
# This test iterates the full Cartesian product of (TaskType × Sensitivity) and
# ensures that the privacy invariant is never violated, regardless of future
# changes to the routing policy table.


@pytest.mark.parametrize(
    "task_type,sensitivity",
    list(product(get_args(TaskType), get_args(Sensitivity))),
)
def test_private_sensitivity_always_selects_local_model(task_type: str, sensitivity: str) -> None:
    """PERMANENT: private sensitivity must always route to a local model."""
    model = select_model(task_type, sensitivity)  # type: ignore[arg-type]
    if sensitivity == "private":
        assert model in LOCAL_MODELS, (
            f"PRIVACY VIOLATION: {task_type!r} + private → {model!r} (not in LOCAL_MODELS)"
        )
