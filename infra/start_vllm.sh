#!/usr/bin/env bash
set -euo pipefail

MODEL="${VLLM_MODEL:-Qwen/Qwen3-8B-Instruct-AWQ}"
PORT="${VLLM_PORT:-8000}"

echo "Starting vLLM: model=${MODEL} port=${PORT}"

vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --quantization awq \
  --max-model-len 32768 \
  --served-model-name qwen3-local \
  --gpu-memory-utilization 0.9

# GPU memory fallback: if the above fails on low VRAM, retry with a smaller model:
# VLLM_MODEL=Qwen/Qwen3-4B-Instruct-AWQ bash infra/start_vllm.sh
