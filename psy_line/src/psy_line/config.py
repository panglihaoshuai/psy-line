"""Configuration management for PSY_line."""

import os
import yaml
from pydantic import BaseModel, Field
from typing import List, Optional


class RedditConfig(BaseModel):
    """Reddit API configuration."""
    client_id: str
    client_secret: str
    user_agent: str = "PSY_line/1.0 (Trading Bot)"
    keywords: List[str] = Field(default_factory=list)
    keywords_mode: str = "include"  # "include" or "exclude"


class OpenAIConfig(BaseModel):
    """OpenAI API configuration."""
    api_key: str
    model: str = "gpt-4o"
    batch_size: int = 30
    max_requests_per_minute: int = 20


class BinanceConfig(BaseModel):
    """Binance API configuration."""
    api_key: str
    secret_key: str
    testnet: bool = True


class TradingConfig(BaseModel):
    """Trading parameters."""
    symbol: str = "BTCUSDT"
    buy_threshold: float = -0.6
    sell_threshold: float = 0.6
    position_size: float = 0.1


class Config(BaseModel):
    """Root configuration."""
    reddit: RedditConfig
    openai: Optional[OpenAIConfig] = None
    binance: BinanceConfig
    subreddits: List[str] = Field(default_factory=lambda: [
        "CryptoCurrency", "SatoshiBets", "Bitcoin", "ethereum", "SOLMarkets", "ethtrader"
    ])
    trading: TradingConfig = Field(default_factory=TradingConfig)

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """Load configuration from YAML file with environment variable expansion."""
        with open(path, "r") as f:
            raw_config: dict[str, object] = yaml.safe_load(f) or {}

        # Expand environment variables
        raw_config = cls._expand_env_vars(raw_config)

        # Override with environment variables if set
        raw_config = cls._apply_env_overrides(raw_config)

        return cls(**raw_config)  # pyright: ignore[reportArgumentType]

    @classmethod
    def _expand_env_vars(cls, obj):
        """Recursively expand ${VAR} patterns in config."""
        if isinstance(obj, dict):
            return {k: cls._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [cls._expand_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_var = obj[2:-1]
            return os.environ.get(env_var, "")
        return obj

    @classmethod
    def _apply_env_overrides(cls, config: dict[str, object]) -> dict[str, object]:
        """Apply environment variable overrides for sensitive fields."""
        env_mappings = {
            "REDDIT_CLIENT_ID": ("reddit", "client_id"),
            "REDDIT_CLIENT_SECRET": ("reddit", "client_secret"),
            "OPENAI_API_KEY": ("openai", "api_key"),
            "BINANCE_API_KEY": ("binance", "api_key"),
            "BINANCE_SECRET_KEY": ("binance", "secret_key"),
        }

        for env_var, (section, key) in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                section_data = config.get(section)
                if isinstance(section_data, dict):
                    section_data[key] = value
        return config

    def validate_required(self) -> None:
        """Validate that all required fields are set."""
        errors = []

        if not self.reddit.client_id:
            errors.append("REDDIT_CLIENT_ID is required")
        if not self.reddit.client_secret:
            errors.append("REDDIT_CLIENT_SECRET is required")
        if self.openai is None or not self.openai.api_key:
            pass  # OpenAI is no longer required — removed in refactor
        if not self.binance.api_key:
            errors.append("BINANCE_API_KEY is required")
        if not self.binance.secret_key:
            errors.append("BINANCE_SECRET_KEY is required")

        if errors:
            raise ValueError("Missing required configuration:\n" + "\n".join(f"  - {e}" for e in errors))
