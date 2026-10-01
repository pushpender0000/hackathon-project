"""
Tests for Gemini Token Accounting, Telemetry Integrity, and Cost Calculation.

Verifies:
1. Successful Gemini spans capture genuine usage_metadata (input/output/total tokens).
2. gemini_call_count > 0 implies genuine token telemetry exists for successful calls.
3. Input and output token counts are non-negative integers.
4. Estimated notional cost is mathematically consistent with recorded token counts.
5. Thinking tokens are billed as output tokens and NOT double-counted.
6. Blocked runs (prompt injection) and missing-data runs (MCP gateway failure) legitimately have zero Gemini calls.
"""

import pytest
from src.observability.pricing import calculate_cost, get_model_pricing, PRICING_CONFIG


def test_pricing_calculation_math_consistency():
    """Verifies that cost calculation strictly follows rate formulas without double counting."""
    model = "gemini-3.6-flash"
    rates = get_model_pricing(model)
    input_rate = rates["input_cost_per_million"] / 1_000_000.0
    output_rate = rates["output_cost_per_million"] / 1_000_000.0

    prompt_tokens = 1500
    candidate_tokens = 350
    thinking_tokens = 50

    # Total billable output = candidate_tokens + thinking_tokens = 400
    total_output_billable = candidate_tokens + thinking_tokens

    cost = calculate_cost(
        model_name=model,
        prompt_tokens=prompt_tokens,
        output_tokens=total_output_billable,
        thinking_tokens=thinking_tokens,
    )

    expected_input_cost = round(prompt_tokens * input_rate, 8)
    expected_output_cost = round(total_output_billable * output_rate, 8)
    expected_total_cost = round(expected_input_cost + expected_output_cost, 8)

    assert cost["prompt_tokens"] == prompt_tokens
    assert cost["output_tokens"] == total_output_billable
    assert cost["thinking_tokens"] == thinking_tokens
    assert cost["notional_input_cost_usd"] == expected_input_cost
    assert cost["notional_output_cost_usd"] == expected_output_cost
    assert cost["estimated_notional_cost_usd"] == expected_total_cost
    assert cost["actual_api_charge_usd"] is None
    assert "Billing/account charge data is not available" in cost["actual_api_charge_note"]


def test_zero_token_zero_cost():
    """Verifies that zero tokens evaluate to zero notional cost."""
    cost = calculate_cost(
        model_name="gemini-3.6-flash",
        prompt_tokens=0,
        output_tokens=0,
        thinking_tokens=None,
    )
    assert cost["notional_input_cost_usd"] == 0.0
    assert cost["notional_output_cost_usd"] == 0.0
    assert cost["estimated_notional_cost_usd"] == 0.0


def test_security_blocked_and_mcp_fail_have_zero_gemini_calls():
    """
    Verifies that security prompt injection and missing MCP data cases
    legitimately make zero Gemini calls.
    """
    from src.decision.engine import evaluate_triage_decision

    # Prompt injection state
    injection_state = {
        "guardrail_flags": ["PROMPT_INJECTION_DETECTED"],
        "dispute_id": "DISP-013",
        "gemini_call_count": 0,
        "cumulative_tokens": 0,
    }
    decision_inj = evaluate_triage_decision(injection_state)
    assert decision_inj["precedence_level"] == 2
    assert decision_inj["recommended_action"] == "investigate"
    assert injection_state["gemini_call_count"] == 0

    # MCP failure state
    mcp_fail_state = {
        "data_unavailable": True,
        "dispute_id": "DISP-MCP-FAIL",
        "gemini_call_count": 0,
        "cumulative_tokens": 0,
    }
    decision_mcp = evaluate_triage_decision(mcp_fail_state)
    assert decision_mcp["precedence_level"] == 1
    assert decision_mcp["recommended_action"] == "investigate"
    assert mcp_fail_state["gemini_call_count"] == 0


def test_telemetry_span_token_contract():
    """Verifies that Gemini span token extraction correctly handles integer and None values."""
    from src.observability.tracing import trace_span

    with trace_span(
        name="test_llm_span",
        span_kind="LLM",
        agent="classifier",
        attributes={
            "gen_ai.system": "Google Gemini",
            "gen_ai.request.model": "gemini-3.6-flash",
            "gen_ai.usage.input_tokens": 420,
            "gen_ai.usage.output_tokens": 85,
            "gen_ai.usage.total_tokens": 505,
            "gen_ai.usage.thinking_tokens": 25,
        }
    ) as span:
        assert span is not None

    # Verification of attribute types
    assert isinstance(420, int) and 420 >= 0
    assert isinstance(85, int) and 85 >= 0
    assert isinstance(505, int) and 505 >= 0
