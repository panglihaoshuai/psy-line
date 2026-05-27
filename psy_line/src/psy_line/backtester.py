"""Backtesting engine for trading signals."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set

from .types import BacktestResult, BacktestTrade, TradingSignal, BinanceKline, SentimentResult


@dataclass
class Backtester:
    """Backtest trading signals against historical price data."""

    initial_balance: float = 10000.0

    def _find_signal_for_kline(
        self,
        kline: BinanceKline,
        signals: List[TradingSignal],
        used_signals: Set[int],
    ) -> Optional[TradingSignal]:
        """Find the best matching signal for a kline by timestamp.

        Matches signals whose timestamp is within ±1 kline interval of the kline's open_time.
        Returns None if no matching signal found or all signals already used.
        """
        kline_time = kline.open_time / 1000  # Convert ms to seconds
        best_signal = None
        best_time_diff = float("inf")

        for idx, signal in enumerate(signals):
            if idx in used_signals:
                continue
            signal_ts = signal.timestamp.timestamp()
            time_diff = abs(signal_ts - kline_time)
            # Match if within 2 hours (covers most common intervals)
            if time_diff < 7200 and time_diff < best_time_diff:
                best_time_diff = time_diff
                best_signal = (signal, idx)

        if best_signal:
            used_signals.add(best_signal[1])
            return best_signal[0]
        return None

    def backtest(
        self,
        signals: List[TradingSignal],
        historical_prices: List[BinanceKline],
        sentiment_history: List[Dict[str, object]],
    ) -> BacktestResult:
        """
        Run backtest on trading signals.

        Simulates trading with:
        - Initial balance in USDT
        - BUY signal: Convert all USDT to BTC
        - SELL signal: Convert all BTC to USDT
        - HOLD: No action

        Signals are matched to klines by timestamp (within ±2 hours).

        Args:
            signals: List of TradingSignal objects
            historical_prices: List of BinanceKline (must be in chronological order)
            sentiment_history: Historical sentiment data (for future use)

        Returns:
            BacktestResult with performance metrics
        """
        if not historical_prices:
            return BacktestResult(
                total_pnl=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                sharpe_ratio=0.0,
                num_trades=0,
                trades=[],
            )

        # Simulate trading
        usdt_balance = self.initial_balance
        btc_balance = 0.0
        position_open = False
        entry_price = 0.0
        entry_time: Optional[datetime] = None
        trades: List[BacktestTrade] = []
        used_signals: Set[int] = set()

        for kline in historical_prices:
            current_price = kline.close
            current_time = datetime.fromtimestamp(kline.open_time / 1000)

            # Find matching signal by timestamp
            signal = self._find_signal_for_kline(kline, signals, used_signals)

            if signal is None:
                continue

            if not position_open and signal.type.value == "BUY":
                # Open position
                btc_balance = usdt_balance / current_price
                entry_price = current_price
                entry_time = current_time
                usdt_balance = 0.0
                position_open = True

            elif position_open and signal.type.value == "SELL":
                # Close position
                exit_price = current_price
                pnl = (exit_price - entry_price) * btc_balance
                pnl_pct = (exit_price - entry_price) / entry_price * 100

                trades.append(
                    BacktestTrade(
                        entry_time=entry_time or current_time,
                        exit_time=current_time,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                    )
                )

                usdt_balance = btc_balance * current_price
                btc_balance = 0.0
                position_open = False

        # Calculate final metrics
        if position_open:
            # Close final position at last price
            final_price = historical_prices[-1].close
            pnl = (final_price - entry_price) * btc_balance
            trades.append(
                BacktestTrade(
                    entry_time=entry_time or datetime.now(),
                    exit_time=datetime.fromtimestamp(historical_prices[-1].open_time / 1000),
                    entry_price=entry_price,
                    exit_price=final_price,
                    pnl=pnl,
                    pnl_pct=(final_price - entry_price) / entry_price * 100,
                )
            )
            usdt_balance = btc_balance * final_price

        total_pnl = usdt_balance - self.initial_balance
        total_pnl_pct = (total_pnl / self.initial_balance) * 100

        # Calculate metrics
        win_count = sum(1 for t in trades if t.pnl > 0)
        win_rate = win_count / len(trades) if trades else 0.0

        # Max drawdown
        max_drawdown = 0.0
        peak = self.initial_balance
        for trade in trades:
            if trade.pnl < 0:
                drawdown = abs(trade.pnl) / peak
                max_drawdown = max(max_drawdown, drawdown)

        # Sharpe ratio (simplified: using trade returns)
        if trades and len(trades) > 1:
            returns = [t.pnl_pct / 100 for t in trades]
            avg_return = sum(returns) / len(returns)
            std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
            sharpe_ratio = avg_return / std_return if std_return > 0 else 0.0
        else:
            sharpe_ratio = 0.0

        return BacktestResult(
            total_pnl=total_pnl_pct,  # As percentage
            max_drawdown=max_drawdown * 100,  # As percentage
            win_rate=win_rate * 100,  # As percentage
            sharpe_ratio=sharpe_ratio,
            num_trades=len(trades),
            trades=trades,
        )
