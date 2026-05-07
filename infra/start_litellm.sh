#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export VLLM_API_BASE="${VLLM_API_BASE:-http://localhost:8000/v1}"
echo "Starting LiteLLM proxy on port 4000 ..."
litellm --config configs/litellm_config.yaml --port 4000
