from __future__ import annotations

import frontmatter as fm

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


def test_raw_source_updated_reflects_today() -> None:
    from datetime import date

    src = RawSource(title="Test", sources=[], body="")
    md = src.to_markdown()
    post = fm.loads(md)
    assert post["updated"] == str(date.today())
