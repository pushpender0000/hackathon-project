"""
Deterministic Graph Supervisor and Context Loader.

Controls worker routing and loop boundaries with ZERO LLM calls.
Enforces hard recursion and step ceilings.
Instruments execution with OpenTelemetry spans.
"""

from typing import Any, Dict, Literal
from src.tools.mcp_client import call_mcp_tool
from src.observability.tracing import trace_span

MAX_SUPERVISOR_ITERATIONS = 8


async def load_context_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Initial data loading node. Fetches transaction and customer history via MCP stdio.
    """
    with trace_span(
        name="load_context",
        span_kind="CHAIN",
        agent="supervisor",
        attributes={"node": "load_context"},
    ):
        tx_id = state.get("transaction_id", "")
        cust_id = state.get("customer_id", "")
        updates: Dict[str, Any] = {}

        # Fetch transaction via MCP
        if not state.get("transaction") and tx_id:
            try:
                tx_res = await call_mcp_tool(
                    "get_transaction_details",
                    {"transaction_id": tx_id},
                    agent="supervisor",
                )
                if "error" in tx_res:
                    return {
                        "data_unavailable": True,
                        "escalation_required": True,
                        "escalation_reason": f"MCP transaction lookup failure: {tx_res.get('message', tx_res.get('error'))}",
                        "recommended_action": "investigate",
                        "precedence_level": 1,
                        "execution_errors": state.get("execution_errors", []) + [tx_res.get("error", "MCPError")],
                    }
                updates["transaction"] = tx_res
                # If customer_id was not explicitly in input, backfill from transaction
                if not cust_id and "customer_id" in tx_res:
                    cust_id = tx_res["customer_id"]
                    updates["customer_id"] = cust_id
            except Exception as e:
                return {
                    "data_unavailable": True,
                    "escalation_required": True,
                    "escalation_reason": f"MCP communication failure loading transaction {tx_id}: {str(e)}",
                    "recommended_action": "investigate",
                    "precedence_level": 1,
                    "execution_errors": state.get("execution_errors", []) + [str(e)],
                }

        # Fetch customer dispute history via MCP
        if not state.get("customer_history") and cust_id:
            try:
                cust_res = await call_mcp_tool(
                    "get_customer_dispute_history",
                    {"customer_id": cust_id},
                    agent="supervisor",
                )
                if "error" in cust_res:
                    return {
                        "data_unavailable": True,
                        "escalation_required": True,
                        "escalation_reason": f"Customer history not found via MCP: {cust_res['error']}",
                        "recommended_action": "investigate",
                        "precedence_level": 1,
                        "execution_errors": state.get("execution_errors", []) + [cust_res["error"]],
                    }
                updates["customer_history"] = cust_res
            except Exception as e:
                return {
                    "data_unavailable": True,
                    "escalation_required": True,
                    "escalation_reason": f"MCP communication failure loading customer {cust_id}: {str(e)}",
                    "recommended_action": "investigate",
                    "precedence_level": 1,
                    "execution_errors": state.get("execution_errors", []) + [str(e)],
                }

        return updates


def supervisor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Supervisor router node.
    Inspects current graph state and deterministically decides the next worker.
    Increments iteration counter to prevent infinite execution loops.
    """
    with trace_span(
        name="supervisor",
        span_kind="AGENT",
        agent="supervisor",
        attributes={"iteration_count": state.get("iteration_count", 0)},
    ) as span:
        iterations = state.get("iteration_count", 0) + 1
        updates: Dict[str, Any] = {"iteration_count": iterations}

        if iterations > MAX_SUPERVISOR_ITERATIONS:
            updates["escalation_required"] = True
            updates["escalation_reason"] = f"Loop limit exceeded: supervisor reached {iterations} steps"
            updates["recommended_action"] = "investigate"
            updates["precedence_level"] = 1
            updates["next_worker"] = "escalation_gate"
            span.set_attribute("supervisor.next_worker", "escalation_gate")
            return updates

        # Fatal error or data unavailable -> route directly to escalation gate if decision already reached
        if state.get("data_unavailable") or state.get("policy_retrieval_failed"):
            if state.get("recommended_action"):
                updates["next_worker"] = "escalation_gate"
            else:
                updates["next_worker"] = "decision_engine"
            span.set_attribute("supervisor.next_worker", updates["next_worker"])
            return updates

        # Security injection detected -> route to decision engine / escalation
        if "PROMPT_INJECTION_DETECTED" in state.get("guardrail_flags", []):
            updates["next_worker"] = "decision_engine"
            span.set_attribute("supervisor.next_worker", "decision_engine")
            return updates

        # 1. Missing context -> load context
        if not state.get("transaction") or not state.get("customer_history"):
            updates["next_worker"] = "load_context"
            span.set_attribute("supervisor.next_worker", "load_context")
            return updates

        # 2. Worker 1: Missing classification -> classifier
        if not state.get("dispute_category"):
            updates["next_worker"] = "classifier"
            span.set_attribute("supervisor.next_worker", "classifier")
            return updates

        # 3. Worker 2: Missing fraud score -> fraud scorer
        if state.get("fraud_score") is None:
            updates["next_worker"] = "fraud_scorer"
            span.set_attribute("supervisor.next_worker", "fraud_scorer")
            return updates

        # 4. Worker 3: Missing policy rule -> chargeback retriever
        if not state.get("selected_rule_id") and not state.get("policy_retrieval_failed"):
            updates["next_worker"] = "chargeback_retriever"
            span.set_attribute("supervisor.next_worker", "chargeback_retriever")
            return updates

        # 5. Missing decision -> decision engine
        if not state.get("recommended_action"):
            updates["next_worker"] = "decision_engine"
            span.set_attribute("supervisor.next_worker", "decision_engine")
            return updates

        # 6. Resolution phase: Escalation vs Synthesis
        if state.get("escalation_required"):
            if not state.get("final_response"):
                updates["next_worker"] = "escalation_gate"
                span.set_attribute("supervisor.next_worker", "escalation_gate")
                return updates
        else:
            if not state.get("final_response"):
                updates["next_worker"] = "synthesis"
                span.set_attribute("supervisor.next_worker", "synthesis")
                return updates

        # 7. Final output safety and audit
        if not state.get("final_response"):
            updates["next_worker"] = "output_guard"
            span.set_attribute("supervisor.next_worker", "output_guard")
            return updates

        updates["next_worker"] = "audit"
        span.set_attribute("supervisor.next_worker", "audit")
        return updates


def supervisor_conditional_edge(state: Dict[str, Any]) -> str:
    """Returns the next worker designated by supervisor_node."""
    next_node = state.get("next_worker", "audit")
    return next_node
