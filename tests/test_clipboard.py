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
