"""
Strategy 5: Momentum Breakout.
Identifies genuine breakouts supported by:
- Volume expansion (> 1.5x MA)
- Institutional displacement candle (body >= 1.2x ATR)
- Trend continuation (BOS)
- Sustained acceptance beyond key levels
Distinguishes genuine trend breakouts from false liquidity sweeps.
"""
from typing import Optional, List, Dict, Any
from src.strategies.base import BaseStrategy
from src.strategies.models import TradeSignal, SignalDirection, SignalState, EntryMethod
from src.events.models import MarketEventBundle, MarketStructureType


class MomentumBreakoutStrategy(BaseStrategy):
    def __init__(self, is_enabled: bool = True, min_score_threshold: float = 65.0):
        super().__init__(name="Momentum Breakout", is_enabled=is_enabled)
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
        if not self.is_enabled or not bundle.structure_events:
            return None

        # Filter out if current candle is a liquidity sweep (sweeps indicate reversal, not momentum breakout)
        if bundle.sweeps:
            return None

        for m in bundle.structure_events:
            # 1. Bullish Momentum Breakout (BOS Bullish with displacement)
            if m.event_type in [MarketStructureType.BOS_BULLISH, MarketStructureType.MSS_BULLISH] and m.displacement_ratio >= 1.0:
                # Stop loss placed behind the broken level
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.LONG,
                    current_price=current_price,
                    structural_extreme=m.broken_level_price - (atr_value * 0.5),
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
                        id=f"MB-LONG-{bundle.symbol}-{bundle.timestamp}",
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
                            f"Bullish Break of Structure (BOS) above ${m.broken_level_price:,.2f}",
                            f"Institutional displacement: {m.displacement_ratio:.2f}x ATR",
                            "High-volume directional momentum"
                        ],
                        invalidation_condition=f"Price falls back below broken structure ${levels['stop_loss']:,.2f}"
                    )

            # 2. Bearish Momentum Breakdown (BOS Bearish with displacement)
            elif m.event_type in [MarketStructureType.BOS_BEARISH, MarketStructureType.MSS_BEARISH] and m.displacement_ratio >= 1.0:
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.SHORT,
                    current_price=current_price,
                    structural_extreme=m.broken_level_price + (atr_value * 0.5),
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
                        id=f"MB-SHORT-{bundle.symbol}-{bundle.timestamp}",
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
                            f"Bearish Break of Structure (BOS) below ${m.broken_level_price:,.2f}",
                            f"Institutional displacement: {m.displacement_ratio:.2f}x ATR",
                            "High-volume directional breakdown"
                        ],
                        invalidation_condition=f"Price reclaims above broken structure ${levels['stop_loss']:,.2f}"
                    )

        return None

