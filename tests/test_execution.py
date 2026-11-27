"""
Unit tests for Paper Trading Engine & WEEX Execution Adapter.
"""
import pytest
from src.core.models import Candle, DataQualityStatus
from src.strategies.models import (
    TradeSignal, SignalDirection, SignalCategory, SignalState,
    ScoreBreakdown, EntryMethod
)
from src.execution.paper_engine import PaperTradingEngine
from src.execution.weex_execution import WeexExecutionAdapter
from src.execution.models import PositionStatus


@pytest.fixture
def sample_long_signal():
    breakdown = ScoreBreakdown(total_score=85.0, category=SignalCategory.STRONG)
    return TradeSignal(
        id="sig_exec_test_1",
        strategy_name="SweepReversal",
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        direction=SignalDirection.LONG,
        state=SignalState.CONFIRMED,
        timestamp=1700000000000,
        datetime="2026-11-25T00:00:00Z",
        current_price=90000.0,
        score=breakdown,
        entry_method=EntryMethod.MARKET_CONFIRMATION,
        proposed_entry=90000.0,
        stop_loss=89000.0,
        tp1=91000.0,
        tp2=92000.0,
        tp3=93000.0,
        risk_reward_tp2=2.0,
        atr=500.0,
        position_size_usd=9000.0,
        confirmations=["Low sweep"]
    )


def test_paper_engine_open_position(sample_long_signal):
    engine = PaperTradingEngine(initial_capital_usd=10000.0)
    pos = engine.open_position_from_signal(sample_long_signal)

    assert pos is not None
    assert pos.status == PositionStatus.OPEN
    assert pos.direction == SignalDirection.LONG
    assert len(engine.open_positions) == 1
    # Check that fee was deducted
    assert engine.capital < 10000.0


def test_paper_engine_tp1_and_breakeven(sample_long_signal):
    engine = PaperTradingEngine(initial_capital_usd=10000.0)
    pos = engine.open_position_from_signal(sample_long_signal)
    initial_contracts = pos.initial_contracts
    initial_sl = pos.stop_loss

    # Candle reaches TP1 ($91,000)
    tp1_candle = Candle(
        symbol="BTC/USDT:USDT", exchange="weex", timeframe="5m",
        timestamp=1700000300000, datetime="",
        open=90500.0, high=91200.0, low=90400.0, close=91100.0,
        volume=10.0, quote_volume=None, is_closed=True, quality_status=DataQualityStatus.VALID
    )
    engine.update_positions(tp1_candle)

    assert pos.tp1_hit is True
    # 33% closed
    assert pos.remaining_contracts < initial_contracts
    # SL moved to Breakeven
    assert pos.stop_loss == pos.entry_price
    assert pos.stop_loss > initial_sl
    assert pos.status == PositionStatus.PARTIALLY_CLOSED


def test_paper_engine_stop_loss(sample_long_signal):
    engine = PaperTradingEngine(initial_capital_usd=10000.0)
    pos = engine.open_position_from_signal(sample_long_signal)

    # Candle hits stop loss ($89,000)
    stop_candle = Candle(
        symbol="BTC/USDT:USDT", exchange="weex", timeframe="5m",
        timestamp=1700000300000, datetime="",
        open=89500.0, high=89600.0, low=88800.0, close=88900.0,
        volume=10.0, quote_volume=None, is_closed=True, quality_status=DataQualityStatus.VALID
    )
    engine.update_positions(stop_candle)

    assert len(engine.open_positions) == 0
    assert len(engine.closed_positions) == 1
    assert engine.closed_positions[0].status == PositionStatus.CLOSED
    assert engine.closed_positions[0].exit_reason == "STOP_LOSS"
    assert engine.closed_positions[0].realized_pnl_usd < 0


def test_weex_execution_adapter_safety_mode(sample_long_signal):
    adapter = WeexExecutionAdapter()
    assert adapter.check_authorization() is False

    # Placing order while unauthorized returns SIMULATED_SUCCESS and blocks live exchange calls
    res = adapter.execute_signal(sample_long_signal)
    assert res["status"] == "SIMULATED_SUCCESS"
    assert "Live trading disabled" in res["note"]

    # Emergency kill switch operates safely in simulation mode
    kill_res = adapter.emergency_kill_switch()
    assert kill_res["status"] == "SUCCESS"

    # update_stop_loss and close_position operate safely in simulation mode
    sl_res = adapter.update_stop_loss("BTC/USDT:USDT", 0.0005, sample_long_signal.direction, 61000.0)
    assert sl_res["status"] == "SIMULATED_SUCCESS"

    close_res = adapter.close_position("BTC/USDT:USDT", 0.0005, sample_long_signal.direction)
    assert close_res["status"] == "SIMULATED_SUCCESS"

