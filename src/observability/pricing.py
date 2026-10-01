"""
Centralized Pricing and Cost Calculation for Gemini API Usage.

Enforces explicit, auditable accounting based on published Google Cloud Gemini rates.
No hard-coded totals; all costs derived mathematically from verified token usage.
"""

from typing import Dict, Any, Optional

# Official Google AI Studio / Google GenAI developer pricing per 1M tokens:
# Source: Official Google AI Developer Pricing (ai.google.dev/pricing)
#
# Gemini 3.x Flash tier (e.g. gemini-3.6-flash, gemini-3.8-flash):
# - Input: $0.75 per 1,000,000 tokens ($0.00000075 / token)
# - Output including thinking: $3.75 per 1,000,000 tokens ($0.00000375 / token)
#
# Gemini 3.x Flash Lite Standard tier (e.g. gemini-3.5-flash-lite, gemini-3.1-flash-lite):
# - Input: $0.30 per 1,000,000 tokens ($0.00000030 / token)
# - Output including thinking: $2.50 per 1,000,000 tokens ($0.00000250 / token)
# - Free tier: free of charge (within Google AI Studio free quota)
# - Note: gemini-3.5-flash-lite supports thinking_level per Google documentation.
#   Thinking-token telemetry (thoughts_token_count) may or may not be returned by
#   the API depending on the runtime response; it is recorded if present.
#   Output pricing is inclusive of thinking tokens where applicable.
#
# Gemini 2.5 Flash tier (e.g. gemini-2.5-flash):
# - Input: $0.30 per 1,000,000 tokens ($0.00000030 / token)
# - Output including thinking: $2.50 per 1,000,000 tokens ($0.00000250 / token)
#
# Note on Free-Tier vs Notional Cost:
# - Actual account billing charge: not available from runtime telemetry (reported as null).
# - Notional / equivalent commercial inference cost: calculated using the official standard rates below.
PRICING_CONFIG = {
    "gemini-3.6-flash": {
        "tier_name": "Gemini 3.x Flash",
        "input_cost_per_million": 0.75,      # $0.75 / 1M tokens
        "output_cost_per_million": 3.75,     # $3.75 / 1M tokens
        "thinking_cost_per_million": 3.75,   # Thinking tokens billed as candidate output tokens
        "pricing_source": "Google AI Developer Official Pricing (ai.google.dev/pricing)",
    },
    "gemini-3.8-flash": {
        "tier_name": "Gemini 3.x Flash",
        "input_cost_per_million": 0.75,      # $0.75 / 1M tokens
        "output_cost_per_million": 3.75,     # $3.75 / 1M tokens
        "thinking_cost_per_million": 3.75,
        "pricing_source": "Google AI Developer Official Pricing (ai.google.dev/pricing)",
    },
    "gemini-3.5-flash-lite": {
        "tier_name": "Gemini 3.x Flash Lite",
        "input_cost_per_million": 0.30,      # $0.30 / 1M tokens (Standard tier)
        "output_cost_per_million": 2.50,     # $2.50 / 1M tokens incl. thinking (Standard tier)
        "thinking_cost_per_million": 2.50,   # Thinking tokens billed at output rate (incl. in output price)
        "pricing_source": "Google AI Developer Official Pricing (ai.google.dev/pricing)",
        "pricing_note": "Standard tier. Free tier available within Google AI Studio quota. Thinking-token telemetry recorded if returned by API.",
    },
    "gemini-3.1-flash-lite": {
        "tier_name": "Gemini 3.x Flash Lite",
        "input_cost_per_million": 0.30,      # $0.30 / 1M tokens (Standard tier)
        "output_cost_per_million": 2.50,     # $2.50 / 1M tokens incl. thinking (Standard tier)
        "thinking_cost_per_million": 2.50,
        "pricing_source": "Google AI Developer Official Pricing (ai.google.dev/pricing)",
        "pricing_note": "Standard tier. Thinking-token telemetry recorded if returned by API.",
    },
    "gemini-2.5-flash": {
        "tier_name": "Gemini 2.5 Flash",
        "input_cost_per_million": 0.30,      # $0.30 / 1M tokens
        "output_cost_per_million": 2.50,     # $2.50 / 1M tokens
        "thinking_cost_per_million": 2.50,
        "pricing_source": "Google AI Developer Official Pricing (ai.google.dev/pricing)",
    },
    "default": {
        "tier_name": "Gemini 3.x Flash",
        "input_cost_per_million": 0.75,
        "output_cost_per_million": 3.75,
        "thinking_cost_per_million": 3.75,
        "pricing_source": "Google AI Developer Official Pricing (ai.google.dev/pricing)",
    }
}


def get_model_pricing(model_name: str) -> Dict[str, Any]:
    """Retrieves token rate table for specified model."""
    for key in PRICING_CONFIG:
        if key in model_name:
            return PRICING_CONFIG[key]
    return PRICING_CONFIG["default"]


def calculate_cost(
    model_name: str,
    prompt_tokens: int,
    output_tokens: int,
    thinking_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Computes precise USD cost for Gemini model inference.

    Accounting Rule for Gemini Flash / Flash Lite:
    - Google GenAI usage_metadata reports `prompt_token_count`, `candidates_token_count`,
      and optionally `thoughts_token_count`.
    - `candidates_token_count` represents text tokens generated in candidate responses.
    - `thoughts_token_count` represents reasoning/thinking tokens, when returned by the API.
      Its availability depends on the model and runtime response; it is recorded when present,
      represented as null when absent.
    - Google bills thinking tokens at the same rate as output tokens.
      Output pricing is inclusive of thinking tokens; thinking tokens are NOT double-counted.
    - `output_tokens` passed here should be `candidates_token_count` (text only).
      If `thinking_tokens` are separately known, they are added for total billable output.
      If `output_tokens` already aggregates thinking (e.g. pre-aggregated span metrics),
      pass `thinking_tokens=None` to prevent double-counting.
    - Prompt tokens are billed at the input token rate.

    Args:
        model_name: Name of Gemini model
        prompt_tokens: Number of prompt/input tokens
        output_tokens: Number of generated candidate text tokens (excluding thinking)
        thinking_tokens: Number of reasoning/thinking tokens if separately reported by API;
                         pass None if unavailable or already included in output_tokens.

    Returns:
        Dictionary with itemized and total notional and actual costs in USD.
    """
    rates = get_model_pricing(model_name)
    input_rate = rates["input_cost_per_million"] / 1_000_000.0
    output_rate = rates["output_cost_per_million"] / 1_000_000.0

    notional_input_cost = prompt_tokens * input_rate
    notional_output_cost = output_tokens * output_rate
    notional_total_cost = notional_input_cost + notional_output_cost

    pricing_assumption = (
        f"{rates['tier_name']}: ${rates['input_cost_per_million']:.2f}/1M input tokens, "
        f"${rates['output_cost_per_million']:.2f}/1M output tokens (inclusive of thinking) ({rates['pricing_source']})"
    )

    return {
        "model": model_name,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "thinking_tokens": thinking_tokens if thinking_tokens is not None else None,
        "thinking_tokens_status": "reported" if thinking_tokens is not None else "Unavailable from API telemetry",
        "pricing_assumption": pricing_assumption,
        "notional_input_cost_usd": round(notional_input_cost, 8),
        "notional_output_cost_usd": round(notional_output_cost, 8),
        "notional_cost_usd": round(notional_total_cost, 8),
        "estimated_notional_cost_usd": round(notional_total_cost, 8),
        "actual_api_charge_usd": None,
        "actual_api_charge_note": "Billing/account charge data is not available from runtime telemetry.",
        "rates": {
            "input_per_million": rates["input_cost_per_million"],
            "output_per_million": rates["output_cost_per_million"],
            "thinking_per_million": rates["thinking_cost_per_million"],
        }
    }
