"""
Domain models for Trading Event Detection Engine.
Covers Liquidity Sweeps, Market Structure, Failed Acceptance, CVD Divergence, OI behavior, and VWAP events.
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SwingType(str, Enum):
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"


class SwingPoint(BaseModel):
    index: int
    timestamp: int
    datetime: Optional[str] = None
    price: float
    type: SwingType
    confirmation_index: int       # Strictly prevented lookahead: index at which point was confirmed
    confirmation_timestamp: int
    left_bars: int = 3
    right_bars: int = 3
    is_broken: bool = False
    is_swept: bool = False


class LiquidityLevelType(str, Enum):
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"
    EQUAL_HIGHS = "EQUAL_HIGHS"
    EQUAL_LOWS = "EQUAL_LOWS"
    SESSION_HIGH = "SESSION_HIGH"
    SESSION_LOW = "SESSION_LOW"
    PREV_DAY_HIGH = "PREV_DAY_HIGH"
    PREV_DAY_LOW = "PREV_DAY_LOW"
    RANGE_HIGH = "RANGE_HIGH"
    RANGE_LOW = "RANGE_LOW"


class LiquidityLevel(BaseModel):
    level_type: LiquidityLevelType
    price: float
    timestamp: int
    datetime: Optional[str] = None
    touch_count: int = 1
    tolerance_pct: float = 0.08
    is_active: bool = True


class SweepDirection(str, Enum):
    BULLISH_SWEEP_LOW = "BULLISH_SWEEP_LOW"     # Swept low, reclaimed -> Potential Long
    BEARISH_SWEEP_HIGH = "BEARISH_SWEEP_HIGH"   # Swept high, reclaimed down -> Potential Short


class LiquiditySweepEvent(BaseModel):
    symbol: str
    timeframe: str
    timestamp: int
    datetime: Optional[str] = None
    direction: SweepDirection
    level_swept_type: LiquidityLevelType
    level_price: float
    extreme_price: float                  # Highest high or lowest low of the sweep
    penetration_pct: float
    penetration_atr_ratio: float
    candles_outside: int                  # Number of candles price was outside before close back inside
    rejection_strength_pct: float         # Wick % or displacement back inside
    reclaimed_close_price: float


class FailedAcceptanceType(str, Enum):
    FAILED_BREAKOUT_ABOVE = "FAILED_BREAKOUT_ABOVE"
    FAILED_BREAKDOWN_BELOW = "FAILED_BREAKDOWN_BELOW"
    FAILED_RECLAIM_SUPPORT = "FAILED_RECLAIM_SUPPORT"
    FAILED_RECLAIM_RESISTANCE = "FAILED_RECLAIM_RESISTANCE"


class FailedAcceptanceEvent(BaseModel):
    symbol: str
    timeframe: str
    timestamp: int
    datetime: Optional[str] = None
    event_type: FailedAcceptanceType
    level_price: float
    extreme_price: float
    closes_beyond: int
    volume_exhaustion_ratio: Optional[float] = None
    reversal_confirmed: bool = True
    description: str


class MarketStructureType(str, Enum):
    HIGHER_HIGH = "HIGHER_HIGH"
    HIGHER_LOW = "HIGHER_LOW"
    LOWER_HIGH = "LOWER_HIGH"
    LOWER_LOW = "LOWER_LOW"
    BOS_BULLISH = "BOS_BULLISH"       # Break of Structure in uptrend continuation
    BOS_BEARISH = "BOS_BEARISH"       # Break of Structure in downtrend continuation
    CHOCH_BULLISH = "CHOCH_BULLISH"   # Change of Character: lower high broken upward
    CHOCH_BEARISH = "CHOCH_BEARISH"   # Change of Character: higher low broken downward
    MSS_BULLISH = "MSS_BULLISH"       # Market Structure Shift with displacement
    MSS_BEARISH = "MSS_BEARISH"       # Market Structure Shift with displacement


class MarketStructureEvent(BaseModel):
    symbol: str
    timeframe: str
    timestamp: int
    datetime: Optional[str] = None
    event_type: MarketStructureType
    broken_level_price: float
    trigger_close_price: float
    displacement_ratio: float         # Candle body relative to ATR (>= 1.5 indicates displacement)
    current_trend: str                # "BULLISH", "BEARISH", "RANGING"


class CVDDivergenceType(str, Enum):
    BULLISH_CVD_ABSORPTION = "BULLISH_CVD_ABSORPTION"   # Price lower low, CVD higher low
    BEARISH_CVD_ABSORPTION = "BEARISH_CVD_ABSORPTION"   # Price higher high, CVD lower high


class CVDDivergenceEvent(BaseModel):
    symbol: str
    timeframe: str
    timestamp: int
    datetime: Optional[str] = None
    divergence_type: CVDDivergenceType
    price_swing_1: float
    price_swing_2: float
    cvd_swing_1: float
    cvd_swing_2: float
    lookback_bars: int
    strength_score: float              # 0 to 100 based on magnitude of divergence


class OIRegimeType(str, Enum):
    PRICE_UP_OI_UP = "PRICE_UP_OI_UP"          # Aggressive Long Buildup
    PRICE_UP_OI_DOWN = "PRICE_UP_OI_DOWN"      # Short Squeeze / Covering
    PRICE_DOWN_OI_UP = "PRICE_DOWN_OI_UP"      # Aggressive Short Buildup
    PRICE_DOWN_OI_DOWN = "PRICE_DOWN_OI_DOWN"  # Long Liquidation / Unwinding


class OIBehaviorEvent(BaseModel):
    symbol: str
    timestamp: int
    datetime: Optional[str] = None
    regime: OIRegimeType
    oi_change_pct_15m: float
    oi_acceleration: float
    is_unusual_expansion: bool = False
    context_note: str


class VWAPVolumeEventType(str, Enum):
    VWAP_REJECTION_BEARISH = "VWAP_REJECTION_BEARISH"
    VWAP_REJECTION_BULLISH = "VWAP_REJECTION_BULLISH"
    VWAP_RECLAIM_BULLISH = "VWAP_RECLAIM_BULLISH"
    VWAP_LOSS_BEARISH = "VWAP_LOSS_BEARISH"
    HIGH_VOLUME_REJECTION = "HIGH_VOLUME_REJECTION"
    LOW_VOLUME_RETEST = "LOW_VOLUME_RETEST"
    POC_REJECTION = "POC_REJECTION"


class VWAPVolumeEvent(BaseModel):
    symbol: str
    timeframe: str
    timestamp: int
    datetime: Optional[str] = None
    event_type: VWAPVolumeEventType
    reference_price: float            # VWAP or POC price
    candle_close: float
    distance_pct: float
    volume_ratio: float               # Relative to 20-period moving average


class MarketEventBundle(BaseModel):
    symbol: str
    timeframe: str
    timestamp: int
    datetime: Optional[str] = None
    sweeps: List[LiquiditySweepEvent] = Field(default_factory=list)
    failed_acceptances: List[FailedAcceptanceEvent] = Field(default_factory=list)
    structure_events: List[MarketStructureEvent] = Field(default_factory=list)
    cvd_divergences: List[CVDDivergenceEvent] = Field(default_factory=list)
    oi_events: List[OIBehaviorEvent] = Field(default_factory=list)
    vwap_events: List[VWAPVolumeEvent] = Field(default_factory=list)

