"""
Event-Driven Historical Backtesting Engine.
Iterates historical candles bar-by-bar with zero look-ahead bias.
At each candle t:
- Generates indicators strictly using candles[0 : t+1]
- Detects trading events and evaluates strategies
- Simulates trade execution over subsequent candles [t+1 : end]
- Compiles performance statistics via MetricsCalculator
"""
import logging
from typing import List, Dict, Any, Optional
from src.core.models import Candle, OpenInterestMetrics
from src.indicators.cvd import CVDEngine, CVDBar
from src.indicators.vwap import VWAPEngine
from src.indicators.volume_profile import VolumeProfileEngine
from src.indicators.volatility import VolatilityEngine
from src.events.event_engine import EventEngine
from src.strategies.strategy_coordinator import StrategyCoordinator
from src.strategies.models import TradeSignal
from src.research.models import TradeRecord, BacktestReport
from src.research.execution_sim import ExecutionSimulator
from src.research.metrics_calculator import MetricsCalculator

logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(
        self,
        warmup_period: int = 35,
        execution_simulator: Optional[ExecutionSimulator] = None,
        strategy_coordinator: Optional[StrategyCoordinator] = None
    ):
        self.warmup_period = warmup_period
        self.sim = execution_simulator or ExecutionSimulator()
        self.coordinator = strategy_coordinator or StrategyCoordinator()
        self.metrics_calc = MetricsCalculator()

        # Indicator & Event engines
        self.cvd_engine = CVDEngine()
        self.vwap_engine = VWAPEngine()
        self.vp_engine = VolumeProfileEngine()
        self.vol_engine = VolatilityEngine()
        self.event_engine = EventEngine()

    def run_backtest(
        self,
        symbol: str,
        timeframe: str,
        candles: List[Candle],
        experiment_name: str = "Backtest",
        funding_rate: Optional[float] = None
    ) -> BacktestReport:
        """
        Executes event-driven backtest over historical candles bar-by-bar.
        """
        if len(candles) < self.warmup_period + 10:
            logger.warning(f"Insufficient candles ({len(candles)}) for backtesting {symbol}.")
            return self.metrics_calc.calculate_report(experiment_name, symbol, timeframe, [])

        trades: List[TradeRecord] = []
        n_candles = len(candles)

        # Pre-calculate estimated CVD bars and ATR across full history to avoid redundant loops,
        # but strictly slice up to index t at each step
        all_cvd = self.cvd_engine.estimate_from_candles(candles)
        all_atr = self.vol_engine.calculate_atr(candles)
        all_vwap = self.vwap_engine.calculate_anchored_vwap(candles)

        # Precompute vectorized EMAs for dynamic HTF trend detection (zero lookahead)
        close_prices = [c.close for c in candles]
        def calc_ema(prices: List[float], period: int) -> List[float]:
            alpha = 2.0 / (period + 1.0)
            res = [prices[0]]
            for p in prices[1:]:
                res.append(alpha * p + (1.0 - alpha) * res[-1])
            return res

        all_ema20 = calc_ema(close_prices, 20)
        all_ema50 = calc_ema(close_prices, 50)

        active_trade_until_idx = -1

        for t in range(self.warmup_period, n_candles - 5):
            # If currently in a simulated trade, can enforce single-position mode
            if t < active_trade_until_idx:
                continue

            current_c = candles[t]
            curr_atr = all_atr[t] if t < len(all_atr) else 1.0

            # Dynamic HTF trend determination at candle t
            e20 = all_ema20[t]
            e50 = all_ema50[t]
            if current_c.close > e50 and e20 > e50:
                htf_trend = "BULLISH"
                htf_aligned = True
            elif current_c.close < e50 and e20 < e50:
                htf_trend = "BEARISH"
                htf_aligned = True
            else:
                htf_trend = "NEUTRAL"
                htf_aligned = False

            # Slices strictly visible at candle t
            visible_candles = candles[: t + 1]
            visible_cvd = all_cvd[: t + 1]
            visible_vwap = all_vwap[: t + 1]
            vp = self.vp_engine.compute_profile(visible_candles[-50:])

            # Detect events at candle t
            bundle = self.event_engine.analyze_candle(
                candles=visible_candles,
                cvd_bars=visible_cvd,
                oi_metrics=None,
                vwap_bands=visible_vwap,
                vp_result=vp,
                atr_value=curr_atr,
                target_index=t
            )

            # Evaluate strategies with dynamic HTF trend alignment
            signals = self.coordinator.evaluate_bundle(
                bundle=bundle,
                current_price=current_c.close,
                atr_value=curr_atr,
                funding_rate=funding_rate,
                htf_aligned=htf_aligned,
                htf_trend=htf_trend
            )

            if signals:
                top_signal = max(signals, key=lambda s: s.score.total_score)
                future_slice = candles[t + 1 :]
                trade_result = self.sim.simulate_trade(top_signal, future_slice)

                if trade_result:
                    trades.append(trade_result)
                    active_trade_until_idx = t + trade_result.holding_period_candles

        return self.metrics_calc.calculate_report(
            experiment_name=experiment_name,
            symbol=symbol,
            timeframe=timeframe,
            trades=trades
        )

