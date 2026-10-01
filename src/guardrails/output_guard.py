"""
Output Guardrail node for the dispute triage graph.

Responsibilities:
1. Scan final agent response for sensitive customer data or PAN leakage.
2. Ensure no raw payment credentials reach the customer or external outputs.
3. Replace any uncovered card numbers with masked representations.
4. Record audited guardrail actions to logs/agent_actions.jsonl and OpenTelemetry spans.
"""

from typing import Any, Dict
from src.utils.masking import mask_text
from src.guardrails.action_logger import log_guardrail_action
from src.observability.tracing import trace_span


def evaluate_output_guardrail(text: str) -> Dict[str, Any]:
    """
    Sanitizes output text and detects if any sensitive information was masked.
    """
    sanitized = mask_text(text)
    leakage_prevented = sanitized != text
    return {
        "sanitized_text": sanitized,
        "leakage_prevented": leakage_prevented,
    }


def output_guard_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node for output guardrail evaluation."""
    raw_output = state.get("final_response") or state.get("synthesis_result") or ""

    with trace_span(
        name="output_guard",
        span_kind="GUARDRAIL",
        agent="output_guard",
        attributes={"guardrail.type": "output_guardrail"},
    ) as span:
        result = evaluate_output_guardrail(raw_output)

        flags = list(state.get("guardrail_flags", []))
        if result["leakage_prevented"]:
            flags.append("OUTPUT_LEAKAGE_MASKED")
            action = "MASK_SENSITIVE_OUTPUT"
            decision = "MASKED"
            action_flags = ["OUTPUT_LEAKAGE_MASKED"]
        else:
            action = "PERMIT_OUTPUT"
            decision = "ALLOWED"
            action_flags = ["CLEAN"]

        log_guardrail_action(
            agent="output_guard",
            action=action,
            decision=decision,
            guardrail_result=action_flags,
            details={
                "customer_id": state.get("customer_id", "N/A"),
                "transaction_id": state.get("transaction_id", "N/A"),
                "leakage_prevented": result["leakage_prevented"],
            },
        )

        span.set_attribute("guardrail.decision", decision)
        span.set_attribute("guardrail.flags", str(action_flags))

        return {
            "final_response": result["sanitized_text"],
            "guardrail_flags": list(set(flags)),
        }
