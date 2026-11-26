"""
Model 1: Trend-Aligned Liquidity Pullback (Core ICT Concept).
Institutional Logic:
- In an established Higher Timeframe (HTF) trend, institutions do NOT fade highs or lows.
- Instead, during pullbacks, price sweeps retail stop-loss pools (internal swing lows in bull trend, swing highs in bear trend).
- Once discount liquidity is consumed, price immediately reclaims the level and resumes the primary trend.

Rules:
1. HTF Trend Alignment:
   - If HTF is BULLISH: ONLY take LONGS on sweeps of lows. Strictly forbid shorts.
   - If HTF is BEARISH: ONLY take SHORTS on sweeps of highs. Strictly forbid longs.
2. Immediate Reclaim:
   - Price penetrates level by >= 0.05 ATR, but closes back inside within 1-3 bars.
3. Entry & Risk:
   - Entry at or near the swept level (reclaim level), NOT at the top of a giant displacement bar.
   - Protective Stop Loss tight behind the sweep wick (0.20 ATR buffer).
   - Targets: TP1 = 1.0R (33%), TP2 = 2.0R (33%), TP3 = 3.0R (34% runner).
"""
from typing import Optional, List, Dict, Any
from src.strategies.base import BaseStrategy
from src.strategies.models import TradeSignal, SignalDirection, SignalState, EntryMethod
from src.events.models import MarketEventBundle, SweepDirection, CVDDivergenceType


class TrendPullbackSweepStrategy(BaseStrategy):
    def __init__(self, is_enabled: bool = True, min_score_threshold: float = 65.0):
        super().__init__(name="Trend Pullback Sweep", is_enabled=is_enabled)
        self.min_score_threshold = min_score_threshold

    def evaluate(
        self,
        bundle: MarketEventBundle,
        current_price: float,
        atr_value: float,
        funding_rate: Optional[float] = None,
        htf_aligned: bool = False,
        htf_trend: str = "NEUTRAL"
    ) -> Optional[TradeSignal]:
        if not self.is_enabled or not bundle.sweeps:
            return None

        # -------------------------------------------------------------
        # 1. BULLISH HTF TREND -> Look for Low Sweeps in Discount
        # -------------------------------------------------------------
        if htf_trend == "BULLISH" or (htf_aligned and htf_trend != "BEARISH"):
            bullish_sweeps = [s for s in bundle.sweeps if s.direction == SweepDirection.BULLISH_SWEEP_LOW]
            if not bullish_sweeps:
                return None

            sweep = bullish_sweeps[0]
            # Verify reclaim: current close is above swept level
            if current_price < sweep.level_price:
                return None

            # Calculate tight levels near swept level
            levels = self.risk_sizer.calculate_trade_levels(
                direction=SignalDirection.LONG,
                current_price=current_price,
                structural_extreme=sweep.extreme_price,
                atr_value=atr_value,
                entry_method=EntryMethod.LIMIT_SWEPT_LEVEL,
                swept_level=sweep.level_price
            )

            score = self.scorer.calculate_score(
                direction=SignalDirection.LONG,
                bundle=bundle,
                risk_reward_ratio=levels["risk_reward_tp2"],
                htf_aligned=True,
                funding_rate=funding_rate
            )

            # High base score because HTF is aligned
            total_score = max(score.total_score, 75.0)
            score.total_score = total_score

            confirmations = [
                f"Bullish 1H Trend: Swept discount {sweep.level_swept_type.value} at ${sweep.level_price:,.4f}",
                f"Immediate reclaim above level (wick: ${sweep.extreme_price:,.4f})",
                "Trend-aligned pullback liquidity run (ICT Model)"
            ]
            if bundle.cvd_divergences:
                confirmations.append("CVD absorption confirmed")

            return TradeSignal(
                id=f"TPS-LONG-{bundle.symbol}-{bundle.timestamp}",
                strategy_name=self.name,
                symbol=bundle.symbol,
                timeframe=bundle.timeframe,
                direction=SignalDirection.LONG,
                state=SignalState.CONFIRMED,
                timestamp=bundle.timestamp,
                datetime=bundle.datetime,
                current_price=current_price,
                score=score,
                entry_method=EntryMethod.LIMIT_SWEPT_LEVEL,
                proposed_entry=levels["entry_price"],
                stop_loss=levels["stop_loss"],
                tp1=levels["tp1"],
                tp2=levels["tp2"],
                tp3=levels["tp3"],
                risk_reward_tp2=levels["risk_reward_tp2"],
                atr=atr_value,
                position_size_usd=levels["position_size_usd"],
                contracts=levels["contracts"],
                confirmations=confirmations,
                invalidation_condition=f"15m close below sweep low ${levels['stop_loss']:,.4f}"
            )

        # -------------------------------------------------------------
        # 2. BEARISH HTF TREND -> Look for High Sweeps in Premium
        # -------------------------------------------------------------
        elif htf_trend == "BEARISH" or (htf_aligned and htf_trend != "BULLISH"):
            bearish_sweeps = [s for s in bundle.sweeps if s.direction == SweepDirection.BEARISH_SWEEP_HIGH]
            if not bearish_sweeps:
                return None

            sweep = bearish_sweeps[0]
            # Verify reclaim: current close is below swept level
            if current_price > sweep.level_price:
                return None

            levels = self.risk_sizer.calculate_trade_levels(
                direction=SignalDirection.SHORT,
                current_price=current_price,
                structural_extreme=sweep.extreme_price,
                atr_value=atr_value,
                entry_method=EntryMethod.LIMIT_SWEPT_LEVEL,
                swept_level=sweep.level_price
            )

            score = self.scorer.calculate_score(
                direction=SignalDirection.SHORT,
                bundle=bundle,
                risk_reward_ratio=levels["risk_reward_tp2"],
                htf_aligned=True,
                funding_rate=funding_rate
            )

            total_score = max(score.total_score, 75.0)
            score.total_score = total_score

            confirmations = [
                f"Bearish 1H Trend: Swept premium {sweep.level_swept_type.value} at ${sweep.level_price:,.4f}",
                f"Immediate reclaim below level (wick: ${sweep.extreme_price:,.4f})",
                "Trend-aligned rally liquidity run (ICT Model)"
            ]
            if bundle.cvd_divergences:
                confirmations.append("CVD absorption confirmed")

            return TradeSignal(
                id=f"TPS-SHORT-{bundle.symbol}-{bundle.timestamp}",
                strategy_name=self.name,
                symbol=bundle.symbol,
                timeframe=bundle.timeframe,
                direction=SignalDirection.SHORT,
                state=SignalState.CONFIRMED,
                timestamp=bundle.timestamp,
                datetime=bundle.datetime,
                current_price=current_price,
                score=score,
                entry_method=EntryMethod.LIMIT_SWEPT_LEVEL,
                proposed_entry=levels["entry_price"],
                stop_loss=levels["stop_loss"],
                tp1=levels["tp1"],
                tp2=levels["tp2"],
                tp3=levels["tp3"],
                risk_reward_tp2=levels["risk_reward_tp2"],
                atr=atr_value,
                position_size_usd=levels["position_size_usd"],
                contracts=levels["contracts"],
                confirmations=confirmations,
                invalidation_condition=f"15m close above sweep high ${levels['stop_loss']:,.4f}"
            )

        return None

