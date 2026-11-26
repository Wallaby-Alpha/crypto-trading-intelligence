"""
Phase 4 Backtest & Research Lab Runner.
Executes event-driven backtests on real market data (BTC, ETH, SOL),
runs quantitative hypothesis tests, and performs out-of-sample walk-forward validation.
"""
import sys
import os
import asyncio

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.core.database import DatabaseManager
from src.adapters.weex import WeexAdapter
from src.research.backtest_engine import BacktestEngine
from src.research.research_lab import ResearchLab
from src.research.walk_forward import WalkForwardValidator


async def main():
    print("=" * 80)
    print("PHASE 4: QUANTITATIVE BACKTESTING & RESEARCH LABORATORY")
    print("=" * 80)

    db = DatabaseManager()
    weex = WeexAdapter()

    symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    timeframes = ["5m", "15m", "1h"]

    print("\n[Step 1] Loading / Fetching historical candle data...")
    market_candles = {}

    for sym in symbols:
        market_candles[sym] = {}
        for tf in timeframes:
            # Check local db first
            cached = db.get_candle_models(sym, tf, limit=500)
            if len(cached) < 150:
                print(f"  Fetching {sym} {tf} from WEEX REST API...")
                fresh = weex.fetch_ohlcv(sym, tf, limit=300)
                if fresh:
                    db.save_candles(fresh)
                    cached = fresh
            print(f"  {sym} [{tf}]: {len(cached)} candles ready.")
            market_candles[sym][tf] = cached



    # Step 2: Run Backtest on primary timeframes
    print("\n" + "=" * 80)
    print("[Step 2] Historical Event-Driven Backtesting (Realistic Fees + Slippage)")
    print("=" * 80)

    engine = BacktestEngine(warmup_period=30)
    all_trades = []

    for sym in symbols:
        for tf in ["5m", "15m"]:
            candles = market_candles[sym].get(tf, [])
            if len(candles) < 40:
                continue

            report = engine.run_backtest(
                symbol=sym,
                timeframe=tf,
                candles=candles,
                experiment_name=f"Backtest_{sym}_{tf}"
            )
            all_trades.extend(report.trades)

            print(f"\n--- Results for {sym.upper()} [{tf}] ---")
            print(f"  Total Trades:     {report.total_trades}")
            print(f"  Win Rate:         {report.win_rate_pct:.1f}%")
            print(f"  Profit Factor:    {report.profit_factor:.2f}")
            print(f"  Net Profit:       ${report.net_profit_usd:.2f}")
            print(f"  Expectancy R:     {report.expectancy_r:.2f}R")
            print(f"  Max Drawdown:     {report.max_drawdown_pct:.2f}%")
            exit_counts = {}
            for t in report.trades:
                reason = t.exit_reason.value if t.exit_reason else "UNKNOWN"
                exit_counts[reason] = exit_counts.get(reason, 0) + 1
            print(f"  Exit Breakdown:   {exit_counts}")

    # Step 3: Research Lab Hypothesis Testing
    print("\n" + "=" * 80)
    print("[Step 3] Quantitative Hypothesis Experiments")
    print("=" * 80)

    lab = ResearchLab(backtest_engine=engine)

    # Hypothesis A: Signal Score Tier Predictive Power
    print("\n[Hypothesis 1] Does higher multi-factor signal score correlate with higher expectancy?")
    tier_results = lab.test_score_tier_predictive_power(all_trades)
    for tier, stats in tier_results.items():
        print(f"  {tier:22s} | Trades: {stats['count']:2d} | WinRate: {stats['win_rate_pct']:5.1f}% | PF: {stats['profit_factor']:4.2f} | Exp R: {stats['expectancy_r']:5.2f}R | Net: ${stats.get('net_pnl_usd', 0.0):6.2f}")

    # Hypothesis B: Timeframe Expectancy Comparison
    print("\n[Hypothesis 2] Multi-Timeframe Expectancy Comparison for BTCUSDT:")
    tf_results = lab.test_timeframe_expectancy("BTC/USDT:USDT", market_candles["BTC/USDT:USDT"])
    for tf, res in tf_results.items():
        print(f"  Timeframe {tf:5s} -> Trades: {res['trades']:2d} | WinRate: {res['win_rate_pct']:5.1f}% | PF: {res['profit_factor']:4.2f} | Exp R: {res['expectancy_r']:5.2f}R | Net: ${res['net_profit_usd']:.2f}")

    # Hypothesis C: Sweep Penetration Sensitivity
    print("\n[Hypothesis 3] Sweep Penetration ATR Multiplier Sensitivity Analysis (ETHUSDT 5m):")
    sensitivity = lab.test_sweep_penetration_sensitivity(
        symbol="ETH/USDT:USDT",
        timeframe="5m",
        candles=market_candles["ETH/USDT:USDT"]["5m"],
        multipliers=[0.05, 0.10, 0.20, 0.30]
    )
    for mult, res in sensitivity.items():
        print(f"  Threshold {mult:10s} -> Trades: {res['trades']:2d} | WinRate: {res['win_rate_pct']:5.1f}% | PF: {res['profit_factor']:4.2f} | Exp R: {res['expectancy_r']:5.2f}R")

    # Step 4: Walk-Forward Validation (70% Train / 30% Test)
    print("\n" + "=" * 80)
    print("[Step 4] Out-of-Sample Walk-Forward Validation (70% In-Sample / 30% Out-of-Sample)")
    print("=" * 80)

    validator = WalkForwardValidator(engine)
    btc_15m = market_candles["BTC/USDT:USDT"]["15m"]
    train_candles, test_candles = validator.split_in_out_of_sample(btc_15m, 0.70)

    train_report = engine.run_backtest("BTC/USDT:USDT", "15m", train_candles, experiment_name="BTC_Train_InSample")
    test_report = engine.run_backtest("BTC/USDT:USDT", "15m", test_candles, experiment_name="BTC_Test_OutOfSample")

    print(f"  In-Sample  (Train {len(train_candles)} bars): Trades={train_report.total_trades}, WinRate={train_report.win_rate_pct:.1f}%, PF={train_report.profit_factor:.2f}, Exp R={train_report.expectancy_r:.2f}R, Net=${train_report.net_profit_usd:.2f}")
    print(f"  Out-of-Sample (Test {len(test_candles)} bars): Trades={test_report.total_trades}, WinRate={test_report.win_rate_pct:.1f}%, PF={test_report.profit_factor:.2f}, Exp R={test_report.expectancy_r:.2f}R, Net=${test_report.net_profit_usd:.2f}")

    print("\n" + "=" * 80)
    print("PHASE 4 BACKTEST & RESEARCH LAB VALIDATION COMPLETED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
