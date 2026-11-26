"""
Strategy & Signal Domain Models.
Strictly distinguishes:
1. Setup DETECTED
2. Setup CONFIRMED
3. Entry TRIGGERED
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SignalDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class SignalState(str, Enum):
    DETECTED = "DETECTED"    # Preliminary setup detected (e.g. sweep underway)
    CONFIRMED = "CONFIRMED"  # Price action & orderflow confirmation verified
    TRIGGERED = "TRIGGERED"  # Entry price reached and filled (paper or live)
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class SignalCategory(str, Enum):
    NO_SIGNAL = "NO_SIGNAL"      # 0–49
    WATCHLIST = "WATCHLIST"      # 50–64
    QUALIFIED = "QUALIFIED"      # 65–79
    STRONG = "STRONG"            # 80–89
    EXCEPTIONAL = "EXCEPTIONAL"  # 90–100


class EntryMethod(str, Enum):
    MARKET_CONFIRMATION = "MARKET_CONFIRMATION"
    LIMIT_RETRACEMENT = "LIMIT_RETRACEMENT"
    LIMIT_SWEPT_LEVEL = "LIMIT_SWEPT_LEVEL"
    LIMIT_STRUCTURE_LEVEL = "LIMIT_STRUCTURE_LEVEL"


class ScoreBreakdown(BaseModel):
    liquidity_quality: float = 0.0     # Max 15
    market_structure: float = 0.0      # Max 15
    oi_behavior: float = 0.0           # Max 15
    cvd_confirmation: float = 0.0      # Max 15
    volume_displacement: float = 0.0   # Max 10
    vwap_context: float = 0.0          # Max 10
    htf_alignment: float = 0.0         # Max 10
    funding_context: float = 0.0       # Max 5
    risk_reward: float = 0.0           # Max 5
    total_score: float = 0.0           # 0 to 100
    category: SignalCategory = SignalCategory.NO_SIGNAL


class TradeSignal(BaseModel):
    id: str
    strategy_name: str
    symbol: str
    timeframe: str
    direction: SignalDirection
    state: SignalState = SignalState.DETECTED
    timestamp: int
    datetime: Optional[str] = None
    current_price: float
    score: ScoreBreakdown
    entry_method: EntryMethod = EntryMethod.MARKET_CONFIRMATION
    proposed_entry: float
    stop_loss: float
    tp1: float                         # 1.0R
    tp2: float                         # 2.0R
    tp3: float                         # 3.0R
    risk_reward_tp2: float
    atr: float
    position_size_usd: float = 0.0
    contracts: float = 0.0
    confirmations: List[str] = Field(default_factory=list)
    invalidation_condition: str = ""
    is_active: bool = True

    @property
    def signal_id(self) -> str:
        return self.id

    @property
    def entry_price(self) -> float:
        return self.proposed_entry

    @property
    def category(self) -> SignalCategory:
        return self.score.category

    @property
    def risk_reward(self) -> float:
        return self.risk_reward_tp2

