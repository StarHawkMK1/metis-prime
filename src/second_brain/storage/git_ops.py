from pathlib import Path
from typing import Any

import pygit2


def _get_signature(repo: Any) -> Any:
    try:
        return repo.default_signature
    except KeyError:
        return pygit2.Signature("Second Brain", "second-brain@local")


def init_repo(path: Path) -> None:
    """Initialize a git repo and commit all files present in the directory."""
    repo = pygit2.init_repository(str(path))
    index = repo.index
    index.read()
    index.add_all()
    index.write()
    sig = _get_signature(repo)
    tree = index.write_tree()
    repo.create_commit("refs/heads/main", sig, sig, "init: initialize vault", tree, [])


def auto_commit(repo_path: Path, message: str, paths: list[Path]) -> None:
    """Stage specific files and create a commit. No-op if paths is empty."""
    if not paths:
        return
    repo = pygit2.Repository(str(repo_path))
    index = repo.index
    index.read()
    for p in paths:
        rel = str(p.relative_to(repo_path)).replace("\\", "/")
        index.add(rel)
    index.write()
    sig = _get_signature(repo)
    tree = index.write_tree()
    parent_ids: list[Any] = [] if repo.head_is_unborn else [repo.head.target]
    repo.create_commit("refs/heads/main", sig, sig, message, tree, parent_ids)
