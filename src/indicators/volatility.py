"""
Volatility & ATR Engine:
- Average True Range (ATR) across timeframes.
- Parkinson realized volatility.
- Garman-Klass volatility (capturing intraday high/low/open/close drift).
- Volatility adjustment multipliers for dynamic stop-loss and sweep penetration thresholds.
"""
from typing import List, Optional
import numpy as np
from src.core.models import Candle


class VolatilityEngine:
    def __init__(self, atr_period: int = 14):
        self.atr_period = atr_period

    def calculate_atr(self, candles: List[Candle]) -> List[float]:
        """
        True Range = max(High - Low, abs(High - Close_prev), abs(Low - Close_prev))
        ATR = Wilder smoothed moving average of TR.
        """
        if len(candles) < 2:
            return [0.0] * len(candles)

        sorted_candles = sorted(candles, key=lambda c: c.timestamp)
        tr_list = [sorted_candles[0].high - sorted_candles[0].low]

        for i in range(1, len(sorted_candles)):
            curr = sorted_candles[i]
            prev = sorted_candles[i - 1]
            tr = max(
                curr.high - curr.low,
                abs(curr.high - prev.close),
                abs(curr.low - prev.close)
            )
            tr_list.append(tr)

        atr_series: List[float] = []
        if len(tr_list) <= self.atr_period:
            avg_tr = float(np.mean(tr_list))
            return [avg_tr] * len(candles)

        # Initial simple average
        curr_atr = float(np.mean(tr_list[:self.atr_period]))
        atr_series = [curr_atr] * self.atr_period

        # Wilder's smoothing
        for i in range(self.atr_period, len(tr_list)):
            curr_atr = (curr_atr * (self.atr_period - 1) + tr_list[i]) / self.atr_period
            atr_series.append(float(curr_atr))

        return atr_series

    def calculate_garman_klass_volatility(self, candles: List[Candle], window: int = 20) -> float:
        """
        Garman-Klass estimator:
        sigma^2 = 0.5 * (ln(H/L))^2 - (2*ln(2) - 1) * (ln(C/O))^2
        """
        if len(candles) < window:
            return 0.0

        recent = candles[-window:]
        vals = []
        for c in recent:
            if c.low <= 0 or c.open <= 0:
                continue
            hl_ratio = np.log(c.high / c.low)
            co_ratio = np.log(c.close / c.open)
            term = 0.5 * (hl_ratio ** 2) - (2.0 * np.log(2.0) - 1.0) * (co_ratio ** 2)
            vals.append(term)

        if not vals:
            return 0.0

        daily_variance = float(np.mean(vals))
        # Annualized or daily annualized volatility
        return float(np.sqrt(max(0.0, daily_variance)) * 100.0)

    def calculate_parkinson_volatility(self, candles: List[Candle], window: int = 20) -> float:
        """
        Parkinson high-low volatility:
        sigma^2 = (1 / (4 * ln(2))) * mean((ln(H/L))^2)
        """
        if len(candles) < window:
            return 0.0

        recent = candles[-window:]
        hl_terms = [np.log(c.high / c.low) ** 2 for c in recent if c.low > 0]
        if not hl_terms:
            return 0.0

        var = (1.0 / (4.0 * np.log(2.0))) * np.mean(hl_terms)
        return float(np.sqrt(var) * 100.0)

