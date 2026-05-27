# PSY_line: Final Implementation Tasks

## TL;DR
> **Summary**: Complete remaining implementation for PSY_line — add RateLimiter `wait_for_slot()`, VADER sentiment fallback, clean up dead OpenAI code, create Hermes plugin config and optional memory provider.
> **Deliverables**: 7 implementation tasks + 1 verification wave
> **Effort**: Medium
> **Parallel**: YES — 3 waves
> **Critical Path**: Task 1 → Task 2 → Verification

## Context
### Original Request
"开始实施" — implement remaining tasks from the planning session:
1. RateLimiter: `wait_for_slot()` blocking method
2. SentimentAggregator: VADER fallback chain
3. pyproject.toml: add vaderSentiment, remove openai
4. Delete sentiment_analyzer.py (dead code)
5. main.py: clean up OpenAIConfig references
6. Create `.hermes/psy_line_config.yaml.example`
7. Create `plugins/memory/psy_line/` Memory Provider

### Interview Summary
- Reddit sentiment chain: MiniMax LLM (primary) → wait_for_slot() (blocking pause) → VADER local (fallback) → 0.0
- sentiment_analyzer.py confirmed dead (0 imports referencing it)
- OpenAIConfig stays in config.py as data model but main.py should not depend on it
- Hermes plugin: PSY_line is already an MCP Server, zero-code integration via `~/.hermes/config.yaml`
- Memory Provider: optional Hermes plugin pattern at `plugins/memory/psy_line/`

### Metis Review
> Skipped (agent kept timing out)

## Work Objectives
### Core Objective
Complete all 7 remaining implementation tasks with zero regression.

### Deliverables
- `rate_limiter.py` with `wait_for_slot()` blocking method
- `sentiment_aggregator.py` with VADER fallback chain
- `pyproject.toml` with `vaderSentiment` dep, `openai` removed
- `sentiment_analyzer.py` deleted
- `main.py` with cleaned-up imports and config fallback
- `.hermes/psy_line_config.yaml.example` created
- `plugins/memory/psy_line/` memory provider stub created

### Definition of Done
- All 51 existing tests pass
- Zero LSP errors across all source files (current baseline: 0)
- New VADER fallback has unit test coverage
- `wait_for_slot()` has unit test coverage

### Must Have
- `wait_for_slot()` blocks until quota available (non-busy wait, max_timeout)
- VADER fallback actually produces sentiment score (not just 0.0)
- Dead code deletion = files removed, not just commented
- Hermes config example is syntactically valid YAML

### Must NOT Have
- No changes to architecture (MarketState → BehaviorModel → SignalGenerator stays)
- No new external API dependencies (VADER is local only)
- No changes to existing test assertions (regression only)
- No changes to behavior model thresholds or signal logic

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.
- Test decision: tests-after (pytest, existing framework)
- QA policy: Every task has agent-executed scenarios
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves

**Wave 1** (foundation — no dependencies):
- Task 1: `rate_limiter.py` — `wait_for_slot()`
- Task 3: `pyproject.toml` — dependency changes (vaderSentiment + remove openai)
- Task 4: Delete `sentiment_analyzer.py`
- Task 6: Create `.hermes/psy_line_config.yaml.example`
- Task 7: Create `plugins/memory/psy_line/`

**Wave 2** (depends on Task 1, 3, 4):
- Task 2: `sentiment_aggregator.py` — VADER fallback (needs vaderSentiment installed, rate_limiter updated)
- Task 5: `main.py` — clean up (needs sentiment_analyzer.py deleted)

**Wave 3** (verification):
- F1-F4: Verification wave

### Dependency Matrix

| Task | Blocks | Blocked By |
|------|--------|------------|
| 1. wait_for_slot() | 2 | — |
| 2. VADER fallback | — | 1, 3, 4 |
| 3. pyproject.toml | 2 | — |
| 4. Delete dead code | 2, 5 | — |
| 5. main.py cleanup | — | 4 |
| 6. Hermes config | — | — |
| 7. Memory Provider | — | — |

### Agent Dispatch Summary
- Wave 1: 5 tasks (independent, parallel)
- Wave 2: 2 tasks (dependent on Wave 1)
- Wave 3: 4 verification agents (parallel)

## TODOs

- [ ] 1. Add `wait_for_slot()` to RateLimiter

  **What to do**:
  Add a blocking `wait_for_slot(max_wait: float = 300.0) -> bool` method to `RateLimiter` class in `rate_limiter.py`.

  Behavior:
  1. If quota available (`can_use_llm()` returns True) → return True immediately
  2. If quota exhausted → sleep in a loop (check every 10s), return False after `max_wait` seconds
  3. Use `threading.Event.wait(timeout)` for efficient non-busy waiting
  4. Log at warning level each check cycle when still waiting
  5. On return False (timeout), log error "wait_for_slot timed out after {max_wait}s"

  Return `True` if slot acquired, `False` if timed out.

  Also add `import time` at top of file.

  **Must NOT do**:
  - Do NOT change any existing method signatures or behavior
  - Do NOT add external dependencies (standard lib only)
  - Do NOT modify `get_wait_time()` or `on_429_error()`

  **Recommended Agent Profile**:
  - Category: `unspecified-low` — single method addition, well-defined
  - Skills: `[]` — trivial Python
  - Omitted: n/a

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [2] | Blocked By: []

  **References**:
  - File: `src/psy_line/rate_limiter.py` — add method after `can_use_llm()` (line ~104)
  - Pattern: existing `_clean_window()` and `can_use_llm()` for lock pattern
  - Existing `get_wait_time()` returns 60.0 when quota exhausted — use as base interval

  **Acceptance Criteria**:
  - [ ] New method `wait_for_slot(max_wait=300)` exists on `RateLimiter`
  - [ ] Returns True immediately when `can_use_llm()` returns True
  - [ ] Blocks and returns False after timeout when quota exhausted
  - [ ] Existing 164 lines of tested code unchanged
  - [ ] `pytest tests/` — all tests pass

  **QA Scenarios**:
  ```
  Scenario: wait_for_slot returns immediately when quota available
    Tool: interactive_bash
    Steps:
      1. Import RateLimiter from psy_line.rate_limiter
      2. Create RateLimiter() instance (fresh, no usage)
      3. Call wait_for_slot(max_wait=5)
    Expected: Returns True within 1 second
    Evidence: .sisyphus/evidence/task-1-quota-available.txt

  Scenario: wait_for_slot times out when quota exhausted
    Tool: interactive_bash
    Steps:
      1. Import RateLimiter
      2. Create RateLimiter with config full_power_limit=1
      3. Record 1 LLM usage (record_llm_usage())
      4. Call wait_for_slot(max_wait=2)
    Expected: Returns False within 3 seconds
    Evidence: .sisyphus/evidence/task-1-quota-exhausted.txt
  ```

  **Commit**: YES | Message: `feat(rate_limiter): add wait_for_slot blocking method` | Files: [`src/psy_line/rate_limiter.py`]

---

- [ ] 2. Add VADER sentiment fallback to SentimentAggregator

  **What to do**:
  Add VADER (Valence Aware Dictionary and sEntiment Reasoner) as fallback sentiment analysis in `SentimentAggregator._analyze_reddit_with_llm()`.

  1. At top of `sentiment_aggregator.py`, add:
     ```python
     try:
         from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
         _VADER_AVAILABLE = True
     except ImportError:
         _VADER_AVAILABLE = False
     ```

  2. Modify `_analyze_reddit_with_llm()` fallback chain as documented:
     - MiniMax LLM runs first (protected by `wait_for_slot` instead of `can_use_llm`)
     - If MiniMax fails/None → try VADER locally
     - If VADER not available → return 0.0 (neutral)

  3. Change the quota check in `_analyze_reddit_with_llm`:
     - Replace `if self._rate_limiter is not None and not self._rate_limiter.can_use_llm(): return None`
     - With: `if self._rate_limiter is not None and not self._rate_limiter.wait_for_slot(): log warning, fall through to VADER`

  4. Add VADER analysis block before the `return None` at end:
     ```python
     if _VADER_AVAILABLE:
         try:
             analyzer = SentimentIntensityAnalyzer()
             scores = [analyzer.polarity_scores(f"{p.title} {p.content[:200]}") for p in posts]
             composite = sum(s["compound"] for s in scores) / len(scores)
             logger.info(f"VADER fallback sentiment: {composite:.3f} (LLM unavailable)")
             return max(-1.0, min(1.0, composite))
         except Exception as e:
             logger.warning(f"VADER analysis failed: {e}")
     ```

  5. Add `import logging` at top if not present (check: it's imported via logger = logging.getLogger)

  **Update docstring**: Change method docstring to:
  ```
  Analyze Reddit post sentiment with fallback chain.
  
  Fallback order:
  1. MiniMax LLM (primary) — protected by wait_for_slot()
  2. VADER local (fallback) — no API key needed
  3. 0.0 (neutral) — last resort
  ```

  **Must NOT do**:
  - Do NOT change the `aggregate()` method
  - Do NOT change how `social_score` is used downstream
  - Do NOT change the public API/interface
  - Do NOT import VADER at module level (use try/except guard)

  **Recommended Agent Profile**:
  - Category: `unspecified-low` — well-defined code addition
  - Skills: `[]` — straightforward Python
  - Omitted: n/a

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: [] | Blocked By: [1, 3, 4]

  **References**:
  - File: `src/psy_line/sentiment_aggregator.py` — lines 147-176 `_analyze_reddit_with_llm()`
  - VADER docs: `https://github.com/cjhutto/vaderSentiment` — `polarity_scores()` returns dict with `compound` key (-1 to 1)
  - Existing pattern: `_minimax.analyze_sentiment()` already returns composite score clamped to [-1, 1]

  **Acceptance Criteria**:
  - [ ] VADER runs when MiniMax LLM unavailable (quota exhausted)
  - [ ] Returns float between -1.0 and 1.0 when VADER succeeds
  - [ ] Returns 0.0 when both MiniMax and VADER fail
  - [ ] No import errors when vaderSentiment not installed (graceful)
  - [ ] `pytest tests/` — all tests pass

  **QA Scenarios**:
  ```
  Scenario: VADER returns sentiment when LLM unavailable
    Tool: interactive_bash
    Steps:
      1. Pip install vaderSentiment
      2. Run: python -c "from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer; a=SentimentIntensityAnalyzer(); r=a.polarity_scores('Bitcoin is great!'); print(r['compound'])"
    Expected: Positive compound score printed
    Evidence: .sisyphus/evidence/task-2-vader-works.txt

  Scenario: VADER fallback activates when rate_limiter blocks
    Tool: interactive_bash
    Steps:
      1. Run: cd psy_line && python -c "
        from psy_line.sentiment_aggregator import SentimentAggregator
        from psy_line.rate_limiter import RateLimiter, RateLimitConfig
        rl = RateLimiter(RateLimitConfig(full_power_limit=0))
        sa = SentimentAggregator(rate_limiter=rl)
        from psy_line.reddit_rss import RedditPost
        score = sa._analyze_reddit_with_llm([RedditPost(id='1', title='Test', content='Great post', url='', subreddit='test')])
        print(f'Score: {score}')
      "
    Expected: Score is a float (not None) — VADER fallback used
    Evidence: .sisyphus/evidence/task-2-vader-fallback.txt
  ```

  **Commit**: YES | Message: `feat(sentiment): add VADER fallback for Reddit sentiment` | Files: [`src/psy_line/sentiment_aggregator.py`]

---

- [ ] 3. Update pyproject.toml dependencies

  **What to do**:
  Edit `pyproject.toml` to:
  1. Remove `"openai>=1.0.0,<2.0.0"` from the `dependencies` list
  2. Add `"vaderSentiment>=3.3.2,<4.0.0"` to the `dependencies` list

  **Must NOT do**:
  - Do NOT change any other dependency versions
  - Do NOT change optional-dependencies or build config

  **Recommended Agent Profile**:
  - Category: `quick` — one-line change
  - Skills: `[]`
  - Omitted: n/a

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [2] | Blocked By: []

  **References**:
  - File: `pyproject.toml` — lines 25-35

  **Acceptance Criteria**:
  - [ ] `openai` not listed in `[project] dependencies`
  - [ ] `vaderSentiment>=3.3.2,<4.0.0` listed in `[project] dependencies`
  - [ ] `pip install -e .` succeeds without OpenAI
  - [ ] `pytest tests/` — all tests pass

  **QA Scenarios**:
  ```
  Scenario: Installation succeeds without openai
    Tool: interactive_bash
    Steps:
      1. cd psy_line && pip install -e ".[dev]"
    Expected: Exit code 0, no ModuleNotFoundError for openai
    Evidence: .sisyphus/evidence/task-3-install.txt
  ```

  **Commit**: YES | Message: `chore(deps): add vaderSentiment, remove openai` | Files: [`pyproject.toml`]

---

- [ ] 4. Delete sentiment_analyzer.py

  **What to do**:
  Delete the file `src/psy_line/sentiment_analyzer.py`.

  This file is dead code — confirmed by: `grep -r "sentiment_analyzer" src/` returns zero matches.

  Also delete the `__pycache__` directory for this file if it exists:
  `src/psy_line/__pycache__/sentiment_analyzer*.pyc`

  **Must NOT do**:
  - Do NOT touch any other files
  - Do NOT leave the file empty — remove it entirely

  **Recommended Agent Profile**:
  - Category: `quick` — single file deletion
  - Skills: `[]`
  - Omitted: n/a

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [2, 5] | Blocked By: []

  **References**:
  - File: `src/psy_line/sentiment_analyzer.py` — confirmed dead code

  **Acceptance Criteria**:
  - [ ] File `src/psy_line/sentiment_analyzer.py` does not exist
  - [ ] `pytest tests/` — all tests pass (no import errors)
  - [ ] `python -c "from psy_line import main"` — no import errors

  **QA Scenarios**:
  ```
  Scenario: Module imports still work after deletion
    Tool: interactive_bash
    Steps:
      1. python -c "from psy_line.main import get_config; print('OK')"
    Expected: Prints "OK"
    Evidence: .sisyphus/evidence/task-4-imports.txt
  ```

  **Commit**: YES | Message: `cleanup: remove dead sentiment_analyzer.py (OpenAI)` | Files: [`src/psy_line/sentiment_analyzer.py`]

---

- [ ] 5. Clean up main.py imports and config

  **What to do**:
  Edit `src/psy_line/main.py` to remove dead OpenAI references:

  1. Remove `OpenAIConfig` from the import line:
     ```python
     # Before:
     from .config import Config, RedditConfig, OpenAIConfig, BinanceConfig
     # After:
     from .config import Config, RedditConfig, BinanceConfig
     ```

  2. In `get_config()`, simplify the fallback Config construction — remove `openai=OpenAIConfig(...)` block:
     ```python
     # Before:
     _config = Config(
         reddit=RedditConfig(
             client_id="",
             client_secret="",
             user_agent="PSY_line/1.0",
             keywords=[],
             keywords_mode="include",
         ),
         openai=OpenAIConfig(
             api_key=os.environ.get("OPENAI_API_KEY", ""),
             model="gpt-4o",
         ),
         binance=BinanceConfig(
             api_key=os.environ.get("BINANCE_API_KEY", ""),
             secret_key=os.environ.get("BINANCE_SECRET_KEY", ""),
             testnet=True,
         ),
     )
     # After:
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
     ```

  3. Update module docstring: change `# Old: SentimentAggregator (weighted average) → REMOVED` to `# Old: SentimentAggregator + SentimentAnalyzer (OpenAI) → REMOVED`

  **Note**: `OpenAIConfig` stays in `config.py` itself — it's part of the `Config` pydantic model and removing it would break the model. Only remove it from `main.py`.

  **Must NOT do**:
  - Do NOT remove `OpenAIConfig` from `config.py`
  - Do NOT change any other function in main.py
  - Do NOT break the Config() structure — YAML-based loading still works with all fields

  **Recommended Agent Profile**:
  - Category: `unspecified-low` — import + config cleanup
  - Skills: `[]`
  - Omitted: n/a

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: [] | Blocked By: [4]

  **References**:
  - File: `src/psy_line/main.py` — lines 24, 54-71
  - File: `src/psy_line/config.py` — `OpenAIConfig` stays

  **Acceptance Criteria**:
  - [ ] `OpenAIConfig` not imported in `main.py`
  - [ ] `get_config()` fallback does not reference `OpenAIConfig`
  - [ ] `python -c "from psy_line.main import get_config; print('OK')"` works
  - [ ] `pytest tests/` — all tests pass

  **QA Scenarios**:
  ```
  Scenario: Config creation works without OpenAIConfig in main
    Tool: interactive_bash
    Steps:
      1. python -c "
        from psy_line.main import get_config
        c = get_config()
        print(f'Reddit: {c.reddit.user_agent}')
        print(f'Binance: {c.binance.testnet}')
      "
    Expected: Prints config values, no AttributeError for openai
    Evidence: .sisyphus/evidence/task-5-config.txt
  ```

  **Commit**: YES | Message: `cleanup(main): remove OpenAIConfig import and fallback` | Files: [`src/psy_line/main.py`]

---

- [ ] 6. Create .hermes/psy_line_config.yaml.example

  **What to do**:
  Create the directory `.hermes/` at project root, then create `psy_line_config.yaml.example`.

  This shows users how to register PSY_line as a Hermes Agent plugin.

  Content:
  ```yaml
  # =============================================================================
  # PSY_line — Hermes Agent Plugin Configuration
  # =============================================================================
  # Place this file at ~/.hermes/config.yaml or merge into existing config.
  #
  # PSY_line is an MCP Server that provides crypto retail behavior signals.
  # Hermes connects to it via MCP protocol — zero code integration.
  #
  # Prerequisites:
  # 1. Install: pip install psy-line
  # 2. Or run from source: python -m psy_line.main
  # 3. Set env vars (optional):
  #    - BINANCE_API_KEY / BINANCE_SECRET_KEY (for price data)
  #    - MINIMAX_API_KEY / MINIMAX_GROUP_ID (for MiniMax LLM)
  #    - PSY_LINE_CONFIG (path to config.yaml, optional)
  # =============================================================================

  mcp_servers:
    psy_line:
      # Command to start PSY_line MCP Server
      command: python
      args:
        - -m
        - psy_line.main
      # Environment variables (override defaults)
      env:
        MINIMAX_API_KEY: "${MINIMAX_API_KEY}"
        MINIMAX_GROUP_ID: "${MINIMAX_GROUP_ID}"
        BINANCE_API_KEY: "${BINANCE_API_KEY}"
        BINANCE_SECRET_KEY: "${BINANCE_SECRET_KEY}"

      # Tools exposed by PSY_line (auto-discovered via MCP list_tools)
      # After loading, Hermes will see:
      #   - run_behavior_scan  — scan symbol for retail behavior signal
      #   - get_quota_status   — check MiniMax API quota remaining
      #   - backtest_signals   — run backtest on historical data

  # === Memory Provider (Optional) ===
  # PSY_line can provide a MemoryProvider for storing sentiment history.
  # Uncomment to enable:
  # memory:
  #   provider: psy_line
  #   psy_line:
  #     mcp_server: psy_line
  #     collection: sentiment_history
  ```

  **Must NOT do**:
  - Do NOT create an actual `config.yaml` — only `.example`
  - Do NOT place this at `~/.hermes/` — it stays in the project repo as a reference

  **Recommended Agent Profile**:
  - Category: `quick` — single YAML file creation
  - Skills: `[]`
  - Omitted: n/a

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [] | Blocked By: []

  **References**:
  - Pattern: Hermes MCP server config via `mcp_servers.<name>` with `command` + `args` + `env`
  - PSY_line MCP tools: `run_behavior_scan`, `get_quota_status`, `backtest_signals`

  **Acceptance Criteria**:
  - [ ] File exists at `.hermes/psy_line_config.yaml.example`
  - [ ] YAML is syntactically valid
  - [ ] `command` and `args` correctly reference `psy_line.main`
  - [ ] README mentions this file in Hermes integration section

  **QA Scenarios**:
  ```
  Scenario: YAML is valid
    Tool: interactive_bash
    Steps:
      1. python -c "import yaml; yaml.safe_load(open('.hermes/psy_line_config.yaml.example'))"
    Expected: No yaml.YAMLError, dict loaded successfully
    Evidence: .sisyphus/evidence/task-6-yaml-valid.txt
  ```

  **Commit**: YES | Message: `docs(hermes): add Hermes plugin config example` | Files: [`.hermes/psy_line_config.yaml.example`]

---

- [ ] 7. Create plugins/memory/psy_line/ Memory Provider stub

  **What to do**:
  Create the directory structure `plugins/memory/psy_line/` with the following files:

  **`__init__.py`**:
  ```python
  """PSY_line memory provider for Hermes Agent.

  Provides MemoryProvider ABC implementation for storing and querying
  sentiment analysis history, behavioral signals, and market state snapshots.

  This is an optional plugin — PSY_line works without it (no memory dependency).
  """

  from typing import Any, Dict, List, Optional
  from datetime import datetime


  class PsyLineMemoryProvider:
      """Memory provider for PSY_line sentiment and signal history.

      Implements Hermes Agent's MemoryProvider ABC pattern.
      Stores sentiment analysis results, behavioral signals, and
      market states for historical query and analysis.
      """

      def __init__(
          self,
          collection: str = "sentiment_history",
          max_records: int = 10000,
      ):
          self.collection = collection
          self.max_records = max_records
          self._records: List[Dict[str, Any]] = []

      # ------------------------------------------------------------------
      # Hermes MemoryProvider Interface
      # ------------------------------------------------------------------

      async def remember(
          self,
          key: str,
          value: Dict[str, Any],
          metadata: Optional[Dict[str, Any]] = None,
      ) -> bool:
          """Store a memory record.

          Args:
              key: Unique identifier (e.g. 'BTC_signal_2026-05-25T12:00:00')
              value: The data to store (sentiment scores, signal, market state, etc.)
              metadata: Optional metadata (timestamp, source, tags)

          Returns:
              True if stored successfully
          """
          record = {
              "key": key,
              "value": value,
              "metadata": metadata or {},
              "timestamp": datetime.now().isoformat(),
          }
          self._records.append(record)

          # Enforce max_records limit (FIFO eviction)
          if len(self._records) > self.max_records:
              self._records = self._records[-self.max_records:]

          return True

      async def recall(
          self,
          key: str,
          limit: int = 1,
      ) -> List[Dict[str, Any]]:
          """Retrieve memory records by key prefix.

          Args:
              key: Key or key prefix to search for
              limit: Max number of records to return

          Returns:
              List of matching records (newest first)
          """
          matches = [r for r in self._records if r["key"].startswith(key)]
          return matches[-limit:][::-1]  # newest first

      async def forget(self, key: str) -> bool:
          """Remove memory records matching key prefix.

          Args:
              key: Key or key prefix to remove

          Returns:
              True if any records were removed
          """
          before = len(self._records)
          self._records = [r for r in self._records if not r["key"].startswith(key)]
          return len(self._records) < before

      async def clear(self) -> bool:
          """Clear all memory records."""
          self._records.clear()
          return True

      # ------------------------------------------------------------------
      # PSY_line-specific convenience methods
      # ------------------------------------------------------------------

      async def store_signal(
          self,
          symbol: str,
          signal: str,
          confidence: float,
          behavior_phase: str,
          sentiment_scores: Dict[str, float],
          market_state: Dict[str, Any],
      ) -> str:
          """Store a behavioral signal with full context.

          Returns the key used for storage.
          """
          timestamp = datetime.now()
          key = f"{symbol}_signal_{timestamp.strftime('%Y%m%d_%H%M%S')}"
          await self.remember(key, {
              "symbol": symbol,
              "signal": signal,
              "confidence": confidence,
              "behavior_phase": behavior_phase,
              "sentiment_scores": sentiment_scores,
              "market_state": market_state,
          }, metadata={
              "type": "behavior_signal",
              "source": "psy_line",
          })
          return key

      def get_stats(self) -> Dict[str, Any]:
          """Get memory provider statistics."""
          return {
              "collection": self.collection,
              "total_records": len(self._records),
              "max_records": self.max_records,
          }
  ```

  **`__init__.pyi`** (optional type stub, can skip):
  Empty for now — types are inline.

  **Must NOT do**:
  - Do NOT integrate this into PSY_line's main code yet (standalone module)
  - Do NOT register this provider — it's a stub for future use
  - Do NOT add external dependencies (pure python stdlib)

  **Recommended Agent Profile**:
  - Category: `unspecified-low` — single file creation, well-defined
  - Skills: `[]`
  - Omitted: n/a

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [] | Blocked By: []

  **References**:
  - Pattern: Hermes `plugins/memory/<name>/` structure with `MemoryProvider` ABC
  - Async methods follow Hermes interface pattern (remember/recall/forget/clear)

  **Acceptance Criteria**:
  - [ ] Directory exists at `plugins/memory/psy_line/`
  - [ ] `__init__.py` exports `PsyLineMemoryProvider` class
  - [ ] Class has `remember`, `recall`, `forget`, `clear` async methods
  - [ ] `python -c "from plugins.memory.psy_line import PsyLineMemoryProvider; print('OK')"` works (if sys.path includes project root)

  **QA Scenarios**:
  ```
  Scenario: Memory provider can store and recall
    Tool: interactive_bash
    Steps:
      1. cd psy_line && python -c "
        import sys; sys.path.insert(0, '.')
        from plugins.memory.psy_line import PsyLineMemoryProvider
        import asyncio
        mp = PsyLineMemoryProvider()
        async def test():
            await mp.remember('test_key', {'value': 42})
            r = await mp.recall('test_key')
            print(f'Recalled: {r}')
            await mp.forget('test_key')
            r2 = await mp.recall('test_key')
            print(f'After forget: {r2}')
        asyncio.run(test())
      "
    Expected: Recalls stored data, forgets successfully
    Evidence: .sisyphus/evidence/task-7-memory.txt
  ```

  **Commit**: YES | Message: `feat(hermes): add PsyLineMemoryProvider stub` | Files: [`plugins/memory/psy_line/__init__.py`]

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE.

- [ ] F1. Plan Compliance Audit — oracle
  **Verify**: All 7 tasks completed per spec. No scope creep. No missing files.
  **Command**: `diff <(grep '^- \[ \]' .sisyphus/plans/psy-line-implementation.md) <(git diff --name-only HEAD)` — zero unchecked tasks, all expected files changed.

- [ ] F2. Code Quality Review — unspecified-high
  **Verify**: No lint errors, no dead imports, no type errors, no unsafe patterns.
  **Command**: `python -m pytest tests/ -v 2>&1 | tail -20` — 51/51 passed.
  **Command**: `python -c "import ast; ast.parse(open('src/psy_line/sentiment_aggregator.py').read()); print('syntax OK')"`

- [ ] F3. Manual QA — unspecified-high
  **Verify**: Each task's QA scenario executes successfully.
  **Command**: Run each QA scenario from tasks 1-7.

- [ ] F4. Scope Fidelity Check — deep
  **Verify**: No changes outside scope. Architecture unchanged. No new dependencies beyond vaderSentiment.
  **Command**: `git diff --stat` — confirm only expected files changed.

## Commit Strategy
- Each task commits independently with its own message
- Commit order: Task 1, 3, 4, 6, 7 (Wave 1 parallel) → Task 2, 5 (Wave 2) → Verification

## Success Criteria
- [ ] All 51 existing tests pass
- [ ] Zero LSP errors across all source files
- [ ] `wait_for_slot()` exists and blocks correctly
- [ ] VADER fallback produces sentiment scores when LLM unavailable
- [ ] No OpenAI references in source code (main.py imports, pyproject.toml deps)
- [ ] Hermes plugin config example created
- [ ] Memory provider stub created
- [ ] All QA scenarios pass
- [ ] All 4 verification agents approve
