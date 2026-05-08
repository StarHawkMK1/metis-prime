# Phase 1 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap the second-brain project skeleton with vault init, settings, storage abstraction, and a basic CLI so that notes can be written to a git-versioned vault from the command line.

**Architecture:** Project code (`D:\python-workspace\metis-prime`) and vault data (user-specified path) are **two separate git repositories**. The code repo is initialized once in Task 1; the vault repo is created on demand by `second-brain init <vault-path>`. All wiki writes go through `Vault`, which enforces the `raw/` immutability rule and auto-commits changes via pygit2.

**Tech Stack:** Python 3.11+, uv, pydantic v2 + pydantic-settings, python-frontmatter, pygit2, typer + rich, structlog, pytest + mypy (strict) + ruff

---

## File Structure

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | Phase-1-only deps, scripts entry point, ruff / mypy / pytest config |
| `.gitignore` | Project-level Python/uv ignores |
| `.env.example` | Env var documentation for contributors |
| `README.md` | Basic setup instructions |
| `.pre-commit-config.yaml` | ruff + mypy hooks (Task 8) |
| `.github/workflows/ci.yml` | CI: pytest + mypy on push (Task 8) |
| `src/second_brain/__init__.py` | Package version string |
| `src/second_brain/config.py` | `Settings` (pydantic-settings, env vars + .env file) |
| `src/second_brain/storage/__init__.py` | Re-exports: `Vault`, `WikiPage`, `ProvenanceBreakdown` |
| `src/second_brain/storage/frontmatter.py` | `WikiPage` pydantic model; parse/serialize YAML frontmatter |
| `src/second_brain/storage/git_ops.py` | `init_repo`, `auto_commit` via pygit2 |
| `src/second_brain/storage/vault.py` | `Vault`: read/write/list wiki pages; enforces raw/ immutability |
| `src/second_brain/cli.py` | typer app: `init`, `status`, `note add` sub-commands |
| `tests/conftest.py` | `tmp_vault` pytest fixture (git-initialized temp vault) |
| `tests/test_vault.py` | Unit tests: Settings, WikiPage model, git ops, Vault CRUD |
| `tests/test_cli.py` | Integration tests: CLI command behavior |

---

## Task 1: Project Bootstrap

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `src/second_brain/__init__.py`
- Create: `src/second_brain/storage/__init__.py` (empty placeholder)
- Create: `tests/__init__.py` (empty)

- [ ] **Step 1: Write `pyproject.toml`**

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
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "mypy>=1.10",
    "pre-commit>=3.7",
]

[project.scripts]
second-brain = "second_brain.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/second_brain"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
strict = true
python_version = "3.11"

[[tool.mypy.overrides]]
module = ["frontmatter", "pygit2"]
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Write `.gitignore`**

```
__pycache__/
*.py[cod]
*.pyo
*.so
.venv/
.env
dist/
build/
*.egg-info/
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/
.idea/
.vscode/
*.swp
.DS_Store
```

- [ ] **Step 3: Write `.env.example`**

```
# Second Brain environment configuration
# Copy to .env and fill in values

# Vault location (defaults to ~/second-brain-vault)
SECOND_BRAIN_VAULT_PATH=~/second-brain-vault

# Logging level: DEBUG | INFO | WARNING | ERROR
SECOND_BRAIN_LOG_LEVEL=INFO

# Set to 1 to block all cloud API calls (privacy mode)
SECOND_BRAIN_LOCAL_ONLY=0
```

- [ ] **Step 4: Write `README.md`**

```markdown
# second-brain

Personal knowledge management system (Metis Prime) built on Andrej Karpathy's LLM Wiki pattern.

## Setup

```bash
# Install dependencies
uv sync --dev

# Initialize a vault
uv run second-brain init ~/second-brain-vault

# Check vault status
uv run second-brain status
```

## Development

```bash
uv run pytest           # Run tests
uv run mypy src/        # Type check (strict)
uv run ruff check src/  # Lint
```

See `docs/spec/second-brain-spec.md` for the full project specification.
```

- [ ] **Step 5: Create package skeleton files**

`src/second_brain/__init__.py`:
```python
__version__ = "0.1.0"
```

`src/second_brain/storage/__init__.py` (empty for now, populated in Task 5):
```python
```

`tests/__init__.py` (empty):
```python
```

- [ ] **Step 6: Install dependencies**

Run:
```
uv sync --dev
```

Expected: uv creates `.venv/` and resolves all deps without errors. Last lines look like:
```
Installed N packages in Xs
```

- [ ] **Step 7: Smoke-check package import**

Run:
```
uv run python -c "import second_brain; print(second_brain.__version__)"
```

Expected:
```
0.1.0
```

- [ ] **Step 8: Initialize project git repo**

Run:
```
git init
git add pyproject.toml .gitignore .env.example README.md src/ tests/
git commit -m "chore: project bootstrap — Phase 1 skeleton"
```

Expected: commit succeeds, `git log --oneline` shows one entry.

---

## Task 2: Settings System

**Files:**
- Create: `src/second_brain/config.py`
- Modify: `tests/test_vault.py`

- [ ] **Step 1: Write failing tests in `tests/test_vault.py`**

```python
import pytest
from second_brain.config import Settings


def test_settings_defaults() -> None:
    s = Settings()
    assert s.log_level == "INFO"
    assert s.local_only is False


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("SECOND_BRAIN_LOCAL_ONLY", "true")
    s = Settings()
    assert s.log_level == "DEBUG"
    assert s.local_only is True


def test_settings_vault_path_default() -> None:
    s = Settings()
    assert "second-brain-vault" in str(s.vault_path)
```

- [ ] **Step 2: Run tests — verify they fail**

Run:
```
uv run pytest tests/test_vault.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'second_brain.config'`

- [ ] **Step 3: Implement `src/second_brain/config.py`**

```python
from pathlib import Path
from typing import Literal

from pydantic import Field
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
```

- [ ] **Step 4: Run tests — verify they pass**

Run:
```
uv run pytest tests/test_vault.py -v
```

Expected:
```
PASSED tests/test_vault.py::test_settings_defaults
PASSED tests/test_vault.py::test_settings_from_env
PASSED tests/test_vault.py::test_settings_vault_path_default
3 passed
```

- [ ] **Step 5: Commit**

```
git add src/second_brain/config.py tests/test_vault.py
git commit -m "feat: add Settings with pydantic-settings"
```

---

## Task 3: WikiPage Model

**Files:**
- Create: `src/second_brain/storage/frontmatter.py`
- Modify: `tests/test_vault.py`

- [ ] **Step 1: Append failing tests to `tests/test_vault.py`**

```python
from datetime import date
from second_brain.storage.frontmatter import WikiPage, ProvenanceBreakdown


def test_wiki_page_defaults() -> None:
    page = WikiPage(title="Test", type="concept")
    assert page.status == "draft"
    assert page.tags == []
    assert page.body == ""
    assert page.provenance.extracted == 70


def test_wiki_page_to_markdown_has_frontmatter() -> None:
    page = WikiPage(title="Python Basics", type="concept", body="Python is a language.")
    md = page.to_markdown()
    assert "title: Python Basics" in md
    assert "type: concept" in md
    assert "Python is a language." in md


def test_wiki_page_roundtrip() -> None:
    original = WikiPage(
        title="Machine Learning",
        type="concept",
        tags=["ai", "learning"],
        sources=["raw/clips/ml-intro.md"],
        body="ML is a subfield of AI.",
    )
    md = original.to_markdown()
    loaded = WikiPage.from_markdown(md)
    assert loaded.title == "Machine Learning"
    assert loaded.type == "concept"
    assert loaded.tags == ["ai", "learning"]
    assert loaded.sources == ["raw/clips/ml-intro.md"]
    assert loaded.body == "ML is a subfield of AI."


def test_provenance_breakdown_defaults() -> None:
    p = ProvenanceBreakdown()
    assert p.extracted + p.inferred + p.ambiguous == 100
```

- [ ] **Step 2: Run tests — verify they fail**

Run:
```
uv run pytest tests/test_vault.py::test_wiki_page_defaults -v
```

Expected: `FAILED` — `ImportError: cannot import name 'WikiPage'`

- [ ] **Step 3: Implement `src/second_brain/storage/frontmatter.py`**

```python
from __future__ import annotations

from datetime import date
from typing import Any, Literal, cast

import frontmatter as fm
from pydantic import BaseModel, Field

PageType = Literal["concept", "project", "person", "place", "ref", "map"]
PageStatus = Literal["draft", "active", "archived"]


class ProvenanceBreakdown(BaseModel):
    extracted: int = Field(ge=0, le=100, default=70)
    inferred: int = Field(ge=0, le=100, default=25)
    ambiguous: int = Field(ge=0, le=100, default=5)


class WikiPage(BaseModel):
    title: str
    type: PageType
    status: PageStatus = "draft"
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    provenance: ProvenanceBreakdown = Field(default_factory=ProvenanceBreakdown)
    created: date = Field(default_factory=date.today)
    updated: date = Field(default_factory=date.today)
    body: str = ""

    def to_markdown(self) -> str:
        post = fm.Post(
            self.body,
            title=self.title,
            type=self.type,
            status=self.status,
            tags=self.tags,
            sources=self.sources,
            provenance=self.provenance.model_dump(),
            created=str(self.created),
            updated=str(self.updated),
        )
        return str(fm.dumps(post))

    @classmethod
    def from_markdown(cls, text: str) -> WikiPage:
        post = fm.loads(text)
        prov_raw: Any = post.get("provenance")
        prov: dict[str, Any] = prov_raw if isinstance(prov_raw, dict) else {}
        return cls(
            title=str(post["title"]),
            type=cast(PageType, post["type"]),
            status=cast(PageStatus, post.get("status", "draft")),
            tags=list(post.get("tags") or []),
            sources=list(post.get("sources") or []),
            provenance=ProvenanceBreakdown(**prov),
            created=post.get("created", date.today()),
            updated=post.get("updated", date.today()),
            body=str(post.content),
        )
```

- [ ] **Step 4: Run tests — verify they pass**

Run:
```
uv run pytest tests/test_vault.py -v -k "wiki_page or provenance"
```

Expected:
```
PASSED tests/test_vault.py::test_wiki_page_defaults
PASSED tests/test_vault.py::test_wiki_page_to_markdown_has_frontmatter
PASSED tests/test_vault.py::test_wiki_page_roundtrip
PASSED tests/test_vault.py::test_provenance_breakdown_defaults
4 passed
```

- [ ] **Step 5: Commit**

```
git add src/second_brain/storage/frontmatter.py tests/test_vault.py
git commit -m "feat: add WikiPage model with frontmatter serialization"
```

---

## Task 4: Git Operations

**Files:**
- Create: `src/second_brain/storage/git_ops.py`
- Create: `tests/conftest.py`
- Modify: `tests/test_vault.py`

- [ ] **Step 1: Append failing tests to `tests/test_vault.py`**

```python
import pygit2
from second_brain.storage.git_ops import init_repo, auto_commit


def test_init_repo_creates_git_directory(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    init_repo(target)
    assert (target / ".git").is_dir()


def test_init_repo_head_is_born(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    init_repo(target)
    repo = pygit2.Repository(str(target))
    assert not repo.head_is_unborn


def test_init_repo_creates_initial_commit(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    init_repo(target)
    repo = pygit2.Repository(str(target))
    commits = list(repo.walk(repo.head.target))
    assert len(commits) == 1
    assert "init" in commits[0].message


def test_auto_commit_stages_file_and_commits(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    init_repo(target)

    test_file = target / "note.md"
    test_file.write_text("hello", encoding="utf-8")
    auto_commit(target, "test: add note", [test_file])

    repo = pygit2.Repository(str(target))
    commits = list(repo.walk(repo.head.target))
    assert len(commits) == 2
    assert commits[0].message == "test: add note"


def test_auto_commit_noop_on_empty_paths(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    init_repo(target)
    # Should not raise and not create an extra commit
    auto_commit(target, "noop", [])
    repo = pygit2.Repository(str(target))
    commits = list(repo.walk(repo.head.target))
    assert len(commits) == 1
```

Also add the missing import at the top of the test file:

```python
from pathlib import Path
```

- [ ] **Step 2: Run tests — verify they fail**

Run:
```
uv run pytest tests/test_vault.py::test_init_repo_creates_git_directory -v
```

Expected: `FAILED` — `ImportError: cannot import name 'init_repo'`

- [ ] **Step 3: Implement `src/second_brain/storage/git_ops.py`**

```python
from pathlib import Path
from typing import Any

import pygit2


def _get_signature(repo: Any) -> Any:
    try:
        return repo.default_signature
    except KeyError:
        return pygit2.Signature("Second Brain", "second-brain@local")


def init_repo(path: Path) -> None:
    """Initialize a git repo and commit all files present in the directory."""
    repo = pygit2.init_repository(str(path))
    index = repo.index
    index.read()
    index.add_all()
    index.write()
    sig = _get_signature(repo)
    tree = index.write_tree()
    repo.create_commit("refs/heads/main", sig, sig, "init: initialize vault", tree, [])


def auto_commit(repo_path: Path, message: str, paths: list[Path]) -> None:
    """Stage specific files and create a commit. No-op if paths is empty."""
    if not paths:
        return
    repo = pygit2.Repository(str(repo_path))
    index = repo.index
    index.read()
    for p in paths:
        rel = str(p.relative_to(repo_path)).replace("\\", "/")
        index.add(rel)
    index.write()
    sig = _get_signature(repo)
    tree = index.write_tree()
    parent_ids: list[Any] = [] if repo.head_is_unborn else [repo.head.target]
    repo.create_commit("refs/heads/main", sig, sig, message, tree, parent_ids)
```

- [ ] **Step 4: Create `tests/conftest.py`**

```python
from pathlib import Path

import pytest

from second_brain.storage.git_ops import init_repo


@pytest.fixture()
def tmp_vault(tmp_path: Path) -> Path:
    """Temp directory with vault subdirs and git initialized."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "wiki" / "concepts").mkdir(parents=True)
    (vault / "raw" / "inbox").mkdir(parents=True)
    (vault / "raw" / "archived").mkdir(parents=True)
    init_repo(vault)
    return vault
```

- [ ] **Step 5: Run tests — verify they pass**

Run:
```
uv run pytest tests/test_vault.py -v -k "init_repo or auto_commit"
```

Expected:
```
PASSED tests/test_vault.py::test_init_repo_creates_git_directory
PASSED tests/test_vault.py::test_init_repo_head_is_born
PASSED tests/test_vault.py::test_init_repo_creates_initial_commit
PASSED tests/test_vault.py::test_auto_commit_stages_file_and_commits
PASSED tests/test_vault.py::test_auto_commit_noop_on_empty_paths
5 passed
```

- [ ] **Step 6: Commit**

```
git add src/second_brain/storage/git_ops.py tests/conftest.py tests/test_vault.py
git commit -m "feat: add pygit2-based git operations (init_repo, auto_commit)"
```

---

## Task 5: Vault Abstraction

**Files:**
- Create: `src/second_brain/storage/vault.py`
- Modify: `src/second_brain/storage/__init__.py`
- Modify: `tests/test_vault.py`

- [ ] **Step 1: Append failing tests to `tests/test_vault.py`**

```python
from second_brain.storage.vault import Vault


def test_write_page_creates_file(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    page = WikiPage(title="Test Concept", type="concept")
    path = vault.write_page("wiki/concepts/test.md", page)
    assert path.exists()


def test_write_page_roundtrip_via_read(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    page = WikiPage(title="Hello World", type="concept", body="Content here.")
    vault.write_page("wiki/concepts/hello.md", page)
    loaded = vault.read_page("wiki/concepts/hello.md")
    assert loaded.title == "Hello World"
    assert loaded.body == "Content here."


def test_list_pages_returns_md_files(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page("wiki/concepts/a.md", WikiPage(title="A", type="concept"))
    vault.write_page("wiki/concepts/b.md", WikiPage(title="B", type="ref"))
    pages = vault.list_pages()
    assert len(pages) == 2


def test_list_pages_empty_returns_empty_list(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    assert vault.list_pages() == []


def test_write_to_raw_raises_runtime_error(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    page = WikiPage(title="Forbidden", type="concept")
    with pytest.raises(RuntimeError, match="Cannot write to raw/"):
        vault.write_page("raw/inbox/forbidden.md", page)


def test_write_page_auto_commits(tmp_vault: Path) -> None:
    import pygit2

    vault = Vault(tmp_vault)
    vault.write_page("wiki/concepts/test.md", WikiPage(title="T", type="concept"))
    repo = pygit2.Repository(str(tmp_vault))
    commits = list(repo.walk(repo.head.target))
    # init commit + write commit = 2
    assert len(commits) >= 2
    assert "write:" in commits[0].message
```

- [ ] **Step 2: Run tests — verify they fail**

Run:
```
uv run pytest tests/test_vault.py::test_write_page_creates_file -v
```

Expected: `FAILED` — `ImportError: cannot import name 'Vault'`

- [ ] **Step 3: Implement `src/second_brain/storage/vault.py`**

```python
from pathlib import Path

from .frontmatter import WikiPage
from .git_ops import auto_commit

_RAW_TOP = "raw"


class Vault:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()

    def _guard_raw(self, full_path: Path) -> None:
        try:
            rel = full_path.relative_to(self.path)
            if rel.parts[0] == _RAW_TOP:
                raise RuntimeError(f"Cannot write to raw/: {full_path}")
        except ValueError:
            pass  # path outside vault — let pydantic/OS error naturally

    def write_page(self, relative_path: str, page: WikiPage) -> Path:
        full_path = self.path / relative_path
        self._guard_raw(full_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(page.to_markdown(), encoding="utf-8")
        auto_commit(self.path, f"write: {relative_path}", [full_path])
        return full_path

    def read_page(self, relative_path: str) -> WikiPage:
        full_path = self.path / relative_path
        return WikiPage.from_markdown(full_path.read_text(encoding="utf-8"))

    def list_pages(self, subdir: str = "wiki") -> list[Path]:
        base = self.path / subdir
        if not base.exists():
            return []
        return sorted(base.rglob("*.md"))
```

- [ ] **Step 4: Update `src/second_brain/storage/__init__.py`**

```python
from .frontmatter import PageStatus, PageType, ProvenanceBreakdown, WikiPage
from .vault import Vault

__all__ = ["Vault", "WikiPage", "ProvenanceBreakdown", "PageType", "PageStatus"]
```

- [ ] **Step 5: Run tests — verify they pass**

Run:
```
uv run pytest tests/test_vault.py -v
```

Expected: all tests pass (includes Task 2, 3, 4, and new vault tests).

```
PASSED tests/test_vault.py::test_settings_defaults
PASSED tests/test_vault.py::test_settings_from_env
PASSED tests/test_vault.py::test_settings_vault_path_default
PASSED tests/test_vault.py::test_wiki_page_defaults
PASSED tests/test_vault.py::test_wiki_page_to_markdown_has_frontmatter
PASSED tests/test_vault.py::test_wiki_page_roundtrip
PASSED tests/test_vault.py::test_provenance_breakdown_defaults
PASSED tests/test_vault.py::test_init_repo_creates_git_directory
PASSED tests/test_vault.py::test_init_repo_head_is_born
PASSED tests/test_vault.py::test_init_repo_creates_initial_commit
PASSED tests/test_vault.py::test_auto_commit_stages_file_and_commits
PASSED tests/test_vault.py::test_auto_commit_noop_on_empty_paths
PASSED tests/test_vault.py::test_write_page_creates_file
PASSED tests/test_vault.py::test_write_page_roundtrip_via_read
PASSED tests/test_vault.py::test_list_pages_returns_md_files
PASSED tests/test_vault.py::test_list_pages_empty_returns_empty_list
PASSED tests/test_vault.py::test_write_to_raw_raises_runtime_error
PASSED tests/test_vault.py::test_write_page_auto_commits
18 passed
```

- [ ] **Step 6: Run mypy on completed storage layer**

Run:
```
uv run mypy src/second_brain/config.py src/second_brain/storage/
```

Expected: `Success: no issues found in 4 source files`

- [ ] **Step 7: Commit**

```
git add src/second_brain/storage/vault.py src/second_brain/storage/__init__.py tests/test_vault.py
git commit -m "feat: add Vault abstraction with raw/ immutability guard"
```

---

## Task 6: CLI `init` Command

**Files:**
- Create: `src/second_brain/cli.py`
- Create: `tests/test_cli.py`

> **Note:** `cli.py` contains large string constants for vault template files (`_SCHEMA_MD`, `_TAXONOMY_MD`, `_ROUTING_POLICY_MD`, `_CHANGELOG_MD`). These are written verbatim below. The schema content is taken directly from SPEC §7.

- [ ] **Step 1: Write failing test in `tests/test_cli.py`**

```python
from pathlib import Path

import pytest
from typer.testing import CliRunner

runner = CliRunner()


def test_init_creates_vault_directory_structure(tmp_path: Path) -> None:
    from second_brain.cli import app

    vault = tmp_path / "test-vault"
    result = runner.invoke(app, ["init", str(vault)])

    assert result.exit_code == 0, result.output

    # SPEC §4: all required vault subdirectories
    for subdir in [
        "wiki/concepts", "wiki/projects", "wiki/people",
        "wiki/places", "wiki/refs", "wiki/maps",
        "raw/inbox", "raw/clips", "raw/transcripts",
        "raw/screenshots", "raw/archived",
        "tasks", "journal", "graph", "_meta",
    ]:
        assert (vault / subdir).is_dir(), f"Missing: {subdir}"

    # Meta files
    assert (vault / "_meta" / "schema.md").exists()
    assert (vault / "_meta" / "taxonomy.md").exists()
    assert (vault / "_meta" / "routing-policy.md").exists()
    assert (vault / "_meta" / "changelog.md").exists()

    # Vault gitignore
    assert (vault / ".gitignore").exists()

    # Git repo initialized
    assert (vault / ".git").is_dir()


def test_init_is_idempotent(tmp_path: Path) -> None:
    from second_brain.cli import app

    vault = tmp_path / "vault"
    runner.invoke(app, ["init", str(vault)])
    result = runner.invoke(app, ["init", str(vault)])
    assert result.exit_code == 0, result.output
```

- [ ] **Step 2: Run tests — verify they fail**

Run:
```
uv run pytest tests/test_cli.py::test_init_creates_vault_directory_structure -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'second_brain.cli'`

- [ ] **Step 3: Create `src/second_brain/cli.py` with `init` command**

```python
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from .storage.git_ops import init_repo

app = typer.Typer(name="second-brain", help="Personal second brain CLI.")
note_app = typer.Typer(help="Note management commands.")
app.add_typer(note_app, name="note")

console = Console()

# ── Vault directory layout (SPEC §4) ──────────────────────────────────────────

_VAULT_DIRS = [
    "_meta",
    "raw/inbox",
    "raw/clips",
    "raw/transcripts",
    "raw/screenshots",
    "raw/archived",
    "wiki/concepts",
    "wiki/projects",
    "wiki/people",
    "wiki/places",
    "wiki/refs",
    "wiki/maps",
    "tasks",
    "journal",
    "graph",
]

_VAULT_GITIGNORE = """\
graph/
.obsidian/workspace*
.obsidian/cache
.DS_Store
"""

# ── Vault meta-file templates ─────────────────────────────────────────────────

_SCHEMA_MD = """\
# Second Brain — Operating Schema

## You are the wiki maintainer

You are an LLM agent maintaining a personal knowledge wiki. Your goal is to compile
incoming raw material into a structured, interlinked, human-readable markdown wiki.

## Core directories

- `raw/` — IMMUTABLE. Source material. NEVER modify or delete files here.
- `wiki/` — Your workspace. Create, edit, link freely.
- `_meta/` — Schema, taxonomy, policies. Edit only when explicitly asked.
- `tasks/`, `journal/` — Append-mostly. Modify only your own previous entries.

## Wiki page structure

Every wiki page MUST have frontmatter:

```yaml
---
title: <Title Case>
type: concept | project | person | place | ref | map
status: draft | active | archived
tags: [tag1, tag2]   # use only tags from _meta/taxonomy.md
sources: [raw/clips/2026-05-06-article.md, ...]
provenance:
  extracted: 70   # % from sources verbatim/paraphrase
  inferred: 25    # % your synthesis
  ambiguous: 5    # % sources disagree
created: 2026-05-06
updated: 2026-05-06
---
```

Body structure:

1. **One-sentence definition** (first line after frontmatter).
2. **Summary** (2-4 sentences).
3. **Sections** (markdown headings). Each claim either:
   - Cites a source: `... according to [[ref/some-paper]] ^[extracted]`
   - Tags inference: `... which suggests Y ^[inferred]`
   - Tags uncertainty: `... but [[ref/A]] and [[ref/B]] disagree ^[ambiguous]`
4. **Related** (auto-generated from wikilinks).

## Operations

### Ingest
1. Read the new source from `raw/`.
2. Extract atomic concepts.
3. For each concept: search existing wiki for similar pages.
   - If similar exists → merge (preserve both perspectives if conflicting).
   - If new → create page.
4. Add wikilinks to related pages (bi-directional where natural).
5. Move source to `raw/archived/` after successful ingest.
6. Commit with message: `ingest: <source-name>`.

### Query
1. Classify intent (factual / synthesis / task).
2. Use graph traversal first (graphify), wiki text second, raw source last.
3. Always cite sources in answers.
4. If answer required reading 3+ pages, suggest creating a new "synthesis" page.

### Lint
1. Find broken wikilinks.
2. Find orphan pages (no incoming/outgoing links).
3. Find pages with `inferred > 70%` (possible hallucination).
4. Find contradictions across pages on same topic.
5. Output report to `journal/lint-YYYY-MM-DD.md`.

## Routing rules (which model to call)

| Task                    | Model         | Reason                           |
|-------------------------|---------------|----------------------------------|
| ingest summary          | bulk          | Volume; Qwen falls back local    |
| ingest of `private` tag | local-fast    | Privacy; never cloud             |
| concept synthesis       | smart-cloud   | Quality matters most             |
| lint contradiction scan | bulk          | Volume                           |
| vision/PDF extraction   | vision-cheap  | Multimodal                       |
| graphify LLM extraction | bulk          | Volume                           |

NEVER use cloud models when sensitivity=private. Caller must pass this flag.

## Hard rules

- NEVER write to `raw/`.
- NEVER delete a wiki page without user confirmation.
- NEVER guess a wikilink target — verify the page exists or mark `^[ambiguous]`.
- ALWAYS update frontmatter `updated:` field on edit.
- ALWAYS commit after edits with descriptive message.
- If contradiction found, DO NOT silently choose — record both with `^[ambiguous]`.

## Style

- Crisp, encyclopedic. No marketing fluff.
- Past-tense for events, present-tense for concepts.
- Prefer concrete examples over abstract definitions.
- Code blocks for commands; LaTeX for math.
- One concept per page, but link liberally.
"""

_TAXONOMY_MD = """\
# Taxonomy — Controlled Vocabulary

All wiki pages must use tags from this list only.
To add a new tag: append to the relevant section and commit.

## Page Types (match `type` frontmatter field)

- `concept` — an idea, technology, term, or principle
- `project` — an ongoing or completed initiative
- `person` — a person (contact, author, public figure)
- `place` — a physical or virtual location
- `ref` — external reference (book, paper, video, article)
- `map` — a hub note; entry point to a topic cluster

## Status

- `draft` — incomplete; not yet reviewed
- `active` — current and actively maintained
- `archived` — no longer relevant; kept for history

## Domain Tags

- `work` — professional / career-related
- `personal` — personal life / health / finance
- `learning` — courses, books, skill development
- `research` — investigation or exploration of a topic
- `tool` — software, hardware, or service
- `ai` — artificial intelligence / machine learning
- `code` — software development / programming
- `writing` — writing, communication, content creation

## Sensitivity

- `private` — MUST NOT be routed to cloud LLMs (enforced by router)
- `public` — safe for any model

## Meta

- `stub` — page exists but needs expansion
- `needs-source` — claims lack citations
- `contradiction` — conflicts with another page; pending resolution
"""

_ROUTING_POLICY_MD = """\
# Routing Policy

Routing policy is configured in Phase 2 (LLM Router). See SPEC §5.2.

## Phase 1 Behavior

No LLM routing is active in Phase 1. All LLM calls raise `NotImplementedError`.

## Invariant (enforced from Phase 2 onward)

Any page or request tagged `private` MUST NOT be sent to a cloud API.
This is enforced at the router layer and has a permanent unit test.

## Phase 2 Model Assignments

| Task type              | Model       |
|------------------------|-------------|
| ingest_summary (normal)| bulk        |
| ingest_summary (private)| local-fast |
| synthesis_complex      | smart-cloud |
| vision                 | vision-cheap|
| lint_check             | bulk        |
"""

_CHANGELOG_MD = """\
# Vault Changelog

Structural changes to the vault (new sections, taxonomy updates, major reorganizations).
Day-to-day content edits are tracked by `git log`.

| Date | Change | Author |
|------|--------|--------|
| INIT | Vault initialized | second-brain init |
"""


# ── CLI commands ──────────────────────────────────────────────────────────────


@app.command()
def init(
    vault_path: Path = typer.Argument(..., help="Path where the new vault will be created."),
) -> None:
    """Initialize a new vault with directory structure, meta files, and git repo."""
    vault_path = vault_path.expanduser().resolve()
    vault_path.mkdir(parents=True, exist_ok=True)

    for subdir in _VAULT_DIRS:
        (vault_path / subdir).mkdir(parents=True, exist_ok=True)

    (vault_path / ".gitignore").write_text(_VAULT_GITIGNORE, encoding="utf-8")
    (vault_path / "_meta" / "schema.md").write_text(_SCHEMA_MD, encoding="utf-8")
    (vault_path / "_meta" / "taxonomy.md").write_text(_TAXONOMY_MD, encoding="utf-8")
    (vault_path / "_meta" / "routing-policy.md").write_text(_ROUTING_POLICY_MD, encoding="utf-8")
    (vault_path / "_meta" / "changelog.md").write_text(_CHANGELOG_MD, encoding="utf-8")

    if not (vault_path / ".git").exists():
        init_repo(vault_path)

    console.print(f"[green]✓[/green] Vault initialized at [bold]{vault_path}[/bold]")
```

- [ ] **Step 4: Run tests — verify they pass**

Run:
```
uv run pytest tests/test_cli.py -v
```

Expected:
```
PASSED tests/test_cli.py::test_init_creates_vault_directory_structure
PASSED tests/test_cli.py::test_init_is_idempotent
2 passed
```

- [ ] **Step 5: Commit**

```
git add src/second_brain/cli.py tests/test_cli.py
git commit -m "feat: add CLI init command — creates vault structure and git repo"
```

---

## Task 7: CLI `status` + `note add`

**Files:**
- Modify: `src/second_brain/cli.py` (append `status` and `note_add` commands)
- Modify: `tests/test_cli.py` (append tests)

- [ ] **Step 1: Append failing tests to `tests/test_cli.py`**

```python
def test_status_vault_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from second_brain.cli import app

    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path / "nonexistent"))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1


def test_status_shows_vault_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from second_brain.cli import app

    vault = tmp_path / "vault"
    runner.invoke(app, ["init", str(vault)])
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(vault))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Wiki pages" in result.output
    assert "Inbox items" in result.output


def test_note_add_creates_wiki_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from second_brain.cli import app

    vault = tmp_path / "vault"
    runner.invoke(app, ["init", str(vault)])
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(vault))

    result = runner.invoke(
        app,
        ["note", "add", "wiki/concepts/python.md", "--title", "Python"],
    )
    assert result.exit_code == 0, result.output
    assert (vault / "wiki" / "concepts" / "python.md").exists()


def test_note_add_raw_path_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from second_brain.cli import app

    vault = tmp_path / "vault"
    runner.invoke(app, ["init", str(vault)])
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(vault))

    result = runner.invoke(
        app,
        ["note", "add", "raw/inbox/bad.md", "--title", "Bad"],
    )
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests — verify they fail**

Run:
```
uv run pytest tests/test_cli.py::test_status_vault_not_found -v
```

Expected: `FAILED` — `No such command 'status'`

- [ ] **Step 3: Append `status` and `note_add` to `src/second_brain/cli.py`**

Add after the `init` command function:

```python
@app.command()
def status() -> None:
    """Show vault health: page count and inbox size."""
    from .config import Settings

    settings = Settings()
    vault_path = settings.vault_path.expanduser().resolve()

    if not vault_path.exists():
        console.print(f"[red]✗[/red] Vault not found: [bold]{vault_path}[/bold]")
        raise typer.Exit(1)

    wiki_pages = list((vault_path / "wiki").rglob("*.md")) if (vault_path / "wiki").exists() else []
    inbox_items = (
        [f for f in (vault_path / "raw" / "inbox").iterdir() if f.is_file()]
        if (vault_path / "raw" / "inbox").exists()
        else []
    )

    console.print(f"[bold]Vault:[/bold] {vault_path}")
    console.print(f"  Wiki pages : {len(wiki_pages)}")
    console.print(f"  Inbox items: {len(inbox_items)}")


@note_app.command("add")
def note_add(
    path: str = typer.Argument(..., help="Relative path inside vault, e.g. wiki/concepts/foo.md"),
    title: str = typer.Option(..., "--title", "-t", help="Page title (required)"),
    page_type: str = typer.Option("concept", "--type", help="Page type (default: concept)"),
) -> None:
    """Create a new wiki page at the given vault-relative path."""
    from typing import cast

    from .config import Settings
    from .storage import Vault, WikiPage
    from .storage.frontmatter import PageType

    _valid_types = ("concept", "project", "person", "place", "ref", "map")
    if page_type not in _valid_types:
        console.print(
            f"[red]Invalid type[/red] '{page_type}'. Choose from: {', '.join(_valid_types)}"
        )
        raise typer.Exit(1)

    settings = Settings()
    vault = Vault(settings.vault_path)

    try:
        page = WikiPage(title=title, type=cast(PageType, page_type))
        written = vault.write_page(path, page)
        console.print(f"[green]✓[/green] Created [bold]{written}[/bold]")
    except RuntimeError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1) from exc
```

- [ ] **Step 4: Run tests — verify they pass**

Run:
```
uv run pytest tests/test_cli.py -v
```

Expected:
```
PASSED tests/test_cli.py::test_init_creates_vault_directory_structure
PASSED tests/test_cli.py::test_init_is_idempotent
PASSED tests/test_cli.py::test_status_vault_not_found
PASSED tests/test_cli.py::test_status_shows_vault_info
PASSED tests/test_cli.py::test_note_add_creates_wiki_page
PASSED tests/test_cli.py::test_note_add_raw_path_raises
6 passed
```

- [ ] **Step 5: Run full test suite**

Run:
```
uv run pytest -v
```

Expected: all 24 tests pass (18 from `test_vault.py` + 6 from `test_cli.py`).

- [ ] **Step 6: Run mypy on full source**

Run:
```
uv run mypy src/
```

Expected: `Success: no issues found in 6 source files`

- [ ] **Step 7: Commit**

```
git add src/second_brain/cli.py tests/test_cli.py
git commit -m "feat: add CLI status and note add commands"
```

---

## Task 8: Pre-commit + CI

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `.github/workflows/ci.yml`

There are no TDD steps here — these are configuration files. The verify step is running the tools manually.

- [ ] **Step 1: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        args: [--strict]
        additional_dependencies:
          - "pydantic>=2.7"
          - "pydantic-settings>=2.4"
          - "typer>=0.12"
          - "structlog>=24.1"
```

- [ ] **Step 2: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: ["main", "dev"]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v2
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: uv sync --dev

      - name: Run tests
        run: uv run pytest -v

      - name: Type check
        run: uv run mypy src/

      - name: Lint
        run: uv run ruff check src/
```

- [ ] **Step 3: Install pre-commit hooks**

Run:
```
uv run pre-commit install
```

Expected:
```
pre-commit installed at .git/hooks/pre-commit
```

- [ ] **Step 4: Run pre-commit on all files — verify clean**

Run:
```
uv run pre-commit run --all-files
```

Expected: all hooks pass (ruff, ruff-format, mypy). If ruff-format reformats any files, re-run until clean.

- [ ] **Step 5: Run full Acceptance Criteria checklist**

Run each command and verify:

```
uv run second-brain init ~/test-vault
```
Expected: all directories created, schema.md and taxonomy.md present, `.git` initialized.

```
uv run pytest
```
Expected: all tests pass.

```
uv run mypy src/
```
Expected: `Success: no issues found`.

Confirm raw/ guard works (covered by `test_write_to_raw_raises_runtime_error`).

Confirm git auto-commit works (covered by `test_write_page_auto_commits`).

- [ ] **Step 6: Commit**

```
git add .pre-commit-config.yaml .github/workflows/ci.yml
git commit -m "chore: add pre-commit hooks and GitHub Actions CI"
```

---

## Acceptance Criteria Checklist (SPEC §5.1)

- [ ] `uv run second-brain init ~/test-vault` — all vault directories created, `.git` initialized
- [ ] `uv run pytest` — all tests pass
- [ ] `uv run mypy src/` — no type errors (strict mode)
- [ ] Writing to `raw/` raises `RuntimeError` — verified by `test_write_to_raw_raises_runtime_error`
- [ ] Git auto-commit works — verified by `test_write_page_auto_commits`

### SPEC §Appendix A folder tree verification

After Phase 1 the project root must match:

```
metis-prime/
├── pyproject.toml
├── README.md
├── .gitignore
├── .pre-commit-config.yaml
├── .env.example
├── src/second_brain/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   └── storage/
│       ├── __init__.py
│       ├── vault.py
│       ├── frontmatter.py
│       └── git_ops.py
├── tests/
│   ├── conftest.py
│   ├── test_vault.py
│   └── test_cli.py
└── .github/workflows/ci.yml
```

Run `tree src/ tests/` (or `Get-ChildItem -Recurse src/, tests/ | Select-Object FullName` on Windows) to verify against this tree before calling Phase 1 complete.
