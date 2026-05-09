from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from second_brain.storage import Vault


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    import pygit2

    repo = pygit2.init_repository(str(tmp_path))
    sig = pygit2.Signature("Test", "t@t.com")
    tree = repo.TreeBuilder().write()
    repo.create_commit("refs/heads/main", sig, sig, "init", tree, [])
    (tmp_path / "wiki").mkdir(parents=True)
    return tmp_path


def test_task_graph_extracts_and_appends(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.task_graph import TaskGraph

    vault = Vault(tmp_vault)
    # Create tasks file
    tasks_file = tmp_vault / "wiki" / "tasks.md"
    tasks_file.parent.mkdir(parents=True, exist_ok=True)
    tasks_file.write_text("# Tasks\n\n- [ ] existing task\n", encoding="utf-8")

    mock_router = MagicMock()
    # extract_actionables response
    extract_resp = json.dumps({"tasks": ["- [ ] write monthly report @due(2026-06-01) #work"]})
    # classify_priority response (no-op here, same tasks back)
    priority_resp = json.dumps({"tasks": ["- [ ] write monthly report @due(2026-06-01) #work"]})
    mock_router.complete.side_effect = [extract_resp, priority_resp]
    mock_router.get_last_cost.return_value = 0.001

    graph = TaskGraph(vault=vault, router=mock_router)
    result = graph.run("Meeting notes: TODO: write monthly report by June 1.")

    content = tasks_file.read_text(encoding="utf-8")
    assert "write monthly report" in content
    assert result.new_tasks_count >= 1


def test_task_graph_deduplicates_existing(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.task_graph import TaskGraph

    vault = Vault(tmp_vault)
    tasks_file = tmp_vault / "wiki" / "tasks.md"
    tasks_file.parent.mkdir(parents=True, exist_ok=True)
    tasks_file.write_text("# Tasks\n\n- [ ] write monthly report\n", encoding="utf-8")

    mock_router = MagicMock()
    extract_resp = json.dumps({"tasks": ["- [ ] write monthly report @due(2026-06-01) #work"]})
    priority_resp = json.dumps({"tasks": []})  # deduped away
    mock_router.complete.side_effect = [extract_resp, priority_resp]
    mock_router.get_last_cost.return_value = 0.0

    graph = TaskGraph(vault=vault, router=mock_router)
    result = graph.run("TODO: write monthly report.")

    assert result.new_tasks_count == 0
