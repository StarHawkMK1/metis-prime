# Phase 3: LLM Wiki Pattern (Karpathy) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Karpathy's ingest/query/lint three operations as simple Python functions, yielding a minimal working LLM Wiki that can absorb markdown files, answer questions citing wiki pages, and report vault health.

**Architecture:** Three agent classes (`IngestAgent`, `QueryAgent`, `LintAgent`) under `src/second_brain/agents/`. Each uses the Phase 2 `LLMRouter` for LLM calls, `BM25Okapi` from `rank-bm25` for wiki retrieval, and the Phase 1 `Vault` for storage. Agents are independently testable via mocked `LLMRouter`. No LangGraph yet — that is Phase 5.

**Tech Stack:** `rank-bm25>=0.3` (BM25 retrieval, pure Python), stdlib `html.parser` (HTML stripping, no new dep), `pygit2` (already in deps, extended for file archival), Phase 2 `LLMRouter` + `Vault`

---

## File Structure

**New files:**
- `src/second_brain/agents/__init__.py`
- `src/second_brain/agents/extractors.py` — `extract_text(path) -> str` by file type
- `src/second_brain/agents/search.py` — `WikiSearcher` + `SearchResult`
- `src/second_brain/agents/ingest.py` — `IngestAgent`, `IngestResult`, `IngestDecision`
- `src/second_brain/agents/query.py` — `QueryAgent`, `QueryResult`
- `src/second_brain/agents/lint.py` — `LintAgent`, `LintReport`, `LintIssue`
- `tests/test_extractors.py`
- `tests/test_wiki_search.py`
- `tests/test_ingest.py`
- `tests/test_query.py`
- `tests/test_lint.py`
- `tests/test_agents_cli.py`

**Modified files:**
- `pyproject.toml` — add `rank-bm25`, mypy override for `rank_bm25`
- `src/second_brain/storage/git_ops.py` — extend `auto_commit` with `removed_paths`
- `src/second_brain/storage/vault.py` — add `archive_raw`, `read_raw_text`, `page_exists`
- `src/second_brain/storage/__init__.py` — no change needed
- `src/second_brain/cli.py` — add `ingest`, `query`, `lint` top-level commands

---

## Task 1: Vault Extensions

**Files:**
- Modify: `src/second_brain/storage/git_ops.py`
- Modify: `src/second_brain/storage/vault.py`
- Test: `tests/test_vault.py` (append to existing file)

### Context

`auto_commit` currently only stages additions. Archiving a raw source requires staging a deletion (`raw/inbox/X`) and an addition (`raw/archived/X`) in one commit. We extend `auto_commit` with an optional `removed_paths` parameter. We also add three helpers to `Vault`.

- [ ] **Step 1: Write failing tests for vault extensions**

Append to `tests/test_vault.py`:

```python
def test_vault_read_raw_text(tmp_vault: Path) -> None:
    source = tmp_vault / "raw" / "inbox" / "note.md"
    source.write_text("# Hello\nContent here.", encoding="utf-8")
    vault = Vault(tmp_vault)
    text = vault.read_raw_text("raw/inbox/note.md")
    assert "Content here." in text


def test_vault_page_exists_true(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page("wiki/concepts/existing.md", WikiPage(title="Existing", type="concept"))
    assert vault.page_exists("wiki/concepts/existing.md") is True


def test_vault_page_exists_false(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    assert vault.page_exists("wiki/concepts/ghost.md") is False


def test_vault_archive_raw_moves_file(tmp_vault: Path) -> None:
    source = tmp_vault / "raw" / "inbox" / "clip.md"
    source.write_text("# Clip\nsome content", encoding="utf-8")
    # Stage the new file so git knows about it
    import pygit2
    repo = pygit2.Repository(str(tmp_vault))
    idx = repo.index
    idx.read()
    idx.add("raw/inbox/clip.md")
    idx.write()
    sig = pygit2.Signature("Test", "test@test.com")
    tree = idx.write_tree()
    repo.create_commit("refs/heads/main", sig, sig, "add raw file", tree, [repo.head.target])

    vault = Vault(tmp_vault)
    archived = vault.archive_raw("raw/inbox/clip.md")
    assert archived.exists()
    assert "archived" in str(archived)
    assert not source.exists()


def test_vault_archive_raw_commits(tmp_vault: Path) -> None:
    source = tmp_vault / "raw" / "inbox" / "note2.md"
    source.write_text("content", encoding="utf-8")
    import pygit2
    repo = pygit2.Repository(str(tmp_vault))
    idx = repo.index
    idx.read()
    idx.add("raw/inbox/note2.md")
    idx.write()
    sig = pygit2.Signature("Test", "test@test.com")
    tree = idx.write_tree()
    repo.create_commit("refs/heads/main", sig, sig, "add raw2", tree, [repo.head.target])

    vault = Vault(tmp_vault)
    vault.archive_raw("raw/inbox/note2.md")
    repo2 = pygit2.Repository(str(tmp_vault))
    commits = list(repo2.walk(repo2.head.target))
    assert any("archive:" in c.message for c in commits)


def test_auto_commit_with_removed_paths(tmp_path: Path) -> None:
    from second_brain.storage.git_ops import auto_commit, init_repo
    target = tmp_path / "repo"
    target.mkdir()
    init_repo(target)
    # add a file so we can remove it
    f = target / "file.md"
    f.write_text("hello", encoding="utf-8")
    auto_commit(target, "add file", [f])
    # now rename (delete original, add at new location)
    dst = target / "moved.md"
    f.rename(dst)
    auto_commit(target, "move file", [dst], removed_paths=[f])
    import pygit2
    repo = pygit2.Repository(str(target))
    commits = list(repo.walk(repo.head.target))
    assert commits[0].message == "move file"
    # verify old path not in tree, new path in tree
    tree = repo.head.peel(pygit2.Tree)
    names = [entry.name for entry in tree]
    assert "moved.md" in names
    assert "file.md" not in names
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_vault.py -k "archive or page_exists or raw_text or removed_paths" -v
```

Expected: multiple FAILs (methods do not exist yet).

- [ ] **Step 3: Extend `auto_commit` in `git_ops.py`**

Replace the entire `auto_commit` function in `src/second_brain/storage/git_ops.py`:

```python
def auto_commit(
    repo_path: Path,
    message: str,
    paths: list[Path],
    removed_paths: list[Path] | None = None,
) -> None:
    """Stage additions and optional removals, then commit. No-op if nothing to stage."""
    if not paths and not removed_paths:
        return
    repo = pygit2.Repository(str(repo_path))
    index = repo.index
    index.read()
    for p in paths:
        rel = str(p.relative_to(repo_path)).replace("\\", "/")
        index.add(rel)
    for p in (removed_paths or []):
        rel = str(p.relative_to(repo_path)).replace("\\", "/")
        index.remove(rel)
    index.write()
    sig = _get_signature(repo)
    tree = index.write_tree()
    parent_ids: list[Any] = [] if repo.head_is_unborn else [repo.head.target]
    repo.create_commit("refs/heads/main", sig, sig, message, tree, parent_ids)
```

- [ ] **Step 4: Add three methods to `Vault` in `vault.py`**

Append to the `Vault` class (before the last line of the file):

```python
    def read_raw_text(self, relative_path: str) -> str:
        """Read a raw source file as plain text. Does not guard writes."""
        return (self.path / relative_path).read_text(encoding="utf-8")

    def page_exists(self, relative_path: str) -> bool:
        """Return True if a vault-relative page path exists on disk."""
        return (self.path / relative_path).exists()

    def archive_raw(self, relative_path: str) -> Path:
        """Move a raw file to raw/archived/ and commit the change."""
        src = self.path / relative_path
        if not src.exists():
            raise FileNotFoundError(f"Raw file not found: {src}")
        dst_dir = self.path / "raw" / "archived"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        src.rename(dst)
        auto_commit(
            self.path,
            f"archive: {src.name}",
            [dst],
            removed_paths=[src],
        )
        return dst
```

Also add the `auto_commit` import at the top of `vault.py` — it's already imported, so no change needed there. Verify the existing import line reads:
```python
from .git_ops import auto_commit
```

- [ ] **Step 5: Run tests to verify they pass**

```
uv run pytest tests/test_vault.py -v
```

Expected: ALL PASS (including previous tests — backward compatible).

- [ ] **Step 6: Commit**

```
git add src/second_brain/storage/git_ops.py src/second_brain/storage/vault.py tests/test_vault.py
git commit -m "feat: extend auto_commit for removals; add Vault.archive_raw, page_exists, read_raw_text"
```

---

## Task 2: Agents Package + File Extractors

**Files:**
- Create: `src/second_brain/agents/__init__.py`
- Create: `src/second_brain/agents/extractors.py`
- Create: `tests/test_extractors.py`

### Context

The ingest agent needs to read source files as plain text regardless of format. Phase 3 supports `.md`/`.txt` natively and `.html` via stdlib stripping. PDF and audio raise `NotImplementedError` with a clear message (hooks for future phases).

- [ ] **Step 1: Write failing tests**

Create `tests/test_extractors.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from second_brain.agents.extractors import extract_text


def test_extract_markdown(tmp_path: Path) -> None:
    f = tmp_path / "note.md"
    f.write_text("# Title\n\nBody text.", encoding="utf-8")
    assert "Body text." in extract_text(f)


def test_extract_txt(tmp_path: Path) -> None:
    f = tmp_path / "note.txt"
    f.write_text("Plain text content.", encoding="utf-8")
    assert "Plain text content." in extract_text(f)


def test_extract_html_strips_tags(tmp_path: Path) -> None:
    f = tmp_path / "page.html"
    f.write_text("<html><body><h1>Title</h1><p>Para text.</p></body></html>", encoding="utf-8")
    result = extract_text(f)
    assert "Title" in result
    assert "Para text." in result
    assert "<h1>" not in result


def test_extract_pdf_not_implemented(tmp_path: Path) -> None:
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4")
    with pytest.raises(NotImplementedError, match="PDF"):
        extract_text(f)


def test_extract_audio_not_implemented(tmp_path: Path) -> None:
    f = tmp_path / "voice.m4a"
    f.write_bytes(b"fakeaudio")
    with pytest.raises(NotImplementedError, match="[Aa]udio"):
        extract_text(f)


def test_extract_unknown_raises(tmp_path: Path) -> None:
    f = tmp_path / "data.xyz"
    f.write_text("content", encoding="utf-8")
    with pytest.raises(ValueError, match=".xyz"):
        extract_text(f)
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_extractors.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'second_brain.agents'`

- [ ] **Step 3: Create `src/second_brain/agents/__init__.py`**

Create as an **empty file** — no imports yet. The agent modules (`ingest`, `query`, `lint`) don't exist until Tasks 4–6; importing them here would crash every test that touches `second_brain.agents`.

```python
```

Python treats this as a valid package. Re-exports are added in Task 7 Step 1 after all agent modules exist.

- [ ] **Step 4: Create `src/second_brain/agents/extractors.py`**

```python
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def extract_text(path: Path) -> str:
    """Extract plain text from a source file.

    Supported: .md, .txt (native), .html (tag-stripped).
    Raises NotImplementedError for .pdf and audio types.
    Raises ValueError for unrecognized extensions.
    """
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".html":
        parser = _TextExtractor()
        parser.feed(path.read_text(encoding="utf-8"))
        return parser.get_text()
    if suffix == ".pdf":
        raise NotImplementedError(
            f"PDF extraction not supported in Phase 3: {path.name}. "
            "Install 'pypdf' and extend extractors.py."
        )
    if suffix in {".m4a", ".wav", ".mp3", ".ogg", ".flac"}:
        raise NotImplementedError(
            f"Audio transcription not supported in Phase 3: {path.name}. "
            "Install 'faster-whisper' and extend extractors.py."
        )
    raise ValueError(f"Unsupported file type '{suffix}': {path.name}")
```

- [ ] **Step 5: Run tests to verify they pass**

```
uv run pytest tests/test_extractors.py -v
```

Expected: ALL 6 PASS.

- [ ] **Step 6: Commit**

```
git add src/second_brain/agents/__init__.py src/second_brain/agents/extractors.py tests/test_extractors.py
git commit -m "feat: add agents package with file text extractor"
```

---

## Task 3: BM25 Wiki Search

**Files:**
- Modify: `pyproject.toml`
- Create: `src/second_brain/agents/search.py`
- Create: `tests/test_wiki_search.py`

### Context

Both `IngestAgent` (find similar pages to avoid duplication) and `QueryAgent` (retrieve relevant pages) use BM25 keyword search. `rank-bm25` is pure Python with no C extensions.

- [ ] **Step 1: Add `rank-bm25` to `pyproject.toml`**

In `pyproject.toml`, update the `dependencies` list and `mypy.overrides`:

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
    "rank-bm25>=0.3",
]
```

And add `rank_bm25` to the existing mypy overrides section:

```toml
[[tool.mypy.overrides]]
module = ["frontmatter", "pygit2", "rank_bm25"]
ignore_missing_imports = true
```

Then install:
```
uv sync
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_wiki_search.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from second_brain.agents.search import SearchResult, WikiSearcher
from second_brain.storage import Vault, WikiPage


@pytest.fixture()
def wiki_vault(tmp_vault: Path) -> Vault:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/machine-learning.md",
        WikiPage(title="Machine Learning", type="concept", body="ML is a subset of AI. Neural networks."),
    )
    vault.write_page(
        "wiki/concepts/python.md",
        WikiPage(title="Python", type="concept", body="Python is a programming language used in data science."),
    )
    vault.write_page(
        "wiki/concepts/databases.md",
        WikiPage(title="Databases", type="concept", body="Relational databases store data in tables."),
    )
    return vault


def test_search_returns_results(wiki_vault: Vault) -> None:
    searcher = WikiSearcher(wiki_vault)
    results = searcher.search("machine learning neural")
    assert len(results) >= 1
    assert all(isinstance(r, SearchResult) for r in results)


def test_search_relevant_first(wiki_vault: Vault) -> None:
    searcher = WikiSearcher(wiki_vault)
    results = searcher.search("machine learning neural networks")
    assert len(results) >= 1
    # machine-learning page should rank highest
    assert "machine-learning" in results[0].relative_path


def test_search_top_k_limit(wiki_vault: Vault) -> None:
    searcher = WikiSearcher(wiki_vault)
    results = searcher.search("data", top_k=2)
    assert len(results) <= 2


def test_search_empty_vault(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    searcher = WikiSearcher(vault)
    results = searcher.search("anything")
    assert results == []


def test_search_result_fields(wiki_vault: Vault) -> None:
    searcher = WikiSearcher(wiki_vault)
    results = searcher.search("python programming")
    assert len(results) >= 1
    r = results[0]
    assert r.path.exists()
    assert r.score > 0
    assert "wiki/" in r.relative_path
    assert len(r.content) > 0
```

- [ ] **Step 3: Run tests to verify they fail**

```
uv run pytest tests/test_wiki_search.py -v
```

Expected: FAIL — `ImportError: cannot import name 'WikiSearcher'`

- [ ] **Step 4: Create `src/second_brain/agents/search.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from ..storage.vault import Vault


@dataclass
class SearchResult:
    path: Path
    relative_path: str
    content: str
    score: float


class WikiSearcher:
    """BM25-based full-text search over wiki pages."""

    def __init__(self, vault: Vault) -> None:
        self._vault = vault

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Return up to top_k wiki pages most relevant to query."""
        pages = self._vault.list_pages()
        if not pages:
            return []

        contents: list[str] = []
        for p in pages:
            try:
                contents.append(p.read_text(encoding="utf-8"))
            except OSError:
                contents.append("")

        tokenized = [doc.lower().split() for doc in contents]
        bm25: Any = BM25Okapi(tokenized)
        scores: Any = bm25.get_scores(query.lower().split())

        ranked = sorted(
            zip(scores, pages, contents),
            key=lambda x: float(x[0]),
            reverse=True,
        )

        results: list[SearchResult] = []
        for score, path, content in ranked[:top_k]:
            score_f = float(score)
            if score_f <= 0:
                continue
            rel = str(path.relative_to(self._vault.path)).replace("\\", "/")
            results.append(
                SearchResult(path=path, relative_path=rel, content=content, score=score_f)
            )
        return results
```

- [ ] **Step 5: Run tests to verify they pass**

```
uv run pytest tests/test_wiki_search.py -v
```

Expected: ALL 5 PASS.

- [ ] **Step 6: Commit**

```
git add pyproject.toml uv.lock src/second_brain/agents/search.py tests/test_wiki_search.py
git commit -m "feat: add BM25 wiki search (rank-bm25)"
```

---

## Task 4: Ingest Agent

**Files:**
- Create: `src/second_brain/agents/ingest.py`
- Create: `tests/test_ingest.py`

### Context

`IngestAgent.run(source_path)` takes a vault-relative path in `raw/`, calls the LLM (mocked in tests) to get a structured ingest decision, writes the wiki page, then archives the source. The LLM response is JSON; a Pydantic model validates it.

- [ ] **Step 1: Write failing tests**

Create `tests/test_ingest.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from second_brain.agents.ingest import IngestAgent, IngestResult
from second_brain.storage import Vault, WikiPage


def _make_llm_response(
    decision: str = "create",
    title: str = "Test Concept",
    page_type: str = "concept",
    body: str = "A one-sentence definition.\n\nMore detail here.",
    target_page: str = "",
) -> str:
    return json.dumps(
        {
            "decision": decision,
            "title": title,
            "type": page_type,
            "body": body,
            "sources": ["raw/inbox/source.md"],
            "provenance": {"extracted": 70, "inferred": 25, "ambiguous": 5},
            "wikilinks": [],
            "tags": ["ai"],
            "target_page": target_page,
        }
    )


def test_ingest_creates_new_page(tmp_vault: Path) -> None:
    source = tmp_vault / "raw" / "inbox" / "source.md"
    source.write_text("# AI Basics\n\nArticle about AI.", encoding="utf-8")
    _stage_file(tmp_vault, "raw/inbox/source.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _make_llm_response()

    vault = Vault(tmp_vault)
    agent = IngestAgent(vault=vault, router=mock_router)
    result = agent.run("raw/inbox/source.md")

    assert result.decision == "create"
    assert result.wiki_path is not None
    assert vault.page_exists(result.wiki_path)


def test_ingest_archives_source(tmp_vault: Path) -> None:
    source = tmp_vault / "raw" / "inbox" / "clip.md"
    source.write_text("# Clip\n\nSome content.", encoding="utf-8")
    _stage_file(tmp_vault, "raw/inbox/clip.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _make_llm_response(title="Clip Content")

    vault = Vault(tmp_vault)
    result = IngestAgent(vault=vault, router=mock_router).run("raw/inbox/clip.md")

    assert not source.exists()
    assert result.archived_path.exists()
    assert "archived" in str(result.archived_path)


def test_ingest_commits_to_git(tmp_vault: Path) -> None:
    import pygit2

    source = tmp_vault / "raw" / "inbox" / "note.md"
    source.write_text("# Note\n\nContent.", encoding="utf-8")
    _stage_file(tmp_vault, "raw/inbox/note.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _make_llm_response(title="Note Concept")

    vault = Vault(tmp_vault)
    IngestAgent(vault=vault, router=mock_router).run("raw/inbox/note.md")

    repo = pygit2.Repository(str(tmp_vault))
    messages = [c.message for c in repo.walk(repo.head.target)]
    assert any("ingest:" in m for m in messages)


def test_ingest_skip_decision_no_wiki_page(tmp_vault: Path) -> None:
    source = tmp_vault / "raw" / "inbox" / "dup.md"
    source.write_text("# Dup\n\nDuplicate content.", encoding="utf-8")
    _stage_file(tmp_vault, "raw/inbox/dup.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _make_llm_response(decision="skip", title="Dup")

    vault = Vault(tmp_vault)
    result = IngestAgent(vault=vault, router=mock_router).run("raw/inbox/dup.md")

    assert result.decision == "skip"
    assert result.wiki_path is None
    # source still archived even on skip
    assert result.archived_path.exists()


def test_ingest_merge_decision_updates_page(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    existing = vault.write_page(
        "wiki/concepts/ai.md",
        WikiPage(title="Artificial Intelligence", type="concept", body="Initial content."),
    )
    assert existing.exists()

    source = tmp_vault / "raw" / "inbox" / "ai-update.md"
    source.write_text("# AI Update\n\nNew info about AI.", encoding="utf-8")
    _stage_file(tmp_vault, "raw/inbox/ai-update.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = _make_llm_response(
        decision="merge",
        title="Artificial Intelligence",
        body="Initial content.\n\nNew info about AI.",
        target_page="ai",
    )

    result = IngestAgent(vault=vault, router=mock_router).run("raw/inbox/ai-update.md")
    assert result.decision == "merge"
    assert result.wiki_path == "wiki/concepts/ai.md"
    updated = vault.read_page("wiki/concepts/ai.md")
    assert "New info about AI." in updated.body


def test_ingest_invalid_json_raises(tmp_vault: Path) -> None:
    from second_brain.agents.ingest import IngestError

    source = tmp_vault / "raw" / "inbox" / "bad.md"
    source.write_text("content", encoding="utf-8")
    _stage_file(tmp_vault, "raw/inbox/bad.md")

    mock_router = MagicMock()
    mock_router.complete.return_value = "NOT VALID JSON AT ALL"

    vault = Vault(tmp_vault)
    with pytest.raises(IngestError, match="[Ff]ailed to parse"):
        IngestAgent(vault=vault, router=mock_router).run("raw/inbox/bad.md")


# ── helpers ──────────────────────────────────────────────────────────────────

def _stage_file(vault_path: Path, rel: str) -> None:
    """Stage a newly written raw file so pygit2 can track its removal."""
    import pygit2

    repo = pygit2.Repository(str(vault_path))
    idx = repo.index
    idx.read()
    idx.add(rel)
    idx.write()
    sig = pygit2.Signature("Test", "t@t.com")
    tree = idx.write_tree()
    repo.create_commit("refs/heads/main", sig, sig, f"add {rel}", tree, [repo.head.target])
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_ingest.py -v
```

Expected: FAIL — `ImportError: cannot import name 'IngestAgent'`

- [ ] **Step 3: Create `src/second_brain/agents/ingest.py`**

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field, ValidationError

from ..llm.router import LLMRouter
from ..llm.types import Sensitivity
from ..storage.frontmatter import PageType, ProvenanceBreakdown, WikiPage
from ..storage.vault import Vault
from .extractors import extract_text
from .search import WikiSearcher

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a wiki maintainer for a personal second brain knowledge base.
Analyze the incoming source material and decide how to incorporate it into the wiki.

You will receive:
1. The source text
2. A list of similar existing wiki pages (for deduplication context)

Respond with ONLY a JSON object — no markdown fences, no explanation:

{
  "decision": "create" | "merge" | "skip",
  "title": "Title Case Title",
  "type": "concept" | "project" | "person" | "place" | "ref" | "map",
  "body": "Markdown body (no frontmatter). First line = one-sentence definition.",
  "provenance": {"extracted": <0-100>, "inferred": <0-100>, "ambiguous": <0-100>},
  "wikilinks": ["stem-of-page-1", "stem-of-page-2"],
  "tags": ["tag1"],
  "target_page": "stem-of-existing-page-to-merge-into"
}

Decision rules:
- "create" — topic is new, no sufficiently similar wiki page exists.
- "merge"  — a very similar page already exists; merge this content into it.
             Set target_page to the stem (filename without extension) of that page.
- "skip"   — source adds nothing new to the wiki.

Constraints:
- provenance values must sum to exactly 100.
- wikilinks: only stems of pages shown in the "Existing similar pages" section.
- target_page: only required for "merge"; set to empty string otherwise.
- Return ONLY the JSON object.
"""


class _IngestDecision(BaseModel):
    decision: Literal["create", "merge", "skip"]
    title: str
    type: PageType
    body: str
    provenance: ProvenanceBreakdown
    wikilinks: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    target_page: str = ""


@dataclass
class IngestResult:
    decision: str
    wiki_path: str | None
    archived_path: Path
    source_name: str


class IngestError(Exception):
    """Raised when ingest fails (e.g. invalid LLM response)."""


class IngestAgent:
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

    def run(self, source_rel_path: str, sensitivity: Sensitivity | None = None) -> IngestResult:
        """Ingest a single raw source file into the wiki."""
        sens = sensitivity or self._sensitivity
        source_path = self._vault.path / source_rel_path

        raw_text = extract_text(source_path)
        similar = self._searcher.search(raw_text[:2000], top_k=3)

        similar_context = ""
        if similar:
            parts = []
            for r in similar:
                parts.append(f"[[{r.path.stem}]] (score: {r.score:.2f})\n{r.content[:400]}")
            similar_context = "\n\n---\n\n".join(parts)

        user_msg = (
            f"Source file: {source_path.name}\n\n"
            f"Source text:\n---\n{raw_text[:3000]}\n---\n\n"
        )
        if similar_context:
            user_msg += f"Existing similar pages ({len(similar)} found):\n\n{similar_context}\n\n"
        else:
            user_msg += "Existing similar pages: none\n\n"
        user_msg += "Make your decision."

        raw_response = self._router.complete(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            task_type="ingest_summary",
            sensitivity=sens,
        )

        decision = _parse_decision(raw_response)

        wiki_path: str | None = None
        if decision.decision == "create":
            wiki_path = _default_wiki_path(decision.title)
            page = WikiPage(
                title=decision.title,
                type=decision.type,
                body=_body_with_related(decision.body, decision.wikilinks),
                tags=decision.tags,
                sources=[source_rel_path],
                provenance=decision.provenance,
            )
            self._vault.write_page(wiki_path, page)
            log.info("ingest.created", page=wiki_path)
        elif decision.decision == "merge":
            wiki_path = _resolve_merge_target(decision.target_page, self._vault)
            if wiki_path:
                existing = self._vault.read_page(wiki_path)
                merged_body = existing.body.rstrip() + "\n\n" + decision.body
                merged_sources = list(dict.fromkeys(existing.sources + [source_rel_path]))
                updated = existing.model_copy(
                    update={
                        "body": _body_with_related(merged_body, decision.wikilinks),
                        "sources": merged_sources,
                    }
                )
                self._vault.write_page(wiki_path, updated)
                log.info("ingest.merged", page=wiki_path)
            else:
                wiki_path = _default_wiki_path(decision.title)
                page = WikiPage(
                    title=decision.title,
                    type=decision.type,
                    body=_body_with_related(decision.body, decision.wikilinks),
                    tags=decision.tags,
                    sources=[source_rel_path],
                    provenance=decision.provenance,
                )
                self._vault.write_page(wiki_path, page)
                log.info("ingest.merge_fallback_created", page=wiki_path)
        else:
            log.info("ingest.skipped", source=source_rel_path)

        archived = self._vault.archive_raw(source_rel_path)
        return IngestResult(
            decision=decision.decision,
            wiki_path=wiki_path,
            archived_path=archived,
            source_name=source_path.name,
        )


# ── helpers ──────────────────────────────────────────────────────────────────

def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text[text.find("\n") + 1 :]
        end = text.rfind("```")
        if end != -1:
            text = text[:end]
    return text.strip()


def _parse_decision(raw: str) -> _IngestDecision:
    cleaned = _strip_json_fences(raw)
    try:
        data: Any = json.loads(cleaned)
        return _IngestDecision.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise IngestError(f"Failed to parse LLM response as IngestDecision: {exc}") from exc


def _default_wiki_path(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"wiki/concepts/{slug}.md"


def _resolve_merge_target(stem: str, vault: Vault) -> str | None:
    """Find the relative vault path of a wiki page by its stem."""
    if not stem:
        return None
    for page_path in vault.list_pages():
        if page_path.stem == stem:
            return str(page_path.relative_to(vault.path)).replace("\\", "/")
    return None


def _body_with_related(body: str, wikilinks: list[str]) -> str:
    if not wikilinks:
        return body
    links = "\n".join(f"[[{stem}]]" for stem in wikilinks)
    return body.rstrip() + "\n\n## Related\n\n" + links
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_ingest.py -v
```

Expected: ALL 6 PASS.

- [ ] **Step 5: Commit**

```
git add src/second_brain/agents/ingest.py tests/test_ingest.py
git commit -m "feat: add IngestAgent with LLM-driven create/merge/skip decisions"
```

---

## Task 5: Query Agent

**Files:**
- Create: `src/second_brain/agents/query.py`
- Create: `tests/test_query.py`

### Context

`QueryAgent.ask(question)` retrieves the top-K relevant wiki pages via BM25, then calls the LLM to synthesize an answer with source citations. The LLM response is free-form text (no JSON parsing needed).

- [ ] **Step 1: Write failing tests**

Create `tests/test_query.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from second_brain.agents.query import QueryAgent, QueryResult
from second_brain.storage import Vault, WikiPage


@pytest.fixture()
def wiki_vault(tmp_vault: Path) -> Vault:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/transformers.md",
        WikiPage(
            title="Transformers",
            type="concept",
            body="Transformers are a neural network architecture using self-attention.",
        ),
    )
    vault.write_page(
        "wiki/concepts/bert.md",
        WikiPage(
            title="BERT",
            type="concept",
            body="BERT is a pre-trained transformer model for NLP tasks.",
        ),
    )
    return vault


def test_query_returns_answer(wiki_vault: Vault) -> None:
    mock_router = MagicMock()
    mock_router.complete.return_value = (
        "Transformers use self-attention [[transformers]]. "
        "BERT is a specific model [[bert]]."
    )
    agent = QueryAgent(vault=wiki_vault, router=mock_router)
    result = agent.ask("What are transformers?")
    assert isinstance(result, QueryResult)
    assert len(result.answer) > 0


def test_query_cites_sources(wiki_vault: Vault) -> None:
    mock_router = MagicMock()
    mock_router.complete.return_value = "Transformers use attention mechanisms."
    agent = QueryAgent(vault=wiki_vault, router=mock_router)
    result = agent.ask("explain transformers self-attention")
    assert len(result.sources) >= 1


def test_query_empty_wiki(tmp_vault: Path) -> None:
    mock_router = MagicMock()
    mock_router.complete.return_value = "I don't have enough information."
    vault = Vault(tmp_vault)
    agent = QueryAgent(vault=vault, router=mock_router)
    result = agent.ask("anything?")
    assert isinstance(result.answer, str)
    assert result.sources == []


def test_query_calls_llm_with_context(wiki_vault: Vault) -> None:
    mock_router = MagicMock()
    mock_router.complete.return_value = "Answer with citations."
    agent = QueryAgent(vault=wiki_vault, router=mock_router)
    agent.ask("transformer architecture")
    # verify LLM was called with a user message containing wiki context
    call_args = mock_router.complete.call_args
    messages = call_args[0][0]
    user_content = messages[-1]["content"]
    assert "transformer" in user_content.lower() or "bert" in user_content.lower()


def test_query_uses_synthesis_complex_task_type(wiki_vault: Vault) -> None:
    mock_router = MagicMock()
    mock_router.complete.return_value = "Some answer."
    agent = QueryAgent(vault=wiki_vault, router=mock_router)
    agent.ask("anything")
    call_kwargs = mock_router.complete.call_args[1]
    assert call_kwargs["task_type"] == "synthesis_complex"
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_query.py -v
```

Expected: FAIL — `ImportError: cannot import name 'QueryAgent'`

- [ ] **Step 3: Create `src/second_brain/agents/query.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import structlog

from ..llm.router import LLMRouter
from ..llm.types import Sensitivity
from ..storage.vault import Vault
from .search import WikiSearcher

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a knowledgeable assistant with access to the user's personal wiki.
Answer questions concisely, citing the wiki pages you used.

Use inline citation format: [[page-stem]] after each claim.
If no wiki pages are relevant, say so clearly.
"""


@dataclass
class QueryResult:
    answer: str
    sources: list[str] = field(default_factory=list)


class QueryAgent:
    def __init__(
        self,
        vault: Vault,
        router: LLMRouter | None = None,
        top_k: int = 5,
        sensitivity: Sensitivity = "normal",
    ) -> None:
        self._vault = vault
        self._router = router or LLMRouter()
        self._top_k = top_k
        self._sensitivity = sensitivity
        self._searcher = WikiSearcher(vault)

    def ask(self, question: str, sensitivity: Sensitivity | None = None) -> QueryResult:
        """Answer a natural language question using the wiki as context."""
        sens = sensitivity or self._sensitivity
        similar = self._searcher.search(question, top_k=self._top_k)

        if not similar:
            answer = self._router.complete(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"Question: {question}\n\nWiki context: none"},
                ],
                task_type="synthesis_complex",
                sensitivity=sens,
            )
            return QueryResult(answer=answer, sources=[])

        context_parts = []
        for r in similar:
            context_parts.append(f"[[{r.path.stem}]] (relevance: {r.score:.2f})\n{r.content[:800]}")

        user_msg = (
            f"Question: {question}\n\n"
            f"Relevant wiki pages:\n\n"
            + "\n\n---\n\n".join(context_parts)
        )

        answer = self._router.complete(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            task_type="synthesis_complex",
            sensitivity=sens,
        )

        sources = [r.relative_path for r in similar]
        log.info("query.answered", question=question[:80], sources_used=len(sources))
        return QueryResult(answer=answer, sources=sources)
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_query.py -v
```

Expected: ALL 5 PASS.

- [ ] **Step 5: Commit**

```
git add src/second_brain/agents/query.py tests/test_query.py
git commit -m "feat: add QueryAgent with BM25 retrieval and LLM synthesis"
```

---

## Task 6: Lint Agent

**Files:**
- Create: `src/second_brain/agents/lint.py`
- Create: `tests/test_lint.py`

### Context

`LintAgent.run()` scans all wiki pages for: broken wikilinks, orphan pages, stale drafts (>30 days + status=draft), frontmatter validation failures, and provenance drift (inferred>70%). No LLM needed — pure static analysis. Writes `journal/lint-YYYY-MM-DD.md`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_lint.py`:

```python
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from second_brain.agents.lint import LintAgent, LintIssue, LintReport
from second_brain.storage import Vault, WikiPage
from second_brain.storage.frontmatter import ProvenanceBreakdown


def test_lint_detects_broken_wikilink(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/page-a.md",
        WikiPage(title="Page A", type="concept", body="See [[nonexistent-page]] for details."),
    )
    report = LintAgent(vault).run()
    assert any(i.kind == "broken_wikilink" for i in report.issues)


def test_lint_clean_page_no_broken_link(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/alpha.md",
        WikiPage(title="Alpha", type="concept", body="No wikilinks here."),
    )
    report = LintAgent(vault).run()
    broken = [i for i in report.issues if i.kind == "broken_wikilink"]
    assert broken == []


def test_lint_detects_orphan_page(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/lonely.md",
        WikiPage(title="Lonely", type="concept", body="No links in or out."),
    )
    report = LintAgent(vault).run()
    assert any(i.kind == "orphan" for i in report.issues)


def test_lint_linked_pages_not_orphan(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/hub.md",
        WikiPage(title="Hub", type="concept", body="See [[spoke]] for more."),
    )
    vault.write_page(
        "wiki/concepts/spoke.md",
        WikiPage(title="Spoke", type="concept", body="Back to [[hub]]."),
    )
    report = LintAgent(vault).run()
    orphans = [i for i in report.issues if i.kind == "orphan"]
    orphan_pages = {i.page for i in orphans}
    assert "wiki/concepts/hub.md" not in orphan_pages
    assert "wiki/concepts/spoke.md" not in orphan_pages


def test_lint_detects_stale_draft(tmp_vault: Path) -> None:
    old_date = date.today() - timedelta(days=45)
    # Vault.write_page unconditionally sets `updated = date.today()`, which
    # would make the page look fresh. Write directly to disk instead.
    page = WikiPage(
        title="Stale",
        type="concept",
        status="draft",
        body="Old content.",
        created=old_date,
        updated=old_date,
    )
    (tmp_vault / "wiki" / "concepts" / "stale.md").write_text(
        page.to_markdown(), encoding="utf-8"
    )
    vault = Vault(tmp_vault)
    report = LintAgent(vault).run()
    assert any(i.kind == "stale_draft" for i in report.issues)


def test_lint_active_page_not_stale(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/fresh.md",
        WikiPage(title="Fresh", type="concept", status="active", body="Up to date."),
    )
    report = LintAgent(vault).run()
    stale = [i for i in report.issues if i.kind == "stale_draft"]
    assert stale == []


def test_lint_detects_provenance_drift(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/speculative.md",
        WikiPage(
            title="Speculative",
            type="concept",
            body="Mostly inferred.",
            provenance=ProvenanceBreakdown(extracted=20, inferred=75, ambiguous=5),
        ),
    )
    report = LintAgent(vault).run()
    assert any(i.kind == "provenance_drift" for i in report.issues)


def test_lint_empty_vault_no_issues(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    report = LintAgent(vault).run()
    assert report.issues == []


def test_lint_writes_report_file(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_page(
        "wiki/concepts/x.md",
        WikiPage(title="X", type="concept", body="[[ghost]] link."),
    )
    report = LintAgent(vault).run()
    journal_dir = tmp_vault / "journal"
    assert journal_dir.exists()
    reports = list(journal_dir.glob("lint-*.md"))
    assert len(reports) >= 1
    content = reports[0].read_text(encoding="utf-8")
    assert "broken_wikilink" in content or "Broken" in content
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_lint.py -v
```

Expected: FAIL — `ImportError: cannot import name 'LintAgent'`

- [ ] **Step 3: Create `src/second_brain/agents/lint.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import structlog

from ..storage.frontmatter import WikiPage
from ..storage.vault import Vault

log = structlog.get_logger(__name__)

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]")
_STALE_DAYS = 30


def _extract_wikilinks(text: str) -> list[str]:
    """Return all wikilink targets (stem or path) from markdown text."""
    return _WIKILINK_RE.findall(text)


def _stems(vault: Vault) -> dict[str, str]:
    """Map page stem → vault-relative path for all wiki pages."""
    result: dict[str, str] = {}
    for p in vault.list_pages():
        rel = str(p.relative_to(vault.path)).replace("\\", "/")
        result[p.stem] = rel
    return result


@dataclass
class LintIssue:
    kind: str  # broken_wikilink | orphan | stale_draft | provenance_drift
    page: str  # vault-relative path
    detail: str = ""


@dataclass
class LintReport:
    generated: date = field(default_factory=date.today)
    issues: list[LintIssue] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"# Lint Report — {self.generated}", ""]
        if not self.issues:
            lines.append("No issues found. Vault is healthy.")
            return "\n".join(lines)
        by_kind: dict[str, list[LintIssue]] = {}
        for issue in self.issues:
            by_kind.setdefault(issue.kind, []).append(issue)
        for kind, items in sorted(by_kind.items()):
            title = kind.replace("_", " ").title()
            lines += [f"## {title} ({len(items)})", ""]
            for i in items:
                lines.append(f"- `{i.page}` — {i.detail}")
            lines.append("")
        return "\n".join(lines)


class LintAgent:
    def __init__(self, vault: Vault) -> None:
        self._vault = vault

    def run(self) -> LintReport:
        """Run all lint checks and write journal/lint-YYYY-MM-DD.md."""
        report = LintReport()
        pages = self._vault.list_pages()

        if not pages:
            self._write_report(report)
            return report

        stem_map = _stems(self._vault)

        # Track which pages are referenced by wikilinks (for orphan detection)
        referenced_stems: set[str] = set()
        page_outlinks: dict[str, list[str]] = {}

        for page_path in pages:
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            try:
                content = page_path.read_text(encoding="utf-8")
                page_obj = WikiPage.from_markdown(content)
            except Exception as exc:
                report.issues.append(
                    LintIssue(kind="parse_error", page=rel, detail=str(exc))
                )
                page_outlinks[rel] = []
                continue

            links = _extract_wikilinks(content)
            page_outlinks[rel] = links
            for stem in links:
                referenced_stems.add(stem)

            # 1. Broken wikilinks
            for stem in links:
                if stem not in stem_map:
                    report.issues.append(
                        LintIssue(
                            kind="broken_wikilink",
                            page=rel,
                            detail=f"[[{stem}]] has no matching page",
                        )
                    )

            # 3. Stale drafts
            if (
                page_obj.status == "draft"
                and (date.today() - page_obj.updated) > timedelta(days=_STALE_DAYS)
            ):
                report.issues.append(
                    LintIssue(
                        kind="stale_draft",
                        page=rel,
                        detail=f"draft since {page_obj.updated} ({(date.today() - page_obj.updated).days}d ago)",
                    )
                )

            # 4. Provenance drift
            if page_obj.provenance.inferred > 70:
                report.issues.append(
                    LintIssue(
                        kind="provenance_drift",
                        page=rel,
                        detail=f"inferred={page_obj.provenance.inferred}% (>70%, possible hallucination)",
                    )
                )

        # 2. Orphan pages — no other page links to them AND they have no outgoing links
        for page_path in pages:
            rel = str(page_path.relative_to(self._vault.path)).replace("\\", "/")
            stem = page_path.stem
            has_outlinks = bool(page_outlinks.get(rel))
            has_inlinks = stem in referenced_stems
            if not has_outlinks and not has_inlinks:
                report.issues.append(
                    LintIssue(kind="orphan", page=rel, detail="no incoming or outgoing wikilinks")
                )

        log.info("lint.complete", issues=len(report.issues))
        self._write_report(report)
        return report

    def _write_report(self, report: LintReport) -> None:
        journal_dir = self._vault.path / "journal"
        journal_dir.mkdir(parents=True, exist_ok=True)
        filename = f"lint-{report.generated}.md"
        (journal_dir / filename).write_text(report.to_markdown(), encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_lint.py -v
```

Expected: ALL 9 PASS.

- [ ] **Step 5: Commit**

```
git add src/second_brain/agents/lint.py tests/test_lint.py
git commit -m "feat: add LintAgent (broken links, orphans, stale drafts, provenance drift)"
```

---

## Task 7: Update `agents/__init__.py` and CLI Integration

**Files:**
- Modify: `src/second_brain/agents/__init__.py` (verify imports work)
- Modify: `src/second_brain/cli.py`
- Create: `tests/test_agents_cli.py`

### Context

Add `ingest`, `query`, and `lint` as top-level `@app.command()` in `cli.py`. All three lazy-import their agent classes to keep startup fast. Tests mock the agent classes entirely (no vault, no LLM needed).

- [ ] **Step 1: Update `src/second_brain/agents/__init__.py` with re-exports**

Now that all three agent modules exist, populate the package's public API:

```python
from .ingest import IngestAgent, IngestResult
from .lint import LintAgent, LintIssue, LintReport
from .query import QueryAgent, QueryResult

__all__ = [
    "IngestAgent",
    "IngestResult",
    "QueryAgent",
    "QueryResult",
    "LintAgent",
    "LintReport",
    "LintIssue",
]
```

Verify it compiles:

```
uv run python -c "from second_brain.agents import IngestAgent, QueryAgent, LintAgent; print('ok')"
```

Expected: `ok`

- [ ] **Step 2: Write failing tests for CLI**

Create `tests/test_agents_cli.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from second_brain.agents.ingest import IngestResult
from second_brain.agents.lint import LintIssue, LintReport
from second_brain.agents.query import QueryResult
from second_brain.cli import app

runner = CliRunner()


def test_ingest_cli_single_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    mock_agent = MagicMock()
    mock_agent.run.return_value = IngestResult(
        decision="create",
        wiki_path="wiki/concepts/test.md",
        archived_path=tmp_path / "raw" / "archived" / "test.md",
        source_name="test.md",
    )
    with patch("second_brain.cli.IngestAgent", return_value=mock_agent):
        result = runner.invoke(app, ["ingest", "raw/inbox/test.md"])
    assert result.exit_code == 0
    assert "create" in result.output


def test_ingest_cli_inbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inbox = tmp_path / "raw" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "a.md").write_text("content a", encoding="utf-8")
    (inbox / "b.md").write_text("content b", encoding="utf-8")
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))

    mock_agent = MagicMock()
    mock_agent.run.return_value = IngestResult(
        decision="create",
        wiki_path="wiki/concepts/x.md",
        archived_path=tmp_path / "raw" / "archived" / "a.md",
        source_name="a.md",
    )
    with patch("second_brain.cli.IngestAgent", return_value=mock_agent):
        result = runner.invoke(app, ["ingest", "--inbox"])
    assert result.exit_code == 0
    assert mock_agent.run.call_count == 2


def test_ingest_cli_no_args_exits_nonzero() -> None:
    result = runner.invoke(app, ["ingest"])
    assert result.exit_code != 0


def test_query_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    mock_agent = MagicMock()
    mock_agent.ask.return_value = QueryResult(
        answer="Transformers use attention.", sources=["wiki/concepts/transformers.md"]
    )
    with patch("second_brain.cli.QueryAgent", return_value=mock_agent):
        result = runner.invoke(app, ["query", "What are transformers?"])
    assert result.exit_code == 0
    assert "Transformers use attention." in result.output


def test_lint_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    mock_agent = MagicMock()
    mock_agent.run.return_value = LintReport(
        issues=[LintIssue(kind="broken_wikilink", page="wiki/concepts/a.md", detail="test")]
    )
    with patch("second_brain.cli.LintAgent", return_value=mock_agent):
        result = runner.invoke(app, ["lint"])
    assert result.exit_code == 0
    assert "1" in result.output or "broken" in result.output.lower()


def test_lint_cli_clean_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    mock_agent = MagicMock()
    mock_agent.run.return_value = LintReport(issues=[])
    with patch("second_brain.cli.LintAgent", return_value=mock_agent):
        result = runner.invoke(app, ["lint"])
    assert result.exit_code == 0
    assert "0" in result.output or "no issues" in result.output.lower()
```

- [ ] **Step 3: Run tests to verify they fail**

```
uv run pytest tests/test_agents_cli.py -v
```

Expected: FAIL — `invoke` returns exit_code != 0 or the ingest/query/lint commands do not exist.

- [ ] **Step 4: Add imports and three commands to `cli.py`**

Replace the existing `from typing import Annotated` import line with:

```python
from typing import Annotated, Optional
```

Then add three new commands after the existing `llm_test` function:

```python
@app.command()
def ingest(
    path: Annotated[Optional[str], typer.Argument(help="Vault-relative path to source file")] = None,
    inbox: Annotated[bool, typer.Option("--inbox", help="Process all files in raw/inbox/")] = False,
    sensitivity: Annotated[str, typer.Option("--sensitivity", "-s", help="normal|private")] = "normal",
) -> None:
    """Ingest a raw source file (or the full inbox) into the wiki."""
    from .agents.ingest import IngestAgent, IngestError
    from .config import Settings
    from .llm import LLMRouter
    from .storage import Vault

    if not path and not inbox:
        console.print("[red]✗[/red] Provide a file path or --inbox")
        raise typer.Exit(1)

    settings = Settings()
    vault = Vault(settings.vault_path)
    router = LLMRouter(settings=settings)
    agent = IngestAgent(vault=vault, router=router)

    def _do_ingest(rel: str) -> None:
        try:
            result = agent.run(rel, sensitivity=sensitivity)  # type: ignore[arg-type]
            console.print(
                f"[green]✓[/green] {result.decision}: [bold]{result.source_name}[/bold]"
                + (f" → {result.wiki_path}" if result.wiki_path else "")
            )
        except IngestError as exc:
            console.print(f"[red]✗[/red] {exc}")

    if inbox:
        inbox_dir = settings.vault_path.expanduser().resolve() / "raw" / "inbox"
        files = [f for f in inbox_dir.iterdir() if f.is_file()] if inbox_dir.exists() else []
        if not files:
            console.print("[yellow]Inbox is empty[/yellow]")
            return
        for f in files:
            rel = str(f.relative_to(settings.vault_path.expanduser().resolve())).replace("\\", "/")
            _do_ingest(rel)
    else:
        _do_ingest(path)  # type: ignore[arg-type]


@app.command()
def query(
    question: Annotated[str, typer.Argument(help="Natural language question")],
    sensitivity: Annotated[str, typer.Option("--sensitivity", "-s", help="normal|private")] = "normal",
) -> None:
    """Ask a question; answer is synthesized from the wiki."""
    from .agents.query import QueryAgent
    from .config import Settings
    from .llm import LLMRouter
    from .storage import Vault

    settings = Settings()
    vault = Vault(settings.vault_path)
    router = LLMRouter(settings=settings)
    agent = QueryAgent(vault=vault, router=router)

    result = agent.ask(question, sensitivity=sensitivity)  # type: ignore[arg-type]
    console.print(result.answer)
    if result.sources:
        console.print("\n[dim]Sources: " + ", ".join(result.sources) + "[/dim]")


@app.command()
def lint() -> None:
    """Scan the wiki for broken links, orphans, stale drafts, and provenance drift."""
    from .agents.lint import LintAgent
    from .config import Settings
    from .storage import Vault

    settings = Settings()
    vault = Vault(settings.vault_path)
    agent = LintAgent(vault)
    report = agent.run()

    issue_count = len(report.issues)
    if issue_count == 0:
        console.print("[green]✓[/green] No issues found. Vault is healthy.")
    else:
        console.print(f"[yellow]⚠[/yellow] {issue_count} issue(s) found:")
        for issue in report.issues[:20]:
            console.print(f"  [{issue.kind}] {issue.page} — {issue.detail}")
        if issue_count > 20:
            console.print(f"  ... and {issue_count - 20} more. See journal/ for full report.")
```

- [ ] **Step 5: Run tests to verify they pass**

```
uv run pytest tests/test_agents_cli.py -v
```

Expected: ALL 6 PASS.

- [ ] **Step 6: Run full test suite**

```
uv run pytest --tb=short -q
```

Expected: ALL tests pass (previous 65 + new tests).

- [ ] **Step 7: Commit**

```
git add src/second_brain/agents/__init__.py src/second_brain/cli.py tests/test_agents_cli.py
git commit -m "feat: add ingest/query/lint CLI commands"
```

---

## Task 8: Full Verification

**Files:** none (verification only)

### Context

All Phase 3 code and tests must pass `pytest`, `mypy --strict`, and `ruff` before the phase is considered complete. A CLI smoke test validates the happy path without a live LLM.

- [ ] **Step 1: Run the full test suite**

```
uv run pytest -v
```

Expected: ALL tests pass. Note the count — it should include the 65 Phase 1+2 tests plus the new Phase 3 tests.

If any test fails, fix the root cause before continuing.

- [ ] **Step 2: Run mypy strict**

```
uv run mypy src/
```

Expected: `Success: no issues found in N source files`

Common issues and fixes:
- `error: Module "rank_bm25" has no attribute "BM25Okapi"` → add `# type: ignore[attr-defined]` on that line AND ensure `[[tool.mypy.overrides]] module = ["rank_bm25"]` is in `pyproject.toml`
- `error: Returning Any from function declared to return "list[SearchResult]"` → annotate the sort with explicit types or add `# type: ignore[return-value]`
- `error: Need type annotation for "_parts"` → already annotated in `_TextExtractor.__init__`

- [ ] **Step 3: Run ruff lint and format**

```
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

Expected: no output (clean).

If ruff reports issues, fix them:
- Import sort: `uv run ruff check --fix src/ tests/`
- Format: `uv run ruff format src/ tests/`

Then re-run checks to confirm clean.

- [ ] **Step 4: Run pre-commit hooks**

```
uv run pre-commit run --all-files
```

Expected: all hooks pass (ruff, ruff-format, mypy).

If any hook modifies files (ruff auto-fix), re-stage and commit the style fixes:
```
git add -u
git commit -m "style: fix ruff/mypy issues in Phase 3 code"
```

- [ ] **Step 5: CLI smoke test (dry-run, no live LLM)**

Test the `lint` command against a freshly initialized vault (no LLM needed):

```
$env:SECOND_BRAIN_VAULT_PATH = "$env:TEMP\smoke-vault"
uv run second-brain init "$env:TEMP\smoke-vault"
uv run second-brain lint
uv run second-brain status
```

Expected:
- `init` prints `✓ Vault initialized at ...`
- `lint` prints `✓ No issues found. Vault is healthy.`
- `status` prints wiki page count (should be 0 after init)

- [ ] **Step 6: Test `llm route` still works (regression check)**

```
uv run second-brain llm route --task synthesis_complex --sensitivity private
```

Expected: `→ local-fast`

- [ ] **Step 7: Commit final verification state**

Only if pre-commit required style fixes (otherwise the previous commit is the last one):

```
git add -u
git commit -m "chore: Phase 3 full verification — all tests pass, mypy clean, ruff clean"
```

---

## Acceptance Criteria Verification

The spec requires all of these to pass before Phase 4 begins:

| Criterion | How to verify |
|---|---|
| Markdown file in `raw/inbox/` → wiki page created | `test_ingest_creates_new_page` |
| Second file on same topic merges, not duplicates | `test_ingest_merge_decision_updates_page` |
| `query` returns wiki-cited answer | `test_query_cites_sources` |
| `lint` detects artificial broken links | `test_lint_detects_broken_wikilink` |
| All wiki changes git-committed | `test_ingest_commits_to_git` |

All five are covered by the test suite added in Tasks 4–6.

---

## Self-Review

### Spec Coverage

- **§5 Phase 3 Task 1 (Schema)** — Schema was written in Phase 1 (`_meta/schema.md` via `second-brain init`). No new code needed.
- **§5 Phase 3 Task 2 (Ingest)** — Covered by Task 4 above.
- **§5 Phase 3 Task 3 (Query)** — Covered by Task 5 above.
- **§5 Phase 3 Task 4 (Lint)** — Covered by Task 6 above. Contradiction detection (LLM) is deferred to Phase 5 per spec.
- **§5 Phase 3 Task 5 (CLI)** — Covered by Task 7 above.
- **§8 Test strategy — ingest: fake source → expected wiki structure** — `test_ingest_creates_new_page` and `test_ingest_merge_decision_updates_page`.
- **§8 Test strategy — lint: artificial broken/orphan/contradiction** — `test_lint_*` suite.
- **§9 Privacy — private tag enforcement** — `IngestAgent.run()` accepts `sensitivity` param; `LLMRouter` enforces routing. Tested via Phase 2 policy tests.

### Placeholder Scan

No "TBD", "TODO", "implement later" present.

### Type Consistency

- `IngestResult.decision: str` (not `Literal`) — safe for all comparisons in tests and CLI.
- `_IngestDecision.type: PageType` — matches `WikiPage.type: PageType` from `frontmatter.py`.
- `ProvenanceBreakdown` — imported from `storage.frontmatter`, same class used in `WikiPage` and `_IngestDecision`.
- `Sensitivity` type — imported from `llm.types`, matches `LLMRouter.complete()` signature.
- `WikiSearcher.search()` → `list[SearchResult]` — consumed by both `IngestAgent` and `QueryAgent`.
- `LintIssue.kind: str` — tests compare with `==` string literals; no type mismatch.
