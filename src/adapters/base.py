"""
Abstract Base Class for Exchange Adapters.
Ensures consistent interface across all exchange implementations.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from src.core.models import Candle, Trade, Ticker, OpenInterestRecord, FundingRateRecord, OrderBook


class BaseExchangeAdapter(ABC):
    def __init__(self, exchange_id: str):
        self.exchange_id = exchange_id

    @abstractmethod
    def load_markets(self, reload: bool = False) -> Dict[str, Any]:
        """Load and cache available markets."""
        pass

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100, since: Optional[int] = None) -> List[Candle]:
        """Fetch historical candlestick data normalized to Candle domain model."""
        pass

    @abstractmethod
    def fetch_trades(self, symbol: str, limit: int = 100, since: Optional[int] = None) -> List[Trade]:
        """Fetch raw individual trades with aggressor side information."""
        pass

    @abstractmethod
    def fetch_ticker(self, symbol: str) -> Ticker:
        """Fetch current 24h ticker metrics."""
        pass

    @abstractmethod
    def fetch_tickers(self, symbols: Optional[List[str]] = None) -> Dict[str, Ticker]:
        """Fetch all tickers or specific tickers in batch."""
        pass

    @abstractmethod
    def fetch_open_interest(self, symbol: str) -> OpenInterestRecord:
        """Fetch current open interest."""
        pass

    @abstractmethod
    def fetch_funding_rate(self, symbol: str) -> FundingRateRecord:
        """Fetch current and predicted funding rate."""
        pass

    @abstractmethod
    def fetch_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """Fetch order book snapshot (bids and asks)."""
        pass

