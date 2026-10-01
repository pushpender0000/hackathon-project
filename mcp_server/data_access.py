import json
import re
from pathlib import Path
from typing import Dict, Any, Optional
from src.utils.masking import sanitize_data

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TX_FILE = DATA_DIR / "synthetic_transactions.json"
CUST_FILE = DATA_DIR / "synthetic_customers.json"
META_FILE = DATA_DIR / "policy_corpus" / "synthetic_metadata.json"

class CoreBankingDataAccess:
    """Provides validated, sanitized access to committed synthetic core banking records."""

    def __init__(self):
        self._load_cache()

    def _load_cache(self):
        with open(TX_FILE, "r", encoding="utf-8") as f:
            tx_list = json.load(f)
            self._transactions = {t["transaction_id"]: t for t in tx_list}

        with open(CUST_FILE, "r", encoding="utf-8") as f:
            cust_list = json.load(f)
            self._customers = {c["customer_id"]: c for c in cust_list}

        with open(META_FILE, "r", encoding="utf-8") as f:
            self._policy_metadata = json.load(f)

    def get_transaction_details(self, transaction_id: str) -> Dict[str, Any]:
        """
        Lookup transaction details by transaction_id.
        Rejects malformed IDs and returns structured errors if not found.
        Injects deterministic failure for synthetic test ID TX-MCP-FAIL.
        """
        if not isinstance(transaction_id, str) or not transaction_id.strip():
            return {
                "error": "InvalidTransactionId",
                "message": "transaction_id must be a non-empty string",
                "code": 400
            }
        
        # Enforce valid ID pattern: alphanumeric and dashes only
        if not re.match(r"^[A-Za-z0-9\-]+$", transaction_id):
            return {
                "error": "MalformedTransactionId",
                "message": f"transaction_id '{transaction_id}' contains invalid characters",
                "code": 400
            }

        # Deterministic failure injection for test ID TX-MCP-FAIL
        if transaction_id == "TX-MCP-FAIL":
            return {
                "error": "MCPGatewayFailure",
                "message": "Synthetic core banking gateway timeout / downstream unavailable for TX-MCP-FAIL",
                "code": 504
            }

        tx = self._transactions.get(transaction_id)
        if not tx:
            return {
                "error": "TransactionNotFound",
                "message": f"Transaction '{transaction_id}' does not exist in synthetic core banking system",
                "code": 404
            }

        result = {
            "transaction_id": tx["transaction_id"],
            "customer_id": tx["customer_id"],
            "masked_pan": tx["masked_pan"],
            "merchant": tx["merchant"],
            "merchant_mcc": tx.get("merchant_mcc"),
            "amount": tx["amount"],
            "currency": tx["currency"],
            "timestamp": tx["timestamp"],
            "country": tx["country"],
            "card_present": tx.get("card_present"),
            "status": tx["status"]
        }
        return sanitize_data(result)

    # Canonical alias
    get_transaction = get_transaction_details

    def get_customer_dispute_history(self, customer_id: str) -> Dict[str, Any]:
        """
        Lookup customer dispute history by customer_id.
        Rejects malformed IDs and returns structured errors if not found.
        """
        if not isinstance(customer_id, str) or not customer_id.strip():
            return {
                "error": "InvalidCustomerId",
                "message": "customer_id must be a non-empty string",
                "code": 400
            }

        if not re.match(r"^[A-Za-z0-9\-]+$", customer_id):
            return {
                "error": "MalformedCustomerId",
                "message": f"customer_id '{customer_id}' contains invalid characters",
                "code": 400
            }

        cust = self._customers.get(customer_id)
        if not cust:
            return {
                "error": "CustomerNotFound",
                "message": f"Customer '{customer_id}' does not exist in synthetic core banking system",
                "code": 404
            }

        result = {
            "customer_id": cust["customer_id"],
            "total_prior_disputes": cust["total_prior_disputes"],
            "open_disputes": cust["open_disputes"],
            "prior_fraud_reports": cust["prior_fraud_reports"],
            "win_rate": cust["win_rate"],
            "tenure_months": cust["tenure_months"]
        }
        return sanitize_data(result)

    # Canonical alias
    get_customer_history = get_customer_dispute_history

    def get_policy_metadata(self) -> Dict[str, Any]:
        """Returns the synthetic benchmark policy metadata catalog."""
        return sanitize_data(self._policy_metadata)
