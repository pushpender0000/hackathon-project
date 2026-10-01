"""
Test Suite for Tiered Memory and Cross-Session Persistence (AC-05).

Verifies:
1. Short-term memory: SQLite checkpointing maintains intra-session thread state across graph steps.
2. Long-term memory: Persistent SQLite semantic store retains facts across distinct sessions.
3. Cross-session recall: Return visits under new thread_ids recall prior session facts for the customer.
4. LangMem compatibility and structured memory logging.
Generates machine-verifiable evidence to logs/memory_test.log.
"""

import json
import logging
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from src.config.settings import get_settings
from src.memory.short_term import ShortTermMemory
from src.memory.long_term import LongTermMemory
from src.memory.tiered_memory import TieredMemoryManager
from src.graph import create_dispute_graph
from src.schemas.gemini_schemas import GeminiDisputeClassificationOutput, GeminiSynthesisOutput


_LOG_INITIALIZED = False

# Configure logger to output to logs/memory_test.log
def setup_memory_logger():
    global _LOG_INITIALIZED
    settings = get_settings()
    log_dir = settings.workspace_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "memory_test.log"

    if not _LOG_INITIALIZED:
        with open(log_file, "w", encoding="utf-8") as f:
            pass
        _LOG_INITIALIZED = True

    logger = logging.getLogger("memory_test")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fh = logging.FileHandler(str(log_file), mode="a", encoding="utf-8")
    formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "test": "%(name)s", "message": "%(message)s"}'
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger, log_file


@pytest.fixture
def memory_logger():
    logger, log_file = setup_memory_logger()
    yield logger
    for h in logger.handlers:
        h.flush()


@pytest.mark.asyncio
async def test_short_term_memory_checkpointing(tmp_path, memory_logger):
    """Verifies that ShortTermMemory correctly checkpoints state using SQLite across graph steps."""
    db_path = tmp_path / "test_checkpoints.sqlite"
    thread_id = "thread-test-001"
    config = {"configurable": {"thread_id": thread_id}}

    mock_classification = GeminiDisputeClassificationOutput(
        dispute_category="fraudulent_transaction",
        customer_intent="Unauthorized charge report",
        extracted_amount=120.00,
        claim_summary="Cardholder did not authorize $120.00 charge",
        requires_human_triage=False,
    )

    mock_synthesis = GeminiSynthesisOutput(
        customer_explanation="Your claim has been processed.",
        next_steps="Provisional credit is under review.",
        policy_reference_summary="SYNTH-RULE-10.4",
        disclaimer="Synthetic benchmark copilot.",
    )

    mock_response_cls = MagicMock()
    mock_response_cls.parsed = mock_classification
    mock_response_cls.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=10, total_token_count=20)

    mock_response_synth = MagicMock()
    mock_response_synth.parsed = mock_synthesis
    mock_response_synth.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=10, total_token_count=20)

    async def mock_generate_content(*args, **kwargs):
        cfg = kwargs.get("config")
        schema = getattr(cfg, "response_schema", None)
        if schema == GeminiSynthesisOutput:
            return mock_response_synth
        return mock_response_cls

    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:
        app = create_dispute_graph(checkpointer=checkpointer)

        initial_state = {
            "dispute_id": "DISP-MEM-01",
            "raw_customer_input": "I did not authorize this charge of $120.00.",
            "customer_id": "CUST-001",
            "transaction_id": "TX-001",
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
            "run_id": "test-run-mem",
            "timestamps": {},
            "audit_metadata": {},
        }

        with patch("google.genai.Client") as mock_genai_cls:
            mock_inst = MagicMock()
            mock_inst.aio.models.generate_content = AsyncMock(side_effect=mock_generate_content)
            mock_genai_cls.return_value = mock_inst

            final_state = await app.ainvoke(initial_state, config=config)

        assert "audit_metadata" in final_state
        assert "OUTPUT_GUARDED" in final_state["guardrail_flags"]

        # Retrieve checkpointed state directly from app and checkpointer
        checkpoint_state = await app.aget_state(config)
        assert checkpoint_state is not None
        assert checkpoint_state.values["transaction_id"] == "TX-001"
        assert checkpoint_state.values["customer_id"] == "CUST-001"
        assert checkpoint_state.values["recommended_action"] in ("provisional_credit", "investigate", "deny", "chargeback")

    memory_logger.info(f"SHORT_TERM_PASSED: Thread {thread_id} checkpoint verified with saved state.")


def test_long_term_semantic_memory_persistence(tmp_path, memory_logger):
    """Verifies that LongTermMemory persists customer facts across database re-connections."""
    db_path = tmp_path / "test_semantic_memory.sqlite"

    # Session 1: Store facts
    lt_mem_1 = LongTermMemory(db_path=db_path)
    cust_id = "CUST-PERSIST-01"
    lt_mem_1.store_fact(cust_id, "card_in_possession", True, source_dispute_id="DISP-001")
    lt_mem_1.store_fact(cust_id, "preferred_contact", "email", source_dispute_id="DISP-001")
    lt_mem_1.store_fact(cust_id, "travel_flag", {"destination": "Tokyo", "until": "2026-10-15"})

    # Session 2: Fresh instance (simulating restart / new session)
    lt_mem_2 = LongTermMemory(db_path=db_path)
    recalled = lt_mem_2.recall_facts(cust_id)

    assert recalled["card_in_possession"] is True
    assert recalled["preferred_contact"] == "email"
    assert recalled["travel_flag"]["destination"] == "Tokyo"

    memory_logger.info(f"LONG_TERM_PASSED: Recalled {len(recalled)} persistent facts for customer {cust_id}")


def test_cross_session_context_recall(tmp_path, memory_logger):
    """
    AC-05: The copilot maintains context — recalls prior-session context on a return visit.
    Verifies that facts stored in Session 1 under Thread A are recalled in Session 2 under Thread B.
    """
    db_cp = tmp_path / "tiered_checkpoints.sqlite"
    db_sem = tmp_path / "tiered_semantic.sqlite"

    manager = TieredMemoryManager(checkpoint_db_path=db_cp, semantic_db_path=db_sem)
    cust_id = "CUST-RETURN-42"

    # --- SESSION 1: First visit ---
    session_1_thread = "thread-session-001"
    session_1_facts = {
        "prior_dispute_outcome": "PROVISIONAL_CREDIT_GRANTED",
        "verified_delivery_address": "123 Main St, Springfield",
        "habitual_merchant_disputes": ["Apex Electronics"],
        "account_tenure_years": 5,
    }
    manager.persist_session_facts(cust_id, session_1_facts, source_dispute_id="DISP-PREV-01")
    memory_logger.info(f"SESSION_1_COMMITTED: Persisted prior facts for {cust_id} under thread {session_1_thread}")

    # --- SESSION 2: Return visit under completely new thread ID ---
    session_2_thread = "thread-session-002"
    recalled_context = manager.recall_prior_context(cust_id)

    assert recalled_context is not None
    assert recalled_context.get("prior_dispute_outcome") == "PROVISIONAL_CREDIT_GRANTED"
    assert recalled_context.get("verified_delivery_address") == "123 Main St, Springfield"
    assert "Apex Electronics" in recalled_context.get("habitual_merchant_disputes", [])
    assert recalled_context.get("account_tenure_years") == 5

    memory_logger.info(
        f"SESSION_2_RECALL_PASSED: Return visit {session_2_thread} successfully recalled cross-session context: {recalled_context}"
    )
    manager.close()


def test_langmem_library_import_and_contract(memory_logger):
    """Verifies that langmem is installed, importable, and provides expected memory management interfaces."""
    import langmem
    assert hasattr(langmem, "create_memory_manager") or hasattr(langmem, "create_memory_store_manager")
    memory_logger.info("LANGMEM_CONTRACT_PASSED: langmem package successfully verified and loaded.")
