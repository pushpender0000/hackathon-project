"""
LangGraph Multi-Agent Dispute & Fraud-Triage Pipeline.

Constructs the complete state graph with SQLite checkpointing and deterministic routing:
START -> input_guard -> load_context -> supervisor -> workers -> decision_engine -> escalation/synthesis -> output_guard -> audit -> END.
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.config.settings import get_settings
from src.state import DisputeGraphState
from src.guardrails.input_guard import input_guard_node, input_guard_conditional_edge
from src.guardrails.output_guard import output_guard_node
from src.agents.supervisor import (
    load_context_node,
    supervisor_node,
    supervisor_conditional_edge,
)
from src.agents.classifier_agent import classifier_agent_node
from src.agents.fraud_agent import fraud_agent_node
from src.agents.chargeback_retriever import chargeback_retriever_node
from src.decision.engine import decision_engine_node
from src.agents.synthesis_agent import escalation_gate_node, synthesis_agent_node


from src.observability.tracing import trace_span


def audit_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Final audit and telemetry stamping node."""
    with trace_span(
        name="audit",
        span_kind="CHAIN",
        agent="audit",
        attributes={"node": "audit"},
    ) as span:
        timestamps = dict(state.get("timestamps", {}))
        timestamps["completed_at"] = datetime.now(timezone.utc).isoformat()

        flags = list(state.get("guardrail_flags", []))
        if "OUTPUT_GUARDED" not in flags:
            flags.append("OUTPUT_GUARDED")

        audit_meta = dict(state.get("audit_metadata", {}))
        audit_meta["final_action"] = state.get("recommended_action")
        audit_meta["escalation_required"] = state.get("escalation_required")
        audit_meta["precedence_tier"] = state.get("precedence_level")
        audit_meta["total_gemini_calls"] = state.get("gemini_call_count", 0)
        audit_meta["cumulative_tokens"] = state.get("cumulative_tokens", 0)

        span.set_attribute("audit.final_action", str(audit_meta["final_action"]))
        span.set_attribute("audit.gemini_calls", int(audit_meta["total_gemini_calls"]))
        span.set_attribute("audit.tokens", int(audit_meta["cumulative_tokens"]))

        return {
            "timestamps": timestamps,
            "guardrail_flags": flags,
            "audit_metadata": audit_meta,
        }



def create_dispute_graph(checkpointer: Optional[Any] = None) -> Any:
    """
    Builds and compiles the StateGraph with node contracts and conditional edges.
    """
    builder = StateGraph(DisputeGraphState)

    # 1. Register Nodes
    builder.add_node("input_guard", input_guard_node)
    builder.add_node("load_context", load_context_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("classifier", classifier_agent_node)
    builder.add_node("fraud_scorer", fraud_agent_node)
    builder.add_node("chargeback_retriever", chargeback_retriever_node)
    builder.add_node("decision_engine", decision_engine_node)
    builder.add_node("escalation_gate", escalation_gate_node)
    builder.add_node("synthesis", synthesis_agent_node)
    builder.add_node("output_guard", output_guard_node)
    builder.add_node("audit", audit_node)

    # 2. Add Ingestion and Security Edge (Blocked inputs route directly to escalation_gate)
    builder.add_edge(START, "input_guard")
    builder.add_conditional_edges(
        "input_guard",
        input_guard_conditional_edge,
        {
            "escalation_gate": "escalation_gate",
            "load_context": "load_context",
        },
    )
    builder.add_edge("load_context", "supervisor")

    # 3. Add Worker Loopback Edges to Supervisor
    builder.add_edge("classifier", "supervisor")
    builder.add_edge("fraud_scorer", "supervisor")
    builder.add_edge("chargeback_retriever", "supervisor")
    builder.add_edge("decision_engine", "supervisor")

    # 4. Add Conditional Routing from Supervisor
    builder.add_conditional_edges(
        "supervisor",
        supervisor_conditional_edge,
        {
            "load_context": "load_context",
            "classifier": "classifier",
            "fraud_scorer": "fraud_scorer",
            "chargeback_retriever": "chargeback_retriever",
            "decision_engine": "decision_engine",
            "escalation_gate": "escalation_gate",
            "synthesis": "synthesis",
            "output_guard": "output_guard",
            "audit": "audit",
        },
    )

    # 5. Add Resolution and Finalization Edges
    builder.add_edge("escalation_gate", "output_guard")
    builder.add_edge("synthesis", "output_guard")
    builder.add_edge("output_guard", "audit")
    builder.add_edge("audit", END)

    return builder.compile(checkpointer=checkpointer)


def get_default_sqlite_checkpointer() -> SqliteSaver:
    """Creates a persistent SqliteSaver using configured checkpoint DB path."""
    settings = get_settings()
    db_path = Path(settings.sqlite_checkpoints_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return SqliteSaver(conn)


def build_app(use_checkpointer: bool = True) -> Any:
    """Convenience factory returning a fully compiled, checkpointer-backed LangGraph app."""
    cp = get_default_sqlite_checkpointer() if use_checkpointer else None
    return create_dispute_graph(checkpointer=cp)
