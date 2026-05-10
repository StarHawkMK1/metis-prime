from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date
from typing import Any, Literal, cast

import frontmatter as fm
from pydantic import BaseModel, Field, model_validator

PageType = Literal["concept", "project", "person", "place", "ref", "map"]
PageStatus = Literal["draft", "active", "archived"]


class ProvenanceBreakdown(BaseModel):
    extracted: int = Field(ge=0, le=100, default=70)
    inferred: int = Field(ge=0, le=100, default=25)
    ambiguous: int = Field(ge=0, le=100, default=5)

    @model_validator(mode="after")
    def _sum_must_be_100(self) -> ProvenanceBreakdown:
        total = self.extracted + self.inferred + self.ambiguous
        if total != 100:
            raise ValueError(f"provenance fields must sum to 100, got {total}")
        return self


class WikiPage(BaseModel):
    title: str
    type: PageType
    status: PageStatus = "draft"
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    provenance: ProvenanceBreakdown = Field(default_factory=ProvenanceBreakdown)
    created: date = Field(default_factory=date.today)
    updated: date = Field(default_factory=date.today)
    body: str = ""

    def to_markdown(self) -> str:
        post = fm.Post(
            self.body,
            title=self.title,
            type=self.type,
            status=self.status,
            tags=self.tags,
            sources=self.sources,
            provenance=self.provenance.model_dump(),
            created=str(self.created),
            updated=str(self.updated),
        )
        return str(fm.dumps(post))

    @classmethod
    def from_markdown(cls, text: str) -> WikiPage:
        post = fm.loads(text)
        prov_raw: Any = post.get("provenance")
        prov: dict[str, Any] = prov_raw if isinstance(prov_raw, dict) else {}
        return cls(
            title=str(post["title"]),
            type=cast(PageType, post["type"]),
            status=cast(PageStatus, post.get("status", "draft")),
            tags=list(post.get("tags") or []),
            sources=list(post.get("sources") or []),
            provenance=ProvenanceBreakdown(**prov),
            created=post.get("created", date.today()),
            updated=post.get("updated", date.today()),
            body=str(post.content),
        )


@dataclass
class RawSource:
    """Frontmatter wrapper for raw source files (transcripts, clips, clipboard)."""

    title: str
    sources: list[str] = dc_field(default_factory=list)
    created: date = dc_field(default_factory=date.today)
    body: str = ""

    def to_markdown(self) -> str:
        post = fm.Post(
            self.body,
            title=self.title,
            type="ref",
            status="draft",
            sources=self.sources,
            created=str(self.created),
            updated=str(date.today()),
        )
        return str(fm.dumps(post))
