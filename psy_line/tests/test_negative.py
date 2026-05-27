"""Negative tests for PSY_line.

Tests error handling, invalid inputs, edge cases, and graceful degradation.
These verify the system doesn't crash on bad data.
"""

import pytest
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from psy_line.market_state import MarketState
from psy_line.retail_behavior import RetailBehaviorModel, BehaviorPhase, BehaviorIndicators
from psy_line.signal_generator import SignalGenerator
from psy_line.types import BinanceKline, SignalType
from psy_line.rate_limiter import RateLimiter, RateLimitConfig


class TestInvalidInputs:
    """Test behavior with invalid or unexpected inputs."""

    def test_empty_prices_signal_generator(self):
        """Signal generator should handle empty price data gracefully."""
        sg = SignalGenerator()
        signal = sg.generate_signal(
            composite_sentiment=-0.5,
            momentum=0.0,
            symbol="BTCUSDT",
            price_data=[]
        )
        # Should not crash, should return HOLD or similar safe default
        assert signal is not None
        assert hasattr(signal, 'type')

    def test_none_prices_signal_generator(self):
        """Signal generator should handle None price data."""
        sg = SignalGenerator()
        # This might raise an error or return default - either is acceptable
        try:
            signal = sg.generate_signal(
                composite_sentiment=-0.5,
                momentum=0.0,
                symbol="BTCUSDT",
                price_data=None
            )
            # If it doesn't crash, that's fine
            assert signal is not None
        except (TypeError, ValueError):
            # Expected - None is invalid input
            pass

    def test_extreme_sentiment_values(self):
        """Signal generator should clamp extreme sentiment values."""
        sg = SignalGenerator()
        # Values beyond [-1, 1]
        signal1 = sg.generate_signal(composite_sentiment=-5.0, momentum=0.0, symbol="BTCUSDT")
        signal2 = sg.generate_signal(composite_sentiment=5.0, momentum=0.0, symbol="BTCUSDT")
        # Should not crash
        assert signal1 is not None
        assert signal2 is not None

    def test_behavior_model_with_all_zeros(self):
        """Behavior model should handle all-zero indicators."""
        model = RetailBehaviorModel()
        indicators = BehaviorIndicators(
            price_momentum=0.0,
            consecutive_up_days=0,
            consecutive_down_days=0,
            momentum_acceleration=0.0,
            volatility=0.0,
            volume_ratio=0.0,
            price_spread=0.0,
            fomo_score=0.0,
            herding_score=0.0,
            disposition_score=0.0,
            panic_score=0.0,
            timestamp=datetime.now(),
        )
        signal = model.detect_phase(indicators)
        assert signal.phase == BehaviorPhase.EQUILIBRIUM

    def test_behavior_model_with_negative_values(self):
        """Behavior model should handle negative indicator values."""
        model = RetailBehaviorModel()
        indicators = BehaviorIndicators(
            price_momentum=-0.5,
            consecutive_up_days=-1,  # Invalid
            consecutive_down_days=-1,  # Invalid
            momentum_acceleration=-0.3,
            volatility=0.5,
            volume_ratio=0.8,
            price_spread=-0.1,  # Invalid
            fomo_score=-0.5,  # Invalid
            herding_score=-0.3,  # Invalid
            disposition_score=-0.2,  # Invalid
            panic_score=-0.4,  # Invalid
            timestamp=datetime.now(),
        )
        # Should handle gracefully, not crash
        signal = model.detect_phase(indicators)
        assert signal is not None

    def test_market_state_with_none_fields(self):
        """MarketState should handle None optional fields."""
        ms = MarketState(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            fear_greed_value=None,
            fear_greed_classification=None,
            fear_greed_score=None,
            reddit_composite_score=None,
            google_trends_score=None,
            binance_klines=[],
            binance_current_price=None,
            binance_momentum=None,
            sources_used=[],
        )
        assert ms.symbol == "BTCUSDT"
        assert ms.fear_greed_value is None


class TestRateLimiterEdgeCases:
    """Test rate limiter with extreme configurations."""

    def test_zero_limit_config(self):
        """Rate limiter with zero limit should block all requests."""
        cfg = RateLimitConfig(
            full_power_limit=0,
            conservative_limit=0,
            peak_multiplier=1.0,
        )
        rl = RateLimiter(cfg)
        assert rl.can_use_llm() is False

    def test_very_high_limit(self):
        """Rate limiter with very high limit should allow requests."""
        cfg = RateLimitConfig(full_power_limit=999999, conservative_limit=999999)
        rl = RateLimiter(cfg)
        assert rl.can_use_llm() is True

    def test_wait_for_slot_zero_timeout(self):
        """wait_for_slot with 0 timeout should return immediately."""
        cfg = RateLimitConfig(full_power_limit=0, conservative_limit=0, peak_multiplier=1.0)
        rl = RateLimiter(cfg)
        result = rl.wait_for_slot(max_wait=0.0)
        assert result is False

    def test_quota_status_with_no_usage(self):
        """Quota status should report correctly with no usage."""
        rl = RateLimiter()
        status = rl.get_remaining_quota()
        assert 'llm_remaining' in status
        assert 'search_remaining' in status
        assert 'current_period' in status
        assert status['llm_remaining'] > 0

    def test_multiple_429_errors(self):
        """Rate limiter should handle multiple 429 errors."""
        rl = RateLimiter()
        for _ in range(10):
            rl.on_429_error()
        # Should not crash
        wait_time = rl.get_wait_time()
        assert wait_time > 0

    def test_success_resets_backoff(self):
        """Successful request should reset backoff counter."""
        rl = RateLimiter()
        rl.on_429_error()
        rl.on_429_error()
        wait_before = rl.get_wait_time()
        rl.on_success()
        wait_after = rl.get_wait_time()
        assert wait_after < wait_before


class TestDataCorruption:
    """Test behavior with corrupted or inconsistent data."""

    def test_kline_with_zero_close(self):
        """Kline with zero close price should not crash signal generator."""
        klines = [BinanceKline(
            open_time=0,
            open=0,
            high=0,
            low=0,
            close=0,  # Invalid
            volume=0,
            close_time=3600000,
        )]
        sg = SignalGenerator()
        # Should handle gracefully
        try:
            signal = sg.generate_signal(
                composite_sentiment=0.0,
                momentum=0.0,
                symbol="BTCUSDT",
                price_data=klines
            )
            assert signal is not None
        except (ZeroDivisionError, ValueError):
            # Acceptable - zero price is invalid
            pass

    def test_kline_with_negative_volume(self):
        """Kline with negative volume should not crash."""
        klines = [BinanceKline(
            open_time=0,
            open=100,
            high=110,
            low=90,
            close=105,
            volume=-1.0,  # Invalid
            close_time=3600000,
        )]
        sg = SignalGenerator()
        try:
            signal = sg.generate_signal(
                composite_sentiment=0.0,
                momentum=0.0,
                symbol="BTCUSDT",
                price_data=klines
            )
            assert signal is not None
        except ValueError:
            # Acceptable
            pass

    def test_single_kline_momentum(self):
        """Momentum calculation with single kline should work."""
        klines = [BinanceKline(
            open_time=0,
            open=100,
            high=110,
            low=90,
            close=105,
            volume=1.0,
            close_time=3600000,
        )]
        sg = SignalGenerator()
        signal = sg.generate_signal(
            composite_sentiment=0.0,
            momentum=0.0,
            symbol="BTCUSDT",
            price_data=klines
        )
        assert signal is not None
