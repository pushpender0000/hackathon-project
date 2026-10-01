"""
Long-Term / Semantic Memory Manager.

Persists customer facts, resolution patterns, and verified dispute history across sessions.
Implements semantic memory retrieval using SQLite-backed key-value store and LangMem-compatible
fact extraction interfaces.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.config.settings import get_settings


class LongTermMemory:
    """
    Persistent cross-session semantic memory store for customer dispute context.
    """

    def __init__(self, db_path: Optional[Path] = None):
        settings = get_settings()
        self.db_path = db_path or (settings.data_dir / "semantic_memory.sqlite")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initializes tables for customer facts, dispute history, and cross-session memory."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS customer_semantic_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    fact_value TEXT NOT NULL,
                    source_dispute_id TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(customer_id, fact_key)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_customer_facts ON customer_semantic_facts(customer_id);
            """)
            conn.commit()

    def store_fact(
        self,
        customer_id: str,
        fact_key: str,
        fact_value: Any,
        source_dispute_id: Optional[str] = None,
    ):
        """Stores or updates a semantic fact for a customer across sessions."""
        val_str = json.dumps(fact_value) if not isinstance(fact_value, str) else fact_value
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO customer_semantic_facts (customer_id, fact_key, fact_value, source_dispute_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(customer_id, fact_key) DO UPDATE SET
                    fact_value = excluded.fact_value,
                    source_dispute_id = excluded.source_dispute_id,
                    created_at = excluded.created_at
            """, (customer_id, fact_key, val_str, source_dispute_id, now))
            conn.commit()

    def recall_facts(self, customer_id: str) -> Dict[str, Any]:
        """Recalls all verified facts for a customer across prior sessions."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("""
                SELECT fact_key, fact_value FROM customer_semantic_facts
                WHERE customer_id = ?
            """, (customer_id,))
            rows = cursor.fetchall()

        facts = {}
        for k, v in rows:
            try:
                facts[k] = json.loads(v)
            except Exception:
                facts[k] = v
        return facts

    def clear_customer_facts(self, customer_id: str):
        """Cleans up memory for a customer (for testing/compliance)."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM customer_semantic_facts WHERE customer_id = ?", (customer_id,))
            conn.commit()
