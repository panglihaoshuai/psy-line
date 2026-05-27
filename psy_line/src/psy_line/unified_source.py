"""Unified data source combining all market data into MarketState.

Replaces SentimentAggregator as the primary data aggregation layer.
Integrates MiniMax web_search for Reddit discussions and Google Trends alternative.
"""

import logging
from datetime import datetime
from typing import List, Optional

from .fear_greed import FearGreedClient
from .reddit_rss import RedditRSSClient
from .google_trends import GoogleTrendsClient
from .tradingview_client import TradingViewClient
from .binance_client import BinanceClient
from .minimax_client import MiniMaxClient
from .rate_limiter import RateLimiter
from .market_state import MarketState, SearchResult

logger = logging.getLogger(__name__)


class UnifiedDataSource:
    """Unified data source that fetches all market data into a single MarketState."""

    def __init__(
        self,
        minimax_client: Optional[MiniMaxClient] = None,
        rate_limiter: Optional[RateLimiter] = None,
        proxy_url: str = "http://127.0.0.1:7897",
    ):
        self._fg_client = FearGreedClient()
        self._reddit_client = RedditRSSClient()
        self._trends_client = GoogleTrendsClient(proxy_url=proxy_url)
        self._tv_client = TradingViewClient()
        self._binance_client = BinanceClient(
            api_key="",
            secret_key="",
            testnet=True,
        )
        self._minimax = minimax_client or MiniMaxClient(rate_limiter=rate_limiter)
        self._rate_limiter = rate_limiter or RateLimiter()

    def fetch(
        self,
        symbol: str = "BTCUSDT",
        subreddits: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        search_queries: Optional[List[str]] = None,
        include_llm: bool = True,
        include_search: bool = True,
    ) -> MarketState:
        """Fetch all data sources and return unified MarketState.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            subreddits: Reddit subreddits to monitor
            keywords: Google Trends keywords
            search_queries: MiniMax web_search queries
            include_llm: Whether to run LLM sentiment analysis on Reddit posts
            include_search: Whether to run web searches

        Returns:
            MarketState with all available data
        """
        if subreddits is None:
            subreddits = ["CryptoCurrency", "Bitcoin", "ethereum"]
        if keywords is None:
            keywords = ["bitcoin", "ethereum", "cryptocurrency"]
        if search_queries is None:
            search_queries = [f"bitcoin price sentiment reddit", f"crypto market outlook"]

        sources_used = []

        # 1. Fear & Greed Index (always fetch - free, no rate limit)
        fear_greed_value = None
        fear_greed_classification = None
        fear_greed_score = None
        try:
            fg = self._fg_client.get_current()
            fear_greed_value = fg.value
            fear_greed_classification = fg.value_classification
            fear_greed_score = fg.sentiment_score
            sources_used.append("fear_greed")
        except Exception as e:
            logger.warning(f"Fear & Greed fetch failed: {e}")

        # 2. Reddit RSS
        reddit_posts = []
        try:
            reddit_posts = self._reddit_client.fetch_posts(subreddits, limit=25, keywords=keywords)
            if reddit_posts:
                sources_used.append("reddit")
        except Exception as e:
            logger.warning(f"Reddit RSS fetch failed: {e}")

        # 3. Reddit LLM sentiment analysis
        reddit_sentiment_scores = []
        reddit_composite_score = None
        if include_llm and reddit_posts and self._rate_limiter.can_use_llm():
            try:
                texts = [p.title + " " + p.content[:200] for p in reddit_posts]
                reddit_sentiment_scores = self._minimax.analyze_sentiment(texts)
                if reddit_sentiment_scores:
                    reddit_composite_score = sum(s.score for s in reddit_sentiment_scores) / len(reddit_sentiment_scores)
                    sources_used.append("reddit_llm")
            except Exception as e:
                logger.warning(f"Reddit LLM analysis failed: {e}")

        # 4. Google Trends
        google_trends_data = None
        google_trends_score = None
        if self._rate_limiter.can_use_search():
            try:
                google_trends_data = self._trends_client.get_interest(keywords)
                if google_trends_data:
                    google_trends_score = sum(t.value for t in google_trends_data.values()) / len(google_trends_data) / 100 - 0.5
                    sources_used.append("google_trends")
            except Exception as e:
                logger.warning(f"Google Trends fetch failed: {e}")

        # 5. TradingView sentiment
        tradingview_sentiment = None
        tradingview_composite = None
        try:
            symbols = ["BTC", "ETH"]
            tradingview_sentiment = self._tv_client.get_sentiment(symbols)
            if tradingview_sentiment:
                tradingview_composite = sum(t.sentiment for t in tradingview_sentiment.values()) / len(tradingview_sentiment)
                sources_used.append("tradingview")
        except Exception as e:
            logger.warning(f"TradingView sentiment fetch failed: {e}")

        # 6. Binance price data
        binance_klines = []
        binance_current_price = None
        binance_momentum = None
        try:
            binance_klines = self._binance_client.get_klines(symbol, "1h", limit=100)
            if binance_klines:
                binance_current_price = binance_klines[-1].close
                oldest = binance_klines[0].close
                if oldest > 0:
                    binance_momentum = (binance_klines[-1].close - oldest) / oldest
                sources_used.append("binance")
        except Exception as e:
            logger.warning(f"Binance fetch failed: {e}")

        # 7. MiniMax web search
        search_results = []
        if include_search:
            for query in search_queries:
                if self._rate_limiter.can_use_search():
                    try:
                        results = self._minimax.web_search(query)
                        search_results.extend(results)
                        if results:
                            sources_used.append("web_search")
                    except Exception as e:
                        logger.warning(f"Web search failed for '{query}': {e}")

        return MarketState(
            timestamp=datetime.now(),
            symbol=symbol,
            fear_greed_value=fear_greed_value,
            fear_greed_classification=fear_greed_classification,
            fear_greed_score=fear_greed_score,
            reddit_posts=reddit_posts,
            reddit_sentiment_scores=reddit_sentiment_scores,
            reddit_composite_score=reddit_composite_score,
            google_trends_data=google_trends_data,
            google_trends_score=google_trends_score,
            tradingview_sentiment=tradingview_sentiment,
            tradingview_composite=tradingview_composite,
            binance_klines=binance_klines,
            binance_current_price=binance_current_price,
            binance_momentum=binance_momentum,
            search_results=search_results,
            sources_used=sources_used,
        )
