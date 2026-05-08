# MCP Server Setup for Claude Code

The graphify MCP server exposes the vault knowledge graph directly to Claude Code,
enabling tools like `query_graph`, `get_node`, `get_neighbors`, and `shortest_path`.

## Prerequisites

1. Build the graph at least once:
   ```bash
   second-brain graph build --vault /path/to/vault
   ```
   This creates `vault/graph/graphify-out/graph.json`.

2. Confirm graphify is installed:
   ```bash
   graphify --version
   ```

## Start the MCP Server

```bash
SECOND_BRAIN_VAULT_PATH=/path/to/vault sh scripts/start_mcp_server.sh
```

Or run directly:
```bash
python -m graphify.serve /path/to/vault/graph/graphify-out/graph.json
```

## Register with Claude Code

Add to `~/.claude/claude_desktop_config.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "second-brain-graph": {
      "command": "python",
      "args": [
        "-m",
        "graphify.serve",
        "/absolute/path/to/vault/graph/graphify-out/graph.json"
      ]
    }
  }
}
```

Replace `/absolute/path/to/vault` with the actual vault path.

Or for a project-scoped MCP server, add to `.mcp.json` in the vault root:

```json
{
  "mcpServers": {
    "second-brain-graph": {
      "command": "python",
      "args": ["-m", "graphify.serve", "graph/graphify-out/graph.json"]
    }
  }
}
```

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `query_graph` | Full-text search over all graph nodes |
| `get_node` | Get a single node by ID |
| `get_neighbors` | Get neighbors within N hops |
| `shortest_path` | Find the shortest path between two nodes |

## Verify the Connection

In Claude Code, run:
```
/mcp
```
You should see `second-brain-graph` listed. Then try:
```
Use the query_graph tool to find nodes about "machine learning"
```

## LiteLLM Proxy Routing

graphify makes its own LLM calls (for entity extraction) using the Anthropic SDK.
To route these through the LiteLLM proxy instead of hitting the cloud directly, set:

```bash
export ANTHROPIC_BASE_URL=http://localhost:4000
export ANTHROPIC_API_KEY=dummy
```

before starting the MCP server or running `second-brain graph build`.

**Verification**: After running `graph build`, check LiteLLM proxy logs for
`POST /chat/completions` requests — they should appear for each markdown file processed.

## Keeping the Graph Fresh

Install the post-commit hook so the graph updates automatically on every vault commit:

```bash
python scripts/install_hooks.py
```

See the [Post-Commit Hook](#) section of the plan for details.
