from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

_SKIP_TAGS: frozenset[str] = frozenset({"script", "style"})


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip: int = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
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
