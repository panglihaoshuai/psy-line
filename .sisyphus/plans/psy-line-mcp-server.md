# Plan: PSY_line MCP Server

## TL;DR
> **Summary**: 构建一个MCP Server，让Hermes Agent通过MCP协议调用，实现Reddit散户情绪监控、Binance价格数据获取、情绪信号生成与回测
> **Deliverables**: psy-line MCP Server (Python)、Hermes配置、完整工具集
> **Effort**: Large
> **Parallel**: YES - 3 waves
> **Critical Path**: Core Server → Tools → Backtester → Config

## Context
### Original Request
用户需要定时驱动Hermes Agent上网看Reddit，搜集散户在加密货币相关讨论区的评论，清洗去重统计情绪值，同时接入Binance获得市场价格，对标和量化散户心理带来的行为带来的价格涨跌，目标是在情绪高涨时卖出，情绪冰点时逐步买入。

### Interview Summary (confirmed)
| Item | Decision |
|------|----------|
| Agent框架 | Hermes (NousResearch, Python, GitHub) |
| 数据源 | r/CryptoCurrency, r/SatoshiBets, r/Bitcoin, r/ethereum, r/SOLMarkets, r/ethtrader |
| 情绪分析 | LLM API (OpenAI GPT-4o) |
| 价格数据 | Binance API |
| 信号输出 | 模拟盘/回测，不执行实盘 |
| 交易逻辑 | 情绪>0.6→SELL, 情绪<-0.6→BUY, 否则HOLD |

### Hermes Integration (researched)
- **官方文档**: https://hermes-agent.nousresearch.com
- **配置位置**: `~/.hermes/config.yaml`
- **传输方式**: stdio (本地子进程)
- **工具命名**: `mcp_<server>_<tool>` (如 `mcp_psyline_fetch_sentiment`)
- **MCP SDK**: Python `mcp` 包

## Work Objectives
### Core Objective
让Hermes Agent能够调用psy-line MCP Server，获得Reddit情绪信号用于模拟盘回测

### Deliverables
1. **psy-line MCP Server** - 可独立运行的Python MCP Server
2. **6个MCP工具** - Hermes可直接调用
3. **Hermes配置** - 添加到~/.hermes/config.yaml的mcp_servers条目
4. **配置文件** - config.yaml存放API密钥和参数
5. **回测引擎** - 基于历史数据的策略验证
6. **[O1] 历史情绪缓存** (可选) - SQLite/内存缓存
7. **[O2] Reddit关键词过滤** (可选) - 噪音过滤

### Definition of Done (verifiable conditions)
- [ ] `python -m psy_line` 可启动MCP Server (stdio模式)
- [ ] Hermes能通过`mcp_psyline_*`工具调用所有6个工具
- [ ] Reddit爬取返回去重后的评论列表
- [ ] LLM情绪分析返回-1~1的分值
- [ ] Binance价格数据实时获取
- [ ] 信号生成符合阈值逻辑
- [ ] 回测引擎输出pnl/max_drawdown/win_rate

### Must Have
- MCP Server基于官方Python `mcp`包构建
- 所有API密钥通过环境变量或config.yaml注入，不硬编码
- 工具超时和错误处理完善
- Reddit去重基于comment ID
- 批量LLM调用控制频率 (每分钟不超过20请求)

### Must NOT Have
- 实盘交易执行功能
- Reddit/Binance账号密码存储在代码中
- 单次超过50条评论的LLM批量分析
- 阻塞Hermes主线程的操作

### Optional Enhancements (非阻塞，可选实现)
- **[O1] 历史情绪缓存**: 使用SQLite或内存缓存存储历史情绪数据，供回测使用
  - 表结构: `(timestamp, subreddit, symbol, composite_sentiment, signal_type)`
  - 保留时间: 7天滚动
  - 实现位置: `src/psy_line/sentiment_cache.py`
- **[O2] Reddit搜索关键词过滤**: 增加关键词过滤减少噪音
  - 默认关键词: `bitcoin, btc, eth, ethereum, crypto, sol, doge`
  - 配置: `config.yaml` 中 `reddit.keywords` 列表
  - 实现位置: `reddit_scraper.py` fetch_comments方法

## Verification Strategy
- **Test decision**: tests-after (单测 + 集成测试)
- **Framework**: pytest
- **QA policy**: 每个工具函数有单测，MCP端到端测试
- **Evidence**: 测试输出截断到`.sisyphus/evidence/`

## Execution Strategy
### Parallel Execution Waves

**Wave 1 (Foundation - 可并行)**:
- T1: 项目结构 + 依赖 (pyproject.toml)
- T2: MCP Server骨架 (main.py)
- T3: 配置文件 (config.yaml)

**Wave 2 (Core Tools - 可并行)**:
- T4: Reddit Scraper (praw)
- T5: Binance Client (python-binance)
- T6: LLM Sentiment Analyzer

**Wave 3 (High-level Logic)**:
- T7: Signal Generator
- T8: Backtester
- T9: 聚合工具 run_sentiment_scan

**Wave 4 (Config + Docs)**:
- T10: Hermes配置 + README
- T11: 集成测试

### Dependency Matrix
```
T1 ─┬─→ T4 ─┐
    ├─→ T5 ─┼─→ T7 ─┬─→ T9 ─┐
    ├─→ T6 ─┘        ├─→ T8 ─┘
    └─→ T3 ──────────┴─→ T10 ─┬─→ T11
```

### Agent Dispatch Summary
| Wave | Tasks | Categories | Parallel |
|------|-------|------------|----------|
| 1 | T1,T2,T3 | build,build,build | YES |
| 2 | T4,T5,T6 | build,build,build | YES |
| 3 | T7,T8,T9 | build,build,build | T7/T8可并行 |
| 4 | T10,T11 | build,quick | NO |

## TODOs

---

- [ ] **T1. 项目结构初始化**

  **What to do**:
  1. 创建目录结构:
     ```
     psy_line/
     ├── src/
     │   └── psy_line/
     │       ├── __init__.py
     │       ├── main.py           # MCP Server入口
     │       ├── config.py         # 配置加载
     │       ├── reddit_scraper.py
     │       ├── sentiment_analyzer.py
     │       ├── binance_client.py
     │       ├── signal_generator.py
     │       ├── backtester.py
     │       └── types.py          # Pydantic类型定义
     ├── tests/
     ├── config.yaml
     ├── pyproject.toml
     └── README.md
  2. 创建pyproject.toml:
     - 依赖: mcp>=1.0.0, praw>=7.0.0, python-binance>=1.0.0, openai>=1.0.0, pydantic>=2.0.0, pyyaml>=6.0.0, pytest>=8.0.0, pytest-asyncio>=0.23.0
     - 构建: pyinstaller或直接python -m运行
     -入口: src/psy_line/main.py

  **Must NOT do**: 不写任何业务逻辑代码

  **Recommended Agent Profile**:
  - Category: `build`
  - Skills: []
  - Omitted: [] - 纯结构任务

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: T4,T5,T6,T7,T8,T9,T10,T11 | Blocked By: none

  **References**:
  - Pattern: 标准Python项目布局 (src layout)
  - MCP: https://github.com/NousResearch/hermes-agent (Hermes原生支持)
  - Config: ~/.hermes/config.yaml mcp_servers格式

  **Acceptance Criteria**:
  - [ ] `ls psy_line/` 看到完整目录结构
  - [ ] `cat psy_line/pyproject.toml` 包含所有依赖
  - [ ] `python -c "from psy_line import *"` 无报错

  **QA Scenarios**:
  ```
  Scenario: 项目结构验证
    Tool: Bash
    Steps: python -c "import psy_line; print('OK')"
    Expected: 输出OK，无ImportError
    Evidence: .sisyphus/evidence/t1-structure.{ext}

  Scenario: 依赖安装验证
    Tool: Bash
    Steps: cd psy_line && pip install -e . && python -c "import mcp, praw, binance, openai"
    Expected: 所有包可导入
    Evidence: .sisyphus/evidence/t1-deps.{ext}
  ```

  **Commit**: YES | Message: `feat: initialize psy-line project structure` | Files: [psy_line/pyproject.toml, psy_line/src/, psy_line/config.yaml]

---

- [ ] **T2. MCP Server骨架实现**

  **What to do**:
  1. 创建`src/psy_line/main.py`:
     ```python
     from mcp.server.fastmcp import FastMCP
     # 或标准MCP: from mcp.server import Server
     mcp = FastMCP("psy-line")
     
     @mcp.tool()
     def fetch_crypto_sentiment(...): ...
     
     if __name__ == "__main__":
         mcp.run(transport="stdio")
     ```
  2. 使用FastMCP或标准MCP Server v1.x API
  3. 所有工具先写stub返回空数据，验证MCP协议正常

  **Must NOT do**: 不实现任何业务逻辑，只验证MCP协议工作

  **Recommended Agent Profile**:
  - Category: `build`
  - Skills: []
  - Omitted: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: T4,T5,T6,T7,T8,T9 | Blocked By: none

  **References**:
  - MCP Python: https://github.com/modelcontextprotocol/typescript-sdk (Python版类似)
  - FastMCP: https://modelcontextprotocol.io/docs/python/server
  - Hermes stdio: ~/.hermes/config.yaml

  **Acceptance Criteria**:
  - [ ] `python -m psy_line.main` 启动后stdio输入`{"jsonrpc":"2.0","method":"tools/list","id":1}`返回工具列表
  - [ ] 工具名包含 `fetch_crypto_sentiment`, `analyze_sentiment`, `get_binance_price`, `generate_trading_signal`, `backtest_signal`, `run_sentiment_scan`

  **QA Scenarios**:
  ```
  Scenario: MCP协议握手验证
    Tool: Bash
    Steps: echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | python -m psy_line.main
    Expected: 返回包含6个工具的列表
    Evidence: .sisyphus/evidence/t2-mcp-handshake.{ext}
  ```

  **Commit**: YES | Message: `feat: add MCP server skeleton` | Files: [psy_line/src/psy_line/main.py]

---

- [ ] **T3. 配置文件系统**

  **What to do**:
  1. 创建`config.yaml`:
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
       testnet: true
     
     subreddits:
       - CryptoCurrency
       - SatoshiBets
       - Bitcoin
       - ethereum
       - SOLMarkets
       - ethtrader
     
     trading:
       symbol: "BTCUSDT"
       buy_threshold: -0.6
       sell_threshold: 0.6
       position_size: 0.1  # BTC
     ```
  2. 创建`src/psy_line/config.py`:
     - 使用pydantic-settings或直接pyyaml+pydantic
     - 环境变量优先，config.yaml次之
     - 验证必填字段

  **Must NOT do**: 不在代码中硬编码任何API密钥

  **Recommended Agent Profile**:
  - Category: `build`
  - Skills: []
  - Omitted: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: T4,T5,T6,T7,T8,T9 | Blocked By: none

  **References**:
  - Pydantic: 配置验证标准库
  - Reddit API: https://www.reddit.com/prefs/apps
  - Binance: https://www.binance.com/en/support/faq/how-to-create-api-keys-on-binance-360002502072

  **Acceptance Criteria**:
  - [ ] `python -c "from psy_line.config import Config; c = Config.from_yaml('config.yaml')"` 无报错
  - [ ] 缺少环境变量时抛出明确错误信息

  **QA Scenarios**:
  ```
  Scenario: 配置加载测试
    Tool: Bash
    Steps: python -c "from psy_line.config import Config; print(Config.from_yaml('config.yaml').reddit.user_agent)"
    Expected: 输出 "PSY_line/1.0 (Trading Bot)"
    Evidence: .sisyphus/evidence/t3-config.{ext}
  ```

  **Commit**: YES | Message: `feat: add configuration system` | Files: [psy_line/config.yaml, psy_line/src/psy_line/config.py]

---

- [ ] **T4. Reddit Scraper实现**

  **What to do**:
  1. 创建`src/psy_line/reddit_scraper.py`:
     ```python
     import praw
     from praw.models import Comment, Submission
     from typing import List
     
     class RedditScraper:
         def __init__(self, client_id, client_secret, user_agent):
             self.reddit = praw.Reddit(
                 client_id=client_id,
                 client_secret=client_secret,
                 user_agent=user_agent
             )
         
         def fetch_comments(self, subreddits: List[str], 
                           time_range: str = "24h", 
                           limit: int = 100) -> List[dict]:
             # 1. 遍历subreddits获取posts
             # 2. 获取每个post的top comments
             # 3. 去重(基于comment.id)
             # 4. 返回清洗后的评论列表
             pass
     ```
  2. 清洗规则:
     - 去除HTML标签 (regex: `<.*?>`)
     - 去除特殊字符只保留中文/英文/数字/常见标点
     - 去重: `seen_ids = set()`, 按ID去重
     - 过滤: 移除已删除评论 `[deleted]`, `[removed]`
  3. 返回格式:
     ```python
     {
       "id": "t1_abc123",
       "body": "清洗后的评论文本",
       "subreddit": "CryptoCurrency", 
       "score": 42,
       "created_utc": 1715000000,
       "permalink": "https://reddit.com/..."
     }
     ```

  **Must NOT do**: 不存储任何数据到磁盘，只返回内存中的列表

  **Recommended Agent Profile**:
  - Category: `build`
  - Skills: []
  - Omitted: []

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: T9 | Blocked By: T1

  **References**:
  - PRAW: https://praw.readthedocs.io/en/stable/
  - Reddit API Rate Limits: 60 requests/minute for authenticated

  **Acceptance Criteria**:
  - [ ] `scraper = RedditScraper(...); comments = scraper.fetch_comments(['CryptoCurrency'])` 返回去重列表
  - [ ] 每条评论包含id, body, subreddit, score, created_utc
  - [ ] 重复ID的评论被正确去重

  **QA Scenarios**:
  ```
  Scenario: Reddit爬取测试 (mock)
    Tool: Bash
    Steps: python -c "from psy_line.reddit_scraper import RedditScraper; ..."
    Expected: 返回mock数据列表，无报错
    Evidence: .sisyphus/evidence/t4-reddit.{ext}
  
  Scenario: 去重验证
    Tool: Bash
    Steps: python -c "from psy_line.reddit_scraper import RedditScraper; c = scraper.fetch_comments(['CryptoCurrency']); ids = [x['id'] for x in c]; print(len(ids) == len(set(ids)))"
    Expected: True
    Evidence: .sisyphus/evidence/t4-dedup.{ext}
  ```

  **Commit**: YES | Message: `feat: add Reddit scraper with deduplication` | Files: [psy_line/src/psy_line/reddit_scraper.py]

---

- [ ] **T5. Binance Client实现**

  **What to do**:
  1. 创建`src/psy_line/binance_client.py`:
     ```python
     from binance.client import Client
     from typing import List, Optional
     
     class BinanceClient:
         def __init__(self, api_key: str, secret_key: str, testnet: bool = True):
             if testnet:
                 self.client = Client(api_key, secret_key, testnet=True)
                 # 配置testnet API URL
             else:
                 self.client = Client(api_key, secret_key)
         
         def get_klines(self, symbol: str, interval: str, limit: int = 100) -> List[dict]:
             # 返回K线数据
             # interval: '1m', '5m', '1h', '1d'
             # 返回: [{"open_time": ..., "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}]
             pass
         
         def get_current_price(self, symbol: str) -> float:
             pass
         
         def get_24hr_stats(self, symbol: str) -> dict:
             # 返回24hr价格统计
             pass
     ```
  2. 缓存: 使用简单dict缓存价格数据，5秒TTL避免频繁调用

  **Must NOT do**: 不执行任何交易下单，只读取数据

  **Recommended Agent Profile**:
  - Category: `build`
  - Skills: []
  - Omitted: []

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: T7,T9 | Blocked By: T1

  **References**:
  - python-binance: https://python-binance.readthedocs.io/en/latest/
  - Binance Testnet: https://testnet.binance.vision/

  **Acceptance Criteria**:
  - [ ] `client.get_current_price("BTCUSDT")` 返回浮点数
  - [ ] `client.get_klines("BTCUSDT", "1h", limit=100)` 返回100条K线
  - [ ] 缓存机制工作正常

  **QA Scenarios**:
  ```
  Scenario: Binance价格获取 (mock)
    Tool: Bash
    Steps: python -c "from psy_line.binance_client import BinanceClient; c = BinanceClient('k', 's', testnet=True); print(type(c.get_current_price('BTCUSDT')))"
    Expected: <class 'float'>
    Evidence: .sisyphus/evidence/t5-binance.{ext}
  ```

  **Commit**: YES | Message: `feat: add Binance client for price data` | Files: [psy_line/src/psy_line/binance_client.py]

---

- [ ] **T6. LLM Sentiment Analyzer实现**

  **What to do**:
  1. 创建`src/psy_line/sentiment_analyzer.py`:
     ```python
     from openai import OpenAI
     from typing import List
     import time
     
     class SentimentAnalyzer:
         SYSTEM_PROMPT = """你是一个加密货币情绪分析师。
         分析每条评论的情绪，判断散户是看涨(bullish)、看跌(bearish)还是中立(neutral)。
         返回格式: {"sentiment": "bullish|bearish|neutral", "score": -1.0到1.0, "reasoning": "简要理由"}"""
         
         def __init__(self, api_key: str, model: str = "gpt-4o", 
                      batch_size: int = 30, max_rpm: int = 20):
             self.client = OpenAI(api_key=api_key)
             self.model = model
             self.batch_size = batch_size
             self.max_rpm = max_rpm
             self.request_timestamps = []
         
         def analyze_batch(self, comments: List[dict]) -> List[dict]:
             # 1. 分批处理 (每批batch_size条)
             # 2. 构造prompt: 包含所有评论文本
             # 3. 调用LLM
             # 4. 解析响应JSON
             # 5. 控制请求频率 (max_rpm)
             pass
         
         def analyze_single(self, comment: dict) -> dict:
             # 单条评论分析
             pass
     ```
  2. 批量提示词设计:
     ```
     分析以下加密货币评论的情绪，返回JSON数组:
     [
       {"id": "t1_abc", "text": "内容1"},
       {"id": "t1_def", "text": "内容2"}
     ]
     对每条评论，判断:
     - sentiment: bullish(看涨)/bearish(看跌)/neutral(中立)
     - score: -1.0(极度看跌)到1.0(极度看涨)
     - reasoning: 20字以内的理由
     ```
  3. 错误处理: LLM返回格式错误时，该条评论标记为neutral/score=0

  **Must NOT do**: 不缓存LLM响应，不存储评论数据

  **Recommended Agent Profile**:
  - Category: `build`
  - Skills: []
  - Omitted: []

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: T9 | Blocked By: T1

  **References**:
  - OpenAI API: https://platform.openai.com/docs/api-reference
  - Batch processing: 控制batch_size避免token超限

  **Acceptance Criteria**:
  - [ ] `analyzer.analyze_batch([{"id": "1", "body": "Bitcoin to the moon!"}])` 返回包含sentiment/score/reasoning的dict
  - [ ] score范围在-1.0到1.0之间
  - [ ] 超过batch_size时分批处理

  **QA Scenarios**:
  ```
  Scenario: 情绪分析测试 (mock)
    Tool: Bash
    Steps: python -c "from psy_line.sentiment_analyzer import SentimentAnalyzer; ..."
    Expected: 返回格式正确的情绪数据
    Evidence: .sisyphus/evidence/t6-sentiment.{ext}
  ```

  **Commit**: YES | Message: `feat: add LLM-based sentiment analyzer` | Files: [psy_line/src/psy_line/sentiment_analyzer.py]

---

- [ ] **T7. Signal Generator实现**

  **What to do**:
  1. 创建`src/psy_line/signal_generator.py`:
     ```python
     from typing import Literal
     from datetime import datetime
     
     class SignalGenerator:
         def __init__(self, buy_threshold: float = -0.6, 
                      sell_threshold: float = 0.6):
             self.buy_threshold = buy_threshold
             self.sell_threshold = sell_threshold
         
         def calculate_composite_sentiment(self, sentiment_results: List[dict]) -> float:
             # 加权平均: 近期评论权重更高
             # score * time_decay_weight
             # 返回-1到1之间的复合情绪值
             pass
         
         def calculate_momentum(self, price_data: List[dict]) -> float:
             # 计算N小时内价格变化率
             # (当前价格 - N小时前价格) / N小时前价格
             pass
         
         def generate_signal(self, composite_sentiment: float, 
                            momentum: float, 
                            symbol: str) -> dict:
             # 信号生成逻辑:
             # sentiment > sell_threshold → SELL
             # sentiment < buy_threshold → BUY
             # else → HOLD
             # strength = abs(sentiment) * abs(momentum)  (动量放大信号)
             pass
     ```
  2. 核心策略:
     - 复合情绪 = Σ(score_i * weight_i) / Σ(weight_i)
     - weight_i = exp(-lambda * age_hours), lambda=0.1
     - 信号强度 = |复合情绪| * |动量因子|
     - BUY/SELL强度分1-5级

  **Must NOT do**: 不执行交易，只生成信号

  **Recommended Agent Profile**:
  - Category: `build`
  - Skills: []
  - Omitted: []

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: T9 | Blocked By: T4,T5,T6

  **References**:
  - Signal processing: 时间衰减加权平均
  - Momentum: 技术分析标准动量指标

  **Acceptance Criteria**:
  - [ ] composite_sentiment在-1到1之间
  - [ ] 情绪>0.6返回SELL信号
  - [ ] 情绪<-0.6返回BUY信号
  - [ ] 返回包含type/strength/reasoning/timestamp的dict

  **QA Scenarios**:
  ```
  Scenario: 信号生成边界测试
    Tool: Bash
    Steps: |
      sg = SignalGenerator()
      print(sg.generate_signal(0.7, 0.05, "BTCUSDT"))  # 应SELL
      print(sg.generate_signal(-0.7, -0.05, "BTCUSDT"))  # 应BUY
      print(sg.generate_signal(0.0, 0.0, "BTCUSDT"))  # 应HOLD
    Expected: 分别是SELL/BUY/HOLD
    Evidence: .sisyphus/evidence/t7-signal.{ext}
  ```

  **Commit**: YES | Message: `feat: add trading signal generator` | Files: [psy_line/src/psy_line/signal_generator.py]

---

- [ ] **T8. Backtester实现**

  **What to do**:
  1. 创建`src/psy_line/backtester.py`:
     ```python
     from typing import List, Dict
     from dataclasses import dataclass
     
     @dataclass
     class BacktestResult:
         total_pnl: float          # 总收益率
         max_drawdown: float       # 最大回撤
         win_rate: float           # 胜率
         sharpe_ratio: float       # 夏普比率
         num_trades: int           # 交易次数
         trades: List[dict]        # 交易明细
     
     class Backtester:
         def __init__(self, initial_balance: float = 10000.0):
             self.initial_balance = initial_balance
         
         def backtest(self, signals: List[dict], 
                     historical_prices: List[dict],
                     sentiment_history: List[dict]) -> BacktestResult:
             # 模拟交易逻辑:
             # - 收到BUY信号 → 买入 (用下一根K线开盘价)
             # - 收到SELL信号 → 卖出 (用下一根K线开盘价)
             # - 记录每笔交易的盈亏
             # 计算: pnl, max_drawdown, win_rate, sharpe_ratio
             pass
         
         def _calculate_metrics(self, trades: List[dict]) -> BacktestResult:
             pass
     ```
  2. 交易模拟:
     - 初始资金 $10,000
     - 每次全仓买入BTC
     - BUY信号: 卖出USDT全部换成BTC
     - SELL信号: 卖出全部BTC换回USDT
     - 计算持有期间的法币收益

  **Must NOT do**: 不连接真实交易账户

  **Recommended Agent Profile**:
  - Category: `build`
  - Skills: []
  - Omitted: []

  **Parallelization**: Can Parallel: YES (with T7) | Wave 3 | Blocks: none | Blocked By: T7 (可并行)

  **References**:
  - Backtesting: 经典量化回测框架
  - Sharpe Ratio: (平均收益 - 无风险利率) / 收益标准差

  **Acceptance Criteria**:
  - [ ] `backtester.backtest(signals, prices, sentiments)` 返回BacktestResult
  - [ ] total_pnl, max_drawdown, win_rate, sharpe_ratio都是有效浮点数
  - [ ] num_trades正确计数

  **QA Scenarios**:
  ```
  Scenario: 回测引擎测试 (mock数据)
    Tool: Bash
    Steps: python -c "from psy_line.backtester import Backtester; ..."
    Expected: 返回有效的BacktestResult
    Evidence: .sisyphus/evidence/t8-backtest.{ext}
  ```

  **Commit**: YES | Message: `feat: add backtesting engine` | Files: [psy_line/src/psy_line/backtester.py]

---

- [ ] **T9. 聚合工具 run_sentiment_scan实现**

  **What to do**:
  1. 在`main.py`添加`run_sentiment_scan`工具:
     ```python
     @mcp.tool()
     def run_sentiment_scan(
         subreddits: List[str] = ["CryptoCurrency", "SatoshiBets", "Bitcoin", "ethereum"],
         symbol: str = "BTCUSDT",
         time_range: str = "24h",
         limit: int = 100
     ) -> dict:
         """
         一站式情绪扫描: 爬取Reddit → 情绪分析 → 获取价格 → 生成信号 → 回测
         """
         # 1. 爬取Reddit评论
         comments = reddit_scraper.fetch_comments(subreddits, time_range, limit)
         
         # 2. 批量情绪分析
         sentiments = sentiment_analyzer.analyze_batch(comments)
         
         # 3. 获取Binance价格
         prices = binance_client.get_klines(symbol, "1h", limit=100)
         current_price = binance_client.get_current_price(symbol)
         
         # 4. 生成信号
         composite = signal_generator.calculate_composite_sentiment(sentiments)
         momentum = signal_generator.calculate_momentum(prices)
         signal = signal_generator.generate_signal(composite, momentum, symbol)
         
         # 5. 回测
         historical_sentiments = get_historical_sentiments()  # 从缓存或历史数据
         backtest_result = backtester.backtest([signal], prices, historical_sentiments)
         
         return {
             "scan_time": datetime.now().isoformat(),
             "symbol": symbol,
             "comments_analyzed": len(comments),
             "composite_sentiment": composite,
             "current_price": current_price,
             "signal": signal,
             "backtest": backtest_result,
             "top_bullish_comments": get_top(sentiments, 3, "bullish"),
             "top_bearish_comments": get_top(sentiments, 3, "bearish")
         }
     ```
  2. 需要实现辅助函数`get_historical_sentiments`: 从过去N小时的扫描中构建简易历史

  **Must NOT do**: 不保存数据到数据库，只保留内存缓存

  **Recommended Agent Profile**:
  - Category: `build`
  - Skills: []
  - Omitted: []

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: none | Blocked By: T4,T5,T6,T7,T8

  **References**:
  - Hermes Tool: 使用@mcp.tool()装饰器

  **Acceptance Criteria**:
  - [ ] `run_sentiment_scan()` 返回完整扫描结果
  - [ ] 包含signal的type (BUY/SELL/HOLD)
  - [ ] 包含top_bullish/bearish评论示例

  **QA Scenarios**:
  ```
  Scenario: 聚合扫描测试
    Tool: Bash
    Steps: python -c "from psy_line.main import mcp; result = mcp.tools['run_sentiment_scan']._callback(...)"
    Expected: 返回完整结果字典
    Evidence: .sisyphus/evidence/t9-scan.{ext}
  ```

  **Commit**: YES | Message: `feat: add aggregated run_sentiment_scan tool` | Files: [psy_line/src/psy_line/main.py]

---

- [ ] **T10. Hermes配置 + 文档**

  **What to do**:
  1. 创建`HERMES_CONFIG.md`:
     ```markdown
     # Hermes MCP Server配置
     
     ## 安装psy-line
     ```bash
     cd /path/to/psy_line
     pip install -e .
     ```
     
     ## 配置Hermes
     编辑 `~/.hermes/config.yaml`:
     
     ```yaml
     mcp_servers:
       psyline:
         command: "python"
         args: ["-m", "psy_line.main"]
         env:
           REDDIT_CLIENT_ID: "your_reddit_client_id"
           REDDIT_CLIENT_SECRET: "your_reddit_client_secret"
           OPENAI_API_KEY: "sk-..."
           BINANCE_API_KEY: "your_binance_api_key"
           BINANCE_SECRET_KEY: "your_binance_secret_key"
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
     
     ## 重载MCP
     在Hermes中运行 `/reload-mcp`
     
     ## 验证
     询问Hermes: "你有mcp_psyline开头的工具吗?"
     ```
  2. 更新`README.md`:
     - 项目介绍
     - 安装步骤
     - API密钥获取说明 (Reddit, OpenAI, Binance)
     - 工具使用示例
     - 测试网说明

  **Must NOT do**: 不在文档中包含任何实际的API密钥

  **Recommended Agent Profile**:
  - Category: `build`
  - Skills: []
  - Omitted: []

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: none | Blocked By: T1,T2,T3,T4,T5,T6,T7,T8,T9

  **References**:
  - Hermes docs: https://hermes-agent.nousresearch.com/docs/guides/use-mcp-with-hermes

  **Acceptance Criteria**:
  - [ ] README.md包含完整安装步骤
  - [ ] Hermes配置示例可复制使用
  - [ ] 不包含任何真实密钥

  **QA Scenarios**:
  ```
  Scenario: 文档完整性检查
    Tool: Bash
    Steps: grep -c "your_reddit_client_id\|OPENAI_API_KEY\|BINANCE_API_KEY" README.md HERMES_CONFIG.md
    Expected: 0 (不应包含真实密钥示例)
    Evidence: .sisyphus/evidence/t10-docs.{ext}
  ```

  **Commit**: YES | Message: `docs: add Hermes integration guide` | Files: [psy_line/README.md, psy_line/HERMES_CONFIG.md]

---

- [ ] **T11. 集成测试**

  **What to do**:
  1. 创建`tests/test_integration.py`:
     - 测试完整流程 (mock所有外部API)
     - 测试MCP协议通信
     - 测试信号生成逻辑
     - 测试错误处理
  2. 创建`tests/test_mcp_protocol.py`:
     - 测试tools/list返回正确工具
     - 测试tool call调用正确函数
     - 测试error返回格式

  **Must NOT do**: 不使用真实API密钥

  **Recommended Agent Profile**:
  - Category: `quick`
  - Skills: []
  - Omitted: []

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: none | Blocked By: T1,T2,T3,T4,T5,T6,T7,T8,T9,T10

  **References**:
  - pytest: 标准Python测试框架
  - pytest-asyncio: 异步测试支持

  **Acceptance Criteria**:
  - [ ] `pytest tests/` 全部通过
  - [ ] 所有单测覆盖主要函数

  **QA Scenarios**:
  ```
  Scenario: 集成测试运行
    Tool: Bash
    Steps: cd psy_line && pytest tests/ -v
    Expected: 所有测试PASSED
    Evidence: .sisyphus/evidence/t11-integration.{ext}
  ```

  **Commit**: YES | Message: `test: add integration tests` | Files: [psy_line/tests/]

---

- [ ] **O1. 历史情绪缓存 (Optional)**

  **What to do**:
  1. 创建`src/psy_line/sentiment_cache.py`:
     ```python
     from typing import Optional, List
     from dataclasses import dataclass
     from datetime import datetime, timedelta
     import sqlite3
     
     @dataclass
     class SentimentRecord:
         timestamp: datetime
         subreddit: str
         symbol: str
         composite_sentiment: float
         signal_type: str  # BUY/SELL/HOLD
     
     class SentimentCache:
         def __init__(self, db_path: str = "sentiment_cache.db"):
             self.db_path = db_path
             self._init_db()
         
         def _init_db(self):
             # 创建表: sentiment_history(timestamp, subreddit, symbol, sentiment, signal)
             # 索引: timestamp, symbol
             pass
         
         def save(self, record: SentimentRecord):
             # 插入记录
             pass
         
         def get_recent(self, symbol: str, hours: int = 24) -> List[SentimentRecord]:
             # 查询最近N小时的记录
             pass
         
         def cleanup(self, days: int = 7):
             # 删除7天前的旧数据
             pass
     ```
  2. 修改`run_sentiment_scan`: 每次扫描后自动保存到缓存
  3. 修改`backtest_signal`: 从缓存获取历史情绪数据

  **Must NOT do**: 不在核心流程中强制依赖缓存，缓存失败应降级

  **Recommended Agent Profile**:
  - Category: `build`
  - Skills: []
  - Omitted: []

  **Parallelization**: Can Parallel: YES | Wave: N/A | Blocks: none | Blocked By: T9

  **References**:
  - SQLite: Python标准库`sqlite3`

  **Acceptance Criteria**:
  - [ ] `cache.save(record)` 成功写入
  - [ ] `cache.get_recent("BTCUSDT", 24)` 返回过去24小时记录
  - [ ] `cache.cleanup()` 删除7天前数据

  **QA Scenarios**:
  ```
  Scenario: 缓存读写测试
    Tool: Bash
    Steps: python -c "from psy_line.sentiment_cache import SentimentCache; c = SentimentCache(); c.save(...); print(c.get_recent('BTCUSDT', 1))"
    Expected: 返回非空列表
    Evidence: .sisyphus/evidence/o1-cache.{ext}
  ```

  **Commit**: YES | Message: `feat(optional): add sentiment history cache` | Files: [psy_line/src/psy_line/sentiment_cache.py]

---

- [ ] **O2. Reddit关键词过滤 (Optional)**

  **What to do**:
  1. 修改`config.yaml`:
     ```yaml
     reddit:
       # ... existing config ...
       keywords:
         - bitcoin
         - btc
         - eth
         - ethereum
         - crypto
         - sol
         - solana
         - doge
         - dogecoin
       keywords_mode: "include"  # or "exclude"
     ```
  2. 修改`reddit_scraper.py` `fetch_comments`方法:
     ```python
     def fetch_comments(self, subreddits: List[str], 
                       time_range: str = "24h", 
                       limit: int = 100,
                       keywords: List[str] = None,
                       keywords_mode: str = "include") -> List[dict]:
         # 获取评论后:
         # include模式: 只保留包含任一关键词的评论
         # exclude模式: 排除包含任一关键词的评论
         filtered = []
         for comment in comments:
             text = comment["body"].lower()
             if keywords_mode == "include":
                 if any(kw.lower() in text for kw in keywords):
                     filtered.append(comment)
             else:  # exclude
                 if not any(kw.lower() in text for kw in keywords):
                     filtered.append(comment)
         return filtered
     ```
  3. 更新MCP工具`fetch_crypto_sentiment`的参数: 增加`keywords`和`keywords_mode`

  **Must NOT do**: 不设置默认关键词，关键词列表可为空(不过滤)

  **Recommended Agent Profile**:
  - Category: `build`
  - Skills: []
  - Omitted: []

  **Parallelization**: Can Parallel: YES | Wave: N/A | Blocks: none | Blocked By: T4

  **References**:
  - PRAW: 支持搜索API `subreddit.search()`

  **Acceptance Criteria**:
  - [ ] `keywords=["bitcoin"]` 只返回包含"bitcoin"的评论
  - [ ] 空关键词列表不过滤任何评论
  - [ ] `keywords_mode="exclude"` 正确排除

  **QA Scenarios**:
  ```
  Scenario: 关键词过滤测试
    Tool: Bash
    Steps: python -c "from psy_line.reddit_scraper import RedditScraper; c = scraper.fetch_comments(['CryptoCurrency'], keywords=['bitcoin']); print(all('bitcoin' in x['body'].lower() for x in c))"
    Expected: True (或空列表如果没匹配)
    Evidence: .sisyphus/evidence/o2-filter.{ext}
  ```

  **Commit**: YES | Message: `feat(optional): add Reddit keyword filtering` | Files: [psy_line/src/psy_line/reddit_scraper.py, psy_line/config.yaml]

---

## Final Verification Wave (MANDATORY)
> 4 review agents run in PARALLEL. ALL must APPROVE.

- [ ] **F1. Plan Compliance Audit** — oracle
  - 验证: 所有T1-T11任务覆盖原需求
  - 验证: 没有遗漏MCP工具
  - 验证: Hermes集成方式正确
- [ ] **F2. Code Quality Review** — unspecified-high
  - 验证: 类型提示完整
  - 验证: 错误处理完善
  - 验证: 无硬编码密钥
- [ ] **F3. API Contract Review** — unspecified-high
  - 验证: MCP工具参数/返回值符合规范
  - 验证: Binance/Reddit/OpenAI API调用正确
- [ ] **F4. Scope Fidelity Check** — deep
  - 验证: 不包含实盘交易
  - 验证: 不保存数据到磁盘
  - 验证: 没有超出原需求范围

## Commit Strategy
- 分阶段提交 (每wave完成时)
- Message格式: `feat: ...`, `docs: ...`, `test: ...`
- 不在早期commit中包含未完成的功能

## Success Criteria
1. Hermes Agent能成功调用所有6个`mcp_psyline_*`工具
2. `run_sentiment_scan`返回完整情绪信号报告
3. 回测引擎输出有效的统计指标
4. 所有测试通过
5. 文档完整可操作
