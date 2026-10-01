"""
Input Guardrail node for the dispute triage graph.

Responsibilities:
1. Mask/sanitize raw sensitive data (PANs, account numbers) using deterministic regex.
2. Detect instruction-injection / system-override attempts in customer input.
3. Quarantine customer input in structured delimiters so it cannot alter LLM system instructions.
4. Flag security anomalies for immediate escalation.
5. Record audited guardrail actions to logs/agent_actions.jsonl and OpenTelemetry spans.
"""

import re
from typing import Any, Dict, List
from src.utils.masking import mask_text
from src.guardrails.action_logger import log_guardrail_action
from src.observability.tracing import trace_span

INJECTION_PATTERNS = [
    r"system\s*override",
    r"ignore\s*(all\s*)?(previous|prior)\s*instructions",
    r"clear\s*fraud\s*score",
    r"credit\s*\$?[0-9,]+\s*immediately",
    r"bypass\s*security",
    r"you\s*are\s*now\s*a",
    r"act\s*as\s*(a\s*)?system\s*admin",
]

COMPILED_INJECTION_REGEX = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def evaluate_input_guardrail(raw_text: str) -> Dict[str, Any]:
    """
    Evaluates raw customer input for security threats and sensitive data.
    Returns:
        - quarantined_text: string wrapped in XML quarantine delimiters with sensitive data masked
        - guardrail_flags: list of triggered security flags
        - security_violation: boolean flag indicating an active prompt injection attack
    """
    flags: List[str] = []
    
    # 1. Mask sensitive PANs/accounts
    masked_content = mask_text(raw_text)
    if masked_content != raw_text:
        flags.append("SENSITIVE_DATA_MASKED")

    # 2. Check for Prompt Injection / System Override
    security_violation = False
    if COMPILED_INJECTION_REGEX.search(raw_text):
        flags.append("PROMPT_INJECTION_DETECTED")
        security_violation = True

    # 3. Quarantine customer input
    quarantined = (
        f"<customer_untrusted_claim>\n"
        f"{masked_content.strip()}\n"
        f"</customer_untrusted_claim>"
    )

    return {
        "quarantined_text": quarantined,
        "guardrail_flags": flags,
        "security_violation": security_violation,
    }


def input_guard_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node for input guardrail evaluation."""
    raw_input = state.get("raw_customer_input", "")

    with trace_span(
        name="input_guard",
        span_kind="GUARDRAIL",
        agent="input_guard",
        attributes={"guardrail.type": "input_guardrail"},
    ) as span:
        result = evaluate_input_guardrail(raw_input)
        
        existing_flags = list(state.get("guardrail_flags", []))
        existing_flags.extend(result["guardrail_flags"])

        # Determine audited action and decision for logs/agent_actions.jsonl
        if result["security_violation"]:
            action = "BLOCK_PROMPT_INJECTION"
            decision = "BLOCKED"
            flags = result["guardrail_flags"]
        elif "SENSITIVE_DATA_MASKED" in result["guardrail_flags"]:
            action = "SANITIZE_AND_QUARANTINE_INPUT"
            decision = "MASKED"
            flags = result["guardrail_flags"]
        else:
            action = "QUARANTINE_UNTRUSTED_INPUT"
            decision = "ALLOWED"
            flags = ["CLEAN"]

        log_guardrail_action(
            agent="input_guard",
            action=action,
            decision=decision,
            guardrail_result=flags,
            details={
                "customer_id": state.get("customer_id", "N/A"),
                "transaction_id": state.get("transaction_id", "N/A"),
                "quarantined": True,
            },
        )

        span.set_attribute("guardrail.decision", decision)
        span.set_attribute("guardrail.flags", json_flags := str(flags))

        updates: Dict[str, Any] = {
            "quarantined_text": result["quarantined_text"],
            "guardrail_flags": list(set(existing_flags)),
        }

        if result["security_violation"]:
            updates["escalation_required"] = True
            updates["escalation_reason"] = "Security injection attack pattern detected in customer input"
            updates["recommended_action"] = "investigate"
            updates["precedence_level"] = 2  # Security anomaly

        return updates


def input_guard_conditional_edge(state: Dict[str, Any]) -> str:
    """
    Evaluates whether input guardrail flagged a security anomaly or malicious injection.
    If flagged, skips context loading, MCP calls, RAG, and Gemini calls entirely,
    routing straight to escalation_gate.
    """
    flags = state.get("guardrail_flags", [])
    if "PROMPT_INJECTION_DETECTED" in flags or state.get("escalation_required"):
        return "escalation_gate"
    return "load_context"
