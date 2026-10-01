"""
Worker 2: Fraud Agent.

Responsible for retrieving customer dispute history (if not present) and
calculating a deterministic fraud score without making any LLM calls.
Instruments execution with OpenTelemetry spans.
"""

from typing import Any, Dict
from src.tools.mcp_client import call_mcp_tool
from src.fraud.scorer import calculate_fraud_score
from src.observability.tracing import trace_span


async def fraud_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node for Worker 2: Deterministic Fraud Scoring."""
    with trace_span(
        name="fraud_scorer",
        span_kind="AGENT",
        agent="fraud_scorer",
        attributes={"agent.role": "fraud_risk_scoring"},
    ) as span:
        updates: Dict[str, Any] = {}
        tx = state.get("transaction")
        cust_hist = state.get("customer_history")
        tx_id = state.get("transaction_id", "")
        cust_id = state.get("customer_id", "")

        # Retrieve transaction via MCP if missing
        if not tx and tx_id:
            try:
                tx_res = await call_mcp_tool(
                    "get_transaction_details",
                    {"transaction_id": tx_id},
                    agent="fraud_scorer",
                )
                if "error" in tx_res:
                    return {
                        "data_unavailable": True,
                        "execution_errors": state.get("execution_errors", []) + [f"MCP Error: {tx_res['error']}"],
                        "escalation_required": True,
                        "escalation_reason": f"Transaction {tx_id} could not be retrieved via MCP",
                        "recommended_action": "investigate",
                        "precedence_level": 1,
                    }
                tx = tx_res
                updates["transaction"] = tx
            except Exception as e:
                return {
                    "data_unavailable": True,
                    "execution_errors": state.get("execution_errors", []) + [f"MCP Failure: {str(e)}"],
                    "escalation_required": True,
                    "escalation_reason": f"MCP communication failure for transaction {tx_id}",
                    "recommended_action": "investigate",
                    "precedence_level": 1,
                }

        # Retrieve customer dispute history via MCP if missing
        if not cust_hist and cust_id:
            try:
                cust_res = await call_mcp_tool(
                    "get_customer_dispute_history",
                    {"customer_id": cust_id},
                    agent="fraud_scorer",
                )
                if "error" in cust_res:
                    return {
                        "data_unavailable": True,
                        "execution_errors": state.get("execution_errors", []) + [f"MCP Error: {cust_res['error']}"],
                        "escalation_required": True,
                        "escalation_reason": f"Customer {cust_id} history could not be retrieved via MCP",
                        "recommended_action": "investigate",
                        "precedence_level": 1,
                    }
                cust_hist = cust_res
                updates["customer_history"] = cust_hist
            except Exception as e:
                return {
                    "data_unavailable": True,
                    "execution_errors": state.get("execution_errors", []) + [f"MCP Failure: {str(e)}"],
                    "escalation_required": True,
                    "escalation_reason": f"MCP communication failure for customer {cust_id}",
                    "recommended_action": "investigate",
                    "precedence_level": 1,
                }

        if not tx or not cust_hist:
            return {
                "data_unavailable": True,
                "escalation_required": True,
                "escalation_reason": "Incomplete context: missing transaction or customer history",
                "recommended_action": "investigate",
                "precedence_level": 1,
            }

        # Compute deterministic score
        score, risk_level, factors, features = calculate_fraud_score(tx, cust_hist)

        span.set_attribute("fraud.score", float(score))
        span.set_attribute("fraud.risk_level", str(risk_level))

        updates["fraud_score"] = score
        updates["risk_level"] = risk_level
        updates["top_risk_factors"] = factors
        updates["fraud_features"] = features

        return updates
