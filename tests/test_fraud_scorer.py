"""
Tests for deterministic fraud scoring model.
"""

from src.fraud.scorer import calculate_fraud_score


def test_fraud_scorer_low_risk():
    """Ordinary low-value domestic transaction with clean customer history."""
    tx = {
        "amount": 35.50,
        "country": "US",
        "merchant_mcc": "4121",
        "card_present": True,
    }
    cust = {
        "total_prior_disputes": 0,
        "tenure_months": 24,
        "prior_fraud_reports": 0,
    }
    score, risk_level, factors, features = calculate_fraud_score(tx, cust)
    assert score <= 30.0
    assert risk_level == "LOW"
    assert len(factors) == 0


def test_fraud_scorer_high_value_anomaly():
    """Transaction over $1000 triggers high value anomaly factor."""
    tx = {
        "amount": 2499.00,
        "country": "US",
        "merchant_mcc": "5732",
        "card_present": False,
    }
    cust = {
        "total_prior_disputes": 1,
        "tenure_months": 12,
        "prior_fraud_reports": 0,
    }
    score, risk_level, factors, features = calculate_fraud_score(tx, cust)
    assert any("High transaction amount" in f for f in factors)
    assert any("MCC 5732" in f for f in factors)
    assert score >= 50.0


def test_fraud_scorer_cross_border_and_crypto():
    """Overseas transaction with crypto MCC triggers multiple high-risk penalties."""
    tx = {
        "amount": 890.00,
        "country": "CY",
        "merchant_mcc": "6051",
        "card_present": False,
    }
    cust = {
        "total_prior_disputes": 2,
        "tenure_months": 6,
        "prior_fraud_reports": 1,
    }
    score, risk_level, factors, features = calculate_fraud_score(tx, cust)
    assert score >= 80.0
    assert risk_level == "HIGH"
    assert any("Cross-border" in f for f in factors)
    assert any("MCC 6051" in f for f in factors)
    assert any("Prior fraud reports" in f for f in factors)


def test_fraud_scorer_reproducibility():
    """Verify that multiple invocations with the same inputs return identical scores."""
    tx = {"amount": 450.00, "country": "US", "merchant_mcc": "5812", "card_present": False}
    cust = {"total_prior_disputes": 0, "tenure_months": 10, "prior_fraud_reports": 0}

    score1, _, _, _ = calculate_fraud_score(tx, cust)
    score2, _, _, _ = calculate_fraud_score(tx, cust)
    assert score1 == score2
