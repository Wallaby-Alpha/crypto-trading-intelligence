"""
Market Structure Engine.
Detects:
- Higher Highs (HH), Higher Lows (HL), Lower Highs (LH), Lower Lows (LL)
- Break of Structure (BOS)
- Change of Character (CHoCH)
- Market Structure Shift (MSS) with displacement confirmation
- Displacement candles
Zero lookahead bias: All structure points must have satisfied their confirmation window.
"""
from typing import List, Dict, Any, Optional
from src.core.models import Candle
from src.events.models import (
    MarketStructureEvent, MarketStructureType, SwingPoint, SwingType
)
from src.events.swing_points import SwingPointDetector


class MarketStructureDetector:
    def __init__(self, displacement_atr_ratio: float = 1.2, swing_detector: Optional[SwingPointDetector] = None):
        self.displacement_atr_ratio = displacement_atr_ratio
        self.swing_detector = swing_detector or SwingPointDetector()

    def detect_structure_events_at_candle(
        self,
        candles: List[Candle],
        current_index: int,
        atr_value: float
    ) -> List[MarketStructureEvent]:
        """
        Evaluates market structure shift, BOS, and CHoCH at current_index candle.
        """
        min_required = self.swing_detector.left_bars + self.swing_detector.right_bars
        if current_index < min_required or current_index >= len(candles):
            return []

        curr_candle = candles[current_index]
        prev_candle = candles[current_index - 1]

        # Get all confirmed swings strictly confirmed at or before current_index - 1
        all_swings = self.swing_detector.detect_confirmed_swings(candles)
        visible_swings = [s for s in all_swings if s.confirmation_index <= (current_index - 1)]

        if not visible_swings:
            return []

        high_swings = [s for s in visible_swings if s.type == SwingType.SWING_HIGH]
        low_swings = [s for s in visible_swings if s.type == SwingType.SWING_LOW]

        if not high_swings or not low_swings:
            return []

        recent_high = high_swings[-1]
        recent_low = low_swings[-1]

        # Determine current prevailing trend from last 2 highs and last 2 lows
        current_trend = "RANGING"
        if len(high_swings) >= 2 and len(low_swings) >= 2:
            prev_high = high_swings[-2]
            prev_low = low_swings[-2]

            if recent_high.price > prev_high.price and recent_low.price > prev_low.price:
                current_trend = "BULLISH"
            elif recent_high.price < prev_high.price and recent_low.price < prev_low.price:
                current_trend = "BEARISH"

        events: List[MarketStructureEvent] = []

        # Displacement calculation: candle body relative to ATR
        candle_body = abs(curr_candle.close - curr_candle.open)
        displacement_ratio = candle_body / max(atr_value, 1e-6)
        has_displacement = (displacement_ratio >= self.displacement_atr_ratio)

        # 1. Bullish Structure Break: Current candle closes ABOVE recent confirmed swing high
        if prev_candle.close <= recent_high.price and curr_candle.close > recent_high.price:
            if current_trend == "BEARISH":
                # Downtrend breaking recent high is a Change of Character (CHoCH) or Market Structure Shift (MSS)
                event_type = MarketStructureType.MSS_BULLISH if has_displacement else MarketStructureType.CHOCH_BULLISH
            else:
                # Continuation break in Bullish/Ranging is a Break of Structure (BOS)
                event_type = MarketStructureType.BOS_BULLISH

            events.append(MarketStructureEvent(
                symbol=curr_candle.symbol,
                timeframe=curr_candle.timeframe,
                timestamp=curr_candle.timestamp,
                datetime=curr_candle.datetime,
                event_type=event_type,
                broken_level_price=recent_high.price,
                trigger_close_price=curr_candle.close,
                displacement_ratio=displacement_ratio,
                current_trend="BULLISH"
            ))

        # 2. Bearish Structure Break: Current candle closes BELOW recent confirmed swing low
        if prev_candle.close >= recent_low.price and curr_candle.close < recent_low.price:
            if current_trend == "BULLISH":
                # Uptrend breaking recent low is a Change of Character (CHoCH) or Market Structure Shift (MSS)
                event_type = MarketStructureType.MSS_BEARISH if has_displacement else MarketStructureType.CHOCH_BEARISH
            else:
                # Continuation break in Bearish/Ranging is a Break of Structure (BOS)
                event_type = MarketStructureType.BOS_BEARISH

            events.append(MarketStructureEvent(
                symbol=curr_candle.symbol,
                timeframe=curr_candle.timeframe,
                timestamp=curr_candle.timestamp,
                datetime=curr_candle.datetime,
                event_type=event_type,
                broken_level_price=recent_low.price,
                trigger_close_price=curr_candle.close,
                displacement_ratio=displacement_ratio,
                current_trend="BEARISH"
            ))

        return events
