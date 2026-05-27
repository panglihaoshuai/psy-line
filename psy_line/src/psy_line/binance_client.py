"""Binance API client."""

import time
from typing import TYPE_CHECKING, List, Optional
from datetime import datetime

from .types import BinanceKline

if TYPE_CHECKING:
    from binance.client import Client  # pyright: ignore[reportMissingImports]


class BinanceClient:
    """Client for Binance API."""

    BASE_URL = "https://api.binance.com"
    TESTNET_URL = "https://testnet.binance.vision"

    def __init__(self, api_key: str, secret_key: str, testnet: bool = True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.testnet = testnet
        self.base_url = self.TESTNET_URL if testnet else self.BASE_URL
        self._client: Optional["Client"] = None
        self._price_cache: dict[str, float] = {}
        self._price_cache_time: float = 0
        self._price_cache_ttl: float = 5.0  # 5 seconds TTL

    @property
    def client(self) -> "Client":
        """Lazy Binance client."""
        if self._client is None:
            from binance.client import Client  # pyright: ignore[reportMissingImports]
            self._client = Client(self.api_key, self.secret_key)
            # Override API URL for testnet
            if self.testnet and self._client is not None:
                self._client.API_URL = self.TESTNET_URL + "/api/v3/order"  # type: ignore[attr-defined]
                self._client.FUTURES_URL = self.TESTNET_URL + "/fapi/v1/order"  # type: ignore[attr-defined]
        return self._client

    def get_klines(self, symbol: str, interval: str, limit: int = 100) -> List[BinanceKline]:
        """
        Fetch candlestick/kline data.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            interval: Kline interval (1m, 5m, 1h, 1d)
            limit: Number of klines to fetch

        Returns:
            List of BinanceKline objects
        """
        try:
            klines = self.client.get_klines(symbol=symbol, interval=interval, limit=limit)

            result = []
            for k in klines:
                result.append(
                    BinanceKline(
                        open_time=int(k[0]),
                        open=float(k[1]),
                        high=float(k[2]),
                        low=float(k[3]),
                        close=float(k[4]),
                        volume=float(k[5]),
                        close_time=int(k[6]),
                    )
                )
            return result

        except Exception as e:
            print(f"Binance klines error: {e}", file=__import__("sys").stderr)
            return []

    def get_current_price(self, symbol: str) -> float:
        """
        Get current price with caching.

        Args:
            symbol: Trading symbol

        Returns:
            Current price
        """
        now = time.time()

        # Check cache
        if symbol in self._price_cache and (now - self._price_cache_time) < self._price_cache_ttl:
            return self._price_cache[symbol]

        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            price = float(ticker["price"])
            self._price_cache[symbol] = price
            self._price_cache_time = now
            return price
        except Exception as e:
            print(f"Binance price error: {e}", file=__import__("sys").stderr)
            # Return cached value even if stale
            return self._price_cache.get(symbol, 0.0)

    def get_24hr_stats(self, symbol: str) -> dict[str, object]:
        """
        Get 24-hour price change statistics.

        Returns:
            Dict with price change stats
        """
        try:
            stats = self.client.get_ticker(symbol=symbol)
            return {
                "symbol": stats["symbol"],
                "price_change": float(stats["priceChange"]),
                "price_change_percent": float(stats["priceChangePercent"]),
                "weighted_avg_price": float(stats["weightedAvgPrice"]),
                "prev_close_price": float(stats["prevClosePrice"]),
                "last_price": float(stats["lastPrice"]),
                "volume": float(stats["volume"]),
                "quote_volume": float(stats["quoteVolume"]),
            }
        except Exception as e:
            print(f"Binance 24hr stats error: {e}", file=__import__("sys").stderr)
            return {}
