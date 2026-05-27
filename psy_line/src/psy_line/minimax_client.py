"""MiniMax client integrating TokenPlan MCP web_search and LLM API.

Provides:
- web_search via TokenPlan MCP (uvx minimax-coding-plan-mcp)
- sentiment analysis via MiniMax 2.7 LLM API
Both protected by RateLimiter.
"""

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from .rate_limiter import RateLimiter
from .types import SentimentResult, SentimentType

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个加密货币情绪分析师。分析每条评论的情绪，判断散户是看涨(bullish)、看跌(bearish)还是中立(neutral)。

返回格式 (必须是有效JSON数组):
[{"id": "comment_id_1", "sentiment": "bullish|bearish|neutral", "score": -1.0到1.0, "reasoning": "20字以内理由"}]

评分规则:
- score: -1.0(极度看跌) 到 1.0(极度看涨)
- 0.0附近表示中立
- 包含"to the moon", "HODL", "buy the dip"等倾向看涨
- 包含"crash", "scam", "sell", "panic"等倾向看跌"""


@dataclass
class SearchResult:
    """Web search result from MiniMax TokenPlan MCP."""
    title: str
    url: str
    snippet: str
    source: str
    timestamp: datetime = field(default_factory=datetime.now)


class MiniMaxClient:
    """Client for MiniMax LLM API and TokenPlan MCP web_search."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_host: str = "https://api.minimaxi.com",
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        self.api_host = api_host or os.environ.get("MINIMAX_API_HOST", "https://api.minimaxi.com")
        self.rate_limiter = rate_limiter or RateLimiter()
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    def web_search(self, query: str, max_retries: int = 3) -> list[SearchResult]:
        """Execute web search via TokenPlan MCP subprocess.

        Protected by RateLimiter (search quota: 150/hour).
        """
        if not self.rate_limiter.can_use_search():
            logger.warning("Search quota exhausted, skipping")
            return []

        for attempt in range(max_retries):
            wait = self.rate_limiter.get_wait_time()
            if wait > 0:
                logger.info(f"Waiting {wait:.0f}s before search")
                time.sleep(wait)

            try:
                # Build JSON-RPC request for web_search tool
                rpc_request = json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "web_search",
                        "arguments": {"query": query},
                    },
                })

                result = subprocess.run(
                    ["uvx", "minimax-coding-plan-mcp", "-y"],
                    input=rpc_request,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    response = json.loads(result.stdout)
                    search_results = self._parse_search_response(response)
                    self.rate_limiter.record_search_usage()
                    self.rate_limiter.on_success()
                    return search_results
                elif "429" in result.stderr or "rate limit" in result.stderr.lower():
                    self.rate_limiter.on_429_error()
                    logger.warning(f"Search rate limited (attempt {attempt+1})")
                    continue
                else:
                    logger.warning(f"Search failed: {result.stderr[:200]}")
                    return []

            except subprocess.TimeoutExpired:
                logger.warning("Search subprocess timed out")
                return []
            except json.JSONDecodeError as e:
                logger.warning(f"Search response parse error: {e}")
                return []
            except FileNotFoundError:
                logger.error("uvx not found. Install with: pip install uv")
                return []
            except Exception as e:
                logger.error(f"Search error: {e}")
                return []

        return []

    def analyze_sentiment(
        self,
        texts: List[str],
        max_retries: int = 3,
        batch_size: int = 30,
    ) -> list[SentimentResult]:
        """Analyze sentiment of texts using MiniMax 2.7 LLM API.

        Protected by RateLimiter (LLM quota: 1300/5h or 900/5h).
        Batches texts into groups of batch_size.
        """
        if not texts:
            return []

        if not self.rate_limiter.can_use_llm():
            logger.warning("LLM quota exhausted, returning neutral results")
            return [
                SentimentResult(id=f"text_{i}", sentiment=SentimentType.NEUTRAL, score=0.0, reasoning="Quota exhausted")
                for i in range(len(texts))
            ]

        all_results = []
        for i in range(0, len(texts), batch_size):
            batch = [{"id": f"text_{i+j}", "body": t} for j, t in enumerate(texts[i:i + batch_size])]
            batch_results = self._analyze_batch(batch, max_retries)
            all_results.extend(batch_results)

            if i + batch_size < len(texts):
                self.rate_limiter.record_llm_usage()
                wait = self.rate_limiter.get_wait_time()
                if wait > 0:
                    time.sleep(wait)

        return all_results

    def _analyze_batch(self, batch: List[Dict[str, Any]], max_retries: int = 3) -> list[SentimentResult]:
        """Analyze a single batch of texts."""
        comments_json = json.dumps(
            [{"id": c.get("id", f"t_{i}"), "text": c.get("body", c.get("text", ""))[:500]} for i, c in enumerate(batch)],
            ensure_ascii=False,
        )

        user_prompt = f"分析以下加密货币评论的情绪:\n\n{comments_json}\n\n返回JSON数组:"

        for attempt in range(max_retries):
            wait = self.rate_limiter.get_wait_time()
            if wait > 0:
                time.sleep(wait)

            try:
                response = self._session.post(
                    f"{self.api_host}/v1/text/chatcompletion_v2",
                    json={
                        "model": "MiniMax-M2.7",
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 4000,
                    },
                    timeout=60,
                )

                if response.status_code == 429:
                    self.rate_limiter.on_429_error()
                    logger.warning(f"LLM rate limited (attempt {attempt+1})")
                    continue

                response.raise_for_status()
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                # Parse JSON from content (may have markdown code blocks)
                parsed = self._parse_json_response(content)
                results = []
                for item in parsed:
                    try:
                        sentiment_str = item.get("sentiment", "neutral").lower()
                        if sentiment_str not in ["bullish", "bearish", "neutral"]:
                            sentiment_str = "neutral"
                        results.append(SentimentResult(
                            id=item.get("id", ""),
                            sentiment=SentimentType(sentiment_str),
                            score=max(-1.0, min(1.0, float(item.get("score", 0.0)))),
                            reasoning=item.get("reasoning", "")[:50],
                        ))
                    except (ValueError, TypeError):
                        results.append(SentimentResult(id=item.get("id", ""), sentiment=SentimentType.NEUTRAL, score=0.0, reasoning="Parse error"))

                self.rate_limiter.record_llm_usage()
                self.rate_limiter.on_success()
                return results

            except requests.exceptions.RequestException as e:
                logger.error(f"LLM API error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                continue

        # Fallback: return neutral for all
        return [
            SentimentResult(id=c.get("id", f"t_{i}"), sentiment=SentimentType.NEUTRAL, score=0.0, reasoning="Analysis failed")
            for i, c in enumerate(batch)
        ]

    def _parse_json_response(self, content: str) -> List[Dict[str, Any]]:
        """Parse JSON from LLM response, handling markdown code blocks."""
        # Try to extract JSON from markdown code blocks
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL)
        if match:
            content = match.group(1)
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON: {content[:200]}")
            return []

    def _parse_search_response(self, response: Dict[str, Any]) -> List[SearchResult]:
        """Parse JSON-RPC response into SearchResult list."""
        results = []
        try:
            content = response.get("result", {}).get("content", [])
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    # Parse text into SearchResult
                    # Format varies, try to extract
                    results.append(SearchResult(
                        title="Search Result",
                        url="",
                        snippet=text[:500],
                        source="minimax_web_search",
                    ))
        except Exception as e:
            logger.warning(f"Search response parse error: {e}")
        return results

    def get_quota_status(self) -> Dict[str, Any]:
        """Returns current quota status."""
        return self.rate_limiter.get_remaining_quota()
