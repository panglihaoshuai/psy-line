"""Google Trends data source.

Uses pytrends library to fetch search interest for cryptocurrencies.
"""

import json
from typing import TYPE_CHECKING, List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass

# pytrends requires manual installation: pip install pytrends
# Note: Google Trends API has rate limits and requires special handling

if TYPE_CHECKING:
    from pytrends.request import TrendReq
    import pandas as pd


@dataclass
class GoogleTrendsData:
    """Google Trends search interest data."""
    keyword: str
    value: float  # 0-100 Google Trends score
    timestamp: datetime
    timeframe: str  # e.g., "now 1h", "past 24h", "past 7 days"


class GoogleTrendsClient:
    """Client for Google Trends API via pytrends with proxy support."""

    def __init__(self, proxy_url: str = "http://127.0.0.1:7897"):
        """
        Initialize Google Trends client with optional proxy.

        Args:
            proxy_url: HTTP/SOCKS proxy URL (e.g., "http://127.0.0.1:7897").
                       Set to "" or None to disable proxy.
        """
        self._connected = False
        self._pytrends: Optional["TrendReq"] = None
        self._proxy_url = proxy_url

    def _ensure_connected(self):
        """Lazy connect to pytrends with proxy."""
        if not self._connected:
            try:
                from pytrends.request import TrendReq
                import os

                proxy = self._proxy_url or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

                if proxy:
                    # pytrends accepts proxies dict directly
                    self._pytrends = TrendReq(proxies={"https": proxy, "http": proxy})  # pyright: ignore[reportArgumentType]
                else:
                    self._pytrends = TrendReq()

                self._connected = True
            except ImportError:
                raise ImportError(
                    "pytrends not installed. Run: pip install pytrends\n"
                    "Note: Google Trends API may have usage limitations."
                )

    def get_interest(self, keywords: List[str], timeframe: str = "now 1h") -> Dict[str, GoogleTrendsData]:
        """
        Get Google Trends interest for keywords.

        Args:
            keywords: List of search terms (e.g., ["bitcoin", "ethereum"])
            timeframe: Time window ("now 1h", "now 4h", "past 24h", "past 7d", "past 30d")

        Returns:
            Dict mapping keyword to GoogleTrendsData
        """
        self._ensure_connected()

        try:
            self._pytrends.build_payload(keywords, timeframe=timeframe)  # pyright: ignore[reportOptionalMemberAccess]
            interest = self._pytrends.interest_over_time()  # pyright: ignore[reportOptionalMemberAccess]

            results = {}
            for kw in keywords:
                if kw not in interest.columns:
                    results[kw] = GoogleTrendsData(keyword=kw, value=50.0, timestamp=datetime.now(), timeframe=timeframe)
                    continue
                # Get the latest non-zero value
                values = interest[kw].dropna()  # pyright: ignore[reportAttributeAccessIssue]
                if len(values) > 0:
                    latest_value = float(values.iloc[-1])  # type: ignore[index]
                    results[kw] = GoogleTrendsData(
                        keyword=kw,
                        value=latest_value,
                        timestamp=datetime.now(),
                        timeframe=timeframe,
                    )
                else:
                    results[kw] = GoogleTrendsData(
                        keyword=kw,
                        value=0.0,
                        timestamp=datetime.now(),
                        timeframe=timeframe,
                    )

            return results

        except Exception as e:
            # Return zeros on error (Google trends has strict rate limits)
            return {kw: GoogleTrendsData(keyword=kw, value=50.0, timestamp=datetime.now(), timeframe=timeframe) for kw in keywords}

    def get_market_breadth(self) -> float:
        """
        Get overall crypto market search breadth.

        Returns:
            Score 0-100 representing search interest
        """
        try:
            data = self.get_interest(["crypto", "bitcoin", "ethereum", "trading"], timeframe="now 1h")
            if data:
                return sum(d.value for d in data.values()) / len(data)
            return 50.0
        except Exception:
            return 50.0
