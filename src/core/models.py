"""
Domain data models for market data, derivatives, and data quality states.
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class DataQualityStatus(str, Enum):
    VALID = "VALID"
    GOOD = "VALID"
    STALE = "STALE"
    INCOMPLETE = "INCOMPLETE"
    ANOMALOUS = "ANOMALOUS"
    SUSPECT = "SUSPECT"
    MISSING = "MISSING"


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
    UNKNOWN = "unknown"


class Candle(BaseModel):
    symbol: str
    exchange: str
    timeframe: str
    timestamp: int              # Epoch milliseconds
    datetime: Optional[str] = None
    open: float
    high: float
    low: float
    close: float
    volume: float               # Base volume
    quote_volume: Optional[float] = None
    buy_volume: Optional[float] = None
    sell_volume: Optional[float] = None
    is_closed: bool = True      # Non-negotiable: incomplete candles must be flagged
    source: str = "direct"
    quality_status: DataQualityStatus = DataQualityStatus.VALID


class Trade(BaseModel):
    id: Optional[str] = None
    symbol: str
    exchange: str
    timestamp: int
    datetime: Optional[str] = None
    price: float
    amount: float
    cost: Optional[float] = None
    side: TradeSide
    is_buyer_maker: Optional[bool] = None


class Ticker(BaseModel):
    symbol: str
    exchange: str
    timestamp: int
    datetime: Optional[str] = None
    last: float
    bid: float
    ask: float
    spread: float
    spread_pct: float
    high_24h: float
    low_24h: float
    volume_24h: float
    quote_volume_24h: float
    percentage_24h: Optional[float] = 0.0
    quality_status: DataQualityStatus = DataQualityStatus.VALID


class OpenInterestRecord(BaseModel):
    symbol: str
    exchange: str
    timestamp: int
    datetime: Optional[str] = None
    open_interest_amount: float = 0.0  # Contracts / coins
    open_interest_usd: Optional[float] = None
    price_at_timestamp: Optional[float] = None
    source: str = "direct"
    quality_status: DataQualityStatus = DataQualityStatus.VALID

    @property
    def open_interest(self) -> float:
        return self.open_interest_amount


class OpenInterestMetrics(BaseModel):
    symbol: str
    exchange: str
    timestamp: int
    current_oi: float
    oi_change_1m: Optional[float] = None
    oi_change_5m: Optional[float] = None
    oi_change_15m: Optional[float] = None
    oi_change_30m: Optional[float] = None
    oi_change_60m: Optional[float] = None
    oi_pct_change_1m: Optional[float] = None
    oi_pct_change_5m: Optional[float] = None
    oi_pct_change_15m: Optional[float] = None
    oi_pct_change_30m: Optional[float] = None
    oi_pct_change_60m: Optional[float] = None
    oi_acceleration: Optional[float] = None
    oi_divergence_flag: Optional[str] = None     # 'PRICE_UP_OI_UP', etc.
    quality_status: DataQualityStatus = DataQualityStatus.VALID


class FundingRateRecord(BaseModel):
    symbol: str
    exchange: str
    timestamp: int
    datetime: Optional[str] = None
    funding_rate: float
    predicted_funding_rate: Optional[float] = None
    funding_interval_hours: int = 8
    next_funding_timestamp: Optional[int] = None
    percentile_30d: Optional[float] = None
    source: str = "direct"
    quality_status: DataQualityStatus = DataQualityStatus.VALID


class CVDRecord(BaseModel):
    symbol: str
    exchange: str
    timeframe: str
    timestamp: int
    datetime: Optional[str] = None
    buy_volume: float
    sell_volume: float
    delta: float                # buy_volume - sell_volume
    cumulative_delta: float
    cvd_momentum: Optional[float] = None
    is_exchange_provided: bool = False
    quality_status: DataQualityStatus = DataQualityStatus.VALID


class OrderBook(BaseModel):
    symbol: str
    exchange: str
    timestamp: int
    datetime: Optional[str] = None
    bids: List[List[float]]     # [[price, amount], ...]
    asks: List[List[float]]
    spread: float
    spread_pct: float
