"""
Tests for Gemini-facing schemas.
Verifies that all schemas have ZERO field defaults for Google GenAI compatibility.
"""

import pytest
from pydantic_core import PydanticUndefined
from src.schemas.gemini_schemas import (
    GeminiDisputeClassificationOutput,
    GeminiSynthesisOutput,
)


def test_gemini_schemas_have_zero_defaults():
    """Verify that every field in Gemini response schemas has no default value."""
    schemas = [GeminiDisputeClassificationOutput, GeminiSynthesisOutput]

    for schema_cls in schemas:
        for field_name, field_info in schema_cls.model_fields.items():
            assert field_info.default is PydanticUndefined, (
                f"Architecture violation: Field '{field_name}' in '{schema_cls.__name__}' "
                f"has default '{field_info.default}'. Gemini-facing schemas must have ZERO defaults."
            )
            assert field_info.default_factory is None, (
                f"Field '{field_name}' in '{schema_cls.__name__}' has default_factory."
            )


def test_gemini_dispute_classification_output_validation():
    """Test valid and invalid inputs for dispute classification output schema."""
    valid_data = {
        "dispute_category": "fraudulent_transaction",
        "customer_intent": "Customer states card was stolen",
        "extracted_amount": 35.50,
        "claim_summary": "Unauthorized ride",
        "requires_human_triage": False,
    }
    model = GeminiDisputeClassificationOutput(**valid_data)
    assert model.dispute_category == "fraudulent_transaction"
    assert model.extracted_amount == 35.50

    # Test invalid category
    with pytest.raises(Exception):
        GeminiDisputeClassificationOutput(
            dispute_category="invalid_category_name",
            customer_intent="test",
            extracted_amount=None,
            claim_summary="test",
            requires_human_triage=True,
        )


def test_gemini_synthesis_output_validation():
    """Test valid and invalid inputs for synthesis output schema."""
    valid_data = {
        "customer_explanation": "Your claim has been triaged for provisional credit.",
        "next_steps": "No further action needed at this time.",
        "policy_reference_summary": "Governed under SYNTH-RULE-10.4 Card Absent Fraud.",
        "disclaimer": "This is a synthetic benchmark dispute copilot.",
    }
    model = GeminiSynthesisOutput(**valid_data)
    assert model.customer_explanation.startswith("Your claim")
