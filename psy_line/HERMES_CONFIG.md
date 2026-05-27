# Hermes Agent MCP Server Configuration

## Overview

This document explains how to configure the **psy-line** MCP server with Hermes Agent.

## Prerequisites

Before configuring, ensure you have:

1. **Hermes Agent** installed (https://github.com/NousResearch/hermes-agent)
2. **API Keys**:
   - Reddit API: https://www.reddit.com/prefs/apps
   - OpenAI API: https://platform.openai.com/api-keys
   - Binance API: https://www.binance.com/en/support/faq/how-to-create-api-keys-on-binance-360002502072

## Installation

```bash
# Navigate to psy_line directory
cd /path/to/psy_line

# Install psy_line in development mode
pip install -e .

# Or install dependencies only
pip install mcp>=1.0.0 praw>=7.0.0 python-binance>=1.0.0 openai>=1.0.0 pydantic>=2.0.0 pyyaml>=6.0.0
```

## Hermes Configuration

### Step 1: Configure `~/.hermes/config.yaml`

Add `psy_line` to the `mcp_servers` section:

```yaml
mcp_servers:
  # ... existing servers (github, filesystem, etc.) ...

  psy_line:
    command: "python"
    args: ["-m", "psy_line.main"]
    env:
      REDDIT_CLIENT_ID: "your_reddit_client_id"
      REDDIT_CLIENT_SECRET: "your_reddit_client_secret"
      OPENAI_API_KEY: "sk-your-openai-api-key"
      BINANCE_API_KEY: "your_binance_api_key"
      BINANCE_SECRET_KEY: "your_binance_secret_key"
      PSY_LINE_CONFIG: "config.yaml"  # Path to config.yaml
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

### Step 2: Reload MCP

In a Hermes chat session, run:

```
/reload-mcp
```

### Step 3: Verify

Ask Hermes:

```
What MCP tools do you have available? Look for mcp_psyline_* tools.
```

## Available Tools

All tools follow the naming convention: `mcp_psyline_<tool_name>`

| Tool | Description |
|------|-------------|
| `fetch_crypto_sentiment` | Fetch Reddit comments from crypto subreddits |
| `analyze_sentiment` | Analyze comment sentiment using LLM |
| `get_binance_price` | Get Binance price/kline data |
| `generate_trading_signal` | Generate BUY/SELL/HOLD signal |
| `backtest_signal` | Backtest signal against historical prices |
| `run_sentiment_scan` | **One-shot**: Full pipeline scan |

## Example Usage

### Quick Sentiment Scan

```
Run a complete sentiment scan on r/CryptoCurrency and r/Bitcoin for BTCUSDT
```

### Get Trading Signal

```
Analyze sentiment from the last 24 hours on crypto subreddits and generate a trading signal for BTCUSDT
```

### Backtest a Signal

```
Backtest a BUY signal with 24 hours of BTCUSDT price data
```

## Troubleshooting

### MCP Server Not Loading

1. Check Hermes logs: `hermes logs`
2. Verify Python can import: `python -c "import psy_line; print('OK')"`
3. Test MCP server manually:
   ```bash
   echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | python -m psy_line.main
   ```

### Rate Limiting

- Reddit: 60 requests/minute
- OpenAI: 20 requests/minute (configurable in config.yaml)
- Binance: 1200 requests/minute

### Testnet Mode

Binance is configured to use testnet by default. To use live trading:

```yaml
binance:
  testnet: false  # Set to false for production
```

## Security Notes

- Never commit API keys to version control
- Use environment variables for production deployments
- Consider using a secrets manager
- The MCP server runs as a subprocess with filtered environment
