"""Sentiment record dataclass for cache."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SentimentRecord:
    """A sentiment history record."""

    timestamp: datetime
    subreddit: str
    symbol: str
    composite_sentiment: float
    signal_type: str  # BUY, SELL, HOLD
    comments_analyzed: int = 0
