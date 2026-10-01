"""
Deterministic Decision Engine.

Evaluates triage state according to strict, non-overridable banking precedence:
1. Required data unavailable / MCP failure -> investigate & escalate
2. Ambiguous intent / security anomaly -> investigate & escalate
3. Mandatory human escalation (amount > $1000 OR fraud_score >= 80 OR chronic disputes > 5) -> investigate & escalate
4. Expired synthetic filing window -> deny
5. Fast-track low-risk provisional credit (amount <= $150 AND fraud_score <= 30) -> provisional_credit
6. Otherwise -> chargeback (when valid synthetic policy criteria are met)
"""

from typing import Any, Dict
from src.config.settings import get_settings


def evaluate_triage_decision(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates triage state deterministically using prioritized precedence tiers.
    Returns:
        recommended_action: 'investigate', 'deny', 'provisional_credit', or 'chargeback'
        escalation_required: bool
        escalation_reason: str or None
        precedence_level: int (1 through 6)
    """
    settings = get_settings()

    # Context values
    tx = state.get("transaction") or {}
    cust = state.get("customer_history") or {}
    amount = float(state.get("extracted_amount") or tx.get("amount") or 0.0)
    fraud_score = float(state.get("fraud_score") if state.get("fraud_score") is not None else 50.0)
    prior_disputes = int(cust.get("total_prior_disputes", 0))
    category = state.get("dispute_category", "ambiguous_inquiry")
    guardrail_flags = state.get("guardrail_flags", [])

    # Timing & filing window
    max_days = int(state.get("max_filing_days") or 120)
    # days_elapsed may be passed in audit_metadata or dispute context
    audit_meta = state.get("audit_metadata") or {}
    days_elapsed = int(audit_meta.get("days_elapsed") or 0)

    # -------------------------------------------------------------
    # PRECEDENCE 1: Required Data Unavailable / System or MCP Failure
    # -------------------------------------------------------------
    if state.get("data_unavailable") or state.get("policy_retrieval_failed"):
        reason = state.get("escalation_reason") or "Required banking data unavailable or MCP retrieval failure"
        return {
            "recommended_action": "investigate",
            "escalation_required": True,
            "escalation_reason": reason,
            "precedence_level": 1,
        }

    # -------------------------------------------------------------
    # PRECEDENCE 2: Ambiguous Intent / Security Anomaly
    # -------------------------------------------------------------
    if "PROMPT_INJECTION_DETECTED" in guardrail_flags:
        return {
            "recommended_action": "investigate",
            "escalation_required": True,
            "escalation_reason": "Security injection attack pattern detected in customer input",
            "precedence_level": 2,
        }

    if category == "ambiguous_inquiry" or state.get("customer_intent") in ("unclear", "ambiguous"):
        return {
            "recommended_action": "investigate",
            "escalation_required": True,
            "escalation_reason": "Ambiguous customer inquiry: insufficient clarity to file automated dispute",
            "precedence_level": 2,
        }

    # -------------------------------------------------------------
    # PRECEDENCE 3: Mandatory Human Escalation Thresholds
    # - High Value: amount > $1000.00
    # - High Risk: fraud_score >= 80.0
    # - Chronic Disputes: prior_disputes > 5
    # -------------------------------------------------------------
    reasons_p3 = []
    if amount > settings.high_value_escalation_amount:
        reasons_p3.append(f"High-value transaction (${amount:.2f} > ${settings.high_value_escalation_amount:.2f})")
    if fraud_score >= settings.fraud_score_high_risk_threshold:
        reasons_p3.append(f"High fraud risk score ({fraud_score:.1f} >= {settings.fraud_score_high_risk_threshold:.1f})")
    if prior_disputes > settings.chronic_dispute_count_threshold:
        reasons_p3.append(f"Chronic dispute history ({prior_disputes} disputes > {settings.chronic_dispute_count_threshold})")

    if reasons_p3:
        return {
            "recommended_action": "investigate",
            "escalation_required": True,
            "escalation_reason": "Mandatory escalation criteria met: " + "; ".join(reasons_p3),
            "precedence_level": 3,
        }

    # -------------------------------------------------------------
    # PRECEDENCE 4: Expired Synthetic Filing Window
    # -------------------------------------------------------------
    if days_elapsed > max_days:
        return {
            "recommended_action": "deny",
            "escalation_required": False,
            "escalation_reason": f"Dispute filing window expired ({days_elapsed} days elapsed > {max_days} days limit)",
            "precedence_level": 4,
        }

    # -------------------------------------------------------------
    # PRECEDENCE 5: Fast-Track Low-Risk Provisional Credit
    # - amount <= $150.00
    # - fraud_score <= 30.0
    # -------------------------------------------------------------
    if amount <= settings.provisional_credit_max_amount and fraud_score <= settings.low_risk_fraud_score_max:
        return {
            "recommended_action": "provisional_credit",
            "escalation_required": False,
            "escalation_reason": None,
            "precedence_level": 5,
        }

    # -------------------------------------------------------------
    # PRECEDENCE 6: Valid Synthetic Chargeback
    # -------------------------------------------------------------
    rule_id = state.get("selected_rule_id")
    if rule_id and not state.get("policy_retrieval_failed"):
        return {
            "recommended_action": "chargeback",
            "escalation_required": False,
            "escalation_reason": None,
            "precedence_level": 6,
        }

    # Default fallback if no other condition met
    return {
        "recommended_action": "investigate",
        "escalation_required": True,
        "escalation_reason": "Unclassified state fallback to human investigator",
        "precedence_level": 1,
    }


from src.observability.tracing import trace_span


def decision_engine_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node for Deterministic Decision Engine."""
    with trace_span(
        name="decision_engine",
        span_kind="AGENT",
        agent="decision_engine",
        attributes={"agent.role": "deterministic_decision_engine"},
    ) as span:
        decision = evaluate_triage_decision(state)
        span.set_attribute("decision.action", str(decision.get("recommended_action")))
        span.set_attribute("decision.precedence_tier", int(decision.get("precedence_level") or 1))
        span.set_attribute("decision.escalation", bool(decision.get("escalation_required")))
        return decision

