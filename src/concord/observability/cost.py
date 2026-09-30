"""Rough LLM cost estimation from token counts, using configurable
per-million-token rates (see concord.config.Settings). Intentionally
approximate — real billing depends on the account's actual rate, which
this project has no API access to read. The point is relative cost
visibility across runs, not exact accounting."""

from concord.config import settings


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    input_cost = (input_tokens / 1_000_000) * settings.llm_input_cost_per_mtok
    output_cost = (output_tokens / 1_000_000) * settings.llm_output_cost_per_mtok
    return round(input_cost + output_cost, 6)
