"""Continuous monitoring loop with time-aware scheduling and quota management.

T10: Provides automated monitoring with:
- Time-aware intervals (5min/15min/20min based on Beijing time period)
- Price anomaly detection for smart triggering
- Quota-aware degradation (skip LLM/search when quota is low)
"""

import logging
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

from .rate_limiter import RateLimiter
from .unified_source import UnifiedDataSource
from .signal_generator import SignalGenerator
from .market_state import MarketState
from .types import TradingSignal

logger = logging.getLogger(__name__)


@dataclass
class MonitorEvent:
    """A monitoring event (signal or anomaly detection)."""
    timestamp: datetime
    symbol: str
    market_state: MarketState
    signal: TradingSignal
    trigger_type: str  # "scheduled" or "anomaly"
    quota_status: Dict[str, int]


@dataclass
class MonitorConfig:
    """Configuration for continuous monitoring."""
    # Symbols to monitor
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])

    # Price anomaly thresholds
    price_change_threshold: float = 0.03  # 3% change triggers anomaly scan
    volume_spike_threshold: float = 2.0   # 2x average volume triggers anomaly

    # Quota thresholds for degradation
    llm_min_remaining: int = 100          # Skip LLM if below this
    search_min_remaining: int = 10        # Skip search if below this

    # Callback for events
    on_event: Optional[Callable[[MonitorEvent], None]] = None


class ContinuousMonitor:
    """T10: Continuous monitoring loop with time-aware scheduling.

    Usage:
        monitor = ContinuousMonitor(rate_limiter, signal_generator)
        monitor.start()  # Runs in background thread
        monitor.stop()   # Graceful shutdown
    """

    def __init__(
        self,
        rate_limiter: RateLimiter,
        signal_generator: SignalGenerator,
        config: Optional[MonitorConfig] = None,
    ):
        self._rate_limiter = rate_limiter
        self._signal_gen = signal_generator
        self._config = config or MonitorConfig()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_prices: dict[str, float] = {}
        self._last_volumes: dict[str, float] = {}
        self._events: List[MonitorEvent] = []
        # T10 Fix: Create UnifiedDataSource once and reuse
        self._data_source = UnifiedDataSource(rate_limiter=rate_limiter)

    def start(self) -> None:
        """Start monitoring in background thread."""
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Continuous monitor started")

    def stop(self) -> None:
        """Stop monitoring gracefully."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=30)
        logger.info("Continuous monitor stopped")

    def run_once(self, symbol: str = "BTCUSDT", trigger_type: str = "scheduled") -> Optional[MonitorEvent]:
        """Run a single monitoring scan.

        Args:
            symbol: Trading symbol to scan
            trigger_type: "scheduled" or "anomaly"

        Returns:
            MonitorEvent if scan completed, None if quota exhausted
        """
        # Check quota before scanning
        quota = self._rate_limiter.get_remaining_quota()
        if quota["llm_remaining"] < self._config.llm_min_remaining:
            logger.warning(f"LLM quota too low ({quota['llm_remaining']}), skipping scan")
            return None

        # Determine scan mode based on quota
        use_llm = quota["llm_remaining"] > self._config.llm_min_remaining
        use_search = quota["search_remaining"] > self._config.search_min_remaining

        # Fetch market state using reused data source
        market_state = self._data_source.fetch(
            symbol=symbol,
            include_llm=use_llm,
            include_search=use_search,
        )

        # Generate behavior-driven signal
        signal = self._signal_gen.generate_signal_from_market_state(market_state)

        # Check for price anomaly
        if self._detect_price_anomaly(symbol, market_state):
            trigger_type = "anomaly"
            logger.info(f"Price anomaly detected for {symbol}")

        # Create event
        event = MonitorEvent(
            timestamp=datetime.now(),
            symbol=symbol,
            market_state=market_state,
            signal=signal,
            trigger_type=trigger_type,
            quota_status=quota,
        )

        self._events.append(event)

        # Notify callback
        if self._config.on_event:
            try:
                self._config.on_event(event)
            except Exception as e:
                logger.error(f"Event callback error: {e}")

        return event

    def _monitor_loop(self) -> None:
        """Main monitoring loop with time-aware intervals."""
        while self._running:
            try:
                interval = self._get_scan_interval()

                # Scan all symbols
                for symbol in self._config.symbols:
                    if not self._running:
                        break
                    self.run_once(symbol, trigger_type="scheduled")

                # Wait for next interval
                logger.debug(f"Monitor sleeping for {interval}s")
                for _ in range(int(interval)):
                    if not self._running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                time.sleep(60)  # Wait 1 minute on error

    def _get_scan_interval(self) -> float:
        """Get scan interval based on current time period (Beijing time).

        Returns:
            Interval in seconds:
            - 300 (5min) during full power hours
            - 900 (15min) during conservative hours
            - 1200 (20min) during peak hours
        """
        period = self._rate_limiter._get_current_period()

        intervals = {
            "full_power": 300,    # 5 minutes
            "conservative": 900,  # 15 minutes
            "peak": 1200,         # 20 minutes
        }

        return intervals.get(period, 900)

    def _detect_price_anomaly(self, symbol: str, market_state: MarketState) -> bool:
        """Detect price anomaly for smart triggering.

        Args:
            symbol: Trading symbol
            market_state: Current market state

        Returns:
            True if price anomaly detected
        """
        current_price = market_state.binance_current_price
        if current_price is None:
            return False

        # Check price change from last scan
        if symbol in self._last_prices:
            last_price = self._last_prices[symbol]
            if last_price > 0:
                price_change = abs(current_price - last_price) / last_price
                if price_change >= self._config.price_change_threshold:
                    return True

        # Check volume spike
        if market_state.binance_klines:
            current_volume = market_state.binance_klines[-1].volume
            if symbol in self._last_volumes:
                last_volume = self._last_volumes[symbol]
                if last_volume > 0 and current_volume / last_volume >= self._config.volume_spike_threshold:
                    return True

        # Update last known values
        self._last_prices[symbol] = current_price
        if market_state.binance_klines:
            self._last_volumes[symbol] = market_state.binance_klines[-1].volume

        return False

    def get_events(self, limit: int = 100) -> List[MonitorEvent]:
        """Get recent monitoring events."""
        return self._events[-limit:]

    def get_last_signal(self, symbol: str) -> Optional[TradingSignal]:
        """Get the last signal for a symbol."""
        for event in reversed(self._events):
            if event.symbol == symbol:
                return event.signal
        return None
