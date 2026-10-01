"""
Tests for RAG retrieval calibration and out-of-scope query rejection.

Asserts that:
1. Valid policy queries retrieve correct synthetic rules with confidence >= 0.42.
2. Irrelevant / out-of-domain queries fail retrieval threshold and return None (no fabricated citation).
"""

import pytest
from src.tools.rag_tool import get_rag_retriever
from src.config.settings import get_settings


@pytest.fixture
def rag_retriever():
    return get_rag_retriever()


def test_rag_retrieval_calibration_positive_queries(rag_retriever):
    """
    Verifies that domain-relevant dispute claims achieve confidence scores >= calibrated threshold (0.42)
    and match the expected synthetic benchmark rule.
    """
    positive_cases = [
        (
            "fraudulent transaction claim card absent unauthorized charge",
            ["SYNTH-RULE-4837", "SYNTH-RULE-10.4"],
        ),
        (
            "merchandise not received never delivered package missing",
            ["SYNTH-RULE-13.1"],
        ),
        (
            "incorrect amount duplicate charge billed twice processing error",
            ["SYNTH-RULE-4853"],
        ),
        (
            "recurring transaction cancellation canceled subscription charged again",
            ["SYNTH-RULE-4853", "SYNTH-RULE-13.1"],
        ),
    ]

    for query, expected_rules in positive_cases:
        res = rag_retriever.retrieve_best_rule(query_text=query)
        assert res is not None, f"Expected successful retrieval for: {query}"
        rule_meta, score = res
        assert score >= 0.42, f"Expected score >= 0.42, got {score} for '{query}'"
        assert rule_meta["rule_id"] in expected_rules, (
            f"Expected rule in {expected_rules}, got {rule_meta['rule_id']}"
        )


def test_rag_retrieval_calibration_negative_queries(rag_retriever):
    """
    Verifies that irrelevant, out-of-domain, or nonsensical queries fall below the
    calibrated threshold (0.42) and return None (never fabricating a synthetic rule or citation).
    """
    negative_cases = [
        "unrelated financial advice should I buy index funds or municipal bonds",
        "what is the stock price of Tesla today and should I invest my retirement money",
        "unrelated technical question how do I configure Kubernetes ingress nginx controller",
        "banana apple orange purple elephant dancing on a cloud in outer space",
    ]

    for query in negative_cases:
        res = rag_retriever.retrieve_best_rule(query_text=query)
        assert res is None, (
            f"Expected None (rejection) for irrelevant query '{query}', but got: {res}"
        )


def test_rag_threshold_configuration_consistency():
    """Verifies settings.rag_retrieval_threshold matches the calibrated benchmark value."""
    settings = get_settings()
    assert settings.rag_retrieval_threshold == 0.42
