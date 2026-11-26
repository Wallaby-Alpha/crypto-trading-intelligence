"""
Strategy 6: VWAP and Volume Profile Reversion.
Identifies statistical overextensions from VWAP (>= 2 sigma) or extreme Value Area excursions,
followed by measurable price action rejection back toward the session mean.
"""
from typing import Optional, List, Dict, Any
from src.strategies.base import BaseStrategy
from src.strategies.models import TradeSignal, SignalDirection, SignalState, EntryMethod
from src.events.models import MarketEventBundle, VWAPVolumeEventType


class VWAPMeanReversionStrategy(BaseStrategy):
    def __init__(self, is_enabled: bool = True, min_score_threshold: float = 65.0):
        super().__init__(name="VWAP & Volume Profile Reversion", is_enabled=is_enabled)
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
        if not self.is_enabled or not bundle.vwap_events:
            return None

        for ve in bundle.vwap_events:
            # 1. Bearish Rejection from Upper Band / VWAP -> Short
            if ve.event_type == VWAPVolumeEventType.VWAP_REJECTION_BEARISH:
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.SHORT,
                    current_price=current_price,
                    structural_extreme=ve.reference_price + (atr_value * 0.8),
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
                        id=f"VWAP-SHORT-{bundle.symbol}-{bundle.timestamp}",
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
                            f"Bearish rejection from VWAP at ${ve.reference_price:,.2f}",
                            f"Overextension distance: {ve.distance_pct:.2f}%",
                            f"Rejection volume ratio: {ve.volume_ratio:.2f}x MA"
                        ],
                        invalidation_condition=f"Price breaks above swing high ${levels['stop_loss']:,.2f}"
                    )

            # 2. Bullish Rejection from Lower Band / VWAP -> Long
            elif ve.event_type in [VWAPVolumeEventType.VWAP_REJECTION_BULLISH, VWAPVolumeEventType.VWAP_RECLAIM_BULLISH]:
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.LONG,
                    current_price=current_price,
                    structural_extreme=ve.reference_price - (atr_value * 0.8),
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
                        id=f"VWAP-LONG-{bundle.symbol}-{bundle.timestamp}",
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
                            f"Bullish bounce/reclaim from VWAP at ${ve.reference_price:,.2f}",
                            f"Reclaim distance: {ve.distance_pct:.2f}%",
                            f"Rejection volume ratio: {ve.volume_ratio:.2f}x MA"
                        ],
                        invalidation_condition=f"Price breaks below swing low ${levels['stop_loss']:,.2f}"
                    )

        return None

