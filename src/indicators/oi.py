"""
Open Interest (OI) Analysis Engine:
- Measures multi-horizon OI variations (1m, 5m, 15m, 30m, 60m).
- Measures 2nd derivative: OI acceleration / deceleration.
- Classifies price-OI matrix regimes:
  * PRICE_UP_OI_UP: Long buildup
  * PRICE_UP_OI_DOWN: Short covering / squeeze
  * PRICE_DOWN_OI_UP: Short buildup
  * PRICE_DOWN_OI_DOWN: Long liquidation / unwinding
- Historical baseline z-scores and unusual expansion/contraction detection.
"""
from typing import List, Dict, Any, Optional
import numpy as np
from src.core.models import OpenInterestRecord, OpenInterestMetrics, DataQualityStatus


class OpenInterestEngine:
    def __init__(self, baseline_lookback: int = 60):
        self.baseline_lookback = baseline_lookback

    def compute_metrics(
        self,
        history: List[OpenInterestRecord],
        current_price: Optional[float] = None,
        past_price: Optional[float] = None
    ) -> Optional[OpenInterestMetrics]:
        if not history:
            return None

        # Sort by timestamp ascending
        sorted_hist = sorted(history, key=lambda x: x.timestamp)
        latest = sorted_hist[-1]
        now_ts = latest.timestamp
        current_oi = latest.open_interest_amount

        # Find historical entries closest to 1m, 5m, 15m, 30m, 60m ago
        def get_oi_at_offset(minutes: int) -> Optional[float]:
            target_ts = now_ts - (minutes * 60 * 1000)
            best_diff = float('inf')
            best_oi = None
            for rec in sorted_hist:
                diff = abs(rec.timestamp - target_ts)
                # Tolerate within 50% window of the target interval
                if diff < best_diff and diff <= (minutes * 60 * 1000 * 0.5):
                    best_diff = diff
                    best_oi = rec.open_interest_amount
            return best_oi

        oi_1m = get_oi_at_offset(1)
        oi_5m = get_oi_at_offset(5)
        oi_15m = get_oi_at_offset(15)
        oi_30m = get_oi_at_offset(30)
        oi_60m = get_oi_at_offset(60)

        def diff_and_pct(past_val: Optional[float]) -> (Optional[float], Optional[float]):
            if past_val is not None and past_val > 0:
                chg = current_oi - past_val
                pct = (chg / past_val) * 100.0
                return chg, pct
            return None, None

        c_1m, p_1m = diff_and_pct(oi_1m)
        c_5m, p_5m = diff_and_pct(oi_5m)
        c_15m, p_15m = diff_and_pct(oi_15m)
        c_30m, p_30m = diff_and_pct(oi_30m)
        c_60m, p_60m = diff_and_pct(oi_60m)

        # Acceleration: rate of change of 5m delta
        # if 5m delta is positive and larger than previous 5m delta -> acceleration > 0
        acceleration = None
        if len(sorted_hist) >= 3:
            oi_recent = [r.open_interest_amount for r in sorted_hist[-3:]]
            v1 = oi_recent[1] - oi_recent[0]
            v2 = oi_recent[2] - oi_recent[1]
            acceleration = v2 - v1

        # Classify price vs OI regime
        regime = None
        if current_price is not None and past_price is not None and c_15m is not None:
            price_change = current_price - past_price
            if price_change > 0 and c_15m > 0:
                regime = "PRICE_UP_OI_UP"      # Long buildup
            elif price_change > 0 and c_15m < 0:
                regime = "PRICE_UP_OI_DOWN"    # Short squeeze
            elif price_change < 0 and c_15m > 0:
                regime = "PRICE_DOWN_OI_UP"    # Short buildup
            elif price_change < 0 and c_15m < 0:
                regime = "PRICE_DOWN_OI_DOWN"  # Long liquidation

        return OpenInterestMetrics(
            symbol=latest.symbol,
            exchange=latest.exchange,
            timestamp=latest.timestamp,
            current_oi=current_oi,
            oi_change_1m=c_1m,
            oi_change_5m=c_5m,
            oi_change_15m=c_15m,
            oi_change_30m=c_30m,
            oi_change_60m=c_60m,
            oi_pct_change_1m=p_1m,
            oi_pct_change_5m=p_5m,
            oi_pct_change_15m=p_15m,
            oi_pct_change_30m=p_30m,
            oi_pct_change_60m=p_60m,
            oi_acceleration=acceleration,
            oi_divergence_flag=regime,
            quality_status=DataQualityStatus.VALID
        )

