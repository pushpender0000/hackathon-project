"""
Tests for deterministic supervisor worker routing.
"""

from src.agents.supervisor import supervisor_node


def test_supervisor_routes_to_load_context():
    """When transaction or customer history is missing, route to load_context."""
    state = {
        "transaction": None,
        "customer_history": None,
        "iteration_count": 0,
    }
    result = supervisor_node(state)
    assert result["next_worker"] == "load_context"


def test_supervisor_routes_to_classifier():
    """When context exists but dispute_category is missing, route to classifier."""
    state = {
        "transaction": {"transaction_id": "TX-001"},
        "customer_history": {"customer_id": "CUST-001"},
        "dispute_category": None,
        "iteration_count": 1,
    }
    result = supervisor_node(state)
    assert result["next_worker"] == "classifier"


def test_supervisor_routes_to_fraud_scorer():
    """When classification is done but fraud_score is missing, route to fraud_scorer."""
    state = {
        "transaction": {"transaction_id": "TX-001"},
        "customer_history": {"customer_id": "CUST-001"},
        "dispute_category": "fraudulent_transaction",
        "fraud_score": None,
        "iteration_count": 2,
    }
    result = supervisor_node(state)
    assert result["next_worker"] == "fraud_scorer"


def test_supervisor_routes_to_chargeback_retriever():
    """When fraud score is calculated but selected_rule_id is missing, route to retriever."""
    state = {
        "transaction": {"transaction_id": "TX-001"},
        "customer_history": {"customer_id": "CUST-001"},
        "dispute_category": "fraudulent_transaction",
        "fraud_score": 15.0,
        "selected_rule_id": None,
        "policy_retrieval_failed": False,
        "iteration_count": 3,
    }
    result = supervisor_node(state)
    assert result["next_worker"] == "chargeback_retriever"


def test_supervisor_routes_to_decision_engine():
    """When all worker data is gathered but action is missing, route to decision_engine."""
    state = {
        "transaction": {"transaction_id": "TX-001"},
        "customer_history": {"customer_id": "CUST-001"},
        "dispute_category": "fraudulent_transaction",
        "fraud_score": 15.0,
        "selected_rule_id": "SYNTH-RULE-10.4",
        "recommended_action": None,
        "iteration_count": 4,
    }
    result = supervisor_node(state)
    assert result["next_worker"] == "decision_engine"


def test_supervisor_routes_to_escalation_gate():
    """When escalation_required is True and no response exists, route to escalation_gate."""
    state = {
        "transaction": {"transaction_id": "TX-001"},
        "customer_history": {"customer_id": "CUST-001"},
        "dispute_category": "fraudulent_transaction",
        "fraud_score": 90.0,
        "selected_rule_id": "SYNTH-RULE-10.4",
        "recommended_action": "investigate",
        "escalation_required": True,
        "final_response": None,
        "iteration_count": 5,
    }
    result = supervisor_node(state)
    assert result["next_worker"] == "escalation_gate"


def test_supervisor_routes_to_synthesis():
    """When escalation_required is False, route to synthesis."""
    state = {
        "transaction": {"transaction_id": "TX-001"},
        "customer_history": {"customer_id": "CUST-001"},
        "dispute_category": "fraudulent_transaction",
        "fraud_score": 15.0,
        "selected_rule_id": "SYNTH-RULE-10.4",
        "recommended_action": "provisional_credit",
        "escalation_required": False,
        "final_response": None,
        "iteration_count": 5,
    }
    result = supervisor_node(state)
    assert result["next_worker"] == "synthesis"
