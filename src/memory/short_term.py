"""
Short-Term Memory Manager using LangGraph SQLite Checkpointer.

Maintains conversation and execution state across multiple graph steps and turns
within a single thread/session.
Supports both synchronous SqliteSaver and asynchronous AsyncSqliteSaver.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from src.config.settings import get_settings


class ShortTermMemory:
    """Manages thread-scoped state checkpointing via SQLite."""

    def __init__(self, db_path: Optional[Path] = None):
        settings = get_settings()
        self.db_path = db_path or Path(settings.sqlite_checkpoints_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.checkpointer = SqliteSaver(self.conn)

    def get_checkpointer(self) -> SqliteSaver:
        return self.checkpointer

    def get_async_checkpointer(self) -> AsyncSqliteSaver:
        return AsyncSqliteSaver.from_conn_string(str(self.db_path))

    def get_thread_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves the latest checkpointed state for a thread."""
        config = {"configurable": {"thread_id": thread_id}}
        checkpoint_tuple = self.checkpointer.get_tuple(config)
        if checkpoint_tuple and checkpoint_tuple.checkpoint:
            return checkpoint_tuple.checkpoint.get("channel_values", {})
        return None

    def close(self):
        """Closes the underlying SQLite connection."""
        try:
            self.conn.close()
        except Exception:
            pass
