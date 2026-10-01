import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any

# Ensure workspace root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP
from mcp_server.data_access import CoreBankingDataAccess
from src.tools.logging_wrapper import log_mcp_event

# Initialize FastMCP Server
mcp = FastMCP(
    "banking_copilot_mcp",
    instructions="Core Banking and Synthetic Chargeback Policy MCP Server"
)

# Initialize data access
data_access = CoreBankingDataAccess()

@mcp.tool(
    name="get_transaction_details",
    description="Retrieve structured core banking card transaction details by transaction_id."
)
def get_transaction_details(transaction_id: str) -> Dict[str, Any]:
    """
    Retrieves core banking transaction record including merchant, amount, currency,
    and masked card PAN. Returns structured error if transaction not found.
    """
    start_time = time.perf_counter()
    status = "SUCCESS"
    try:
        result = data_access.get_transaction_details(transaction_id)
        if "error" in result:
            if result.get("code") == 404:
                status = "NOT_FOUND"
            elif result.get("code") in (500, 502, 504):
                status = "GATEWAY_TIMEOUT" if result.get("code") == 504 else "ERROR"
            else:
                status = "INVALID_ARGUMENT"
        return result
    except Exception as e:
        status = "ERROR"
        result = {"error": type(e).__name__, "message": str(e), "code": 500}
        return result
    finally:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        log_mcp_event(
            method="tools/call",
            tool_name="get_transaction_details",
            args={"transaction_id": transaction_id},
            result=result,
            status=status,
            latency_ms=latency_ms
        )

@mcp.tool(
    name="get_customer_dispute_history",
    description="Retrieve historical dispute statistics, tenure, and prior fraud claims for a customer."
)
def get_customer_dispute_history(customer_id: str) -> Dict[str, Any]:
    """
    Retrieves customer dispute profile including prior dispute counts, win rates,
    and prior fraud report flags. Returns structured error if customer not found.
    """
    start_time = time.perf_counter()
    status = "SUCCESS"
    try:
        result = data_access.get_customer_dispute_history(customer_id)
        if "error" in result:
            status = "NOT_FOUND" if result.get("code") == 404 else "INVALID_ARGUMENT"
        return result
    except Exception as e:
        status = "ERROR"
        result = {"error": type(e).__name__, "message": str(e), "code": 500}
        return result
    finally:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        log_mcp_event(
            method="tools/call",
            tool_name="get_customer_dispute_history",
            args={"customer_id": customer_id},
            result=result,
            status=status,
            latency_ms=latency_ms
        )

# RFC 3986 requires URI scheme to use letters, digits, plus, period, or hyphen (no underscores)
RESOURCE_URI = "dispute-policy-spec://network_rules"

@mcp.resource(
    uri=RESOURCE_URI,
    name="synthetic_network_rules_metadata",
    description="Synthetic benchmark card network dispute rules and bank triage thresholds",
    mime_type="application/json"
)
def get_network_rules_resource() -> str:
    """
    Exposes the synthetic policy catalog metadata, including valid rule reason codes,
    maximum filing days, and triage thresholds.
    """
    start_time = time.perf_counter()
    status = "SUCCESS"
    try:
        metadata = data_access.get_policy_metadata()
        content = json.dumps(metadata)
        return content
    except Exception as e:
        status = "ERROR"
        content = json.dumps({"error": str(e)})
        return content
    finally:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        log_mcp_event(
            method="resources/read",
            uri=RESOURCE_URI,
            result={"status": "resource_returned", "bytes": len(content)},
            status=status,
            latency_ms=latency_ms
        )

if __name__ == "__main__":
    mcp.run(transport="stdio")
