"""
Performance Metrics & Statistical Expectancy Calculator.
Calculates:
- Win rate, Profit Factor, Expectancy ($ and R), Net Profit
- Average Winner, Average Loser, Average R multiple
- Maximum Drawdown (in $ and %)
- Long vs. Short breakdown
- Performance by Signal Score Tier (0-49, 50-64, 65-79, 80-89, 90-100)
- Performance by Strategy
"""
from typing import List, Dict, Any
import numpy as np
from src.research.models import TradeRecord, BacktestReport, TradeStatus
from src.strategies.models import SignalDirection, SignalCategory


class MetricsCalculator:
    def calculate_report(
        self,
        experiment_name: str,
        symbol: str,
        timeframe: str,
        trades: List[TradeRecord]
    ) -> BacktestReport:
        if not trades:
            return BacktestReport(
                experiment_name=experiment_name,
                symbol=symbol,
                timeframe=timeframe,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                breakeven_trades=0,
                win_rate_pct=0.0,
                avg_winner_r=0.0,
                avg_loser_r=0.0,
                profit_factor=0.0,
                net_profit_usd=0.0,
                avg_r_multiple=0.0,
                max_drawdown_usd=0.0,
                max_drawdown_pct=0.0,
                expectancy_r=0.0,
                expectancy_usd=0.0,
                long_trades=0,
                long_win_rate_pct=0.0,
                short_trades=0,
                short_win_rate_pct=0.0,
                trades=[]
            )

        total_trades = len(trades)
        winners = [t for t in trades if t.net_pnl_usd > 0]
        losers = [t for t in trades if t.net_pnl_usd < 0]
        breakevens = [t for t in trades if t.net_pnl_usd == 0]

        win_rate = (len(winners) / total_trades) * 100.0 if total_trades > 0 else 0.0

        gross_profit = sum(t.net_pnl_usd for t in winners)
        gross_loss = abs(sum(t.net_pnl_usd for t in losers))
        net_profit = sum(t.net_pnl_usd for t in trades)

        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        winner_rs = [t.r_multiple for t in winners]
        loser_rs = [t.r_multiple for t in losers]
        avg_winner_r = float(np.mean(winner_rs)) if winner_rs else 0.0
        avg_loser_r = float(np.mean(loser_rs)) if loser_rs else 0.0

        all_rs = [t.r_multiple for t in trades]
        avg_r = float(np.mean(all_rs)) if all_rs else 0.0

        # Mathematical Expectancy = (Win% * AvgWin) - (Loss% * |AvgLoss|)
        p_win = len(winners) / total_trades if total_trades > 0 else 0.0
        p_loss = len(losers) / total_trades if total_trades > 0 else 0.0
        expectancy_r = (p_win * avg_winner_r) + (p_loss * avg_loser_r)
        avg_pnl = float(np.mean([t.net_pnl_usd for t in trades])) if trades else 0.0

        # Drawdown calculation
        cumulative_pnl = np.cumsum([t.net_pnl_usd for t in trades])
        peak = np.maximum.accumulate(cumulative_pnl)
        drawdowns = peak - cumulative_pnl
        max_dd_usd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0
        peak_val = max(1.0, float(np.max(peak)) if len(peak) > 0 else 1.0)
        max_dd_pct = (max_dd_usd / peak_val) * 100.0 if peak_val > 0 else 0.0

        # Long vs Short breakdown
        longs = [t for t in trades if t.direction == SignalDirection.LONG]
        shorts = [t for t in trades if t.direction == SignalDirection.SHORT]
        long_win_rate = (len([t for t in longs if t.net_pnl_usd > 0]) / len(longs) * 100.0) if longs else 0.0
        short_win_rate = (len([t for t in shorts if t.net_pnl_usd > 0]) / len(shorts) * 100.0) if shorts else 0.0

        # Breakdown by score tier
        tiers = {}
        for category in SignalCategory:
            cat_trades = [t for t in trades if t.signal_category == category.value]
            if cat_trades:
                cat_win_rate = (len([t for t in cat_trades if t.net_pnl_usd > 0]) / len(cat_trades)) * 100.0
                cat_net = sum(t.net_pnl_usd for t in cat_trades)
                tiers[category.value] = {
                    "count": len(cat_trades),
                    "win_rate_pct": round(cat_win_rate, 1),
                    "net_pnl_usd": round(cat_net, 2),
                    "avg_r": round(float(np.mean([t.r_multiple for t in cat_trades])), 2)
                }

        # Breakdown by strategy
        strategies = {}
        strat_names = set(t.strategy_name for t in trades)
        for s_name in strat_names:
            s_trades = [t for t in trades if t.strategy_name == s_name]
            s_win_rate = (len([t for t in s_trades if t.net_pnl_usd > 0]) / len(s_trades)) * 100.0
            strategies[s_name] = {
                "count": len(s_trades),
                "win_rate_pct": round(s_win_rate, 1),
                "net_pnl_usd": round(sum(t.net_pnl_usd for t in s_trades), 2),
                "profit_factor": round(
                    sum(t.net_pnl_usd for t in s_trades if t.net_pnl_usd > 0) /
                    max(1e-4, abs(sum(t.net_pnl_usd for t in s_trades if t.net_pnl_usd < 0))), 2
                )
            }

        return BacktestReport(
            experiment_name=experiment_name,
            symbol=symbol,
            timeframe=timeframe,
            total_trades=total_trades,
            winning_trades=len(winners),
            losing_trades=len(losers),
            breakeven_trades=len(breakevens),
            win_rate_pct=round(win_rate, 1),
            avg_winner_r=round(avg_winner_r, 2),
            avg_loser_r=round(avg_loser_r, 2),
            profit_factor=round(profit_factor, 2),
            net_profit_usd=round(net_profit, 2),
            avg_r_multiple=round(avg_r, 2),
            max_drawdown_usd=round(max_dd_usd, 2),
            max_drawdown_pct=round(max_dd_pct, 1),
            expectancy_r=round(expectancy_r, 2),
            expectancy_usd=round(avg_pnl, 2),
            long_trades=len(longs),
            long_win_rate_pct=round(long_win_rate, 1),
            short_trades=len(shorts),
            short_win_rate_pct=round(short_win_rate, 1),
            performance_by_score_tier=tiers,
            performance_by_strategy=strategies,
            trades=trades
        )

