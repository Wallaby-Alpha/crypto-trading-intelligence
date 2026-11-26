"""
Failed Acceptance and Failed Reclaim Detection Engine.
- Failed Acceptance: Price breaks a key level but cannot sustain closes beyond it, followed by return inside.
- Failed Reclaim: Price attempts to retest a broken support or resistance level and fails to reclaim it,
  signaling continuation in the breakout direction.
"""
from typing import List, Dict, Any, Optional
from src.core.models import Candle
from src.events.models import (
    FailedAcceptanceEvent, FailedAcceptanceType, LiquidityLevel, LiquidityLevelType
)
from src.events.swing_points import SwingPointDetector


class FailedAcceptanceDetector:
    def __init__(self, max_closes_beyond: int = 2, retest_tolerance_pct: float = 0.15):
        self.max_closes_beyond = max_closes_beyond
        self.retest_tolerance_pct = retest_tolerance_pct
        self.swing_detector = SwingPointDetector()

    def detect_events_at_candle(
        self,
        candles: List[Candle],
        current_index: int,
        atr_value: float
    ) -> List[FailedAcceptanceEvent]:
        """
        Evaluates failed acceptance and failed reclaim at current_index candle.
        """
        min_required = self.swing_detector.left_bars + self.swing_detector.right_bars
        if current_index < min_required or current_index >= len(candles):
            return []

        curr_candle = candles[current_index]
        prev_candle = candles[current_index - 1]

        active_levels = self.swing_detector.extract_liquidity_levels(candles, current_index - 1)
        events: List[FailedAcceptanceEvent] = []

        lookback_window = 6
        start_idx = max(0, current_index - lookback_window + 1)
        window = candles[start_idx : current_index + 1]

        for lvl in active_levels:
            # 1. Failed Breakout Above Resistance / High
            if lvl.level_type in [LiquidityLevelType.SWING_HIGH, LiquidityLevelType.RANGE_HIGH, LiquidityLevelType.SESSION_HIGH]:
                # Did price break above level in recent window?
                broke_above = any(c.high > lvl.price for c in window[:-1])
                if broke_above:
                    # Count closes beyond
                    closes_beyond = sum(1 for c in window if c.close > lvl.price)
                    # Current candle closes firmly back below
                    if closes_beyond <= self.max_closes_beyond and curr_candle.close < lvl.price and prev_candle.high > lvl.price:
                        extreme_high = max(c.high for c in window)
                        events.append(FailedAcceptanceEvent(
                            symbol=curr_candle.symbol,
                            timeframe=curr_candle.timeframe,
                            timestamp=curr_candle.timestamp,
                            datetime=curr_candle.datetime,
                            event_type=FailedAcceptanceType.FAILED_BREAKOUT_ABOVE,
                            level_price=lvl.price,
                            extreme_price=extreme_high,
                            closes_beyond=closes_beyond,
                            reversal_confirmed=True,
                            description=f"Failed acceptance above {lvl.level_type.value} at {lvl.price:.2f}. Returned inside after {closes_beyond} close(s)."
                        ))

            # 2. Failed Breakdown Below Support / Low
            elif lvl.level_type in [LiquidityLevelType.SWING_LOW, LiquidityLevelType.RANGE_LOW, LiquidityLevelType.SESSION_LOW]:
                broke_below = any(c.low < lvl.price for c in window[:-1])
                if broke_below:
                    closes_beyond = sum(1 for c in window if c.close < lvl.price)
                    if closes_beyond <= self.max_closes_beyond and curr_candle.close > lvl.price and prev_candle.low < lvl.price:
                        extreme_low = min(c.low for c in window)
                        events.append(FailedAcceptanceEvent(
                            symbol=curr_candle.symbol,
                            timeframe=curr_candle.timeframe,
                            timestamp=curr_candle.timestamp,
                            datetime=curr_candle.datetime,
                            event_type=FailedAcceptanceType.FAILED_BREAKDOWN_BELOW,
                            level_price=lvl.price,
                            extreme_price=extreme_low,
                            closes_beyond=closes_beyond,
                            reversal_confirmed=True,
                            description=f"Failed breakdown below {lvl.level_type.value} at {lvl.price:.2f}. Returned inside after {closes_beyond} close(s)."
                        ))

            # 3. Failed Reclaim (Resistance Retest from Below)
            # Level was broken downward previously, price retests from below and rejects
            if lvl.level_type == LiquidityLevelType.SWING_LOW:
                # Broken level now acting as resistance
                was_below = all(c.close < lvl.price for c in window[-4:-1])
                retested = curr_candle.high >= (lvl.price * (1.0 - self.retest_tolerance_pct / 100.0)) and curr_candle.high <= (lvl.price * 1.01)
                rejected = curr_candle.close < curr_candle.open and curr_candle.close < lvl.price
                if was_below and retested and rejected:
                    events.append(FailedAcceptanceEvent(
                        symbol=curr_candle.symbol,
                        timeframe=curr_candle.timeframe,
                        timestamp=curr_candle.timestamp,
                        datetime=curr_candle.datetime,
                        event_type=FailedAcceptanceType.FAILED_RECLAIM_RESISTANCE,
                        level_price=lvl.price,
                        extreme_price=curr_candle.high,
                        closes_beyond=0,
                        reversal_confirmed=True,
                        description=f"Failed reclaim of broken support level {lvl.price:.2f}. Retest rejected with bearish close."
                    ))

            # 4. Failed Reclaim (Support Retest from Above)
            if lvl.level_type == LiquidityLevelType.SWING_HIGH:
                was_above = all(c.close > lvl.price for c in window[-4:-1])
                retested = curr_candle.low <= (lvl.price * (1.0 + self.retest_tolerance_pct / 100.0)) and curr_candle.low >= (lvl.price * 0.99)
                rejected = curr_candle.close > curr_candle.open and curr_candle.close > lvl.price
                if was_above and retested and rejected:
                    events.append(FailedAcceptanceEvent(
                        symbol=curr_candle.symbol,
                        timeframe=curr_candle.timeframe,
                        timestamp=curr_candle.timestamp,
                        datetime=curr_candle.datetime,
                        event_type=FailedAcceptanceType.FAILED_RECLAIM_SUPPORT,
                        level_price=lvl.price,
                        extreme_price=curr_candle.low,
                        closes_beyond=0,
                        reversal_confirmed=True,
                        description=f"Successful retest of broken resistance level {lvl.price:.2f}. Bounced with bullish close."
                    ))

        return events
