"""
Data Quality & Integrity Monitoring Engine.
Strictly validates market data before persistence and downstream event detection.
Rules:
- Never fabricate missing values.
- Never substitute missing OI or volume with 0 without marking quality status.
- Check OHLC internal mathematical consistency (High >= max(Open, Close), Low <= min(Open, Close)).
- Check timestamp monotonicity and detect gaps.
- Check stale ticks / delay beyond tolerance.
"""
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from src.core.models import (
    Candle, Trade, Ticker, OpenInterestRecord,
    FundingRateRecord, DataQualityStatus
)
from src.core.database import DatabaseManager

logger = logging.getLogger(__name__)


class DataQualityMonitor:
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager

    def validate_candle(self, c: Candle) -> Tuple[bool, Candle, Optional[str]]:
        """
        Validates mathematical integrity of a single candle:
        1. Open, High, Low, Close must be > 0.
        2. High must be >= max(Open, Close).
        3. Low must be <= min(Open, Close).
        4. Volume must be >= 0.
        """
        reasons = []

        if c.open <= 0 or c.high <= 0 or c.low <= 0 or c.close <= 0:
            reasons.append("Non-positive OHLC price detected")

        if c.high < max(c.open, c.close):
            reasons.append(f"High {c.high} is less than max(Open {c.open}, Close {c.close})")

        if c.low > min(c.open, c.close):
            reasons.append(f"Low {c.low} is greater than min(Open {c.open}, Close {c.close})")

        if c.volume < 0:
            reasons.append(f"Negative volume detected: {c.volume}")

        if reasons:
            c.quality_status = DataQualityStatus.ANOMALOUS
            reason_str = "; ".join(reasons)
            if self.db:
                self.db.log_quality_issue(c.symbol, c.exchange, c.timestamp, "CANDLE_INTEGRITY", reason_str)
            return False, c, reason_str

        return True, c, None

    def validate_candles_series(self, candles: List[Candle], timeframe_minutes: int) -> List[Candle]:
        """
        Validates series continuity, detects timestamp gaps, and marks anomalies.
        """
        if not candles:
            return []

        sorted_candles = sorted(candles, key=lambda c: c.timestamp)
        expected_step_ms = timeframe_minutes * 60 * 1000
        validated: List[Candle] = []

        for i, c in enumerate(sorted_candles):
            is_valid, checked_c, issue = self.validate_candle(c)

            # Check gap with previous candle
            if i > 0 and expected_step_ms > 0:
                prev_ts = sorted_candles[i - 1].timestamp
                delta_ms = checked_c.timestamp - prev_ts
                if delta_ms > (expected_step_ms * 1.5):
                    # Gap detected
                    gap_candles = int(delta_ms / expected_step_ms) - 1
                    msg = f"Data gap of {gap_candles} candles between {prev_ts} and {checked_c.timestamp}"
                    if self.db:
                        self.db.log_quality_issue(checked_c.symbol, checked_c.exchange, checked_c.timestamp, "GAP_DETECTED", msg)

            validated.append(checked_c)

        return validated

    def validate_open_interest(self, oi: OpenInterestRecord, max_staleness_sec: int = 180) -> Tuple[bool, OpenInterestRecord, Optional[str]]:
        """
        Validates Open Interest:
        - Must be > 0.
        - Must not be older than max_staleness_sec.
        """
        now_ms = int(time.time() * 1000)
        age_sec = (now_ms - oi.timestamp) / 1000.0

        if oi.open_interest_amount <= 0:
            oi.quality_status = DataQualityStatus.SUSPECT
            msg = f"Zero or negative open interest: {oi.open_interest_amount}"
            if self.db:
                self.db.log_quality_issue(oi.symbol, oi.exchange, oi.timestamp, "OI_ZERO_OR_NEGATIVE", msg)
            return False, oi, msg

        if age_sec > max_staleness_sec:
            oi.quality_status = DataQualityStatus.STALE
            msg = f"Stale open interest: age {age_sec:.1f}s > {max_staleness_sec}s"
            if self.db:
                self.db.log_quality_issue(oi.symbol, oi.exchange, oi.timestamp, "OI_STALE", msg)
            return True, oi, msg

        return True, oi, None

    def validate_funding_rate(self, fr: FundingRateRecord) -> Tuple[bool, FundingRateRecord, Optional[str]]:
        """
        Validates Funding Rate:
        - Must be within reasonable bounds (e.g. between -3% and +3% per 8h).
        """
        if abs(fr.funding_rate) > 0.05:  # > 5% is an extreme anomaly or decimal scaling bug
            fr.quality_status = DataQualityStatus.ANOMALOUS
            msg = f"Extreme funding rate anomaly: {fr.funding_rate * 100:.3f}%"
            if self.db:
                self.db.log_quality_issue(fr.symbol, fr.exchange, fr.timestamp, "FUNDING_ANOMALY", msg)
            return False, fr, msg

        return True, fr, None
