from __future__ import annotations

import shutil
import stat
import sys
from pathlib import Path


def test_install_hooks_logic(tmp_path: Path) -> None:
    """Test the hook copy + chmod logic directly."""
    git_hooks = tmp_path / ".git" / "hooks"
    git_hooks.mkdir(parents=True)
    src = tmp_path / "post-commit"
    src.write_text("#!/bin/sh\necho hi", encoding="utf-8")
    dst = git_hooks / "post-commit"
    shutil.copy(src, dst)
    current = dst.stat().st_mode
    dst.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    assert dst.exists()
    # Windows NTFS does not honour Unix execute bits; skip the mode check there.
    if sys.platform != "win32":
        assert dst.stat().st_mode & stat.S_IXUSR


def test_hook_content_is_valid_sh(tmp_path: Path) -> None:
    """Verify the post-commit hook file exists and starts with a shebang."""
    repo_root = Path(__file__).resolve().parent.parent
    hook = repo_root / "scripts" / "post-commit"
    assert hook.exists(), f"scripts/post-commit not found at {hook}"
    content = hook.read_text(encoding="utf-8")
    assert content.startswith("#!/bin/sh"), "Hook must start with #!/bin/sh shebang"
    assert "SECOND_BRAIN_VAULT_PATH" in content
    assert "second-brain graph build --update" in content
