# Phase 6: Capture Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Capture Layer — the topmost axis of Metis Prime's 4-axis architecture — so that files, audio, web clips, and clipboard content automatically flow into `raw/inbox/`, and a daily journal is generated from vault git activity.

**Architecture:** A new `src/second_brain/capture/` package contains five independent modules: `watcher.py` (watchdog file monitor), `transcribe.py` (faster-whisper STT), `clipper_endpoint.py` (FastAPI web clipper), `clipboard.py` (pyperclip save), and `journal.py` (daily journal from vault git log). All markdown-producing modules use a new `RawSource.to_markdown()` helper in `storage/frontmatter.py` to guarantee YAML-safe output via `frontmatter.dumps()`. A `capture_app` typer sub-app wires all commands into the existing CLI.

**Tech Stack:** `watchdog>=4.0` (core), `faster-whisper>=1.0` + `fastapi>=0.111` + `uvicorn>=0.30` + `pyperclip>=1.8` (`capture` optional extra), `pygit2` (already present), Windows Task Scheduler for daily journal cron.

**Scope Decisions:**
- **Daemon start/stop:** `second-brain capture watch` runs **blocking in the foreground** (stop with Ctrl+C). Background daemon operation is handled via Windows Task Scheduler (same pattern as `install-lint-cron.ps1` from Phase 5). No PID-file daemonization.
- **ActivityWatch deferred:** SPEC §5 Phase 6 Task 5 (ActivityWatch OS-level activity) is out of scope. The daily journal populates the activity section from vault `git log` entries instead. ActivityWatch integration remains a future enhancement.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `pyproject.toml` | `watchdog` → core deps; new `capture` optional extra |
| Modify | `pyproject.toml` | mypy overrides for new deps |
| Modify | `src/second_brain/storage/frontmatter.py` | Add `RawSource` dataclass |
| Modify | `src/second_brain/config.py` | Add capture config fields |
| Modify | `src/second_brain/cli.py` | Add vault dirs; add `capture_app` |
| Add | `src/second_brain/capture/__init__.py` | Package init |
| Add | `src/second_brain/capture/watcher.py` | `InboxHandler` (denylist, audio routing) + `CaptureWatcher` |
| Add | `src/second_brain/capture/transcribe.py` | `TranscribeWorker` + `TranscriptResult` |
| Add | `src/second_brain/capture/clipper_endpoint.py` | `create_app(vault_path)` FastAPI |
| Add | `src/second_brain/capture/clipboard.py` | `capture_clipboard(inbox_path)` |
| Add | `src/second_brain/capture/journal.py` | `generate_daily_journal(vault_path, date)` |
| Add | `scripts/install-capture-cron.ps1` | Windows Task Scheduler for daily journal |
| Add | `docs/obsidian-web-clipper-setup.md` | Guide for configuring Obsidian Web Clipper |
| Add | `tests/test_raw_source.py` | `RawSource.to_markdown()` YAML safety |
| Add | `tests/test_watcher.py` | `InboxHandler` routing, denylist, dedup |
| Add | `tests/test_transcribe.py` | `TranscribeWorker` with mocked faster-whisper |
| Add | `tests/test_clipper_endpoint.py` | FastAPI endpoint via `TestClient` |
| Add | `tests/test_clipboard.py` | Clipboard with mocked `pyperclip` |
| Add | `tests/test_capture_journal.py` | Journal generation and idempotency |
| Add | `tests/test_capture_cli.py` | CLI commands via `typer.testing.CliRunner` |

---

## Task 1: Add Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing import test**

Create `tests/test_capture_imports.py`:

```python
def test_watchdog_importable() -> None:
    from watchdog.observers import Observer  # noqa: F401
    from watchdog.events import FileSystemEventHandler  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_capture_imports.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'watchdog'`

- [ ] **Step 3: Update pyproject.toml**

In `pyproject.toml`, add `watchdog` to `[project]` dependencies and a new `capture` optional extra. Also extend `[[tool.mypy.overrides]]`.

Replace the `dependencies` list (keep all existing, append watchdog):

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
    "watchdog>=4.0",
]
```

Add a `capture` optional extra (after `proxy`):

```toml
[project.optional-dependencies]
proxy = [
    "litellm[proxy]>=1.50",
]
capture = [
    "faster-whisper>=1.0",
    "fastapi>=0.111",
    "uvicorn>=0.30",
    "pyperclip>=1.8",
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

Append a new `[[tool.mypy.overrides]]` block:

```toml
[[tool.mypy.overrides]]
module = ["watchdog", "watchdog.*", "faster_whisper", "fastapi", "fastapi.*", "uvicorn", "pyperclip"]
ignore_missing_imports = true
```

- [ ] **Step 4: Install core + capture extras**

```
uv sync --extra capture
```

Expected: resolves without errors.

- [ ] **Step 5: Run import test to verify it passes**

```
uv run pytest tests/test_capture_imports.py -v
```

Expected: `PASSED`

- [ ] **Step 6: Commit**

```
git add pyproject.toml uv.lock tests/test_capture_imports.py
git commit -m "feat: add watchdog to core deps; capture optional extra (faster-whisper, fastapi, pyperclip)"
```

---

## Task 2: RawSource Dataclass

**Files:**
- Modify: `src/second_brain/storage/frontmatter.py`
- Test: `tests/test_raw_source.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_raw_source.py`:

```python
from __future__ import annotations

import frontmatter as fm
import pytest

from second_brain.storage.frontmatter import RawSource


def test_raw_source_to_markdown_produces_valid_yaml() -> None:
    src = RawSource(title="My Clip", sources=["https://example.com"], body="Article body.")
    md = src.to_markdown()
    post = fm.loads(md)
    assert post["title"] == "My Clip"
    assert post["type"] == "ref"
    assert post["status"] == "draft"
    assert "https://example.com" in post["sources"]
    assert post.content.strip() == "Article body."


def test_raw_source_escapes_colon_in_title() -> None:
    """fm.dumps must handle colons in titles without breaking YAML."""
    src = RawSource(title="Key: Value ratio", sources=[], body="")
    md = src.to_markdown()
    post = fm.loads(md)
    assert post["title"] == "Key: Value ratio"


def test_raw_source_escapes_quotes_in_title() -> None:
    src = RawSource(title='She said "hello"', sources=[], body="text")
    md = src.to_markdown()
    post = fm.loads(md)
    assert post["title"] == 'She said "hello"'


def test_raw_source_empty_sources_list() -> None:
    src = RawSource(title="Clipboard 2026-05-10", sources=[], body="clipped")
    md = src.to_markdown()
    post = fm.loads(md)
    assert post["sources"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_raw_source.py -v
```

Expected: `FAILED` — `ImportError: cannot import name 'RawSource'`

- [ ] **Step 3: Add RawSource to frontmatter.py**

Append to `src/second_brain/storage/frontmatter.py` (after the existing `WikiPage` class):

```python
from dataclasses import dataclass, field as dc_field
from datetime import date as _date


@dataclass
class RawSource:
    """Frontmatter wrapper for raw source files (transcripts, clips, clipboard)."""

    title: str
    sources: list[str] = dc_field(default_factory=list)
    created: _date = dc_field(default_factory=_date.today)
    body: str = ""

    def to_markdown(self) -> str:
        post = fm.Post(
            self.body,
            title=self.title,
            type="ref",
            status="draft",
            sources=self.sources,
            created=str(self.created),
            updated=str(self.created),
        )
        return str(fm.dumps(post))
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_raw_source.py -v
```

Expected: 4 `PASSED`

- [ ] **Step 5: Commit**

```
git add src/second_brain/storage/frontmatter.py tests/test_raw_source.py
git commit -m "feat: add RawSource dataclass to frontmatter for safe YAML capture output"
```

---

## Task 3: Config Updates and Vault Dirs

**Files:**
- Modify: `src/second_brain/config.py`
- Modify: `src/second_brain/cli.py` (only the `_VAULT_DIRS` list)

- [ ] **Step 1: Write failing test for new config fields**

Append to `tests/test_llm_config.py` (or create `tests/test_capture_config.py`):

```python
def test_capture_config_defaults() -> None:
    import os
    # Clear any env vars that might interfere
    for k in ["SECOND_BRAIN_CAPTURE_WATCH_DIRS", "SECOND_BRAIN_CLIPPER_PORT",
               "SECOND_BRAIN_CLIPPER_HOST", "SECOND_BRAIN_WHISPER_MODEL_SIZE"]:
        os.environ.pop(k, None)

    from second_brain.config import Settings
    s = Settings()
    assert s.capture_watch_dirs == []
    assert s.clipper_port == 7331
    assert s.clipper_host == "127.0.0.1"
    assert s.whisper_model_size == "base"
    assert ".md" in s.capture_extensions
    assert ".pdf" in s.capture_extensions
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_capture_config.py -v
```

Expected: `FAILED` — `AttributeError: 'Settings' has no attribute 'capture_watch_dirs'`

- [ ] **Step 3: Update config.py**

Replace `src/second_brain/config.py` with:

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

    litellm_base_url: AnyHttpUrl = Field(  # type: ignore[assignment]
        default="http://localhost:4000"
    )
    litellm_master_key: SecretStr | None = Field(default=None)

    # Capture layer
    capture_watch_dirs: list[Path] = Field(default_factory=list)
    capture_extensions: list[str] = Field(
        default_factory=lambda: [".md", ".pdf", ".txt", ".png", ".jpg", ".jpeg", ".webp"]
    )
    clipper_port: int = 7331
    clipper_host: str = "127.0.0.1"
    whisper_model_size: str = "base"
```

- [ ] **Step 4: Run config test to verify it passes**

```
uv run pytest tests/test_capture_config.py -v
```

Expected: `PASSED`

- [ ] **Step 5: Update _VAULT_DIRS in cli.py**

In `src/second_brain/cli.py`, find the `_VAULT_DIRS` list and add the missing directories. Replace the existing list with:

```python
_VAULT_DIRS = [
    "_meta",
    "raw/inbox",
    "raw/inbox/audio",
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
    "human_review/pending",
    "human_review/accepted",
    "human_review/rejected",
]
```

- [ ] **Step 6: Run existing CLI test to verify init still works**

```
uv run pytest tests/test_cli.py -v
```

Expected: all `PASSED`

- [ ] **Step 7: Commit**

```
git add src/second_brain/config.py src/second_brain/cli.py tests/test_capture_config.py
git commit -m "feat: add capture config fields; add raw/inbox/audio and human_review dirs to vault init"
```

---

## Task 4: File Watcher

**Files:**
- Add: `src/second_brain/capture/__init__.py`
- Add: `src/second_brain/capture/watcher.py`
- Test: `tests/test_watcher.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_watcher.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from watchdog.events import FileCreatedEvent

from second_brain.capture.watcher import InboxHandler, _is_sensitive_path


def test_handler_copies_md_file(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    src = tmp_path / "note.md"
    src.write_text("hello", encoding="utf-8")

    handler = InboxHandler(inbox_path=inbox, extensions={".md"})
    handler.on_created(FileCreatedEvent(str(src)))

    assert (inbox / "note.md").exists()
    assert (inbox / "note.md").read_text(encoding="utf-8") == "hello"


def test_handler_ignores_unknown_extension(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    src = tmp_path / "script.py"
    src.write_text("code", encoding="utf-8")

    handler = InboxHandler(inbox_path=inbox, extensions={".md"})
    handler.on_created(FileCreatedEvent(str(src)))

    assert not (inbox / "script.py").exists()


def test_handler_routes_audio_to_audio_subdir(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    audio_inbox = inbox / "audio"
    audio_inbox.mkdir(parents=True)
    src = tmp_path / "memo.m4a"
    src.write_bytes(b"audio data")

    handler = InboxHandler(inbox_path=inbox, extensions={".md", ".m4a"})
    handler.on_created(FileCreatedEvent(str(src)))

    assert (audio_inbox / "memo.m4a").exists()
    assert not (inbox / "memo.m4a").exists()


def test_handler_deduplicates_name_collision(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "note.md").write_text("existing", encoding="utf-8")
    src = tmp_path / "note.md"
    src.write_text("new", encoding="utf-8")

    handler = InboxHandler(inbox_path=inbox, extensions={".md"})
    handler.on_created(FileCreatedEvent(str(src)))

    md_files = list(inbox.glob("note*.md"))
    assert len(md_files) == 2


def test_handler_blocks_sensitive_path(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    sensitive_dir = tmp_path / ".ssh"
    sensitive_dir.mkdir()
    src = sensitive_dir / "id_rsa"
    src.write_text("PRIVATE KEY", encoding="utf-8")

    handler = InboxHandler(inbox_path=inbox, extensions={".md", ""})
    handler.on_created(FileCreatedEvent(str(src)))

    assert not (inbox / "id_rsa").exists()


def test_handler_ignores_directory_events(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    subdir = tmp_path / "subdir"
    subdir.mkdir()

    event = FileCreatedEvent(str(subdir))
    event.is_directory = True  # type: ignore[attr-defined]

    handler = InboxHandler(inbox_path=inbox, extensions={".md"})
    handler.on_created(event)  # Should not raise

    assert list(inbox.iterdir()) == []


@pytest.mark.parametrize("path_str", [
    "/home/user/.ssh/id_rsa",
    "C:/Users/me/.aws/credentials",
    "/home/user/secrets/db_password.txt",
    "/home/user/Documents/password_list.md",
])
def test_is_sensitive_path(path_str: str) -> None:
    assert _is_sensitive_path(Path(path_str)) is True


@pytest.mark.parametrize("path_str", [
    "/home/user/Documents/note.md",
    "/home/user/Downloads/article.pdf",
])
def test_is_not_sensitive_path(path_str: str) -> None:
    assert _is_sensitive_path(Path(path_str)) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_watcher.py -v
```

Expected: all `FAILED` — `ModuleNotFoundError: No module named 'second_brain.capture'`

- [ ] **Step 3: Create package init**

Create `src/second_brain/capture/__init__.py`:

```python
```

(Empty file.)

- [ ] **Step 4: Create watcher.py**

Create `src/second_brain/capture/watcher.py`:

```python
from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path

import structlog
from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer

log = structlog.get_logger(__name__)

_AUDIO_EXTENSIONS: frozenset[str] = frozenset({".m4a", ".wav", ".mp3", ".ogg", ".flac"})

_DENYLIST_KEYWORDS: frozenset[str] = frozenset({
    ".ssh",
    ".aws",
    ".gnupg",
    ".gpg",
    "secrets",
    "credentials",
    "keychain",
    "password",
    "private_key",
    "secret",
})


def _is_sensitive_path(path: Path) -> bool:
    """Return True if any component of *path* matches the denylist."""
    for part in path.parts:
        lower = part.lower()
        if lower in _DENYLIST_KEYWORDS:
            return True
        if any(kw in lower for kw in ("secret", "credential", "password", "private_key")):
            return True
    return False


class InboxHandler(FileSystemEventHandler):
    """Copy new files from watched directories into raw/inbox/ (or raw/inbox/audio/ for audio)."""

    def __init__(
        self,
        inbox_path: Path,
        extensions: set[str] | None = None,
    ) -> None:
        self.inbox_path = inbox_path
        self.extensions: set[str] = extensions or {
            ".md", ".pdf", ".txt", ".png", ".jpg", ".jpeg", ".webp"
        }

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if getattr(event, "is_directory", False):
            return
        src = Path(event.src_path)
        if src.suffix.lower() not in self.extensions:
            return
        if _is_sensitive_path(src):
            log.warning("capture.watcher.denied_sensitive", path=str(src))
            return

        if src.suffix.lower() in _AUDIO_EXTENSIONS:
            dest_dir = self.inbox_path / "audio"
        else:
            dest_dir = self.inbox_path

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists():
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = dest_dir / f"{src.stem}-{ts}{src.suffix}"

        shutil.copy2(src, dest)
        log.info("capture.watcher.copied", src=str(src), dest=str(dest))


class CaptureWatcher:
    """Blocking watcher daemon. Call run_forever() — stop with Ctrl+C."""

    def __init__(self, watch_dirs: list[Path], inbox_path: Path) -> None:
        self.watch_dirs = watch_dirs
        self.inbox_path = inbox_path
        self._observer: Observer | None = None

    def start(self) -> None:
        handler = InboxHandler(self.inbox_path)
        self._observer = Observer()
        for d in self.watch_dirs:
            if d.exists():
                self._observer.schedule(handler, str(d), recursive=False)
                log.info("capture.watcher.watching", dir=str(d))
        self._observer.start()

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def run_forever(self) -> None:
        self.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
```

- [ ] **Step 5: Run tests to verify they pass**

```
uv run pytest tests/test_watcher.py -v
```

Expected: all `PASSED`

- [ ] **Step 6: Commit**

```
git add src/second_brain/capture/__init__.py src/second_brain/capture/watcher.py tests/test_watcher.py
git commit -m "feat: add InboxHandler and CaptureWatcher with denylist and audio routing"
```

---

## Task 5: Audio Transcription

**Files:**
- Add: `src/second_brain/capture/transcribe.py`
- Test: `tests/test_transcribe.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_transcribe.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import frontmatter as fm
import pytest

from second_brain.capture.transcribe import TranscribeWorker, TranscriptResult


@pytest.fixture()
def audio_vault(tmp_path: Path) -> Path:
    (tmp_path / "raw" / "inbox" / "audio").mkdir(parents=True)
    (tmp_path / "raw" / "transcripts").mkdir(parents=True)
    return tmp_path


def _make_mock_model(text: str = "Hello world.", duration: float = 3.5, lang: str = "en") -> MagicMock:
    seg = MagicMock()
    seg.text = text
    info = MagicMock()
    info.duration = duration
    info.language = lang
    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([seg], info)
    return mock_model


def test_transcribe_file_creates_transcript(audio_vault: Path) -> None:
    audio = audio_vault / "raw" / "inbox" / "audio" / "memo.wav"
    audio.write_bytes(b"mock audio")

    with patch("second_brain.capture.transcribe.WhisperModel", return_value=_make_mock_model()):
        worker = TranscribeWorker(vault_path=audio_vault, model_size="base")
        result = worker.transcribe_file(audio)

    assert isinstance(result, TranscriptResult)
    assert result.transcript_path.exists()
    content = result.transcript_path.read_text(encoding="utf-8")
    assert "Hello world." in content
    assert result.duration_seconds == pytest.approx(3.5)
    assert result.language == "en"


def test_transcribe_file_frontmatter_is_valid_yaml(audio_vault: Path) -> None:
    audio = audio_vault / "raw" / "inbox" / "audio" / "note.m4a"
    audio.write_bytes(b"mock audio")

    with patch("second_brain.capture.transcribe.WhisperModel", return_value=_make_mock_model("Text.")):
        worker = TranscribeWorker(vault_path=audio_vault)
        result = worker.transcribe_file(audio)

    post = fm.loads(result.transcript_path.read_text(encoding="utf-8"))
    assert post["title"] == "Transcript of note.m4a"
    assert post["type"] == "ref"
    assert post["status"] == "draft"


def test_process_inbox_audio_returns_results(audio_vault: Path) -> None:
    for name in ("a.wav", "b.m4a"):
        (audio_vault / "raw" / "inbox" / "audio" / name).write_bytes(b"mock")

    with patch("second_brain.capture.transcribe.WhisperModel", return_value=_make_mock_model()):
        worker = TranscribeWorker(vault_path=audio_vault)
        results = worker.process_inbox_audio()

    assert len(results) == 2


def test_process_inbox_audio_empty_dir(audio_vault: Path) -> None:
    with patch("second_brain.capture.transcribe.WhisperModel", return_value=_make_mock_model()):
        worker = TranscribeWorker(vault_path=audio_vault)
        results = worker.process_inbox_audio()

    assert results == []


```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_transcribe.py -v
```

Expected: all `FAILED` — `ModuleNotFoundError: No module named 'second_brain.capture.transcribe'`

- [ ] **Step 3: Create transcribe.py**

Create `src/second_brain/capture/transcribe.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

from ..storage.frontmatter import RawSource

log = structlog.get_logger(__name__)

_AUDIO_EXTENSIONS: frozenset[str] = frozenset({".m4a", ".wav", ".mp3", ".ogg", ".flac"})


@dataclass
class TranscriptResult:
    source_path: Path
    transcript_path: Path
    duration_seconds: float
    language: str


# Top-level name so tests can patch `second_brain.capture.transcribe.WhisperModel`
try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # type: ignore[assignment,misc]


class TranscribeWorker:
    """Transcribe audio files using faster-whisper and write transcripts to raw/transcripts/."""

    def __init__(self, vault_path: Path, model_size: str = "base") -> None:
        self.vault_path = vault_path
        self.model_size = model_size
        self._model: object | None = None

    def _get_model(self) -> object:
        if WhisperModel is None:
            raise ImportError(
                "faster-whisper is not installed. "
                "Run: uv sync --extra capture"
            )
        if self._model is None:
            self._model = WhisperModel(self.model_size)
        return self._model

    def transcribe_file(self, audio_path: Path) -> TranscriptResult:
        model = self._get_model()
        segments, info = model.transcribe(str(audio_path), beam_size=5)  # type: ignore[union-attr]
        text = "\n".join(seg.text.strip() for seg in segments)

        transcript_dir = self.vault_path / "raw" / "transcripts"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = transcript_dir / f"{audio_path.stem}.md"

        raw_source = RawSource(
            title=f"Transcript of {audio_path.name}",
            sources=[str(audio_path)],
            body=text,
        )
        transcript_path.write_text(raw_source.to_markdown(), encoding="utf-8")
        log.info("capture.transcribe.done", audio=str(audio_path), transcript=str(transcript_path))

        return TranscriptResult(
            source_path=audio_path,
            transcript_path=transcript_path,
            duration_seconds=float(info.duration),
            language=str(info.language),
        )

    def process_inbox_audio(self) -> list[TranscriptResult]:
        audio_inbox = self.vault_path / "raw" / "inbox" / "audio"
        if not audio_inbox.exists():
            return []
        results = []
        for f in sorted(audio_inbox.iterdir()):
            if f.is_file() and f.suffix.lower() in _AUDIO_EXTENSIONS:
                results.append(self.transcribe_file(f))
        return results
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_transcribe.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```
git add src/second_brain/capture/transcribe.py tests/test_transcribe.py
git commit -m "feat: add TranscribeWorker for audio → transcript via faster-whisper"
```

---

## Task 6: Web Clipper Endpoint

**Files:**
- Add: `src/second_brain/capture/clipper_endpoint.py`
- Test: `tests/test_clipper_endpoint.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_clipper_endpoint.py`:

```python
from __future__ import annotations

from pathlib import Path

import frontmatter as fm
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def clip_vault(tmp_path: Path) -> Path:
    (tmp_path / "raw" / "clips").mkdir(parents=True)
    return tmp_path


def test_clip_saves_to_clips_dir(clip_vault: Path) -> None:
    from second_brain.capture.clipper_endpoint import create_app

    client = TestClient(create_app(clip_vault))
    response = client.post(
        "/clip",
        json={"content": "Article text.", "url": "https://example.com/article", "title": "Test Article"},
    )
    assert response.status_code == 200
    saved = Path(response.json()["saved"])
    assert saved.exists()
    content = saved.read_text(encoding="utf-8")
    assert "Article text." in content


def test_clip_frontmatter_valid_yaml(clip_vault: Path) -> None:
    from second_brain.capture.clipper_endpoint import create_app

    client = TestClient(create_app(clip_vault))
    response = client.post(
        "/clip",
        json={"content": "Body.", "url": "https://ex.com/page", "title": "Page: A Guide"},
    )
    assert response.status_code == 200
    post = fm.loads(Path(response.json()["saved"]).read_text(encoding="utf-8"))
    assert post["title"] == "Page: A Guide"
    assert post["type"] == "ref"
    assert "https://ex.com/page" in post["sources"]


def test_clip_minimal_request_no_url_no_title(clip_vault: Path) -> None:
    from second_brain.capture.clipper_endpoint import create_app

    client = TestClient(create_app(clip_vault))
    response = client.post("/clip", json={"content": "Just content."})
    assert response.status_code == 200
    saved = Path(response.json()["saved"])
    assert saved.exists()


def test_clip_empty_content_returns_422(clip_vault: Path) -> None:
    from second_brain.capture.clipper_endpoint import create_app

    client = TestClient(create_app(clip_vault))
    response = client.post("/clip", json={"content": ""})
    assert response.status_code == 422


def test_health_endpoint(clip_vault: Path) -> None:
    from second_brain.capture.clipper_endpoint import create_app

    client = TestClient(create_app(clip_vault))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_clipper_endpoint.py -v
```

Expected: all `FAILED` — `ModuleNotFoundError: No module named 'second_brain.capture.clipper_endpoint'`

- [ ] **Step 3: Create clipper_endpoint.py**

Create `src/second_brain/capture/clipper_endpoint.py`:

```python
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

try:
    from fastapi import FastAPI
    from pydantic import BaseModel, field_validator
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "fastapi is not installed. Run: uv sync --extra capture"
    ) from exc

from ..storage.frontmatter import RawSource


class ClipRequest(BaseModel):
    content: str
    url: str = ""
    title: str = ""

    @field_validator("content")
    @classmethod
    def _content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be empty")
        return v


def create_app(vault_path: Path) -> FastAPI:
    app = FastAPI(title="Second Brain Web Clipper")
    clips_dir = vault_path / "raw" / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/clip")
    def clip(req: ClipRequest) -> dict[str, str]:
        ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        safe = re.sub(r"[^\w\-]", "-", req.title)[:40] if req.title else "clip"
        filename = f"{ts}-{safe}.md"
        dest = clips_dir / filename

        sources = [s for s in [req.url] if s]
        raw_source = RawSource(title=req.title or f"Web Clip {ts}", sources=sources, body=req.content)
        dest.write_text(raw_source.to_markdown(), encoding="utf-8")
        return {"saved": str(dest)}

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_clipper_endpoint.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```
git add src/second_brain/capture/clipper_endpoint.py tests/test_clipper_endpoint.py
git commit -m "feat: add FastAPI web clipper endpoint (localhost-only, YAML-safe frontmatter)"
```

---

## Task 7: Clipboard Capture

**Files:**
- Add: `src/second_brain/capture/clipboard.py`
- Test: `tests/test_clipboard.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_clipboard.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import frontmatter as fm
import pytest


def test_capture_clipboard_saves_file(tmp_path: Path) -> None:
    inbox = tmp_path / "raw" / "inbox"
    inbox.mkdir(parents=True)

    with patch("second_brain.capture.clipboard.pyperclip") as mock_clip:
        mock_clip.paste.return_value = "This is clipboard content."
        from second_brain.capture.clipboard import capture_clipboard
        dest = capture_clipboard(inbox)

    assert dest.exists()
    assert "This is clipboard content." in dest.read_text(encoding="utf-8")
    assert dest.name.startswith("clip-")
    assert dest.suffix == ".md"


def test_capture_clipboard_frontmatter_valid(tmp_path: Path) -> None:
    inbox = tmp_path / "raw" / "inbox"
    inbox.mkdir(parents=True)

    with patch("second_brain.capture.clipboard.pyperclip") as mock_clip:
        mock_clip.paste.return_value = "Content: some value here."
        from second_brain.capture.clipboard import capture_clipboard
        dest = capture_clipboard(inbox)

    post = fm.loads(dest.read_text(encoding="utf-8"))
    assert post["type"] == "ref"
    assert post["status"] == "draft"
    assert "Content: some value here." in post.content


def test_capture_clipboard_raises_on_empty(tmp_path: Path) -> None:
    inbox = tmp_path / "raw" / "inbox"
    inbox.mkdir(parents=True)

    with patch("second_brain.capture.clipboard.pyperclip") as mock_clip:
        mock_clip.paste.return_value = "   "
        from second_brain.capture.clipboard import capture_clipboard
        with pytest.raises(ValueError, match="Clipboard is empty"):
            capture_clipboard(inbox)


```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_clipboard.py -v
```

Expected: all `FAILED` — `ModuleNotFoundError: No module named 'second_brain.capture.clipboard'`

- [ ] **Step 3: Create clipboard.py**

Create `src/second_brain/capture/clipboard.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

try:
    import pyperclip
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pyperclip is not installed. Run: uv sync --extra capture"
    ) from exc

from ..storage.frontmatter import RawSource


def capture_clipboard(inbox_path: Path) -> Path:
    """Read clipboard and save contents to a new file in inbox_path."""
    content = pyperclip.paste()
    if not content.strip():
        raise ValueError("Clipboard is empty")

    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    dest = inbox_path / f"clip-{ts}.md"
    raw_source = RawSource(title=f"Clipboard {ts}", sources=[], body=content)
    dest.write_text(raw_source.to_markdown(), encoding="utf-8")
    return dest
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_clipboard.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```
git add src/second_brain/capture/clipboard.py tests/test_clipboard.py
git commit -m "feat: add clipboard capture to raw/inbox/"
```

---

## Task 8: Daily Journal Generator

**Files:**
- Add: `src/second_brain/capture/journal.py`
- Test: `tests/test_capture_journal.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_capture_journal.py`:

```python
from __future__ import annotations

from datetime import date
from pathlib import Path

import frontmatter as fm
import pytest


@pytest.fixture()
def journal_vault(tmp_path: Path) -> Path:
    """A minimal vault with journal dir and no git repo (for isolation)."""
    (tmp_path / "journal").mkdir()
    return tmp_path


def test_generate_daily_journal_creates_file(journal_vault: Path) -> None:
    from second_brain.capture.journal import generate_daily_journal

    target = date(2026, 5, 10)
    path = generate_daily_journal(journal_vault, for_date=target)

    assert path.exists()
    assert path.name == "2026-05-10.md"
    assert path.parent == journal_vault / "journal" / "2026"


def test_generate_daily_journal_contains_date_heading(journal_vault: Path) -> None:
    from second_brain.capture.journal import generate_daily_journal

    path = generate_daily_journal(journal_vault, for_date=date(2026, 5, 10))
    content = path.read_text(encoding="utf-8")
    assert "## 2026-05-10" in content


def test_generate_daily_journal_frontmatter_valid(journal_vault: Path) -> None:
    from second_brain.capture.journal import generate_daily_journal

    path = generate_daily_journal(journal_vault, for_date=date(2026, 5, 10))
    post = fm.loads(path.read_text(encoding="utf-8"))
    assert post["date"] == "2026-05-10"
    assert post["type"] == "journal"


def test_generate_daily_journal_idempotent(journal_vault: Path) -> None:
    """Calling twice with same date does NOT overwrite existing content."""
    from second_brain.capture.journal import generate_daily_journal

    target = date(2026, 5, 10)
    path1 = generate_daily_journal(journal_vault, for_date=target)
    path1.write_text("custom content", encoding="utf-8")

    path2 = generate_daily_journal(journal_vault, for_date=target)

    assert path2.read_text(encoding="utf-8") == "custom content"
    assert path1 == path2


def test_generate_daily_journal_no_git_falls_back(journal_vault: Path) -> None:
    """Without a git repo, activity section shows fallback message."""
    from second_brain.capture.journal import generate_daily_journal

    path = generate_daily_journal(journal_vault, for_date=date(2026, 5, 10))
    content = path.read_text(encoding="utf-8")
    assert "No vault changes" in content or "No activity" in content


def test_generate_daily_journal_uses_today_by_default(journal_vault: Path) -> None:
    from datetime import date as dt
    from second_brain.capture.journal import generate_daily_journal

    path = generate_daily_journal(journal_vault)
    today_str = dt.today().strftime("%Y-%m-%d")
    assert today_str in path.name
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_capture_journal.py -v
```

Expected: all `FAILED` — `ModuleNotFoundError: No module named 'second_brain.capture.journal'`

- [ ] **Step 3: Create journal.py**

Create `src/second_brain/capture/journal.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import frontmatter as fm
import structlog

log = structlog.get_logger(__name__)


def generate_daily_journal(vault_path: Path, for_date: date | None = None) -> Path:
    """Create a daily journal file for *for_date* (defaults to today).

    Returns the path without overwriting if it already exists.
    Activity section is populated from vault git log entries for that date.
    """
    target_date = for_date or date.today()
    date_str = target_date.strftime("%Y-%m-%d")

    year_dir = vault_path / "journal" / str(target_date.year)
    year_dir.mkdir(parents=True, exist_ok=True)
    journal_path = year_dir / f"{date_str}.md"

    if journal_path.exists():
        return journal_path

    activity = _get_git_activity(vault_path, date_str)

    body = f"""\
## {date_str} — Daily Log

### Activity

{activity}

### Notes

<!-- Add your notes here -->

### Tasks

<!-- Today's tasks -->
"""
    post = fm.Post(body, date=date_str, type="journal", created=date_str, updated=date_str)
    journal_path.write_text(str(fm.dumps(post)), encoding="utf-8")
    log.info("capture.journal.created", path=str(journal_path))
    return journal_path


def _get_git_activity(vault_path: Path, date_str: str) -> str:
    """Return bullet list of git commits from *date_str* in the vault, or a fallback."""
    try:
        import pygit2
        repo = pygit2.Repository(str(vault_path))
        walker = repo.walk(repo.head.target, pygit2.GIT_SORT_TIME)
        lines: list[str] = []
        for commit in walker:
            commit_date = datetime.fromtimestamp(commit.commit_time).strftime("%Y-%m-%d")
            if commit_date < date_str:
                break
            if commit_date == date_str:
                lines.append(f"- {commit.message.strip()}")
            if len(lines) >= 20:
                break
        return "\n".join(lines) if lines else "_No vault changes today._"
    except Exception as exc:
        log.debug("capture.journal.git_activity_failed", error=str(exc))
        return "_No activity data available._"
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_capture_journal.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```
git add src/second_brain/capture/journal.py tests/test_capture_journal.py
git commit -m "feat: add daily journal generator with vault git-log activity section"
```

---

## Task 9: CLI Wiring

**Files:**
- Modify: `src/second_brain/cli.py`
- Test: `tests/test_capture_cli.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_capture_cli.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from second_brain.cli import app

runner = CliRunner()


def test_capture_journal_creates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    (tmp_path / "journal").mkdir()

    with patch("second_brain.capture.journal.generate_daily_journal") as mock_gen:
        mock_gen.return_value = tmp_path / "journal" / "2026" / "2026-05-10.md"
        result = runner.invoke(app, ["capture", "journal", "--date", "2026-05-10"])

    assert result.exit_code == 0
    assert "2026-05-10" in result.output


def test_capture_clip_calls_capture_clipboard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    inbox = tmp_path / "raw" / "inbox"
    inbox.mkdir(parents=True)

    dest = inbox / "clip-2026-05-10-120000.md"
    dest.write_text("content", encoding="utf-8")

    with patch("second_brain.capture.clipboard.capture_clipboard", return_value=dest):
        result = runner.invoke(app, ["capture", "clip"])

    assert result.exit_code == 0
    assert "clip-" in result.output


def test_capture_transcribe_single_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from second_brain.capture.transcribe import TranscriptResult

    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    audio = tmp_path / "memo.wav"
    audio.write_bytes(b"mock")
    transcript = tmp_path / "raw" / "transcripts" / "memo.md"
    (tmp_path / "raw" / "transcripts").mkdir(parents=True)
    transcript.write_text("transcript", encoding="utf-8")

    mock_worker = MagicMock()
    mock_worker.transcribe_file.return_value = TranscriptResult(
        source_path=audio,
        transcript_path=transcript,
        duration_seconds=5.0,
        language="en",
    )

    with patch("second_brain.capture.transcribe.TranscribeWorker", return_value=mock_worker):
        result = runner.invoke(app, ["capture", "transcribe", str(audio)])

    assert result.exit_code == 0
    assert "memo.md" in result.output


def test_capture_watch_errors_without_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    monkeypatch.delenv("SECOND_BRAIN_CAPTURE_WATCH_DIRS", raising=False)
    result = runner.invoke(app, ["capture", "watch"])
    assert result.exit_code != 0
    assert "No watch directories" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_capture_cli.py -v
```

Expected: all `FAILED` — `No such command 'capture'`

- [ ] **Step 3: Add capture_app to cli.py**

In `src/second_brain/cli.py`, add immediately after these two lines (which already exist near the top of the file):

```python
cost_app = typer.Typer(help="LLM cost tracking commands.")
app.add_typer(cost_app, name="cost")
```

Insert:

```python
capture_app = typer.Typer(help="Capture layer commands.")
app.add_typer(capture_app, name="capture")
```

Then append the following command implementations at the end of `cli.py`:

```python
# ── Capture commands ───────────────────────────────────────────────────────────


@capture_app.command("watch")
def capture_watch() -> None:
    """Watch configured directories and copy new files to raw/inbox/ (blocking — Ctrl+C to stop)."""
    from .capture.watcher import CaptureWatcher
    from .config import Settings

    settings = Settings()
    if not settings.capture_watch_dirs:
        console.print("[red]✗[/red] No watch directories configured.")
        console.print("  Set SECOND_BRAIN_CAPTURE_WATCH_DIRS or add capture_watch_dirs to .env")
        raise typer.Exit(1)

    vault_path = settings.vault_path.expanduser().resolve()
    inbox_path = vault_path / "raw" / "inbox"
    dirs = [Path(d).expanduser().resolve() for d in settings.capture_watch_dirs]

    console.print(f"[green]Watching {len(dirs)} dir(s) → {inbox_path}[/green]  (Ctrl+C to stop)")
    for d in dirs:
        console.print(f"  • {d}")

    watcher = CaptureWatcher(watch_dirs=dirs, inbox_path=inbox_path)
    watcher.run_forever()


@capture_app.command("transcribe")
def capture_transcribe(
    path: Annotated[
        str | None, typer.Argument(help="Path to audio file. Omit to scan raw/inbox/audio/")
    ] = None,
) -> None:
    """Transcribe audio file(s) using faster-whisper."""
    from .capture.transcribe import TranscribeWorker
    from .config import Settings

    settings = Settings()
    vault_path = settings.vault_path.expanduser().resolve()
    worker = TranscribeWorker(vault_path=vault_path, model_size=settings.whisper_model_size)

    if path:
        result = worker.transcribe_file(Path(path))
        console.print(
            f"[green]✓[/green] Transcript: [bold]{result.transcript_path}[/bold]"
            f"  ({result.duration_seconds:.1f}s, {result.language})"
        )
    else:
        results = worker.process_inbox_audio()
        if not results:
            console.print("[yellow]No audio files found in raw/inbox/audio/[/yellow]")
        for r in results:
            console.print(
                f"[green]✓[/green] {r.source_path.name} → [bold]{r.transcript_path.name}[/bold]"
            )


@capture_app.command("serve")
def capture_serve(
    port: Annotated[int | None, typer.Option("--port", "-p", help="Override clipper port")] = None,
    host: Annotated[str | None, typer.Option("--host", help="Override bind host")] = None,
) -> None:
    """Start the web clipper FastAPI server (blocking — Ctrl+C to stop)."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]✗[/red] uvicorn is not installed. Run: uv sync --extra capture")
        raise typer.Exit(1)

    from .capture.clipper_endpoint import create_app
    from .config import Settings

    settings = Settings()
    vault_path = settings.vault_path.expanduser().resolve()
    bind_host = host or settings.clipper_host
    bind_port = port or settings.clipper_port

    console.print(f"[green]Clipper listening on http://{bind_host}:{bind_port}[/green]  (Ctrl+C to stop)")
    fast_app = create_app(vault_path)
    uvicorn.run(fast_app, host=bind_host, port=bind_port)


@capture_app.command("clip")
def capture_clip() -> None:
    """Save clipboard contents to raw/inbox/."""
    from .capture.clipboard import capture_clipboard
    from .config import Settings

    settings = Settings()
    vault_path = settings.vault_path.expanduser().resolve()
    inbox_path = vault_path / "raw" / "inbox"
    inbox_path.mkdir(parents=True, exist_ok=True)

    try:
        dest = capture_clipboard(inbox_path)
        console.print(f"[green]✓[/green] Saved clipboard to [bold]{dest.name}[/bold]")
    except (ValueError, ImportError) as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1) from exc


@capture_app.command("journal")
def capture_journal(
    date: Annotated[
        str | None, typer.Option("--date", "-d", help="Date as YYYY-MM-DD (default: today)")
    ] = None,
) -> None:
    """Generate (or locate) the daily journal file."""
    from datetime import date as dt

    from .capture.journal import generate_daily_journal
    from .config import Settings

    settings = Settings()
    vault_path = settings.vault_path.expanduser().resolve()

    target: dt | None = None
    if date:
        try:
            target = dt.fromisoformat(date)
        except ValueError:
            console.print(f"[red]✗[/red] Invalid date format: {date!r}. Use YYYY-MM-DD.")
            raise typer.Exit(1)

    path = generate_daily_journal(vault_path, for_date=target)
    console.print(f"[green]✓[/green] Journal: [bold]{path}[/bold]")
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_capture_cli.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Run full test suite**

```
uv run pytest -v
```

Expected: all tests pass. Note: any existing test that imports from `cli.py` should still pass because we only appended new commands.

- [ ] **Step 6: Commit**

```
git add src/second_brain/cli.py tests/test_capture_cli.py
git commit -m "feat: wire capture_app into CLI (watch/transcribe/serve/clip/journal)"
```

---

## Task 10: Cron Script and Obsidian Guide

**Files:**
- Add: `scripts/install-capture-cron.ps1`
- Add: `docs/obsidian-web-clipper-setup.md`

- [ ] **Step 1: Create the Windows Task Scheduler script**

Create `scripts/install-capture-cron.ps1`:

```powershell
<#
.SYNOPSIS
    Register a daily Windows Task Scheduler job to generate the journal at 06:00.

.DESCRIPTION
    Installs "MetisPrime-DailyJournal" task.
    Run once as an Administrator or as the current user (no admin needed for user tasks).

.EXAMPLE
    .\scripts\install-capture-cron.ps1

.EXAMPLE
    # Custom time
    .\scripts\install-capture-cron.ps1 -TriggerTime "08:00"
#>
param(
    [string]$TriggerTime = "06:00"
)

$TaskName   = "MetisPrime-DailyJournal"
$WorkingDir = (Get-Location).Path
$Executable = "uv"
$Arguments  = "run second-brain capture journal"

# Remove existing task silently
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action  = New-ScheduledTaskAction -Execute $Executable -Argument $Arguments -WorkingDirectory $WorkingDir
$trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -RunOnlyIfNetworkAvailable:$false

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Metis Prime: generate daily journal at $TriggerTime" `
    -RunLevel Limited `
    -Force

Write-Host "Registered task '$TaskName' — fires daily at $TriggerTime."
Write-Host "To verify: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "To remove:  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
```

- [ ] **Step 2: Verify script syntax**

```powershell
powershell -NonInteractive -Command "& { Get-Content scripts\install-capture-cron.ps1 | Out-Null; Write-Host 'Syntax OK' }"
```

Expected: `Syntax OK` (no parse errors)

- [ ] **Step 3: Create the Obsidian Web Clipper setup guide**

Create `docs/obsidian-web-clipper-setup.md`:

```markdown
# Obsidian Web Clipper — Setup Guide

This guide configures Obsidian Web Clipper to save clipped pages directly to
`raw/clips/` in your vault, satisfying Phase 6 AC2.

## Prerequisites

- Obsidian desktop app with your vault open
- [Obsidian Web Clipper](https://obsidian.md/clipper) browser extension installed

## Configuration

### Option A: Direct vault save (simplest)

1. Open the Obsidian Web Clipper extension settings.
2. Set **Save location** to your vault's `raw/clips/` directory.
   - Example: `~/second-brain-vault/raw/clips/`
3. Set **File name format** to `{date:YYYY-MM-DD}-{title:50}` to match vault naming conventions.
4. Ensure **Frontmatter** includes at minimum:
   ```yaml
   type: ref
   status: draft
   sources: [{url}]
   ```

After saving, clipped pages appear in `raw/clips/` and are picked up by
`second-brain ingest --inbox` (or the file watcher if you've configured `capture watch`
to monitor `raw/clips/`).

### Option B: POST to clipper endpoint

If you prefer routing clips through Metis Prime's own endpoint (useful for mobile
share-sheet integration):

1. Start the clipper server:
   ```
   second-brain capture serve
   ```
   Default: `http://127.0.0.1:7331`

2. In the Web Clipper extension, set **Webhook URL** to `http://127.0.0.1:7331/clip`.
3. Map the request body to:
   ```json
   { "content": "{content}", "url": "{url}", "title": "{title}" }
   ```

## Verification

After clipping a page, run:

```
second-brain status
```

You should see the inbox item count increase. Then run:

```
second-brain ingest --inbox
```

to process the clip into `wiki/`.

## Mobile share sheet (Option B only)

On Android/iOS, add a shortcut that sends a POST request to
`http://<your-PC-IP>:7331/clip` with the shared URL and page title.
Note: expose the server on your LAN only with `--host 0.0.0.0` and a firewall rule
limiting access to your devices. The default `127.0.0.1` binding is localhost-only.
```

- [ ] **Step 4: Run the full test suite one final time**

```
uv run pytest -v
```

Expected: all tests pass. No regressions.

- [ ] **Step 5: Commit**

```
git add scripts/install-capture-cron.ps1 docs/obsidian-web-clipper-setup.md
git commit -m "feat: add daily journal cron installer and Obsidian Web Clipper setup guide"
```

---

## Acceptance Criteria Verification

Run each check after all 10 tasks are complete:

- [ ] **AC1 — File watcher copies within 5s**

  Start a watcher in one terminal (after configuring `SECOND_BRAIN_CAPTURE_WATCH_DIRS`):
  ```
  second-brain capture watch
  ```
  In another terminal, create a file in the watched directory. Verify it appears in `raw/inbox/` within 5 seconds.

- [ ] **AC2 — Web clipper saves to raw/clips/**

  Follow `docs/obsidian-web-clipper-setup.md`. Clip any page. Verify a `.md` file appears in `raw/clips/`. Alternatively: start `capture serve` and POST to `/clip` — verify saved file.

- [ ] **AC3 — Audio transcription**

  Place a `.wav` or `.m4a` file in `raw/inbox/audio/`, then run:
  ```
  second-brain capture transcribe
  ```
  Verify a `.md` file appears in `raw/transcripts/` with the spoken text.

- [ ] **AC4 — Daily journal auto-generated**

  ```
  second-brain capture journal
  ```
  Verify `journal/<YEAR>/<YYYY-MM-DD>.md` was created with an Activity section.

---

## Self-Review

**Spec coverage:**
- Phase 6 Task 1 (파일 감시자) → Task 4 (watcher.py, InboxHandler) ✓
- Phase 6 Task 2 (Web Clipper) → Task 6 (clipper_endpoint.py) + Task 10 (obsidian guide) ✓
- Phase 6 Task 3 (음성 캡처) → Task 5 (transcribe.py) ✓
- Phase 6 Task 4 (클립보드, 선택) → Task 7 (clipboard.py) ✓
- Phase 6 Task 5 (활동 로그, 선택 고급) → Task 8 (journal.py with git-log) + ActivityWatch deferred per Scope Decisions ✓

**Security:**
- Denylist enforced in InboxHandler before any copy ✓
- Clipper endpoint binds `127.0.0.1` by default (`clipper_host` config) ✓
- Audio extension allowlist limits surface area ✓

**YAML safety:**
- All markdown-producing modules use `RawSource.to_markdown()` via `frontmatter.dumps()` ✓
- Journal uses `fm.dumps(fm.Post(...))` directly ✓

**Type consistency:**
- `TranscriptResult.source_path/transcript_path` (Path) used consistently across transcribe.py tests and CLI ✓
- `RawSource` imported from `..storage.frontmatter` in transcribe.py, clipper_endpoint.py, clipboard.py ✓
- `_is_sensitive_path` exported from watcher.py and used in tests ✓
