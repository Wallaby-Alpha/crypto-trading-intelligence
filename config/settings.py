"""
Configuration management for the Crypto Trading Intelligence System.
Loads environment variables, config files, and provides type-checked settings.
"""
from typing import List, Optional
from pydantic import BaseModel, Field
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

class ExchangeConfig(BaseModel):
    name: str = "weex"
    api_key: Optional[str] = os.getenv("WEEX_API_KEY", "")
    secret: Optional[str] = os.getenv("WEEX_API_SECRET", "")
    passphrase: Optional[str] = os.getenv("WEEX_PASSPHRASE", "")
    rate_limit: bool = True
    timeout_ms: int = 15000
    sandbox: bool = False

class UniverseConfig(BaseModel):
    max_symbols: int = 50
    min_24h_volume_usd: float = 5_000_000.0  # $5M USD minimum volume
    max_spread_pct: float = 0.20             # Max 0.20% bid-ask spread
    min_volatility_pct: float = 0.5          # Minimum 24h range volatility %
    min_open_interest_usd: float = 500_000.0 # Minimum OI
    refresh_interval_hours: int = 4
    priority_symbols: List[str] = Field(
        default_factory=lambda: [
            "BTC/USDT:USDT",
            "ETH/USDT:USDT",
            "SOL/USDT:USDT",
            "TAO/USDT:USDT",
            "SUI/USDT:USDT",
            "DOGE/USDT:USDT",
            "AVAX/USDT:USDT",
            "LINK/USDT:USDT",
            "XRP/USDT:USDT",
            "NEAR/USDT:USDT"
        ]
    )

class DatabaseConfig(BaseModel):
    db_path: str = str(DATA_DIR / "market_intelligence.db")
    wal_mode: bool = True
    timeout_seconds: float = 30.0

class CollectorConfig(BaseModel):
    timeframes: List[str] = Field(default_factory=lambda: ["1m", "5m", "15m", "1h", "4h"])
    candle_history_limit: int = 200
    trade_limit: int = 150
    oi_poll_interval_sec: int = 30
    funding_poll_interval_sec: int = 120
    orderbook_depth: int = 20

class TelegramConfig(BaseModel):
    bot_token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id: Optional[str] = os.getenv("TELEGRAM_CHAT_ID", "")

class SystemSettings(BaseModel):
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    collector: CollectorConfig = Field(default_factory=CollectorConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    telegram_bot_token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: Optional[str] = os.getenv("TELEGRAM_CHAT_ID", "")

    @property
    def db_path(self) -> str:
        return self.db.db_path

# Global settings singleton
settings = SystemSettings()
