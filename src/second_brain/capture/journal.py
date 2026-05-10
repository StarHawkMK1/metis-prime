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
