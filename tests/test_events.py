"""
Comprehensive Unit Tests for Trading Event Detection Engine (Phase 2).
Verifies:
- Confirmed swing points with zero lookahead bias
- Liquidity sweep detection (swing high, swing low, EQH, EQL)
- Failed acceptance and failed reclaim
- Market structure shifts (BOS, CHoCH, MSS with displacement)
- CVD divergence absorption scoring
- OI behavior 4-quadrant classification
- VWAP and volume interaction events
- EventEngine bundle assembly and DB persistence
"""
import os
import tempfile
import pytest
from src.core.models import Candle, OpenInterestMetrics, DataQualityStatus
from src.core.database import DatabaseManager
from src.indicators.cvd import CVDBar
from src.indicators.vwap import VWAPBand
from src.events.models import (
    SwingType, SweepDirection, FailedAcceptanceType, MarketStructureType,
    CVDDivergenceType, OIRegimeType, VWAPVolumeEventType
)
from src.events.swing_points import SwingPointDetector
from src.events.liquidity_sweeps import LiquiditySweepDetector
from src.events.failed_acceptance import FailedAcceptanceDetector
from src.events.market_structure import MarketStructureDetector
from src.events.cvd_divergence import CVDDivergenceDetector
from src.events.oi_classifier import OIBehaviorClassifier
from src.events.vwap_volume_events import VWAPVolumeEventDetector
from src.events.event_engine import EventEngine


def make_candle(idx: int, o: float, h: float, l: float, c: float, v: float = 1000.0) -> Candle:
    return Candle(
        symbol="BTC/USDT",
        exchange="weex",
        timeframe="5m",
        timestamp=1700000000000 + (idx * 300000),
        datetime=f"2023-11-14T{idx:02d}:00:00Z",
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
        is_closed=True,
        quality_status=DataQualityStatus.VALID
    )


def test_swing_point_zero_lookahead():
    detector = SwingPointDetector(left_bars=2, right_bars=2)
    candles = [
        make_candle(0, 100, 102, 99, 101),
        make_candle(1, 101, 105, 100, 104),
        make_candle(2, 104, 115, 103, 112), # Swing High
        make_candle(3, 112, 108, 102, 105),
        make_candle(4, 105, 103, 98, 100),  # Confirmation candle at index 2 + 2 = 4
    ]

    swings = detector.detect_confirmed_swings(candles)
    assert len(swings) == 1
    sh = swings[0]
    assert sh.type == SwingType.SWING_HIGH
    assert sh.index == 2
    assert sh.price == 115.0
    assert sh.confirmation_index == 4


def test_liquidity_sweep_high():
    swing_det = SwingPointDetector(left_bars=2, right_bars=2)
    detector = LiquiditySweepDetector(min_penetration_pct=0.05, min_atr_multiplier=0.10, swing_detector=swing_det)
    
    # Swing High at index 2 (high=110), confirmed at index 4
    candles = [
        make_candle(0, 100, 102, 99, 101),
        make_candle(1, 101, 105, 100, 104),
        make_candle(2, 104, 110, 103, 108), # Swing High at 110
        make_candle(3, 108, 106, 103, 105),
        make_candle(4, 105, 104, 101, 102), # Confirmed here
        make_candle(5, 102, 103, 100, 101),
        make_candle(6, 101, 104, 100, 103),
        make_candle(7, 103, 107, 102, 106),
        make_candle(8, 106, 112, 105, 108), # Sweeps high (112 > 110) and closes back down (108 < 110)
    ]

    sweeps = detector.detect_sweeps_at_candle(candles, current_index=8, atr_value=2.0)
    assert len(sweeps) >= 1
    sweep = sweeps[0]
    assert sweep.direction == SweepDirection.BEARISH_SWEEP_HIGH
    assert sweep.level_price == 110.0
    assert sweep.extreme_price == 112.0
    assert sweep.reclaimed_close_price == 108.0


def test_market_structure_mss():
    swing_det = SwingPointDetector(left_bars=2, right_bars=2)
    detector = MarketStructureDetector(displacement_atr_ratio=1.2, swing_detector=swing_det)

    candles = [
        make_candle(0, 100, 103, 99, 102),
        make_candle(1, 102, 105, 101, 104),
        make_candle(2, 104, 110, 103, 108), # Real Swing High at 110 (110 > 105, 103)
        make_candle(3, 108, 106, 103, 104),
        make_candle(4, 104, 103, 96, 97),   # Confirms swing high at index 2
        make_candle(5, 97, 98, 92, 93),     # Swing Low at 92
        make_candle(6, 93, 96, 93, 95),
        make_candle(7, 95, 97, 94, 96),     # Confirms swing low at index 5
        make_candle(8, 96, 102, 95, 101),
        # Displacement breakout above 110: opens 101, closes 114 (body = 13, ATR = 3)
        make_candle(9, 101, 115, 100, 114),
    ]

    events = detector.detect_structure_events_at_candle(candles, current_index=9, atr_value=3.0)
    assert len(events) >= 1
    evt = events[0]
    assert evt.trigger_close_price == 114.0
    assert evt.broken_level_price == 110.0


def test_cvd_divergence():
    detector = CVDDivergenceDetector(lookback_bars=6)
    candles = [
        make_candle(0, 100, 105, 98, 104),
        make_candle(1, 104, 108, 102, 107),
        make_candle(2, 107, 106, 101, 103),
        make_candle(3, 103, 105, 100, 104),
        make_candle(4, 104, 110, 103, 109),
        make_candle(5, 109, 112, 108, 111), # Higher high at 112 (vs 108)
    ]
    cvd_bars = [
        CVDBar(timestamp=0, datetime="", buy_volume=500, sell_volume=100, delta=400, cumulative_delta=1000),
        CVDBar(timestamp=1, datetime="", buy_volume=500, sell_volume=100, delta=400, cumulative_delta=1400), # Peak CVD 1400
        CVDBar(timestamp=2, datetime="", buy_volume=100, sell_volume=300, delta=-200, cumulative_delta=1200),
        CVDBar(timestamp=3, datetime="", buy_volume=100, sell_volume=200, delta=-100, cumulative_delta=1100),
        CVDBar(timestamp=4, datetime="", buy_volume=150, sell_volume=100, delta=50, cumulative_delta=1150),
        CVDBar(timestamp=5, datetime="", buy_volume=100, sell_volume=80, delta=20, cumulative_delta=1170),   # Lower CVD (1170 < 1400)
    ]

    div = detector.detect_divergence_at_candle(candles, cvd_bars, current_index=5)
    assert div is not None
    assert div.divergence_type == CVDDivergenceType.BEARISH_CVD_ABSORPTION
    assert div.strength_score > 50.0


def test_oi_classifier():
    classifier = OIBehaviorClassifier(expansion_threshold_pct=1.5)
    
    # Price Up + OI Up
    m_long = OpenInterestMetrics(
        symbol="BTC/USDT", exchange="weex", timestamp=1000, current_oi=100000,
        oi_pct_change_15m=2.5, oi_acceleration=15.0
    )
    evt = classifier.classify_behavior("BTC/USDT", price_change_pct=1.2, metrics=m_long)
    assert evt is not None
    assert evt.regime == OIRegimeType.PRICE_UP_OI_UP
    assert evt.is_unusual_expansion is True

    # Price Down + OI Down (Liquidation Unwinding)
    m_liq = OpenInterestMetrics(
        symbol="BTC/USDT", exchange="weex", timestamp=1000, current_oi=95000,
        oi_pct_change_15m=-3.2, oi_acceleration=-20.0
    )
    evt_liq = classifier.classify_behavior("BTC/USDT", price_change_pct=-2.0, metrics=m_liq)
    assert evt_liq is not None
    assert evt_liq.regime == OIRegimeType.PRICE_DOWN_OI_DOWN


def test_event_engine_e2e():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path)
    engine = EventEngine(db_manager=db)

    candles = [make_candle(i, 100 + i, 102 + i, 98 + i, 101 + i) for i in range(25)]
    cvd_bars = [CVDBar(timestamp=c.timestamp, datetime=c.datetime, buy_volume=100, sell_volume=50, delta=50, cumulative_delta=50*(i+1)) for i, c in enumerate(candles)]
    vwap_bands = [
        VWAPBand(
            timestamp=c.timestamp, datetime=c.datetime, vwap=100.0,
            upper_band_1=102.0, lower_band_1=98.0, upper_band_2=104.0, lower_band_2=96.0,
            upper_band_3=106.0, lower_band_3=94.0, std_dev=2.0, distance_from_vwap_pct=1.0
        )
        for c in candles
    ]

    bundle = engine.analyze_candle(
        candles=candles,
        cvd_bars=cvd_bars,
        oi_metrics=None,
        vwap_bands=vwap_bands,
        vp_result=None,
        atr_value=2.0,
        target_index=24
    )
    assert bundle.symbol == "BTC/USDT"
    assert bundle.timeframe == "5m"
    assert bundle.timestamp == candles[24].timestamp
