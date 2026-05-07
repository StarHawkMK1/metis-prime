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
            if rel.parts[0] == _RAW_TOP:
                raise RuntimeError(f"Cannot write to raw/: {full_path}")
        except ValueError:
            pass  # path outside vault — let pydantic/OS error naturally

    def write_page(self, relative_path: str, page: WikiPage) -> Path:
        full_path = self.path / relative_path
        self._guard_raw(full_path)
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
