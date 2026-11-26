"""
Deep Historical Backtesting & Multi-Asset Quantitative Research Engine.
Pulls 1,000 candles per asset across BTC, ETH, SOL, XRP, DOGE, and SUI,
evaluates across 5m, 15m, and 1h timeframes,
models real-world taker fees (0.05%) and slippage (0.02%),
and aggregates strategy-by-strategy and score-tier performance metrics.
"""
import sys
import os
import time
import asyncio
from typing import Dict, List, Any
from tabulate import tabulate

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.core.database import DatabaseManager
from src.adapters.weex import WeexAdapter
from src.research.backtest_engine import BacktestEngine
from src.research.research_lab import ResearchLab
from src.research.walk_forward import WalkForwardValidator
from src.research.models import TradeRecord, BacktestReport


def main():
    print("=" * 80)
    print("DEEP MULTI-ASSET HISTORICAL BACKTESTING ENGINE (1,000 BARS PER MARKET)")
    print("=" * 80)

    db = DatabaseManager()
    adapter = WeexAdapter(rate_limit=True)

    target_symbols = [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "XRP/USDT:USDT",
        "DOGE/USDT:USDT",
        "SUI/USDT:USDT"
    ]
    timeframes = ["5m", "15m", "1h"]

    print("\n[Step 1] Ingesting Deep Historical Candles (up to 1,000 bars each)...")
    dataset: Dict[str, Dict[str, List]] = {}

    for sym in target_symbols:
        dataset[sym] = {}
        for tf in timeframes:
            # Check local DB
            cached = db.get_candle_models(sym, tf, limit=1000)
            if len(cached) < 800:
                print(f"  Fetching 1,000 {tf} candles for {sym} from WEEX...")
                try:
                    fresh = adapter.fetch_ohlcv(sym, tf, limit=1000)
                    if fresh:
                        db.save_candles(fresh)
                        cached = fresh
                except Exception as e:
                    print(f"  Warning fetching {sym} {tf}: {e}")
            print(f"  --> {sym:15s} [{tf:3s}]: {len(cached)} candles ready.")
            dataset[sym][tf] = cached

    # Initialize Backtest Engine (warmup period: 35 bars)
    engine = BacktestEngine(warmup_period=35)
    lab = ResearchLab(backtest_engine=engine)

    print("\n" + "=" * 80)
    print("[Step 2] Executing Event-Driven Backtests (Realistic Fees + Slippage)")
    print("=" * 80)

    all_trades: List[TradeRecord] = []
    asset_reports: List[Dict[str, Any]] = []

    for sym in target_symbols:
        for tf in ["5m", "15m"]:
            candles = dataset[sym].get(tf, [])
            if len(candles) < 60:
                continue

            report: BacktestReport = engine.run_backtest(
                symbol=sym,
                timeframe=tf,
                candles=candles,
                experiment_name=f"DeepBacktest_{sym}_{tf}"
            )
            all_trades.extend(report.trades)

            # Exit reasons count
            exit_summary = {}
            for t in report.trades:
                r = t.exit_reason.value if t.exit_reason else "OPEN"
                exit_summary[r] = exit_summary.get(r, 0) + 1

            asset_reports.append({
                "Symbol": sym.split(":")[0],
                "TF": tf,
                "Bars": len(candles),
                "Trades": report.total_trades,
                "Win Rate": f"{report.win_rate_pct:.1f}%",
                "Profit Factor": f"{report.profit_factor:.2f}",
                "Expectancy": f"{report.expectancy_r:+.2f}R",
                "Net PnL": f"${report.net_profit_usd:,.2f}",
                "Max DD": f"{report.max_drawdown_pct:.1f}%",
                "Exits": str(exit_summary)
            })

    # Print Asset Summary Table
    headers = ["Symbol", "TF", "Bars", "Trades", "Win Rate", "Profit Factor", "Expectancy", "Net PnL", "Max DD", "Exits"]
    rows = [[r[h] for h in headers] for r in asset_reports]
    print("\n" + tabulate(rows, headers=headers, tablefmt="grid"))

    # Step 3: Strategy-by-Strategy Aggregation
    print("\n" + "=" * 80)
    print("[Step 3] Performance Aggregated by Strategy")
    print("=" * 80)

    strat_groups: Dict[str, List[TradeRecord]] = {}
    for t in all_trades:
        strat_groups.setdefault(t.strategy_name, []).append(t)

    strat_rows = []
    for s_name, s_trades in strat_groups.items():
        winners = [t for t in s_trades if t.net_pnl_usd > 0]
        losers = [t for t in s_trades if t.net_pnl_usd < 0]
        wr = (len(winners) / len(s_trades) * 100.0) if s_trades else 0.0
        gross_win = sum(t.net_pnl_usd for t in winners)
        gross_loss = abs(sum(t.net_pnl_usd for t in losers))
        pf = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
        all_r = [t.r_multiple for t in s_trades]
        exp_r = sum(all_r) / len(all_r) if all_r else 0.0
        tot_net = sum(t.net_pnl_usd for t in s_trades)

        strat_rows.append([
            s_name,
            len(s_trades),
            len(winners),
            len(losers),
            f"{wr:.1f}%",
            f"{pf:.2f}",
            f"{exp_r:+.2f}R",
            f"${tot_net:,.2f}"
        ])

    s_headers = ["Strategy Name", "Total Trades", "Wins", "Losses", "Win Rate", "PF", "Expectancy R", "Net PnL"]
    print(tabulate(strat_rows, headers=s_headers, tablefmt="grid"))

    # Step 4: Multi-Factor Score Tier Analysis
    print("\n" + "=" * 80)
    print("[Step 4] Confluence Score Tier Predictive Power (0–100 Multi-Factor)")
    print("=" * 80)

    tier_results = lab.test_score_tier_predictive_power(all_trades)
    tier_rows = []
    for tier, stats in tier_results.items():
        tier_rows.append([
            tier,
            stats["count"],
            f"{stats['win_rate_pct']:.1f}%",
            f"{stats['profit_factor']:.2f}",
            f"{stats['expectancy_r']:+.2f}R",
            f"${stats.get('net_pnl_usd', 0.0):,.2f}"
        ])

    t_headers = ["Score Tier (0-100)", "Trades", "Win Rate", "PF", "Expectancy R", "Net PnL"]
    print(tabulate(tier_rows, headers=t_headers, tablefmt="grid"))

    # Step 5: Walk-Forward Validation (70% In-Sample / 30% Out-of-Sample)
    print("\n" + "=" * 80)
    print("[Step 5] Out-of-Sample Walk-Forward Stability Check (BTC 5m, 1,000 Bars)")
    print("=" * 80)

    btc_5m = dataset["BTC/USDT:USDT"]["5m"]
    validator = WalkForwardValidator(engine)
    train_bars, test_bars = validator.split_in_out_of_sample(btc_5m, in_sample_ratio=0.70)

    rep_train = engine.run_backtest("BTC/USDT:USDT", "5m", train_bars, experiment_name="BTC_Train_700bars")
    rep_test = engine.run_backtest("BTC/USDT:USDT", "5m", test_bars, experiment_name="BTC_Test_300bars")

    wf_data = [
        ["In-Sample (Train 700 bars)", rep_train.total_trades, f"{rep_train.win_rate_pct:.1f}%", f"{rep_train.profit_factor:.2f}", f"{rep_train.expectancy_r:+.2f}R", f"${rep_train.net_profit_usd:,.2f}"],
        ["Out-of-Sample (Test 300 bars)", rep_test.total_trades, f"{rep_test.win_rate_pct:.1f}%", f"{rep_test.profit_factor:.2f}", f"{rep_test.expectancy_r:+.2f}R", f"${rep_test.net_profit_usd:,.2f}"]
    ]
    wf_headers = ["Sample Window", "Trades", "Win Rate", "Profit Factor", "Expectancy R", "Net PnL"]
    print(tabulate(wf_data, headers=wf_headers, tablefmt="grid"))

    print("\n" + "=" * 80)
    print(f"DEEP BACKTEST COMPLETED: {len(all_trades)} TOTAL TRADES EVALUATED")
    print("=" * 80)


if __name__ == "__main__":
    main()

