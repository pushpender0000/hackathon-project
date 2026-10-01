"""
Tests for loop boundary limits, step ceilings, and output guardrails.
"""

from src.agents.supervisor import supervisor_node, MAX_SUPERVISOR_ITERATIONS
from src.guardrails.output_guard import evaluate_output_guardrail


def test_supervisor_loop_limit_enforcement():
    """Supervisor must forcibly terminate and route to escalation if iteration limit is exceeded."""
    state = {
        "transaction": None,
        "iteration_count": MAX_SUPERVISOR_ITERATIONS + 1,
    }
    result = supervisor_node(state)
    assert result["next_worker"] == "escalation_gate"
    assert result["escalation_required"] is True
    assert "Loop limit exceeded" in result["escalation_reason"]


def test_output_guardrail_masks_pan():
    """Output guardrail must detect and mask any PAN leakage in LLM output."""
    leaked_text = "Your card 4532015098121001 will receive a provisional credit of $35.50."
    result = evaluate_output_guardrail(leaked_text)
    assert result["leakage_prevented"] is True
    assert "4532015098121001" not in result["sanitized_text"]
    assert "****-****-****-1001" in result["sanitized_text"]


def test_output_guardrail_clean_text():
    """Output guardrail leaves non-sensitive text unaltered."""
    clean_text = "Your dispute has been processed under rule SYNTH-RULE-10.4."
    result = evaluate_output_guardrail(clean_text)
    assert result["leakage_prevented"] is False
    assert result["sanitized_text"] == clean_text
