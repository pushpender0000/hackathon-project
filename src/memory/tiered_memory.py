"""
Tiered Memory Architecture.

Integrates:
1. Short-term memory (LangGraph SQLite Checkpointer) for intra-thread state continuity.
2. Long-term semantic memory (SQLite-backed semantic store & LangMem interfaces) for cross-session recall.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from src.memory.short_term import ShortTermMemory
from src.memory.long_term import LongTermMemory


class TieredMemoryManager:
    """
    Unified manager for tiered memory across session and cross-session boundaries.
    """

    def __init__(
        self,
        checkpoint_db_path: Optional[Path] = None,
        semantic_db_path: Optional[Path] = None,
    ):
        self.short_term = ShortTermMemory(db_path=checkpoint_db_path)
        self.long_term = LongTermMemory(db_path=semantic_db_path)

    def get_checkpointer(self):
        """Returns the LangGraph-compatible checkpointer."""
        return self.short_term.get_checkpointer()

    def recall_prior_context(self, customer_id: str) -> Dict[str, Any]:
        """Recalls cross-session facts for a customer on a return visit."""
        return self.long_term.recall_facts(customer_id)

    def persist_session_facts(
        self,
        customer_id: str,
        facts: Dict[str, Any],
        source_dispute_id: Optional[str] = None,
    ):
        """Stores important dispute/customer facts to long-term memory upon session resolution."""
        for key, val in facts.items():
            self.long_term.store_fact(customer_id, key, val, source_dispute_id=source_dispute_id)

    def close(self):
        self.short_term.close()


_default_tiered_memory: Optional[TieredMemoryManager] = None


def get_tiered_memory_manager() -> TieredMemoryManager:
    global _default_tiered_memory
    if _default_tiered_memory is None:
        _default_tiered_memory = TieredMemoryManager()
    return _default_tiered_memory
