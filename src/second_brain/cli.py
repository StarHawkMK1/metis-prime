from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from .storage.git_ops import init_repo

app = typer.Typer(name="second-brain", help="Personal second brain CLI.")
note_app = typer.Typer(help="Note management commands.")
app.add_typer(note_app, name="note")

console = Console()

# ── Vault directory layout (SPEC §4) ──────────────────────────────────────────

_VAULT_DIRS = [
    "_meta",
    "raw/inbox",
    "raw/clips",
    "raw/transcripts",
    "raw/screenshots",
    "raw/archived",
    "wiki/concepts",
    "wiki/projects",
    "wiki/people",
    "wiki/places",
    "wiki/refs",
    "wiki/maps",
    "tasks",
    "journal",
    "graph",
]

_VAULT_GITIGNORE = """\
graph/
.obsidian/workspace*
.obsidian/cache
.DS_Store
"""

# ── Vault meta-file templates ─────────────────────────────────────────────────

_SCHEMA_MD = """\
# Second Brain — Operating Schema

## You are the wiki maintainer

You are an LLM agent maintaining a personal knowledge wiki. Your goal is to compile
incoming raw material into a structured, interlinked, human-readable markdown wiki.

## Core directories

- `raw/` — IMMUTABLE. Source material. NEVER modify or delete files here.
- `wiki/` — Your workspace. Create, edit, link freely.
- `_meta/` — Schema, taxonomy, policies. Edit only when explicitly asked.
- `tasks/`, `journal/` — Append-mostly. Modify only your own previous entries.

## Wiki page structure

Every wiki page MUST have frontmatter:

```yaml
---
title: <Title Case>
type: concept | project | person | place | ref | map
status: draft | active | archived
tags: [tag1, tag2]   # use only tags from _meta/taxonomy.md
sources: [raw/clips/2026-05-06-article.md, ...]
provenance:
  extracted: 70   # % from sources verbatim/paraphrase
  inferred: 25    # % your synthesis
  ambiguous: 5    # % sources disagree
created: 2026-05-06
updated: 2026-05-06
---
```

Body structure:

1. **One-sentence definition** (first line after frontmatter).
2. **Summary** (2-4 sentences).
3. **Sections** (markdown headings). Each claim either:
   - Cites a source: `... according to [[ref/some-paper]] ^[extracted]`
   - Tags inference: `... which suggests Y ^[inferred]`
   - Tags uncertainty: `... but [[ref/A]] and [[ref/B]] disagree ^[ambiguous]`
4. **Related** (auto-generated from wikilinks).

## Operations

### Ingest
1. Read the new source from `raw/`.
2. Extract atomic concepts.
3. For each concept: search existing wiki for similar pages.
   - If similar exists → merge (preserve both perspectives if conflicting).
   - If new → create page.
4. Add wikilinks to related pages (bi-directional where natural).
5. Move source to `raw/archived/` after successful ingest.
6. Commit with message: `ingest: <source-name>`.

### Query
1. Classify intent (factual / synthesis / task).
2. Use graph traversal first (graphify), wiki text second, raw source last.
3. Always cite sources in answers.
4. If answer required reading 3+ pages, suggest creating a new "synthesis" page.

### Lint
1. Find broken wikilinks.
2. Find orphan pages (no incoming/outgoing links).
3. Find pages with `inferred > 70%` (possible hallucination).
4. Find contradictions across pages on same topic.
5. Output report to `journal/lint-YYYY-MM-DD.md`.

## Routing rules (which model to call)

| Task                    | Model         | Reason                           |
|-------------------------|---------------|----------------------------------|
| ingest summary          | bulk          | Volume; Qwen falls back local    |
| ingest of `private` tag | local-fast    | Privacy; never cloud             |
| concept synthesis       | smart-cloud   | Quality matters most             |
| lint contradiction scan | bulk          | Volume                           |
| vision/PDF extraction   | vision-cheap  | Multimodal                       |
| graphify LLM extraction | bulk          | Volume                           |

NEVER use cloud models when sensitivity=private. Caller must pass this flag.

## Hard rules

- NEVER write to `raw/`.
- NEVER delete a wiki page without user confirmation.
- NEVER guess a wikilink target — verify the page exists or mark `^[ambiguous]`.
- ALWAYS update frontmatter `updated:` field on edit.
- ALWAYS commit after edits with descriptive message.
- If contradiction found, DO NOT silently choose — record both with `^[ambiguous]`.

## Style

- Crisp, encyclopedic. No marketing fluff.
- Past-tense for events, present-tense for concepts.
- Prefer concrete examples over abstract definitions.
- Code blocks for commands; LaTeX for math.
- One concept per page, but link liberally.
"""

_TAXONOMY_MD = """\
# Taxonomy — Controlled Vocabulary

All wiki pages must use tags from this list only.
To add a new tag: append to the relevant section and commit.

## Page Types (match `type` frontmatter field)

- `concept` — an idea, technology, term, or principle
- `project` — an ongoing or completed initiative
- `person` — a person (contact, author, public figure)
- `place` — a physical or virtual location
- `ref` — external reference (book, paper, video, article)
- `map` — a hub note; entry point to a topic cluster

## Status

- `draft` — incomplete; not yet reviewed
- `active` — current and actively maintained
- `archived` — no longer relevant; kept for history

## Domain Tags

- `work` — professional / career-related
- `personal` — personal life / health / finance
- `learning` — courses, books, skill development
- `research` — investigation or exploration of a topic
- `tool` — software, hardware, or service
- `ai` — artificial intelligence / machine learning
- `code` — software development / programming
- `writing` — writing, communication, content creation

## Sensitivity

- `private` — MUST NOT be routed to cloud LLMs (enforced by router)
- `public` — safe for any model

## Meta

- `stub` — page exists but needs expansion
- `needs-source` — claims lack citations
- `contradiction` — conflicts with another page; pending resolution
"""

_ROUTING_POLICY_MD = """\
# Routing Policy

Routing policy is configured in Phase 2 (LLM Router). See SPEC §5.2.

## Phase 1 Behavior

No LLM routing is active in Phase 1. All LLM calls raise `NotImplementedError`.

## Invariant (enforced from Phase 2 onward)

Any page or request tagged `private` MUST NOT be sent to a cloud API.
This is enforced at the router layer and has a permanent unit test.

## Phase 2 Model Assignments

| Task type              | Model       |
|------------------------|-------------|
| ingest_summary (normal)| bulk        |
| ingest_summary (private)| local-fast |
| synthesis_complex      | smart-cloud |
| vision                 | vision-cheap|
| lint_check             | bulk        |
"""

_CHANGELOG_MD = """\
# Vault Changelog

Structural changes to the vault (new sections, taxonomy updates, major reorganizations).
Day-to-day content edits are tracked by `git log`.

| Date | Change | Author |
|------|--------|--------|
| INIT | Vault initialized | second-brain init |
"""


# ── CLI commands ──────────────────────────────────────────────────────────────


@app.command()
def init(
    vault_path: Annotated[Path, typer.Argument(help="Path where the new vault will be created.")],
) -> None:
    """Initialize a new vault with directory structure, meta files, and git repo."""
    vault_path = vault_path.expanduser().resolve()
    vault_path.mkdir(parents=True, exist_ok=True)

    for subdir in _VAULT_DIRS:
        (vault_path / subdir).mkdir(parents=True, exist_ok=True)

    (vault_path / ".gitignore").write_text(_VAULT_GITIGNORE, encoding="utf-8")
    (vault_path / "_meta" / "schema.md").write_text(_SCHEMA_MD, encoding="utf-8")
    (vault_path / "_meta" / "taxonomy.md").write_text(_TAXONOMY_MD, encoding="utf-8")
    (vault_path / "_meta" / "routing-policy.md").write_text(_ROUTING_POLICY_MD, encoding="utf-8")
    (vault_path / "_meta" / "changelog.md").write_text(_CHANGELOG_MD, encoding="utf-8")

    if not (vault_path / ".git").exists():
        init_repo(vault_path)

    console.print(f"[green]✓[/green] Vault initialized at [bold]{vault_path}[/bold]")
