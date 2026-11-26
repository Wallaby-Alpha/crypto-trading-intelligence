"""
Unit tests for Scanner Daemon & Telegram Notification Engine.
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from src.core.models import Candle, DataQualityStatus
from src.strategies.models import (
    TradeSignal, SignalDirection, SignalCategory, SignalState,
    ScoreBreakdown, EntryMethod
)
from src.notifications.telegram_bot import TelegramNotifier
from src.scanner.scanner_daemon import ScannerDaemon


@pytest.fixture
def sample_signal():
    breakdown = ScoreBreakdown(
        liquidity_quality=14.0,
        market_structure=13.5,
        oi_behavior=12.0,
        cvd_confirmation=13.0,
        volume_displacement=7.0,
        vwap_context=8.0,
        htf_alignment=8.0,
        funding_context=4.0,
        risk_reward=4.5,
        total_score=84.0,
        category=SignalCategory.STRONG
    )
    return TradeSignal(
        id="sig_test_123456",
        strategy_name="LiquiditySweepReversal",
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        direction=SignalDirection.LONG,
        state=SignalState.CONFIRMED,
        timestamp=1700000000000,
        datetime="2026-11-25T00:00:00Z",
        current_price=96000.0,
        score=breakdown,
        entry_method=EntryMethod.MARKET_CONFIRMATION,
        proposed_entry=96000.0,
        stop_loss=95200.0,
        tp1=96800.0,
        tp2=97600.0,
        tp3=98400.0,
        risk_reward_tp2=2.0,
        atr=400.0,
        position_size_usd=12500.0,
        confirmations=["Low sweep at $95,300", "Bullish MSS confirmed", "Bullish CVD absorption"]
    )


def test_telegram_alert_formatting(sample_signal):
    notifier = TelegramNotifier()  # Simulation mode
    text = notifier.format_signal_alert(sample_signal)

    assert "STRONG" in text
    assert "LONG" in text
    assert "BTC/USDT" in text
    assert "96,000" in text
    assert "Stop Loss" in text
    assert "Take Profit 1" in text
    assert "Liquidity Sweep" in text
    assert "Market Structure" in text


def test_telegram_lifecycle_update():
    notifier = TelegramNotifier()
    msg = notifier.format_lifecycle_update(
        signal_id="sig_test_123456",
        symbol="BTC/USDT:USDT",
        direction="LONG",
        event_type="TP1_HIT",
        details="Hit TP1 at $96,800. Closed 33%. SL moved to Breakeven $96,000."
    )

    assert "TP1_HIT" in msg
    assert "BTC/USDT" in msg
    assert "$96,800" in msg


@pytest.mark.asyncio
async def test_telegram_notifier_mock_send(sample_signal):
    notifier = TelegramNotifier(rate_limit_seconds=0.01)
    sent = await notifier.notify_signal(sample_signal)
    assert sent is True
    # Duplicate signal shouldn't resend
    second_sent = await notifier.notify_signal(sample_signal)
    assert second_sent is False


@pytest.mark.asyncio
async def test_scanner_daemon_mock_cycle(monkeypatch):
    mock_db = MagicMock()
    mock_db.get_candle_models.return_value = [
        Candle(
            symbol="BTC/USDT:USDT", exchange="weex", timeframe="5m",
            timestamp=1700000000000 + i * 300000, datetime="",
            open=90000.0 + i, high=90050.0 + i, low=89980.0 + i, close=90020.0 + i,
            volume=50.0, quote_volume=None, is_closed=True, quality_status=DataQualityStatus.VALID
        )
        for i in range(40)
    ]
    mock_adapter = MagicMock()
    daemon = ScannerDaemon(db=mock_db, adapter=mock_adapter, max_symbols=3)
    daemon.monitored_symbols = ["BTC/USDT:USDT"]
    
    # Mock data pipeline sync
    daemon.pipeline.sync_symbol_full = MagicMock(return_value={
        "symbol": "BTC/USDT:USDT",
        "timeframes": {
            "5m": {
                "candle_count": 40,
                "current_atr": 100.0,
                "vwap_bands": [],
                "volume_profile": None,
                "cvd_bars": []
            }
        },
        "oi": None,
        "funding": None
    })

    cycle_res = await daemon.run_scan_cycle()
    assert cycle_res["cycle"] == 1
    assert cycle_res["symbols_scanned"] == 1
    assert "duration_seconds" in cycle_res
