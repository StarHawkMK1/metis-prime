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
