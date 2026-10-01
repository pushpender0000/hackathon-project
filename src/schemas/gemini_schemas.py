"""
Gemini-facing Pydantic schemas.

CRITICAL:
These schemas are supplied directly to `response_schema` in the Google GenAI SDK.
They MUST have ZERO FIELD DEFAULTS (no `= None`, no `= False`, etc.).
"""

from typing import Literal, Optional
from pydantic import BaseModel


class GeminiDisputeClassificationOutput(BaseModel):
    """Zero-defaults schema for Worker 1 (Dispute Classification Agent)."""
    dispute_category: Literal[
        "fraudulent_transaction",
        "merchandise_not_received",
        "duplicate_processing",
        "incorrect_amount",
        "canceled_service",
        "ambiguous_inquiry",
    ]
    customer_intent: str
    extracted_amount: Optional[float]
    claim_summary: str
    requires_human_triage: bool


class GeminiSynthesisOutput(BaseModel):
    """Zero-defaults schema for Synthesis Agent."""
    customer_explanation: str
    next_steps: str
    policy_reference_summary: str
    disclaimer: str
