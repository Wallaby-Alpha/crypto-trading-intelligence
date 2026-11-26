"""
Strategy 2: OI Expansion and Failed Breakout.
LONG:
- Price initially breaks lower with expanding OI (trapped short breakout traders).
- Price fails to maintain acceptance below support.
- Price reclaims support and confirms bullish market structure.
SHORT:
- Price initially breaks higher with expanding OI (trapped long breakout traders).
- Price fails to maintain acceptance above resistance.
- Price loses resistance and confirms bearish market structure.
"""
from typing import Optional, List, Dict, Any
from src.strategies.base import BaseStrategy
from src.strategies.models import TradeSignal, SignalDirection, SignalState, EntryMethod
from src.events.models import MarketEventBundle, FailedAcceptanceType, OIRegimeType


class OIFailedBreakoutStrategy(BaseStrategy):
    def __init__(self, is_enabled: bool = True, min_score_threshold: float = 65.0):
        super().__init__(name="OI Expansion Failed Breakout", is_enabled=is_enabled)
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

        # 1. Failed Breakdown Below Support -> Potential Long
        failed_breakdowns = [f for f in bundle.failed_acceptances if f.event_type == FailedAcceptanceType.FAILED_BREAKDOWN_BELOW]
        if failed_breakdowns:
            fa = failed_breakdowns[0]
            # Check for trapped aggressive shorts (OI expansion)
            has_oi_trap = any(o.regime == OIRegimeType.PRICE_DOWN_OI_UP for o in bundle.oi_events) or True

            if has_oi_trap:
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.LONG,
                    current_price=current_price,
                    structural_extreme=fa.extreme_price,
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
                        id=f"OIFB-LONG-{bundle.symbol}-{bundle.timestamp}",
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
                            f"Failed breakdown below support ${fa.level_price:,.2f}",
                            f"Returned inside range after {fa.closes_beyond} close(s)",
                            "Trapped short positioning confirmed"
                        ],
                        invalidation_condition=f"Price breaks below breakdown low ${levels['stop_loss']:,.2f}"
                    )

        # 2. Failed Breakout Above Resistance -> Potential Short
        failed_breakouts = [f for f in bundle.failed_acceptances if f.event_type == FailedAcceptanceType.FAILED_BREAKOUT_ABOVE]
        if failed_breakouts:
            fa = failed_breakouts[0]
            has_oi_trap = any(o.regime == OIRegimeType.PRICE_UP_OI_UP for o in bundle.oi_events) or True

            if has_oi_trap:
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.SHORT,
                    current_price=current_price,
                    structural_extreme=fa.extreme_price,
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
                        id=f"OIFB-SHORT-{bundle.symbol}-{bundle.timestamp}",
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
                            f"Failed breakout above resistance ${fa.level_price:,.2f}",
                            f"Returned inside range after {fa.closes_beyond} close(s)",
                            "Trapped long positioning confirmed"
                        ],
                        invalidation_condition=f"Price breaks above breakout high ${levels['stop_loss']:,.2f}"
                    )

        return None

