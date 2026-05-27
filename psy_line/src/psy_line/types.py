"""Type definitions for PSY_line."""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class SentimentType(str, Enum):
    """Sentiment classification."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class SignalType(str, Enum):
    """Trading signal type."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class RedditComment(BaseModel):
    """A scraped Reddit comment."""
    id: str
    body: str
    subreddit: str
    score: int
    created_utc: float
    permalink: str


class SentimentResult(BaseModel):
    """Sentiment analysis result for a single comment."""
    id: str
    sentiment: SentimentType
    score: float = Field(ge=-1.0, le=1.0)
    reasoning: str


class BinanceKline(BaseModel):
    """A single Binance candlestick/kline."""
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int


class TradingSignal(BaseModel):
    """Generated trading signal."""
    type: SignalType
    strength: float = Field(ge=0.0, le=1.0)
    composite_sentiment: float
    momentum: float
    reasoning: str
    timestamp: datetime


class BacktestTrade(BaseModel):
    """A single backtest trade."""
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float


class BacktestResult(BaseModel):
    """Backtest results."""
    total_pnl: float
    max_drawdown: float
    win_rate: float
    sharpe_ratio: float
    num_trades: int
    trades: List[BacktestTrade]


class ScanResult(BaseModel):
    """Complete sentiment scan result."""
    scan_time: datetime
    symbol: str
    comments_analyzed: int
    composite_sentiment: float
    current_price: float
    signal: TradingSignal
    backtest: Optional[BacktestResult] = None
    top_bullish_comments: List[SentimentResult] = Field(default_factory=list)
    top_bearish_comments: List[SentimentResult] = Field(default_factory=list)


class SentimentRecord(BaseModel):
    """A sentiment history record for caching."""
    timestamp: datetime
    subreddit: str
    symbol: str
    composite_sentiment: float
    signal_type: str  # BUY, SELL, HOLD
    comments_analyzed: int = 0
