"""Per-million-token prices (USD) used by the cost ledger (spec 32). Update when prices change."""

from __future__ import annotations

from shunya.core.models.base import Usage

# model: (input, output, cache_read, cache_write)
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-fable-5-1": (10.0, 50.0, 0.25, 12.5),
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-opus-5": (5.0, 25.0, 0.50, 6.25),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.5),
    "claude-haiku-4-5": (1.0, 5.0, 0.10, 1.25),
}


def cost_usd(model: str, usage: Usage) -> float:
    price = PRICES.get(model)
    if price is None:
        # unknown / local / scripted models are free; real unknown cloud models are priced like Opus
        price = (0.0, 0.0, 0.0, 0.0) if model.startswith(("scripted", "local")) else PRICES["claude-opus-5-5"]
    p_in, p_out, p_cr, p_cw = price
    return (
        usage.input_tokens * p_in
        + usage.output_tokens * p_out
        + usage.cache_read_tokens * p_cr
        + usage.cache_write_tokens * p_cw
    ) / 1_000_000
