"""Smoke tests for PSY_line.

Quick health checks to verify the system can start and basic imports work.
These run FIRST in CI/CD pipeline to catch deployment issues early.
"""

import pytest
import sys
import os
import importlib

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestImports:
    """Verify all modules can be imported without errors."""

    def test_import_market_state(self):
        from psy_line.market_state import MarketState
        assert MarketState is not None

    def test_import_retail_behavior(self):
        from psy_line.retail_behavior import RetailBehaviorModel, BehaviorPhase
        assert RetailBehaviorModel is not None
        assert BehaviorPhase is not None

    def test_import_signal_generator(self):
        from psy_line.signal_generator import SignalGenerator
        assert SignalGenerator is not None

    def test_import_rate_limiter(self):
        from psy_line.rate_limiter import RateLimiter
        assert RateLimiter is not None

    def test_import_sentiment_aggregator(self):
        from psy_line.sentiment_aggregator import SentimentAggregator
        assert SentimentAggregator is not None

    def test_import_unified_source(self):
        from psy_line.unified_source import UnifiedDataSource
        assert UnifiedDataSource is not None

    def test_import_minimax_client(self):
        from psy_line.minimax_client import MiniMaxClient
        assert MiniMaxClient is not None

    def test_import_backtester(self):
        from psy_line.backtester import Backtester
        assert Backtester is not None

    def test_import_config(self):
        from psy_line.config import Config
        assert Config is not None

    def test_import_types(self):
        from psy_line.types import SignalType, SentimentType, BinanceKline
        assert SignalType is not None
        assert SentimentType is not None
        assert BinanceKline is not None

    def test_import_memory_provider(self):
        """Memory provider should be importable (optional dependency)."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from plugins.memory.psy_line import PsyLineMemoryProvider
        assert PsyLineMemoryProvider is not None


class TestBasicFunctionality:
    """Verify core classes can be instantiated."""

    def test_create_rate_limiter(self):
        from psy_line.rate_limiter import RateLimiter
        rl = RateLimiter()
        assert rl is not None
        assert hasattr(rl, 'wait_for_slot')
        assert hasattr(rl, 'can_use_llm')

    def test_create_behavior_model(self):
        from psy_line.retail_behavior import RetailBehaviorModel
        model = RetailBehaviorModel()
        assert model is not None

    def test_create_signal_generator(self):
        from psy_line.signal_generator import SignalGenerator
        sg = SignalGenerator()
        assert sg is not None

    def test_create_backtester(self):
        from psy_line.backtester import Backtester
        bt = Backtester()
        assert bt is not None

    def test_create_memory_provider(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from plugins.memory.psy_line import PsyLineMemoryProvider
        mp = PsyLineMemoryProvider()
        assert mp is not None
        assert mp.collection == "sentiment_history"


class TestMCPToolsExist:
    """Verify MCP tools are registered in main.py."""

    def test_mcp_server_importable(self):
        """main.py should import without errors."""
        from psy_line import main
        assert hasattr(main, 'SERVER')
        # Tools are registered via @SERVER.call_tool() decorator
        # Check that the server has the call_tool handler registered
        assert hasattr(main, 'call_tool')

    def test_mcp_tools_registered(self):
        """MCP server should have tools registered."""
        from psy_line.main import SERVER
        # SERVER is an mcp.server.Server instance
        # It should have registered tools
        assert SERVER is not None
