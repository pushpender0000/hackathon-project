"""
Tests for Deterministic Decision Engine.
Verifies all 6 precedence tiers and edge case boundary conditions.
"""

from src.decision.engine import evaluate_triage_decision


def test_precedence_1_missing_mcp_data():
    """Missing MCP data must escalate at Tier 1."""
    state = {
        "data_unavailable": True,
        "escalation_reason": "MCP transaction fetch failed",
    }
    decision = evaluate_triage_decision(state)
    assert decision["recommended_action"] == "investigate"
    assert decision["escalation_required"] is True
    assert decision["precedence_level"] == 1


def test_precedence_1_retrieval_failure():
    """Policy retrieval failure must escalate at Tier 1."""
    state = {
        "policy_retrieval_failed": True,
        "escalation_reason": "No policy rule found",
    }
    decision = evaluate_triage_decision(state)
    assert decision["recommended_action"] == "investigate"
    assert decision["escalation_required"] is True
    assert decision["precedence_level"] == 1


def test_precedence_2_security_injection():
    """Security injection pattern must escalate at Tier 2."""
    state = {
        "guardrail_flags": ["PROMPT_INJECTION_DETECTED"],
        "transaction": {"amount": 50.0},
        "dispute_category": "fraudulent_transaction",
    }
    decision = evaluate_triage_decision(state)
    assert decision["recommended_action"] == "investigate"
    assert decision["escalation_required"] is True
    assert decision["precedence_level"] == 2


def test_precedence_2_ambiguous_intent():
    """Ambiguous inquiry category must escalate at Tier 2."""
    state = {
        "dispute_category": "ambiguous_inquiry",
        "customer_intent": "unclear",
        "transaction": {"amount": 25.0},
        "fraud_score": 10.0,
    }
    decision = evaluate_triage_decision(state)
    assert decision["recommended_action"] == "investigate"
    assert decision["escalation_required"] is True
    assert decision["precedence_level"] == 2


def test_precedence_3_high_value_escalation():
    """Transaction > $1000 must escalate at Tier 3."""
    state = {
        "dispute_category": "fraudulent_transaction",
        "transaction": {"amount": 2499.00},
        "fraud_score": 20.0,
        "customer_history": {"total_prior_disputes": 0},
    }
    decision = evaluate_triage_decision(state)
    assert decision["recommended_action"] == "investigate"
    assert decision["escalation_required"] is True
    assert decision["precedence_level"] == 3
    assert "High-value" in decision["escalation_reason"]


def test_precedence_3_high_fraud_escalation():
    """Fraud score >= 80.0 must escalate at Tier 3."""
    state = {
        "dispute_category": "fraudulent_transaction",
        "transaction": {"amount": 300.00},
        "fraud_score": 85.0,
        "customer_history": {"total_prior_disputes": 0},
    }
    decision = evaluate_triage_decision(state)
    assert decision["recommended_action"] == "investigate"
    assert decision["escalation_required"] is True
    assert decision["precedence_level"] == 3
    assert "High fraud risk" in decision["escalation_reason"]


def test_precedence_3_high_value_and_expired():
    """High value transaction that is ALSO expired must escalate at Tier 3 (Tier 3 > Tier 4)."""
    state = {
        "dispute_category": "fraudulent_transaction",
        "transaction": {"amount": 1500.00},
        "fraud_score": 15.0,
        "max_filing_days": 120,
        "audit_metadata": {"days_elapsed": 180},
    }
    decision = evaluate_triage_decision(state)
    assert decision["recommended_action"] == "investigate"
    assert decision["escalation_required"] is True
    assert decision["precedence_level"] == 3


def test_precedence_3_high_fraud_and_expired():
    """High fraud transaction that is ALSO expired must escalate at Tier 3 (Tier 3 > Tier 4)."""
    state = {
        "dispute_category": "fraudulent_transaction",
        "transaction": {"amount": 40.00},
        "fraud_score": 90.0,
        "max_filing_days": 120,
        "audit_metadata": {"days_elapsed": 150},
    }
    decision = evaluate_triage_decision(state)
    assert decision["recommended_action"] == "investigate"
    assert decision["escalation_required"] is True
    assert decision["precedence_level"] == 3


def test_precedence_4_expired_filing_window():
    """Dispute filed after maximum allowable days without high risk must be denied at Tier 4."""
    state = {
        "dispute_category": "merchandise_not_received",
        "transaction": {"amount": 180.00},
        "fraud_score": 10.0,
        "max_filing_days": 120,
        "audit_metadata": {"days_elapsed": 195},
        "selected_rule_id": "SYNTH-RULE-13.1",
    }
    decision = evaluate_triage_decision(state)
    assert decision["recommended_action"] == "deny"
    assert decision["escalation_required"] is False
    assert decision["precedence_level"] == 4
    assert "expired" in decision["escalation_reason"].lower()


def test_precedence_5_low_risk_provisional_credit():
    """Low amount (<= $150) and low fraud (<= 30) within window receives provisional credit."""
    state = {
        "dispute_category": "fraudulent_transaction",
        "transaction": {"amount": 35.50},
        "fraud_score": 15.0,
        "max_filing_days": 120,
        "audit_metadata": {"days_elapsed": 6},
        "selected_rule_id": "SYNTH-RULE-10.4",
    }
    decision = evaluate_triage_decision(state)
    assert decision["recommended_action"] == "provisional_credit"
    assert decision["escalation_required"] is False
    assert decision["precedence_level"] == 5


def test_precedence_6_valid_chargeback():
    """Standard dispute exceeding provisional credit ($450) but under $1000 with low risk becomes chargeback."""
    state = {
        "dispute_category": "merchandise_not_received",
        "transaction": {"amount": 450.00},
        "fraud_score": 25.0,
        "max_filing_days": 120,
        "audit_metadata": {"days_elapsed": 11},
        "selected_rule_id": "SYNTH-RULE-13.1",
    }
    decision = evaluate_triage_decision(state)
    assert decision["recommended_action"] == "chargeback"
    assert decision["escalation_required"] is False
    assert decision["precedence_level"] == 6
