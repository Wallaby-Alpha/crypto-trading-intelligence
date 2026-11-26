"""
VWAP & Volume Profile Event Detection Engine.
Detects:
- Rejection from VWAP (Bearish rejection from upper side, Bullish bounce from lower side)
- VWAP Reclaim (Price crossing back above/below VWAP)
- High Volume Rejection Candles (Volume > 2x MA with long upper/lower wick)
- Low Volume Retests (Retest on declining volume indicating lack of counter-trend interest)
- Point of Control (POC) Interaction
"""
from typing import List, Dict, Any, Optional
import numpy as np
from src.core.models import Candle
from src.indicators.vwap import VWAPBand
from src.indicators.volume_profile import VolumeProfileResult
from src.events.models import VWAPVolumeEvent, VWAPVolumeEventType


class VWAPVolumeEventDetector:
    def __init__(self, high_volume_multiplier: float = 1.8, low_volume_multiplier: float = 0.7):
        self.high_volume_multiplier = high_volume_multiplier
        self.low_volume_multiplier = low_volume_multiplier

    def detect_events_at_candle(
        self,
        candles: List[Candle],
        vwap_bands: List[VWAPBand],
        vp_result: Optional[VolumeProfileResult],
        current_index: int
    ) -> List[VWAPVolumeEvent]:
        """
        Evaluates VWAP and Volume profile interaction events at current_index candle.
        """
        if current_index < 20 or current_index >= len(candles) or current_index >= len(vwap_bands):
            return []

        curr_candle = candles[current_index]
        prev_candle = candles[current_index - 1]
        curr_vwap = vwap_bands[current_index].vwap
        prev_vwap = vwap_bands[current_index - 1].vwap
        std_dev = vwap_bands[current_index].std_dev

        # Volume MA over previous 20 bars
        recent_volumes = [c.volume for c in candles[current_index - 20 : current_index]]
        vol_ma = float(np.mean(recent_volumes)) if recent_volumes else curr_candle.volume
        vol_ratio = curr_candle.volume / max(vol_ma, 1e-6)

        c_range = max(curr_candle.high - curr_candle.low, 1e-6)
        upper_wick = curr_candle.high - max(curr_candle.open, curr_candle.close)
        lower_wick = min(curr_candle.open, curr_candle.close) - curr_candle.low

        events: List[VWAPVolumeEvent] = []

        # 1. Bearish VWAP Rejection: Candle penetrated above VWAP but closed back below with upper wick
        if curr_candle.high >= curr_vwap and curr_candle.close < curr_vwap and (upper_wick / c_range) >= 0.35:
            dist_pct = (curr_candle.high - curr_vwap) / curr_vwap * 100.0
            events.append(VWAPVolumeEvent(
                symbol=curr_candle.symbol,
                timeframe=curr_candle.timeframe,
                timestamp=curr_candle.timestamp,
                datetime=curr_candle.datetime,
                event_type=VWAPVolumeEventType.VWAP_REJECTION_BEARISH,
                reference_price=curr_vwap,
                candle_close=curr_candle.close,
                distance_pct=dist_pct,
                volume_ratio=vol_ratio
            ))

        # 2. Bullish VWAP Bounce/Rejection: Candle penetrated below VWAP but closed back above with lower wick
        if curr_candle.low <= curr_vwap and curr_candle.close > curr_vwap and (lower_wick / c_range) >= 0.35:
            dist_pct = (curr_vwap - curr_candle.low) / curr_vwap * 100.0
            events.append(VWAPVolumeEvent(
                symbol=curr_candle.symbol,
                timeframe=curr_candle.timeframe,
                timestamp=curr_candle.timestamp,
                datetime=curr_candle.datetime,
                event_type=VWAPVolumeEventType.VWAP_REJECTION_BULLISH,
                reference_price=curr_vwap,
                candle_close=curr_candle.close,
                distance_pct=dist_pct,
                volume_ratio=vol_ratio
            ))

        # 3. Bullish VWAP Reclaim: Previous close was below VWAP, current close is firmly above VWAP
        if prev_candle.close < prev_vwap and curr_candle.close > curr_vwap and curr_candle.close > curr_candle.open:
            dist_pct = (curr_candle.close - curr_vwap) / curr_vwap * 100.0
            events.append(VWAPVolumeEvent(
                symbol=curr_candle.symbol,
                timeframe=curr_candle.timeframe,
                timestamp=curr_candle.timestamp,
                datetime=curr_candle.datetime,
                event_type=VWAPVolumeEventType.VWAP_RECLAIM_BULLISH,
                reference_price=curr_vwap,
                candle_close=curr_candle.close,
                distance_pct=dist_pct,
                volume_ratio=vol_ratio
            ))

        # 4. Bearish VWAP Loss: Previous close was above VWAP, current close is firmly below VWAP
        if prev_candle.close > prev_vwap and curr_candle.close < curr_vwap and curr_candle.close < curr_candle.open:
            dist_pct = (curr_vwap - curr_candle.close) / curr_vwap * 100.0
            events.append(VWAPVolumeEvent(
                symbol=curr_candle.symbol,
                timeframe=curr_candle.timeframe,
                timestamp=curr_candle.timestamp,
                datetime=curr_candle.datetime,
                event_type=VWAPVolumeEventType.VWAP_LOSS_BEARISH,
                reference_price=curr_vwap,
                candle_close=curr_candle.close,
                distance_pct=dist_pct,
                volume_ratio=vol_ratio
            ))

        # 5. High Volume Rejection Candle: Extremely high volume (>1.8x MA) with absorption wick
        if vol_ratio >= self.high_volume_multiplier:
            if (upper_wick / c_range) >= 0.40 or (lower_wick / c_range) >= 0.40:
                events.append(VWAPVolumeEvent(
                    symbol=curr_candle.symbol,
                    timeframe=curr_candle.timeframe,
                    timestamp=curr_candle.timestamp,
                    datetime=curr_candle.datetime,
                    event_type=VWAPVolumeEventType.HIGH_VOLUME_REJECTION,
                    reference_price=curr_candle.close,
                    candle_close=curr_candle.close,
                    distance_pct=0.0,
                    volume_ratio=vol_ratio
                ))

        # 6. POC Interaction (if Volume Profile provided)
        if vp_result:
            poc = vp_result.poc_price
            if curr_candle.low <= poc <= curr_candle.high:
                events.append(VWAPVolumeEvent(
                    symbol=curr_candle.symbol,
                    timeframe=curr_candle.timeframe,
                    timestamp=curr_candle.timestamp,
                    datetime=curr_candle.datetime,
                    event_type=VWAPVolumeEventType.POC_REJECTION,
                    reference_price=poc,
                    candle_close=curr_candle.close,
                    distance_pct=abs(curr_candle.close - poc) / poc * 100.0,
                    volume_ratio=vol_ratio
                ))

        return events

