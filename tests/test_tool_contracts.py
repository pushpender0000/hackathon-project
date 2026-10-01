import pytest
import sys
import json
import re
from mcp_server.data_access import CoreBankingDataAccess
from mcp_server.schemas import TransactionDetailsOutput, CustomerDisputeHistoryOutput
from src.utils.masking import mask_card_pan, mask_account_number, mask_text_sensitive_data, sanitize_data
from langchain_mcp_adapters.client import MultiServerMCPClient

@pytest.fixture
def data_access():
    return CoreBankingDataAccess()

def test_get_transaction_valid(data_access):
    """Test valid transaction lookup returns expected fields and masked PAN."""
    res = data_access.get_transaction_details("TX-001")
    assert "error" not in res
    assert res["transaction_id"] == "TX-001"
    assert res["customer_id"] == "CUST-001"
    assert res["amount"] == 35.50
    assert res["masked_pan"].startswith("****-****-****-")
    # Verify no raw 16-digit number exists
    assert not re.search(r"\b\d{16}\b", json.dumps(res))

def test_get_transaction_invalid(data_access):
    """Test non-existent transaction returns structured 404 error."""
    res = data_access.get_transaction_details("TX-NONEXISTENT-999")
    assert "error" in res
    assert res["error"] == "TransactionNotFound"
    assert res["code"] == 404

def test_get_transaction_mcp_fail_injection(data_access):
    """Test deterministic MCP gateway failure injection for synthetic test ID TX-MCP-FAIL."""
    res = data_access.get_transaction_details("TX-MCP-FAIL")
    assert "error" in res
    assert res["error"] == "MCPGatewayFailure"
    assert res["code"] == 504

def test_get_transaction_malformed(data_access):
    """Test malformed transaction ID returns structured 400 error."""
    res_empty = data_access.get_transaction_details("")
    assert res_empty["code"] == 400
    assert res_empty["error"] == "InvalidTransactionId"

    res_special = data_access.get_transaction_details("TX-001; DROP TABLE")
    assert res_special["code"] == 400
    assert res_special["error"] == "MalformedTransactionId"

def test_get_customer_history_valid(data_access):
    """Test valid customer dispute history lookup."""
    res = data_access.get_customer_dispute_history("CUST-001")
    assert "error" not in res
    assert res["customer_id"] == "CUST-001"
    assert "total_prior_disputes" in res
    assert "win_rate" in res
    assert isinstance(res["total_prior_disputes"], int)
    assert isinstance(res["win_rate"], float)

def test_get_customer_history_invalid(data_access):
    """Test non-existent customer returns structured 404 error."""
    res = data_access.get_customer_dispute_history("CUST-99999")
    assert "error" in res
    assert res["error"] == "CustomerNotFound"
    assert res["code"] == 404

def test_get_customer_history_malformed(data_access):
    """Test malformed customer ID returns structured 400 error."""
    res = data_access.get_customer_dispute_history("CUST $#@!")
    assert res["code"] == 400
    assert res["error"] == "MalformedCustomerId"

def test_policy_metadata_resource(data_access):
    """Test synthetic policy metadata contains required benchmark rules and disclaimer."""
    meta = data_access.get_policy_metadata()
    assert "disclaimer" in meta
    assert "synthetic benchmark" in meta["disclaimer"].lower()
    assert "rules_index" in meta
    assert "SYNTH-RULE-10.4" in meta["rules_index"]
    assert "SYNTH-RULE-13.1" in meta["rules_index"]
    assert "SYNTH-RULE-4837" in meta["rules_index"]
    assert "SYNTH-RULE-4853" in meta["rules_index"]
    assert "thresholds" in meta
    assert meta["thresholds"]["provisional_credit_max_amount"] == 150.00
    assert meta["thresholds"]["high_value_escalation_amount"] == 1000.00

def test_masking_utilities():
    """Test PAN, account number, and recursive data sanitization."""
    raw_pan = "4111222233334444"
    masked = mask_card_pan(raw_pan)
    assert masked == "****-****-****-4444"

    raw_acc = "1234567890"
    masked_acc = mask_account_number(raw_acc)
    assert masked_acc == "******7890"

    text_with_pan = "My card number is 4111 2222 3333 4444 please charge it."
    sanitized_text = mask_text_sensitive_data(text_with_pan)
    assert "4111 2222 3333 4444" not in sanitized_text
    assert "****-****-****-4444" in sanitized_text

    nested_dict = {
        "card_pan": "4111222233334444",
        "notes": "Transaction for 5555666677778888",
        "sub": {"account_number": "9876543210"}
    }
    cleaned = sanitize_data(nested_dict)
    assert cleaned["card_pan"] == "****-****-****-4444"
    assert "5555666677778888" not in cleaned["notes"]
    assert cleaned["sub"]["account_number"] == "******3210"

@pytest.mark.asyncio
async def test_mcp_client_adapter_boundary():
    """
    Integration smoke test exercising the actual MCP client-server boundary
    via langchain-mcp-adapters over stdio.
    """
    client = MultiServerMCPClient({
        "banking": {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-m", "mcp_server.server"]
        }
    })
    
    # 1. Verify Tool Discovery
    tools = await client.get_tools()
    tool_names = [t.name for t in tools]
    assert "get_transaction_details" in tool_names
    assert "get_customer_dispute_history" in tool_names

    # 2. Verify Tool 1: get_transaction_details Execution over stdio
    tx_tool = next(t for t in tools if t.name == "get_transaction_details")
    result_tx = await tx_tool.ainvoke({"transaction_id": "TX-002"})
    assert result_tx is not None
    parsed_tx = json.loads(result_tx[0]["text"]) if isinstance(result_tx, list) else json.loads(result_tx)
    assert parsed_tx["transaction_id"] == "TX-002"
    assert parsed_tx["customer_id"] == "CUST-002"
    assert parsed_tx["amount"] == 42.10
    assert parsed_tx["masked_pan"].startswith("****-****-****-")
    # Verify no raw PAN exposure
    assert not any(c.isdigit() for c in parsed_tx["masked_pan"][:12])

    # 3. Verify Tool 2: get_customer_dispute_history Execution over stdio
    cust_tool = next(t for t in tools if t.name == "get_customer_dispute_history")
    result_cust = await cust_tool.ainvoke({"customer_id": "CUST-002"})
    assert result_cust is not None
    parsed_cust = json.loads(result_cust[0]["text"]) if isinstance(result_cust, list) else json.loads(result_cust)
    assert parsed_cust["customer_id"] == "CUST-002"
    assert "total_prior_disputes" in parsed_cust
    assert "open_disputes" in parsed_cust
    assert "prior_fraud_reports" in parsed_cust
    assert "win_rate" in parsed_cust
    assert "tenure_months" in parsed_cust
    assert isinstance(parsed_cust["total_prior_disputes"], int)

    # 4. Verify Resource Retrieval over stdio
    resources = await client.get_resources(uris="dispute-policy-spec://network_rules")
    assert len(resources) == 1
    resource_payload = json.loads(resources[0].data)
    assert "rules_index" in resource_payload
    assert "SYNTH-RULE-10.4" in resource_payload["rules_index"]


def test_gemini_thinking_config_helper():
    """Verify model-specific thinking configuration governance for Gemini 3.x vs 2.5."""
    from src.utils.gemini_config import (
        detect_model_family,
        get_thinking_config,
        build_generate_content_config,
    )
    from google.genai import types

    # 1. Family detection
    assert detect_model_family("gemini-3.6-flash") == "gemini-3"
    assert detect_model_family("gemini-3-flash") == "gemini-3"
    assert detect_model_family("gemini-2.5-flash") == "gemini-2.5"
    assert detect_model_family("gemini-2.0-flash") == "gemini-2.5"

    # 2. Gemini 3.x configuration
    cfg_3 = get_thinking_config("gemini-3.6-flash", thinking_level="minimal")
    assert cfg_3.thinking_level == types.ThinkingLevel.MINIMAL
    assert cfg_3.thinking_budget is None

    gen_cfg_3 = build_generate_content_config(
        model_name="gemini-3.6-flash",
        temperature=0.0,
        max_output_tokens=300,
        thinking_level="minimal",
    )
    assert gen_cfg_3.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL
    assert gen_cfg_3.thinking_config.thinking_budget is None
    assert gen_cfg_3.temperature == 0.0
    assert gen_cfg_3.max_output_tokens == 300

    # 3. Gemini 2.x configuration
    cfg_2 = get_thinking_config("gemini-2.5-flash", thinking_budget=0)
    assert cfg_2.thinking_budget == 0
    assert cfg_2.thinking_level is None

    gen_cfg_2 = build_generate_content_config(
        model_name="gemini-2.5-flash",
        temperature=0.0,
        max_output_tokens=300,
        thinking_budget=0,
    )
    assert gen_cfg_2.thinking_config.thinking_budget == 0
    assert gen_cfg_2.thinking_config.thinking_level is None

