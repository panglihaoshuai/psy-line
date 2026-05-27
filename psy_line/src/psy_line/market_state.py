"""Unified market state combining all data sources."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .types import BinanceKline, SentimentResult
from .fear_greed import FearGreedData
from .reddit_rss import RedditPost
from .google_trends import GoogleTrendsData
from .tradingview_client import TradingViewSentiment


@dataclass
class SearchResult:
    """Web search result from MiniMax TokenPlan MCP."""
    title: str
    url: str
    snippet: str
    source: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MarketState:
    """Unified market state from all data sources."""
    timestamp: datetime
    symbol: str

    # Fear & Greed
    fear_greed_value: Optional[int] = None
    fear_greed_classification: Optional[str] = None
    fear_greed_score: Optional[float] = None

    # Reddit
    reddit_posts: list[RedditPost] = field(default_factory=list)
    reddit_sentiment_scores: list[SentimentResult] = field(default_factory=list)
    reddit_composite_score: Optional[float] = None

    # Google Trends
    google_trends_data: Optional[dict[str, GoogleTrendsData]] = None
    google_trends_score: Optional[float] = None

    # TradingView
    tradingview_sentiment: Optional[dict[str, TradingViewSentiment]] = None
    tradingview_composite: Optional[float] = None

    # Binance
    binance_klines: list[BinanceKline] = field(default_factory=list)
    binance_current_price: Optional[float] = None
    binance_momentum: Optional[float] = None

    # MiniMax web search
    search_results: list[SearchResult] = field(default_factory=list)

    # Metadata
    sources_used: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True if all major sources have data."""
        return bool(
            self.fear_greed_value is not None
            and self.reddit_posts
            and self.google_trends_data
            and self.binance_klines
        )

    @property
    def composite_sentiment(self) -> float:
        """Weighted average of all available sentiment sources."""
        scores = []
        weights = []
        if self.fear_greed_score is not None:
            scores.append(self.fear_greed_score)
            weights.append(0.3)
        if self.reddit_composite_score is not None:
            scores.append(self.reddit_composite_score)
            weights.append(0.3)
        if self.google_trends_score is not None:
            scores.append(self.google_trends_score)
            weights.append(0.2)
        if self.tradingview_composite is not None:
            scores.append(self.tradingview_composite)
            weights.append(0.2)
        if not scores:
            return 0.0
        total_weight = sum(weights)
        return sum(s * w for s, w in zip(scores, weights)) / total_weight
