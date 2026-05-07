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


def auto_commit(
    repo_path: Path,
    message: str,
    paths: list[Path],
    removed_paths: list[Path] | None = None,
) -> None:
    """Stage additions and optional removals, then commit. No-op if nothing to stage."""
    if not paths and not removed_paths:
        return
    repo = pygit2.Repository(str(repo_path))
    index = repo.index
    index.read()
    for p in paths:
        rel = str(p.relative_to(repo_path)).replace("\\", "/")
        index.add(rel)
    for p in removed_paths or []:
        rel = str(p.relative_to(repo_path)).replace("\\", "/")
        index.remove(rel)
    index.write()
    sig = _get_signature(repo)
    tree = index.write_tree()
    parent_ids: list[Any] = [] if repo.head_is_unborn else [repo.head.target]
    repo.create_commit("refs/heads/main", sig, sig, message, tree, parent_ids)
