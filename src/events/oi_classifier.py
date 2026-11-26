"""
Open Interest Behavior Matrix & Anomaly Classifier.
Classifies price-OI dynamics into four market regime quadrants:
1. PRICE_UP_OI_UP: Aggressive Long Buildup
2. PRICE_UP_OI_DOWN: Short Squeeze / Liquidation Covering
3. PRICE_DOWN_OI_UP: Aggressive Short Buildup
4. PRICE_DOWN_OI_DOWN: Long Liquidation / Margin Unwinding
Detects unusual OI expansion and acceleration anomalies relative to historical baseline.
"""
import time
from typing import List, Dict, Any, Optional
from src.core.models import OpenInterestMetrics
from src.events.models import OIBehaviorEvent, OIRegimeType


class OIBehaviorClassifier:
    def __init__(self, expansion_threshold_pct: float = 1.5):
        self.expansion_threshold_pct = expansion_threshold_pct

    def classify_behavior(
        self,
        symbol: str,
        price_change_pct: float,
        metrics: Any
    ) -> Optional[OIBehaviorEvent]:
        """
        Classifies OI behavior based on 15m price change and 15m OI change.
        """
        if metrics is None:
            return None

        if isinstance(metrics, dict):
            oi_pct = metrics.get("oi_pct_change_15m")
            accel = metrics.get("oi_acceleration") or 0.0
            ts = metrics.get("timestamp", int(time.time() * 1000))
            dt = metrics.get("datetime")
        else:
            oi_pct = getattr(metrics, "oi_pct_change_15m", None)
            accel = getattr(metrics, "oi_acceleration", 0.0) or 0.0
            ts = getattr(metrics, "timestamp", int(time.time() * 1000))
            dt = getattr(metrics, "datetime", None)

        if oi_pct is None:
            return None

        if price_change_pct >= 0 and oi_pct >= 0:
            regime = OIRegimeType.PRICE_UP_OI_UP
            note = "Price rising with expanding Open Interest: aggressive new long positions opening."
        elif price_change_pct >= 0 and oi_pct < 0:
            regime = OIRegimeType.PRICE_UP_OI_DOWN
            note = "Price rising with declining Open Interest: short covering / squeeze driving price up."
        elif price_change_pct < 0 and oi_pct >= 0:
            regime = OIRegimeType.PRICE_DOWN_OI_UP
            note = "Price falling with expanding Open Interest: aggressive new short positions opening."
        else:
            regime = OIRegimeType.PRICE_DOWN_OI_DOWN
            note = "Price falling with declining Open Interest: long liquidation / margin unwinding."

        is_unusual = abs(oi_pct) >= self.expansion_threshold_pct

        return OIBehaviorEvent(
            symbol=symbol,
            timestamp=ts,
            datetime=dt,
            regime=regime,
            oi_change_pct_15m=oi_pct,
            oi_acceleration=accel,
            is_unusual_expansion=is_unusual,
            context_note=note
        )

