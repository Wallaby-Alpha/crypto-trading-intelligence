"""
Tests for Data Quality & Integrity Monitor.
"""
import pytest
from src.core.quality import DataQualityMonitor
from src.core.models import Candle, OpenInterestRecord, FundingRateRecord, DataQualityStatus


def test_candle_integrity_validation():
    monitor = DataQualityMonitor()

    # Valid candle
    valid_c = Candle(
        symbol="BTC/USDT", exchange="weex", timeframe="1m", timestamp=1000, datetime="",
        open=100.0, high=105.0, low=98.0, close=102.0, volume=10.0
    )
    ok, _, reason = monitor.validate_candle(valid_c)
    assert ok is True
    assert reason is None

    # Invalid candle: High < Open
    bad_high_c = Candle(
        symbol="BTC/USDT", exchange="weex", timeframe="1m", timestamp=1000, datetime="",
        open=100.0, high=95.0, low=90.0, close=92.0, volume=10.0
    )
    ok, c, reason = monitor.validate_candle(bad_high_c)
    assert ok is False
    assert c.quality_status == DataQualityStatus.ANOMALOUS
    assert "High" in reason

    # Invalid candle: Negative Volume
    neg_vol_c = Candle(
        symbol="BTC/USDT", exchange="weex", timeframe="1m", timestamp=1000, datetime="",
        open=100.0, high=105.0, low=98.0, close=102.0, volume=-5.0
    )
    ok, c, reason = monitor.validate_candle(neg_vol_c)
    assert ok is False
    assert "Negative volume" in reason


def test_oi_and_funding_validation():
    monitor = DataQualityMonitor()

    # Zero OI
    zero_oi = OpenInterestRecord(
        symbol="SOL/USDT", exchange="weex", timestamp=1000, datetime="", open_interest_amount=0.0
    )
    ok, oi, reason = monitor.validate_open_interest(zero_oi)
    assert ok is False
    assert oi.quality_status == DataQualityStatus.SUSPECT

    # Extreme Funding Anomaly (> 5%)
    bad_fr = FundingRateRecord(
        symbol="SOL/USDT", exchange="weex", timestamp=1000, datetime="", funding_rate=0.08
    )
    ok, fr, reason = monitor.validate_funding_rate(bad_fr)
    assert ok is False
    assert fr.quality_status == DataQualityStatus.ANOMALOUS
