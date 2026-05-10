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
