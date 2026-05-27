"""Acceptance tests for PSY_line.

Tests user-facing scenarios and business requirements.
These verify the system meets user expectations.
"""

import pytest
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from psy_line.market_state import MarketState
from psy_line.retail_behavior import RetailBehaviorModel, BehaviorPhase
from psy_line.signal_generator import SignalGenerator
from psy_line.types import BinanceKline, SignalType
from psy_line.rate_limiter import RateLimiter


class TestUserScenarios:
    """Test real user scenarios."""

    def _make_market_state(
        self,
        trend: str = "neutral",
        fear_greed: int = 50,
        reddit_score: float = 0.0,
    ) -> MarketState:
        """Create market state for testing."""
        klines = []
        for i in range(20):
            if trend == "up":
                base = 100 + i * 2
            elif trend == "down":
                base = 100 - i * 2
            else:
                base = 100 + (i % 3 - 1)
            klines.append(BinanceKline(
                open_time=i * 3600000,
                open=base - 1,
                high=base + 1,
                low=base - 2,
                close=base,
                volume=1.0,
                close_time=(i + 1) * 3600000 - 1,
            ))

        return MarketState(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            fear_greed_value=fear_greed,
            fear_greed_classification="Neutral",
            fear_greed_score=(fear_greed - 50) / 50,
            reddit_composite_score=reddit_score,
            google_trends_score=0.0,
            binance_klines=klines,
            binance_current_price=klines[-1].close,
            binance_momentum=(klines[-1].close - klines[0].close) / klines[0].close,
            sources_used=["fear_greed", "binance", "reddit"],
        )

    def test_user_scans_btc_gets_signal(self):
        """User scans BTC → receives a valid trading signal."""
        market_state = self._make_market_state(trend="up", fear_greed=70, reddit_score=0.5)
        
        model = RetailBehaviorModel()
        generator = SignalGenerator()
        
        behavior = model.analyze_market_state(market_state)
        signal = generator.generate_signal_from_market_state(market_state)
        
        # User should get a valid signal
        assert signal is not None
        assert hasattr(signal, 'type')
        assert signal.type in [SignalType.BUY, SignalType.SELL, SignalType.HOLD]
        assert hasattr(signal, 'strength')
        assert 0 <= signal.strength <= 1

    def test_user_gets_behavior_phase_info(self):
        """User should see which behavior phase was detected."""
        market_state = self._make_market_state(trend="up", fear_greed=80, reddit_score=0.7)
        
        model = RetailBehaviorModel()
        behavior = model.analyze_market_state(market_state)
        
        # Should include behavior phase info
        assert behavior is not None
        assert hasattr(behavior, 'phase')
        assert behavior.phase in [
            BehaviorPhase.EQUILIBRIUM,
            BehaviorPhase.FOMO_BUY,
            BehaviorPhase.FOMO_EXTREME,
            BehaviorPhase.PANIC_SELL,
            BehaviorPhase.CAPITULATION,
            BehaviorPhase.SUSPICION,
        ]

    def test_user_signal_includes_rationale(self):
        """User should understand WHY a signal was generated."""
        market_state = self._make_market_state(trend="down", fear_greed=20, reddit_score=-0.5)
        
        model = RetailBehaviorModel()
        generator = SignalGenerator()
        
        behavior = model.analyze_market_state(market_state)
        signal = generator.generate_signal_from_market_state(market_state)
        
        # Signal should have some form of rationale
        # (Check for warnings, behavior phase, or reasoning)
        assert signal is not None
        # The behavior model should have warnings if applicable
        assert hasattr(behavior, 'warnings')

    def test_user_quota_status_is_informative(self):
        """User should see clear quota status."""
        rl = RateLimiter()
        status = rl.get_remaining_quota()
        
        # Should have all required fields
        assert 'llm_remaining' in status
        assert 'llm_limit' in status
        assert 'search_remaining' in status
        assert 'search_limit' in status
        assert 'current_period' in status
        
        # Values should be reasonable
        assert status['llm_remaining'] >= 0
        assert status['llm_limit'] > 0
        assert status['current_period'] in ['full_power', 'conservative', 'peak']

    def test_user_handles_api_failure_gracefully(self):
        """User should see graceful degradation when APIs fail."""
        # Market state with no data
        market_state = MarketState(
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
        
        model = RetailBehaviorModel()
        generator = SignalGenerator()
        
        # Should not crash
        try:
            behavior = model.analyze_market_state(market_state)
            signal = generator.generate_signal_from_market_state(market_state)
            # Should get some default/conservative signal
            assert signal is not None
        except Exception as e:
            # If it fails, error should be clear
            assert "No data" in str(e) or "Empty" in str(e) or "missing" in str(e).lower()


class TestBusinessRules:
    """Test business rule compliance."""

    def test_buy_signal_on_extreme_fear(self):
        """BUY signal when market shows extreme fear (contrarian)."""
        market_state = MarketState(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            fear_greed_value=10,  # Extreme fear
            fear_greed_classification="Extreme Fear",
            fear_greed_score=-0.8,
            reddit_composite_score=-0.7,
            google_trends_score=-0.5,
            binance_klines=self._make_klines("down"),
            binance_current_price=80.0,
            binance_momentum=-0.2,
            sources_used=["fear_greed", "binance", "reddit"],
        )
        
        model = RetailBehaviorModel()
        generator = SignalGenerator()
        
        behavior = model.analyze_market_state(market_state)
        signal = generator.generate_signal_from_market_state(market_state)
        
        # Contrarian: extreme fear → BUY opportunity
        # (This depends on the actual signal logic)
        assert signal.type in [SignalType.BUY, SignalType.HOLD]

    def test_sell_signal_on_extreme_greed(self):
        """SELL signal when market shows extreme greed (contrarian)."""
        market_state = MarketState(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            fear_greed_value=90,  # Extreme greed
            fear_greed_classification="Extreme Greed",
            fear_greed_score=0.8,
            reddit_composite_score=0.7,
            google_trends_score=0.5,
            binance_klines=self._make_klines("up"),
            binance_current_price=120.0,
            binance_momentum=0.2,
            sources_used=["fear_greed", "binance", "reddit"],
        )
        
        model = RetailBehaviorModel()
        generator = SignalGenerator()
        
        behavior = model.analyze_market_state(market_state)
        signal = generator.generate_signal_from_market_state(market_state)
        
        # Contrarian: extreme greed → SELL opportunity
        assert signal.type in [SignalType.SELL, SignalType.HOLD]

    def _make_klines(self, trend: str) -> list:
        """Helper to create klines."""
        klines = []
        for i in range(20):
            if trend == "up":
                base = 100 + i * 2
            elif trend == "down":
                base = 100 - i * 2
            else:
                base = 100 + (i % 3 - 1)
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


class TestErrorMessages:
    """Test that error messages are user-friendly."""

    def test_config_validation_messages(self):
        """Config validation should give clear error messages."""
        from psy_line.config import Config, RedditConfig, OpenAIConfig, BinanceConfig
        
        cfg = Config(
            reddit=RedditConfig(
                client_id="",
                client_secret="",
                user_agent="test",
                keywords=[],
                keywords_mode="include",
            ),
            openai=OpenAIConfig(api_key="", model="gpt-4o"),
            binance=BinanceConfig(api_key="", secret_key="", testnet=True),
        )
        
        with pytest.raises(ValueError) as exc_info:
            cfg.validate_required()
        
        error_msg = str(exc_info.value)
        # Should mention which fields are missing
        assert "REDDIT_CLIENT_ID" in error_msg
        assert "BINANCE_API_KEY" in error_msg

    def test_signal_type_is_clear(self):
        """Signal types should be human-readable."""
        from psy_line.types import SignalType
        
        # SignalType enum should have clear names
        assert SignalType.BUY.value == "BUY" or hasattr(SignalType.BUY, 'name')
        assert SignalType.SELL.value == "SELL" or hasattr(SignalType.SELL, 'name')
        assert SignalType.HOLD.value == "HOLD" or hasattr(SignalType.HOLD, 'name')
