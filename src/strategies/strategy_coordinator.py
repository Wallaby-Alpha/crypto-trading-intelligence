"""
Strategy Coordinator & Signal Dispatcher.
Coordinates all 6 trading strategies:
1. Liquidity Sweep Reversal
2. OI Expansion & Failed Breakout
3. Failed Reclaim Continuation
4. CVD Divergence Reversal
5. Momentum Breakout
6. VWAP & Volume Profile Reversion
Enforces deduplication, ranking, and persistent database storage.
"""
import logging
from typing import List, Dict, Any, Optional
from src.core.database import DatabaseManager
from src.events.models import MarketEventBundle
from src.strategies.models import TradeSignal, SignalCategory
from src.strategies.base import BaseStrategy
from src.strategies.duplicate_filter import DuplicateSignalFilter
from src.strategies.sweep_reversal import LiquiditySweepReversalStrategy
from src.strategies.trend_pullback_sweep import TrendPullbackSweepStrategy
from src.strategies.liquidation_absorption import LiquidationAbsorptionStrategy
from src.strategies.swing_failure_range import SwingFailureRangeTrapStrategy
from src.strategies.oi_failed_breakout import OIFailedBreakoutStrategy
from src.strategies.failed_reclaim import FailedReclaimContinuationStrategy
from src.strategies.cvd_divergence import CVDDivergenceReversalStrategy
from src.strategies.momentum_breakout import MomentumBreakoutStrategy
from src.strategies.vwap_mean_reversion import VWAPMeanReversionStrategy

logger = logging.getLogger(__name__)


class StrategyCoordinator:
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager
        self.duplicate_filter = DuplicateSignalFilter(cooldown_minutes=20)

        # Register specialized strategies
        self.strategies: Dict[str, BaseStrategy] = {
            "trend_pullback_sweep": TrendPullbackSweepStrategy(),
            "liquidation_absorption": LiquidationAbsorptionStrategy(),
            "swing_failure_range": SwingFailureRangeTrapStrategy(),
            "sweep_reversal": LiquiditySweepReversalStrategy(),
            "oi_failed_breakout": OIFailedBreakoutStrategy(),
            "failed_reclaim": FailedReclaimContinuationStrategy(),
            "cvd_divergence": CVDDivergenceReversalStrategy(),
            "momentum_breakout": MomentumBreakoutStrategy(),
            "vwap_reversion": VWAPMeanReversionStrategy(),
        }

    def evaluate_bundle(
        self,
        bundle: MarketEventBundle,
        current_price: float,
        atr_value: float,
        funding_rate: Optional[float] = None,
        htf_aligned: bool = False,
        htf_trend: str = "NEUTRAL"
    ) -> List[TradeSignal]:
        """
        Runs all active strategies against the market event bundle.
        Returns deduplicated, qualified trade signals.
        """
        candidate_signals: List[TradeSignal] = []

        for strat_key, strat in self.strategies.items():
            if not strat.is_enabled:
                continue
            try:
                sig = strat.evaluate(
                    bundle=bundle,
                    current_price=current_price,
                    atr_value=atr_value,
                    funding_rate=funding_rate,
                    htf_aligned=htf_aligned,
                    htf_trend=htf_trend
                )
                if sig:
                    candidate_signals.append(sig)
            except Exception as e:
                logger.error(f"Error evaluating strategy {strat_key}: {e}")

        # Filter duplicates and persist
        emitted_signals: List[TradeSignal] = []
        for sig in candidate_signals:
            if self.duplicate_filter.should_emit_signal(sig):
                emitted_signals.append(sig)
                if self.db:
                    self._persist_signal(sig)

        return emitted_signals

    def _persist_signal(self, sig: TradeSignal):
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS trade_signals (
                id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                direction TEXT NOT NULL,
                state TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                current_price REAL NOT NULL,
                total_score REAL NOT NULL,
                category TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                tp1 REAL NOT NULL,
                tp2 REAL NOT NULL,
                tp3 REAL NOT NULL,
                risk_reward REAL NOT NULL,
                position_size_usd REAL NOT NULL,
                confirmations_json TEXT NOT NULL
            );
            """)

            import json
            cur.execute("""
            INSERT OR REPLACE INTO trade_signals (
                id, strategy_name, symbol, timeframe, direction, state,
                timestamp, current_price, total_score, category,
                entry_price, stop_loss, tp1, tp2, tp3, risk_reward,
                position_size_usd, confirmations_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                sig.id, sig.strategy_name, sig.symbol, sig.timeframe, sig.direction.value,
                sig.state.value, sig.timestamp, sig.current_price, sig.score.total_score,
                sig.score.category.value, sig.proposed_entry, sig.stop_loss,
                sig.tp1, sig.tp2, sig.tp3, sig.risk_reward_tp2,
                sig.position_size_usd, json.dumps(sig.confirmations)
            ))
            conn.commit()

