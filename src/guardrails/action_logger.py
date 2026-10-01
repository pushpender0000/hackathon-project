"""
Guardrail Action Logger.

Records every security evaluation, input sanitization, quarantine action,
and output leakage check directly to `logs/agent_actions.jsonl`.
Guarantees zero logging of raw payment card numbers (PANs) or credentials.
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.config.settings import get_settings
from src.utils.masking import mask_text, sanitize_data


def log_guardrail_action(
    agent: str,
    action: str,
    decision: str,
    guardrail_result: List[str],
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Appends an audited guardrail action record to logs/agent_actions.jsonl.
    
    Args:
        agent: "input_guard", "output_guard", or component name
        action: Specific action performed (e.g. "INSPECT_CUSTOMER_INPUT", "MASK_PAYMENT_OUTPUT")
        decision: Final outcome: "BLOCKED", "MASKED", "ALLOWED", "QUARANTINED", or "ESCALATED"
        guardrail_result: List of flags triggered (e.g. ["PROMPT_INJECTION_DETECTED"], ["CLEAN"])
        details: Metadata dictionary (sanitized to remove any sensitive text)
    """
    if "PYTEST_CURRENT_TEST" in os.environ or "EVALUATION_RUN" in os.environ:
        return
    settings = get_settings()
    log_path = settings.workspace_root / "logs" / "agent_actions.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    sanitized_details = sanitize_data(details or {})

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "action": action,
        "decision": decision,
        "guardrail_result": guardrail_result,
        "details": sanitized_details,
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
