#!/bin/sh
# Start the graphify MCP server for Claude Code integration.
# Usage: SECOND_BRAIN_VAULT_PATH=/path/to/vault sh scripts/start_mcp_server.sh
set -e

VAULT="${SECOND_BRAIN_VAULT_PATH:?SECOND_BRAIN_VAULT_PATH must be set}"
GRAPH_JSON="$VAULT/graph/graphify-out/graph.json"

if [ ! -f "$GRAPH_JSON" ]; then
    echo "Error: graph.json not found at $GRAPH_JSON"
    echo "Run: second-brain graph build --vault $VAULT"
    exit 1
fi

echo "Starting graphify MCP server on graph: $GRAPH_JSON"
python -m graphify.serve "$GRAPH_JSON"
