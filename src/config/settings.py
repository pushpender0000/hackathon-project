import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

class Settings:
    """Centralized configuration loaded from environment variables."""

    def __init__(self):
        # Base Workspace Paths
        self.workspace_root: Path = Path(__file__).resolve().parent.parent.parent

        # Gemini Model Settings
        self.gemini_api_key: Optional[str] = os.environ.get("GEMINI_API_KEY")
        self.gemini_model: str = os.environ.get("GEMINI_MODEL", "").strip()

        # Quota-Safe Thinking Governance (Supports Gemini 3.x and 2.5 families)
        self.gemini_thinking_level: str = os.environ.get("GEMINI_THINKING_LEVEL", "minimal").strip().lower()
        raw_thinking_budget = os.environ.get("GEMINI_THINKING_BUDGET", "0")
        try:
            self.gemini_thinking_budget: int = int(raw_thinking_budget)
        except ValueError:
            self.gemini_thinking_budget = 0

        # Validate thinking governance based on model family
        if self.gemini_model.startswith("gemini-3") or "3." in self.gemini_model:
            valid_levels = {"minimal", "low", "medium", "high"}
            if self.gemini_thinking_level not in valid_levels:
                raise ValueError(
                    f"Invalid GEMINI_THINKING_LEVEL '{self.gemini_thinking_level}' for Gemini 3.x. "
                    f"Must be one of {valid_levels}, preferably 'minimal' for quota safety."
                )
        else:
            if self.gemini_thinking_budget != 0:
                raise ValueError(
                    f"Architecture violation: GEMINI_THINKING_BUDGET must be 0 for Gemini 2.x quota safety, "
                    f"got {self.gemini_thinking_budget}"
                )

        # Output Token Ceilings
        self.classifier_max_output_tokens: int = self._parse_int("GEMINI_CLASSIFIER_MAX_OUTPUT_TOKENS", 300)
        self.synthesis_max_output_tokens: int = self._parse_int("GEMINI_SYNTHESIS_MAX_OUTPUT_TOKENS", 500)
        self.judge_max_output_tokens: int = self._parse_int("GEMINI_JUDGE_MAX_OUTPUT_TOKENS", 350)

        # Cumulative Safety Ceilings
        self.max_cumulative_tokens: int = self._parse_int("GEMINI_MAX_CUMULATIVE_TOKENS", 30000)

        # Paths
        self.data_dir: Path = self.workspace_root / "data"
        self.policy_corpus_dir: Path = self.workspace_root / "data" / "policy_corpus"
        self.memory_dir: Path = self.workspace_root / "data" / "memory"
        self.logs_dir: Path = self.workspace_root / "logs"
        self.traces_dir: Path = self.workspace_root / "traces"
        self.reports_dir: Path = self.workspace_root / "reports"

        # Database Paths
        self.sqlite_checkpoints_path: str = os.environ.get(
            "SQLITE_DB_PATH", str(self.memory_dir / "checkpoints.sqlite")
        )
        self.sqlite_long_term_store_path: str = os.environ.get(
            "LONG_TERM_STORE_PATH", str(self.memory_dir / "long_term_store.sqlite")
        )

        # Synthetic Business Triage Benchmarks (Defined explicitly as benchmark thresholds)
        self.provisional_credit_max_amount: float = 150.00
        self.high_value_escalation_amount: float = 1000.00
        self.fraud_score_high_risk_threshold: float = 80.0
        self.chronic_dispute_count_threshold: int = 5
        self.low_risk_fraud_score_max: float = 30.0
        # Calibrated RAG confidence threshold: distinguishes valid policy claims (>=0.44) from irrelevant/OOD queries (<=0.34)
        self.rag_retrieval_threshold: float = float(os.environ.get("RAG_RETRIEVAL_THRESHOLD", "0.42"))

    def _parse_int(self, env_var: str, default: int) -> int:
        val = os.environ.get(env_var)
        if not val:
            return default
        try:
            parsed = int(val)
            if parsed <= 0:
                return default
            return parsed
        except ValueError:
            return default

    def validate_api_credentials(self) -> bool:
        """Returns True if Gemini API credentials and model are configured."""
        return bool(self.gemini_api_key and self.gemini_model)

_settings_instance: Optional[Settings] = None

def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
