from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

try:
    from fastapi import FastAPI
    from pydantic import BaseModel, field_validator
except ImportError as exc:  # pragma: no cover
    raise ImportError("fastapi is not installed. Run: uv sync --extra capture") from exc

from ..storage.frontmatter import RawSource


class ClipRequest(BaseModel):
    content: str
    url: str = ""
    title: str = ""

    @field_validator("content")
    @classmethod
    def _content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be empty")
        return v


def create_app(vault_path: Path) -> FastAPI:
    app = FastAPI(title="Second Brain Web Clipper")
    clips_dir = vault_path / "raw" / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/clip")
    def clip(req: ClipRequest) -> dict[str, str]:
        ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        safe = re.sub(r"[^\w\-]", "-", req.title)[:40] if req.title else "clip"
        filename = f"{ts}-{safe}.md"
        dest = clips_dir / filename

        sources = [s for s in [req.url] if s]
        raw_source = RawSource(
            title=req.title or f"Web Clip {ts}", sources=sources, body=req.content
        )
        dest.write_text(raw_source.to_markdown(), encoding="utf-8")
        return {"saved": str(dest)}

    return app
