# PSY_line - Crypto Sentiment Trading Signal MCP Server

**PSY_line** is an MCP (Model Context Protocol) server that provides multi-source sentiment analysis and trading signals for Hermes Agent.

## Overview

PSY_line aggregates sentiment from multiple **free** data sources (no API keys needed!), analyzes it, and generates trading signals for backtesting.

**Core Strategy**: Buy when sentiment is fear/panic (冰点), Sell when sentiment is greed/euphoria (高潮).

## Data Sources

| Source | Status | API Key Required |
|--------|--------|------------------|
| **Crypto Fear & Greed Index** (alternative.me) | ✅ Working | None |
| **Reddit RSS Feeds** | ✅ Working | None |
| **Google Trends** (pytrends) | ⚠️ Optional | None |
| **TradingView Sentiment** (cryptocurrency.cv) | ✅ Working | None |
| **Binance Price Data** | ✅ Working | Optional (testnet) |
| **OpenAI LLM Analysis** | ⏳ Optional | Required |

## Features

- **Fear & Greed Index** - Real-time 0-100 market sentiment
- **PSY Indicator** - Psychological Line technical analysis (连涨连跌天数)
- **Multi-Source Aggregation** - Combines all free sentiment sources
- **Reddit RSS** - No authentication, no rate limits
- **Google Trends** - Search interest data (pytrends)
- **Signal Generation** - BUY/SELL/HOLD based on combined sentiment + PSY + momentum
- **Backtesting Engine** - Validate against historical data
- **MCP Protocol** - Native Hermes Agent integration

## Installation

```bash
# Clone or navigate to psy_line directory
cd /path/to/psy_line

# Install in development mode
pip install -e .

# Or install with dev dependencies
pip install -e ".[dev]"
```

## Configuration

1. **Copy and edit config.yaml**:
   ```bash
   cp config.yaml config.local.yaml
   ```

2. **Set environment variables** (recommended for production):
   ```bash
   export REDDIT_CLIENT_ID="your_reddit_client_id"
   export REDDIT_CLIENT_SECRET="your_reddit_client_secret"
   export OPENAI_API_KEY="sk-your-openai-api-key"
   export BINANCE_API_KEY="your_binance_api_key"
   export BINANCE_SECRET_KEY="your_binance_secret_key"
   ```

3. **Edit config.yaml** (or config.local.yaml):
   ```yaml
   reddit:
     client_id: "${REDDIT_CLIENT_ID}"
     client_secret: "${REDDIT_CLIENT_SECRET}"
     user_agent: "PSY_line/1.0 (Trading Bot)"

   openai:
     api_key: "${OPENAI_API_KEY}"
     model: "gpt-4o"
     batch_size: 30
     max_requests_per_minute: 20

   binance:
     api_key: "${BINANCE_API_KEY}"
     secret_key: "${BINANCE_SECRET_KEY}"
     testnet: true  # Set to false for live trading

   subreddits:
     - CryptoCurrency
     - SatoshiBets
     - Bitcoin
     - ethereum
     - SOLMarkets
     - ethtrader

   trading:
     symbol: "BTCUSDT"
     buy_threshold: -0.6   # BUY when sentiment < -0.6
     sell_threshold: 0.6  # SELL when sentiment > 0.6
     position_size: 0.1
   ```

## API Keys Setup

### Reddit API

1. Go to https://www.reddit.com/prefs/apps
2. Click "Create App" or "Are you a developer? Create an app..."
3. Select "script" type
4. Copy **Client ID** (under app name) and **Client Secret**

### OpenAI API

1. Go to https://platform.openai.com/api-keys
2. Click "Create new secret key"
3. Copy the key (starts with `sk-`)

### Binance API

1. Go to https://www.binance.com/en/support/faq/how-to-create-api-keys-on-binance-360002502072
2. Create API key (enable Spot trading for reading)
3. Use testnet for development: https://testnet.binance.vision/

## Hermes Agent Integration

See [HERMES_CONFIG.md](HERMES_CONFIG.md) for detailed Hermes configuration.

Quick setup:

```yaml
# In ~/.hermes/config.yaml
mcp_servers:
  psy_line:
    command: "python"
    args: ["-m", "psy_line.main"]
    env:
      REDDIT_CLIENT_ID: "your_client_id"
      REDDIT_CLIENT_SECRET: "your_client_secret"
      OPENAI_API_KEY: "sk-your-key"
      BINANCE_API_KEY: "your_key"
      BINANCE_SECRET_KEY: "your_secret"
    timeout: 120
    tools:
      include:
        - fetch_crypto_sentiment
        - analyze_sentiment
        - get_binance_price
        - generate_trading_signal
        - backtest_signal
        - run_sentiment_scan
```

Then in Hermes, run `/reload-mcp`.

## Usage

### As MCP Server (for Hermes)

Start the server:
```bash
python -m psy_line.main
```

Test MCP protocol:
```bash
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | python -m psy_line.main
```

### Programmatic Usage

```python
from psy_line.reddit_scraper import RedditScraper
from psy_line.sentiment_analyzer import SentimentAnalyzer
from psy_line.binance_client import BinanceClient
from psy_line.signal_generator import SignalGenerator
from psy_line.backtester import Backtester
from psy_line.config import Config

# Load config
config = Config.from_yaml("config.yaml")

# Initialize clients
scraper = RedditScraper(
    client_id=config.reddit.client_id,
    client_secret=config.reddit.client_secret,
    user_agent=config.reddit.user_agent,
)

analyzer = SentimentAnalyzer(api_key=config.openai.api_key)
binance = BinanceClient(api_key=config.binance.api_key, secret_key=config.binance.secret_key)
signal_gen = SignalGenerator()
backtester = Backtester()

# Fetch and analyze
comments = scraper.fetch_comments(["CryptoCurrency", "Bitcoin"], time_range="24h")
sentiments = analyzer.analyze_batch(comments)
composite = signal_gen.calculate_composite_sentiment(sentiments)

# Get price and generate signal
prices = binance.get_klines("BTCUSDT", "1h", limit=100)
current_price = binance.get_current_price("BTCUSDT")
momentum = signal_gen.calculate_momentum(prices)
signal = signal_gen.generate_signal(composite, momentum, "BTCUSDT")

# Backtest
result = backtester.backtest([signal], prices, [])

print(f"Signal: {signal.type.value}")
print(f"Composite Sentiment: {composite:.3f}")
print(f"Backtest PnL: {result.total_pnl:.2f}%")
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `get_fear_greed_index` | Get current Crypto Fear & Greed Index (free!) |
| `get_aggregated_sentiment` | Aggregate all sentiment sources |
| `fetch_reddit_rss` | Fetch Reddit posts via RSS (no API key) |
| `analyze_sentiment` | LLM sentiment analysis (optional) |
| `get_binance_price` | Get Binance price/kline data |
| `generate_trading_signal` | Generate BUY/SELL/HOLD signal |
| `backtest_signal` | Backtest against historical data |
| `run_sentiment_scan` | One-shot complete scan |

## Hermes Integration

```yaml
mcp_servers:
  psy_line:
    command: "python"
    args: ["-m", "psy_line.main"]
    timeout: 120
    tools:
      include:
        - get_fear_greed_index
        - get_aggregated_sentiment
        - fetch_reddit_rss
        - get_binance_price
        - generate_trading_signal
        - backtest_signal
        - run_sentiment_scan
```

## Signal Logic

```
Combined Score > +0.6  →  SELL (过度贪婪)
Combined Score < -0.6  →  BUY  (过度恐惧)
Otherwise               →  HOLD
```

**Combined Score Formula**:
```
Combined = (Social_Sentiment × 0.4) + (PSY_Sentiment × 0.3) + (Momentum × 0.3)
```

Where:
- **Social_Sentiment** (-1 to 1): Fear & Greed + aggregated social sentiment
- **PSY_Sentiment** (-1 to 1): Technical indicator from price data
  - PSY > 75 = Extreme Greed, PSY < 25 = Extreme Fear
- **Momentum** (-1 to 1): Recent price change rate

**PSY Indicator** (Psychological Line):
- Formula: `PSY = (up_days / total_days) × 100`
- >75: Extreme Greed (overbought)
- >50: Bullish
- <50: Bearish
- <25: Extreme Fear (oversold)

References:
- https://www.investchannels.com/psychological-line-indicator-trading-strategies-and-tips/
- arXiv: Sentiment + Technical analysis improves BTC prediction (2410.14532)

**Current Reading**: Fear & Greed = 27/100 (Fear) → BUY signal

## Disclaimer

**This software is for educational and research purposes only.**

- Signals are generated for backtesting/simulation, NOT for live trading
- Past performance does not guarantee future results
- Cryptocurrency trading involves substantial risk of loss
- Always do your own research before making investment decisions

## License

MIT
