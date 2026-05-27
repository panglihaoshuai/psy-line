"""Trading signal generator.

T8 Refactor: Behavior phase is now the PRIMARY driver of trading signals.
Previous architecture used weighted average (sentiment + PSY + momentum + behavior).
New architecture: behavior phase → signal type, PSY/momentum → strength adjustment.

Signal Mapping (behavior-driven):
- FOMO_EXTREME → SELL (极度贪婪，反向做空)
- FOMO_BUY     → SELL (FOMO追入，反向做空)
- PANIC_SELL   → BUY  (恐慌抛售，反向做多)
- CAPITULATION → BUY  (割肉离场，底部信号)
- SUSPICION    → BUY  (怀疑阶段，可能吸筹)
- EQUILIBRIUM  → HOLD (均衡状态，观望)

PSY/momentum act as secondary confirmers that adjust signal strength, not type.

Original Signal Logic (preserved for backward compatibility):
- Combined Score > +0.6  →  SELL (过度贪婪)
- Combined Score < -0.6  →  BUY  (过度恐惧)
- Otherwise               →  HOLD

PSY Indicator (Technical):
- PSY > 75: Extreme Greed (overbought)
- PSY > 50: Bullish
- PSY < 50: Bearish
- PSY < 25: Extreme Fear (oversold)

References:
- PSY Formula: PSY = (rising periods / total periods) × 100
- https://www.investchannels.com/psychological-line-indicator-trading-strategies-and-tips/
"""

import math
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from .types import TradingSignal, SignalType, SentimentResult, BinanceKline
from .retail_behavior import RetailBehaviorModel, BehaviorSignal, BehaviorPhase

if TYPE_CHECKING:
    from .market_state import MarketState


class SignalGenerator:
    """Generate trading signals based on sentiment, PSY indicator, and momentum."""

    def __init__(
        self,
        buy_threshold: float = -0.6,
        sell_threshold: float = 0.6,
        psy_weight: float = 0.3,
        sentiment_weight: float = 0.4,
        momentum_weight: float = 0.3,
    ):
        """
        Initialize signal generator.

        Args:
            buy_threshold: Sentiment below this triggers BUY (default: -0.6)
            sell_threshold: Sentiment above this triggers SELL (default: 0.6)
            psy_weight: Weight for PSY indicator (default: 0.3)
            sentiment_weight: Weight for social sentiment (default: 0.4)
            momentum_weight: Weight for price momentum (default: 0.3)
        """
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.psy_weight = psy_weight
        self.sentiment_weight = sentiment_weight
        self.momentum_weight = momentum_weight
        self._retail_model = RetailBehaviorModel()

    def calculate_composite_sentiment(self, sentiment_results: List[SentimentResult]) -> float:
        """
        Calculate weighted composite sentiment.

        Uses time-decay weighting where recent comments have higher weight.

        Args:
            sentiment_results: List of SentimentResult objects

        Returns:
            Composite sentiment score between -1 and 1
        """
        if not sentiment_results:
            return 0.0

        now = datetime.now().timestamp()
        lambda_decay = 0.1  # Decay rate

        weighted_sum = 0.0
        weight_sum = 0.0

        for result in sentiment_results:
            # Estimate age (older items assumed to have older timestamps)
            # In practice, we'd use actual timestamps from Reddit
            age_hours = 1.0  # Default to 1 hour

            weight = math.exp(-lambda_decay * age_hours)
            weighted_sum += result.score * weight
            weight_sum += weight

        if weight_sum == 0:
            return 0.0

        composite = weighted_sum / weight_sum
        # Clamp to [-1, 1]
        return max(-1.0, min(1.0, composite))

    def calculate_momentum(self, price_data: List[BinanceKline]) -> float:
        """
        Calculate price momentum over the period.

        Args:
            price_data: List of BinanceKline objects (oldest first)

        Returns:
            Momentum as a decimal (e.g., 0.05 = 5% change)
        """
        if len(price_data) < 2:
            return 0.0

        oldest_price = price_data[0].close
        newest_price = price_data[-1].close

        if oldest_price == 0:
            return 0.0

        momentum = (newest_price - oldest_price) / oldest_price
        return momentum

    def calculate_psy(self, price_data: List[BinanceKline], period: int = 12) -> float:
        """
        Calculate PSY (Psychological Line) indicator.

        Formula: PSY = (rising periods / total periods) × 100

        Args:
            price_data: List of BinanceKline objects (oldest first)
            period: Number of periods to calculate over (default: 12)

        Returns:
            PSY value (0-100)
        """
        if len(price_data) < 2:
            return 50.0

        # Count periods where price increased
        bullish_count = 0
        for i in range(1, min(len(price_data), period + 1)):
            if price_data[i].close > price_data[i - 1].close:
                bullish_count += 1

        psy_value = (bullish_count / period) * 100
        return psy_value

    def calculate_psy_sentiment(self, price_data: List[BinanceKline], period: int = 12) -> float:
        """
        Calculate PSY and convert to -1 to 1 sentiment scale.

        Args:
            price_data: List of BinanceKline objects
            period: Number of periods

        Returns:
            PSY sentiment score (-1 to 1)
        """
        psy = self.calculate_psy(price_data, period)
        return (psy - 50) / 50  # 0 -> -1, 50 -> 0, 100 -> 1

    def get_consecutive_streak(self, price_data: List[BinanceKline]) -> tuple[int, int]:
        """
        Count consecutive up/down days.

        Returns:
            (consecutive_up, consecutive_down)
        """
        if len(price_data) < 2:
            return (0, 0)

        consecutive_up = 0
        consecutive_down = 0

        # Count consecutive up from end
        i = len(price_data) - 1
        while i > 0:
            if price_data[i].close > price_data[i - 1].close:
                consecutive_up += 1
            else:
                break
            i -= 1

        # Count consecutive down from end
        i = len(price_data) - 1
        while i > 0:
            if price_data[i].close < price_data[i - 1].close:
                consecutive_down += 1
            else:
                break
            i -= 1

        return (consecutive_up, consecutive_down)

    def get_retail_behavior_signal(
        self,
        price_data: List[BinanceKline],
        volume_data: Optional[List[float]] = None,
    ) -> BehaviorSignal:
        """
        Get retail behavior signal from price (and optional volume) data.

        Args:
            price_data: List of BinanceKline objects (oldest first)
            volume_data: Optional list of volume values

        Returns:
            BehaviorSignal object
        """
        prices = [k.close for k in price_data]
        volumes = [k.volume for k in price_data] if volume_data is None else volume_data

        indicators = self._retail_model.calculate_indicators(prices, volumes)
        signal = self._retail_model.detect_phase(indicators)
        return signal

    def generate_signal(
        self,
        composite_sentiment: float,
        momentum: float,
        symbol: str,
        price_data: Optional[List[BinanceKline]] = None,
        behavior_signal: Optional[BehaviorSignal] = None,
    ) -> TradingSignal:
        """
        T8 Refactor: Generate trading signal driven by behavior phase.

        Behavior phase → signal type (primary driver).
        PSY/momentum → strength adjustment (secondary confirmation).

        Args:
            composite_sentiment: Social sentiment score (-1 to 1)
            momentum: Price momentum (e.g., 0.05 = 5% change)
            symbol: Trading symbol
            price_data: Optional kline data for PSY and behavior calculation
            behavior_signal: Optional pre-computed behavior signal

        Returns:
            TradingSignal object
        """
        # Calculate PSY sentiment if price data provided
        psy_sentiment = 0.0
        psy_value = 50.0
        consecutive_up = 0
        consecutive_down = 0

        if price_data:
            psy_sentiment = self.calculate_psy_sentiment(price_data)
            psy_value = self.calculate_psy(price_data)
            consecutive_up, consecutive_down = self.get_consecutive_streak(price_data)

            # Auto-calculate behavior signal if not provided
            if behavior_signal is None:
                behavior_signal = self.get_retail_behavior_signal(price_data)

        # T8: Behavior phase → signal type (PRIMARY driver)
        if behavior_signal is not None:
            signal_type, base_strength = self._behavior_to_signal(behavior_signal)
        else:
            # Fallback to old weighted average if no behavior signal
            signal_type, base_strength = self._weighted_average_signal(
                composite_sentiment, momentum, psy_sentiment
            )

        # T8: PSY/momentum as secondary confirmers → adjust strength
        strength_adjustment = self._calculate_confirmation_adjustment(
            psy_sentiment, momentum, behavior_signal
        )
        strength = min(1.0, max(0.0, base_strength + strength_adjustment))

        # Build reasoning
        reasoning_parts = []

        # Behavior phase (primary)
        if behavior_signal is not None:
            phase_labels = {
                BehaviorPhase.SUSPICION: "怀疑(吸筹?)",
                BehaviorPhase.FOMO_BUY: "FOMO买入",
                BehaviorPhase.PANIC_SELL: "恐慌抛售",
                BehaviorPhase.CAPITULATION: "割肉离场",
                BehaviorPhase.FOMO_EXTREME: "极度FOMO",
                BehaviorPhase.EQUILIBRIUM: "均衡",
            }
            behavior_label = phase_labels.get(behavior_signal.phase, behavior_signal.phase.value)
            reasoning_parts.append(f"行为:{behavior_label}({behavior_signal.confidence:.0%})")
            if behavior_signal.warnings:
                reasoning_parts.extend(behavior_signal.warnings[:1])

        # PSY info
        if price_data:
            psy_class = "中性"
            if psy_value >= 75:
                psy_class = "极度贪婪"
            elif psy_value >= 65:
                psy_class = "贪婪"
            elif psy_value >= 50:
                psy_class = "偏多"
            elif psy_value >= 35:
                psy_class = "偏空"
            elif psy_value >= 25:
                psy_class = "恐惧"
            else:
                psy_class = "极度恐惧"
            reasoning_parts.append(f"PSY:{psy_class}({psy_value:.0f})")

            # Streak info
            if consecutive_up > 2:
                reasoning_parts.append(f"连涨:{consecutive_up}天")
            elif consecutive_down > 2:
                reasoning_parts.append(f"连跌:{consecutive_down}天")

        # Momentum info
        reasoning_parts.append(f"动量:{'+' if momentum > 0 else ''}{momentum*100:.1f}%")

        return TradingSignal(
            type=signal_type,
            strength=strength,
            composite_sentiment=composite_sentiment,
            momentum=momentum,
            reasoning=" | ".join(reasoning_parts),
            timestamp=datetime.now(),
        )

    def _behavior_to_signal(self, behavior_signal: BehaviorSignal) -> tuple[SignalType, float]:
        """T8: Map behavior phase to signal type and base strength.

        This is the PRIMARY signal logic. Behavior phase directly determines
        BUY/SELL/HOLD, not a weighted average.

        Returns:
            (SignalType, base_strength 0-1)
        """
        phase = behavior_signal.phase
        confidence = behavior_signal.confidence

        mapping = {
            BehaviorPhase.FOMO_EXTREME: (SignalType.SELL, 0.8),
            BehaviorPhase.FOMO_BUY:     (SignalType.SELL, 0.6),
            BehaviorPhase.PANIC_SELL:   (SignalType.BUY,  0.6),
            BehaviorPhase.CAPITULATION: (SignalType.BUY,  0.8),
            BehaviorPhase.SUSPICION:    (SignalType.BUY,  0.4),
            BehaviorPhase.EQUILIBRIUM:  (SignalType.HOLD, 0.2),
        }

        signal_type, base_strength = mapping.get(phase, (SignalType.HOLD, 0.2))

        # Scale strength by confidence
        strength = base_strength * confidence
        return signal_type, strength

    def _weighted_average_signal(
        self,
        composite_sentiment: float,
        momentum: float,
        psy_sentiment: float,
    ) -> tuple[SignalType, float]:
        """Fallback: old weighted average signal when behavior signal unavailable."""
        normalized_momentum = max(-1.0, min(1.0, momentum * 10))

        combined_score = (
            composite_sentiment * self.sentiment_weight +
            psy_sentiment * self.psy_weight +
            normalized_momentum * self.momentum_weight
        )

        if combined_score > self.sell_threshold:
            return SignalType.SELL, min(1.0, abs(combined_score))
        elif combined_score < self.buy_threshold:
            return SignalType.BUY, min(1.0, abs(combined_score))
        else:
            return SignalType.HOLD, min(1.0, abs(combined_score))

    def _calculate_confirmation_adjustment(
        self,
        psy_sentiment: float,
        momentum: float,
        behavior_signal: Optional[BehaviorSignal],
    ) -> float:
        """T8: PSY/momentum as secondary confirmers → adjust signal strength.

        If PSY and momentum confirm the behavior phase, increase strength.
        If they contradict, decrease strength (but don't flip signal type).

        Returns:
            Adjustment value (-0.2 to +0.2)
        """
        if behavior_signal is None:
            return 0.0

        phase = behavior_signal.phase

        # For BUY signals (PANIC_SELL, CAPITULATION, SUSPICION)
        if phase in (BehaviorPhase.PANIC_SELL, BehaviorPhase.CAPITULATION, BehaviorPhase.SUSPICION):
            # Confirm if PSY shows fear (oversold) and momentum is negative
            confirmation = 0.0
            if psy_sentiment < -0.3:  # PSY shows fear
                confirmation += 0.1
            if momentum < -0.05:  # Negative momentum (falling)
                confirmation += 0.1
            return min(0.2, confirmation)

        # For SELL signals (FOMO_BUY, FOMO_EXTREME)
        if phase in (BehaviorPhase.FOMO_BUY, BehaviorPhase.FOMO_EXTREME):
            # Confirm if PSY shows greed (overbought) and momentum is positive
            confirmation = 0.0
            if psy_sentiment > 0.3:  # PSY shows greed
                confirmation += 0.1
            if momentum > 0.05:  # Positive momentum (rising)
                confirmation += 0.1
            return min(0.2, confirmation)

        # EQUILIBRIUM → no adjustment
        return 0.0

    def generate_signal_from_market_state(
        self,
        market_state: "MarketState",
    ) -> TradingSignal:
        """T8: Generate trading signal from unified MarketState.

        Uses the full T5→T7→T8 pipeline:
        1. BehaviorModel.analyze_market_state() → BehaviorSignal (T7)
        2. BehaviorSignal → SignalType (T8 behavior-driven mapping)
        3. PSY/momentum from Binance klines → strength adjustment

        Args:
            market_state: Unified market state from all sources

        Returns:
            TradingSignal object
        """
        # Step 1: Behavior analysis from MarketState (T7)
        behavior_signal = self._retail_model.analyze_market_state(market_state)

        # Step 2: Extract price data for PSY/momentum
        price_data = market_state.binance_klines
        momentum = market_state.binance_momentum or 0.0
        composite_sentiment = market_state.composite_sentiment

        # Step 3: Generate behavior-driven signal (T8)
        return self.generate_signal(
            composite_sentiment=composite_sentiment,
            momentum=momentum,
            symbol=market_state.symbol,
            price_data=price_data,
            behavior_signal=behavior_signal,
        )
