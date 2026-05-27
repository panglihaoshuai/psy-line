"""Time-aware rate limiter for MiniMax API quota management.

Manages MiniMax API quotas with automatic time-of-day strategy switching
based on Beijing time (UTC+8).

Time periods (Beijing time):
- Full power (20:00-09:00 + weekends): 1300 requests/5h
- Conservative (09:00-20:00 weekdays): 900 requests/5h
- Peak (15:00-17:30 weekdays): extra conservative
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Deque

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    full_power_limit: int = 1300
    conservative_limit: int = 900
    search_limit: int = 150
    llm_window_seconds: int = 18000  # 5 hours
    search_window_seconds: int = 3600  # 1 hour
    min_request_interval_seconds: float = 12.0
    peak_hours_start: int = 15
    peak_hours_end: int = 17
    full_power_start: int = 20
    full_power_end: int = 9
    peak_multiplier: float = 0.7  # Reduce limit during peak hours


class RateLimiter:
    """Time-aware rate limiter for MiniMax API."""

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._lock = threading.Lock()
        self._llm_timestamps: deque[float] = deque()
        self._search_timestamps: deque[float] = deque()
        self._consecutive_429s: int = 0
        self._last_request_time: float = 0.0

    def _get_beijing_time(self) -> datetime:
        """Returns current time in UTC+8."""
        return datetime.now(BEIJING_TZ)

    def _is_weekend(self, dt: datetime) -> bool:
        """Check if date is weekend (Saturday=5, Sunday=6)."""
        return dt.weekday() >= 5

    def _get_current_period(self) -> str:
        """Returns 'full_power', 'conservative', or 'peak' based on Beijing time."""
        now = self._get_beijing_time()

        # Weekend/holiday → full_power
        if self._is_weekend(now):
            return "full_power"

        hour = now.hour

        # Peak hours: 15:00-17:30 weekdays
        if self.config.peak_hours_start <= hour < self.config.peak_hours_end:
            if hour == self.config.peak_hours_end - 1 and now.minute > 30:
                pass  # After 17:30, fall through
            else:
                return "peak"

        # Full power: 20:00-09:00
        if hour >= self.config.full_power_start or hour < self.config.full_power_end:
            return "full_power"

        # Conservative: 09:00-20:00 (excluding peak)
        return "conservative"

    def _get_llm_limit(self) -> int:
        """Returns LLM limit based on current period."""
        period = self._get_current_period()
        if period == "full_power":
            return self.config.full_power_limit
        elif period == "peak":
            return int(self.config.conservative_limit * self.config.peak_multiplier)
        else:
            return self.config.conservative_limit

    def _clean_window(self, timestamps: Deque[float], window_seconds: int) -> None:
        """Remove timestamps older than the window."""
        cutoff = datetime.now().timestamp() - window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

    def can_use_llm(self) -> bool:
        """Check if LLM quota is available using sliding window."""
        with self._lock:
            self._clean_window(self._llm_timestamps, self.config.llm_window_seconds)
            limit = self._get_llm_limit()
            return len(self._llm_timestamps) < limit

    def wait_for_slot(self, max_wait: float = 300.0) -> bool:
        """Block until LLM quota available or timeout.

        Args:
            max_wait: Maximum seconds to wait before giving up.

        Returns:
            True if slot acquired, False if timed out.
        """
        if self.can_use_llm():
            return True

        deadline = time.monotonic() + max_wait
        check_interval = 10.0
        logger.warning(f"LLM quota exhausted, waiting up to {max_wait:.0f}s for slot...")

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            wait = min(check_interval, remaining)
            if wait <= 0:
                break
            time.sleep(wait)
            if self.can_use_llm():
                logger.info("LLM slot acquired after wait")
                return True
            logger.warning(f"Still waiting for LLM slot ({remaining:.0f}s remaining)")

        logger.error(f"wait_for_slot timed out after {max_wait:.0f}s")
        return False

    def can_use_search(self) -> bool:
        """Check if search quota is available using sliding window."""
        with self._lock:
            self._clean_window(self._search_timestamps, self.config.search_window_seconds)
            return len(self._search_timestamps) < self.config.search_limit

    def record_llm_usage(self) -> None:
        """Record LLM usage timestamp."""
        with self._lock:
            self._llm_timestamps.append(datetime.now().timestamp())
            self._last_request_time = datetime.now().timestamp()
            remaining = self._get_llm_limit() - len(self._llm_timestamps)
            if remaining < self._get_llm_limit() * 0.2:
                logger.warning(f"LLM quota low: {remaining} remaining")

    def record_search_usage(self) -> None:
        """Record search usage timestamp."""
        with self._lock:
            self._search_timestamps.append(datetime.now().timestamp())
            remaining = self.config.search_limit - len(self._search_timestamps)
            if remaining < self.config.search_limit * 0.2:
                logger.warning(f"Search quota low: {remaining} remaining")

    def get_remaining_quota(self) -> Dict[str, Any]:
        """Returns remaining quota info."""
        with self._lock:
            self._clean_window(self._llm_timestamps, self.config.llm_window_seconds)
            self._clean_window(self._search_timestamps, self.config.search_window_seconds)
            llm_limit = self._get_llm_limit()
            return {
                "llm_remaining": max(0, llm_limit - len(self._llm_timestamps)),
                "llm_limit": llm_limit,
                "search_remaining": max(0, self.config.search_limit - len(self._search_timestamps)),
                "search_limit": self.config.search_limit,
                "current_period": self._get_current_period(),
                "next_reset": datetime.now(BEIJING_TZ) + timedelta(seconds=self.config.llm_window_seconds),
            }

    def get_wait_time(self) -> float:
        """Returns seconds to wait before next request (0 if can use immediately)."""
        if self._consecutive_429s > 0:
            return min(self.config.min_request_interval_seconds * (2 ** self._consecutive_429s), 300)
        if not self.can_use_llm():
            return 60.0  # Wait 1 minute if quota exhausted
        return 0.0

    def on_429_error(self) -> None:
        """Handle 429 rate limit error with exponential backoff."""
        with self._lock:
            self._consecutive_429s += 1
            wait = self.get_wait_time()
            logger.warning(f"429 error #{self._consecutive_429s}, backing off {wait:.0f}s")
            if self._consecutive_429s >= 5:
                logger.error("Max 429 retries reached, disabling LLM until window reset")

    def on_success(self) -> None:
        """Reset backoff counter on successful request."""
        with self._lock:
            self._consecutive_429s = 0
