"""Sentiment history cache using SQLite."""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Optional
from dataclasses import dataclass

from .types import SentimentRecord, SentimentType, SignalType


class SentimentCache:
    """SQLite-based cache for sentiment history."""

    def __init__(self, db_path: str = "sentiment_cache.db"):
        """
        Initialize sentiment cache.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    subreddit TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    composite_sentiment REAL NOT NULL,
                    signal_type TEXT NOT NULL,
                    comments_analyzed INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON sentiment_history(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_symbol ON sentiment_history(symbol)
            """)
            conn.commit()

    def save(self, record: SentimentRecord) -> int:
        """
        Save a sentiment record to the cache.

        Args:
            record: SentimentRecord to save

        Returns:
            Row ID of inserted record
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO sentiment_history
                (timestamp, subreddit, symbol, composite_sentiment, signal_type, comments_analyzed)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.timestamp.isoformat(),
                    record.subreddit,
                    record.symbol,
                    record.composite_sentiment,
                    record.signal_type,
                    record.comments_analyzed,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_recent(self, symbol: str, hours: int = 24) -> List[SentimentRecord]:
        """
        Get recent sentiment records for a symbol.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            hours: Number of hours to look back

        Returns:
            List of SentimentRecord objects
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT timestamp, subreddit, symbol, composite_sentiment, signal_type, comments_analyzed
                FROM sentiment_history
                WHERE symbol = ? AND timestamp >= ?
                ORDER BY timestamp DESC
                """,
                (symbol, cutoff),
            )

            records = []
            for row in cursor.fetchall():
                records.append(
                    SentimentRecord(
                        timestamp=datetime.fromisoformat(row[0]),
                        subreddit=row[1],
                        symbol=row[2],
                        composite_sentiment=row[3],
                        signal_type=row[4],
                        comments_analyzed=row[5],
                    )
                )
            return records

    def get_all_for_symbol(self, symbol: str, limit: int = 100) -> List[SentimentRecord]:
        """
        Get all sentiment records for a symbol, most recent first.

        Args:
            symbol: Trading symbol
            limit: Maximum number of records to return

        Returns:
            List of SentimentRecord objects
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT timestamp, subreddit, symbol, composite_sentiment, signal_type, comments_analyzed
                FROM sentiment_history
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (symbol, limit),
            )

            records = []
            for row in cursor.fetchall():
                records.append(
                    SentimentRecord(
                        timestamp=datetime.fromisoformat(row[0]),
                        subreddit=row[1],
                        symbol=row[2],
                        composite_sentiment=row[3],
                        signal_type=row[4],
                        comments_analyzed=row[5],
                    )
                )
            return records

    def cleanup(self, days: int = 7) -> int:
        """
        Delete records older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of deleted records
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM sentiment_history WHERE timestamp < ?",
                (cutoff,),
            )
            conn.commit()
            return cursor.rowcount

    def get_stats(self, symbol: str, hours: int = 24) -> dict[str, object]:
        """
        Get statistics for recent sentiment.

        Args:
            symbol: Trading symbol
            hours: Number of hours to analyze

        Returns:
            Dict with avg_sentiment, num_scans, buy_count, sell_count, hold_count
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    AVG(composite_sentiment) as avg_sentiment,
                    COUNT(*) as num_scans,
                    SUM(CASE WHEN signal_type = 'BUY' THEN 1 ELSE 0 END) as buy_count,
                    SUM(CASE WHEN signal_type = 'SELL' THEN 1 ELSE 0 END) as sell_count,
                    SUM(CASE WHEN signal_type = 'HOLD' THEN 1 ELSE 0 END) as hold_count
                FROM sentiment_history
                WHERE symbol = ? AND timestamp >= ?
                """,
                (symbol, cutoff),
            )

            row = cursor.fetchone()
            return {
                "avg_sentiment": row[0] if row[0] is not None else 0.0,
                "num_scans": row[1] or 0,
                "buy_count": row[2] or 0,
                "sell_count": row[3] or 0,
                "hold_count": row[4] or 0,
            }
