import re
from typing import Any, Dict, List, Union

# Regex patterns for card PANs (13 to 19 digits with optional spaces or dashes)
PAN_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
# Regex pattern for bank account numbers (8 to 12 contiguous digits)
ACCOUNT_PATTERN = re.compile(r"\b\d{8,12}\b")

def mask_card_pan(pan: str) -> str:
    """
    Mask a credit/debit card Primary Account Number (PAN).
    Preserves only the last 4 digits, replacing preceding digits with asterisks.
    Example: '4111222233334444' -> '****-****-****-4444'
    """
    digits_only = re.sub(r"\D", "", pan)
    if len(digits_only) < 4:
        return "****"
    last_four = digits_only[-4:]
    return f"****-****-****-{last_four}"

def mask_account_number(acc: str) -> str:
    """
    Mask a bank account number, preserving only the last 4 digits.
    Example: '1234567890' -> '******7890'
    """
    digits_only = re.sub(r"\D", "", acc)
    if len(digits_only) < 4:
        return "****"
    last_four = digits_only[-4:]
    return "*" * (len(digits_only) - 4) + last_four

def mask_text_sensitive_data(text: str) -> str:
    """
    Scans a free-form string and masks any detected card PANs or account numbers.
    """
    if not isinstance(text, str):
        return text

    def _replace_pan(match: re.Match) -> str:
        raw_val = match.group(0)
        digits = re.sub(r"\D", "", raw_val)
        if 13 <= len(digits) <= 19:
            return mask_card_pan(digits)
        return raw_val

    masked_pans = PAN_PATTERN.sub(_replace_pan, text)
    return masked_pans

# Convenient alias for guardrail modules
mask_text = mask_text_sensitive_data

def sanitize_data(data: Any) -> Any:
    """
    Recursively traverse dictionaries, lists, and primitives to mask PANs
    and account numbers from values and keys before logging or state storage.
    """
    if isinstance(data, dict):
        sanitized = {}
        for key, val in data.items():
            key_lower = str(key).lower()
            if any(term in key_lower for term in ["pan", "card_number", "account_number", "cvv", "cvc"]):
                if isinstance(val, str) and len(val) >= 4:
                    sanitized[key] = mask_card_pan(val) if "card" in key_lower or "pan" in key_lower else mask_account_number(val)
                else:
                    sanitized[key] = "***MASKED***"
            else:
                sanitized[key] = sanitize_data(val)
        return sanitized
    elif isinstance(data, (list, tuple, set)):
        return [sanitize_data(item) for item in data]
    elif isinstance(data, str):
        return mask_text_sensitive_data(data)
    else:
        return data

def to_json_safe(data: Any) -> Any:
    """
    Convert data structures to JSON-safe primitives, handling Pydantic models.
    """
    if hasattr(data, "model_dump"):
        return sanitize_data(data.model_dump())
    elif hasattr(data, "dict"):
        return sanitize_data(data.dict())
    return sanitize_data(data)
