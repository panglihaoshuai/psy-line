"""Aggregated sentiment data source combining multiple inputs.

This module combines:
- Fear & Greed Index (alternative.me)
- Google Trends (pytrends)
- Reddit RSS feeds + MiniMax LLM sentiment analysis
- TradingView sentiment (via cryptocurrency.cv)

Into a unified sentiment score for trading signals.

T6 Refactor: Reddit posts now go through MiniMax LLM for actual sentiment analysis
instead of naive post-count scoring. Protected by RateLimiter for quota management.
"""

from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass

from .fear_greed import FearGreedClient, FearGreedData
from .google_trends import GoogleTrendsClient, GoogleTrendsData
from .reddit_rss import RedditRSSClient, RedditPost
from .tradingview_client import TradingViewClient, TradingViewSentiment
from .minimax_client import MiniMaxClient
from .rate_limiter import RateLimiter

# VADER sentiment analyzer as local fallback (no API key needed)
_vader_available: bool = False
_VaderAnalyzer: type | None = None  # noqa: N816 — class reference stored as module-level
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _VaderAnalyzer = SentimentIntensityAnalyzer
    _vader_available = True
except ImportError:
    pass


@dataclass
class AggregatedSentiment:
    """Aggregated sentiment from multiple sources."""
    composite_score: float  # -1 to 1
    fear_greed: Optional[FearGreedData] = None
    google_trends: Optional[Dict[str, GoogleTrendsData]] = None
    reddit_posts: Optional[List[RedditPost]] = None
    tradingview: Optional[Dict[str, TradingViewSentiment]] = None

    # Individual scores
    fear_greed_score: float = 0.0  # -1 to 1
    trends_score: float = 0.0  # -1 to 1
    social_score: float = 0.0  # -1 to 1
    reddit_llm_score: float = 0.0  # -1 to 1, from MiniMax LLM analysis

    # Metadata
    timestamp: Optional[datetime] = None
    sources_used: Optional[List[str]] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.sources_used is None:
            self.sources_used = []
        if self.reddit_posts is None:
            self.reddit_posts = []


class SentimentAggregator:
    """
    Aggregates sentiment from multiple sources.

    T6 Refactor: Uses MiniMax LLM for Reddit sentiment analysis instead of
    naive post-count scoring. Protected by RateLimiter for quota management.

    Weights can be configured to prioritize certain sources.
    """

    def __init__(
        self,
        fear_greed_weight: float = 0.3,
        trends_weight: float = 0.2,
        social_weight: float = 0.3,
        reddit_weight: float = 0.2,
        proxy_url: str = "http://127.0.0.1:7897",
        minimax_client: Optional[MiniMaxClient] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """
        Initialize aggregator with weights.

        Args:
            fear_greed_weight: Weight for Fear & Greed Index
            trends_weight: Weight for Google Trends
            social_weight: Weight for TradingView/social sentiment
            reddit_weight: Weight for Reddit content analysis
            proxy_url: Proxy URL for Google Trends (clash default: http://127.0.0.1:7897)
            minimax_client: Optional MiniMax client for LLM sentiment analysis
            rate_limiter: Optional rate limiter for quota management
        """
        self.fear_greed_weight = fear_greed_weight
        self.trends_weight = trends_weight
        self.social_weight = social_weight
        self.reddit_weight = reddit_weight
        self._proxy_url = proxy_url

        # Initialize clients
        self._fg_client = FearGreedClient()
        self._trends_client = None  # Lazy init
        self._reddit_client = RedditRSSClient()
        self._tv_client = TradingViewClient()

        # T6: MiniMax LLM integration
        self._minimax = minimax_client
        self._rate_limiter = rate_limiter

    def _get_trends_client(self) -> GoogleTrendsClient:
        """Lazy init Google Trends client with proxy."""
        if self._trends_client is None:
            self._trends_client = GoogleTrendsClient(proxy_url=self._proxy_url)
        return self._trends_client

    def get_fear_greed(self) -> FearGreedData:
        """Get current Fear & Greed Index."""
        try:
            return self._fg_client.get_current()
        except Exception as e:
            print(f"Fear & Greed fetch error: {e}", file=__import__("sys").stderr)
            return FearGreedData(value=50, value_classification="Neutral", timestamp=datetime.now())

    def get_google_trends(self, keywords: Optional[List[str]] = None) -> Dict[str, GoogleTrendsData]:
        """Get Google Trends data for keywords."""
        if keywords is None:
            keywords = ["bitcoin", "ethereum", "crypto"]
        try:
            return self._get_trends_client().get_interest(keywords)
        except Exception as e:
            print(f"Google Trends fetch error: {e}", file=__import__("sys").stderr)
            return {kw: GoogleTrendsData(keyword=kw, value=50, timestamp=datetime.now(), timeframe="now 1h") for kw in keywords}

    def get_reddit(self, subreddits: Optional[List[str]] = None, limit: int = 25) -> List[RedditPost]:
        """Get Reddit posts from RSS feeds."""
        if subreddits is None:
            subreddits = ["CryptoCurrency", "Bitcoin", "ethereum"]
        try:
            return self._reddit_client.fetch_posts(subreddits, limit=limit)
        except Exception as e:
            print(f"Reddit RSS fetch error: {e}", file=__import__("sys").stderr)
            return []

    def get_tradingview_sentiment(self, symbols: Optional[List[str]] = None) -> Dict[str, TradingViewSentiment]:
        """Get TradingView-style sentiment."""
        if symbols is None:
            symbols = ["BTC", "ETH"]
        try:
            return self._tv_client.get_sentiment(symbols)
        except Exception as e:
            print(f"TradingView sentiment fetch error: {e}", file=__import__("sys").stderr)
            return {s: TradingViewSentiment(symbol=s, sentiment=0.0, classification="Neutral", buzz=50.0, timestamp=datetime.now()) for s in symbols}

    def _analyze_reddit_with_llm(self, posts: List[RedditPost]) -> Optional[float]:
        """Analyze Reddit post sentiment with fallback chain.

        Fallback order:
        1. MiniMax LLM (primary) — protected by wait_for_slot()
        2. VADER local (fallback) — no API key needed
        3. 0.0 (neutral) — last resort

        Returns:
            Sentiment score (-1 to 1) if any analyzer succeeded, None only if no posts.
        """
        if not posts:
            return None

        # --- Attempt 1: MiniMax LLM ---
        if self._minimax is not None:
            llm_available = True
            if self._rate_limiter is not None:
                llm_available = self._rate_limiter.wait_for_slot(max_wait=60.0)

            if llm_available:
                try:
                    texts = [f"{p.title} {p.content[:200]}" for p in posts]
                    results = self._minimax.analyze_sentiment(texts)

                    if results:
                        composite = sum(r.score for r in results) / len(results)
                        return max(-1.0, min(1.0, composite))
                except Exception as e:
                    print(f"Reddit LLM analysis error: {e}", file=__import__("sys").stderr)
            else:
                print("LLM quota exhausted, falling back to VADER", file=__import__("sys").stderr)
        else:
            print("MiniMax client not configured, falling back to VADER", file=__import__("sys").stderr)

        # --- Attempt 2: VADER local fallback ---
        if _vader_available and _VaderAnalyzer is not None:
            try:
                analyzer = _VaderAnalyzer()
                scores = [analyzer.polarity_scores(f"{p.title} {p.content[:200]}") for p in posts]
                composite = sum(s["compound"] for s in scores) / len(scores)
                print(f"VADER fallback sentiment: {composite:.3f} (LLM unavailable)", file=__import__("sys").stderr)
                return max(-1.0, min(1.0, composite))
            except Exception as e:
                print(f"VADER analysis failed: {e}", file=__import__("sys").stderr)
        else:
            print("VADER not installed, install with: pip install vaderSentiment", file=__import__("sys").stderr)

        # --- Last resort ---
        return 0.0

    def aggregate(
        self,
        fetch_all: bool = True,
        subreddits: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        symbols: Optional[List[str]] = None,
    ) -> AggregatedSentiment:
        """
        Fetch and aggregate all sentiment sources.

        T6 Refactor: Reddit posts now go through MiniMax LLM for sentiment analysis.
        LLM usage is protected by RateLimiter quota management.

        Args:
            fetch_all: Whether to fetch all sources (else use cached/mock)
            subreddits: Reddit subreddits to monitor
            keywords: Google Trends keywords
            symbols: TradingView symbols

        Returns:
            AggregatedSentiment with composite score
        """
        sources_used = []
        fear_greed_data = None
        trends_data = None
        reddit_posts = []
        tv_data = None

        # Fear & Greed (always fetch - free, no rate limit)
        fear_greed_score = 0.0
        try:
            fear_greed_data = self.get_fear_greed()
            fear_greed_score = fear_greed_data.sentiment_score
            sources_used.append("fear_greed")
        except Exception:
            pass

        # Google Trends (has rate limits)
        trends_score = 0.0
        if fetch_all:
            try:
                if keywords is None:
                    keywords = ["bitcoin", "ethereum", "cryptocurrency"]
                trends_data = self.get_google_trends(keywords)
                # Average all trends scores
                if trends_data:
                    trends_score = sum(t.value for t in trends_data.values()) / len(trends_data) / 100 - 0.5
                    sources_used.append("google_trends")
            except Exception:
                pass

        # Reddit RSS + T6 LLM sentiment analysis
        reddit_llm_score: Optional[float] = None
        if fetch_all:
            try:
                if subreddits is None:
                    subreddits = ["CryptoCurrency", "Bitcoin", "ethereum"]
                reddit_posts = self.get_reddit(subreddits)
                sources_used.append("reddit")

                # T6: Use MiniMax LLM for actual sentiment analysis
                if reddit_posts:
                    reddit_llm_score = self._analyze_reddit_with_llm(reddit_posts)
                    if reddit_llm_score is not None:
                        sources_used.append("reddit_llm")
            except Exception:
                pass

        # TradingView sentiment
        if fetch_all:
            try:
                if symbols is None:
                    symbols = ["BTC", "ETH"]
                tv_data = self.get_tradingview_sentiment(symbols)
                if tv_data:
                    tv_score = sum(t.sentiment for t in tv_data.values()) / len(tv_data)
                    sources_used.append("tradingview")
            except Exception:
                pass

        # T6: LLM ran → use its score (even if 0.0 = neutral). LLM unavailable → NO fallback to post count.
        if reddit_llm_score is not None:
            social_score = reddit_llm_score
        else:
            # LLM not available - do NOT fall back to naive post counting
            social_score = 0.0

        # If TradingView is available, average with social score
        if tv_data:
            tv_score = sum(t.sentiment for t in tv_data.values()) / len(tv_data)
            social_score = (social_score + tv_score) / 2

        # Calculate composite score
        composite = (
            fear_greed_score * self.fear_greed_weight +
            trends_score * self.trends_weight +
            social_score * (self.social_weight + self.reddit_weight)
        )

        # Normalize composite to -1 to 1
        composite = max(-1.0, min(1.0, composite))

        return AggregatedSentiment(
            composite_score=composite,
            fear_greed=fear_greed_data,
            google_trends=trends_data,
            reddit_posts=reddit_posts,
            tradingview=tv_data,
            fear_greed_score=fear_greed_score,
            trends_score=trends_score,
            social_score=social_score,
            reddit_llm_score=reddit_llm_score if reddit_llm_score is not None else 0.0,
            sources_used=sources_used,
            timestamp=datetime.now(),
        )
