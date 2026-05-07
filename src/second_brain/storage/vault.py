from datetime import date
from pathlib import Path

from .frontmatter import WikiPage
from .git_ops import auto_commit

_RAW_TOP = "raw"


class Vault:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()

    def _guard_raw(self, full_path: Path) -> None:
        try:
            rel = full_path.relative_to(self.path)
        except ValueError:
            raise ValueError(f"Path escapes vault: {full_path}") from None
        if rel.parts[0] == _RAW_TOP:
            raise RuntimeError(f"Cannot write to raw/: {full_path}")

    def write_page(self, relative_path: str, page: WikiPage) -> Path:
        full_path = self.path / relative_path
        self._guard_raw(full_path)
        page = page.model_copy(update={"updated": date.today()})
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(page.to_markdown(), encoding="utf-8")
        auto_commit(self.path, f"write: {relative_path}", [full_path])
        return full_path

    def read_page(self, relative_path: str) -> WikiPage:
        full_path = self.path / relative_path
        return WikiPage.from_markdown(full_path.read_text(encoding="utf-8"))

    def list_pages(self, subdir: str = "wiki") -> list[Path]:
        base = self.path / subdir
        if not base.exists():
            return []
        return sorted(base.rglob("*.md"))

    def read_raw_text(self, relative_path: str) -> str:
        """Read a raw source file as plain text. Does not guard writes."""
        return (self.path / relative_path).read_text(encoding="utf-8")

    def page_exists(self, relative_path: str) -> bool:
        """Return True if a vault-relative page path exists on disk."""
        return (self.path / relative_path).exists()

    def archive_raw(self, relative_path: str) -> Path:
        """Move a raw file to raw/archived/ and commit the change.

        Raises FileNotFoundError if source does not exist.
        Raises ValueError if relative_path escapes the vault boundary.
        Raises FileExistsError if destination already exists (same filename archived twice).
        """
        resolved = (self.path / relative_path).resolve()
        if not resolved.is_relative_to(self.path.resolve()):
            raise ValueError(f"Path escapes vault boundary: {relative_path}")
        src = self.path / relative_path
        if not src.exists():
            raise FileNotFoundError(f"Raw file not found: {src}")
        dst_dir = self.path / "raw" / "archived"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        src.rename(dst)
        auto_commit(
            self.path,
            f"archive: {src.name}",
            [dst],
            removed_paths=[src],
        )
        return dst
