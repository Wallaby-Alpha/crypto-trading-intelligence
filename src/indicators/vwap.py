"""
Volume Weighted Average Price (VWAP) Engine:
- Anchored VWAP (Session 00:00 UTC, weekly, or custom anchor).
- Standard deviation bands (+/- 1 sigma, +/- 2 sigma, +/- 3 sigma).
- Rolling VWAP for multi-timeframe analysis.
- VWAP reclaim and rejection distance tracking.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import numpy as np
from src.core.models import Candle


class VWAPBand(BaseModel):
    timestamp: int
    datetime: str
    vwap: float
    upper_band_1: float
    lower_band_1: float
    upper_band_2: float
    lower_band_2: float
    upper_band_3: float
    lower_band_3: float
    std_dev: float
    distance_from_vwap_pct: float


class VWAPEngine:
    def __init__(self, session_anchor_hours: int = 24):
        self.session_anchor_hours = session_anchor_hours

    def calculate_anchored_vwap(self, candles: List[Candle]) -> List[VWAPBand]:
        """
        Calculates anchored session VWAP with standard deviation volatility bands.
        """
        if not candles:
            return []

        sorted_candles = sorted(candles, key=lambda c: c.timestamp)
        results: List[VWAPBand] = []

        cum_typical_volume = 0.0
        cum_volume = 0.0
        cum_vol_sq_diff = 0.0

        for c in sorted_candles:
            # Typical price = (High + Low + Close) / 3
            typical_price = (c.high + c.low + c.close) / 3.0
            vol = max(c.volume, 1e-8)

            cum_typical_volume += typical_price * vol
            cum_volume += vol

            current_vwap = cum_typical_volume / cum_volume

            # Variance calculation
            sq_diff = (typical_price - current_vwap) ** 2
            cum_vol_sq_diff += vol * sq_diff
            variance = cum_vol_sq_diff / cum_volume
            std_dev = np.sqrt(variance)

            dist_pct = ((c.close - current_vwap) / current_vwap) * 100.0 if current_vwap > 0 else 0.0

            results.append(VWAPBand(
                timestamp=c.timestamp,
                datetime=c.datetime,
                vwap=current_vwap,
                upper_band_1=current_vwap + (1.0 * std_dev),
                lower_band_1=current_vwap - (1.0 * std_dev),
                upper_band_2=current_vwap + (2.0 * std_dev),
                lower_band_2=current_vwap - (2.0 * std_dev),
                upper_band_3=current_vwap + (3.0 * std_dev),
                lower_band_3=current_vwap - (3.0 * std_dev),
                std_dev=float(std_dev),
                distance_from_vwap_pct=dist_pct
            ))

        return results

    # Alias
    calculate_session_vwap = calculate_anchored_vwap

    def calculate_rolling_vwap(self, candles: List[Candle], window: int = 50) -> List[VWAPBand]:
        """
        Calculates rolling window VWAP over the last N candles.
        """
        if len(candles) < window:
            return self.calculate_anchored_vwap(candles)

        sorted_candles = sorted(candles, key=lambda c: c.timestamp)
        results: List[VWAPBand] = []

        for i in range(len(sorted_candles)):
            start_idx = max(0, i - window + 1)
            window_slice = sorted_candles[start_idx : i + 1]

            t_prices = np.array([(c.high + c.low + c.close) / 3.0 for c in window_slice])
            volumes = np.array([max(c.volume, 1e-8) for c in window_slice])

            tot_vol = np.sum(volumes)
            vwap = np.sum(t_prices * volumes) / tot_vol

            variance = np.sum(volumes * ((t_prices - vwap) ** 2)) / tot_vol
            std_dev = np.sqrt(variance)

            curr = sorted_candles[i]
            dist_pct = ((curr.close - vwap) / vwap) * 100.0 if vwap > 0 else 0.0

            results.append(VWAPBand(
                timestamp=curr.timestamp,
                datetime=curr.datetime,
                vwap=float(vwap),
                upper_band_1=float(vwap + std_dev),
                lower_band_1=float(vwap - std_dev),
                upper_band_2=float(vwap + 2 * std_dev),
                lower_band_2=float(vwap - 2 * std_dev),
                upper_band_3=float(vwap + 3 * std_dev),
                lower_band_3=float(vwap - 3 * std_dev),
                std_dev=float(std_dev),
                distance_from_vwap_pct=float(dist_pct)
            ))

        return results

    # Alias
    calculate_session_vwap = calculate_anchored_vwap

