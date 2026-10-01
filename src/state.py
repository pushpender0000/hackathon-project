"""
Typed State definitions for the LangGraph Dispute-Triage pipeline.

Uses TypedDict for graph state and Pydantic models for structured node contracts.
"""

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field


class DisputeGraphState(TypedDict):
    """
    Complete state object passed through LangGraph nodes.
    Each node returns a dictionary containing only the keys it updates.
    """
    # Input
    raw_customer_input: str
    quarantined_text: str
    customer_id: str
    transaction_id: str
    session_id: str

    # Retrieved Context (via MCP)
    transaction: Optional[Dict[str, Any]]
    customer_history: Optional[Dict[str, Any]]

    # Classification Output (Worker 1: Gemini)
    dispute_category: Optional[str]
    customer_intent: Optional[str]
    extracted_amount: Optional[float]
    claim_summary: Optional[str]

    # Fraud Scoring Output (Worker 2: Deterministic)
    fraud_score: Optional[float]
    risk_level: Optional[str]
    top_risk_factors: List[str]
    fraud_features: Dict[str, Any]

    # Chargeback Rule Retrieval (Worker 3: ChromaDB RAG + MCP Resource)
    selected_rule_id: Optional[str]
    rule_title: Optional[str]
    max_filing_days: Optional[int]
    evidence_required: List[str]
    synthetic_citation: Optional[str]
    retrieval_score: Optional[float]
    policy_retrieval_failed: bool

    # Decision Engine Output
    recommended_action: Optional[str]
    escalation_required: bool
    escalation_reason: Optional[str]
    precedence_level: Optional[int]

    # Execution & Governance Telemetry
    iteration_count: int
    execution_errors: List[str]
    data_unavailable: bool
    guardrail_flags: List[str]
    next_worker: Optional[str]
    gemini_call_count: int
    cumulative_tokens: int

    # Final Output
    synthesis_result: Optional[str]
    final_response: Optional[str]

    # Audit & Tracking
    run_id: str
    timestamps: Dict[str, str]
    audit_metadata: Dict[str, Any]


class NodeExecutionResult(BaseModel):
    """Structured contract returned by internal execution helpers."""
    success: bool
    node_name: str
    updates: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
