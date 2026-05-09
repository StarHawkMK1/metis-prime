from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from .agents.ingest import IngestAgent, IngestError
from .agents.lint import LintAgent
from .agents.query import QueryAgent
from .llm import LLMRouter
from .storage.git_ops import init_repo

app = typer.Typer(name="second-brain", help="Personal second brain CLI.")
note_app = typer.Typer(help="Note management commands.")
llm_app = typer.Typer(help="LLM router commands.")
app.add_typer(note_app, name="note")
app.add_typer(llm_app, name="llm")
graph_app = typer.Typer(help="Knowledge graph commands.")
app.add_typer(graph_app, name="graph")
review_app = typer.Typer(help="Human-in-the-loop review queue commands.")
app.add_typer(review_app, name="review")

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

Routing is governed by `task_type` and `sensitivity`. The policy is enforced in two layers:
1. `policy.select_model(task_type, sensitivity)` → selects logical model name
2. `policy.assert_local_or_raise(model, sensitivity)` → defense-in-depth guard

## Model Assignments

| Task type               | Sensitivity | Model        | Reason                         |
|-------------------------|-------------|--------------|--------------------------------|
| ingest_summary          | normal      | bulk         | High volume, cost-sensitive    |
| ingest_summary          | private     | local-fast   | Privacy override               |
| synthesis_complex       | normal      | smart-cloud  | Quality matters most           |
| synthesis_complex       | private     | local-fast   | Privacy override               |
| vision                  | normal      | vision-cheap | Multimodal capability          |
| vision                  | private     | local-fast   | Privacy override               |
| lint_check              | normal      | bulk         | High volume, cost-sensitive    |
| lint_check              | private     | local-fast   | Privacy override               |

## Logical Model Definitions

| Logical Name  | Provider   | Model ID              | Port  |
|---------------|------------|-----------------------|-------|
| local-fast    | vLLM       | Qwen3-8B-Instruct-AWQ | 8000  |
| smart-cloud   | Anthropic  | claude-opus-4-7       | cloud |
| vision-cheap  | Google     | gemini-2.5-pro        | cloud |
| bulk          | OpenAI     | gpt-5-mini            | cloud |

## Invariant

Any request with `sensitivity=private` MUST route to `local-fast`.
This is enforced at the router layer with a permanent property test.
`local_only=True` causes cloud-routed tasks to RAISE (not silently downgrade).
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


@app.command()
def status() -> None:
    """Show vault health: page count and inbox size."""
    from .config import Settings

    settings = Settings()
    vault_path = settings.vault_path.expanduser().resolve()

    if not vault_path.exists():
        console.print(f"[red]✗[/red] Vault not found: [bold]{vault_path}[/bold]")
        raise typer.Exit(1)

    wiki_pages = list((vault_path / "wiki").rglob("*.md")) if (vault_path / "wiki").exists() else []
    inbox_items = (
        [f for f in (vault_path / "raw" / "inbox").iterdir() if f.is_file()]
        if (vault_path / "raw" / "inbox").exists()
        else []
    )

    console.print(f"[bold]Vault:[/bold] {vault_path}")
    console.print(f"  Wiki pages : {len(wiki_pages)}")
    console.print(f"  Inbox items: {len(inbox_items)}")


@note_app.command("add")
def note_add(
    path: Annotated[
        str, typer.Argument(help="Relative path inside vault, e.g. wiki/concepts/foo.md")
    ],
    title: Annotated[str, typer.Option("--title", "-t", help="Page title (required)")],
    page_type: Annotated[
        str, typer.Option("--type", help="Page type (default: concept)")
    ] = "concept",
) -> None:
    """Create a new wiki page at the given vault-relative path."""
    from typing import cast

    from .config import Settings
    from .storage import Vault, WikiPage
    from .storage.frontmatter import PageType

    _valid_types = ("concept", "project", "person", "place", "ref", "map")
    if page_type not in _valid_types:
        console.print(
            f"[red]Invalid type[/red] '{page_type}'. Choose from: {', '.join(_valid_types)}"
        )
        raise typer.Exit(1)

    settings = Settings()
    vault = Vault(settings.vault_path)

    try:
        page = WikiPage(title=title, type=cast(PageType, page_type))
        written = vault.write_page(path, page)
        console.print(f"[green]✓[/green] Created [bold]{written}[/bold]")
    except (RuntimeError, ValueError) as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1) from exc


@llm_app.command("route")
def llm_route(
    task: Annotated[
        str,
        typer.Option(
            "--task", "-t", help="Task type (ingest_summary|synthesis_complex|vision|lint_check)"
        ),
    ],
    sensitivity: Annotated[
        str,
        typer.Option("--sensitivity", "-s", help="Sensitivity (normal|private)"),
    ] = "normal",
) -> None:
    """Show which model would be selected for a given task/sensitivity (dry-run)."""
    from typing import get_args

    from .llm.policy import select_model
    from .llm.types import Sensitivity, TaskType

    valid_tasks = get_args(TaskType)
    valid_sensitivities = get_args(Sensitivity)

    if task not in valid_tasks:
        console.print(f"[red]Invalid task[/red] '{task}'. Choose from: {', '.join(valid_tasks)}")
        raise typer.Exit(1)

    if sensitivity not in valid_sensitivities:
        console.print(
            f"[red]Invalid sensitivity[/red] '{sensitivity}'. "
            f"Choose from: {', '.join(valid_sensitivities)}"
        )
        raise typer.Exit(1)

    model = select_model(task, sensitivity)  # type: ignore[arg-type]
    console.print(
        f"[bold]Route:[/bold] task={task!r} sensitivity={sensitivity!r} → [green]{model}[/green]"
    )


@llm_app.command("test")
def llm_test() -> None:
    """Ping the LLM router with a fixed prompt (requires LiteLLM proxy running)."""
    from .llm.errors import RouterError

    router = LLMRouter()
    try:
        response = router.complete(
            [{"role": "user", "content": "Reply with exactly: pong"}],
            task_type="ingest_summary",
            sensitivity="normal",
        )
        console.print(f"[green]✓[/green] Router responded: [bold]{response}[/bold]")
    except RouterError as exc:
        console.print(f"[red]✗[/red] Router error: {exc}")
        raise typer.Exit(1) from exc
    except Exception as exc:
        console.print(f"[red]✗[/red] Unexpected error: {exc}")
        raise typer.Exit(1) from exc


@app.command()
def ingest(
    path: Annotated[str | None, typer.Argument(help="Vault-relative path to source file")] = None,
    inbox: Annotated[bool, typer.Option("--inbox", help="Process all files in raw/inbox/")] = False,
    sensitivity: Annotated[
        str, typer.Option("--sensitivity", "-s", help="normal|private")
    ] = "normal",
) -> None:
    """Ingest a raw source file (or the full inbox) into the wiki."""
    from .config import Settings
    from .storage import Vault

    if not path and not inbox:
        console.print("[red]✗[/red] Provide a file path or --inbox")
        raise typer.Exit(1)

    settings = Settings()
    vault = Vault(settings.vault_path)
    router = LLMRouter(settings=settings)
    agent = IngestAgent(vault=vault, router=router)

    def _do_ingest(rel: str) -> None:
        try:
            result = agent.run(rel, sensitivity=sensitivity)  # type: ignore[arg-type]
            console.print(
                f"[green]✓[/green] {result.decision}: [bold]{result.source_name}[/bold]"
                + (f" → {result.wiki_path}" if result.wiki_path else "")
            )
        except IngestError as exc:
            console.print(f"[red]✗[/red] {exc}")

    if inbox:
        inbox_dir = settings.vault_path.expanduser().resolve() / "raw" / "inbox"
        files = [f for f in inbox_dir.iterdir() if f.is_file()] if inbox_dir.exists() else []
        if not files:
            console.print("[yellow]Inbox is empty[/yellow]")
            return
        for f in files:
            rel = str(f.relative_to(settings.vault_path.expanduser().resolve())).replace("\\", "/")
            _do_ingest(rel)
    else:
        _do_ingest(path)  # type: ignore[arg-type]


@app.command()
def query(
    question: Annotated[str, typer.Argument(help="Natural language question")],
    sensitivity: Annotated[
        str, typer.Option("--sensitivity", "-s", help="normal|private")
    ] = "normal",
) -> None:
    """Ask a question; answer is synthesized from the wiki."""
    from .config import Settings
    from .storage import Vault

    settings = Settings()
    vault = Vault(settings.vault_path)
    router = LLMRouter(settings=settings)
    agent = QueryAgent(vault=vault, router=router)

    result = agent.ask(question, sensitivity=sensitivity)  # type: ignore[arg-type]
    console.print(result.answer)
    if result.sources:
        console.print("\n[dim]Sources: " + ", ".join(result.sources) + "[/dim]")


# ── Graph commands ────────────────────────────────────────────────────────────


@graph_app.command("build")
def graph_build(
    vault: Annotated[str, typer.Option(envvar="SECOND_BRAIN_VAULT_PATH", help="Vault root path")],
    update: bool = typer.Option(False, "--update", help="Incremental update only"),
    scope: str = typer.Option("wiki", "--scope", help="Scan scope: wiki | raw | all"),
) -> None:
    """Build (or incrementally update) the knowledge graph."""
    from .graph.builder import GraphBuilder

    builder = GraphBuilder(Path(vault))
    try:
        if update:
            path = builder.update(scope=scope)
            console.print(f"[green]Graph updated:[/green] {path}")
        else:
            path = builder.build(scope=scope)
            report = Path(vault) / "GRAPH_REPORT.md"
            console.print(f"[green]Graph built:[/green] {path}")
            if report.exists():
                console.print(f"[green]Report:[/green] {report}")
    except RuntimeError as exc:
        console.print(f"[red]Graph build failed:[/red] {exc}")
        raise typer.Exit(1) from exc


@graph_app.command("query")
def graph_query_cmd(
    question: Annotated[str, typer.Argument(help="Natural language question")],
    vault: Annotated[str, typer.Option(envvar="SECOND_BRAIN_VAULT_PATH", help="Vault root path")],
    depth: int = typer.Option(2, "--depth", "-d", help="Graph traversal depth"),
    sensitivity: str = typer.Option("normal", "--sensitivity", "-s", help="normal | private"),
) -> None:
    """Answer a question using graph-augmented wiki context."""
    from .agents.query import QueryAgent
    from .storage.vault import Vault as _Vault

    agent = QueryAgent(
        _Vault(Path(vault)),
        sensitivity=sensitivity,  # type: ignore[arg-type]
        graph_depth=depth,
    )
    result = agent.ask(question)
    console.print(result.answer)
    if result.sources:
        console.print(f"\n[dim]Sources: {', '.join(result.sources)}[/dim]")


@app.command()
def lint() -> None:
    """Scan the wiki for broken links, orphans, stale drafts, and provenance drift."""
    from .config import Settings
    from .storage import Vault

    settings = Settings()
    vault = Vault(settings.vault_path)
    agent = LintAgent(vault)
    report = agent.run()

    issue_count = len(report.issues)
    if issue_count == 0:
        console.print("[green]✓[/green] No issues found. Vault is healthy.")
    else:
        console.print(f"[yellow]⚠[/yellow] {issue_count} issue(s) found:")
        for issue in report.issues[:20]:
            console.print(f"  [{issue.kind}] {issue.page} — {issue.detail}")
        if issue_count > 20:
            console.print(f"  ... and {issue_count - 20} more. See journal/ for full report.")


# ── Review commands ────────────────────────────────────────────────────────────


@review_app.command("process")
def review_process() -> None:
    """Process human_review/accepted/ and human_review/rejected/ queues."""
    from .agents.graphs.human_review import process_review
    from .config import Settings
    from .storage.vault import Vault

    settings = Settings()
    vault = Vault(settings.vault_path)
    result = process_review(vault)
    typer.echo(f"Processed: {result.accepted} accepted, {result.rejected} rejected.")
