"""MCP Server main entry point for PSY_line.

Refactored architecture:
- Old: SentimentAggregator (weighted average) + SentimentAnalyzer (OpenAI) → REMOVED
- New: UnifiedDataSource → MarketState → BehaviorModel → SignalGenerator
"""

import os
import sys
from typing import Any

# Add src to path for local imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import modules - new architecture only
from .binance_client import BinanceClient
from .signal_generator import SignalGenerator
from .backtester import Backtester
from .fear_greed import FearGreedClient
from .config import Config, RedditConfig, BinanceConfig
from .minimax_client import MiniMaxClient
from .rate_limiter import RateLimiter
from .unified_source import UnifiedDataSource

# Server instance
APP_NAME = "psy-line"
SERVER = Server(APP_NAME)

# Global instances (initialized on first tool call)
_config: Config | None = None
_binance_client: BinanceClient | None = None
_signal_generator: SignalGenerator | None = None
_backtester: Backtester | None = None
_fear_greed_client: FearGreedClient | None = None
_minimax_client: MiniMaxClient | None = None
_rate_limiter: RateLimiter | None = None
_unified_source: UnifiedDataSource | None = None


def get_config() -> Config:
    """Get or initialize configuration."""
    global _config
    if _config is None:
        config_path = os.environ.get("PSY_LINE_CONFIG", "config.yaml")
        for path in [config_path, "config.yaml", "../config.yaml"]:
            if os.path.exists(path):
                _config = Config.from_yaml(path)
                break
        else:
            _config = Config(
                reddit=RedditConfig(
                    client_id="",
                    client_secret="",
                    user_agent="PSY_line/1.0",
                    keywords=[],
                    keywords_mode="include",
                ),
                binance=BinanceConfig(
                    api_key=os.environ.get("BINANCE_API_KEY", ""),
                    secret_key=os.environ.get("BINANCE_SECRET_KEY", ""),
                    testnet=True,
                ),
            )
    return _config


def get_binance_client() -> BinanceClient:
    """Get or initialize Binance client."""
    global _binance_client
    if _binance_client is None:
        cfg = get_config()
        _binance_client = BinanceClient(
            api_key=cfg.binance.api_key,
            secret_key=cfg.binance.secret_key,
            testnet=cfg.binance.testnet,
        )
    return _binance_client


def get_signal_generator() -> SignalGenerator:
    """Get or initialize signal generator."""
    global _signal_generator
    if _signal_generator is None:
        cfg = get_config()
        _signal_generator = SignalGenerator(
            buy_threshold=cfg.trading.buy_threshold,
            sell_threshold=cfg.trading.sell_threshold,
        )
    return _signal_generator


def get_backtester() -> Backtester:
    """Get or initialize backtester."""
    global _backtester
    if _backtester is None:
        _backtester = Backtester(initial_balance=10000.0)
    return _backtester


def get_rate_limiter() -> RateLimiter:
    """Get or initialize rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def get_minimax_client(rate_limiter: RateLimiter) -> MiniMaxClient:
    """Get or initialize MiniMax client."""
    global _minimax_client
    if _minimax_client is None:
        _minimax_client = MiniMaxClient(rate_limiter=rate_limiter)
    return _minimax_client


def get_fear_greed_client() -> FearGreedClient:
    """Get or initialize Fear & Greed client."""
    global _fear_greed_client
    if _fear_greed_client is None:
        _fear_greed_client = FearGreedClient()
    return _fear_greed_client


def get_unified_source() -> UnifiedDataSource:
    """Get or initialize unified data source."""
    global _unified_source
    if _unified_source is None:
        rate_limiter = get_rate_limiter()
        minimax = get_minimax_client(rate_limiter)
        _unified_source = UnifiedDataSource(
            minimax_client=minimax,
            rate_limiter=rate_limiter,
        )
    return _unified_source


# =============================================================================
# MCP Tools
# =============================================================================

@SERVER.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MCP tools."""
    return [
        Tool(
            name="get_fear_greed_index",
            description="Get current Crypto Fear & Greed Index from alternative.me (free, no API key)",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_binance_price",
            description="Get Binance price data for a symbol (current price + kline summary)",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "default": "BTCUSDT",
                    },
                    "interval": {
                        "type": "string",
                        "default": "1h",
                        "enum": ["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
                    },
                    "limit": {
                        "type": "integer",
                        "default": 100,
                    },
                },
            },
        ),
        Tool(
            name="generate_trading_signal",
            description="Generate behavior-driven trading signal from sentiment score and price momentum",
            inputSchema={
                "type": "object",
                "properties": {
                    "composite_sentiment": {
                        "type": "number",
                        "description": "Composite sentiment score (-1 to 1)",
                    },
                    "momentum": {
                        "type": "number",
                        "description": "Price momentum (e.g., 0.05 = 5% change)",
                    },
                    "symbol": {
                        "type": "string",
                        "default": "BTCUSDT",
                    },
                },
                "required": ["composite_sentiment", "momentum", "symbol"],
            },
        ),
        Tool(
            name="backtest_signal",
            description="Backtest a trading signal against historical price data",
            inputSchema={
                "type": "object",
                "properties": {
                    "signal": {"type": "object"},
                    "historical_prices": {"type": "array"},
                    "sentiment_history": {"type": "array"},
                },
                "required": ["signal", "historical_prices"],
            },
        ),
        Tool(
            name="detect_retail_behavior",
            description="Detect retail investor behavior phase (FOMO, panic sell, capitulation, etc.) from price and volume data",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "default": "BTCUSDT"},
                    "interval": {"type": "string", "default": "1h", "description": "Kline interval (1m, 5m, 15m, 1h, 4h, 1d)"},
                    "limit": {"type": "integer", "default": 100, "description": "Number of klines to analyze"},
                },
            },
        ),
        Tool(
            name="get_quota_status",
            description="Get MiniMax API quota status (LLM and search remaining requests, current time period)",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="run_behavior_scan",
            description="Run complete behavior-driven scan: all data sources → MarketState → BehaviorModel → SignalGenerator. Includes behavior phase, LLM sentiment, and quota status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "default": "BTCUSDT"},
                    "use_llm": {"type": "boolean", "default": True, "description": "Use MiniMax LLM for Reddit sentiment analysis (consumes quota)"},
                    "use_search": {"type": "boolean", "default": True, "description": "Use MiniMax web_search for additional context (consumes quota)"},
                },
            },
        ),
    ]


@SERVER.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "get_fear_greed_index":
            client = get_fear_greed_client()
            fg = client.get_current()
            return [TextContent(type="text", text=f"Fear & Greed Index: {fg.value}/100 ({fg.value_classification})\nTimestamp: {fg.timestamp.isoformat()}")]

        elif name == "get_binance_price":
            client = get_binance_client()
            symbol = arguments.get("symbol", "BTCUSDT")
            interval = arguments.get("interval", "1h")
            limit = arguments.get("limit", 100)
            klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
            if klines:
                latest = klines[-1]
                current_price = client.get_current_price(symbol=symbol) if client else 0.0
                return [
                    TextContent(type="text", text=f"{symbol} @ ${current_price:.2f}"),
                    TextContent(type="text", text=f"Interval: {interval} | Klines: {len(klines)} | Latest: ${latest.close:.2f}"),
                ]
            return [TextContent(type="text", text=f"No data for {symbol}")]

        elif name == "generate_trading_signal":
            gen = get_signal_generator()
            result = gen.generate_signal(
                composite_sentiment=arguments.get("composite_sentiment", 0.0),
                momentum=arguments.get("momentum", 0.0),
                symbol=arguments.get("symbol", "BTCUSDT"),
            )
            return [TextContent(type="text", text=f"Signal: {result.type.value} (strength: {result.strength:.2f})\nReasoning: {result.reasoning}")]

        elif name == "backtest_signal":
            bt = get_backtester()
            result = bt.backtest(
                signals=[arguments.get("signal", {})],
                historical_prices=arguments.get("historical_prices", []),
                sentiment_history=arguments.get("sentiment_history", []),
            )
            return [TextContent(type="text", text=f"Backtest: PnL={result.total_pnl:.2f}%, Win Rate={result.win_rate:.1f}%, Trades={result.num_trades}")]

        elif name == "detect_retail_behavior":
            symbol = arguments.get("symbol", "BTCUSDT")
            interval = arguments.get("interval", "1h")
            limit = arguments.get("limit", 100)

            client = get_binance_client()
            prices = client.get_klines(symbol, interval, limit=limit)

            if not prices:
                return [TextContent(type="text", text=f"No price data found for {symbol}")]

            gen = get_signal_generator()
            behavior = gen.get_retail_behavior_signal(prices)

            # Build output
            ind = behavior.indicators
            output = [
                f"=== Retail Behavior Detection for {symbol} ===",
                f"Phase: {behavior.phase.value.upper()}",
                f"Confidence: {behavior.confidence:.1%}",
                f"",
                f"--- Indicators ---",
                f"FOMO Score: {ind.fomo_score:.1%}",
                f"Herding Score: {ind.herding_score:.1%}",
                f"Disposition Score: {ind.disposition_score:.1%}",
                f"Panic Score: {ind.panic_score:.1%}",
                f"",
                f"Price Momentum: {ind.price_momentum:.3f}",
                f"Consecutive Up Days: {ind.consecutive_up_days}",
                f"Consecutive Down Days: {ind.consecutive_down_days}",
                f"Volatility: {ind.volatility:.3f}",
                f"Volume Ratio: {ind.volume_ratio:.2f}",
                f"",
                f"--- Narrative ---",
                behavior.narrative,
            ]
            if behavior.warnings:
                output.append("")
                output.append("--- Warnings ---")
                output.extend(behavior.warnings)

            return [TextContent(type="text", text="\n".join(output))]

        elif name == "get_quota_status":
            rate_limiter = get_rate_limiter()
            quota = rate_limiter.get_remaining_quota()
            output = [
                "=== MiniMax API Quota Status ===",
                f"LLM Remaining: {quota['llm_remaining']}/{quota['llm_limit']}",
                f"Search Remaining: {quota['search_remaining']}/{quota['search_limit']}",
                f"Current Period: {quota['current_period']}",
                f"Next Reset: {quota['next_reset'].isoformat()}",
            ]
            return [TextContent(type="text", text="\n".join(output))]

        elif name == "run_behavior_scan":
            from datetime import datetime

            symbol = arguments.get("symbol", "BTCUSDT")
            use_llm = arguments.get("use_llm", True)
            use_search = arguments.get("use_search", True)

            rate_limiter = get_rate_limiter()
            data_source = get_unified_source()

            # Step 1: Fetch all data sources → MarketState (T5)
            market_state = data_source.fetch(
                symbol=symbol,
                include_llm=use_llm,
                include_search=use_search,
            )

            # Step 2: Generate behavior-driven signal (T7→T8)
            gen = get_signal_generator()
            signal = gen.generate_signal_from_market_state(market_state)

            # Step 3: Build comprehensive output
            output = [
                f"=== Behavior-Driven Scan for {symbol} ===",
                f"Scan Time: {datetime.now().isoformat()}",
                f"",
                f"--- Behavior Phase (PRIMARY) ---",
                f"Phase: {signal.reasoning.split(':')[1].split('(')[0] if ':' in signal.reasoning else 'N/A'}",
                f"Signal: {signal.type.value}",
                f"Strength: {signal.strength:.2f}",
                f"Reasoning: {signal.reasoning}",
                f"",
                f"--- Price Data ---",
                f"Current Price: ${market_state.binance_current_price:.2f}" if market_state.binance_current_price else "Current Price: N/A",
                f"Momentum: {market_state.binance_momentum*100:+.2f}%" if market_state.binance_momentum is not None else "Momentum: N/A",
                f"Klines Analyzed: {len(market_state.binance_klines)}",
                f"",
                f"--- Sentiment Sources ---",
                f"Fear & Greed: {market_state.fear_greed_value}/100 ({market_state.fear_greed_classification})" if market_state.fear_greed_value is not None else "Fear & Greed: N/A",
                f"Reddit Posts: {len(market_state.reddit_posts)}",
                f"Reddit LLM Score: {market_state.reddit_composite_score:+.3f}" if market_state.reddit_composite_score is not None else "Reddit LLM: N/A",
                f"Google Trends: {market_state.google_trends_score:+.3f}" if market_state.google_trends_score is not None else "Google Trends: N/A",
                f"TradingView: {market_state.tradingview_composite:+.3f}" if market_state.tradingview_composite is not None else "TradingView: N/A",
                f"",
                f"--- Data Sources Used ---",
                f"Sources: {', '.join(market_state.sources_used)}",
                f"LLM Used: {'Yes' if 'reddit_llm' in market_state.sources_used else 'No'}",
                f"Web Search Used: {'Yes' if 'web_search' in market_state.sources_used else 'No'}",
                f"",
                f"--- Quota Status ---",
            ]

            # Add quota status
            quota = rate_limiter.get_remaining_quota()
            output.append(f"LLM Remaining: {quota['llm_remaining']}/{quota['llm_limit']}")
            output.append(f"Search Remaining: {quota['search_remaining']}/{quota['search_limit']}")
            output.append(f"Current Period: {quota['current_period']}")

            return [TextContent(type="text", text="\n".join(output))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        import traceback
        return [TextContent(type="text", text=f"Error: {str(e)}\n{traceback.format_exc()}")]


async def main():
    """Main entry point for MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await SERVER.run(read_stream, write_stream, SERVER.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
