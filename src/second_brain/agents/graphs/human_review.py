from __future__ import annotations

import shutil
from dataclasses import dataclass

import structlog

from ...storage.vault import Vault

log = structlog.get_logger(__name__)


@dataclass
class ReviewResult:
    accepted: int = 0
    rejected: int = 0


def process_review(vault: Vault) -> ReviewResult:
    """
    Scan human_review/accepted/ and human_review/rejected/.
    - accepted/: move markdown files to wiki/concepts/
    - rejected/: delete markdown files
    """
    result = ReviewResult()
    review_base = vault.path / "human_review"

    accepted_dir = review_base / "accepted"
    if accepted_dir.exists():
        for md_file in accepted_dir.glob("*.md"):
            dest = vault.path / "wiki" / "concepts" / md_file.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(md_file), str(dest))
            result.accepted += 1
            log.info("human_review.accepted", file=md_file.name)

    rejected_dir = review_base / "rejected"
    if rejected_dir.exists():
        for md_file in rejected_dir.glob("*.md"):
            md_file.unlink()
            result.rejected += 1
            log.info("human_review.rejected", file=md_file.name)

    return result
