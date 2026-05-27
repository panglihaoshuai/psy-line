# Plan: PSY_line 架构重构

## TL;DR
> **Summary**: 将当前"孤立数据源加权平均"架构重构为"行为模型为核心决策层"架构，集成MiniMax TokenPlan MCP实现持续网络搜索和LLM情绪分析，所有数据源统一输入行为模型，由行为模型输出阶段判断驱动信号生成
> **Deliverables**: 重构后的数据层、行为模型层、信号生成层、MCP工具层、MiniMax集成、配额管理器、持续监控循环
> **Effort**: Large
> **Parallel**: YES - 5 waves
> **Critical Path**: 配额管理 → MiniMax集成 → 数据源统一 → 行为模型重构 → 信号生成重构 → MCP工具更新
> **配额约束**: LLM 1500次/5小时，搜索 150次/小时

## Context

### 当前架构问题（审查发现）

```
┌─────────────────────────────────────────────────────────┐
│                    当前架构（错误）                       │
│                                                         │
│  Fear&Greed ──→ weighted avg ──┐                        │
│  Reddit计数 ──→ weighted avg ──┤                        │
│  GoogleTrends → weighted avg ──┼→ combined_score        │
│  TradingView ─→ weighted avg ──┤   → BUY/SELL/HOLD      │
│  Binance价格 ─→ PSY+动量 ──────┘                        │
│                                                         │
│  RetailBehaviorModel ← 只看K线（孤立）                   │
│  SentimentAnalyzer ← 从未被调用（孤立）                  │
└─────────────────────────────────────────────────────────┘
```

### 目标架构

```
┌─────────────────────────────────────────────────────────┐
│                    目标架构（正确）                       │
│                                                         │
│  ┌───────────────────────────────────────────┐          │
│  │          数据获取层 (多源)                   │          │
│  │                                           │          │
│  │  静态API:                                  │          │
│  │  • Fear&Greed Index (alternative.me)       │          │
│  │  • Binance OHLCV (官方API)                 │          │
│  │  • Reddit RSS (feedparser)                 │          │
│  │                                           │          │
│  │  动态搜索 (MiniMax TokenPlan MCP):          │          │
│  │  • web_search → Reddit热搜/讨论            │          │
│  │  • web_search → Google Trends替代           │          │
│  │  • 150次/小时配额管理                       │          │
│  │                                           │          │
│  │  LLM分析 (MiniMax 2.7):                    │          │
│  │  • Reddit帖子情绪分析                       │          │
│  │  • 行为叙述生成                             │          │
│  │  • 1500次/5小时配额管理                     │          │
│  │                                           │          │
│  │  → MarketState (统一数据结构)              │          │
│  └──────────────────┬────────────────────────┘          │
│                     │                                   │
│  ┌──────────────────▼────────────────────────┐          │
│  │          配额管理器 (RateLimiter)           │          │
│  │  • LLM请求: 1500次/5小时 → 智能batching     │          │
│  │  • 搜索请求: 150次/小时 → 频率控制          │          │
│  │  • 优先级: 行为判断 > 情绪分析 > 搜索        │          │
│  └──────────────────┬────────────────────────┘          │
│                     │                                   │
│  ┌──────────────────▼────────────────────────┐          │
│  │          BehaviorModel (核心决策层)         │          │
│  │  输入: MarketState (所有数据)               │          │
│  │  输出: BehaviorPhase + confidence           │          │
│  │  判断: FOMO/恐慌/割肉/怀疑/均衡/极度FOMO     │          │
│  └──────────────────┬────────────────────────┘          │
│                     │                                   │
│  ┌──────────────────▼────────────────────────┐          │
│  │          SignalGenerator                   │          │
│  │  输入: BehaviorPhase + MarketState          │          │
│  │  输出: BUY/SELL/HOLD + reasoning            │          │
│  └───────────────────────────────────────────┘          │
│                                                         │
│  ┌───────────────────────────────────────────┐          │
│  │          持续监控循环 (可选)                 │          │
│  │  • 定时触发 (每5-15分钟)                    │          │
│  │  • 智能触发 (价格异动时)                     │          │
│  │  • 配额感知 (剩余额度不足时降级)             │          │
│  └───────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────┘
```

### 审查发现汇总

| 模块 | 状态 | 问题 |
|------|------|------|
| `fear_greed.py` | ✅ 可用 | 无大问题，可复用 |
| `reddit_rss.py` | ⚠️ 部分可用 | 只获取帖子，不做情绪分析 |
| `sentiment_analyzer.py` | ❌ 未使用 | LLM分析器存在但从未被调用 |
| `google_trends.py` | ⚠️ 部分可用 | 代理已修复，但数据未进入行为模型 |
| `tradingview_client.py` | ⚠️ 存疑 | cryptocurrency.cv API可能已失效 |
| `binance_client.py` | ✅ 可用 | 无大问题 |
| `sentiment_aggregator.py` | ❌ 需重构 | Reddit只计数不做情绪分析，加权逻辑不合理 |
| `signal_generator.py` | ❌ 需重构 | 加权平均无意义，行为模型未充分利用数据 |
| `retail_behavior.py` | ⚠️ 需扩展 | 只看K线，不看社会情绪 |
| `backtester.py` | ⚠️ 有bug | 信号与时间不匹配，用第一个信号对所有K线 |
| `main.py` | ⚠️ 需更新 | MCP工具不展示行为阶段 |
| `test_integration.py` | ⚠️ 不足 | 无行为模型测试，无聚合层测试 |

### 新增能力：MiniMax TokenPlan MCP

用户拥有 MiniMax 2.7 订阅，提供以下能力：

| 能力 | 基础配额 | 用途 |
|------|---------|------|
| **LLM 请求** | 1500次/5小时 (滚动窗口) | Reddit情绪分析、行为叙述生成 |
| **网络搜索** | 150次/小时 (TokenPlan MCP) | 持续监控Reddit热搜、Google Trends替代 |
| **图片理解** | 按token计 | 可选，分析图表/截图 |

### MiniMax 官方速率限制规则

根据官方文档 (https://platform.minimaxi.com/docs/token-plan/faq)：

**1. 5小时滚动窗口**
- 文本模型限制基于动态5小时窗口
- 过去5小时内的请求总数不能超过上限
- 窗口滚动后自动恢复

**2. 高峰期动态限速**
- **高峰期**: 工作日下午 15:00-17:30 (根据集群负载动态调整)
- 高峰期会动态收紧速率限制
- 基于账户使用维度控制，确保公平分配

**3. RPM/TPM 限制**
- 充值用户: RPM 500, TPM 20,000,000
- 超出后通常约1分钟恢复，高峰期可能动态收紧

### 用户自定义时段策略

| 时段 (北京时间) | 类型 | 最大请求数 | 说明 |
|----------------|------|-----------|------|
| **20:00 - 09:00** | 全功率 | 1300次/5h | 留200次冗余，避开官方1500上限 |
| **09:00 - 20:00** | 保守 | 900次/5h | 覆盖官方高峰期(15:00-17:30)，降低风险 |
| **周末/节假日** | 全功率 | 1300次/5h | 无官方高峰期限制 |

**关键设计约束**：
- LLM请求: 5小时滚动窗口，非固定时间块
- 搜索请求: 150次/小时，独立于LLM配额
- 需实现**时段感知配额管理器**，根据北京时间自动切换策略
- 高峰期(15:00-17:30工作日)额外保守，避免触发官方动态限速

## Work Objectives

### Core Objective
将PSY_line从"孤立数据源加权平均"重构为"行为模型驱动"架构

### Deliverables
1. **MarketState** - 统一数据结构，包含所有数据源
2. **MiniMax集成** - TokenPlan MCP (web_search) + LLM情绪分析
3. **RateLimiter** - 配额管理器，控制LLM和搜索请求频率
4. **UnifiedDataSource** - 统一数据获取层，输出 MarketState
5. **BehaviorModel v2** - 接收所有数据源，输出行为阶段
6. **SignalGenerator v2** - 基于行为阶段生成信号
7. **持续监控循环** - 定时/智能触发，配额感知
8. **MCP工具更新** - 暴露行为阶段、配额状态
9. **测试覆盖** - 行为模型、聚合层、信号层、配额管理完整测试

### Definition of Done
- [ ] `MarketState` 数据结构统一所有数据源输出
- [ ] `BehaviorModel` 接收 `MarketState`，输出行为阶段
- [ ] `SentimentAggregator` 对Reddit帖子做情绪分析
- [ ] `SignalGenerator` 基于行为阶段生成信号
- [ ] `run_sentiment_scan` 输出行为阶段信息
- [ ] 所有测试通过（≥30个）
- [ ] MCP工具正常工作

### Must Have
- 行为模型必须接收所有数据源（价格+情绪+搜索热度）
- Reddit帖子必须经过LLM情绪分析（非简单计数）
- 信号生成必须基于行为阶段（非加权平均）
- 所有模块保持向后兼容（MCP工具签名不变）
- **配额管理器**必须控制LLM和搜索请求频率
- **MiniMax web_search**替代Google Trends（更灵活）
- **持续监控**支持定时触发和智能触发（价格异动）

### Must NOT Have
- 不删除现有MCP工具（只扩展）
- 不引入新的外部API依赖（除MiniMax）
- 不改变Binance/Fear&Greed数据获取逻辑
- **不超额消耗配额**（LLM 1500次/5h，搜索 150次/h）

## Verification Strategy
- **Test decision**: TDD (RED-GREEN-REFACTOR)
- **Framework**: pytest
- **QA policy**: 每个模块有单元测试，端到端集成测试
- **Evidence**: `.sisyphus/evidence/task-{N}-{slug}.txt`

## Execution Strategy

### Wave 1: 基础设施（可并行）
- T1. 创建 `MarketState` 统一数据结构
- T2. 创建 `RateLimiter` 配额管理器
- T3. 创建 `MiniMaxClient` 集成 (TokenPlan MCP + LLM)
- T4. 修复 `backtester.py` 信号时间匹配bug

### Wave 2: 数据获取层
- T5. 创建 `UnifiedDataSource` 聚合层（含MiniMax web_search）
- T6. 重构 `SentimentAggregator` 集成LLM情绪分析

### Wave 3: 核心重构
- T7. 重构 `RetailBehaviorModel` 接收 `MarketState`
- T8. 重构 `SignalGenerator` 基于行为阶段

### Wave 4: MCP工具与持续监控
- T9. 更新 `main.py` MCP工具
- T10. 创建持续监控循环 (定时/智能触发)
- T11. 编写行为模型单元测试
- T12. 编写端到端集成测试

### Wave 5: 验证
- T13. 运行全部测试
- T14. 验证MCP工具和配额管理正常工作

### Dependency Matrix
| Task | Depends On | Blocks |
|------|-----------|--------|
| T1 | - | T5, T7, T8 |
| T2 | - | T3, T5, T10 |
| T3 | T2 | T5, T6 |
| T4 | - | - |
| T5 | T1, T2, T3 | T7, T8 |
| T6 | T3, T5 | T8 |
| T7 | T5 | T8 |
| T8 | T6, T7 | T9, T10 |
| T9 | T8 | T13 |
| T10 | T2, T8 | T13 |
| T11 | T7 | T13 |
| T12 | T8, T9 | T13 |
| T13 | T9, T10, T11, T12 | T14 |
| T14 | T13 | - |

### Agent Dispatch Summary
- Wave 1: 4 tasks (quick × 2, unspecified-high × 2)
- Wave 2: 2 tasks (unspecified-high × 2)
- Wave 3: 2 tasks (unspecified-high × 2)
- Wave 4: 4 tasks (visual-engineering × 1, unspecified-high × 3)
- Wave 5: 2 tasks (unspecified-high × 2)

## TODOs

- [ ] T1. 创建 `MarketState` 统一数据结构

  **What to do**: 创建新的 `market_state.py` 文件，定义 `MarketState` 数据类，统一所有数据源的输出格式

  **Must NOT do**: 不修改现有数据源模块的获取逻辑

  **Recommended Agent Profile**:
  - Category: `quick` - 纯数据结构定义
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: YES | Wave 1 | Blocks: T2, T4, T5 | Blocked By: -

  **References**:
  - Pattern: `src/psy_line/types.py` - 现有类型定义风格
  - Data: `FearGreedData`, `RedditPost`, `GoogleTrendsData`, `TradingViewSentiment`, `BinanceKline`

  **Acceptance Criteria**:
  - [ ] `MarketState` 包含所有数据源字段
  - [ ] `MarketState` 支持从各数据源构建
  - [ ] 无LSP错误

  **QA Scenarios**:
  ```
  Scenario: MarketState from all sources
    Tool: Bash (pytest)
    Steps: 构造完整MarketState，验证所有字段可访问
    Expected: 无异常，所有字段有正确类型
    Evidence: .sisyphus/evidence/task-1-market-state.txt

  Scenario: MarketState partial data
    Tool: Bash (pytest)
    Steps: 构造部分数据源的MarketState（如只有Fear&Greed+Binance）
    Expected: 缺失字段为None或默认值，不抛异常
    Evidence: .sisyphus/evidence/task-1-market-state-partial.txt
  ```

  **Commit**: YES | Message: `feat(types): add MarketState unified data structure` | Files: `src/psy_line/market_state.py`

- [ ] T2. 创建 `RateLimiter` 时段感知配额管理器

  **What to do**: 创建 `rate_limiter.py`，管理MiniMax API配额，支持时段感知策略：

  **时段策略** (北京时间 UTC+8):
  - **全功率时段** (20:00-09:00 + 周末/节假日): 1300次/5h
  - **保守时段** (09:00-20:00 工作日): 900次/5h
  - **官方高峰期** (工作日15:00-17:30): 额外保守，降低请求频率

  **核心功能**:
  - 5小时滑动窗口计数 (非固定时间块)
  - 时段自动切换 (根据北京时间)
  - 搜索请求独立计数: 150次/小时
  - 优先级队列: 行为判断 > 情绪分析 > 搜索
  - 配额不足时自动降级 (跳过非关键请求)
  - 官方高峰期动态调整 (检测到429错误时自动降频)

  **Must NOT do**: 不修改现有数据源模块的获取逻辑

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - 需要理解时段感知配额管理逻辑
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: YES | Wave 1 | Blocks: T3, T5, T10 | Blocked By: -

  **References**:
  - Pattern: 滑动窗口限流算法 + 时段策略
  - Config: `FULL_POWER_LIMIT=1300`, `CONSERVATIVE_LIMIT=900`, `SEARCH_LIMIT=150`
  - Official: https://platform.minimaxi.com/docs/token-plan/faq

  **RateLimiter 接口设计**:
  ```python
  class RateLimiter:
      def __init__(self, config: RateLimitConfig):
          # config 包含时段策略配置

      def can_use_llm(self) -> bool:
          """根据当前时段和滑动窗口判断是否可用LLM"""

      def can_use_search(self) -> bool:
          """根据滑动窗口判断是否可用搜索"""

      def record_llm_usage(self):
          """记录一次LLM使用"""

      def record_search_usage(self):
          """记录一次搜索使用"""

      def get_remaining_quota(self) -> dict:
          """返回剩余配额信息"""

      def get_current_period(self) -> str:
          """返回当前时段: 'full_power', 'conservative', 'peak'"""
  ```

  **Acceptance Criteria**:
  - [ ] `can_use_llm()` 根据时段返回正确配额
  - [ ] `can_use_search()` 滑动窗口正确计数，不超额
  - [ ] 时段自动切换 (全功率/保守/高峰)
  - [ ] 429错误时自动降频 (官方高峰期保护)
  - [ ] 支持重置和查询剩余配额
  - [ ] 北京时间 (UTC+8) 正确计算

  **QA Scenarios**:
  ```
  Scenario: Full power period (20:00-09:00)
    Tool: Bash (pytest with mocked datetime)
    Steps: Mock当前时间为北京时间22:00
    Expected: can_use_llm() 返回True直到1300次耗尽
    Evidence: .sisyphus/evidence/task-2-full-power.txt

  Scenario: Conservative period (09:00-20:00 weekday)
    Tool: Bash (pytest with mocked datetime)
    Steps: Mock当前时间为北京时间周三14:00
    Expected: can_use_llm() 返回True直到900次耗尽
    Evidence: .sisyphus/evidence/task-2-conservative.txt

  Scenario: Peak hours extra caution (15:00-17:30 weekday)
    Tool: Bash (pytest with mocked datetime)
    Steps: Mock当前时间为北京时间周三16:00
    Expected: 请求频率降低，间隔增加
    Evidence: .sisyphus/evidence/task-2-peak-hours.txt

  Scenario: Weekend full power
    Tool: Bash (pytest with mocked datetime)
    Steps: Mock当前时间为北京时间周六14:00
    Expected: 周末无官方高峰期，使用全功率配额1300
    Evidence: .sisyphus/evidence/task-2-weekend.txt

  Scenario: 429 error handling
    Tool: Bash (pytest)
    Steps: Mock API返回429错误
    Expected: RateLimiter自动降频，等待后重试
    Evidence: .sisyphus/evidence/task-2-429-handling.txt
  ```

  **Commit**: YES | Message: `feat(ratelimiter): add time-aware RateLimiter for MiniMax API quota management` | Files: `src/psy_line/rate_limiter.py`

- [ ] T3. 创建 `MiniMaxClient` 集成 (TokenPlan MCP + LLM)

  **What to do**: 创建 `minimax_client.py`，集成MiniMax两个能力：
  1. **TokenPlan MCP web_search** - 通过uvx调用minimax-coding-plan-mcp的web_search工具
  2. **LLM API** - 直接调用MiniMax 2.7 API进行情绪分析

  **Must NOT do**: 不实现自己的搜索逻辑，使用TokenPlan MCP

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - 需要理解MCP协议和MiniMax API
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: NO | Wave 1 | Blocks: T5, T6 | Blocked By: T2

  **References**:
  - MCP: `uvx minimax-coding-plan-mcp -y` with `MINIMAX_API_KEY` and `MINIMAX_API_HOST`
  - API: https://api.minimaxi.com/v1/text/chatcompletion_v2 (MiniMax 2.7)
  - Guide: https://platform.minimaxi.com/docs/guides/token-plan-mcp-guide
  - Rate Limits: https://platform.minimaxi.com/docs/guides/rate-limits

  **MiniMaxClient 接口设计**:
  ```python
  class MiniMaxClient:
      def __init__(self, api_key: str, rate_limiter: RateLimiter):
          ...

      def web_search(self, query: str) -> List[SearchResult]:
          """通过TokenPlan MCP执行网络搜索 (受搜索配额保护)"""
          ...

      def analyze_sentiment(self, texts: List[str]) -> List[SentimentResult]:
          """使用MiniMax 2.7分析文本情绪 (受LLM配额保护)"""
          ...

      def get_quota_status(self) -> dict:
          """返回当前配额状态 (时段、剩余配额、下次重置时间)"""
          ...
  ```

  **Acceptance Criteria**:
  - [ ] `web_search()` 通过TokenPlan MCP返回搜索结果
  - [ ] `analyze_sentiment()` 使用MiniMax 2.7返回情绪分析
  - [ ] 两个方法都受RateLimiter保护 (时段感知)
  - [ ] 429错误时自动重试 (指数退避)
  - [ ] API失败时优雅降级

  **QA Scenarios**:
  ```
  Scenario: Web search via TokenPlan MCP
    Tool: Bash (pytest with mocked subprocess)
    Steps: Mock uvx调用返回搜索结果
    Expected: 解析搜索结果，返回List[SearchResult]
    Evidence: .sisyphus/evidence/task-3-web-search.txt

  Scenario: Sentiment analysis with MiniMax 2.7
    Tool: Bash (pytest with mocked HTTP)
    Steps: Mock MiniMax API返回情绪分析结果
    Expected: 解析JSON，返回List[SentimentResult]
    Evidence: .sisyphus/evidence/task-3-sentiment-analysis.txt

  Scenario: Rate limiter protection (time-aware)
    Tool: Bash (pytest)
    Steps: Mock RateLimiter在保守时段返回False
    Expected: web_search/analyze_sentiment返回空结果，不实际调用API
    Evidence: .sisyphus/evidence/task-3-rate-limiter-protection.txt

  Scenario: 429 retry with exponential backoff
    Tool: Bash (pytest with mocked HTTP)
    Steps: Mock API返回429，然后成功
    Expected: 自动重试，最终返回结果
    Evidence: .sisyphus/evidence/task-3-429-retry.txt
  ```

  **Commit**: YES | Message: `feat(minimax): add MiniMaxClient with TokenPlan MCP and LLM integration` | Files: `src/psy_line/minimax_client.py`

- [ ] T4. 修复 `backtester.py` 信号时间匹配bug

  **What to do**: 修复回测引擎中信号与K线时间不匹配的问题。当前用第一个信号对所有K线交易，应改为信号与K线时间戳匹配

  **Must NOT do**: 不改变回测核心逻辑（开仓/平仓/计算PnL）

  **Recommended Agent Profile**:
  - Category: `quick` - 单一bug修复
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: YES | Wave 1 | Blocks: - | Blocked By: -

  **References**:
  - Bug location: `src/psy_line/backtester.py:65` - `if not position_open and signals and signals[0].type.value == "BUY"`
  - Pattern: 信号应按时间戳匹配到对应K线

  **Acceptance Criteria**:
  - [ ] 信号与K线按时间戳匹配
  - [ ] 无信号的K线不触发交易
  - [ ] 现有测试通过

  **QA Scenarios**:
  ```
  Scenario: Signal-time matching
    Tool: Bash (pytest)
    Steps: 创建3个信号（不同时间戳）+ 10根K线，运行回测
    Expected: 只在信号对应时间附近触发交易
    Evidence: .sisyphus/evidence/task-4-backtest-time-match.txt

  Scenario: No signal = no trade
    Tool: Bash (pytest)
    Steps: 创建空信号列表 + 10根K线，运行回测
    Expected: num_trades == 0
    Evidence: .sisyphus/evidence/task-4-backtest-no-signal.txt
  ```

  **Commit**: YES | Message: `fix(backtester): match signals to klines by timestamp` | Files: `src/psy_line/backtester.py`

- [ ] T5. 创建 `UnifiedDataSource` 聚合层（含MiniMax web_search）

  **What to do**: 创建 `unified_source.py`，替代现有 `SentimentAggregator`，统一获取所有数据源并输出 `MarketState`。集成MiniMax web_search作为Google Trends替代

  **Must NOT do**: 不改变各数据源的获取逻辑，只做聚合

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - 需要理解现有数据源接口
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: NO | Wave 2 | Blocks: T7, T8 | Blocked By: T1, T2, T3

  **References**:
  - Pattern: `src/psy_line/sentiment_aggregator.py` - 现有聚合逻辑（需改进）
  - API: `FearGreedClient`, `RedditRSSClient`, `BinanceClient`, `MiniMaxClient`
  - New: MiniMax web_search 替代 Google Trends

  **Acceptance Criteria**:
  - [ ] `UnifiedDataSource.fetch()` 返回完整 `MarketState`
  - [ ] 各数据源失败时优雅降级（返回None/默认值）
  - [ ] 支持代理配置（Google Trends走7897）
  - [ ] 支持部分数据源获取
  - [ ] 集成MiniMax web_search作为搜索数据源
  - [ ] 受RateLimiter保护（搜索配额）

  **QA Scenarios**:
  ```
  Scenario: Full market state fetch
    Tool: Bash (pytest with mocked clients)
    Steps: Mock所有数据源返回有效数据，调用fetch()
    Expected: MarketState包含所有字段，无None
    Evidence: .sisyphus/evidence/task-5-unified-full.txt

  Scenario: Partial fetch with failures
    Tool: Bash (pytest with mocked clients)
    Steps: Mock MiniMax search和TradingView抛异常，其他正常
    Expected: MarketState中失败源为None/默认值，其他正常
    Evidence: .sisyphus/evidence/task-5-unified-partial.txt

  Scenario: Rate limiter respected
    Tool: Bash (pytest)
    Steps: Mock RateLimiter搜索配额耗尽
    Expected: UnifiedDataSource跳过搜索，其他数据源正常获取
    Evidence: .sisyphus/evidence/task-5-rate-limiter-respected.txt
  ```

  **Commit**: YES | Message: `feat(datasource): add UnifiedDataSource with MiniMax web_search integration` | Files: `src/psy_line/unified_source.py`

- [ ] T6. 重构 `SentimentAggregator` 集成LLM情绪分析

  **What to do**: 重构聚合层，对Reddit帖子标题/内容做LLM情绪分析，而非简单计数。使用MiniMax 2.7 API进行分析

  **Must NOT do**: 不改变数据获取逻辑，只做情绪分析集成

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - 需要集成LLM分析
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: NO | Wave 2 | Blocks: T8 | Blocked By: T3, T5

  **References**:
  - Existing: `src/psy_line/sentiment_analyzer.py` - LLM分析器（从未被调用）
  - Existing: `src/psy_line/sentiment_aggregator.py` - 现有聚合逻辑
  - New: `MiniMaxClient.analyze_sentiment()` 替代OpenAI
  - Pattern: `SentimentAnalyzer.analyze_batch()` 接受评论列表

  **Acceptance Criteria**:
  - [ ] Reddit帖子经过MiniMax LLM情绪分析
  - [ ] 分析结果纳入composite_score
  - [ ] API失败时优雅降级（返回中性情绪）
  - [ ] 支持跳过LLM分析（use_llm=False）
  - [ ] 受RateLimiter保护（LLM配额）

  **QA Scenarios**:
  ```
  Scenario: Reddit sentiment analysis integration
    Tool: Bash (pytest with mocked MiniMax)
    Steps: Mock MiniMax返回看涨情绪，传入5条Reddit帖子
    Expected: composite_score反映看涨情绪
    Evidence: .sisyphus/evidence/task-6-reddit-llm.txt

  Scenario: LLM fallback on error
    Tool: Bash (pytest with mocked MiniMax)
    Steps: Mock MiniMax抛异常
    Expected: 返回中性情绪，不崩溃
    Evidence: .sisyphus/evidence/task-6-llm-fallback.txt

  Scenario: Rate limiter respected
    Tool: Bash (pytest)
    Steps: Mock RateLimiter LLM配额耗尽
    Expected: 跳过LLM分析，返回中性情绪
    Evidence: .sisyphus/evidence/task-6-rate-limiter.txt
  ```

  **Commit**: YES | Message: `feat(aggregator): integrate MiniMax LLM sentiment analysis for Reddit posts` | Files: `src/psy_line/sentiment_aggregator.py`

- [ ] T7. 重构 `RetailBehaviorModel` 接收 `MarketState`

  **What to do**: 扩展行为模型，使其接收 `MarketState` 而非仅价格数据。将社会情绪数据（Fear&Greed、Reddit情绪、Google Trends、TradingView）作为行为判断的交叉验证

  **Must NOT do**: 不删除现有价格/成交量分析逻辑，只做扩展

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - 核心业务逻辑重构
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: NO | Wave 2 | Blocks: T6 | Blocked By: T1, T2

  **References**:
  - Current: `src/psy_line/retail_behavior.py` - 现有行为模型
  - New input: `MarketState` from T1
  - Academic: arXiv:1806.11348 (Herding), NBER 2023 (Disposition Effect)

  **Acceptance Criteria**:
  - [ ] `RetailBehaviorModel.calculate_indicators()` 接收 `MarketState`
  - [ ] FOMO指数结合价格动量 + Google Trends搜索热度
  - [ ] 恐慌指数结合价格下跌 + Fear&Greed恐惧指数
  - [ ] 从众指数结合价格趋势 + Reddit帖子情绪一致性
  - [ ] 现有价格分析逻辑保持不变

  **QA Scenarios**:
  ```
  Scenario: FOMO detection with social confirmation
    Tool: Bash (pytest)
    Steps: 构造价格上涨 + Google Trends飙升 + Reddit看涨情绪一致的MarketState
    Expected: FOMO指数 > 0.8，阶段为FOMO_BUY或FOMO_EXTREME
    Evidence: .sisyphus/evidence/task-4-fomo-social.txt

  Scenario: Panic detection with fear confirmation
    Tool: Bash (pytest)
    Steps: 构造价格下跌 + Fear&Greed<20 + Reddit恐慌情绪的MarketState
    Expected: 恐慌指数 > 0.7，阶段为PANIC_SELL或CAPITULATION
    Evidence: .sisyphus/evidence/task-4-panic-fear.txt

  Scenario: Suspicion phase (price up, social neutral)
    Tool: Bash (pytest)
    Steps: 构造价格连涨但Fear&Greed中性、Reddit情绪中性的MarketState
    Expected: 阶段为SUSPICION（机构吸筹，散户犹豫）
    Evidence: .sisyphus/evidence/task-4-suspicion.txt
  ```

  **Commit**: YES | Message: `feat(behavior): extend RetailBehaviorModel to accept MarketState` | Files: `src/psy_line/retail_behavior.py`

- [ ] T8. 重构 `SignalGenerator` 基于行为阶段

  **What to do**: 重构信号生成器，将行为阶段作为核心决策依据，而非加权平均。行为阶段直接映射到交易信号

  **Must NOT do**: 不删除PSY/动量计算，作为辅助验证

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - 核心业务逻辑重构
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: NO | Wave 3 | Blocks: T9, T10 | Blocked By: T6, T7

  **References**:
  - Current: `src/psy_line/signal_generator.py` - 现有信号生成器
  - New: `BehaviorPhase` → `SignalType` 映射逻辑

  **Signal Mapping**:
  | BehaviorPhase | Signal | Rationale |
  |--------------|--------|-----------|
  | FOMO_EXTREME | SELL | 极度贪婪，反向做空 |
  | FOMO_BUY | SELL | FOMO追入，反向做空 |
  | PANIC_SELL | BUY | 恐慌抛售，反向做多 |
  | CAPITULATION | BUY | 割肉离场，底部信号 |
  | SUSPICION | BUY | 怀疑阶段，可能吸筹 |
  | EQUILIBRIUM | HOLD | 均衡状态，观望 |

  **Acceptance Criteria**:
  - [ ] 信号生成基于行为阶段
  - [ ] PSY/动量作为辅助验证（可增强/减弱信号强度）
  - [ ] 现有MCP工具签名不变
  - [ ] reasoning包含行为阶段信息

  **QA Scenarios**:
  ```
  Scenario: FOMO_EXTREME → SELL
    Tool: Bash (pytest)
    Steps: 构造FOMO_EXTREME行为信号，调用generate_signal
    Expected: SignalType.SELL, strength > 0.7
    Evidence: .sisyphus/evidence/task-8-fomo-sell.txt

  Scenario: CAPITULATION → BUY
    Tool: Bash (pytest)
    Steps: 构造CAPITULATION行为信号，调用generate_signal
    Expected: SignalType.BUY, strength > 0.7
    Evidence: .sisyphus/evidence/task-8-capitulation-buy.txt

  Scenario: EQUILIBRIUM → HOLD
    Tool: Bash (pytest)
    Steps: 构造EQUILIBRIUM行为信号，调用generate_signal
    Expected: SignalType.HOLD
    Evidence: .sisyphus/evidence/task-8-equilibrium-hold.txt
  ```

  **Commit**: YES | Message: `feat(signal): refactor SignalGenerator to use behavior phase as primary driver` | Files: `src/psy_line/signal_generator.py`

- [ ] T9. 更新 `main.py` MCP工具

  **What to do**: 更新MCP工具，在 `run_sentiment_scan` 输出中展示行为阶段信息。新增 `get_quota_status` 工具显示MiniMax配额状态

  **Must NOT do**: 不删除现有工具，只扩展输出

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - 输出格式美化
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: NO | Wave 4 | Blocks: T13 | Blocked By: T8

  **References**:
  - Current: `src/psy_line/main.py` - MCP工具定义和handler
  - New output: 行为阶段、FOMO指数、恐慌指数、配额状态

  **Acceptance Criteria**:
  - [ ] `run_sentiment_scan` 输出包含行为阶段
  - [ ] `detect_retail_behavior` 工具正常工作
  - [ ] 新增 `get_quota_status` 工具显示MiniMax配额
  - [ ] 所有工具无LSP错误
  - [ ] MCP Server可正常启动

  **QA Scenarios**:
  ```
  Scenario: run_sentiment_scan shows behavior phase
    Tool: Bash (pytest with mocked clients)
    Steps: Mock所有数据源，调用run_sentiment_scan工具
    Expected: 输出包含"Behavior Phase:"行
    Evidence: .sisyphus/evidence/task-9-scan-behavior.txt

  Scenario: get_quota_status shows remaining quota
    Tool: Bash (pytest with mocked RateLimiter)
    Steps: 调用get_quota_status工具
    Expected: 输出包含LLM和搜索剩余配额
    Evidence: .sisyphus/evidence/task-9-quota-status.txt

  Scenario: MCP server starts
    Tool: Bash (python -m psy_line)
    Steps: 启动MCP Server，验证无启动错误
    Expected: Server正常启动（stdio模式）
    Evidence: .sisyphus/evidence/task-9-server-start.txt
  ```

  **Commit**: YES | Message: `feat(mcp): add behavior phase and quota status output` | Files: `src/psy_line/main.py`

- [ ] T10. 创建持续监控循环 (时段感知)

  **What to do**: 创建 `monitor.py`，实现持续监控循环：
  - **全功率时段** (20:00-09:00): 每5分钟扫描一次，最大化数据收集
  - **保守时段** (09:00-20:00): 每15分钟扫描一次，降低请求频率
  - **智能触发**: Binance价格异动（>2%）时立即触发
  - **配额感知**: 剩余额度不足时降级（跳过LLM/搜索，仅用静态API）
  - **后台运行**: 不阻塞MCP Server

  **Must NOT do**: 不修改现有数据获取逻辑

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - 需要理解异步和定时任务
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: NO | Wave 4 | Blocks: T13 | Blocked By: T2, T8

  **References**:
  - Pattern: Python asyncio定时任务
  - RateLimiter: T2创建的时段感知配额管理器
  - UnifiedDataSource: T5创建的数据源

  **监控策略**:
  | 时段 | 扫描间隔 | LLM使用 | 搜索使用 |
  |------|---------|---------|---------|
  | 20:00-09:00 | 5分钟 | ✅ 每批次 | ✅ 每批次 |
  | 09:00-20:00 | 15分钟 | ✅ 每2批次 | ✅ 每3批次 |
  | 官方高峰(15:00-17:30) | 20分钟 | ⚠️ 仅关键 | ❌ 跳过 |

  **Acceptance Criteria**:
  - [ ] 定时触发器根据时段自动调整间隔
  - [ ] 价格异动检测（>2%变化）立即触发
  - [ ] 配额不足时自动降级
  - [ ] 后台运行不阻塞主线程
  - [ ] 时段切换时无缝过渡

  **QA Scenarios**:
  ```
  Scenario: Full power monitoring (20:00-09:00)
    Tool: Bash (pytest with mocked asyncio)
    Steps: Mock北京时间22:00，启动监控循环
    Expected: 每5分钟执行一次扫描
    Evidence: .sisyphus/evidence/task-10-full-power-monitor.txt

  Scenario: Conservative monitoring (09:00-20:00)
    Tool: Bash (pytest with mocked asyncio)
    Steps: Mock北京时间周三14:00，启动监控循环
    Expected: 每15分钟执行一次扫描
    Evidence: .sisyphus/evidence/task-10-conservative-monitor.txt

  Scenario: Price trigger monitoring
    Tool: Bash (pytest)
    Steps: Mock价格变化>2%
    Expected: 立即触发扫描，不等定时周期
    Evidence: .sisyphus/evidence/task-10-price-trigger.txt

  Scenario: Quota-aware degradation
    Tool: Bash (pytest)
    Steps: Mock配额耗尽
    Expected: 监控循环跳过LLM/搜索，仅用静态API
    Evidence: .sisyphus/evidence/task-10-quota-degrade.txt
  ```

  **Commit**: YES | Message: `feat(monitor): add time-aware continuous monitoring loop with quota awareness` | Files: `src/psy_line/monitor.py`

- [ ] T11. 编写行为模型单元测试

  **What to do**: 为 `RetailBehaviorModel` 编写完整单元测试，覆盖所有行为阶段和边界情况

  **Must NOT do**: 不测试数据获取逻辑（那是T12的范围）

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - 需要全面测试覆盖
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: YES | Wave 4 | Blocks: T13 | Blocked By: T7

  **References**:
  - Existing: `tests/test_integration.py` - 现有测试风格
  - Target: `src/psy_line/retail_behavior.py`

  **Acceptance Criteria**:
  - [ ] 覆盖6个行为阶段
  - [ ] 覆盖边界情况（空数据、单条数据）
  - [ ] 覆盖FOMO/herding/disposition/panic指数计算
  - [ ] 测试数量 ≥ 15个

  **QA Scenarios**:
  ```
  Scenario: All tests pass
    Tool: Bash (pytest tests/test_behavior.py -v)
    Steps: 运行行为模型测试
    Expected: ≥15个测试全部通过
    Evidence: .sisyphus/evidence/task-11-behavior-tests.txt
  ```

  **Commit**: YES | Message: `test(behavior): add comprehensive unit tests for RetailBehaviorModel` | Files: `tests/test_behavior.py`

- [ ] T12. 编写端到端集成测试

  **What to do**: 编写端到端测试，验证完整数据流：数据获取 → 聚合 → 行为模型 → 信号生成

  **Must NOT do**: 不mock行为模型内部逻辑（那是T11的范围）

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - 需要理解完整数据流
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: YES | Wave 4 | Blocks: T13 | Blocked By: T8, T9

  **References**:
  - Existing: `tests/test_integration.py` - 现有集成测试
  - Full flow: UnifiedDataSource → BehaviorModel → SignalGenerator

  **Acceptance Criteria**:
  - [ ] 测试完整数据流
  - [ ] 测试各数据源失败时的优雅降级
  - [ ] 测试信号生成正确性
  - [ ] 测试数量 ≥ 10个

  **QA Scenarios**:
  ```
  Scenario: Full pipeline test
    Tool: Bash (pytest tests/test_pipeline.py -v)
    Steps: 运行端到端测试
    Expected: ≥10个测试全部通过
    Evidence: .sisyphus/evidence/task-12-pipeline-tests.txt
  ```

  **Commit**: YES | Message: `test(e2e): add end-to-end pipeline tests` | Files: `tests/test_pipeline.py`

- [ ] T13. 运行全部测试

  **What to do**: 运行所有测试（单元+集成+端到端），确保无回归

  **Must NOT do**: 不修改测试代码（除非发现测试本身有bug）

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - 需要验证全部通过
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: NO | Wave 5 | Blocks: T14 | Blocked By: T9, T10, T11, T12

  **Acceptance Criteria**:
  - [ ] 所有测试通过（≥40个）
  - [ ] 无LSP错误
  - [ ] MCP Server可正常启动

  **QA Scenarios**:
  ```
  Scenario: All tests pass
    Tool: Bash (pytest tests/ -v)
    Steps: 运行全部测试
    Expected: ≥40个测试全部通过，0失败
    Evidence: .sisyphus/evidence/task-13-all-tests.txt
  ```

  **Commit**: NO

- [ ] T14. 验证MCP工具和配额管理正常工作

  **What to do**: 手动验证MCP工具可正常调用，配额管理正确工作

  **Must NOT do**: 不修改代码

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - 需要手动验证
  - Skills: []
  - Omitted: 无需特殊技能

  **Parallelization**: CanParallel: NO | Wave 5 | Blocks: - | Blocked By: T13

  **Acceptance Criteria**:
  - [ ] `get_fear_greed_index` 返回正确数据
  - [ ] `run_sentiment_scan` 返回完整扫描结果（含行为阶段）
  - [ ] `detect_retail_behavior` 返回行为阶段
  - [ ] `get_binance_price` 返回实时价格
  - [ ] `get_quota_status` 显示MiniMax配额状态
  - [ ] 配额管理正确限制请求频率

  **Commit**: NO

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE.
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. Real Manual QA — unspecified-high
- [ ] F4. Scope Fidelity Check — deep

## Commit Strategy
每个任务独立提交，保持原子性。最终squash为4个commit：
1. `feat(types): add MarketState and RateLimiter`
2. `feat(minimax): add MiniMaxClient and UnifiedDataSource`
3. `feat(behavior): refactor behavior model, signal generation, and monitoring`
4. `test: add comprehensive tests for all modules`

## Success Criteria
- [ ] 行为模型接收所有数据源（价格+情绪+搜索热度）
- [ ] Reddit帖子经过MiniMax LLM情绪分析
- [ ] 信号生成基于行为阶段
- [ ] **时段感知配额管理**正确工作:
  - [ ] 20:00-09:00 全功率: 1300次/5h
  - [ ] 09:00-20:00 保守: 900次/5h
  - [ ] 官方高峰期(15:00-17:30工作日) 额外保守
- [ ] 持续监控循环支持时段自适应 (5min/15min/20min)
- [ ] 所有测试通过（≥40个）
- [ ] MCP工具正常工作
- [ ] 无LSP错误
- [ ] 向后兼容（MCP工具签名不变）
