"""Unit tests for RetailBehaviorModel.

T11: Comprehensive tests covering all 6 behavior phases,
indicator calculations, and edge cases.
"""

import pytest
import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from psy_line.retail_behavior import (
    RetailBehaviorModel,
    BehaviorPhase,
    BehaviorIndicators,
    BehaviorSignal,
)


class TestRetailBehaviorModel:
    """Tests for RetailBehaviorModel."""

    def _make_model(self) -> RetailBehaviorModel:
        return RetailBehaviorModel()

    def _make_indicators(
        self,
        fomo: float = 0.0,
        panic: float = 0.0,
        herding: float = 0.0,
        disposition: float = 0.0,
        momentum: float = 0.0,
        consecutive_up: int = 0,
        consecutive_down: int = 0,
        acceleration: float = 0.0,
        volatility: float = 0.0,
        volume_ratio: float = 1.0,
        price_spread: float = 0.0,
    ) -> BehaviorIndicators:
        return BehaviorIndicators(
            price_momentum=momentum,
            consecutive_up_days=consecutive_up,
            consecutive_down_days=consecutive_down,
            momentum_acceleration=acceleration,
            volatility=volatility,
            volume_ratio=volume_ratio,
            price_spread=price_spread,
            fomo_score=fomo,
            herding_score=herding,
            disposition_score=disposition,
            panic_score=panic,
            timestamp=datetime.now(),
        )

    # === Phase Detection Tests ===

    def test_equilibrium_phase(self):
        """All scores low → EQUILIBRIUM."""
        model = self._make_model()
        indicators = self._make_indicators()
        signal = model.detect_phase(indicators)
        assert signal.phase == BehaviorPhase.EQUILIBRIUM
        assert 0.0 <= signal.confidence <= 1.0

    def test_fomo_buy_phase(self):
        """High FOMO score + positive acceleration → FOMO_BUY."""
        model = self._make_model()
        indicators = self._make_indicators(
            fomo=0.75,  # Must be > 0.7 (threshold)
            momentum=0.3,
            acceleration=0.1,
            consecutive_up=5,  # Must be >= 5 to avoid SUSPICION (2-4 days)
        )
        signal = model.detect_phase(indicators)
        assert signal.phase == BehaviorPhase.FOMO_BUY
        assert signal.confidence >= 0.5

    def test_fomo_extreme_phase(self):
        """Very high FOMO + 5+ consecutive up days → FOMO_EXTREME."""
        model = self._make_model()
        indicators = self._make_indicators(
            fomo=0.9,
            momentum=0.5,
            acceleration=0.2,
            consecutive_up=6,
        )
        signal = model.detect_phase(indicators)
        assert signal.phase == BehaviorPhase.FOMO_EXTREME
        assert signal.confidence >= 0.8
        assert len(signal.warnings) > 0

    def test_panic_sell_phase(self):
        """High panic score → PANIC_SELL."""
        model = self._make_model()
        indicators = self._make_indicators(
            panic=0.7,
            momentum=-0.3,
            consecutive_down=4,
            volatility=0.06,
        )
        signal = model.detect_phase(indicators)
        assert signal.phase == BehaviorPhase.PANIC_SELL
        assert signal.confidence >= 0.5

    def test_capitulation_phase(self):
        """6+ consecutive down days + moderate panic → CAPITULATION.

        Note: panic must be <= 0.6 to avoid triggering PANIC_SELL first,
        but > 0.4 for capitulation threshold.
        """
        model = self._make_model()
        indicators = self._make_indicators(
            panic=0.5,  # > 0.4 but <= 0.6 (avoid PANIC_SELL)
            momentum=-0.5,
            consecutive_down=7,  # >= 6
            volatility=0.08,
        )
        signal = model.detect_phase(indicators)
        assert signal.phase == BehaviorPhase.CAPITULATION
        assert signal.confidence >= 0.7

    def test_suspicion_phase(self):
        """2-4 consecutive up days + low herding → SUSPICION."""
        model = self._make_model()
        indicators = self._make_indicators(
            momentum=0.1,
            consecutive_up=3,
            herding=0.2,
        )
        signal = model.detect_phase(indicators)
        assert signal.phase == BehaviorPhase.SUSPICION
        assert signal.confidence >= 0.5

    # === Indicator Calculation Tests ===

    def test_calculate_indicators_upward_trend(self):
        """Upward accelerating trend produces high FOMO."""
        model = self._make_model()
        # Accelerating upward prices
        prices = [100 + i * i for i in range(20)]
        volumes = [1.0] * 20
        indicators = model.calculate_indicators(prices, volumes)
        assert indicators.consecutive_up_days >= 3
        assert indicators.price_momentum > 0
        assert indicators.fomo_score > 0.3

    def test_calculate_indicators_downward_trend(self):
        """Downward accelerating trend produces high panic."""
        model = self._make_model()
        # Accelerating downward prices
        prices = [100 - i * i for i in range(20)]
        volumes = [1.0] * 20
        indicators = model.calculate_indicators(prices, volumes)
        assert indicators.consecutive_down_days >= 3
        assert indicators.price_momentum < 0
        assert indicators.panic_score > 0.3

    def test_calculate_indicators_flat_market(self):
        """Flat market produces low scores across all indicators."""
        model = self._make_model()
        prices = [100.0] * 20
        volumes = [1.0] * 20
        indicators = model.calculate_indicators(prices, volumes)
        assert indicators.fomo_score < 0.3
        assert indicators.panic_score < 0.3
        assert indicators.herding_score < 0.3

    def test_calculate_indicators_volume_spike(self):
        """Volume spike increases herding score."""
        model = self._make_model()
        prices = [100 + i * 2 for i in range(20)]
        volumes = [1.0] * 19 + [10.0]  # Massive spike at end
        indicators = model.calculate_indicators(prices, volumes)
        assert indicators.volume_ratio > 2.0
        assert indicators.herding_score > 0.3

    # === Edge Cases ===

    def test_empty_prices(self):
        """Empty prices list returns default indicators."""
        model = self._make_model()
        indicators = model.calculate_indicators([], [])
        assert indicators.price_momentum == 0.0
        assert indicators.fomo_score == 0.0
        assert indicators.panic_score == 0.0

    def test_single_price(self):
        """Single price returns default indicators."""
        model = self._make_model()
        indicators = model.calculate_indicators([100.0], [1.0])
        assert indicators.price_momentum == 0.0
        assert indicators.consecutive_up_days == 0
        assert indicators.consecutive_down_days == 0

    # === Sentiment Adjustment Tests ===

    def test_sentiment_adjustment_fomo_extreme(self):
        """FOMO_EXTREME gives strong negative adjustment."""
        signal = BehaviorSignal(
            phase=BehaviorPhase.FOMO_EXTREME,
            confidence=0.9,
            narrative="test",
            indicators=self._make_indicators(),
            warnings=[],
            timestamp=datetime.now(),
        )
        adjustment = signal.sentiment_adjustment()
        assert adjustment < -0.3  # Strong negative

    def test_sentiment_adjustment_capitulation(self):
        """CAPITULATION gives strong positive adjustment."""
        signal = BehaviorSignal(
            phase=BehaviorPhase.CAPITULATION,
            confidence=0.9,
            narrative="test",
            indicators=self._make_indicators(),
            warnings=[],
            timestamp=datetime.now(),
        )
        adjustment = signal.sentiment_adjustment()
        assert adjustment > 0.3  # Strong positive

    def test_sentiment_adjustment_equilibrium(self):
        """EQUILIBRIUM gives zero adjustment."""
        signal = BehaviorSignal(
            phase=BehaviorPhase.EQUILIBRIUM,
            confidence=0.5,
            narrative="test",
            indicators=self._make_indicators(),
            warnings=[],
            timestamp=datetime.now(),
        )
        adjustment = signal.sentiment_adjustment()
        assert adjustment == 0.0

    def test_sentiment_adjustment_scaled_by_confidence(self):
        """Adjustment is scaled by confidence."""
        high_conf = BehaviorSignal(
            phase=BehaviorPhase.FOMO_BUY,
            confidence=0.9,
            narrative="test",
            indicators=self._make_indicators(),
            warnings=[],
            timestamp=datetime.now(),
        )
        low_conf = BehaviorSignal(
            phase=BehaviorPhase.FOMO_BUY,
            confidence=0.3,
            narrative="test",
            indicators=self._make_indicators(),
            warnings=[],
            timestamp=datetime.now(),
        )
        assert abs(high_conf.sentiment_adjustment()) > abs(low_conf.sentiment_adjustment())

    # === Warning Tests ===

    def test_fomo_extreme_has_warnings(self):
        """FOMO_EXTREME phase includes warnings."""
        model = self._make_model()
        indicators = self._make_indicators(
            fomo=0.9,
            consecutive_up=6,
            momentum=0.5,
        )
        signal = model.detect_phase(indicators)
        assert len(signal.warnings) >= 2
        assert any("FOMO" in w for w in signal.warnings)

    def test_fomo_buy_has_warnings(self):
        """FOMO_BUY phase includes warnings."""
        model = self._make_model()
        indicators = self._make_indicators(
            fomo=0.75,  # > 0.7 threshold
            momentum=0.3,
            acceleration=0.1,
            consecutive_up=5,  # >= 5 to avoid SUSPICION
        )
        signal = model.detect_phase(indicators)
        assert len(signal.warnings) >= 1

    def test_equilibrium_no_warnings(self):
        """EQUILIBRIUM phase has no warnings."""
        model = self._make_model()
        indicators = self._make_indicators()
        signal = model.detect_phase(indicators)
        assert len(signal.warnings) == 0
