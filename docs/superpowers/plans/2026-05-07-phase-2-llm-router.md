# Phase 2: LLM Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a unified `LLMRouter` that routes LLM calls to 4 providers (vLLM/Qwen3 local, Claude, GPT, Gemini) via a LiteLLM proxy, with two-layer privacy enforcement that guarantees `sensitivity=private` calls never reach cloud APIs.

**Architecture:** Python `LLMRouter` (sync) calls `openai.OpenAI(base_url=litellm_proxy)` using the OpenAI SDK as the sole wire protocol. A `policy.select_model(task_type, sensitivity)` function picks the logical model name (`local-fast` / `smart-cloud` / `vision-cheap` / `bulk`), followed by a defense-in-depth `assert_local_or_raise` guard. LiteLLM proxy (port 4000) translates logical model names to provider-specific API calls; vLLM (port 8000) serves Qwen3 with an OpenAI-compatible endpoint. All unit tests mock `openai.OpenAI().chat.completions.create` — no live keys required for CI.

**Tech Stack:** `openai>=1.50` (SDK), `litellm[proxy]>=1.50` (optional `[proxy]` extra), `structlog>=24.1` (routing telemetry), `pytest-mock>=3.14` (test fixtures), Docker Compose (local dev infra)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `configs/litellm_config.yaml` | Create | LiteLLM proxy model definitions and fallback chains |
| `infra/start_vllm.sh` | Create | vLLM startup script (Qwen3 AWQ, port 8000) |
| `infra/start_litellm.sh` | Create | LiteLLM proxy startup script (port 4000) |
| `infra/docker-compose.yml` | Create | Docker Compose for vLLM + LiteLLM (local dev) |
| `src/second_brain/llm/__init__.py` | Create | Package public exports |
| `src/second_brain/llm/types.py` | Create | `TaskType`, `Sensitivity` `Literal` type aliases |
| `src/second_brain/llm/errors.py` | Create | `RouterError`, `PrivacyViolationError` |
| `src/second_brain/llm/policy.py` | Create | `select_model`, `assert_local_or_raise`, `LOCAL_MODELS` |
| `src/second_brain/llm/metrics.py` | Create | `LLMCallMetrics` (pydantic), `MetricsRecorder` |
| `src/second_brain/llm/router.py` | Create | `LLMRouter` client (openai SDK + policy + metrics + structlog) |
| `src/second_brain/config.py` | Modify | Add `litellm_base_url`, `litellm_master_key` fields |
| `src/second_brain/cli.py` | Modify | Add `llm_app` subcommand (`llm test`, `llm route`); update `_ROUTING_POLICY_MD` |
| `pyproject.toml` | Modify | Add `openai>=1.50` to core; new `[proxy]` extra; `pytest-mock` to dev |
| `.env.example` | Modify | Add LiteLLM and provider API key entries |
| `tests/test_llm_policy.py` | Create | Routing policy tests + permanent privacy property test |
| `tests/test_llm_router.py` | Create | `LLMRouter.complete()` tests (mocked openai SDK) |
| `tests/test_llm_cli.py` | Create | `llm route` and `llm test` CLI command tests |

---

## Task 1: Infra Scripts and Docker Compose

**Files:**
- Create: `configs/litellm_config.yaml`
- Create: `infra/start_vllm.sh`
- Create: `infra/start_litellm.sh`
- Create: `infra/docker-compose.yml`

These are infrastructure files — no unit tests. Manual verification via `curl` is described in the smoke test section (Task 9).

- [ ] **Step 1: Create `configs/litellm_config.yaml`**

```yaml
model_list:
  # Local model — forced for privacy=private
  - model_name: local-fast
    litellm_params:
      model: openai/qwen3-local
      api_base: http://localhost:8000/v1
      api_key: dummy
      max_tokens: 4096

  # Complex synthesis — highest quality
  - model_name: smart-cloud
    litellm_params:
      model: anthropic/claude-opus-4-7
      # Uses ANTHROPIC_API_KEY env var automatically

  # Multimodal (image + text)
  - model_name: vision-cheap
    litellm_params:
      model: gemini/gemini-2.5-pro
      # Uses GEMINI_API_KEY env var automatically

  # High-volume, low-cost (summaries, classification)
  - model_name: bulk
    litellm_params:
      model: openai/gpt-5-mini
      # Uses OPENAI_API_KEY env var automatically

router_settings:
  routing_strategy: simple-shuffle
  num_retries: 2
  timeout: 60
  fallbacks:
    - smart-cloud: ["bulk"]
    - vision-cheap: ["smart-cloud"]
  context_window_fallbacks:
    - bulk: ["smart-cloud"]

litellm_settings:
  drop_params: true
  set_verbose: false
  cache: true
  cache_params:
    type: local
    ttl: 3600

general_settings:
  master_key: ${LITELLM_MASTER_KEY}
  database_url: sqlite:///./litellm.db
```

- [ ] **Step 2: Create `infra/start_vllm.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

MODEL="${VLLM_MODEL:-Qwen/Qwen3-8B-Instruct-AWQ}"
PORT="${VLLM_PORT:-8000}"

echo "Starting vLLM: model=${MODEL} port=${PORT}"

vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --quantization awq \
  --max-model-len 32768 \
  --served-model-name qwen3-local \
  --gpu-memory-utilization 0.9

# GPU memory fallback: if the above fails on low VRAM, retry with a smaller model:
# VLLM_MODEL=Qwen/Qwen3-4B-Instruct-AWQ bash infra/start_vllm.sh
```

- [ ] **Step 3: Create `infra/start_litellm.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
echo "Starting LiteLLM proxy on port 4000 ..."
litellm --config configs/litellm_config.yaml --port 4000
```

- [ ] **Step 4: Make scripts executable and create `infra/docker-compose.yml`**

```bash
chmod +x infra/start_vllm.sh infra/start_litellm.sh
```

```yaml
# infra/docker-compose.yml
version: "3.9"

services:
  vllm:
    image: vllm/vllm-openai:latest
    runtime: nvidia
    environment:
      HUGGING_FACE_HUB_TOKEN: "${HF_TOKEN:-}"
    command:
      - "--model=Qwen/Qwen3-8B-Instruct-AWQ"
      - "--quantization=awq"
      - "--max-model-len=32768"
      - "--served-model-name=qwen3-local"
      - "--gpu-memory-utilization=0.9"
    ports:
      - "8000:8000"
    volumes:
      - type: bind
        source: "${HF_CACHE_DIR:-~/.cache/huggingface}"
        target: /root/.cache/huggingface
    restart: unless-stopped

  litellm:
    image: ghcr.io/berriai/litellm:main-latest
    ports:
      - "4000:4000"
    volumes:
      - type: bind
        source: ../configs/litellm_config.yaml
        target: /app/config.yaml
    command: ["--config=/app/config.yaml", "--port=4000"]
    environment:
      ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY:-}"
      OPENAI_API_KEY: "${OPENAI_API_KEY:-}"
      GEMINI_API_KEY: "${GEMINI_API_KEY:-}"
      LITELLM_MASTER_KEY: "${LITELLM_MASTER_KEY:-}"
    depends_on:
      - vllm
    restart: unless-stopped
```

- [ ] **Step 5: Commit**

```bash
git add configs/litellm_config.yaml infra/start_vllm.sh infra/start_litellm.sh infra/docker-compose.yml
git commit -m "chore: add LiteLLM proxy config and vLLM infra scripts"
```

---

## Task 2: Dependencies and Settings

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/second_brain/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_config.py
import pytest
from pydantic import AnyHttpUrl

from second_brain.config import Settings


def test_settings_has_litellm_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_LITELLM_BASE_URL", "http://localhost:4000")
    s = Settings()
    assert str(s.litellm_base_url) == "http://localhost:4000/"


def test_settings_litellm_master_key_default_is_none() -> None:
    s = Settings()
    assert s.litellm_master_key is None


def test_settings_litellm_master_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_LITELLM_MASTER_KEY", "sk-test-key")
    s = Settings()
    assert s.litellm_master_key is not None
    assert s.litellm_master_key.get_secret_value() == "sk-test-key"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_llm_config.py -v
```

Expected: `FAILED` — `Settings` has no `litellm_base_url` field

- [ ] **Step 3: Add `openai` to `pyproject.toml`, add `[proxy]` extra and `pytest-mock` to dev**

In `pyproject.toml`, update the `dependencies` array to add `openai`:

```toml
dependencies = [
    "python-frontmatter>=1.1",
    "pydantic>=2.7",
    "pydantic-settings>=2.4",
    "typer>=0.12",
    "rich>=13.7",
    "structlog>=24.1",
    "pygit2>=1.15",
    "openai>=1.50",
]

[project.optional-dependencies]
proxy = [
    "litellm[proxy]>=1.50",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.14",
    "ruff>=0.4",
    "mypy>=1.10",
    "pre-commit>=3.7",
]
```

Then add mypy override for openai (it ships type stubs, but add a permissive override if strict mode complains):

```toml
[[tool.mypy.overrides]]
module = ["frontmatter", "pygit2"]
ignore_missing_imports = true
```

(No changes to the overrides needed — `openai` has built-in type stubs.)

- [ ] **Step 4: Extend `src/second_brain/config.py`**

```python
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SECOND_BRAIN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    vault_path: Path = Field(default_factory=lambda: Path.home() / "second-brain-vault")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    local_only: bool = False

    litellm_base_url: AnyHttpUrl = Field(
        default="http://localhost:4000",
    )
    litellm_master_key: SecretStr | None = Field(default=None)
```

- [ ] **Step 5: Update `.env.example`**

```bash
# Vault
SECOND_BRAIN_VAULT_PATH=~/second-brain-vault
SECOND_BRAIN_LOG_LEVEL=INFO
SECOND_BRAIN_LOCAL_ONLY=false

# LiteLLM proxy
SECOND_BRAIN_LITELLM_BASE_URL=http://localhost:4000
SECOND_BRAIN_LITELLM_MASTER_KEY=sk-your-master-key

# Provider API keys (used by LiteLLM proxy, not by second-brain directly)
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
LITELLM_MASTER_KEY=sk-your-master-key
```

- [ ] **Step 6: Install updated deps**

```bash
uv sync
```

- [ ] **Step 7: Run test to verify it passes**

```bash
uv run pytest tests/test_llm_config.py -v
```

Expected: `PASSED` (3 tests)

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/second_brain/config.py .env.example tests/test_llm_config.py
git commit -m "chore: add openai dep, [proxy] extra, and LiteLLM Settings fields"
```

---

## Task 3: Router Types and Errors

**Files:**
- Create: `src/second_brain/llm/__init__.py`
- Create: `src/second_brain/llm/types.py`
- Create: `src/second_brain/llm/errors.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_types.py
from second_brain.llm import RouterError, PrivacyViolationError, TaskType, Sensitivity
from second_brain.llm.types import TaskType, Sensitivity
from second_brain.llm.errors import RouterError, PrivacyViolationError
from typing import get_args


def test_task_type_literals() -> None:
    args = get_args(TaskType)
    assert set(args) == {"ingest_summary", "synthesis_complex", "vision", "lint_check"}


def test_sensitivity_literals() -> None:
    args = get_args(Sensitivity)
    assert set(args) == {"normal", "private"}


def test_privacy_violation_is_router_error() -> None:
    exc = PrivacyViolationError("test")
    assert isinstance(exc, RouterError)


def test_router_error_message() -> None:
    exc = RouterError("something went wrong")
    assert "something went wrong" in str(exc)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_llm_types.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'second_brain.llm'`

- [ ] **Step 3: Create `src/second_brain/llm/types.py`**

```python
from __future__ import annotations

from typing import Literal

TaskType = Literal["ingest_summary", "synthesis_complex", "vision", "lint_check"]
Sensitivity = Literal["normal", "private"]
```

- [ ] **Step 4: Create `src/second_brain/llm/errors.py`**

```python
from __future__ import annotations


class RouterError(Exception):
    """Base class for all LLM router errors."""


class PrivacyViolationError(RouterError):
    """Raised when a private request would be sent to a cloud model."""
```

- [ ] **Step 5: Create `src/second_brain/llm/__init__.py`**

```python
from .errors import PrivacyViolationError, RouterError
from .metrics import LLMCallMetrics, MetricsRecorder
from .router import LLMRouter
from .types import Sensitivity, TaskType

__all__ = [
    "LLMRouter",
    "TaskType",
    "Sensitivity",
    "RouterError",
    "PrivacyViolationError",
    "LLMCallMetrics",
    "MetricsRecorder",
]
```

Note: `__init__.py` imports from `router` and `metrics` — create those placeholder files now to avoid circular import errors during test:

Create `src/second_brain/llm/metrics.py` (stub, will be filled in Task 5):

```python
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
```

Create `src/second_brain/llm/router.py` (stub, will be filled in Task 6):

```python
from __future__ import annotations


class LLMRouter:
    """Placeholder — implemented in Task 6."""
```

- [ ] **Step 6: Run test to verify it passes**

```bash
uv run pytest tests/test_llm_types.py -v
```

Expected: `PASSED` (4 tests)

- [ ] **Step 7: Commit**

```bash
git add src/second_brain/llm/ tests/test_llm_types.py
git commit -m "feat: add LLM router types and error classes"
```

---

## Task 4: Routing Policy and Privacy Guard

**Files:**
- Create: `src/second_brain/llm/policy.py`
- Create: `tests/test_llm_policy.py`

This task contains the **permanent privacy property test** — a parametrized test over the full Cartesian product of `(TaskType × Sensitivity)` that must never be removed.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_policy.py
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
def test_private_sensitivity_always_selects_local_model(
    task_type: str, sensitivity: str
) -> None:
    """PERMANENT: private sensitivity must always route to a local model."""
    model = select_model(task_type, sensitivity)  # type: ignore[arg-type]
    if sensitivity == "private":
        assert model in LOCAL_MODELS, (
            f"PRIVACY VIOLATION: {task_type!r} + private → {model!r} (not in LOCAL_MODELS)"
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_llm_policy.py -v
```

Expected: `ERROR` — `ImportError: cannot import name 'select_model' from 'second_brain.llm.policy'`

- [ ] **Step 3: Create `src/second_brain/llm/policy.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_llm_policy.py -v
```

Expected: `PASSED` (8 tests + 8 parametrized property tests = 16 total)

- [ ] **Step 5: Commit**

```bash
git add src/second_brain/llm/policy.py tests/test_llm_policy.py
git commit -m "feat: add routing policy with permanent privacy property test"
```

---

## Task 5: Call Metrics

**Files:**
- Modify: `src/second_brain/llm/metrics.py` (replace stub with full pydantic implementation)
- Create: `tests/test_llm_metrics.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_metrics.py
from __future__ import annotations

from datetime import datetime

import pytest

from second_brain.llm.metrics import LLMCallMetrics, MetricsRecorder


def test_metrics_records_are_stored() -> None:
    recorder = MetricsRecorder()
    m = LLMCallMetrics(
        task_type="ingest_summary",
        sensitivity="normal",
        model="bulk",
        latency_ms=123.4,
        prompt_tokens=50,
        completion_tokens=200,
    )
    recorder.record(m)
    assert len(recorder.all()) == 1
    assert recorder.all()[0].model == "bulk"


def test_metrics_clear() -> None:
    recorder = MetricsRecorder()
    recorder.record(
        LLMCallMetrics(
            task_type="lint_check",
            sensitivity="normal",
            model="bulk",
            latency_ms=50.0,
            prompt_tokens=10,
            completion_tokens=5,
        )
    )
    recorder.clear()
    assert recorder.all() == []


def test_metrics_error_field_defaults_none() -> None:
    m = LLMCallMetrics(
        task_type="vision",
        sensitivity="private",
        model="local-fast",
        latency_ms=200.0,
        prompt_tokens=100,
        completion_tokens=80,
    )
    assert m.error is None


def test_metrics_timestamp_is_recent() -> None:
    before = datetime.now()
    m = LLMCallMetrics(
        task_type="synthesis_complex",
        sensitivity="normal",
        model="smart-cloud",
        latency_ms=1800.0,
        prompt_tokens=500,
        completion_tokens=300,
    )
    after = datetime.now()
    assert before <= m.timestamp <= after


def test_metrics_all_returns_copy() -> None:
    recorder = MetricsRecorder()
    snapshot = recorder.all()
    snapshot.append(  # type: ignore[arg-type]
        LLMCallMetrics(
            task_type="ingest_summary",
            sensitivity="normal",
            model="bulk",
            latency_ms=0.0,
            prompt_tokens=0,
            completion_tokens=0,
        )
    )
    assert recorder.all() == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_llm_metrics.py -v
```

Expected: `FAILED` — stub `LLMCallMetrics` is a dataclass with no pydantic validation; `all()` returns the same list reference

- [ ] **Step 3: Rewrite `src/second_brain/llm/metrics.py` with pydantic**

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LLMCallMetrics(BaseModel):
    task_type: str
    sensitivity: str
    model: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    timestamp: datetime = Field(default_factory=datetime.now)
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_llm_metrics.py -v
```

Expected: `PASSED` (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/second_brain/llm/metrics.py tests/test_llm_metrics.py
git commit -m "feat: add pydantic LLMCallMetrics and MetricsRecorder"
```

---

## Task 6: LLMRouter Client

**Files:**
- Modify: `src/second_brain/llm/router.py` (replace stub with full implementation)
- Create: `tests/test_llm_router.py`

All tests mock at `openai.OpenAI().chat.completions.create` — no live proxy needed.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_router.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from second_brain.config import Settings
from second_brain.llm.errors import PrivacyViolationError, RouterError
from second_brain.llm.metrics import MetricsRecorder
from second_brain.llm.router import LLMRouter


def _make_mock_response(content: str = "hello", prompt_tokens: int = 10, completion_tokens: int = 5) -> MagicMock:
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


@pytest.fixture()
def mock_openai_create():
    with patch("second_brain.llm.router.OpenAI") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.chat.completions.create.return_value = _make_mock_response("ok")
        yield instance.chat.completions.create


@pytest.fixture()
def recorder() -> MetricsRecorder:
    return MetricsRecorder()


@pytest.fixture()
def router(mock_openai_create: MagicMock, recorder: MetricsRecorder) -> LLMRouter:
    settings = Settings()
    return LLMRouter(settings=settings, metrics_recorder=recorder)


def test_complete_returns_content(router: LLMRouter, mock_openai_create: MagicMock) -> None:
    result = router.complete(
        [{"role": "user", "content": "ping"}],
        task_type="ingest_summary",
        sensitivity="normal",
    )
    assert result == "ok"


def test_complete_calls_correct_model_for_ingest_summary(
    router: LLMRouter, mock_openai_create: MagicMock
) -> None:
    router.complete(
        [{"role": "user", "content": "summarize"}],
        task_type="ingest_summary",
        sensitivity="normal",
    )
    call_kwargs = mock_openai_create.call_args
    assert call_kwargs.kwargs["model"] == "bulk"


def test_complete_calls_local_fast_for_private(
    router: LLMRouter, mock_openai_create: MagicMock
) -> None:
    router.complete(
        [{"role": "user", "content": "secret"}],
        task_type="ingest_summary",
        sensitivity="private",
    )
    call_kwargs = mock_openai_create.call_args
    assert call_kwargs.kwargs["model"] == "local-fast"


def test_complete_records_metrics(
    router: LLMRouter, mock_openai_create: MagicMock, recorder: MetricsRecorder
) -> None:
    router.complete(
        [{"role": "user", "content": "ping"}],
        task_type="lint_check",
        sensitivity="normal",
    )
    records = recorder.all()
    assert len(records) == 1
    assert records[0].task_type == "lint_check"
    assert records[0].model == "bulk"
    assert records[0].latency_ms >= 0
    assert records[0].error is None


def test_complete_records_error_on_exception(
    router: LLMRouter, mock_openai_create: MagicMock, recorder: MetricsRecorder
) -> None:
    mock_openai_create.side_effect = RuntimeError("connection refused")
    with pytest.raises(RuntimeError):
        router.complete(
            [{"role": "user", "content": "ping"}],
            task_type="ingest_summary",
            sensitivity="normal",
        )
    records = recorder.all()
    assert records[0].error == "connection refused"


def test_local_only_raises_for_cloud_task() -> None:
    settings = Settings()
    settings.local_only = True  # type: ignore[misc]
    with patch("second_brain.llm.router.OpenAI"):
        router = LLMRouter(settings=settings)
    with pytest.raises(RouterError, match="local_only"):
        router.complete(
            [{"role": "user", "content": "synthesize"}],
            task_type="synthesis_complex",
            sensitivity="normal",
        )


def test_local_only_does_not_raise_for_local_task() -> None:
    settings = Settings()
    settings.local_only = True  # type: ignore[misc]
    with patch("second_brain.llm.router.OpenAI") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.chat.completions.create.return_value = _make_mock_response("local ok")
        router = LLMRouter(settings=settings)
        result = router.complete(
            [{"role": "user", "content": "classify"}],
            task_type="ingest_summary",
            sensitivity="private",
        )
    assert result == "local ok"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_llm_router.py -v
```

Expected: `FAILED` — stub `LLMRouter` has no `complete` method

- [ ] **Step 3: Implement `src/second_brain/llm/router.py`**

```python
from __future__ import annotations

import time
from typing import Any

import structlog
from openai import OpenAI

from ..config import Settings
from .errors import PrivacyViolationError, RouterError
from .metrics import LLMCallMetrics, MetricsRecorder
from .policy import LOCAL_MODELS, assert_local_or_raise, select_model
from .types import Sensitivity, TaskType

log = structlog.get_logger(__name__)

_REDACT_KEYS = frozenset({"api_key", "master_key", "Authorization"})


def _redact_processor(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    for key in _REDACT_KEYS:
        if key in event_dict:
            event_dict[key] = "***"
    return event_dict


structlog.configure(
    processors=[
        _redact_processor,
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)


class LLMRouter:
    def __init__(
        self,
        settings: Settings | None = None,
        metrics_recorder: MetricsRecorder | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self._recorder = metrics_recorder or MetricsRecorder()
        master_key = (
            self._settings.litellm_master_key.get_secret_value()
            if self._settings.litellm_master_key
            else "sk-no-key"
        )
        self._client = OpenAI(
            base_url=str(self._settings.litellm_base_url),
            api_key=master_key,
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        task_type: TaskType,
        sensitivity: Sensitivity,
        **kwargs: Any,
    ) -> str:
        model = select_model(task_type, sensitivity)
        assert_local_or_raise(model, sensitivity)

        if self._settings.local_only and model not in LOCAL_MODELS:
            raise RouterError(
                f"local_only=True but policy selected cloud model '{model}' for {task_type!r}"
            )

        t0 = time.monotonic()
        error: str | None = None
        prompt_tokens = 0
        completion_tokens = 0

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                **kwargs,
            )
            content = response.choices[0].message.content or ""
            if response.usage:
                prompt_tokens = response.usage.prompt_tokens
                completion_tokens = response.usage.completion_tokens
            return content
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            latency_ms = (time.monotonic() - t0) * 1000
            self._recorder.record(
                LLMCallMetrics(
                    task_type=task_type,
                    sensitivity=sensitivity,
                    model=model,
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error=error,
                )
            )
            log.info(
                "llm.complete",
                task_type=task_type,
                sensitivity=sensitivity,
                model=model,
                latency_ms=round(latency_ms, 1),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                error=error,
            )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_llm_router.py -v
```

Expected: `PASSED` (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/second_brain/llm/router.py tests/test_llm_router.py
git commit -m "feat: implement LLMRouter with policy routing, metrics, and structlog"
```

---

## Task 7: CLI `llm` Subcommand

**Files:**
- Modify: `src/second_brain/cli.py`
- Create: `tests/test_llm_cli.py`

Add a `llm_app = typer.Typer()` with two commands:
- `llm route --task ... --sensitivity ...` — dry-run policy resolution, no network
- `llm test` — sends a fixed prompt; unit test mocks the router, manual smoke test is separate

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_cli.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from second_brain.cli import app

runner = CliRunner()


def test_llm_route_ingest_normal() -> None:
    result = runner.invoke(app, ["llm", "route", "--task", "ingest_summary", "--sensitivity", "normal"])
    assert result.exit_code == 0
    assert "bulk" in result.output


def test_llm_route_synthesis_private() -> None:
    result = runner.invoke(app, ["llm", "route", "--task", "synthesis_complex", "--sensitivity", "private"])
    assert result.exit_code == 0
    assert "local-fast" in result.output


def test_llm_route_invalid_task() -> None:
    result = runner.invoke(app, ["llm", "route", "--task", "nonexistent", "--sensitivity", "normal"])
    assert result.exit_code != 0


def test_llm_route_invalid_sensitivity() -> None:
    result = runner.invoke(app, ["llm", "route", "--task", "ingest_summary", "--sensitivity", "secret"])
    assert result.exit_code != 0


def test_llm_test_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_router = MagicMock()
    mock_router.complete.return_value = "pong"
    with patch("second_brain.cli.LLMRouter", return_value=mock_router):
        result = runner.invoke(app, ["llm", "test"])
    assert result.exit_code == 0
    assert "pong" in result.output or "ok" in result.output.lower()


def test_llm_test_router_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from second_brain.llm.errors import RouterError

    mock_router = MagicMock()
    mock_router.complete.side_effect = RouterError("proxy not running")
    with patch("second_brain.cli.LLMRouter", return_value=mock_router):
        result = runner.invoke(app, ["llm", "test"])
    assert result.exit_code == 1
    assert "proxy not running" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_llm_cli.py -v
```

Expected: `FAILED` — no `llm` subcommand exists on `app`

- [ ] **Step 3: Add `llm_app` to `src/second_brain/cli.py`**

At the top of `cli.py`, add the import and create `llm_app`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from .storage.git_ops import init_repo

app = typer.Typer(name="second-brain", help="Personal second brain CLI.")
note_app = typer.Typer(help="Note management commands.")
llm_app = typer.Typer(help="LLM router commands.")
app.add_typer(note_app, name="note")
app.add_typer(llm_app, name="llm")

console = Console()
```

Then add the two commands after the existing `note_add` command:

```python
@llm_app.command("route")
def llm_route(
    task: Annotated[
        str,
        typer.Option("--task", "-t", help="Task type (ingest_summary|synthesis_complex|vision|lint_check)"),
    ],
    sensitivity: Annotated[
        str,
        typer.Option("--sensitivity", "-s", help="Sensitivity (normal|private)"),
    ] = "normal",
) -> None:
    """Show which model would be selected for a given task/sensitivity (dry-run)."""
    from .llm.policy import select_model
    from .llm.types import TaskType, Sensitivity
    from typing import get_args

    valid_tasks = get_args(TaskType)
    valid_sensitivities = get_args(Sensitivity)

    if task not in valid_tasks:
        console.print(
            f"[red]Invalid task[/red] '{task}'. Choose from: {', '.join(valid_tasks)}"
        )
        raise typer.Exit(1)

    if sensitivity not in valid_sensitivities:
        console.print(
            f"[red]Invalid sensitivity[/red] '{sensitivity}'. Choose from: {', '.join(valid_sensitivities)}"
        )
        raise typer.Exit(1)

    model = select_model(task, sensitivity)  # type: ignore[arg-type]
    console.print(
        f"[bold]Route:[/bold] task={task!r} sensitivity={sensitivity!r} → [green]{model}[/green]"
    )


@llm_app.command("test")
def llm_test() -> None:
    """Ping the LLM router with a fixed prompt (requires LiteLLM proxy running)."""
    from .llm import LLMRouter
    from .llm.errors import RouterError

    router = LLMRouter()
    try:
        response = router.complete(
            [{"role": "user", "content": "Reply with exactly: pong"}],
            task_type="ingest_summary",
            sensitivity="normal",
        )
        console.print(f"[green]✓[/green] Router responded: [bold]{response}[/bold]")
    except RouterError as exc:
        console.print(f"[red]✗[/red] Router error: {exc}")
        raise typer.Exit(1) from exc
    except Exception as exc:
        console.print(f"[red]✗[/red] Unexpected error: {exc}")
        raise typer.Exit(1) from exc
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_llm_cli.py -v
```

Expected: `PASSED` (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/second_brain/cli.py tests/test_llm_cli.py
git commit -m "feat: add CLI llm subcommand (route and test)"
```

---

## Task 8: Update `_ROUTING_POLICY_MD`

**Files:**
- Modify: `src/second_brain/cli.py:191-214`

The Phase 1 stub says "No LLM routing is active in Phase 1. All LLM calls raise `NotImplementedError`." Replace it with the live Phase 2 policy table.

- [ ] **Step 1: Replace `_ROUTING_POLICY_MD` constant in `cli.py`**

Find and replace the existing `_ROUTING_POLICY_MD` string (the one with "Phase 1 Behavior" stub) with:

```python
_ROUTING_POLICY_MD = """\
# Routing Policy

Routing is governed by `task_type` and `sensitivity`. The policy is enforced in two layers:
1. `policy.select_model(task_type, sensitivity)` → selects logical model name
2. `policy.assert_local_or_raise(model, sensitivity)` → defense-in-depth guard

## Model Assignments

| Task type               | Sensitivity | Model        | Reason                         |
|-------------------------|-------------|--------------|--------------------------------|
| ingest_summary          | normal      | bulk         | High volume, cost-sensitive    |
| ingest_summary          | private     | local-fast   | Privacy override               |
| synthesis_complex       | normal      | smart-cloud  | Quality matters most           |
| synthesis_complex       | private     | local-fast   | Privacy override               |
| vision                  | normal      | vision-cheap | Multimodal capability          |
| vision                  | private     | local-fast   | Privacy override               |
| lint_check              | normal      | bulk         | High volume, cost-sensitive    |
| lint_check              | private     | local-fast   | Privacy override               |

## Logical Model Definitions

| Logical Name  | Provider   | Model ID              | Port  |
|---------------|------------|-----------------------|-------|
| local-fast    | vLLM       | Qwen3-8B-Instruct-AWQ | 8000  |
| smart-cloud   | Anthropic  | claude-opus-4-7       | cloud |
| vision-cheap  | Google     | gemini-2.5-pro        | cloud |
| bulk          | OpenAI     | gpt-5-mini            | cloud |

## Invariant

Any request with `sensitivity=private` MUST route to `local-fast`.
This is enforced at the router layer with a permanent property test.
`local_only=True` causes cloud-routed tasks to RAISE (not silently downgrade).
"""
```

- [ ] **Step 2: Run the full test suite to verify no regressions**

```bash
uv run pytest -v
```

Expected: all tests pass (24 existing + new llm tests)

- [ ] **Step 3: Commit**

```bash
git add src/second_brain/cli.py
git commit -m "fix: update _ROUTING_POLICY_MD to reflect Phase 2 routing policy"
```

---

## Task 9: Full Verification

**Files:** None (read-only verification)

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass with no failures or errors. Verify that `test_private_sensitivity_always_selects_local_model` appears in output (8 parametrized cases, one per `task_type × sensitivity` pair where sensitivity=private matters).

- [ ] **Step 2: Run mypy strict check**

```bash
uv run mypy src/
```

Expected: `Success: no issues found in N source files`

If you see errors about `openai` stub types (e.g., `Cannot find implementation`), add to `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = ["openai.*"]
ignore_missing_imports = true
```

- [ ] **Step 3: Run ruff lint and format check**

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

Expected: no issues

- [ ] **Step 4: Manual smoke test (requires proxy running)**

This step requires the LiteLLM proxy and at least one provider configured. Run it locally after starting the proxy:

```bash
# Terminal 1: start vLLM (requires GPU)
bash infra/start_vllm.sh

# Terminal 2: start LiteLLM proxy
bash infra/start_litellm.sh

# Terminal 3: verify proxy health
curl http://localhost:4000/health
# Expected: {"status": "healthy"}

# Verify model list
curl http://localhost:4000/v1/models
# Expected: JSON with local-fast, smart-cloud, vision-cheap, bulk

# Test via CLI
uv run second-brain llm route --task ingest_summary --sensitivity normal
# Expected: Route: task='ingest_summary' sensitivity='normal' → bulk

uv run second-brain llm route --task synthesis_complex --sensitivity private
# Expected: Route: task='synthesis_complex' sensitivity='private' → local-fast

uv run second-brain llm test
# Expected: ✓ Router responded: pong  (or whatever the model returns)
```

---

## Acceptance Criteria Checklist

- [ ] `uv run pytest -v` — all tests pass, including 8+ parametrized privacy property tests
- [ ] `uv run mypy src/` — no type errors (strict mode)
- [ ] `uv run ruff check src/ tests/` — no lint issues
- [ ] `uv run ruff format --check src/ tests/` — no format issues
- [ ] `test_private_sensitivity_always_selects_local_model` is present in `tests/test_llm_policy.py` and passes
- [ ] `local_only=True` raises `RouterError` (not silently downgrades) — verified by `test_local_only_raises_for_cloud_task`
- [ ] `PrivacyViolationError` is raised by `assert_local_or_raise` when sensitivity=private and model is cloud — verified by `test_assert_local_or_raise_raises_for_cloud_model_with_private`
- [ ] CI runs with no API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` absent) — all unit tests mock the openai SDK seam
- [ ] Manual smoke test: `second-brain llm test` returns a response when proxy is running
- [ ] `second-brain llm route` correctly shows `local-fast` for any `--sensitivity private` input
- [ ] `second-brain init ~/vault` creates `_meta/routing-policy.md` with the Phase 2 policy table
- [ ] `uv sync --extra proxy` installs `litellm[proxy]`; `uv sync` (no extra) does not require litellm

---

## Notes for Future Phases

- **Phase 5 async migration**: Wrap `LLMRouter.complete` with `asyncio.to_thread(router.complete, ...)` in LangGraph nodes. No changes to `router.py` required.
- **Fallback testing**: LiteLLM proxy fallback chains (`smart-cloud → bulk`, `vision-cheap → smart-cloud`) are proxy-level configuration — not tested at the Python unit level. Integration testing requires a running proxy with intentionally broken upstream.
- **Cost tracking**: `LLMCallMetrics` captures `prompt_tokens` and `completion_tokens`. Phase 5+ can add a cost calculator using provider pricing tables.
