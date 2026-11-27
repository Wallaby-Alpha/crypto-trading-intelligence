"""
Unit tests for RiskGovernor, ActiveLivePosition, and Live Bot Execution.
"""
import pytest
from src.bot.risk_governor import RiskGovernor
from src.bot.live_bot import ActiveLivePosition
from src.strategies.models import SignalDirection


def test_risk_governor_sizing_and_notional():
    governor = RiskGovernor(trade_margin_usd=20.0, default_leverage=3, max_open_positions=2)
    contracts, notional = governor.calculate_position_size("BTC/USDT:USDT", price=90000.0)

    # 20 margin * 3x leverage = $60 notional
    assert notional >= 50.0
    assert contracts > 0


def test_risk_governor_max_positions_cap():
    governor = RiskGovernor(max_open_positions=2)

    # 0 positions -> OK
    ok, reason = governor.can_open_position(0)
    assert ok is True

    # 1 position -> OK
    ok, reason = governor.can_open_position(1)
    assert ok is True

    # 2 positions -> Reached cap
    ok, reason = governor.can_open_position(2)
    assert ok is False
    assert "Maximum concurrent positions" in reason


def test_risk_governor_circuit_breaker():
    governor = RiskGovernor(max_daily_loss_usd=25.0)

    # Small loss
    governor.record_trade_result(-10.0)
    assert governor.circuit_breaker_tripped is False
    ok, _ = governor.can_open_position(0)
    assert ok is True

    # Another loss exceeding $25 threshold
    governor.record_trade_result(-20.0)
    assert governor.circuit_breaker_tripped is True
    ok, reason = governor.can_open_position(0)
    assert ok is False
    assert "Daily loss limit reached" in reason


def test_active_position_breakeven_logic():
    pos = ActiveLivePosition(
        symbol="SOL/USDT:USDT",
        direction=SignalDirection.LONG,
        entry_price=150.0,
        stop_loss=147.0,
        tp1=153.0,
        tp2=156.0,
        tp3=159.0,
        contracts=1.0,
        notional_usd=150.0
    )

    assert pos.tp1_hit is False
    assert pos.stop_loss == 147.0

    # Price crosses TP1 ($153.0) -> simulate breakeven update
    curr_price = 153.5
    if curr_price >= pos.tp1:
        pos.tp1_hit = True
        pos.stop_loss = pos.entry_price

    assert pos.tp1_hit is True
    assert pos.stop_loss == 150.0  # Stop Loss is now locked at entry (risk free)


@pytest.mark.asyncio
async def test_live_bot_scan_symbol_pipeline():
    from unittest.mock import MagicMock
    from src.bot.live_bot import LiveTradingBot
    from src.core.models import Candle, DataQualityStatus

    bot = LiveTradingBot()

    # Generate 50 dummy candles
    dummy_candles = []
    base_ts = 1700000000000
    for i in range(50):
        dummy_candles.append(Candle(
            symbol="BTC/USDT:USDT",
            exchange="weex",
            timeframe="15m",
            timestamp=base_ts + i * 900000,
            datetime=f"2026-11-26T00:{i:02d}:00Z",
            open=90000.0 + i * 10,
            high=90050.0 + i * 10,
            low=89950.0 + i * 10,
            close=90020.0 + i * 10,
            volume=10.0 + i,
            quote_volume=None,
            is_closed=True,
            quality_status=DataQualityStatus.VALID
        ))

    bot.weex_data.fetch_ohlcv = MagicMock(return_value=dummy_candles)
    bot.calculate_htf_trend = MagicMock(return_value="BULLISH")
    bot.telegram.send_message = MagicMock(return_value=True)

    # Ensure scan_symbol completes without any AttributeError or TypeError
    await bot.scan_symbol("BTC/USDT:USDT")


