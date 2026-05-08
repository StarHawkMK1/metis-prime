#!/usr/bin/env python3
"""Install git hooks from scripts/ into .git/hooks/."""

from __future__ import annotations

import shutil
import stat
from pathlib import Path


def install() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    git_hooks = repo_root / ".git" / "hooks"
    if not git_hooks.exists():
        print(f"Error: {git_hooks} does not exist -- are you in a git repo?")
        return

    src = repo_root / "scripts" / "post-commit"
    dst = git_hooks / "post-commit"
    shutil.copy(src, dst)
    current = dst.stat().st_mode
    dst.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Installed: {dst}")
    print("Set SECOND_BRAIN_VAULT_PATH in your shell profile to activate auto-update.")


if __name__ == "__main__":
    install()
