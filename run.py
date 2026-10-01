"""
Command Line Interface for the Dispute & Fraud-Triage Copilot.

Usage:
    python run.py --dispute-id DISP-001
"""

import sys
import json
import uuid
import asyncio
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Ensure root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config.settings import get_settings
from src.graph import create_dispute_graph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


def load_synthetic_dispute(dispute_id: str) -> dict:
    """Loads a synthetic dispute record by ID from data/synthetic_disputes.json."""
    if dispute_id in ("DISP-MCP-FAIL", "TX-MCP-FAIL"):
        return {
            "dispute_id": "DISP-MCP-FAIL",
            "customer_id": "CUST-001",
            "transaction_id": "TX-MCP-FAIL",
            "claim_text": "I noticed an unrecognized charge on my card statement and wish to dispute it.",
            "days_elapsed": 10,
            "expected_action": "investigate",
            "expected_rule": None,
        }

    settings = get_settings()
    disputes_path = settings.data_dir / "synthetic_disputes.json"
    if not disputes_path.exists():
        raise FileNotFoundError(f"Synthetic disputes file not found: {disputes_path}")

    with open(disputes_path, "r", encoding="utf-8") as f:
        disputes = json.load(f)

    record = next((d for d in disputes if d.get("dispute_id") == dispute_id), None)
    if not record:
        available = [d.get("dispute_id") for d in disputes] + ["DISP-MCP-FAIL"]
        raise ValueError(f"Dispute '{dispute_id}' not found. Available IDs: {available}")
    return record


async def run_dispute_triage(dispute_id: str):
    """Executes the multi-agent graph on the specified synthetic dispute."""
    settings = get_settings()
    dispute = load_synthetic_dispute(dispute_id)
    db_path = Path(settings.sqlite_checkpoints_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    thread_id = f"thread-{dispute_id}-{uuid.uuid4().hex[:6]}"
    config = {
        "configurable": {
            "thread_id": thread_id,
        },
        "recursion_limit": 25,
    }

    initial_state = {
        "raw_customer_input": dispute["claim_text"],
        "quarantined_text": "",
        "customer_id": dispute["customer_id"],
        "transaction_id": dispute["transaction_id"],
        "session_id": f"session-{dispute_id}",
        "transaction": None,
        "customer_history": None,
        "dispute_category": None,
        "customer_intent": None,
        "extracted_amount": None,
        "claim_summary": None,
        "fraud_score": None,
        "risk_level": None,
        "top_risk_factors": [],
        "fraud_features": {},
        "selected_rule_id": None,
        "rule_title": None,
        "max_filing_days": None,
        "evidence_required": [],
        "synthetic_citation": None,
        "retrieval_score": None,
        "policy_retrieval_failed": False,
        "recommended_action": None,
        "escalation_required": False,
        "escalation_reason": None,
        "precedence_level": None,
        "iteration_count": 0,
        "execution_errors": [],
        "data_unavailable": False,
        "guardrail_flags": [],
        "next_worker": None,
        "gemini_call_count": 0,
        "cumulative_tokens": 0,
        "synthesis_result": None,
        "final_response": None,
        "run_id": str(uuid.uuid4()),
        "timestamps": {"started_at": datetime.now(timezone.utc).isoformat()},
        "audit_metadata": {
            "dispute_id": dispute["dispute_id"],
            "days_elapsed": dispute.get("days_elapsed", 0),
            "expected_action": dispute.get("expected_action"),
            "expected_rule": dispute.get("expected_rule"),
        },
    }

    print("=" * 60)
    print(f"EXECUTING DISPUTE TRIAGE PIPELINE FOR {dispute_id}")
    print("=" * 60)
    print(f"Customer ID        : {dispute['customer_id']}")
    print(f"Transaction ID     : {dispute['transaction_id']}")
    print(f"Claim Text         : {dispute['claim_text']}")
    print(f"Benchmark Expectation: Action={dispute.get('expected_action')}, Rule={dispute.get('expected_rule')}")
    print("=" * 60)

    from src.observability.tracing import trace_span

    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as saver:
        app = create_dispute_graph(checkpointer=saver)
        with trace_span(
            name="graph.run",
            span_kind="CHAIN",
            agent="dispute_copilot",
            attributes={
                "dispute.id": dispute_id,
                "customer.id": dispute["customer_id"],
                "transaction.id": dispute["transaction_id"],
            },
        ) as root_span:
            final_state = await app.ainvoke(initial_state, config=config)
            root_span.set_attribute("decision.action", str(final_state.get("recommended_action")))
            root_span.set_attribute("decision.precedence_tier", int(final_state.get("precedence_level") or 1))
            root_span.set_attribute("decision.escalation_required", bool(final_state.get("escalation_required")))
            root_span.set_attribute("llm.call_count", int(final_state.get("gemini_call_count") or 0))
            root_span.set_attribute("llm.cumulative_tokens", int(final_state.get("cumulative_tokens") or 0))


    print("\n" + "=" * 60)
    print("TRIAGE EXECUTION REPORT")
    print("=" * 60)
    print(f"Recommended Action : {final_state.get('recommended_action', '').upper()}")
    print(f"Precedence Tier    : Tier {final_state.get('precedence_level')}")
    print(f"Escalation Status  : {'YES (HUMAN REVIEW REQUIRED)' if final_state.get('escalation_required') else 'NO (AUTOMATED RESOLUTION)'}")
    if final_state.get("escalation_reason"):
        print(f"Escalation Reason  : {final_state.get('escalation_reason')}")
    category_display = final_state.get("dispute_category") or "UNAVAILABLE"
    fraud_val = final_state.get("fraud_score")
    fraud_display = f"{fraud_val} / 100 ({final_state.get('risk_level')})" if fraud_val is not None else "UNAVAILABLE"
    rule_id = final_state.get("selected_rule_id")
    rule_display = f"{rule_id} - {final_state.get('rule_title')}" if rule_id else "UNAVAILABLE"

    print(f"Dispute Category   : {category_display}")
    print(f"Fraud Score        : {fraud_display}")
    if final_state.get("top_risk_factors"):
        print(f"Risk Factors       : {', '.join(final_state.get('top_risk_factors'))}")
    print(f"Applied Policy Rule: {rule_display}")
    print(f"Total Gemini Calls : {final_state.get('gemini_call_count')}")
    print(f"Cumulative Tokens  : {final_state.get('cumulative_tokens')}")
    print(f"Guardrail Flags    : {', '.join(final_state.get('guardrail_flags', [])) or 'None'}")
    print("-" * 60)
    print("FINAL RESPONSE OUTPUT:")
    print(final_state.get("final_response", "No response generated"))
    print("=" * 60)
    return final_state


def main():
    parser = argparse.ArgumentParser(description="Transaction Dispute & Fraud Triage Copilot CLI")
    parser.add_argument("--dispute-id", default="DISP-001", help="Synthetic dispute ID (e.g. DISP-001, DISP-003)")
    args = parser.parse_args()

    asyncio.run(run_dispute_triage(args.dispute_id))


if __name__ == "__main__":
    main()
