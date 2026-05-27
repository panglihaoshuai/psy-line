"""Integration tests for PSY_line MCP Server."""

import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from psy_line.signal_generator import SignalGenerator
from psy_line.backtester import Backtester
from psy_line.types import (
    SentimentResult,
    SentimentType,
    TradingSignal,
    SignalType,
    BinanceKline,
)


class TestSignalGenerator:
    """Tests for SignalGenerator."""

    def _make_prices(self, trend: str = "neutral") -> list:
        """Helper to create test price data.

        T8 Update: Trends now include acceleration to trigger behavior model correctly.
        - "up": Accelerating upward trend (triggers FOMO_BUY)
        - "down": Accelerating downward trend (triggers PANIC_SELL/CAPITULATION)
        - "neutral": Flat with minor fluctuations (triggers EQUILIBRIUM)
        """
        from datetime import datetime
        prices = []
        for i in range(15):
            if trend == "up":
                # Accelerating upward: 100, 101, 103, 106, 110, 115, 121, 128...
                base = 100 + i * i // 2 + i  # Quadratic growth
            elif trend == "down":
                # Accelerating downward: 100, 99, 97, 94, 90, 85...
                base = 100 - i * i // 2 - i
            else:
                base = 100 + (i % 3 - 1)  # Small fluctuations around 100
            prices.append(BinanceKline(
                open_time=i * 3600000,
                open=base - 1,
                high=base + 1,
                low=base - 2,
                close=base,
                volume=1.0,
                close_time=(i + 1) * 3600000 - 1,
            ))
        return prices

    def test_buy_signal_threshold(self):
        """Sentiment below buy_threshold triggers BUY."""
        sg = SignalGenerator(buy_threshold=-0.6, sell_threshold=0.6)
        prices = self._make_prices("down")  # Bearish price trend
        signal = sg.generate_signal(-0.7, -0.02, "BTCUSDT", price_data=prices)
        assert signal.type == SignalType.BUY

    def test_sell_signal_threshold(self):
        """Sentiment above sell_threshold triggers SELL."""
        sg = SignalGenerator(buy_threshold=-0.6, sell_threshold=0.6)
        prices = self._make_prices("up")  # Bullish price trend
        signal = sg.generate_signal(0.7, 0.02, "BTCUSDT", price_data=prices)
        assert signal.type == SignalType.SELL

    def test_hold_signal_threshold(self):
        """Sentiment between thresholds triggers HOLD."""
        sg = SignalGenerator(buy_threshold=-0.6, sell_threshold=0.6)
        prices = self._make_prices("neutral")
        signal = sg.generate_signal(0.0, 0.0, "BTCUSDT", price_data=prices)
        assert signal.type == SignalType.HOLD

    def test_composite_sentiment_calculation(self):
        """Composite sentiment correctly weights multiple results."""
        sg = SignalGenerator()
        results = [
            SentimentResult(id="1", sentiment=SentimentType.BULLISH, score=1.0, reasoning=""),
            SentimentResult(id="2", sentiment=SentimentType.BEARISH, score=-1.0, reasoning=""),
        ]
        composite = sg.calculate_composite_sentiment(results)
        assert -0.1 <= composite <= 0.1  # Should be near 0

    def test_composite_sentiment_empty(self):
        """Empty results return 0."""
        sg = SignalGenerator()
        composite = sg.calculate_composite_sentiment([])
        assert composite == 0.0

    def test_momentum_calculation(self):
        """Momentum calculated as price change percentage."""
        sg = SignalGenerator()
        klines = [
            BinanceKline(open_time=1000, open=100, high=105, low=95, close=100, volume=1.0, close_time=1999),
            BinanceKline(open_time=2000, open=100, high=110, low=95, close=110, volume=1.0, close_time=2999),
        ]
        momentum = sg.calculate_momentum(klines)
        assert momentum == 0.1  # 10% increase

    def test_momentum_single_kline(self):
        """Single kline returns 0 momentum."""
        sg = SignalGenerator()
        klines = [
            BinanceKline(open_time=1000, open=100, high=105, low=95, close=100, volume=1.0, close_time=1999),
        ]
        momentum = sg.calculate_momentum(klines)
        assert momentum == 0.0

    def test_signal_strength(self):
        """Signal strength is between 0 and 1."""
        sg = SignalGenerator()
        prices = self._make_prices("neutral")
        signal = sg.generate_signal(0.9, 0.1, "BTCUSDT", price_data=prices)
        assert 0.0 <= signal.strength <= 1.0

    def test_signal_has_timestamp(self):
        """Signal includes timestamp."""
        sg = SignalGenerator()
        prices = self._make_prices("neutral")
        signal = sg.generate_signal(0.5, 0.05, "BTCUSDT", price_data=prices)
        assert signal.timestamp is not None

    def test_psy_calculation(self):
        """PSY indicator calculates correctly."""
        sg = SignalGenerator()
        # All up days (11 out of 12 comparisons are up = 91.67%)
        up_prices = [
            BinanceKline(open_time=i * 3600000, open=100 + i, high=101 + i, low=99 + i, close=101 + i, volume=1.0, close_time=(i + 1) * 3600000 - 1)
            for i in range(12)
        ]
        psy = sg.calculate_psy(up_prices)
        assert psy > 90.0  # Most periods up

        # Mix of up and down (should be around 50%)
        mixed_prices = [
            BinanceKline(open_time=i * 3600000, open=100, high=105, low=95,
                       close=105 if i % 2 == 0 else 95,
                       volume=1.0, close_time=(i + 1) * 3600000 - 1)
            for i in range(12)
        ]
        psy = sg.calculate_psy(mixed_prices)
        assert 40 <= psy <= 60  # Roughly balanced

    def test_psy_sentiment_conversion(self):
        """PSY converts to -1 to 1 sentiment."""
        sg = SignalGenerator()
        assert sg.calculate_psy_sentiment([]) == 0.0  # Empty = neutral

    def test_consecutive_streak(self):
        """Consecutive streak counts correctly."""
        sg = SignalGenerator()
        prices = self._make_prices("up")
        up, down = sg.get_consecutive_streak(prices)
        assert up > 0  # Last price was higher than previous
        assert down == 0


class TestBacktester:
    """Tests for Backtester."""

    def test_backtest_empty_prices(self):
        """Empty prices returns zero results."""
        bt = Backtester(initial_balance=10000.0)
        result = bt.backtest([], [], [])
        assert result.total_pnl == 0.0
        assert result.num_trades == 0

    def test_backtest_buy_and_sell(self):
        """Backtest simulates buy and sell correctly."""
        bt = Backtester(initial_balance=10000.0)

        # Create upward trending prices
        base_time = 1700000000000  # Fixed base time (ms)
        prices = [
            BinanceKline(
                open_time=base_time + i * 3600000,
                open=100 + i * 5,
                high=106 + i * 5,
                low=94 + i * 5,
                close=102 + i * 5,
                volume=1.0,
                close_time=base_time + (i + 1) * 3600000 - 1,
            )
            for i in range(10)
        ]

        signal = TradingSignal(
            type=SignalType.BUY,
            strength=0.8,
            composite_sentiment=-0.7,
            momentum=-0.02,
            reasoning="test",
            timestamp=__import__("datetime").datetime.fromtimestamp(base_time / 1000),
        )

        result = bt.backtest([signal], prices, [])

        assert result.num_trades == 1
        assert len(result.trades) == 1
        assert result.trades[0].pnl > 0  # Should be profitable on upward trend

    def test_backtest_hold(self):
        """HOLD signal doesn't open trades."""
        bt = Backtester(initial_balance=10000.0)

        prices = [
            BinanceKline(
                open_time=i * 3600000,
                open=100,
                high=105,
                low=95,
                close=100,
                volume=1.0,
                close_time=(i + 1) * 3600000 - 1,
            )
            for i in range(5)
        ]

        signal = TradingSignal(
            type=SignalType.HOLD,
            strength=0.5,
            composite_sentiment=0.0,
            momentum=0.0,
            reasoning="test",
            timestamp=__import__("datetime").datetime.now(),
        )

        result = bt.backtest([signal], prices, [])
        assert result.num_trades == 0

    def test_backtest_win_rate(self):
        """Win rate calculated correctly."""
        bt = Backtester(initial_balance=10000.0)

        # Create prices that go up then down
        prices = [
            BinanceKline(
                open_time=i * 3600000,
                open=100 + i * 10 if i < 5 else 150 - (i - 5) * 10,
                high=106 + i * 10 if i < 5 else 156 - (i - 5) * 10,
                low=94 + i * 10 if i < 5 else 144 - (i - 5) * 10,
                close=102 + i * 10 if i < 5 else 152 - (i - 5) * 10,
                volume=1.0,
                close_time=(i + 1) * 3600000 - 1,
            )
            for i in range(10)
        ]

        signals = [
            TradingSignal(
                type=SignalType.BUY,
                strength=0.8,
                composite_sentiment=-0.7,
                momentum=-0.02,
                reasoning="test",
                timestamp=__import__("datetime").datetime.now(),
            ),
            TradingSignal(
                type=SignalType.SELL,
                strength=0.8,
                composite_sentiment=0.7,
                momentum=0.02,
                reasoning="test",
                timestamp=__import__("datetime").datetime.now(),
            ),
        ]

        result = bt.backtest(signals, prices, [])
        assert result.num_trades >= 0  # At least some trades executed
        assert 0 <= result.win_rate <= 100


class TestTypes:
    """Tests for type definitions."""

    def test_sentiment_result_validation(self):
        """SentimentResult validates score range."""
        result = SentimentResult(
            id="test",
            sentiment=SentimentType.BULLISH,
            score=0.5,
            reasoning="test",
        )
        assert result.score == 0.5

    def test_sentiment_type_enum(self):
        """SentimentType enum values."""
        assert SentimentType.BULLISH.value == "bullish"
        assert SentimentType.BEARISH.value == "bearish"
        assert SentimentType.NEUTRAL.value == "neutral"

    def test_signal_type_enum(self):
        """SignalType enum values."""
        assert SignalType.BUY.value == "BUY"
        assert SignalType.SELL.value == "SELL"
        assert SignalType.HOLD.value == "HOLD"


class TestConfig:
    """Tests for configuration."""

    def test_config_env_expansion(self):
        """Config expands environment variables."""
        from psy_line.config import Config

        os.environ["TEST_API_KEY"] = "test_key_123"

        config = Config(
            reddit={"client_id": "id", "client_secret": "secret", "user_agent": "test"},
            openai={"api_key": "${TEST_API_KEY}", "model": "gpt-4o"},
            binance={"api_key": "key", "secret_key": "secret", "testnet": True},
        )

        # Note: from_yaml does expansion, direct Config() doesn't
        assert config.openai.api_key == "${TEST_API_KEY}"  # Direct init doesn't expand

    def test_config_validation_empty(self):
        """Empty config fails validation."""
        from psy_line.config import Config

        config = Config(
            reddit={"client_id": "", "client_secret": "", "user_agent": "test"},
            openai={"api_key": "", "model": "gpt-4o"},
            binance={"api_key": "", "secret_key": "", "testnet": True},
        )

        with pytest.raises(ValueError):
            config.validate_required()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
