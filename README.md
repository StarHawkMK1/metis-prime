# second-brain

Personal knowledge management system (Metis Prime) built on Andrej Karpathy's LLM Wiki pattern.

## Setup

```bash
# Install dependencies
uv sync --dev

# Initialize a vault
uv run second-brain init ~/second-brain-vault

# Check vault status
uv run second-brain status
```

## Development

```bash
uv run pytest           # Run tests
uv run mypy src/        # Type check (strict)
uv run ruff check src/  # Lint
```

See `docs/spec/second-brain-spec.md` for the full project specification.
