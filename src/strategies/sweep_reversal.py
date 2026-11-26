"""
Strategy 1: Liquidity Sweep Reversal.
LONG:
- Price sweeps a significant low (Swing Low, Equal Lows, Session Low).
- Price reclaims the swept level.
- Bullish CVD divergence absorption or Bullish market structure shift (MSS/CHoCH).
SHORT:
- Price sweeps a significant high (Swing High, Equal Highs, Session High).
- Price reclaims below the swept level.
- Bearish CVD divergence absorption or Bearish market structure shift (MSS/CHoCH).
"""
import uuid
from typing import Optional, List, Dict, Any
from src.strategies.base import BaseStrategy
from src.strategies.models import TradeSignal, SignalDirection, SignalState, EntryMethod
from src.events.models import MarketEventBundle, SweepDirection, MarketStructureType, CVDDivergenceType


class LiquiditySweepReversalStrategy(BaseStrategy):
    def __init__(self, is_enabled: bool = True, min_score_threshold: float = 65.0):
        super().__init__(name="Liquidity Sweep Reversal", is_enabled=is_enabled)
        self.min_score_threshold = min_score_threshold

    def evaluate(
        self,
        bundle: MarketEventBundle,
        current_price: float,
        atr_value: float,
        funding_rate: Optional[float] = None,
        htf_aligned: bool = False,
        **kwargs
    ) -> Optional[TradeSignal]:
        if not self.is_enabled or not bundle.sweeps:
            return None

        # 1. Evaluate Bullish Sweep of Lows -> Potential Long
        bullish_sweeps = [s for s in bundle.sweeps if s.direction == SweepDirection.BULLISH_SWEEP_LOW]
        if bullish_sweeps:
            sweep = bullish_sweeps[0]
            # Check for bullish confirmation: MSS/CHoCH or Bullish CVD Divergence
            has_mss = any(m.current_trend == "BULLISH" for m in bundle.structure_events)
            has_cvd = any(c.divergence_type == CVDDivergenceType.BULLISH_CVD_ABSORPTION for c in bundle.cvd_divergences)
            has_rejection = sweep.rejection_strength_pct >= 50.0

            if has_mss or has_cvd or has_rejection:
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.LONG,
                    current_price=current_price,
                    structural_extreme=sweep.extreme_price,
                    atr_value=atr_value,
                    entry_method=EntryMethod.MARKET_CONFIRMATION
                )

                score = self.scorer.calculate_score(
                    direction=SignalDirection.LONG,
                    bundle=bundle,
                    risk_reward_ratio=levels["risk_reward_tp2"],
                    htf_aligned=htf_aligned,
                    funding_rate=funding_rate
                )

                if score.total_score >= self.min_score_threshold:
                    confirmations = [
                        f"Swept {sweep.level_swept_type.value} at ${sweep.level_price:,.2f}",
                        f"Reclaimed above level (extreme: ${sweep.extreme_price:,.2f}, rejection: {sweep.rejection_strength_pct:.1f}%)"
                    ]
                    if has_mss:
                        confirmations.append("Bullish Market Structure Shift confirmed")
                    if has_cvd:
                        confirmations.append("Bullish CVD absorption divergence detected")
                    if htf_aligned:
                        confirmations.append("Higher timeframe directional confluence")

                    return TradeSignal(
                        id=f"LSR-LONG-{bundle.symbol}-{bundle.timestamp}",
                        strategy_name=self.name,
                        symbol=bundle.symbol,
                        timeframe=bundle.timeframe,
                        direction=SignalDirection.LONG,
                        state=SignalState.CONFIRMED,
                        timestamp=bundle.timestamp,
                        datetime=bundle.datetime,
                        current_price=current_price,
                        score=score,
                        entry_method=EntryMethod.MARKET_CONFIRMATION,
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
                        invalidation_condition=f"Price breaks below sweep low ${levels['stop_loss']:,.2f}"
                    )

        # 2. Evaluate Bearish Sweep of Highs -> Potential Short
        bearish_sweeps = [s for s in bundle.sweeps if s.direction == SweepDirection.BEARISH_SWEEP_HIGH]
        if bearish_sweeps:
            sweep = bearish_sweeps[0]
            has_mss = any(m.current_trend == "BEARISH" for m in bundle.structure_events)
            has_cvd = any(c.divergence_type == CVDDivergenceType.BEARISH_CVD_ABSORPTION for c in bundle.cvd_divergences)
            has_rejection = sweep.rejection_strength_pct >= 50.0

            if has_mss or has_cvd or has_rejection:
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.SHORT,
                    current_price=current_price,
                    structural_extreme=sweep.extreme_price,
                    atr_value=atr_value,
                    entry_method=EntryMethod.MARKET_CONFIRMATION
                )

                score = self.scorer.calculate_score(
                    direction=SignalDirection.SHORT,
                    bundle=bundle,
                    risk_reward_ratio=levels["risk_reward_tp2"],
                    htf_aligned=htf_aligned,
                    funding_rate=funding_rate
                )

                if score.total_score >= self.min_score_threshold:
                    confirmations = [
                        f"Swept {sweep.level_swept_type.value} at ${sweep.level_price:,.2f}",
                        f"Reclaimed below level (extreme: ${sweep.extreme_price:,.2f}, rejection: {sweep.rejection_strength_pct:.1f}%)"
                    ]
                    if has_mss:
                        confirmations.append("Bearish Market Structure Shift confirmed")
                    if has_cvd:
                        confirmations.append("Bearish CVD absorption divergence detected")
                    if htf_aligned:
                        confirmations.append("Higher timeframe directional confluence")

                    return TradeSignal(
                        id=f"LSR-SHORT-{bundle.symbol}-{bundle.timestamp}",
                        strategy_name=self.name,
                        symbol=bundle.symbol,
                        timeframe=bundle.timeframe,
                        direction=SignalDirection.SHORT,
                        state=SignalState.CONFIRMED,
                        timestamp=bundle.timestamp,
                        datetime=bundle.datetime,
                        current_price=current_price,
                        score=score,
                        entry_method=EntryMethod.MARKET_CONFIRMATION,
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
                        invalidation_condition=f"Price breaks above sweep high ${levels['stop_loss']:,.2f}"
                    )

        return None

