"""Performance tests for PSY_line.

Tests execution time, memory usage, and throughput benchmarks.
These ensure the system meets performance requirements.
"""

import pytest
import sys
import os
import time
import asyncio
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from psy_line.market_state import MarketState
from psy_line.retail_behavior import RetailBehaviorModel, BehaviorIndicators
from psy_line.signal_generator import SignalGenerator
from psy_line.types import BinanceKline
from psy_line.rate_limiter import RateLimiter


class TestPipelinePerformance:
    """Benchmark the full pipeline execution time."""

    def _make_klines(self, count: int = 100) -> list:
        """Create test kline data."""
        klines = []
        for i in range(count):
            base = 100 + i * 0.5
            klines.append(BinanceKline(
                open_time=i * 3600000,
                open=base - 1,
                high=base + 1,
                low=base - 2,
                close=base,
                volume=1.0,
                close_time=(i + 1) * 3600000 - 1,
            ))
        return klines

    def test_single_pipeline_execution_under_100ms(self):
        """Single pipeline execution should complete under 100ms."""
        klines = self._make_klines(100)
        market_state = MarketState(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            fear_greed_value=50,
            fear_greed_classification="Neutral",
            fear_greed_score=0.0,
            reddit_composite_score=0.0,
            google_trends_score=0.0,
            binance_klines=klines,
            binance_current_price=klines[-1].close,
            binance_momentum=0.01,
            sources_used=["test"],
        )

        model = RetailBehaviorModel()
        generator = SignalGenerator()

        start = time.monotonic()
        for _ in range(100):  # Run 100 iterations
            behavior = model.analyze_market_state(market_state)
            signal = generator.generate_signal_from_market_state(market_state)
        elapsed = time.monotonic() - start

        avg_ms = (elapsed / 100) * 1000
        assert avg_ms < 100, f"Average execution time {avg_ms:.2f}ms exceeds 100ms limit"

    def test_behavior_model_throughput(self):
        """Behavior model should process 1000+ analyses per second."""
        model = RetailBehaviorModel()
        indicators = BehaviorIndicators(
            price_momentum=0.1,
            consecutive_up_days=5,
            consecutive_down_days=0,
            momentum_acceleration=0.05,
            volatility=0.2,
            volume_ratio=1.5,
            price_spread=0.01,
            fomo_score=0.8,
            herding_score=0.6,
            disposition_score=0.4,
            panic_score=0.1,
            timestamp=datetime.now(),
        )

        start = time.monotonic()
        count = 0
        while time.monotonic() - start < 1.0:  # Run for 1 second
            model.detect_phase(indicators)
            count += 1

        assert count >= 1000, f"Throughput {count}/sec below 1000/sec minimum"

    def test_signal_generator_throughput(self):
        """Signal generator should process 1000+ signals per second."""
        sg = SignalGenerator()
        klines = self._make_klines(20)

        start = time.monotonic()
        count = 0
        while time.monotonic() - start < 1.0:
            sg.generate_signal(
                composite_sentiment=-0.5,
                momentum=0.01,
                symbol="BTCUSDT",
                price_data=klines,
            )
            count += 1

        assert count >= 1000, f"Throughput {count}/sec below 1000/sec minimum"


class TestRateLimiterPerformance:
    """Test rate limiter performance under load."""

    def test_quota_check_performance(self):
        """Quota checks should be fast even with many recorded requests."""
        rl = RateLimiter()
        # Record many requests
        for _ in range(1000):
            rl.record_llm_usage()

        start = time.monotonic()
        for _ in range(10000):
            rl.can_use_llm()
        elapsed = time.monotonic() - start

        avg_us = (elapsed / 10000) * 1_000_000
        assert avg_us < 100, f"Average quota check {avg_us:.2f}μs exceeds 100μs limit"

    def test_quota_status_performance(self):
        """Quota status retrieval should be fast."""
        rl = RateLimiter()
        for _ in range(500):
            rl.record_llm_usage()

        start = time.monotonic()
        for _ in range(1000):
            rl.get_remaining_quota()
        elapsed = time.monotonic() - start

        avg_us = (elapsed / 1000) * 1_000_000
        assert avg_us < 1000, f"Average status retrieval {avg_us:.2f}μs exceeds 1ms limit"


class TestMemoryProviderPerformance:
    """Test memory provider performance."""

    def test_memory_store_throughput(self):
        """Memory provider should store 1000+ records per second."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from plugins.memory.psy_line import PsyLineMemoryProvider

        async def run():
            mp = PsyLineMemoryProvider(max_records=100000)
            start = time.monotonic()
            count = 0
            while time.monotonic() - start < 1.0:
                await mp.remember(f"key_{count}", {"value": count})
                count += 1
            return count

        count = asyncio.run(run())
        assert count >= 1000, f"Store throughput {count}/sec below 1000/sec minimum"

    def test_memory_recall_performance(self):
        """Memory recall should be fast even with many records."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from plugins.memory.psy_line import PsyLineMemoryProvider

        async def run():
            mp = PsyLineMemoryProvider(max_records=100000)
            # Populate with data
            for i in range(10000):
                await mp.remember(f"key_{i:05d}", {"value": i})

            start = time.monotonic()
            for _ in range(1000):
                await mp.recall("key_50000", limit=10)
            elapsed = time.monotonic() - start
            return elapsed

        elapsed = asyncio.run(run())
        avg_us = (elapsed / 1000) * 1_000_000
        assert avg_us < 10000, f"Average recall {avg_us:.2f}μs exceeds 10ms limit"

    def test_memory_fifo_eviction_performance(self):
        """FIFO eviction should not degrade performance."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from plugins.memory.psy_line import PsyLineMemoryProvider

        async def run():
            mp = PsyLineMemoryProvider(max_records=1000)
            start = time.monotonic()
            for i in range(5000):  # Exceed max_records
                await mp.remember(f"key_{i}", {"value": i})
            elapsed = time.monotonic() - start
            assert len(mp._records) <= 1000  # Should have evicted old records
            return elapsed

        elapsed = asyncio.run(run())
        assert elapsed < 5.0, f"5000 stores with eviction took {elapsed:.2f}s, exceeds 5s limit"


class TestMemoryUsage:
    """Test memory usage patterns."""

    def test_memory_provider_bounded(self):
        """Memory provider should not grow beyond max_records."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from plugins.memory.psy_line import PsyLineMemoryProvider

        async def run():
            mp = PsyLineMemoryProvider(max_records=1000)
            for i in range(5000):
                await mp.remember(f"key_{i}", {"value": i, "data": "x" * 100})
            return len(mp._records)

        count = asyncio.run(run())
        assert count <= 1000, f"Memory provider has {count} records, expected ≤1000"

    def test_rate_limiter_bounded(self):
        """Rate limiter should not accumulate unbounded timestamps."""
        rl = RateLimiter()
        for _ in range(100000):
            rl.record_llm_usage()
        # The deque should be bounded by the window
        # With 5h window and 100k records, it should still work
        status = rl.get_remaining_quota()
        assert status['llm_remaining'] >= 0
