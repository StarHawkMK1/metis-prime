# Phase 5: LangGraph Multi-Agent Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Metis Prime's IngestAgent, QueryAgent, and LintAgent into proper LangGraph `StateGraph` state machines, add a new TaskGraph for actionable extraction, and wire them into the CLI — enabling parallel lint scans, bidirectional cross-linking, file-system human-review routing, and per-graph LLM cost tracking.

**Architecture:** Four LangGraph graphs live in the new `src/second_brain/agents/graphs/` package alongside the existing agents (which are kept intact). Each graph is a `StateGraph[XState]` compiled with `.compile()` and exposed via a thin wrapper class with a `.run()` method. LintGraph uses LangGraph's `Send` API for parallel fan-out across 4 scan nodes. Human review uses a file-system queue (`human_review/pending/`). Cost is tracked via a new `pricing.py` module and the existing `MetricsRecorder`.

**Tech Stack:** `langgraph>=0.2`, `langchain-core>=0.3`, Python `TypedDict`, `Annotated` + `operator.add` reducers, `Send` for parallel dispatch, Windows Task Scheduler for lint cron.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `pyproject.toml` | Add langgraph, langchain-core |
| Modify | `src/second_brain/llm/types.py` | Add `task_extract`, `lint_contradiction` |
| Add | `src/second_brain/llm/pricing.py` | Per-model USD cost computation |
| Modify | `src/second_brain/llm/metrics.py` | Add `cost_usd` to `LLMCallMetrics` |
| Modify | `src/second_brain/llm/router.py` | Record `cost_usd`; add `get_last_cost()` |
| Add | `src/second_brain/agents/graphs/__init__.py` | Package init |
| Add | `src/second_brain/agents/graphs/state.py` | `IngestState`, `QueryState`, `LintState`, `TaskState` |
| Add | `src/second_brain/agents/graphs/ingest_graph.py` | `IngestGraph` with cross-link and human-review routing |
| Add | `src/second_brain/agents/graphs/query_graph.py` | `QueryGraph` with intent classification |
| Add | `src/second_brain/agents/graphs/lint_graph.py` | `LintGraph` with parallel `Send` fan-out |
| Add | `src/second_brain/agents/graphs/task_graph.py` | `TaskGraph` for actionable extraction |
| Add | `src/second_brain/agents/graphs/human_review.py` | File-system review queue helpers |
| Add | `src/second_brain/agents/graphs/cost_reporter.py` | Monthly cost report writer |
| Modify | `src/second_brain/cli.py` | Update ingest/query/lint; add `task extract`, `review process`, `cost report` |
| Add | `scripts/install-lint-cron.ps1` | Windows Task Scheduler for weekly lint |

---

## Task 1: Add Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add langgraph and langchain-core to pyproject.toml**

Replace the `dependencies` list in `pyproject.toml`:

```toml
[project]
name = "second-brain"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "python-frontmatter>=1.1",
    "pydantic>=2.7",
    "pydantic-settings>=2.4",
    "typer>=0.12",
    "rich>=13.7",
    "structlog>=24.1",
    "pygit2>=1.15",
    "openai>=1.50",
    "rank-bm25>=0.2",
    "graphifyy[mcp]>=0.7.10",
    "langgraph>=0.2",
    "langchain-core>=0.3",
]
```

- [ ] **Step 2: Install**

```
uv sync
```

Expected: resolves and installs langgraph + langchain-core, no errors.

- [ ] **Step 3: Verify imports**

```
python -c "from langgraph.graph import StateGraph, START, END; from langgraph.types import Send; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add langgraph and langchain-core dependencies"
```

---

## Task 2: Extend LLM Task Types

**Files:**
- Modify: `src/second_brain/llm/types.py`
- Test: `tests/test_llm_types.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_llm_types.py`:

```python
def test_task_type_includes_phase5_types() -> None:
    from typing import get_args
    from second_brain.llm.types import TaskType
    args = get_args(TaskType)
    assert "task_extract" in args
    assert "lint_contradiction" in args
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_llm_types.py::test_task_type_includes_phase5_types -v
```

Expected: FAIL — `AssertionError`

- [ ] **Step 3: Update types.py**

```python
from __future__ import annotations

from typing import Literal

TaskType = Literal[
    "ingest_summary",
    "synthesis_complex",
    "vision",
    "lint_check",
    "graph_traversal",
    "task_extract",
    "lint_contradiction",
]
Sensitivity = Literal["normal", "private"]
```

- [ ] **Step 4: Run all llm_types tests**

```
pytest tests/test_llm_types.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/second_brain/llm/types.py tests/test_llm_types.py
git commit -m "feat: add task_extract and lint_contradiction task types"
```

---

## Task 3: Cost Tracking Infrastructure

**Files:**
- Create: `src/second_brain/llm/pricing.py`
- Modify: `src/second_brain/llm/metrics.py`
- Modify: `src/second_brain/llm/router.py`
- Test: `tests/test_pricing.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pricing.py`:

```python
from __future__ import annotations
import pytest


def test_compute_cost_haiku() -> None:
    from second_brain.llm.pricing import compute_cost
    # $0.25/M input + $1.25/M output = $1.50 for 1M + 1M tokens
    cost = compute_cost("claude-3-haiku-20240307", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == pytest.approx(1.50)


def test_compute_cost_unknown_model_returns_zero() -> None:
    from second_brain.llm.pricing import compute_cost
    assert compute_cost("unknown-xyz", prompt_tokens=9999, completion_tokens=9999) == 0.0


def test_compute_cost_local_model_is_zero() -> None:
    from second_brain.llm.pricing import compute_cost
    assert compute_cost("qwen3:30b-a3b", prompt_tokens=50_000, completion_tokens=10_000) == 0.0


def test_llm_call_metrics_has_cost_usd() -> None:
    from second_brain.llm.metrics import LLMCallMetrics
    m = LLMCallMetrics(
        task_type="ingest_summary",
        sensitivity="normal",
        model="claude-3-haiku-20240307",
        latency_ms=42.0,
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.0000875,
    )
    assert m.cost_usd == pytest.approx(0.0000875)


def test_router_get_last_cost_returns_zero_when_no_calls() -> None:
    from unittest.mock import MagicMock, patch
    from second_brain.llm.router import LLMRouter
    from second_brain.config import Settings
    settings = MagicMock(spec=Settings)
    settings.litellm_base_url = "http://localhost:4000"
    settings.litellm_master_key = None
    settings.local_only = False
    with patch("second_brain.llm.router.OpenAI"):
        router = LLMRouter(settings=settings)
    assert router.get_last_cost() == 0.0


def test_metrics_recorder_persists_to_jsonl(tmp_path: Path) -> None:
    from second_brain.llm.metrics import LLMCallMetrics, MetricsRecorder
    log_path = tmp_path / "metrics" / "2026-05.jsonl"
    recorder = MetricsRecorder(log_path=log_path)
    recorder.record(LLMCallMetrics(
        task_type="ingest_summary", sensitivity="normal", model="claude-3-haiku-20240307",
        latency_ms=50.0, prompt_tokens=100, completion_tokens=50, cost_usd=0.0001,
    ))
    assert log_path.exists()
    loaded = MetricsRecorder.from_jsonl(log_path)
    assert len(loaded.all()) == 1
    assert loaded.all()[0].cost_usd == pytest.approx(0.0001)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_pricing.py -v
```

Expected: FAIL — `ModuleNotFoundError` and `TypeError`

- [ ] **Step 3: Create pricing.py**

Create `src/second_brain/llm/pricing.py`:

```python
from __future__ import annotations

# (input_usd_per_1m_tokens, output_usd_per_1m_tokens)
PRICING: dict[str, tuple[float, float]] = {
    "claude-3-haiku-20240307": (0.25, 1.25),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (0.80, 4.00),
    # Local models — zero marginal cost
    "qwen3:30b-a3b": (0.0, 0.0),
    "qwen3:8b": (0.0, 0.0),
}


def compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return USD cost for one LLM call. Returns 0.0 for unknown or local models."""
    if model not in PRICING:
        return 0.0
    in_rate, out_rate = PRICING[model]
    return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000
```

- [ ] **Step 4: Add cost_usd to LLMCallMetrics and JSONL persistence to MetricsRecorder**

Replace `src/second_brain/llm/metrics.py`:

```python
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
    def from_jsonl(cls, log_path: Path) -> "MetricsRecorder":
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
```

- [ ] **Step 5: Update router.py to compute cost and expose get_last_cost()**

In `src/second_brain/llm/router.py`, add import at top (after existing imports):

```python
from .pricing import compute_cost
```

In the `finally` block (lines 94–103), replace the `LLMCallMetrics(...)` call with:

```python
            self._recorder.record(
                LLMCallMetrics(
                    task_type=task_type,
                    sensitivity=sensitivity,
                    model=model,
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=compute_cost(model, prompt_tokens, completion_tokens),
                    error=error,
                )
            )
```

Add this method to the `LLMRouter` class (after `complete`):

```python
    def get_last_cost(self) -> float:
        """Return the cost_usd of the most recent LLM call, or 0.0 if none."""
        records = self._recorder.all()
        return records[-1].cost_usd if records else 0.0
```

- [ ] **Step 5b: Wire persistent recorder into each graph class**

Each graph (`IngestGraph`, `QueryGraph`, `LintGraph`, `TaskGraph`) already accepts a `router` argument. The CLI commands that call these graphs should pass a router configured with the JSONL-writing recorder. Add a helper to make this easy.

Add `_make_router` to `src/second_brain/agents/graphs/ingest_graph.py` (repeat for each graph file):

```python
from pathlib import Path
from datetime import date
from ...llm.metrics import MetricsRecorder

def _make_router(vault_path: Path) -> LLMRouter:
    month_str = date.today().strftime("%Y-%m")
    log_path = vault_path / "journal" / ".metrics" / f"{month_str}.jsonl"
    recorder = MetricsRecorder(log_path=log_path)
    return LLMRouter(recorder=recorder)
```

In each graph's `__init__`, change the fallback from `LLMRouter()` to use this helper only when no router is provided. Since graphs are also used in tests with mock routers, this change is safe:

```python
# In IngestGraph.__init__ (and similarly in QueryGraph, LintGraph, TaskGraph):
self._router = router or _make_router(vault.path)
```

This ensures every LLM call from CLI commands is logged to the JSONL file. Tests are unaffected because they always pass a `mock_router`.

- [ ] **Step 6: Run all cost-related tests**

```
pytest tests/test_pricing.py tests/test_llm_metrics.py tests/test_llm_router.py -v
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/second_brain/llm/pricing.py src/second_brain/llm/metrics.py src/second_brain/llm/router.py tests/test_pricing.py
git commit -m "feat: add per-model cost tracking to LLM router with JSONL persistence"
```

---

## Task 4: Shared State Types

**Files:**
- Create: `src/second_brain/agents/graphs/__init__.py`
- Create: `src/second_brain/agents/graphs/state.py`
- Test: `tests/test_graphs_state.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_graphs_state.py`:

```python
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
    from second_brain.agents.graphs.state import LintState
    from typing import get_type_hints, get_args
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_graphs_state.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create package init**

Create `src/second_brain/agents/graphs/__init__.py` (empty file).

- [ ] **Step 4: Create state.py**

Create `src/second_brain/agents/graphs/state.py`:

```python
from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict


class IngestState(TypedDict):
    source_rel_path: str
    sensitivity: str
    raw_text: str
    similar_pages: list[dict]
    decision: str          # "create" | "merge" | "skip"
    decision_data: dict    # parsed LLM response fields
    wiki_path: str | None
    archived_path: str
    validation_passed: bool
    cost_usd: float
    errors: list[str]


class QueryState(TypedDict):
    question: str
    sensitivity: str
    intent: str            # "factual" | "synthesis" | "task_command"
    context_parts: list[str]
    sources: list[str]
    answer: str
    archive: bool
    cost_usd: float


class LintState(TypedDict):
    issues: Annotated[list[dict], operator.add]
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
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_graphs_state.py -v
```

Expected: all 4 PASS

- [ ] **Step 6: Commit**

```bash
git add src/second_brain/agents/graphs/__init__.py src/second_brain/agents/graphs/state.py tests/test_graphs_state.py
git commit -m "feat: add shared LangGraph state types (IngestState, QueryState, LintState, TaskState)"
```

---

## Task 5: IngestGraph

**Files:**
- Create: `src/second_brain/agents/graphs/ingest_graph.py`
- Test: `tests/test_ingest_graph.py`

Wraps existing IngestAgent helpers in LangGraph nodes. Adds two new capabilities: bidirectional cross-linking after write, and validation-failure routing to `human_review/pending/`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_ingest_graph.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pygit2
import pytest

from second_brain.storage import Vault, WikiPage


def _llm_response(
    decision: str = "create",
    title: str = "Test Concept",
    page_type: str = "concept",
    body: str = "A one-sentence definition.",
    target_page: str = "",
    inferred: int = 20,
) -> str:
    extracted = 100 - inferred - 5
    return json.dumps({
        "decision": decision,
        "title": title,
        "type": page_type,
        "body": body,
        "provenance": {"extracted": extracted, "inferred": inferred, "ambiguous": 5},
        "wikilinks": [],
        "tags": [],
        "target_page": target_page,
    })


def _stage(vault_path: Path, rel: str) -> None:
    repo = pygit2.Repository(str(vault_path))
    idx = repo.index
    idx.read()
    idx.add(rel)
    idx.write()
    sig = pygit2.Signature("Test", "t@t.com")
    tree = idx.write_tree()
    repo.create_commit("refs/heads/main", sig, sig, f"add {rel}", tree, [repo.head.target])


def test_ingest_graph_creates_page(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.ingest_graph import IngestGraph

    source = tmp_vault / "raw" / "inbox" / "note.md"
    source.write_text("# Note\n\nContent.", encoding="utf-8")
    _stage(tmp_vault, "raw/inbox/note.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _llm_response()
    mock_router.get_last_cost.return_value = 0.001

    vault = Vault(tmp_vault)
    result = IngestGraph(vault=vault, router=mock_router).run("raw/inbox/note.md")

    assert result.decision == "create"
    assert result.wiki_path is not None
    assert vault.page_exists(result.wiki_path)


def test_ingest_graph_archives_source(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.ingest_graph import IngestGraph

    source = tmp_vault / "raw" / "inbox" / "clip.md"
    source.write_text("# Clip\n\nContent.", encoding="utf-8")
    _stage(tmp_vault, "raw/inbox/clip.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _llm_response(title="Clip")
    mock_router.get_last_cost.return_value = 0.0

    vault = Vault(tmp_vault)
    result = IngestGraph(vault=vault, router=mock_router).run("raw/inbox/clip.md")

    assert not source.exists()
    assert result.archived_path.exists()


def test_ingest_graph_routes_high_inferred_to_review(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.ingest_graph import IngestGraph

    source = tmp_vault / "raw" / "inbox" / "risky.md"
    source.write_text("# Risky\n\nSpeculative content.", encoding="utf-8")
    _stage(tmp_vault, "raw/inbox/risky.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _llm_response(inferred=80)
    mock_router.get_last_cost.return_value = 0.0

    vault = Vault(tmp_vault)
    result = IngestGraph(vault=vault, router=mock_router).run("raw/inbox/risky.md")

    review_dir = tmp_vault / "human_review" / "pending"
    assert result.wiki_path is None
    assert not vault.page_exists("wiki/concepts/risky.md")
    assert review_dir.exists() and any(review_dir.iterdir())


def test_ingest_graph_skip_no_wiki_page(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.ingest_graph import IngestGraph

    source = tmp_vault / "raw" / "inbox" / "dup.md"
    source.write_text("# Dup\n\nDuplicate.", encoding="utf-8")
    _stage(tmp_vault, "raw/inbox/dup.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _llm_response(decision="skip")
    mock_router.get_last_cost.return_value = 0.0

    vault = Vault(tmp_vault)
    result = IngestGraph(vault=vault, router=mock_router).run("raw/inbox/dup.md")

    assert result.decision == "skip"
    assert result.wiki_path is None
    assert result.archived_path.exists()


def test_ingest_graph_cross_links_referenced_page(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.ingest_graph import IngestGraph

    # Create a target page that the new page will link to
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/existing-topic.md",
        WikiPage(title="Existing Topic", type="concept", body="Existing content."),
    )

    source = tmp_vault / "raw" / "inbox" / "new.md"
    source.write_text("# New\n\nRefs existing.", encoding="utf-8")
    _stage(tmp_vault, "raw/inbox/new.md")

    response = json.dumps({
        "decision": "create",
        "title": "New Topic",
        "type": "concept",
        "body": "Links to existing.",
        "provenance": {"extracted": 75, "inferred": 20, "ambiguous": 5},
        "wikilinks": ["existing-topic"],
        "tags": [],
        "target_page": "",
    })
    mock_router = MagicMock()
    mock_router.complete.return_value = response
    mock_router.get_last_cost.return_value = 0.0

    IngestGraph(vault=vault, router=mock_router).run("raw/inbox/new.md")

    existing_content = vault.read_raw_text("wiki/concepts/existing-topic.md")
    assert "[[new-topic]]" in existing_content
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_ingest_graph.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create ingest_graph.py**

Create `src/second_brain/agents/graphs/ingest_graph.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import structlog
from langgraph.graph import END, START, StateGraph

from ..extractors import extract_text
from ..ingest import (
    IngestError,
    _IngestDecision,
    _body_with_related,
    _default_wiki_path,
    _parse_decision,
    _resolve_merge_target,
)
from ..search import WikiSearcher
from ...llm.router import LLMRouter
from ...llm.types import Sensitivity
from ...storage.frontmatter import WikiPage
from ...storage.vault import Vault
from .state import IngestState

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a wiki maintainer for a personal second brain knowledge base.
Analyze the incoming source material and decide how to incorporate it into the wiki.

Respond with ONLY a JSON object:

{
  "decision": "create" | "merge" | "skip",
  "title": "Title Case Title",
  "type": "concept" | "project" | "person" | "place" | "ref" | "map",
  "body": "Markdown body (no frontmatter). First line = one-sentence definition.",
  "provenance": {"extracted": <0-100>, "inferred": <0-100>, "ambiguous": <0-100>},
  "wikilinks": ["stem-of-page-1"],
  "tags": ["tag1"],
  "target_page": "stem-of-existing-page-to-merge-into"
}

Rules: "create" if new topic; "merge" if very similar page exists (set target_page);
"skip" if source adds nothing new. provenance must sum to 100. Return ONLY JSON.
"""


@dataclass
class IngestResult:
    decision: str
    wiki_path: str | None
    archived_path: Path
    source_name: str
    cost_usd: float = 0.0


class IngestGraph:
    def __init__(
        self,
        vault: Vault,
        router: LLMRouter | None = None,
        sensitivity: Sensitivity = "normal",
    ) -> None:
        self._vault = vault
        self._router = router or LLMRouter()
        self._sensitivity = sensitivity
        self._searcher = WikiSearcher(vault)
        self._compiled = self._build()

    def _build(self):  # type: ignore[return]
        g = StateGraph(IngestState)
        g.add_node("extract", self._extract)
        g.add_node("search_similar", self._search_similar)
        g.add_node("decide", self._decide)
        g.add_node("validate", self._validate)
        g.add_node("generate_page", self._generate_page)
        g.add_node("merge_into_existing", self._merge_into_existing)
        g.add_node("skip_node", self._skip_node)
        g.add_node("cross_link", self._cross_link)
        g.add_node("commit_node", self._commit_node)
        g.add_node("queue_human_review", self._queue_human_review)

        g.add_edge(START, "extract")
        g.add_edge("extract", "search_similar")
        g.add_edge("search_similar", "decide")
        g.add_edge("decide", "validate")
        # validate runs BEFORE writing — routes to review if inferred > 70%
        g.add_conditional_edges(
            "validate",
            lambda s: s["decision"] if s["validation_passed"] else "queue_human_review",
            {"create": "generate_page", "merge": "merge_into_existing", "skip": "skip_node", "queue_human_review": "queue_human_review"},
        )
        g.add_edge("generate_page", "cross_link")
        g.add_edge("merge_into_existing", "cross_link")
        g.add_edge("cross_link", "commit_node")
        g.add_edge("skip_node", "commit_node")
        g.add_edge("commit_node", END)
        g.add_edge("queue_human_review", END)
        return g.compile()

    def run(self, source_rel_path: str, sensitivity: Sensitivity | None = None) -> IngestResult:
        sens = sensitivity or self._sensitivity
        initial: IngestState = {
            "source_rel_path": source_rel_path,
            "sensitivity": sens,
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
        final = self._compiled.invoke(initial)
        return IngestResult(
            decision=final["decision"],
            wiki_path=final.get("wiki_path"),
            archived_path=Path(final["archived_path"]) if final["archived_path"] else Path(""),
            source_name=Path(source_rel_path).name,
            cost_usd=final.get("cost_usd", 0.0),
        )

    # ── nodes ─────────────────────────────────────────────────────────────────

    def _extract(self, state: IngestState) -> dict:
        source_path = self._vault.path / state["source_rel_path"]
        return {"raw_text": extract_text(source_path)}

    def _search_similar(self, state: IngestState) -> dict:
        results = self._searcher.search(state["raw_text"][:2000], top_k=3)
        return {
            "similar_pages": [
                {"stem": r.path.stem, "score": r.score, "content": r.content[:400]}
                for r in results
            ]
        }

    def _decide(self, state: IngestState) -> dict:
        source_path = self._vault.path / state["source_rel_path"]
        similar = state["similar_pages"]
        user_msg = (
            f"Source file: {source_path.name}\n\nSource text:\n---\n{state['raw_text'][:3000]}\n---\n\n"
        )
        if similar:
            parts = [f"[[{p['stem']}]] (score: {p['score']:.2f})\n{p['content']}" for p in similar]
            user_msg += f"Existing similar pages ({len(similar)} found):\n\n" + "\n\n---\n\n".join(parts) + "\n\n"
        else:
            user_msg += "Existing similar pages: none\n\n"
        user_msg += "Make your decision."

        raw = self._router.complete(
            [{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": user_msg}],
            task_type="ingest_summary",
            sensitivity=state["sensitivity"],
        )
        dec = _parse_decision(raw)
        return {
            "decision": dec.decision,
            "decision_data": dec.model_dump(),
            "cost_usd": state["cost_usd"] + self._router.get_last_cost(),
        }

    def _generate_page(self, state: IngestState) -> dict:
        dec = _IngestDecision.model_validate(state["decision_data"])
        wiki_path = _default_wiki_path(dec.title)
        self._vault.write_page(
            wiki_path,
            WikiPage(
                title=dec.title,
                type=dec.type,
                body=_body_with_related(dec.body, dec.wikilinks),
                tags=dec.tags,
                sources=[state["source_rel_path"]],
                provenance=dec.provenance,
            ),
        )
        log.info("ingest_graph.created", page=wiki_path)
        return {"wiki_path": wiki_path}

    def _merge_into_existing(self, state: IngestState) -> dict:
        dec = _IngestDecision.model_validate(state["decision_data"])
        wiki_path = _resolve_merge_target(dec.target_page, self._vault)
        if wiki_path:
            existing = self._vault.read_page(wiki_path)
            merged_sources = list(dict.fromkeys(existing.sources + [state["source_rel_path"]]))
            self._vault.write_page(
                wiki_path,
                existing.model_copy(update={
                    "body": _body_with_related(dec.body, dec.wikilinks),
                    "sources": merged_sources,
                }),
            )
            log.info("ingest_graph.merged", page=wiki_path)
        else:
            wiki_path = _default_wiki_path(dec.title)
            self._vault.write_page(
                wiki_path,
                WikiPage(
                    title=dec.title,
                    type=dec.type,
                    body=_body_with_related(dec.body, dec.wikilinks),
                    tags=dec.tags,
                    sources=[state["source_rel_path"]],
                    provenance=dec.provenance,
                ),
            )
            log.info("ingest_graph.merge_fallback_created", page=wiki_path)
        return {"wiki_path": wiki_path}

    def _skip_node(self, state: IngestState) -> dict:
        log.info("ingest_graph.skipped", source=state["source_rel_path"])
        return {}

    def _cross_link(self, state: IngestState) -> dict:
        """Append backlink to each page referenced by the new/updated page."""
        wiki_path = state.get("wiki_path")
        if not wiki_path:
            return {}
        wikilinks: list[str] = state.get("decision_data", {}).get("wikilinks", [])
        new_stem = Path(wiki_path).stem
        for stem in wikilinks:
            target_path = _resolve_merge_target(stem, self._vault)
            if not target_path:
                continue
            try:
                page = self._vault.read_page(target_path)
                if f"[[{new_stem}]]" not in page.body:
                    self._vault.write_page(
                        target_path,
                        page.model_copy(update={"body": page.body.rstrip() + f"\n\n[[{new_stem}]]"}),
                    )
            except Exception:
                continue
        return {}

    def _validate(self, state: IngestState) -> dict:
        if state["decision"] == "skip":
            return {"validation_passed": True}
        inferred = state.get("decision_data", {}).get("provenance", {}).get("inferred", 0)
        return {"validation_passed": inferred <= 70}

    def _commit_node(self, state: IngestState) -> dict:
        source_rel = state["source_rel_path"]
        source_path = self._vault.path / source_rel
        try:
            archived = self._vault.archive_raw(
                source_rel,
                commit_message=f"ingest: {state['decision']} {source_path.name}",
            )
            return {"archived_path": str(archived)}
        except FileExistsError as exc:
            raise IngestError(f"Cannot archive {source_rel}: {exc}") from exc

    def _queue_human_review(self, state: IngestState) -> dict:
        """Write draft to human_review/pending/ and archive raw source."""
        review_dir = self._vault.path / "human_review" / "pending"
        review_dir.mkdir(parents=True, exist_ok=True)

        data = state.get("decision_data", {})
        title = data.get("title", "unknown")
        import re
        stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "unknown"
        draft_path = review_dir / f"{stem}.md"
        draft_path.write_text(
            f"# Review Required: {title}\n\n"
            f"**Reason:** inferred provenance > 70%\n\n"
            f"**Source:** {state['source_rel_path']}\n\n"
            f"{data.get('body', '')}",
            encoding="utf-8",
        )
        log.info("ingest_graph.queued_for_review", stem=stem)

        source_rel = state["source_rel_path"]
        source_path = self._vault.path / source_rel
        try:
            archived = self._vault.archive_raw(
                source_rel,
                commit_message=f"ingest: pending-review {source_path.name}",
            )
            return {"wiki_path": None, "archived_path": str(archived)}
        except FileExistsError:
            return {"wiki_path": None, "archived_path": ""}
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_ingest_graph.py -v
```

Expected: all 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/second_brain/agents/graphs/ingest_graph.py tests/test_ingest_graph.py
git commit -m "feat: add IngestGraph with cross-linking and human-review routing"
```

---

## Task 6: QueryGraph

**Files:**
- Create: `src/second_brain/agents/graphs/query_graph.py`
- Test: `tests/test_query_graph.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_query_graph.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from second_brain.storage import Vault, WikiPage


def test_query_graph_returns_answer(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.query_graph import QueryGraph

    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/rag.md",
        WikiPage(title="RAG", type="concept", body="Retrieval Augmented Generation is a technique."),
    )

    mock_router = MagicMock()
    # First call: classify intent → "factual"
    # Second call: answer
    mock_router.complete.side_effect = ['{"intent": "factual"}', "RAG stands for Retrieval Augmented Generation."]
    mock_router.get_last_cost.return_value = 0.001

    graph = QueryGraph(vault=vault, router=mock_router)
    result = graph.ask("What is RAG?")

    assert "RAG" in result.answer or len(result.answer) > 0


def test_query_graph_synthesis_intent(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.query_graph import QueryGraph

    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/ml.md",
        WikiPage(title="ML", type="concept", body="Machine learning uses data."),
    )

    mock_router = MagicMock()
    mock_router.complete.side_effect = ['{"intent": "synthesis"}', "Synthesis answer here."]
    mock_router.get_last_cost.return_value = 0.002

    graph = QueryGraph(vault=vault, router=mock_router)
    result = graph.ask("Explain how ML and AI relate?")

    assert len(result.answer) > 0


def test_query_graph_no_context_still_answers(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.query_graph import QueryGraph

    vault = Vault(tmp_vault)
    mock_router = MagicMock()
    mock_router.complete.side_effect = ['{"intent": "factual"}', "I don't have relevant pages."]
    mock_router.get_last_cost.return_value = 0.0

    graph = QueryGraph(vault=vault, router=mock_router)
    result = graph.ask("What is the capital of France?")

    assert len(result.answer) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_query_graph.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create query_graph.py**

Create `src/second_brain/agents/graphs/query_graph.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from langgraph.graph import END, START, StateGraph

from ..search import WikiSearcher
from ...graph.query import GraphQuery
from ...llm.router import LLMRouter
from ...llm.types import Sensitivity
from ...storage.vault import Vault
from .state import QueryState

log = structlog.get_logger(__name__)

_CLASSIFY_PROMPT = """\
Classify the user's question into one of three intents.

Respond with ONLY a JSON object:
{"intent": "factual" | "synthesis" | "task_command"}

- "factual": single specific fact or definition
- "synthesis": requires combining multiple sources or explaining relationships
- "task_command": action request (extract tasks, remind me, schedule something)
"""

_ANSWER_PROMPT = """\
You are a knowledgeable assistant with access to the user's personal wiki.
Answer concisely, citing wiki pages with [[page-stem]] inline citations.
If no wiki pages are relevant, say so clearly.
"""


@dataclass
class QueryResult:
    answer: str
    sources: list[str] = field(default_factory=list)
    cost_usd: float = 0.0


class QueryGraph:
    def __init__(
        self,
        vault: Vault,
        router: LLMRouter | None = None,
        top_k: int = 5,
        sensitivity: Sensitivity = "normal",
        graph_depth: int = 2,
    ) -> None:
        self._vault = vault
        self._router = router or LLMRouter()
        self._top_k = top_k
        self._sensitivity = sensitivity
        self._searcher = WikiSearcher(vault)
        self._graph_query = GraphQuery(vault.path / "graph" / "graphify-out" / "graph.json")
        self._compiled = self._build()

    def _build(self):  # type: ignore[return]
        g = StateGraph(QueryState)
        g.add_node("classify_intent", self._classify_intent)
        g.add_node("graph_lookup", self._graph_lookup)
        g.add_node("multi_page_fetch", self._multi_page_fetch)
        g.add_node("answer", self._answer)
        g.add_node("record", self._record)

        g.add_edge(START, "classify_intent")
        g.add_conditional_edges(
            "classify_intent",
            lambda s: s["intent"] if s["intent"] in ("factual", "synthesis") else "factual",
            {"factual": "graph_lookup", "synthesis": "multi_page_fetch"},
        )
        g.add_edge("graph_lookup", "answer")
        g.add_edge("multi_page_fetch", "answer")
        g.add_edge("answer", "record")
        g.add_edge("record", END)
        return g.compile()

    def ask(self, question: str, sensitivity: Sensitivity | None = None, archive: bool = False) -> QueryResult:
        sens = sensitivity or self._sensitivity
        initial: QueryState = {
            "question": question,
            "sensitivity": sens,
            "intent": "",
            "context_parts": [],
            "sources": [],
            "answer": "",
            "archive": archive,
            "cost_usd": 0.0,
        }
        final = self._compiled.invoke(initial)
        return QueryResult(
            answer=final["answer"],
            sources=final["sources"],
            cost_usd=final.get("cost_usd", 0.0),
        )

    # ── nodes ─────────────────────────────────────────────────────────────────

    def _classify_intent(self, state: QueryState) -> dict:
        raw = self._router.complete(
            [
                {"role": "system", "content": _CLASSIFY_PROMPT},
                {"role": "user", "content": state["question"]},
            ],
            task_type="synthesis_complex",
            sensitivity=state["sensitivity"],
        )
        try:
            intent = json.loads(raw.strip()).get("intent", "factual")
        except (json.JSONDecodeError, AttributeError):
            intent = "factual"
        return {
            "intent": intent,
            "cost_usd": state["cost_usd"] + self._router.get_last_cost(),
        }

    def _graph_lookup(self, state: QueryState) -> dict:
        """Graph-first retrieval, BM25 fallback."""
        try:
            graph_ctx = self._graph_query.search_and_expand(state["question"], depth=2)
        except Exception:
            graph_ctx = None

        if graph_ctx and graph_ctx.nodes:
            parts: list[str] = []
            sources: list[str] = []
            seen: set[str] = set()
            for node in graph_ctx.nodes:
                if not node.source_file or node.source_file in seen:
                    continue
                seen.add(node.source_file)
                if self._vault.page_exists(node.source_file):
                    try:
                        content = self._vault.read_raw_text(node.source_file)
                        stem = Path(node.source_file).stem
                        parts.append(f"[[{stem}]] (graph: {node.label})\n{content[:800]}")
                        sources.append(node.source_file)
                    except OSError:
                        continue
            if parts:
                return {"context_parts": parts, "sources": sources}

        # BM25 fallback
        results = self._searcher.search(state["question"], top_k=self._top_k)
        return {
            "context_parts": [
                f"[[{r.path.stem}]] (relevance: {r.score:.2f})\n{r.content[:800]}" for r in results
            ],
            "sources": [r.relative_path for r in results],
        }

    def _multi_page_fetch(self, state: QueryState) -> dict:
        """Broader BM25 retrieval for synthesis questions."""
        results = self._searcher.search(state["question"], top_k=self._top_k)
        return {
            "context_parts": [
                f"[[{r.path.stem}]] (relevance: {r.score:.2f})\n{r.content[:1200]}" for r in results
            ],
            "sources": [r.relative_path for r in results],
        }

    def _answer(self, state: QueryState) -> dict:
        context = state["context_parts"]
        if context:
            user_msg = (
                f"Question: {state['question']}\n\nRelevant wiki pages:\n\n"
                + "\n\n---\n\n".join(context)
            )
        else:
            user_msg = f"Question: {state['question']}\n\nWiki context: none"

        answer = self._router.complete(
            [{"role": "system", "content": _ANSWER_PROMPT}, {"role": "user", "content": user_msg}],
            task_type="synthesis_complex",
            sensitivity=state["sensitivity"],
        )
        return {
            "answer": answer,
            "cost_usd": state["cost_usd"] + self._router.get_last_cost(),
        }

    def _record(self, state: QueryState) -> dict:
        """Append Q&A to journal/queries.md."""
        journal_dir = self._vault.path / "journal"
        journal_dir.mkdir(parents=True, exist_ok=True)
        queries_file = journal_dir / "queries.md"
        from datetime import date
        entry = (
            f"\n## {date.today()} — {state['question'][:80]}\n\n"
            f"{state['answer']}\n\n"
            f"*Sources: {', '.join(f'[[{s}]]' for s in state['sources']) or 'none'}*\n"
        )
        with queries_file.open("a", encoding="utf-8") as f:
            f.write(entry)
        log.info("query_graph.recorded", question=state["question"][:80])
        return {}
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_query_graph.py -v
```

Expected: all 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/second_brain/agents/graphs/query_graph.py tests/test_query_graph.py
git commit -m "feat: add QueryGraph with intent classification and graph-first retrieval"
```

---

## Task 7: LintGraph (Parallel Fan-out)

**Files:**
- Create: `src/second_brain/agents/graphs/lint_graph.py`
- Test: `tests/test_lint_graph.py`

The LintGraph uses LangGraph's `Send` API to dispatch 4 scan nodes in parallel. Their `issues` outputs merge automatically via the `operator.add` reducer defined in `LintState`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_lint_graph.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from second_brain.storage import Vault, WikiPage


def test_lint_graph_detects_broken_wikilink(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.lint_graph import LintGraph

    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/note.md",
        WikiPage(title="Note", type="concept", body="See [[nonexistent-page]] for details."),
    )

    mock_router = MagicMock()
    mock_router.complete.return_value = '{"contradictions": []}'
    mock_router.get_last_cost.return_value = 0.0

    graph = LintGraph(vault=vault, router=mock_router)
    report = graph.run()

    kinds = {i.kind for i in report.issues}
    assert "broken_wikilink" in kinds


def test_lint_graph_detects_orphan(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.lint_graph import LintGraph

    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/lonely.md",
        WikiPage(title="Lonely Page", type="concept", body="No links here."),
    )

    mock_router = MagicMock()
    mock_router.complete.return_value = '{"contradictions": []}'
    mock_router.get_last_cost.return_value = 0.0

    graph = LintGraph(vault=vault, router=mock_router)
    report = graph.run()

    kinds = {i.kind for i in report.issues}
    assert "orphan" in kinds


def test_lint_graph_detects_stale_draft(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.lint_graph import LintGraph
    from datetime import date, timedelta
    from second_brain.storage.frontmatter import WikiPage

    vault = Vault(tmp_vault)
    old_date = date.today() - timedelta(days=40)
    page = WikiPage(
        title="Old Draft",
        type="concept",
        body="Some content.",
        status="draft",
        updated=old_date,
    )
    vault.write_page("wiki/concepts/old-draft.md", page)

    mock_router = MagicMock()
    mock_router.complete.return_value = '{"contradictions": []}'
    mock_router.get_last_cost.return_value = 0.0

    graph = LintGraph(vault=vault, router=mock_router)
    report = graph.run()

    kinds = {i.kind for i in report.issues}
    assert "stale_draft" in kinds


def test_lint_graph_writes_report_file(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.lint_graph import LintGraph

    vault = Vault(tmp_vault)
    mock_router = MagicMock()
    mock_router.complete.return_value = '{"contradictions": []}'
    mock_router.get_last_cost.return_value = 0.0

    graph = LintGraph(vault=vault, router=mock_router)
    report = graph.run()

    from datetime import date
    report_path = tmp_vault / "journal" / f"lint-{date.today()}.md"
    assert report_path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_lint_graph.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create lint_graph.py**

Create `src/second_brain/agents/graphs/lint_graph.py`:

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ..lint import LintIssue, LintReport, _extract_wikilinks, _stems
from ..search import WikiSearcher
from ...llm.router import LLMRouter
from ...llm.types import Sensitivity
from ...storage.frontmatter import WikiPage
from ...storage.vault import Vault
from .state import LintState

log = structlog.get_logger(__name__)

_STALE_DAYS = 30
_MAX_CONTRADICTION_PAIRS = 3

_CONTRADICTION_PROMPT = """\
Compare these two wiki pages and identify any contradictory claims.
Respond with ONLY JSON: {"contradictions": [{"detail": "description of contradiction"}]}
If no contradictions, return {"contradictions": []}.
"""


class LintGraph:
    def __init__(self, vault: Vault, router: LLMRouter | None = None) -> None:
        self._vault = vault
        self._router = router or LLMRouter()
        self._searcher = WikiSearcher(vault)
        self._compiled = self._build()

    def _build(self):  # type: ignore[return]
        g = StateGraph(LintState)
        g.add_node("scan_links", self._scan_links)
        g.add_node("scan_orphans", self._scan_orphans)
        g.add_node("scan_provenance", self._scan_provenance)
        g.add_node("scan_contradictions", self._scan_contradictions)
        g.add_node("aggregate", self._aggregate)
        g.add_node("report", self._report)

        g.add_conditional_edges(
            START,
            self._dispatch,
            ["scan_links", "scan_orphans", "scan_provenance", "scan_contradictions"],
        )
        g.add_edge("scan_links", "aggregate")
        g.add_edge("scan_orphans", "aggregate")
        g.add_edge("scan_provenance", "aggregate")
        g.add_edge("scan_contradictions", "aggregate")
        g.add_edge("aggregate", "report")
        g.add_edge("report", END)
        return g.compile()

    def run(self) -> LintReport:
        initial: LintState = {"issues": [], "report_path": "", "cost_usd": 0.0}
        final = self._compiled.invoke(initial)
        report = LintReport(
            issues=[LintIssue(**i) for i in final["issues"]],
        )
        log.info("lint_graph.complete", issues=len(report.issues))
        return report

    # ── dispatch ──────────────────────────────────────────────────────────────

    def _dispatch(self, state: LintState) -> list[Send]:
        return [
            Send("scan_links", state),
            Send("scan_orphans", state),
            Send("scan_provenance", state),
            Send("scan_contradictions", state),
        ]

    # ── scan nodes ────────────────────────────────────────────────────────────

    def _scan_links(self, state: LintState) -> dict:
        issues: list[dict] = []
        stem_map = _stems(self._vault)
        for page_path in self._vault.list_pages():
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            try:
                content = page_path.read_text(encoding="utf-8")
            except OSError:
                continue
            for stem in _extract_wikilinks(content):
                if stem not in stem_map:
                    issues.append({"kind": "broken_wikilink", "page": rel, "detail": f"[[{stem}]] has no matching page"})
        return {"issues": issues}

    def _scan_orphans(self, state: LintState) -> dict:
        issues: list[dict] = []
        pages = self._vault.list_pages()
        referenced_stems: set[str] = set()
        page_outlinks: dict[str, list[str]] = {}

        for page_path in pages:
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            try:
                content = page_path.read_text(encoding="utf-8")
            except OSError:
                page_outlinks[rel] = []
                continue
            links = _extract_wikilinks(content)
            page_outlinks[rel] = links
            for stem in links:
                referenced_stems.add(stem)

        for page_path in pages:
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            stem = page_path.stem
            if not page_outlinks.get(rel) and stem not in referenced_stems:
                issues.append({"kind": "orphan", "page": rel, "detail": "no incoming or outgoing wikilinks"})
        return {"issues": issues}

    def _scan_provenance(self, state: LintState) -> dict:
        issues: list[dict] = []
        for page_path in self._vault.list_pages():
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            try:
                content = page_path.read_text(encoding="utf-8")
                page_obj = WikiPage.from_markdown(content)
            except Exception:
                continue

            if page_obj.status == "draft" and (date.today() - page_obj.updated) > timedelta(days=_STALE_DAYS):
                issues.append({
                    "kind": "stale_draft",
                    "page": rel,
                    "detail": f"draft since {page_obj.updated} ({(date.today() - page_obj.updated).days}d ago)",
                })
            if page_obj.provenance.inferred > 70:
                issues.append({
                    "kind": "provenance_drift",
                    "page": rel,
                    "detail": f"inferred={page_obj.provenance.inferred}% (>70%, possible hallucination)",
                })
        return {"issues": issues}

    def _scan_contradictions(self, state: LintState) -> dict:
        """LLM-based contradiction detection across similar page pairs."""
        issues: list[dict] = []
        pages = self._vault.list_pages()
        if len(pages) < 2:
            return {"issues": issues, "cost_usd": 0.0}

        checked: set[frozenset[str]] = set()
        pairs_checked = 0
        total_cost = 0.0

        for page_path in pages:
            if pairs_checked >= _MAX_CONTRADICTION_PAIRS:
                break
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            try:
                content_a = page_path.read_text(encoding="utf-8")
            except OSError:
                continue

            results = self._searcher.search(content_a[:1000], top_k=2)
            for result in results:
                pair_key = frozenset([rel, result.relative_path])
                if pair_key in checked or result.relative_path == rel:
                    continue
                checked.add(pair_key)
                pairs_checked += 1

                try:
                    content_b = self._vault.read_raw_text(result.relative_path)
                    user_msg = (
                        f"Page A ({page_path.stem}):\n{content_a[:600]}\n\n"
                        f"Page B ({result.path.stem}):\n{content_b[:600]}"
                    )
                    raw = self._router.complete(
                        [
                            {"role": "system", "content": _CONTRADICTION_PROMPT},
                            {"role": "user", "content": user_msg},
                        ],
                        task_type="lint_contradiction",
                        sensitivity="normal",
                    )
                    total_cost += self._router.get_last_cost()
                    data = json.loads(raw.strip())
                    for c in data.get("contradictions", []):
                        issues.append({
                            "kind": "contradiction",
                            "page": rel,
                            "detail": f"vs [[{result.path.stem}]]: {c.get('detail', '')}",
                        })
                except Exception:
                    continue

        return {"issues": issues, "cost_usd": total_cost}

    def _aggregate(self, state: LintState) -> dict:
        return {}

    def _report(self, state: LintState) -> dict:
        report = LintReport(issues=[LintIssue(**i) for i in state["issues"]])
        journal_dir = self._vault.path / "journal"
        journal_dir.mkdir(parents=True, exist_ok=True)
        filename = f"lint-{report.generated}.md"
        report_path = journal_dir / filename
        report_path.write_text(report.to_markdown(), encoding="utf-8")
        return {"report_path": str(report_path)}
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_lint_graph.py -v
```

Expected: all 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/second_brain/agents/graphs/lint_graph.py tests/test_lint_graph.py
git commit -m "feat: add LintGraph with parallel Send fan-out and contradiction detection"
```

---

## Task 8: TaskGraph

**Files:**
- Create: `src/second_brain/agents/graphs/task_graph.py`
- Test: `tests/test_task_graph.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_task_graph.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from second_brain.storage import Vault


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
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_task_graph.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create task_graph.py**

Create `src/second_brain/agents/graphs/task_graph.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

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

    def _build(self):  # type: ignore[return]
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

    def _extract_actionables(self, state: TaskState) -> dict:
        raw = self._router.complete(
            [
                {"role": "system", "content": _EXTRACT_PROMPT},
                {"role": "user", "content": state["source_text"][:4000]},
            ],
            task_type="task_extract",
            sensitivity=state["sensitivity"],
        )
        try:
            tasks = json.loads(raw.strip()).get("tasks", [])
        except (json.JSONDecodeError, AttributeError):
            tasks = []
        return {
            "actionables": tasks,
            "cost_usd": state["cost_usd"] + self._router.get_last_cost(),
        }

    def _dedupe_with_existing(self, state: TaskState) -> dict:
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
            f"Existing tasks:\n" + "\n".join(existing[:50]) + "\n\n"
            f"New tasks to deduplicate:\n" + "\n".join(state["actionables"])
        )
        raw = self._router.complete(
            [
                {"role": "system", "content": _PRIORITY_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            task_type="task_extract",
            sensitivity=state["sensitivity"],
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

    def _append_to_tasks(self, state: TaskState) -> dict:
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_task_graph.py -v
```

Expected: all 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/second_brain/agents/graphs/task_graph.py tests/test_task_graph.py
git commit -m "feat: add TaskGraph for actionable extraction with deduplication"
```

---

## Task 9: Human Review Helpers + CLI Command

**Files:**
- Create: `src/second_brain/agents/graphs/human_review.py`
- Modify: `src/second_brain/cli.py`
- Test: `tests/test_human_review.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_human_review.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from second_brain.storage import Vault, WikiPage


def test_process_review_moves_accepted_to_wiki(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.human_review import process_review

    vault = Vault(tmp_vault)
    pending = tmp_vault / "human_review" / "pending"
    accepted = tmp_vault / "human_review" / "accepted"
    pending.mkdir(parents=True)
    accepted.mkdir(parents=True)

    # Write a draft page to accepted/
    (accepted / "my-concept.md").write_text(
        "# Review Required: My Concept\n\n**Reason:** inferred provenance > 70%\n\n"
        "**Source:** raw/inbox/source.md\n\nSome body content.",
        encoding="utf-8",
    )

    result = process_review(vault)
    assert result.accepted == 1
    assert result.rejected == 0
    assert not (accepted / "my-concept.md").exists()
    # File moved to wiki
    wiki_page = tmp_vault / "wiki" / "concepts" / "my-concept.md"
    assert wiki_page.exists()


def test_process_review_deletes_rejected(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.human_review import process_review

    vault = Vault(tmp_vault)
    rejected = tmp_vault / "human_review" / "rejected"
    rejected.mkdir(parents=True)
    (rejected / "bad-page.md").write_text("# Bad\n\nContent.", encoding="utf-8")

    result = process_review(vault)
    assert result.rejected == 1
    assert not (rejected / "bad-page.md").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_human_review.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create human_review.py**

Create `src/second_brain/agents/graphs/human_review.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

import structlog

from ...storage.vault import Vault

log = structlog.get_logger(__name__)


@dataclass
class ReviewResult:
    accepted: int = 0
    rejected: int = 0


def process_review(vault: Vault) -> ReviewResult:
    """
    Scan human_review/accepted/ and human_review/rejected/.
    - accepted/: move markdown files to wiki/concepts/
    - rejected/: delete markdown files
    """
    result = ReviewResult()
    review_base = vault.path / "human_review"

    accepted_dir = review_base / "accepted"
    if accepted_dir.exists():
        for md_file in accepted_dir.glob("*.md"):
            dest = vault.path / "wiki" / "concepts" / md_file.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(md_file), str(dest))
            result.accepted += 1
            log.info("human_review.accepted", file=md_file.name)

    rejected_dir = review_base / "rejected"
    if rejected_dir.exists():
        for md_file in rejected_dir.glob("*.md"):
            md_file.unlink()
            result.rejected += 1
            log.info("human_review.rejected", file=md_file.name)

    return result
```

- [ ] **Step 4: Add `review process` CLI command**

In `src/second_brain/cli.py`, add after the existing command groups (find the `app = typer.Typer(...)` line and add):

```python
review_app = typer.Typer(help="Human-in-the-loop review queue commands.")
app.add_typer(review_app, name="review")


@review_app.command("process")
def review_process() -> None:
    """Process human_review/accepted/ and human_review/rejected/ queues."""
    from .agents.graphs.human_review import process_review
    from .storage.vault import Vault
    from .config import Settings

    settings = Settings()
    vault = Vault(settings.vault_path)
    result = process_review(vault)
    typer.echo(f"Processed: {result.accepted} accepted, {result.rejected} rejected.")
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_human_review.py -v
```

Expected: all 2 PASS

- [ ] **Step 6: Smoke test CLI command exists**

```
second-brain review --help
```

Expected: shows `process` subcommand.

- [ ] **Step 7: Commit**

```bash
git add src/second_brain/agents/graphs/human_review.py tests/test_human_review.py src/second_brain/cli.py
git commit -m "feat: add human review queue processor and review process CLI command"
```

---

## Task 10: Cost Reporter + CLI Command

**Files:**
- Create: `src/second_brain/agents/graphs/cost_reporter.py`
- Modify: `src/second_brain/cli.py`
- Test: `tests/test_cost_reporter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cost_reporter.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from second_brain.storage import Vault


def test_cost_reporter_writes_monthly_report(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.cost_reporter import CostReporter
    from second_brain.llm.metrics import LLMCallMetrics, MetricsRecorder

    recorder = MetricsRecorder()
    recorder.record(LLMCallMetrics(
        task_type="ingest_summary", sensitivity="normal", model="claude-3-haiku-20240307",
        latency_ms=100.0, prompt_tokens=500, completion_tokens=200, cost_usd=0.00038,
    ))
    recorder.record(LLMCallMetrics(
        task_type="synthesis_complex", sensitivity="normal", model="claude-3-5-sonnet-20241022",
        latency_ms=800.0, prompt_tokens=1000, completion_tokens=400, cost_usd=0.009,
    ))

    vault = Vault(tmp_vault)
    reporter = CostReporter(vault=vault, recorder=recorder)
    report_path = reporter.write_monthly_report()

    content = report_path.read_text(encoding="utf-8")
    assert "cost" in content.lower() or "$" in content
    assert "claude" in content.lower()


def test_cost_reporter_totals_are_accurate(tmp_vault: Path) -> None:
    from second_brain.agents.graphs.cost_reporter import CostReporter
    from second_brain.llm.metrics import LLMCallMetrics, MetricsRecorder

    recorder = MetricsRecorder()
    recorder.record(LLMCallMetrics(
        task_type="ingest_summary", sensitivity="normal", model="claude-3-haiku-20240307",
        latency_ms=100.0, prompt_tokens=500, completion_tokens=200, cost_usd=0.00038,
    ))

    vault = Vault(tmp_vault)
    reporter = CostReporter(vault=vault, recorder=recorder)
    report_path = reporter.write_monthly_report()
    content = report_path.read_text(encoding="utf-8")

    assert "0.00038" in content or "0.000" in content
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_cost_reporter.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create cost_reporter.py**

Create `src/second_brain/agents/graphs/cost_reporter.py`:

```python
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

import structlog

from ...llm.metrics import LLMCallMetrics, MetricsRecorder
from ...storage.vault import Vault

log = structlog.get_logger(__name__)


class CostReporter:
    def __init__(self, vault: Vault, recorder: MetricsRecorder) -> None:
        self._vault = vault
        self._recorder = recorder

    def write_monthly_report(self, month: date | None = None) -> Path:
        """Write journal/cost-YYYY-MM.md and return the path."""
        target = month or date.today()
        month_str = target.strftime("%Y-%m")

        records = [
            r for r in self._recorder.all()
            if r.timestamp.strftime("%Y-%m") == month_str and r.error is None
        ]

        total_cost = sum(r.cost_usd for r in records)
        total_calls = len(records)
        by_model: dict[str, float] = defaultdict(float)
        by_task: dict[str, float] = defaultdict(float)
        for r in records:
            by_model[r.model] += r.cost_usd
            by_task[r.task_type] += r.cost_usd

        lines = [
            f"# LLM Cost Report — {month_str}",
            "",
            f"**Total calls:** {total_calls}",
            f"**Total cost:** ${total_cost:.6f} USD",
            "",
            "## By Model",
            "",
        ]
        for model, cost in sorted(by_model.items(), key=lambda x: -x[1]):
            lines.append(f"- `{model}`: ${cost:.6f}")
        lines += ["", "## By Task Type", ""]
        for task, cost in sorted(by_task.items(), key=lambda x: -x[1]):
            lines.append(f"- `{task}`: ${cost:.6f}")
        lines.append("")

        journal_dir = self._vault.path / "journal"
        journal_dir.mkdir(parents=True, exist_ok=True)
        report_path = journal_dir / f"cost-{month_str}.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        log.info("cost_reporter.wrote", path=str(report_path), total_cost=total_cost)
        return report_path
```

- [ ] **Step 4: Add `cost report` CLI command**

In `src/second_brain/cli.py`, add after the review_app block:

```python
cost_app = typer.Typer(help="LLM cost tracking commands.")
app.add_typer(cost_app, name="cost")


@cost_app.command("report")
def cost_report() -> None:
    """Write the monthly LLM cost report to journal/cost-YYYY-MM.md."""
    from .agents.graphs.cost_reporter import CostReporter
    from .llm.metrics import MetricsRecorder
    from .storage.vault import Vault
    from .config import Settings
    from datetime import date

    settings = Settings()
    vault = Vault(settings.vault_path)
    month_str = date.today().strftime("%Y-%m")
    log_path = vault.path / "journal" / ".metrics" / f"{month_str}.jsonl"
    recorder = MetricsRecorder.from_jsonl(log_path)
    reporter = CostReporter(vault=vault, recorder=recorder)
    path = reporter.write_monthly_report()
    typer.echo(f"Cost report written to: {path}")
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_cost_reporter.py -v
```

Expected: all 2 PASS

- [ ] **Step 6: Commit**

```bash
git add src/second_brain/agents/graphs/cost_reporter.py tests/test_cost_reporter.py src/second_brain/cli.py
git commit -m "feat: add monthly LLM cost reporter and cost report CLI command"
```

---

## Task 11: CLI Wiring — Update Ingest/Query/Lint + Add Task Extract

**Files:**
- Modify: `src/second_brain/cli.py`
- Test: `tests/test_agents_cli.py` (add new assertions)

Update the existing `ingest`, `query`, and `lint` CLI commands to delegate to the new LangGraph wrappers. Add `task extract` command.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_agents_cli.py`:

```python
def test_task_extract_command_exists(tmp_vault: Path, monkeypatch) -> None:
    from typer.testing import CliRunner
    from second_brain.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["task", "--help"])
    assert result.exit_code == 0
    assert "extract" in result.output


def test_ingest_command_uses_ingest_graph(tmp_vault: Path, monkeypatch) -> None:
    """ingest command should invoke IngestGraph.run(), not IngestAgent.run()."""
    import json
    from typer.testing import CliRunner
    from second_brain.cli import app
    from unittest.mock import patch, MagicMock

    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_vault))

    source = tmp_vault / "raw" / "inbox" / "test.md"
    source.write_text("# Test\n\nContent.", encoding="utf-8")

    mock_result = MagicMock()
    mock_result.decision = "create"
    mock_result.wiki_path = "wiki/concepts/test.md"

    runner = CliRunner()
    with patch("second_brain.agents.graphs.ingest_graph.IngestGraph.run", return_value=mock_result):
        result = runner.invoke(app, ["ingest", "raw/inbox/test.md"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_agents_cli.py::test_task_extract_command_exists tests/test_agents_cli.py::test_ingest_command_uses_ingest_graph -v
```

Expected: FAIL

- [ ] **Step 3: Add task app and update ingest/query/lint in cli.py**

In `src/second_brain/cli.py`, add the `task_app` Typer group:

```python
task_app = typer.Typer(help="Task extraction commands.")
app.add_typer(task_app, name="task")


@task_app.command("extract")
def task_extract(
    source: str = typer.Argument(..., help="Text to extract tasks from, or path to a file."),
    sensitivity: str = typer.Option("normal", help="Sensitivity level (normal/private)."),
) -> None:
    """Extract actionable tasks from text or a file."""
    from .agents.graphs.task_graph import TaskGraph
    from .storage.vault import Vault
    from .config import Settings

    settings = Settings()
    vault = Vault(settings.vault_path)
    source_path = Path(source)
    if source_path.exists():
        text = source_path.read_text(encoding="utf-8")
    else:
        text = source

    graph = TaskGraph(vault=vault)
    result = graph.run(text, sensitivity=sensitivity)
    typer.echo(f"Extracted {result.new_tasks_count} new tasks → {result.tasks_file_path}")
```

Find the existing `ingest` command in `cli.py` and update its body to use `IngestGraph`:

```python
@app.command()
def ingest(
    source: str = typer.Argument(..., help="Vault-relative path to raw source file."),
    sensitivity: str = typer.Option("normal", help="Sensitivity level (normal/private)."),
) -> None:
    """Ingest a raw source file into the wiki using the LangGraph pipeline."""
    from .agents.graphs.ingest_graph import IngestGraph
    from .storage.vault import Vault
    from .config import Settings

    settings = Settings()
    vault = Vault(settings.vault_path)
    graph = IngestGraph(vault=vault, sensitivity=sensitivity)
    result = graph.run(source)
    typer.echo(f"[{result.decision}] {result.wiki_path or '(skipped)'}")
```

Find the existing `query` command and update to use `QueryGraph`:

```python
@app.command()
def query(
    question: str = typer.Argument(..., help="Natural language question to answer."),
    sensitivity: str = typer.Option("normal", help="Sensitivity level."),
    archive: bool = typer.Option(False, "--archive", help="Save answer as a new wiki page."),
) -> None:
    """Answer a question using the knowledge graph and wiki."""
    from .agents.graphs.query_graph import QueryGraph
    from .storage.vault import Vault
    from .config import Settings

    settings = Settings()
    vault = Vault(settings.vault_path)
    graph = QueryGraph(vault=vault, sensitivity=sensitivity)
    result = graph.ask(question, archive=archive)
    typer.echo(result.answer)
    if result.sources:
        typer.echo(f"\nSources: {', '.join(result.sources)}")
```

Find the existing `lint` command and update to use `LintGraph`:

```python
@app.command()
def lint() -> None:
    """Run vault lint checks (parallel) and write journal/lint-YYYY-MM-DD.md."""
    from .agents.graphs.lint_graph import LintGraph
    from .storage.vault import Vault
    from .config import Settings

    settings = Settings()
    vault = Vault(settings.vault_path)
    graph = LintGraph(vault=vault)
    report = graph.run()
    typer.echo(f"Lint complete: {len(report.issues)} issues found.")
    if report.issues:
        from collections import Counter
        counts = Counter(i.kind for i in report.issues)
        for kind, count in sorted(counts.items()):
            typer.echo(f"  {kind}: {count}")
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_agents_cli.py -v
```

Expected: all PASS (including new ones)

- [ ] **Step 5: Run full test suite to verify no regressions**

```
pytest -v
```

Expected: all existing tests PASS. New tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/second_brain/cli.py tests/test_agents_cli.py
git commit -m "feat: wire ingest/query/lint CLI to LangGraph graphs; add task extract command"
```

---

## Task 12: Windows Task Scheduler for Weekly Lint Cron

**Files:**
- Create: `scripts/install-lint-cron.ps1`

- [ ] **Step 1: Create the PowerShell install script**

Create `scripts/install-lint-cron.ps1`:

```powershell
# install-lint-cron.ps1
# Registers a Windows Task Scheduler job to run 'second-brain lint' every Sunday at 08:00.
# Run once as Administrator: powershell -ExecutionPolicy Bypass -File scripts\install-lint-cron.ps1

param(
    [string]$VaultPath = $env:SECOND_BRAIN_VAULT_PATH,
    [string]$PythonExe = (Get-Command uv -ErrorAction SilentlyContinue).Source
)

if (-not $VaultPath) {
    Write-Error "Set SECOND_BRAIN_VAULT_PATH environment variable or pass -VaultPath."
    exit 1
}

if (-not $PythonExe) {
    Write-Error "uv not found in PATH. Install uv first."
    exit 1
}

$TaskName = "MetisPrime-WeeklyLint"
$ProjectDir = Split-Path -Parent $PSScriptRoot

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "run second-brain lint" `
    -WorkingDirectory $ProjectDir

$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "08:00"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

$Env = [System.Environment]
$EnvVars = @{
    SECOND_BRAIN_VAULT_PATH = $VaultPath
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -RunLevel Highest `
    -Force | Out-Null

# Set environment variable for the task
$Task = Get-ScheduledTask -TaskName $TaskName
$Task.Principal.RunLevel = "Highest"
Set-ScheduledTask -InputObject $Task | Out-Null

Write-Host "Scheduled task '$TaskName' registered successfully."
Write-Host "Runs every Sunday at 08:00 in: $ProjectDir"
Write-Host ""
Write-Host "To run immediately:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "To remove:           Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
```

- [ ] **Step 2: Verify script syntax**

```
powershell -NoProfile -NonInteractive -Command "Get-Content scripts\install-lint-cron.ps1 | Select-String 'Register-ScheduledTask'"
```

Expected: shows the `Register-ScheduledTask` line.

- [ ] **Step 3: Commit**

```bash
git add scripts/install-lint-cron.ps1
git commit -m "feat: add Windows Task Scheduler script for weekly lint cron"
```

---

## Acceptance Criteria Verification

After all tasks complete, verify each Phase 5 acceptance criterion:

- [ ] **4 graphs work with LangGraph**
  ```
  python -c "
  from second_brain.agents.graphs.ingest_graph import IngestGraph
  from second_brain.agents.graphs.query_graph import QueryGraph
  from second_brain.agents.graphs.lint_graph import LintGraph
  from second_brain.agents.graphs.task_graph import TaskGraph
  print('All 4 graph classes import successfully')
  "
  ```

- [ ] **Full test suite passes**
  ```
  pytest -v --tb=short
  ```
  Expected: 0 failures.

- [ ] **CLI commands available**
  ```
  second-brain --help
  ```
  Expected: shows `ingest`, `query`, `lint`, `task`, `review`, `cost` commands.

- [ ] **Task extract works end-to-end**
  ```
  second-brain task extract "TODO: review the PR by Friday. Also need to update the docs."
  ```
  Expected: `Extracted N new tasks → wiki/tasks.md`

- [ ] **Lint cron script registered (Windows)**
  ```
  powershell -ExecutionPolicy Bypass -File scripts\install-lint-cron.ps1
  Get-ScheduledTask -TaskName "MetisPrime-WeeklyLint"
  ```
  Expected: task shows as `Ready`.

---

*Self-review: spec coverage checked. IngestGraph covers Tasks 2+6 (classify→extract→dedupe→cross_link→validate→commit/human_review). QueryGraph covers Task 3 (classify_intent→lookup→answer→record). LintGraph covers Task 4 (parallel: scan_links, scan_orphans, scan_provenance, scan_contradictions→aggregate→report). TaskGraph covers Task 5 (extract→dedupe→append). Common infra (Task 6) covered by human_review.py, cost_reporter.py, pricing.py, and Windows scheduler script. All acceptance criteria mapped.*
