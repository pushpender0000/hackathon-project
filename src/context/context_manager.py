"""
Context Engineering for Dispute & Fraud Triage Copilot.

Provides deterministic context write, select, compress, isolate, and summarization
middleware. Enforces strict quarantine of untrusted customer input and prevents
context-stuffing token bloat.
"""

import re
from typing import Any, Dict, List, Optional
from src.utils.masking import mask_text

# Regex patterns to detect instruction-injection / prompt escape attempts
INJECTION_PATTERNS = [
    r"system\s*override",
    r"ignore\s*(all\s*)?(previous|prior)\s*instructions",
    r"clear\s*fraud\s*score",
    r"credit\s*\$?[0-9,]+\s*immediately",
    r"bypass\s*security",
    r"you\s*are\s*now\s*a",
    r"act\s*as\s*(a\s*)?system\s*admin",
    r"<script\b",
    r"drop\s+table",
]

COMPILED_INJECTION_REGEX = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def quarantine_untrusted_text(raw_text: str) -> Dict[str, Any]:
    """
    Quarantines untrusted free-text customer-supplied input.
    
    1. Masks any sensitive cardholder data (PAN, SSN, Account).
    2. Inspects for instruction-injection or prompt escape attempts.
    3. Encapsulates text in structured XML isolation delimiters:
       `<customer_untrusted_claim>...</customer_untrusted_claim>`.
       
    Returns:
        Dict containing:
        - 'quarantined_text': Isolated string wrapped in delimiters
        - 'is_quarantined': True
        - 'injection_detected': bool
        - 'masked_content': Sanitized text without delimiters
    """
    if not raw_text:
        return {
            "quarantined_text": "<customer_untrusted_claim>\n</customer_untrusted_claim>",
            "is_quarantined": True,
            "injection_detected": False,
            "masked_content": "",
        }

    masked = mask_text(raw_text)
    injection_detected = bool(COMPILED_INJECTION_REGEX.search(raw_text))

    quarantined = (
        f"<customer_untrusted_claim>\n"
        f"{masked.strip()}\n"
        f"</customer_untrusted_claim>"
    )

    return {
        "quarantined_text": quarantined,
        "is_quarantined": True,
        "injection_detected": injection_detected,
        "masked_content": masked.strip(),
    }


def select_worker_context(
    worker_name: str,
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Selects and isolates the minimum necessary context slice for a given worker agent.
    Avoids sending whole graph state, preventing token waste and hallucinations.
    """
    tx = state.get("transaction") or {}
    cust = state.get("customer_history") or {}
    quarantined = state.get("quarantined_text", "")

    if worker_name == "classifier":
        return {
            "claim_text": quarantined,
            "merchant_name": tx.get("merchant_name", "UNKNOWN"),
            "merchant_mcc": tx.get("merchant_mcc", "UNKNOWN"),
            "amount": tx.get("amount", 0.0),
            "card_present": tx.get("card_present", False),
        }

    elif worker_name == "fraud_scorer":
        return {
            "amount": tx.get("amount", 0.0),
            "customer_id": state.get("customer_id", tx.get("customer_id", "UNKNOWN")),
            "customer_history": cust,
            "merchant_name": tx.get("merchant_name", "UNKNOWN"),
            "merchant_mcc": tx.get("merchant_mcc", "UNKNOWN"),
            "card_present": tx.get("card_present", False),
            "is_cross_border": tx.get("is_cross_border", False),
        }

    elif worker_name == "chargeback_retriever":
        return {
            "claim_text": quarantined,
            "category": state.get("dispute_category", "fraud"),
            "card_present": tx.get("card_present", False),
            "dispute_id": state.get("dispute_id", "N/A"),
        }

    elif worker_name == "synthesis":
        return {
            "dispute_id": state.get("dispute_id", "N/A"),
            "customer_id": state.get("customer_id", "UNKNOWN"),
            "transaction_id": state.get("transaction_id", "UNKNOWN"),
            "amount": tx.get("amount", 0.0),
            "merchant_name": tx.get("merchant_name", "UNKNOWN"),
            "dispute_category": state.get("dispute_category", "fraud"),
            "recommended_action": state.get("recommended_action", "investigate"),
            "decision_rationale": state.get("decision_rationale", ""),
            "selected_rule_id": state.get("selected_rule_id"),
            "rule_metadata": state.get("rule_metadata") or {},
            "escalation_required": state.get("escalation_required", False),
            "escalation_reason": state.get("escalation_reason"),
        }

    return state


def compress_dispute_history(history: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compresses verbose customer dispute records into summary statistics.
    Reduces token payload for LLM and agent workers by up to 70%.
    """
    if not history:
        return {
            "total_prior_disputes": 0,
            "resolved_count": 0,
            "chargeback_win_rate": 0.0,
            "prior_fraud_disputes": 0,
            "total_disputed_amount": 0.0,
            "account_standing": "clean",
        }

    prior_disputes = history.get("prior_disputes", [])
    total_count = len(prior_disputes)
    resolved_count = sum(1 for d in prior_disputes if d.get("status") in ("RESOLVED", "CLOSED", "WON"))
    fraud_count = sum(1 for d in prior_disputes if "fraud" in d.get("category", "").lower())
    total_disputed = sum(float(d.get("amount", 0.0)) for d in prior_disputes)

    win_rate = round(resolved_count / total_count, 2) if total_count > 0 else 1.0

    return {
        "customer_id": history.get("customer_id"),
        "customer_name": history.get("name", "UNKNOWN"),
        "total_prior_disputes": total_count,
        "resolved_count": resolved_count,
        "chargeback_win_rate": win_rate,
        "prior_fraud_disputes": fraud_count,
        "total_disputed_amount": round(total_disputed, 2),
        "account_standing": "high_dispute" if total_count >= 5 else "standard",
    }


def summarize_dispute_context(state: Dict[str, Any]) -> str:
    """
    Generates a deterministic single-paragraph executive summary of the dispute context.
    """
    tx = state.get("transaction") or {}
    cust = state.get("customer_history") or {}
    dispute_id = state.get("dispute_id", "N/A")
    category = state.get("dispute_category", "unclassified")
    action = state.get("recommended_action", "pending")
    amt = tx.get("amount", 0.0)
    merchant = tx.get("merchant_name", "Unknown Merchant")

    summary = (
        f"Dispute {dispute_id}: {category.upper()} claim for ${amt:.2f} at {merchant}. "
        f"Recommended Action: {action.upper()}."
    )
    if state.get("escalation_required"):
        summary += f" Escalated: {state.get('escalation_reason')}."
    return summary
