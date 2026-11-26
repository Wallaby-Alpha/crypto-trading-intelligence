"""
Tests for Quantitative Indicators: CVD, OI, VWAP, Volume Profile, and Volatility.
"""
import pytest
from src.core.models import Candle, Trade, OpenInterestRecord, TradeSide, DataQualityStatus
from src.indicators.cvd import CVDEngine
from src.indicators.oi import OpenInterestEngine
from src.indicators.vwap import VWAPEngine
from src.indicators.volume_profile import VolumeProfileEngine
from src.indicators.volatility import VolatilityEngine


@pytest.fixture
def sample_candles():
    base_ts = 1700000000000
    candles = []
    prices = [100.0, 102.0, 105.0, 103.0, 108.0, 107.0, 110.0, 109.0, 112.0, 115.0]
    for i, p in enumerate(prices):
        candles.append(Candle(
            symbol="TEST/USDT",
            exchange="weex",
            timeframe="5m",
            timestamp=base_ts + (i * 300000),
            datetime=f"2023-11-14T{i:02d}:00:00Z",
            open=p - 1.0,
            high=p + 2.0,
            low=p - 1.5,
            close=p,
            volume=1000.0 + (i * 50),
            is_closed=True,
            quality_status=DataQualityStatus.VALID
        ))
    return candles


def test_cvd_calculation_from_trades(sample_candles):
    cvd_engine = CVDEngine(momentum_window=3)
    c0 = sample_candles[0]
    c1 = sample_candles[1]

    # Create synthetic buy and sell trades
    trades = [
        Trade(id="1", symbol="TEST/USDT", exchange="weex", timestamp=c0.timestamp + 1000, datetime="", price=100.0, amount=10.0, side=TradeSide.BUY),
        Trade(id="2", symbol="TEST/USDT", exchange="weex", timestamp=c0.timestamp + 2000, datetime="", price=100.5, amount=4.0, side=TradeSide.SELL),
        Trade(id="3", symbol="TEST/USDT", exchange="weex", timestamp=c1.timestamp + 1000, datetime="", price=102.0, amount=20.0, side=TradeSide.BUY),
    ]

    bars = cvd_engine.compute_from_trades(trades, [c0, c1])
    assert len(bars) == 2
    # Bar 0: buy 10, sell 4 -> delta = 6, cumulative = 6
    assert bars[0].delta == 6.0
    assert bars[0].cumulative_delta == 6.0
    # Bar 1: buy 20, sell 0 -> delta = 20, cumulative = 26
    assert bars[1].delta == 20.0
    assert bars[1].cumulative_delta == 26.0


def test_cvd_divergence_detection(sample_candles):
    cvd_engine = CVDEngine()
    # Create artificial bearish divergence: Price higher high, CVD lower high
    bars = cvd_engine.estimate_from_candles(sample_candles)
    # Manually tweak CVD to simulate buyer exhaustion on last bar
    bars[-1].cumulative_delta = bars[-5].cumulative_delta - 500.0

    div = cvd_engine.detect_divergence(sample_candles, bars, lookback=8)
    assert div is not None
    assert div["type"] == "BEARISH_CVD_DIVERGENCE"


def test_open_interest_engine():
    oi_engine = OpenInterestEngine()
    base_ts = 1700000000000
    # Create OI sequence at 0, 5m, 15m, 30m, 60m
    history = [
        OpenInterestRecord(symbol="TEST/USDT", exchange="weex", timestamp=base_ts - 3600*1000, datetime="", open_interest_amount=10000.0),
        OpenInterestRecord(symbol="TEST/USDT", exchange="weex", timestamp=base_ts - 1800*1000, datetime="", open_interest_amount=10200.0),
        OpenInterestRecord(symbol="TEST/USDT", exchange="weex", timestamp=base_ts - 900*1000, datetime="", open_interest_amount=10400.0),
        OpenInterestRecord(symbol="TEST/USDT", exchange="weex", timestamp=base_ts - 300*1000, datetime="", open_interest_amount=10600.0),
        OpenInterestRecord(symbol="TEST/USDT", exchange="weex", timestamp=base_ts, datetime="", open_interest_amount=10800.0)
    ]
    metrics = oi_engine.compute_metrics(history, current_price=110.0, past_price=100.0)
    assert metrics is not None
    assert metrics.current_oi == 10800.0
    assert metrics.oi_change_60m == 800.0
    assert metrics.oi_pct_change_60m == 8.0
    assert metrics.oi_divergence_flag == "PRICE_UP_OI_UP"


def test_vwap_engine(sample_candles):
    vwap_engine = VWAPEngine()
    bands = vwap_engine.calculate_anchored_vwap(sample_candles)
    assert len(bands) == len(sample_candles)
    last_band = bands[-1]
    assert last_band.vwap > 0
    assert last_band.upper_band_1 > last_band.vwap
    assert last_band.lower_band_1 < last_band.vwap
    assert last_band.upper_band_2 > last_band.upper_band_1


def test_volume_profile_engine(sample_candles):
    vp_engine = VolumeProfileEngine(num_bins=20)
    result = vp_engine.compute_profile(sample_candles)
    assert result is not None
    assert result.poc_price >= min(c.low for c in sample_candles)
    assert result.poc_price <= max(c.high for c in sample_candles)
    assert result.val_price <= result.vah_price
    assert result.total_volume > 0


def test_volatility_engine(sample_candles):
    vol_engine = VolatilityEngine(atr_period=5)
    atr = vol_engine.calculate_atr(sample_candles)
    assert len(atr) == len(sample_candles)
    assert atr[-1] > 0
    gk_vol = vol_engine.calculate_garman_klass_volatility(sample_candles, window=5)
    assert gk_vol >= 0
