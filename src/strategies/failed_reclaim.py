"""
Strategy 3: Failed Reclaim Continuation.
LONG:
- Bullish market structure.
- Price breaks above a significant level.
- Retest of breakout level holds (support retest), followed by continuation.
SHORT:
- Bearish market structure.
- Price breaks below a significant level.
- Retest of breakdown level fails to reclaim (rejected at resistance), followed by continuation lower.
"""
from typing import Optional, List, Dict, Any
from src.strategies.base import BaseStrategy
from src.strategies.models import TradeSignal, SignalDirection, SignalState, EntryMethod
from src.events.models import MarketEventBundle, FailedAcceptanceType


class FailedReclaimContinuationStrategy(BaseStrategy):
    def __init__(self, is_enabled: bool = True, min_score_threshold: float = 65.0):
        super().__init__(name="Failed Reclaim Continuation", is_enabled=is_enabled)
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
        if not self.is_enabled or not bundle.failed_acceptances:
            return None

        # 1. Bearish Failed Reclaim Continuation (Short)
        failed_reclaims_res = [f for f in bundle.failed_acceptances if f.event_type == FailedAcceptanceType.FAILED_RECLAIM_RESISTANCE]
        if failed_reclaims_res:
            fr = failed_reclaims_res[0]
            levels = self.risk_sizer.calculate_trade_levels(
                direction=SignalDirection.SHORT,
                current_price=current_price,
                structural_extreme=fr.extreme_price,
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
                return TradeSignal(
                    id=f"FRC-SHORT-{bundle.symbol}-{bundle.timestamp}",
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
                    confirmations=[
                        f"Failed to reclaim broken support ${fr.level_price:,.2f}",
                        "Retest rejected with bearish continuation"
                    ],
                    invalidation_condition=f"Price reclaims above resistance ${levels['stop_loss']:,.2f}"
                )

        # 2. Bullish Retest Bounce Continuation (Long)
        support_bounces = [f for f in bundle.failed_acceptances if f.event_type == FailedAcceptanceType.FAILED_RECLAIM_SUPPORT]
        if support_bounces:
            sb = support_bounces[0]
            levels = self.risk_sizer.calculate_trade_levels(
                direction=SignalDirection.LONG,
                current_price=current_price,
                structural_extreme=sb.extreme_price,
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
                return TradeSignal(
                    id=f"FRC-LONG-{bundle.symbol}-{bundle.timestamp}",
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
                    confirmations=[
                        f"Retest of broken resistance at ${sb.level_price:,.2f} held as support",
                        "Bullish continuation confirmed"
                    ],
                    invalidation_condition=f"Price breaks below support level ${levels['stop_loss']:,.2f}"
                )

        return None

