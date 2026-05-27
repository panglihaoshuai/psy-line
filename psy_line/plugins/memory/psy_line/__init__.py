"""PSY_line memory provider for Hermes Agent.

Provides MemoryProvider implementation for storing and querying
sentiment analysis history, behavioral signals, and market state snapshots.

This is an optional plugin — PSY_line works without it (no memory dependency).
"""

from typing import Any, Dict, List, Optional
from datetime import datetime


class PsyLineMemoryProvider:
    """Memory provider for PSY_line sentiment and signal history.

    Implements Hermes Agent's MemoryProvider interface.
    Stores sentiment analysis results, behavioral signals, and
    market states for historical query and analysis.
    """

    def __init__(
        self,
        collection: str = "sentiment_history",
        max_records: int = 10000,
    ):
        self.collection = collection
        self.max_records = max_records
        self._records: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Hermes MemoryProvider Interface
    # ------------------------------------------------------------------

    async def remember(
        self,
        key: str,
        value: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store a memory record.

        Args:
            key: Unique identifier (e.g. 'BTC_signal_2026-05-25T12:00:00')
            value: The data to store (sentiment scores, signal, market state)
            metadata: Optional metadata (timestamp, source, tags)

        Returns:
            True if stored successfully
        """
        record = {
            "key": key,
            "value": value,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
        }
        self._records.append(record)

        # Enforce max_records limit (FIFO eviction)
        if len(self._records) > self.max_records:
            self._records = self._records[-self.max_records :]

        return True

    async def recall(
        self,
        key: str,
        limit: int = 1,
    ) -> List[Dict[str, Any]]:
        """Retrieve memory records by key prefix.

        Args:
            key: Key or key prefix to search for
            limit: Max number of records to return

        Returns:
            List of matching records (newest first)
        """
        matches = [r for r in self._records if r["key"].startswith(key)]
        return matches[-limit:][::-1]  # newest first

    async def forget(self, key: str) -> bool:
        """Remove memory records matching key prefix.

        Args:
            key: Key or key prefix to remove

        Returns:
            True if any records were removed
        """
        before = len(self._records)
        self._records = [r for r in self._records if not r["key"].startswith(key)]
        return len(self._records) < before

    async def clear(self) -> bool:
        """Clear all memory records."""
        self._records.clear()
        return True

    # ------------------------------------------------------------------
    # PSY_line-specific convenience methods
    # ------------------------------------------------------------------

    async def store_signal(
        self,
        symbol: str,
        signal: str,
        confidence: float,
        behavior_phase: str,
        sentiment_scores: Dict[str, float],
        market_state: Dict[str, Any],
    ) -> str:
        """Store a behavioral signal with full context.

        Returns the key used for storage.
        """
        timestamp = datetime.now()
        key = f"{symbol}_signal_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        await self.remember(
            key,
            {
                "symbol": symbol,
                "signal": signal,
                "confidence": confidence,
                "behavior_phase": behavior_phase,
                "sentiment_scores": sentiment_scores,
                "market_state": market_state,
            },
            metadata={
                "type": "behavior_signal",
                "source": "psy_line",
            },
        )
        return key

    def get_stats(self) -> Dict[str, Any]:
        """Get memory provider statistics."""
        return {
            "collection": self.collection,
            "total_records": len(self._records),
            "max_records": self.max_records,
        }
