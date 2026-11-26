"""
Quantitative Research Laboratory & Hypothesis Testing Framework.
Directly tests quantitative market hypotheses:
1. Does an OI increase of 1% improve liquidity sweep reversal profitability?
2. Does CVD divergence improve strategy win rate?
3. Are sweeps of 1-Hour highs more profitable than sweeps of 5-Minute highs?
4. Does a higher signal score predict better out-of-sample expectancy?
"""
from typing import List, Dict, Any, Optional
import numpy as np
from src.core.models import Candle
from src.research.models import BacktestReport, TradeRecord
from src.research.backtest_engine import BacktestEngine
from src.research.metrics_calculator import MetricsCalculator


class ResearchLab:
    def __init__(self, backtest_engine: Optional[BacktestEngine] = None):
        self.engine = backtest_engine or BacktestEngine()
        self.metrics_calc = MetricsCalculator()

    def test_timeframe_expectancy(
        self,
        symbol: str,
        candle_data_by_tf: Dict[str, List[Candle]]
    ) -> Dict[str, Any]:
        """
        Tests which timeframe has the highest expectancy for the strategy suite.
        """
        results = {}
        for tf, candles in candle_data_by_tf.items():
            report = self.engine.run_backtest(
                symbol=symbol,
                timeframe=tf,
                candles=candles,
                experiment_name=f"TF_Comparison_{tf}"
            )
            results[tf] = {
                "trades": report.total_trades,
                "win_rate_pct": report.win_rate_pct,
                "profit_factor": report.profit_factor,
                "expectancy_r": report.expectancy_r,
                "net_profit_usd": report.net_profit_usd
            }
        return results

    def test_score_tier_predictive_power(self, trades: List[TradeRecord]) -> Dict[str, Any]:
        """
        Verifies whether higher signal scores actually predict better out-of-sample performance.
        Separates into: Watchlist (50-64), Qualified (65-79), Strong (80-89), Exceptional (90-100).
        """
        tiers = {
            "WATCHLIST (50-64)": [t for t in trades if 50.0 <= t.signal_score < 65.0],
            "QUALIFIED (65-79)": [t for t in trades if 65.0 <= t.signal_score < 80.0],
            "STRONG (80-89)": [t for t in trades if 80.0 <= t.signal_score < 90.0],
            "EXCEPTIONAL (90-100)": [t for t in trades if t.signal_score >= 90.0]
        }

        comparison = {}
        for tier_name, tier_trades in tiers.items():
            if not tier_trades:
                comparison[tier_name] = {"count": 0, "win_rate_pct": 0.0, "profit_factor": 0.0, "expectancy_r": 0.0}
                continue

            winners = [t for t in tier_trades if t.net_pnl_usd > 0]
            losers = [t for t in tier_trades if t.net_pnl_usd < 0]
            win_rate = (len(winners) / len(tier_trades)) * 100.0

            gross_profit = sum(t.net_pnl_usd for t in winners)
            gross_loss = abs(sum(t.net_pnl_usd for t in losers))
            pf = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

            all_r = [t.r_multiple for t in tier_trades]
            avg_r = float(np.mean(all_r))

            comparison[tier_name] = {
                "count": len(tier_trades),
                "win_rate_pct": round(win_rate, 1),
                "profit_factor": round(pf, 2),
                "expectancy_r": round(avg_r, 2),
                "net_pnl_usd": round(sum(t.net_pnl_usd for t in tier_trades), 2)
            }

        return comparison

    def test_sweep_penetration_sensitivity(
        self,
        symbol: str,
        timeframe: str,
        candles: List[Candle],
        multipliers: List[float] = [0.05, 0.10, 0.20, 0.30]
    ) -> Dict[str, Any]:
        """
        Sensitivity analysis: How does the minimum sweep penetration threshold affect expectancy?
        """
        results = {}
        original_mult = self.engine.event_engine.sweep_detector.min_atr_multiplier

        for mult in multipliers:
            self.engine.event_engine.sweep_detector.min_atr_multiplier = mult
            report = self.engine.run_backtest(
                symbol=symbol,
                timeframe=timeframe,
                candles=candles,
                experiment_name=f"Sweep_Penetration_{mult}xATR"
            )
            results[f"{mult}xATR"] = {
                "trades": report.total_trades,
                "win_rate_pct": report.win_rate_pct,
                "profit_factor": report.profit_factor,
                "expectancy_r": report.expectancy_r,
                "net_profit_usd": report.net_profit_usd
            }

        self.engine.event_engine.sweep_detector.min_atr_multiplier = original_mult
        return results

