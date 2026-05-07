#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
echo "Starting LiteLLM proxy on port 4000 ..."
litellm --config configs/litellm_config.yaml --port 4000
