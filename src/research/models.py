"""
Research & Backtesting Domain Models.
Tracks granular trade lifecycle, execution costs (fees, slippage, funding carry),
performance metrics, and experimental hypothesis parameters.
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from src.strategies.models import SignalDirection, SignalCategory


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED_STOP = "CLOSED_STOP"
    CLOSED_TP1_PARTIAL = "CLOSED_TP1_PARTIAL"
    CLOSED_TP2_PARTIAL = "CLOSED_TP2_PARTIAL"
    CLOSED_TP3_FULL = "CLOSED_TP3_FULL"
    CLOSED_BREAKEVEN = "CLOSED_BREAKEVEN"
    CLOSED_TIMEOUT = "CLOSED_TIMEOUT"
    CLOSED_INVALIDATED = "CLOSED_INVALIDATED"


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    BREAKEVEN = "BREAKEVEN"
    TAKE_PROFIT_1 = "TAKE_PROFIT_1"
    TAKE_PROFIT_2 = "TAKE_PROFIT_2"
    TAKE_PROFIT_3 = "TAKE_PROFIT_3"
    TIMEOUT = "TIMEOUT"
    STRUCTURE_INVAL = "STRUCTURE_INVAL"


class TradeRecord(BaseModel):
    trade_id: str
    signal_id: str
    symbol: str
    timeframe: str
    strategy_name: str
    direction: SignalDirection
    entry_timestamp: int
    entry_datetime: Optional[str] = None
    entry_price: float
    exit_timestamp: Optional[int] = None
    exit_datetime: Optional[str] = None
    exit_price: Optional[float] = None
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    initial_risk_usd: float
    position_size_usd: float
    contracts: float
    r_multiple: float = 0.0
    gross_pnl_usd: float = 0.0
    net_pnl_usd: float = 0.0
    commission_paid: float = 0.0
    slippage_cost: float = 0.0
    status: TradeStatus = TradeStatus.OPEN
    exit_reason: Optional[ExitReason] = None
    holding_period_candles: int = 0
    signal_score: float = 0.0
    signal_category: SignalCategory = SignalCategory.QUALIFIED


class BacktestReport(BaseModel):
    experiment_name: str
    symbol: str
    timeframe: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate_pct: float
    avg_winner_r: float
    avg_loser_r: float
    profit_factor: float
    net_profit_usd: float
    avg_r_multiple: float
    max_drawdown_usd: float
    max_drawdown_pct: float
    expectancy_r: float
    expectancy_usd: float
    long_trades: int
    long_win_rate_pct: float
    short_trades: int
    short_win_rate_pct: float
    performance_by_score_tier: Dict[str, Any] = Field(default_factory=dict)
    performance_by_strategy: Dict[str, Any] = Field(default_factory=dict)
    trades: List[TradeRecord] = Field(default_factory=list)

