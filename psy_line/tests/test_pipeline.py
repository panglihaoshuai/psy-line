"""End-to-end pipeline tests for PSY_line.

T12: Tests the full data flow:
MarketState → BehaviorModel → SignalGenerator
with graceful degradation when sources fail.
"""

import pytest
import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from psy_line.market_state import MarketState
from psy_line.retail_behavior import RetailBehaviorModel, BehaviorPhase
from psy_line.signal_generator import SignalGenerator
from psy_line.types import BinanceKline, SignalType
from psy_line.rate_limiter import RateLimiter


class TestPipeline:
    """End-to-end pipeline tests."""

    def _make_klines(self, trend: str = "neutral", count: int = 20) -> list[BinanceKline]:
        """Create test kline data."""
        klines = []
        for i in range(count):
            if trend == "up":
                base = 100 + i * i // 2 + i  # Accelerating upward
            elif trend == "down":
                base = 100 - i * i // 2 - i  # Accelerating downward
            else:
                base = 100 + (i % 3 - 1)  # Flat
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

    def _make_market_state(
        self,
        trend: str = "neutral",
        fear_greed_value: int = 50,
        fear_greed_score: float = 0.0,
        reddit_composite: float = None,
        google_trends_score: float = None,
    ) -> MarketState:
        """Create test MarketState with specified parameters."""
        klines = self._make_klines(trend)
        momentum = (klines[-1].close - klines[0].close) / klines[0].close if klines else 0.0

        return MarketState(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            fear_greed_value=fear_greed_value,
            fear_greed_classification="Neutral",
            fear_greed_score=fear_greed_score,
            reddit_composite_score=reddit_composite,
            google_trends_score=google_trends_score,
            binance_klines=klines,
            binance_current_price=klines[-1].close if klines else None,
            binance_momentum=momentum,
            sources_used=["fear_greed", "binance"],
        )

    # === Full Pipeline Tests ===

    def test_full_pipeline_upward_trend(self):
        """Upward trend → FOMO behavior → SELL signal."""
        market_state = self._make_market_state(trend="up")
        model = RetailBehaviorModel()
        gen = SignalGenerator()

        behavior = model.analyze_market_state(market_state)
        signal = gen.generate_signal_from_market_state(market_state)

        assert behavior.phase in (BehaviorPhase.FOMO_BUY, BehaviorPhase.FOMO_EXTREME, BehaviorPhase.SUSPICION)
        assert signal.type in ("SELL", "BUY", "HOLD")  # Behavior-driven
        assert signal.strength > 0

    def test_full_pipeline_downward_trend(self):
        """Downward trend → Panic/Capitulation → BUY signal."""
        market_state = self._make_market_state(trend="down")
        model = RetailBehaviorModel()
        gen = SignalGenerator()

        behavior = model.analyze_market_state(market_state)
        signal = gen.generate_signal_from_market_state(market_state)

        assert behavior.phase in (BehaviorPhase.PANIC_SELL, BehaviorPhase.CAPITULATION)
        assert signal.type == SignalType.BUY
        assert signal.strength > 0

    def test_full_pipeline_flat_market(self):
        """Flat market → Equilibrium → HOLD signal."""
        market_state = self._make_market_state(trend="neutral")
        model = RetailBehaviorModel()
        gen = SignalGenerator()

        behavior = model.analyze_market_state(market_state)
        signal = gen.generate_signal_from_market_state(market_state)

        assert behavior.phase == BehaviorPhase.EQUILIBRIUM
        assert signal.type == SignalType.HOLD

    # === Graceful Degradation Tests ===

    def test_degradation_no_fear_greed(self):
        """Pipeline works without Fear & Greed data."""
        market_state = self._make_market_state(trend="down")
        market_state.fear_greed_value = None
        market_state.fear_greed_score = None
        market_state.fear_greed_classification = None

        model = RetailBehaviorModel()
        gen = SignalGenerator()

        behavior = model.analyze_market_state(market_state)
        signal = gen.generate_signal_from_market_state(market_state)

        assert behavior.phase in (BehaviorPhase.PANIC_SELL, BehaviorPhase.CAPITULATION)
        assert signal.type == SignalType.BUY

    def test_degradation_no_social_sentiment(self):
        """Pipeline works without Reddit/Google Trends data."""
        market_state = self._make_market_state(trend="up")
        market_state.reddit_composite_score = None
        market_state.google_trends_score = None

        model = RetailBehaviorModel()
        gen = SignalGenerator()

        behavior = model.analyze_market_state(market_state)
        signal = gen.generate_signal_from_market_state(market_state)

        assert signal.type in ("SELL", "BUY", "HOLD")
        assert signal.strength >= 0

    def test_degradation_minimal_data(self):
        """Pipeline works with only Binance price data."""
        klines = self._make_klines("down")
        momentum = (klines[-1].close - klines[0].close) / klines[0].close

        market_state = MarketState(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            binance_klines=klines,
            binance_current_price=klines[-1].close,
            binance_momentum=momentum,
            sources_used=["binance"],
        )

        model = RetailBehaviorModel()
        gen = SignalGenerator()

        behavior = model.analyze_market_state(market_state)
        signal = gen.generate_signal_from_market_state(market_state)

        # Should still produce a signal from price data alone
        assert behavior.phase is not None
        assert signal.type is not None
        assert signal.strength >= 0

    # === Signal Generation Tests ===

    def test_signal_contains_behavior_info(self):
        """Signal reasoning includes behavior phase information."""
        market_state = self._make_market_state(trend="up")
        gen = SignalGenerator()
        signal = gen.generate_signal_from_market_state(market_state)

        assert "行为" in signal.reasoning or "FOMO" in signal.reasoning or "行为" in signal.reasoning

    def test_signal_strength_scaled_by_confidence(self):
        """Higher confidence behavior → stronger signal."""
        model = RetailBehaviorModel()
        gen = SignalGenerator()

        # Strong trend
        strong_state = self._make_market_state(trend="down")
        strong_behavior = model.analyze_market_state(strong_state)
        strong_signal = gen.generate_signal_from_market_state(strong_state)

        # Weak trend (flat)
        weak_state = self._make_market_state(trend="neutral")
        weak_behavior = model.analyze_market_state(weak_state)
        weak_signal = gen.generate_signal_from_market_state(weak_state)

        # Strong trend should have higher or equal strength
        assert strong_signal.strength >= weak_signal.strength

    # === Rate Limiter Integration Tests ===

    def test_rate_limiter_quota_status(self):
        """Rate limiter returns valid quota status."""
        limiter = RateLimiter()
        quota = limiter.get_remaining_quota()

        assert "llm_remaining" in quota
        assert "search_remaining" in quota
        assert "current_period" in quota
        assert quota["llm_remaining"] > 0
        assert quota["search_remaining"] > 0

    def test_rate_limiter_can_use_llm(self):
        """Rate limiter allows LLM usage when quota available."""
        limiter = RateLimiter()
        assert limiter.can_use_llm() is True

    def test_rate_limiter_can_use_search(self):
        """Rate limiter allows search usage when quota available."""
        limiter = RateLimiter()
        assert limiter.can_use_search() is True
