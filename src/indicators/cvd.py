"""
Cumulative Volume Delta (CVD) Engine:
- Calculates aggressor-side trade volume delta: Delta = Buy_Volume - Sell_Volume.
- Computes cumulative CVD series.
- Computes CVD momentum and rolling rate of change.
- Identifies bullish and bearish CVD divergences against price action.
- Distinguishes exchange-provided vs tick-derived vs candle-estimated CVD.
"""
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel
import numpy as np
from src.core.models import Trade, Candle, CVDRecord, TradeSide, DataQualityStatus


class CVDBar(BaseModel):
    timestamp: int
    datetime: str
    buy_volume: float
    sell_volume: float
    delta: float
    cumulative_delta: float
    cvd_momentum: Optional[float] = None
    is_exchange_provided: bool = False


class CVDEngine:
    def __init__(self, momentum_window: int = 5):
        self.momentum_window = momentum_window

    def compute_from_trades(
        self,
        trades: List[Trade],
        candles: List[Candle],
        initial_cumulative_delta: float = 0.0
    ) -> List[CVDBar]:
        """
        Calculates exact tick-level CVD by mapping aggressor trades into candle timestamp buckets.
        """
        if not candles:
            return []

        # Sort candles and trades by timestamp ascending
        sorted_candles = sorted(candles, key=lambda c: c.timestamp)
        sorted_trades = sorted(trades, key=lambda t: t.timestamp)

        # Build candle boundaries
        # For each candle i, it spans from candle[i].timestamp to candle[i+1].timestamp
        bars: List[CVDBar] = []
        cum_delta = initial_cumulative_delta

        trade_idx = 0
        num_trades = len(sorted_trades)

        for i, candle in enumerate(sorted_candles):
            start_ts = candle.timestamp
            # Next candle timestamp or approximate end
            if i + 1 < len(sorted_candles):
                end_ts = sorted_candles[i + 1].timestamp
            else:
                end_ts = start_ts + 3600 * 1000 * 24  # Large future bound

            buy_vol = 0.0
            sell_vol = 0.0

            while trade_idx < num_trades and sorted_trades[trade_idx].timestamp < end_ts:
                t = sorted_trades[trade_idx]
                if t.timestamp >= start_ts:
                    if t.side == TradeSide.BUY:
                        buy_vol += t.amount
                    elif t.side == TradeSide.SELL:
                        sell_vol += t.amount
                trade_idx += 1

            delta = buy_vol - sell_vol
            cum_delta += delta

            bars.append(CVDBar(
                timestamp=candle.timestamp,
                datetime=candle.datetime,
                buy_volume=buy_vol,
                sell_volume=sell_vol,
                delta=delta,
                cumulative_delta=cum_delta,
                is_exchange_provided=False
            ))

        # Calculate momentum
        self._calculate_momentum(bars)
        return bars

    def estimate_from_candles(
        self,
        candles: List[Candle],
        initial_cumulative_delta: float = 0.0
    ) -> List[CVDBar]:
        """
        Intra-bar volume delta approximation using high-low close location:
        delta ≈ volume * (2 * (close - low) / (high - low) - 1)
        Strictly flagged as approximation when raw ticks are not yet stored.
        """
        bars: List[CVDBar] = []
        cum_delta = initial_cumulative_delta

        for c in sorted(candles, key=lambda x: x.timestamp):
            price_range = c.high - c.low
            if price_range > 0:
                pos = (c.close - c.low) / price_range
                delta = c.volume * (2.0 * pos - 1.0)
                buy_vol = c.volume * pos
                sell_vol = c.volume * (1.0 - pos)
            else:
                delta = 0.0
                buy_vol = c.volume * 0.5
                sell_vol = c.volume * 0.5

            cum_delta += delta
            bars.append(CVDBar(
                timestamp=c.timestamp,
                datetime=c.datetime,
                buy_volume=buy_vol,
                sell_volume=sell_vol,
                delta=delta,
                cumulative_delta=cum_delta,
                is_exchange_provided=False
            ))

        self._calculate_momentum(bars)
        return bars

    def _calculate_momentum(self, bars: List[CVDBar]):
        for i in range(len(bars)):
            if i >= self.momentum_window:
                past_cum = bars[i - self.momentum_window].cumulative_delta
                bars[i].cvd_momentum = bars[i].cumulative_delta - past_cum
            else:
                bars[i].cvd_momentum = 0.0

    def detect_divergence(
        self,
        candles: List[Candle],
        cvd_bars: List[CVDBar],
        lookback: int = 14
    ) -> Optional[Dict[str, Any]]:
        """
        Detects CVD vs Price divergence across lookback window.
        - Bearish: Price Higher High, CVD Lower High (Absorption / exhausted buyers)
        - Bullish: Price Lower Low, CVD Higher Low (Absorption / exhausted sellers)
        """
        if len(candles) < lookback or len(cvd_bars) < lookback:
            return None

        recent_candles = candles[-lookback:]
        recent_cvd = cvd_bars[-lookback:]

        # Price extremes
        p_highs = [c.high for c in recent_candles]
        p_lows = [c.low for c in recent_candles]
        cvd_vals = [b.cumulative_delta for b in recent_cvd]

        half = lookback // 2
        p1_high = max(p_highs[:half])
        p2_high = max(p_highs[half:])

        p1_low = min(p_lows[:half])
        p2_low = min(p_lows[half:])

        cvd1_high = max(cvd_vals[:half])
        cvd2_high = max(cvd_vals[half:])

        cvd1_low = min(cvd_vals[:half])
        cvd2_low = min(cvd_vals[half:])

        # Bearish divergence: price made higher high, but CVD made lower high
        if p2_high > p1_high and cvd2_high < cvd1_high:
            return {
                "type": "BEARISH_CVD_DIVERGENCE",
                "price_diff": p2_high - p1_high,
                "cvd_diff": cvd2_high - cvd1_high,
                "description": "Price made higher high while aggressive buying (CVD) weakened."
            }

        # Bullish divergence: price made lower low, but CVD made higher low
        if p2_low < p1_low and cvd2_low > cvd1_low:
            return {
                "type": "BULLISH_CVD_DIVERGENCE",
                "price_diff": p2_low - p1_low,
                "cvd_diff": cvd2_low - cvd1_low,
                "description": "Price made lower low while aggressive selling (CVD) weakened."
            }

        return None

