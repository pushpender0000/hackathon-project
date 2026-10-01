"""
Worker 3: Chargeback Rule Retrieval Agent.

Retrieves synthetic chargeback rules via MCP resource catalog + local ChromaDB vector search.
Never calls an LLM.
Instruments execution with OpenTelemetry spans.
"""

from typing import Any, Dict, List, Optional
from src.tools.mcp_client import read_mcp_resource
from src.tools.rag_tool import get_rag_retriever
from src.observability.tracing import trace_span


async def chargeback_retriever_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node for Worker 3: Chargeback Policy Retrieval."""
    with trace_span(
        name="chargeback_retriever",
        span_kind="AGENT",
        agent="chargeback_retriever",
        attributes={"agent.role": "policy_retrieval"},
    ) as span:
        category = state.get("dispute_category")
        claim_text = state.get("claim_summary") or state.get("quarantined_text") or state.get("raw_customer_input") or ""

        # 1. Read synthetic rule catalog from MCP resource
        try:
            resource_data = await read_mcp_resource(
                "dispute-policy-spec://network_rules",
                agent="chargeback_retriever",
            )
            rules_index = resource_data.get("rules_index", {})
        except Exception as e:
            # If MCP resource read fails, set retrieval failure and escalate
            return {
                "policy_retrieval_failed": True,
                "escalation_required": True,
                "escalation_reason": f"MCP resource failure reading network rules: {str(e)}",
                "recommended_action": "investigate",
                "precedence_level": 1,
                "execution_errors": state.get("execution_errors", []) + [f"MCP Resource Error: {str(e)}"],
            }

        # 2. Filter allowed candidate rule IDs from resource catalog
        candidate_rule_ids: List[str] = []
        if category:
            for r_id, meta in rules_index.items():
                if meta.get("category") == category:
                    candidate_rule_ids.append(r_id)

        # Canceled service non-delivery maps to merchandise/service non-delivery rule
        if category == "canceled_service":
            for r_id, meta in rules_index.items():
                if meta.get("category") == "merchandise_not_received":
                    candidate_rule_ids.append(r_id)

        # If category didn't match directly, allow all catalog rules
        if not candidate_rule_ids:
            candidate_rule_ids = list(rules_index.keys())

        # 3. Perform local RAG retrieval
        tx = state.get("transaction") or {}
        card_present = tx.get("card_present")
        card_context = ""
        if card_present is False:
            card_context = "Card-absent e-commerce transaction. "
        elif card_present is True:
            card_context = "Card-present physical merchant transaction. "

        retriever = get_rag_retriever()
        search_query = f"{card_context}Category: {category}. Claim: {claim_text}"
        result = retriever.retrieve_best_rule(
            query_text=search_query,
            candidate_rule_ids=candidate_rule_ids,
        )

        if not result:
            return {
                "policy_retrieval_failed": True,
                "escalation_required": True,
                "escalation_reason": f"No valid synthetic chargeback rule found for category '{category}'",
                "recommended_action": "investigate",
                "precedence_level": 1,
            }

        rule_meta, confidence = result
        span.set_attribute("policy.selected_rule", rule_meta["rule_id"])
        span.set_attribute("policy.retrieval_confidence", float(confidence))

        return {
            "selected_rule_id": rule_meta["rule_id"],
            "rule_title": rule_meta["title"],
            "max_filing_days": rule_meta["max_filing_days"],
            "evidence_required": rule_meta["required_evidence"],
            "synthetic_citation": rule_meta["synthetic_section"],
            "retrieval_score": confidence,
            "policy_retrieval_failed": False,
        }
