"""
Master Trading Event Engine.
Coordinates all specialized event detection modules:
- Liquidity sweeps & stop hunts
- Failed acceptance & reclaims
- Market structure shifts (BOS / CHoCH / MSS)
- CVD orderflow divergence & absorption
- Open Interest 4-quadrant behavior matrix
- VWAP & Volume Profile rejections/reclaims
Persists detected events to the database with full audit trail.
"""
import json
import logging
from typing import List, Dict, Any, Optional
from src.core.models import Candle, OpenInterestMetrics
from src.indicators.cvd import CVDBar
from src.indicators.vwap import VWAPBand
from src.indicators.volume_profile import VolumeProfileResult
from src.core.database import DatabaseManager
from src.events.models import (
    MarketEventBundle, LiquiditySweepEvent, FailedAcceptanceEvent,
    MarketStructureEvent, CVDDivergenceEvent, OIBehaviorEvent,
    VWAPVolumeEvent
)
from src.events.swing_points import SwingPointDetector
from src.events.liquidity_sweeps import LiquiditySweepDetector
from src.events.failed_acceptance import FailedAcceptanceDetector
from src.events.market_structure import MarketStructureDetector
from src.events.cvd_divergence import CVDDivergenceDetector
from src.events.oi_classifier import OIBehaviorClassifier
from src.events.vwap_volume_events import VWAPVolumeEventDetector

logger = logging.getLogger(__name__)


class EventEngine:
    def __init__(self, db_manager: Optional[DatabaseManager] = None, db: Optional[DatabaseManager] = None):
        self.db = db or db_manager

        # Specialized detection modules
        self.swing_detector = SwingPointDetector(left_bars=3, right_bars=3)
        self.sweep_detector = LiquiditySweepDetector(min_penetration_pct=0.05, min_atr_multiplier=0.10)
        self.failed_acceptance_detector = FailedAcceptanceDetector(max_closes_beyond=2)
        self.market_structure_detector = MarketStructureDetector(displacement_atr_ratio=1.2)
        self.cvd_divergence_detector = CVDDivergenceDetector(lookback_bars=14)
        self.oi_classifier = OIBehaviorClassifier(expansion_threshold_pct=1.5)
        self.vwap_event_detector = VWAPVolumeEventDetector(high_volume_multiplier=1.8)

    def analyze_candle(
        self,
        candles: List[Candle],
        cvd_bars: List[CVDBar],
        oi_metrics: Optional[OpenInterestMetrics],
        vwap_bands: List[VWAPBand],
        vp_result: Optional[VolumeProfileResult],
        atr_value: float,
        target_index: Optional[int] = None
    ) -> MarketEventBundle:
        """
        Runs complete event detection suite on candles at target_index (defaults to latest candle).
        Guarantees strict zero lookahead bias.
        """
        if not candles:
            return MarketEventBundle(symbol="", timeframe="", timestamp=0)

        idx = target_index if target_index is not None else len(candles) - 1
        curr_c = candles[idx]

        # 1. Detect Liquidity Sweeps
        sweeps = self.sweep_detector.detect_sweeps_at_candle(candles, idx, atr_value)

        # 2. Detect Failed Acceptance & Failed Reclaim
        failed_acc = self.failed_acceptance_detector.detect_events_at_candle(candles, idx, atr_value)

        # 3. Detect Market Structure Shifts (BOS / CHoCH / MSS)
        structure_events = self.market_structure_detector.detect_structure_events_at_candle(candles, idx, atr_value)

        # 4. Detect CVD Divergence
        cvd_divs = []
        if cvd_bars and len(cvd_bars) > idx:
            div = self.cvd_divergence_detector.detect_divergence_at_candle(candles, cvd_bars, idx)
            if div:
                cvd_divs.append(div)

        # 5. Classify OI Behavior
        oi_events = []
        if oi_metrics and idx >= 3:
            price_change_pct = ((curr_c.close - candles[idx - 3].close) / candles[idx - 3].close) * 100.0
            oi_evt = self.oi_classifier.classify_behavior(curr_c.symbol, price_change_pct, oi_metrics)
            if oi_evt:
                oi_events.append(oi_evt)

        # 6. Detect VWAP & Volume Profile interaction events
        vwap_events = self.vwap_event_detector.detect_events_at_candle(candles, vwap_bands, vp_result, idx)

        bundle = MarketEventBundle(
            symbol=curr_c.symbol,
            timeframe=curr_c.timeframe,
            timestamp=curr_c.timestamp,
            datetime=curr_c.datetime,
            sweeps=sweeps,
            failed_acceptances=failed_acc,
            structure_events=structure_events,
            cvd_divergences=cvd_divs,
            oi_events=oi_events,
            vwap_events=vwap_events
        )

        if self.db:
            self._persist_bundle(bundle)

        return bundle

    def _persist_bundle(self, bundle: MarketEventBundle):
        """
        Stores any detected events in the persistent database.
        """
        total_events = (
            len(bundle.sweeps) + len(bundle.failed_acceptances) +
            len(bundle.structure_events) + len(bundle.cvd_divergences) +
            len(bundle.oi_events) + len(bundle.vwap_events)
        )
        if total_events == 0:
            return

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            # Ensure market_events table exists
            cur.execute("""
            CREATE TABLE IF NOT EXISTS market_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                category TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details_json TEXT NOT NULL
            );
            """)

            for s in bundle.sweeps:
                cur.execute(
                    "INSERT INTO market_events (symbol, timeframe, timestamp, category, event_type, details_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (bundle.symbol, bundle.timeframe, bundle.timestamp, "LIQUIDITY_SWEEP", s.direction.value, s.model_dump_json())
                )

            for f in bundle.failed_acceptances:
                cur.execute(
                    "INSERT INTO market_events (symbol, timeframe, timestamp, category, event_type, details_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (bundle.symbol, bundle.timeframe, bundle.timestamp, "FAILED_ACCEPTANCE", f.event_type.value, f.model_dump_json())
                )

            for m in bundle.structure_events:
                cur.execute(
                    "INSERT INTO market_events (symbol, timeframe, timestamp, category, event_type, details_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (bundle.symbol, bundle.timeframe, bundle.timestamp, "MARKET_STRUCTURE", m.event_type.value, m.model_dump_json())
                )

            for c in bundle.cvd_divergences:
                cur.execute(
                    "INSERT INTO market_events (symbol, timeframe, timestamp, category, event_type, details_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (bundle.symbol, bundle.timeframe, bundle.timestamp, "CVD_DIVERGENCE", c.divergence_type.value, c.model_dump_json())
                )

            for o in bundle.oi_events:
                cur.execute(
                    "INSERT INTO market_events (symbol, timeframe, timestamp, category, event_type, details_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (bundle.symbol, bundle.timeframe, bundle.timestamp, "OI_BEHAVIOR", o.regime.value, o.model_dump_json())
                )

            for v in bundle.vwap_events:
                cur.execute(
                    "INSERT INTO market_events (symbol, timeframe, timestamp, category, event_type, details_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (bundle.symbol, bundle.timeframe, bundle.timestamp, "VWAP_VOLUME", v.event_type.value, v.model_dump_json())
                )

            conn.commit()

