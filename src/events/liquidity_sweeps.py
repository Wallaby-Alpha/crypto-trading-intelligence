"""
Liquidity Sweeps & Stop Hunts Detection Engine.
Mathematically detects sweeps of:
- Previous swing highs and lows
- Equal highs (EQH) and Equal lows (EQL)
- Previous session highs and lows
Zero look-ahead bias: Strictly evaluates closed candles at the decision boundary.
"""
from typing import List, Dict, Any, Optional
from src.core.models import Candle
from src.events.models import (
    LiquidityLevel, LiquidityLevelType, LiquiditySweepEvent, SweepDirection
)
from src.events.swing_points import SwingPointDetector


class LiquiditySweepDetector:
    def __init__(
        self,
        min_penetration_pct: float = 0.05,
        min_atr_multiplier: float = 0.10,
        max_reclaim_candles: int = 3,
        swing_detector: Optional[SwingPointDetector] = None
    ):
        self.min_penetration_pct = min_penetration_pct
        self.min_atr_multiplier = min_atr_multiplier
        self.max_reclaim_candles = max_reclaim_candles
        self.swing_detector = swing_detector or SwingPointDetector()

    def detect_sweeps_at_candle(
        self,
        candles: List[Candle],
        current_index: int,
        atr_value: float
    ) -> List[LiquiditySweepEvent]:
        """
        Detects if current_index candle completed a liquidity sweep of any active liquidity level.
        Evaluates immediate single-candle sweeps and multi-candle sweeps (up to max_reclaim_candles).
        """
        min_required = self.swing_detector.left_bars + self.swing_detector.right_bars
        if current_index < min_required or current_index >= len(candles):
            return []

        curr_candle = candles[current_index]
        # Only examine liquidity levels confirmed PRIOR to the sweep attempt
        active_levels = self.swing_detector.extract_liquidity_levels(candles, current_index - 1)
        if not active_levels:
            return []

        min_penetration_dist = max(atr_value * self.min_atr_multiplier, curr_candle.close * (self.min_penetration_pct / 100.0))
        detected_sweeps: List[LiquiditySweepEvent] = []

        for lvl in active_levels:
            # 1. Bearish Sweep of Highs (Swing High, Equal Highs, Session High)
            if lvl.level_type in [LiquidityLevelType.SWING_HIGH, LiquidityLevelType.EQUAL_HIGHS, LiquidityLevelType.SESSION_HIGH]:
                # Check candles in the reclaim window: from (current_index - max_reclaim_candles + 1) to current_index
                start_win = max(0, current_index - self.max_reclaim_candles + 1)
                window_candles = candles[start_win : current_index + 1]

                highest_high = max(c.high for c in window_candles)
                pen_dist = highest_high - lvl.price

                # Condition 1: Penetrated above level by min_penetration_dist
                if pen_dist >= min_penetration_dist:
                    # Condition 2: Current candle closed back BELOW the level
                    if curr_candle.close < lvl.price:
                        # Ensure price was actually above level before closing back below
                        time_outside = sum(1 for c in window_candles if c.high > lvl.price)
                        c_range = max(curr_candle.high - curr_candle.low, 1e-6)
                        rejection_strength = (curr_candle.high - curr_candle.close) / c_range * 100.0

                        pen_pct = (pen_dist / lvl.price) * 100.0
                        pen_atr = pen_dist / max(atr_value, 1e-6)

                        detected_sweeps.append(LiquiditySweepEvent(
                            symbol=curr_candle.symbol,
                            timeframe=curr_candle.timeframe,
                            timestamp=curr_candle.timestamp,
                            datetime=curr_candle.datetime,
                            direction=SweepDirection.BEARISH_SWEEP_HIGH,
                            level_swept_type=lvl.level_type,
                            level_price=lvl.price,
                            extreme_price=highest_high,
                            penetration_pct=pen_pct,
                            penetration_atr_ratio=pen_atr,
                            candles_outside=time_outside,
                            rejection_strength_pct=rejection_strength,
                            reclaimed_close_price=curr_candle.close
                        ))

            # 2. Bullish Sweep of Lows (Swing Low, Equal Lows, Session Low)
            elif lvl.level_type in [LiquidityLevelType.SWING_LOW, LiquidityLevelType.EQUAL_LOWS, LiquidityLevelType.SESSION_LOW]:
                start_win = max(0, current_index - self.max_reclaim_candles + 1)
                window_candles = candles[start_win : current_index + 1]

                lowest_low = min(c.low for c in window_candles)
                pen_dist = lvl.price - lowest_low

                # Condition 1: Penetrated below level by min_penetration_dist
                if pen_dist >= min_penetration_dist:
                    # Condition 2: Current candle closed back ABOVE the level
                    if curr_candle.close > lvl.price:
                        time_outside = sum(1 for c in window_candles if c.low < lvl.price)
                        c_range = max(curr_candle.high - curr_candle.low, 1e-6)
                        rejection_strength = (curr_candle.close - curr_candle.low) / c_range * 100.0

                        pen_pct = (pen_dist / lvl.price) * 100.0
                        pen_atr = pen_dist / max(atr_value, 1e-6)

                        detected_sweeps.append(LiquiditySweepEvent(
                            symbol=curr_candle.symbol,
                            timeframe=curr_candle.timeframe,
                            timestamp=curr_candle.timestamp,
                            datetime=curr_candle.datetime,
                            direction=SweepDirection.BULLISH_SWEEP_LOW,
                            level_swept_type=lvl.level_type,
                            level_price=lvl.price,
                            extreme_price=lowest_low,
                            penetration_pct=pen_pct,
                            penetration_atr_ratio=pen_atr,
                            candles_outside=time_outside,
                            rejection_strength_pct=rejection_strength,
                            reclaimed_close_price=curr_candle.close
                        ))

        return detected_sweeps
