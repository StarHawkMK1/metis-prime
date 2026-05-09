from __future__ import annotations

# (input_usd_per_1m_tokens, output_usd_per_1m_tokens)
PRICING: dict[str, tuple[float, float]] = {
    "claude-3-haiku-20240307": (0.25, 1.25),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (0.80, 4.00),
    # Local models — zero marginal cost
    "qwen3:30b-a3b": (0.0, 0.0),
    "qwen3:8b": (0.0, 0.0),
    # Policy aliases (what select_model() returns)
    "bulk": (0.80, 4.00),  # claude-haiku-4-5 rates
    "smart-cloud": (3.00, 15.00),  # claude-sonnet-4-5 rates
    "vision-cheap": (0.80, 4.00),  # claude-haiku-4-5 rates
    "local-fast": (0.0, 0.0),  # local model, zero cost
}


def compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return USD cost for one LLM call. Returns 0.0 for unknown or local models."""
    if model not in PRICING:
        return 0.0
    in_rate, out_rate = PRICING[model]
    return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000
