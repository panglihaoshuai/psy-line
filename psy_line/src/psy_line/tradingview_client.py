"""TradingView sentiment data source.

Note: TradingView doesn't have an official free API.
This module provides integration with free alternatives that aggregate TradingView data.

Uses cryptocurrency.cv API which provides:
- Social sentiment from multiple sources
- TradingView buzz data
"""

import requests
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class TradingViewSentiment:
    """TradingView-style sentiment data."""
    symbol: str
    sentiment: float  # -1 to 1
    classification: str  # "Bearish", "Neutral", "Bullish"
    buzz: float  # Social media buzz score
    timestamp: datetime


class TradingViewClient:
    """
    Client for social sentiment data.

    Uses cryptocurrency.cv free API (no auth required).
    Alternative: TradingView social sentiment via various aggregators.
    """

    BASE_URL = "https://cryptocurrency.cv"

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "PSY_line/1.0"
        })

    def get_sentiment(self, symbols: Optional[List[str]] = None) -> Dict[str, TradingViewSentiment]:
        """
        Get sentiment for symbols.

        Args:
            symbols: List of symbols (e.g., ["BTC", "ETH"]). If None, returns overall market.

        Returns:
            Dict mapping symbol to TradingViewSentiment
        """
        if symbols is None:
            symbols = ["BTC"]

        results = {}

        try:
            # Try cryptocurrency.cv social sentiment endpoint
            response = self._session.get(
                f"{self.BASE_URL}/api/social",
                params={"coins": ",".join(symbols)},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()

                # Parse response format
                if isinstance(data, dict) and "data" in data:
                    for item in data["data"]:
                        symbol = item.get("symbol", item.get("coin", "UNKNOWN"))
                        sentiment_score = float(item.get("sentiment", item.get("score", 0)))
                        buzz = float(item.get("buzz", item.get("mentions", 0)))

                        # Convert 0-100 to -1 to 1 if needed
                        if sentiment_score > 1:
                            sentiment_score = (sentiment_score - 50) / 50

                        if sentiment_score > 0.2:
                            classification = "Bullish"
                        elif sentiment_score < -0.2:
                            classification = "Bearish"
                        else:
                            classification = "Neutral"

                        results[symbol] = TradingViewSentiment(
                            symbol=symbol,
                            sentiment=sentiment_score,
                            classification=classification,
                            buzz=buzz,
                            timestamp=datetime.now(),
                        )

        except Exception as e:
            print(f"TradingView sentiment error: {e}", file=__import__("sys").stderr)

        # Return default if failed
        for symbol in symbols:
            if symbol not in results:
                results[symbol] = TradingViewSentiment(
                    symbol=symbol,
                    sentiment=0.0,
                    classification="Neutral",
                    buzz=50.0,
                    timestamp=datetime.now(),
                )

        return results

    def get_overall_market(self) -> TradingViewSentiment:
        """
        Get overall crypto market sentiment.

        Returns:
            TradingViewSentiment for overall market
        """
        try:
            response = self._session.get(
                f"{self.BASE_URL}/api/social/monitor",
                params={"hours": 24},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return TradingViewSentiment(
                    symbol="MARKET",
                    sentiment=0.0,  # Parse from response
                    classification="Neutral",
                    buzz=data.get("total_buzz", 50.0),
                    timestamp=datetime.now(),
                )

        except Exception:
            pass

        return TradingViewSentiment(
            symbol="MARKET",
            sentiment=0.0,
            classification="Neutral",
            buzz=50.0,
            timestamp=datetime.now(),
        )
