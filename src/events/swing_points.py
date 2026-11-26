"""
Confirmed Swing Points & Liquidity Levels Detector.
Non-negotiable requirement: Zero look-ahead bias.
A swing point at candle i with confirmation window (left=N, right=M)
is ONLY confirmed and visible to the engine at candle i + M.
"""
from typing import List, Dict, Any, Optional, Tuple
from src.core.models import Candle
from src.events.models import SwingPoint, SwingType, LiquidityLevel, LiquidityLevelType


class SwingPointDetector:
    def __init__(self, left_bars: int = 3, right_bars: int = 3, eq_tolerance_pct: float = 0.08):
        self.left_bars = left_bars
        self.right_bars = right_bars
        self.eq_tolerance_pct = eq_tolerance_pct

    def detect_confirmed_swings(self, candles: List[Candle]) -> List[SwingPoint]:
        """
        Detects all confirmed swing points up to the latest candle.
        Each confirmed swing point is tagged with confirmation_index and confirmation_timestamp.
        """
        if len(candles) < (self.left_bars + self.right_bars + 1):
            return []

        swings: List[SwingPoint] = []
        n = len(candles)

        # For index i to be a swing point, we need candles from i - left_bars to i + right_bars
        for i in range(self.left_bars, n - self.right_bars):
            curr_c = candles[i]
            confirm_c = candles[i + self.right_bars]

            # 1. Check Swing High
            is_high = True
            for left_idx in range(i - self.left_bars, i):
                if candles[left_idx].high >= curr_c.high:
                    is_high = False
                    break
            if is_high:
                for right_idx in range(i + 1, i + self.right_bars + 1):
                    if candles[right_idx].high >= curr_c.high:
                        is_high = False
                        break

            if is_high:
                swings.append(SwingPoint(
                    index=i,
                    timestamp=curr_c.timestamp,
                    datetime=curr_c.datetime,
                    price=curr_c.high,
                    type=SwingType.SWING_HIGH,
                    confirmation_index=i + self.right_bars,
                    confirmation_timestamp=confirm_c.timestamp,
                    left_bars=self.left_bars,
                    right_bars=self.right_bars
                ))

            # 2. Check Swing Low
            is_low = True
            for left_idx in range(i - self.left_bars, i):
                if candles[left_idx].low <= curr_c.low:
                    is_low = False
                    break
            if is_low:
                for right_idx in range(i + 1, i + self.right_bars + 1):
                    if candles[right_idx].low <= curr_c.low:
                        is_low = False
                        break

            if is_low:
                swings.append(SwingPoint(
                    index=i,
                    timestamp=curr_c.timestamp,
                    datetime=curr_c.datetime,
                    price=curr_c.low,
                    type=SwingType.SWING_LOW,
                    confirmation_index=i + self.right_bars,
                    confirmation_timestamp=confirm_c.timestamp,
                    left_bars=self.left_bars,
                    right_bars=self.right_bars
                ))

        # Sort by index ascending
        swings.sort(key=lambda s: s.index)
        return swings

    def extract_liquidity_levels(self, candles: List[Candle], current_index: int) -> List[LiquidityLevel]:
        """
        Extracts active liquidity levels visible strictly at or before current_index.
        Includes:
        - Confirmed Swing Highs & Lows
        - Equal Highs (EQH) and Equal Lows (EQL)
        - Session Highs & Lows (24h lookback)
        """
        confirmed_swings = [
            s for s in self.detect_confirmed_swings(candles)
            if s.confirmation_index <= current_index
        ]

        levels: List[LiquidityLevel] = []

        # 1. Add Swing Highs and Lows
        high_swings = [s for s in confirmed_swings if s.type == SwingType.SWING_HIGH]
        low_swings = [s for s in confirmed_swings if s.type == SwingType.SWING_LOW]

        for s in high_swings:
            levels.append(LiquidityLevel(
                level_type=LiquidityLevelType.SWING_HIGH,
                price=s.price,
                timestamp=s.timestamp,
                datetime=s.datetime,
                touch_count=1
            ))

        for s in low_swings:
            levels.append(LiquidityLevel(
                level_type=LiquidityLevelType.SWING_LOW,
                price=s.price,
                timestamp=s.timestamp,
                datetime=s.datetime,
                touch_count=1
            ))

        # 2. Detect Equal Highs (EQH) and Equal Lows (EQL)
        # Check pairs of recent swings within tolerance
        if len(high_swings) >= 2:
            for a in range(len(high_swings) - 1):
                for b in range(a + 1, len(high_swings)):
                    p1 = high_swings[a].price
                    p2 = high_swings[b].price
                    diff_pct = abs(p1 - p2) / p1 * 100.0
                    if diff_pct <= self.eq_tolerance_pct:
                        levels.append(LiquidityLevel(
                            level_type=LiquidityLevelType.EQUAL_HIGHS,
                            price=max(p1, p2),
                            timestamp=high_swings[b].timestamp,
                            datetime=high_swings[b].datetime,
                            touch_count=2
                        ))

        if len(low_swings) >= 2:
            for a in range(len(low_swings) - 1):
                for b in range(a + 1, len(low_swings)):
                    p1 = low_swings[a].price
                    p2 = low_swings[b].price
                    diff_pct = abs(p1 - p2) / p1 * 100.0
                    if diff_pct <= self.eq_tolerance_pct:
                        levels.append(LiquidityLevel(
                            level_type=LiquidityLevelType.EQUAL_LOWS,
                            price=min(p1, p2),
                            timestamp=low_swings[b].timestamp,
                            datetime=low_swings[b].datetime,
                            touch_count=2
                        ))

        # 3. Session / Rolling 24h High and Low
        # Lookback up to 288 5m candles or available candles up to current_index
        lookback = min(current_index + 1, 288)
        session_slice = candles[max(0, current_index - lookback + 1) : current_index + 1]
        if session_slice:
            s_high = max(c.high for c in session_slice)
            s_low = min(c.low for c in session_slice)
            levels.append(LiquidityLevel(
                level_type=LiquidityLevelType.SESSION_HIGH,
                price=s_high,
                timestamp=session_slice[-1].timestamp,
                datetime=session_slice[-1].datetime
            ))
            levels.append(LiquidityLevel(
                level_type=LiquidityLevelType.SESSION_LOW,
                price=s_low,
                timestamp=session_slice[-1].timestamp,
                datetime=session_slice[-1].datetime
            ))

        return levels

