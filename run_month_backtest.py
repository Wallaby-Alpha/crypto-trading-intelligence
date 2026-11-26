"""
1-Month Multi-Asset Intraday Backtesting Engine (15-Minute Timeframe).
Evaluates ~2,500 candles per asset (~26 days to 1 month of continuous 15m data)
across the Top 10 Liquid USDT Perpetual Markets:
BTC, ETH, SOL, XRP, DOGE, SUI, AVAX, LINK, NEAR, and ADA.

Applies institutional execution modeling:
- 0.05% Taker Fee on all fills
- 0.02% Slippage modeling
- 1% Account Risk Sizing
- Trailing Stop-Loss to Breakeven at 1.0R (TP1)
- Staged Targets: TP1 (1.0R - 33%), TP2 (2.0R - 33%), TP3 (3.0R - 34% runner)
"""
import sys
import os
import time
from typing import Dict, List, Any
from tabulate import tabulate

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.core.database import DatabaseManager
from src.core.models import Candle, DataQualityStatus
from src.adapters.weex import WeexAdapter
from src.research.backtest_engine import BacktestEngine
from src.research.research_lab import ResearchLab
from src.research.models import TradeRecord, BacktestReport


def fetch_paginated_15m_candles(
    adapter: WeexAdapter,
    symbol: str,
    target_candles: int = 2500
) -> List[Candle]:
    """
    Paginates backward on WEEX to retrieve ~2,500 continuous 15m candles (~26 days).
    """
    duration_ms = 15 * 60 * 1000
    all_raw: Dict[int, list] = {}
    end_time = int(time.time() * 1000)
    batches = (target_candles // 100) + 2

    for _ in range(batches):
        start_time = end_time - 100 * duration_ms
        try:
            batch = adapter.client.fetch_ohlcv(
                symbol,
                timeframe='15m',
                since=start_time,
                params={'historical': True, 'until': end_time}
            )
            if not batch:
                break
            for c in batch:
                all_raw[c[0]] = c
            end_time = batch[0][0] - 1
            if len(all_raw) >= target_candles:
                break
            time.sleep(0.08)
        except Exception as e:
            print(f"    Notice during pagination for {symbol}: {e}")
            break

    # Convert sorted raw candles to Candle objects
    sorted_raw = sorted(all_raw.values(), key=lambda x: x[0])
    candles: List[Candle] = []
    now_ms = int(time.time() * 1000)

    for c in sorted_raw:
        ts = int(c[0])
        dt = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(ts / 1000))
        candles.append(Candle(
            symbol=symbol,
            exchange="weex",
            timeframe="15m",
            timestamp=ts,
            datetime=dt,
            open=float(c[1]),
            high=float(c[2]),
            low=float(c[3]),
            close=float(c[4]),
            volume=float(c[5]),
            quote_volume=None,
            is_closed=(now_ms >= ts + duration_ms),
            quality_status=DataQualityStatus.VALID
        ))

    return candles


def main():
    print("=" * 85)
    print(" 1-MONTH MULTI-ASSET QUANTITATIVE BACKTEST (TOP 10 PERPETUAL MARKETS - 15M)")
    print("=" * 85)

    db = DatabaseManager()
    adapter = WeexAdapter(rate_limit=True)

    top10_symbols = [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "XRP/USDT:USDT",
        "DOGE/USDT:USDT",
        "SUI/USDT:USDT",
        "AVAX/USDT:USDT",
        "LINK/USDT:USDT",
        "NEAR/USDT:USDT",
        "ADA/USDT:USDT"
    ]

    print("\n[Step 1] Loading / Ingesting 1-Month 15m Historical Candles (~2,500 bars per asset)...")
    dataset: Dict[str, List[Candle]] = {}

    for sym in top10_symbols:
        # Check DB cache first
        cached = db.get_candle_models(sym, "15m", limit=3000)
        if len(cached) < 2000:
            print(f"  Fetching ~2,500 15m candles for {sym}...")
            fresh = fetch_paginated_15m_candles(adapter, sym, target_candles=2500)
            if fresh:
                db.save_candles(fresh)
                cached = fresh

        if cached:
            earliest_dt = cached[0].datetime[:10] if cached[0].datetime else "N/A"
            latest_dt = cached[-1].datetime[:10] if cached[-1].datetime else "N/A"
            print(f"  --> {sym:15s}: {len(cached)} bars ({earliest_dt} to {latest_dt}) ready.")
        else:
            print(f"  --> {sym:15s}: 0 bars found.")
        dataset[sym] = cached

    # Initialize Backtest Engine
    engine = BacktestEngine(warmup_period=35)
    lab = ResearchLab(backtest_engine=engine)

    print("\n" + "=" * 85)
    print("[Step 2] Executing Event-Driven Backtests (Realistic Fees + Slippage)")
    print("=" * 85)

    all_trades: List[TradeRecord] = []
    asset_summaries: List[Dict[str, Any]] = []

    for sym in top10_symbols:
        candles = dataset.get(sym, [])
        if len(candles) < 100:
            continue

        t0 = time.time()
        report: BacktestReport = engine.run_backtest(
            symbol=sym,
            timeframe="15m",
            candles=candles,
            experiment_name=f"Month_15m_{sym}"
        )
        elapsed = time.time() - t0
        all_trades.extend(report.trades)

        # Count exit reasons
        exit_counts = {}
        for t in report.trades:
            r = t.exit_reason.value if t.exit_reason else "OPEN"
            exit_counts[r] = exit_counts.get(r, 0) + 1

        asset_summaries.append({
            "Asset": sym.split(":")[0],
            "Bars": len(candles),
            "Trades": report.total_trades,
            "Wins": report.winning_trades,
            "Losses": report.losing_trades,
            "Win Rate": f"{report.win_rate_pct:.1f}%",
            "Profit Factor": f"{report.profit_factor:.2f}",
            "Expectancy": f"{report.expectancy_r:+.2f}R",
            "Net PnL ($)": f"${report.net_profit_usd:,.2f}",
            "Max DD": f"{report.max_drawdown_pct:.1f}%",
            "Exits Breakdown": str(exit_counts),
            "_net_pnl": report.net_profit_usd
        })

    # Print Table 1: Asset-by-Asset Performance
    print("\n[Asset Performance Matrix]")
    headers1 = ["Asset", "Bars", "Trades", "Wins", "Losses", "Win Rate", "Profit Factor", "Expectancy", "Net PnL ($)", "Max DD", "Exits Breakdown"]
    rows1 = [[a[h] for h in headers1] for a in asset_summaries]
    print(tabulate(rows1, headers=headers1, tablefmt="grid"))

    # Print Table 2: Strategy Performance
    print("\n" + "=" * 85)
    print("[Step 3] Strategy Suite Aggregate Performance")
    print("=" * 85)

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

    s_headers = ["Strategy Name", "Total Trades", "Wins", "Losses", "Win Rate", "PF", "Expectancy R", "Net PnL ($)"]
    print(tabulate(strat_rows, headers=s_headers, tablefmt="grid"))

    # Print Table 3: Score Tier Predictive Power
    print("\n" + "=" * 85)
    print("[Step 4] Multi-Factor Score Tier Predictive Power (0–100 Multi-Factor)")
    print("=" * 85)

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

    t_headers = ["Score Tier (0-100)", "Trades", "Win Rate", "PF", "Expectancy R", "Net PnL ($)"]
    print(tabulate(tier_rows, headers=t_headers, tablefmt="grid"))

    # Print Table 4: Portfolio Summary
    total_trades_all = len(all_trades)
    winning_trades_all = len([t for t in all_trades if t.net_pnl_usd > 0])
    losing_trades_all = len([t for t in all_trades if t.net_pnl_usd < 0])
    total_net_pnl = sum(t.net_pnl_usd for t in all_trades)
    portfolio_wr = (winning_trades_all / total_trades_all * 100.0) if total_trades_all > 0 else 0.0
    all_r_multiples = [t.r_multiple for t in all_trades]
    portfolio_exp_r = sum(all_r_multiples) / len(all_r_multiples) if all_r_multiples else 0.0
    gross_pnl_win = sum(t.net_pnl_usd for t in all_trades if t.net_pnl_usd > 0)
    gross_pnl_loss = abs(sum(t.net_pnl_usd for t in all_trades if t.net_pnl_usd < 0))
    portfolio_pf = (gross_pnl_win / gross_pnl_loss) if gross_pnl_loss > 0 else (99.0 if gross_pnl_win > 0 else 0.0)

    print("\n" + "=" * 85)
    print(" PORTFOLIO 1-MONTH CUMULATIVE BACKTEST RESULTS")
    print("=" * 85)
    print(f"  Total Trades Evaluated:    {total_trades_all}")
    print(f"  Winning Trades:            {winning_trades_all}")
    print(f"  Losing Trades:             {losing_trades_all}")
    print(f"  Portfolio Win Rate:        {portfolio_wr:.1f}%")
    print(f"  Portfolio Profit Factor:   {portfolio_pf:.2f}")
    print(f"  Portfolio Expectancy R:    {portfolio_exp_r:+.2f}R")
    print(f"  Cumulative Net PnL:        ${total_net_pnl:,.2f}")
    print("=" * 85)


if __name__ == "__main__":
    main()

