"""
Execution & Portfolio Domain Models.
Tracks paper and live positions, fills, margin allocation, and PnL.
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from src.strategies.models import SignalDirection


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"


class PositionStatus(str, Enum):
    PENDING_ENTRY = "PENDING_ENTRY"
    OPEN = "OPEN"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class PositionRecord(BaseModel):
    position_id: str
    signal_id: str
    symbol: str
    direction: SignalDirection
    status: PositionStatus = PositionStatus.PENDING_ENTRY
    entry_time: int
    entry_price: float
    current_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    initial_contracts: float
    remaining_contracts: float
    allocated_margin_usd: float
    leverage: float = 3.0
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    realized_pnl_usd: float = 0.0
    unrealized_pnl_usd: float = 0.0
    total_fees_usd: float = 0.0
    exit_price: Optional[float] = None
    exit_time: Optional[int] = None
    exit_reason: Optional[str] = None

