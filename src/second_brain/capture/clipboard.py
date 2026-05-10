from __future__ import annotations

from datetime import datetime
from pathlib import Path

try:
    import pyperclip
except ImportError as exc:  # pragma: no cover
    raise ImportError("pyperclip is not installed. Run: uv sync --extra capture") from exc

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
