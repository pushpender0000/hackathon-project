"""
Deterministic Fraud Scorer.

Calculates reproducible numerical fraud scores (0.0 - 100.0) based on
transaction telemetry and customer history without invoking an LLM.
"""

from typing import Any, Dict, List, Tuple


# High risk Merchant Category Codes (MCC)
HIGH_RISK_MCCS = {
    "6051": ("Quasi-Cash / Crypto / FX", 30.0),
    "7995": ("Betting / Gambling", 25.0),
    "5732": ("Electronics Megastore", 15.0),
    "5944": ("Jewelry / Luxury Goods", 20.0),
}


def calculate_fraud_score(
    transaction: Dict[str, Any],
    customer_history: Dict[str, Any],
) -> Tuple[float, str, List[str], Dict[str, Any]]:
    """
    Computes deterministic fraud risk score from transaction and customer attributes.

    Returns:
        fraud_score: float in [0.0, 100.0]
        risk_level: 'LOW', 'MEDIUM', or 'HIGH'
        top_risk_factors: list of identified risk drivers
        fraud_features: raw extracted feature dictionary
    """
    risk_factors: List[str] = []
    total_score = 5.0  # Base nominal risk for any transaction

    # 1. Amount Anomaly
    amount = float(transaction.get("amount", 0.0))
    if amount >= 1000.0:
        total_score += 35.0
        risk_factors.append(f"High transaction amount (${amount:.2f} >= $1000.00)")
    elif amount >= 500.0:
        total_score += 20.0
        risk_factors.append(f"Elevated transaction amount (${amount:.2f} >= $500.00)")

    # 2. Geographic Anomaly
    country = str(transaction.get("country", "US")).upper()
    if country != "US":
        total_score += 30.0
        risk_factors.append(f"Cross-border transaction detected (Country: {country})")

    # 3. Merchant / MCC Category Risk
    mcc = str(transaction.get("merchant_mcc", "")).strip()
    if mcc in HIGH_RISK_MCCS:
        desc, weight = HIGH_RISK_MCCS[mcc]
        total_score += weight
        risk_factors.append(f"High-risk merchant category (MCC {mcc}: {desc})")

    # 4. Card-Not-Present Environment
    card_present = bool(transaction.get("card_present", False))
    if not card_present and amount >= 200.0:
        total_score += 10.0
        risk_factors.append("Card-not-present transaction with amount >= $200.00")

    # 5. Customer Historical Dispute Ratio & Prior Fraud
    prior_disputes = int(customer_history.get("total_prior_disputes", 0))
    tenure_months = max(int(customer_history.get("tenure_months", 1)), 1)
    dispute_frequency = prior_disputes / tenure_months

    if prior_disputes >= 5:
        total_score += 25.0
        risk_factors.append(f"Chronic dispute history ({prior_disputes} prior disputes)")
    elif prior_disputes >= 2:
        total_score += 10.0
        risk_factors.append(f"Multiple prior disputes on file ({prior_disputes} disputes)")

    prior_fraud = int(customer_history.get("prior_fraud_reports", 0))
    if prior_fraud > 0:
        total_score += 20.0
        risk_factors.append(f"Prior fraud reports on file ({prior_fraud} reports)")

    # Clamp score to [0.0, 100.0]
    final_score = min(max(total_score, 0.0), 100.0)

    # Classify Risk Level
    if final_score >= 80.0:
        risk_level = "HIGH"
    elif final_score >= 35.0:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    features = {
        "amount": amount,
        "country": country,
        "merchant_mcc": mcc,
        "card_present": card_present,
        "prior_disputes": prior_disputes,
        "tenure_months": tenure_months,
        "dispute_frequency": round(dispute_frequency, 3),
        "prior_fraud_reports": prior_fraud,
    }

    return final_score, risk_level, risk_factors, features
