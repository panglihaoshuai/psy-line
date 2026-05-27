"""Fear and Greed Index data source.

API: https://api.alternative.me/fng/
Free, no API key required.
"""

import requests
from typing import Dict, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class FearGreedData:
    """Fear and Greed Index data."""
    value: int  # 0-100
    value_classification: str  # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    timestamp: datetime
    time_until_update: Optional[int] = None  # seconds until next update

    @property
    def sentiment_score(self) -> float:
        """Convert 0-100 to -1 to 1 scale."""
        return (self.value - 50) / 50  # 0 -> -1, 50 -> 0, 100 -> 1


class FearGreedClient:
    """Client for Alternative.me Fear and Greed Index API."""

    BASE_URL = "https://api.alternative.me/fng/"

    def __init__(self):
        self._session = requests.Session()

    def get_current(self) -> FearGreedData:
        """
        Get current Fear and Greed Index.

        Returns:
            FearGreedData with current index value and classification
        """
        response = self._session.get(self.BASE_URL, params={"limit": 1}, timeout=10)
        response.raise_for_status()
        data = response.json()

        item = data["data"][0]
        return FearGreedData(
            value=int(item["value"]),
            value_classification=item["value_classification"],
            timestamp=datetime.fromtimestamp(int(item["timestamp"])),
            time_until_update=int(item.get("time_until_update", 0)),
        )

    def get_history(self, days: int = 30) -> list[FearGreedData]:
        """
        Get historical Fear and Greed data.

        Args:
            days: Number of days of history to fetch

        Returns:
            List of FearGreedData sorted by time (newest first)
        """
        response = self._session.get(self.BASE_URL, params={"limit": days}, timeout=10)
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data["data"]:
            results.append(
                FearGreedData(
                    value=int(item["value"]),
                    value_classification=item["value_classification"],
                    timestamp=datetime.fromtimestamp(int(item["timestamp"])),
                )
            )
        return results

    def get_average(self, days: int = 7) -> float:
        """Get average Fear and Greed value over N days."""
        history = self.get_history(days)
        if not history:
            return 50.0
        return sum(d.value for d in history) / len(history)
