"""
CVD Divergence & Orderflow Absorption Detection Engine.
Detects:
- Bullish CVD Divergence (Price lower low, CVD higher low) -> Aggressive selling absorbed by limit buyers.
- Bearish CVD Divergence (Price higher high, CVD lower high) -> Aggressive buying absorbed by limit sellers.
Calculates quantitative absorption score (0-100).
"""
from typing import List, Dict, Any, Optional
import numpy as np
from src.core.models import Candle
from src.indicators.cvd import CVDBar
from src.events.models import CVDDivergenceEvent, CVDDivergenceType


class CVDDivergenceDetector:
    def __init__(self, lookback_bars: int = 14):
        self.lookback_bars = lookback_bars

    def detect_divergence_at_candle(
        self,
        candles: List[Candle],
        cvd_bars: List[CVDBar],
        current_index: int
    ) -> Optional[CVDDivergenceEvent]:
        """
        Evaluates CVD divergence over lookback window ending at current_index.
        """
        if current_index < self.lookback_bars - 1 or len(cvd_bars) <= current_index:
            return None

        window_candles = candles[current_index - self.lookback_bars + 1 : current_index + 1]
        window_cvd = cvd_bars[current_index - self.lookback_bars + 1 : current_index + 1]

        half = self.lookback_bars // 2
        first_half_candles = window_candles[:half]
        second_half_candles = window_candles[half:]

        first_half_cvd = window_cvd[:half]
        second_half_cvd = window_cvd[half:]

        p1_high = max(c.high for c in first_half_candles)
        p2_high = max(c.high for c in second_half_candles)

        p1_low = min(c.low for c in first_half_candles)
        p2_low = min(c.low for c in second_half_candles)

        cvd1_high = max(b.cumulative_delta for b in first_half_cvd)
        cvd2_high = max(b.cumulative_delta for b in second_half_cvd)

        cvd1_low = min(b.cumulative_delta for b in first_half_cvd)
        cvd2_low = min(b.cumulative_delta for b in second_half_cvd)

        curr_candle = candles[current_index]

        # 1. Bearish Divergence: Price higher high, but CVD lower high
        if p2_high > p1_high and cvd2_high < cvd1_high:
            price_delta_pct = (p2_high - p1_high) / p1_high * 100.0
            cvd_diff = cvd1_high - cvd2_high
            # Score: larger divergence yields higher absorption score up to 100
            score = min(100.0, 50.0 + (price_delta_pct * 10.0) + (abs(cvd_diff) / (abs(cvd1_high) + 1e-6) * 40.0))

            return CVDDivergenceEvent(
                symbol=curr_candle.symbol,
                timeframe=curr_candle.timeframe,
                timestamp=curr_candle.timestamp,
                datetime=curr_candle.datetime,
                divergence_type=CVDDivergenceType.BEARISH_CVD_ABSORPTION,
                price_swing_1=p1_high,
                price_swing_2=p2_high,
                cvd_swing_1=cvd1_high,
                cvd_swing_2=cvd2_high,
                lookback_bars=self.lookback_bars,
                strength_score=score
            )

        # 2. Bullish Divergence: Price lower low, but CVD higher low
        if p2_low < p1_low and cvd2_low > cvd1_low:
            price_delta_pct = (p1_low - p2_low) / p1_low * 100.0
            cvd_diff = cvd2_low - cvd1_low
            score = min(100.0, 50.0 + (price_delta_pct * 10.0) + (abs(cvd_diff) / (abs(cvd1_low) + 1e-6) * 40.0))

            return CVDDivergenceEvent(
                symbol=curr_candle.symbol,
                timeframe=curr_candle.timeframe,
                timestamp=curr_candle.timestamp,
                datetime=curr_candle.datetime,
                divergence_type=CVDDivergenceType.BULLISH_CVD_ABSORPTION,
                price_swing_1=p1_low,
                price_swing_2=p2_low,
                cvd_swing_1=cvd1_low,
                cvd_swing_2=cvd2_low,
                lookback_bars=self.lookback_bars,
                strength_score=score
            )

        return None
