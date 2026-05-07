from pathlib import Path

import pytest

from second_brain.storage.git_ops import init_repo


@pytest.fixture()
def tmp_vault(tmp_path: Path) -> Path:
    """Temp directory with vault subdirs and git initialized."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "wiki" / "concepts").mkdir(parents=True)
    (vault / "raw" / "inbox").mkdir(parents=True)
    (vault / "raw" / "archived").mkdir(parents=True)
    init_repo(vault)
    return vault
