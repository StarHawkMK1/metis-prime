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

_DENYLIST_KEYWORDS: frozenset[str] = frozenset(
    {
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
    }
)


def _is_sensitive_path(path: Path) -> bool:
    """Return True if any component of *path* matches the denylist."""
    for part in path.parts:
        lower = part.lower()
        if lower in _DENYLIST_KEYWORDS:
            return True
        if any(kw in lower for kw in ("secret", "credential", "password", "private_key")):
            return True
    return False


class InboxHandler(FileSystemEventHandler):  # type: ignore[misc]
    """Copy new files from watched directories into raw/inbox/ (or raw/inbox/audio/ for audio)."""

    def __init__(
        self,
        inbox_path: Path,
        extensions: set[str] | None = None,
    ) -> None:
        self.inbox_path = inbox_path
        self.extensions: set[str] = extensions or {
            ".md",
            ".pdf",
            ".txt",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
        }

    def on_created(self, event: FileCreatedEvent) -> None:
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

    def __init__(
        self,
        watch_dirs: list[Path],
        inbox_path: Path,
        extensions: set[str] | None = None,
    ) -> None:
        self.watch_dirs = watch_dirs
        self.inbox_path = inbox_path
        self.extensions = extensions
        self._observer: Observer | None = None

    def start(self) -> None:
        handler = InboxHandler(self.inbox_path, extensions=self.extensions)
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
