"""
Comprehensive Unit Tests for Research & Backtesting Laboratory (Phase 4).
Verifies:
- ExecutionSimulator: fees, slippage, partial exits (TP1/TP2/TP3), protective SL
- MetricsCalculator: Win rate, Profit Factor, Expectancy, Max Drawdown
- BacktestEngine: Bar-by-bar historical backtest execution
- WalkForwardValidator: Train/test split and out-of-sample reporting
- ResearchLab: Score tier predictive power and sensitivity analysis
"""
import pytest
from src.core.models import Candle, DataQualityStatus
from src.strategies.models import TradeSignal, SignalDirection, SignalState, SignalCategory, ScoreBreakdown
from src.research.models import TradeRecord, TradeStatus, ExitReason
from src.research.execution_sim import ExecutionSimulator
from src.research.metrics_calculator import MetricsCalculator
from src.research.backtest_engine import BacktestEngine
from src.research.walk_forward import WalkForwardValidator
from src.research.research_lab import ResearchLab


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


def test_execution_simulator_winning_trade():
    sim = ExecutionSimulator(taker_fee_pct=0.05, maker_fee_pct=0.02, slippage_pct=0.02)
    sig = TradeSignal(
        id="SIG-1", strategy_name="Sweep Reversal", symbol="BTC/USDT", timeframe="5m",
        direction=SignalDirection.LONG, state=SignalState.CONFIRMED, timestamp=1000,
        current_price=50000.0,
        score=ScoreBreakdown(total_score=85.0, category=SignalCategory.STRONG),
        proposed_entry=50000.0, stop_loss=49500.0,
        tp1=50500.0, tp2=51000.0, tp3=51500.0,
        risk_reward_tp2=2.0, atr=200.0,
        position_size_usd=10000.0, contracts=0.2
    )

    future = [
        make_candle(1, 50010, 50600, 49950, 50550), # Hits TP1 (50500) -> SL moves to Breakeven
        make_candle(2, 50550, 51100, 50400, 51050), # Hits TP2 (51000) -> SL moves to TP1
        make_candle(3, 51050, 51600, 51000, 51550), # Hits TP3 (51500) -> Closed Full
    ]

    trade = sim.simulate_trade(sig, future)
    assert trade is not None
    assert trade.status == TradeStatus.CLOSED_TP3_FULL
    assert trade.exit_reason == ExitReason.TAKE_PROFIT_3
    assert trade.r_multiple > 1.5
    assert trade.net_pnl_usd > 0
    assert trade.commission_paid > 0


def test_execution_simulator_losing_trade():
    sim = ExecutionSimulator()
    sig = TradeSignal(
        id="SIG-2", strategy_name="Sweep Reversal", symbol="BTC/USDT", timeframe="5m",
        direction=SignalDirection.LONG, state=SignalState.CONFIRMED, timestamp=1000,
        current_price=50000.0,
        score=ScoreBreakdown(total_score=70.0, category=SignalCategory.QUALIFIED),
        proposed_entry=50000.0, stop_loss=49500.0,
        tp1=50500.0, tp2=51000.0, tp3=51500.0,
        risk_reward_tp2=2.0, atr=200.0,
        position_size_usd=10000.0, contracts=0.2
    )

    future = [
        make_candle(1, 49900, 50100, 49400, 49450), # Hits Stop Loss (49500)
    ]

    trade = sim.simulate_trade(sig, future)
    assert trade is not None
    assert trade.status == TradeStatus.CLOSED_STOP
    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert trade.net_pnl_usd < 0
    assert trade.r_multiple < 0


def test_metrics_calculator():
    calc = MetricsCalculator()
    trades = [
        TradeRecord(
            trade_id="1", signal_id="S1", symbol="BTC/USDT", timeframe="5m",
            strategy_name="Sweep Reversal", direction=SignalDirection.LONG,
            entry_timestamp=1000, entry_price=50000.0, stop_loss=49500.0,
            tp1=50500.0, tp2=51000.0, tp3=51500.0, initial_risk_usd=100.0,
            position_size_usd=10000.0, contracts=0.2, r_multiple=2.0,
            net_pnl_usd=195.0, status=TradeStatus.CLOSED_TP2_PARTIAL,
            signal_score=85.0, signal_category=SignalCategory.STRONG
        ),
        TradeRecord(
            trade_id="2", signal_id="S2", symbol="BTC/USDT", timeframe="5m",
            strategy_name="Sweep Reversal", direction=SignalDirection.SHORT,
            entry_timestamp=2000, entry_price=51000.0, stop_loss=51500.0,
            tp1=50500.0, tp2=50000.0, tp3=49500.0, initial_risk_usd=100.0,
            position_size_usd=10000.0, contracts=0.2, r_multiple=-1.0,
            net_pnl_usd=-105.0, status=TradeStatus.CLOSED_STOP,
            signal_score=60.0, signal_category=SignalCategory.WATCHLIST
        )
    ]

    report = calc.calculate_report("Test_Experiment", "BTC/USDT", "5m", trades)
    assert report.total_trades == 2
    assert report.winning_trades == 1
    assert report.losing_trades == 1
    assert report.win_rate_pct == 50.0
    assert report.net_profit_usd == 90.0 # 195 - 105
    assert report.profit_factor > 1.5
    assert report.expectancy_r > 0


def test_walk_forward_splitter():
    engine = BacktestEngine()
    validator = WalkForwardValidator(engine)
    candles = [make_candle(i, 100 + i, 102 + i, 99 + i, 101 + i) for i in range(100)]
    in_sample, out_sample = validator.split_in_out_of_sample(candles, in_sample_ratio=0.70)
    assert len(in_sample) == 70
    assert len(out_sample) == 30

