"""
Strategy 4: CVD Divergence Reversal.
Identifies high-conviction orderflow divergence at significant levels.
Requires price-action confirmation (e.g. rejection wick or MSS) before generating an actionable trade.
"""
from typing import Optional, List, Dict, Any
from src.strategies.base import BaseStrategy
from src.strategies.models import TradeSignal, SignalDirection, SignalState, EntryMethod
from src.events.models import MarketEventBundle, CVDDivergenceType


class CVDDivergenceReversalStrategy(BaseStrategy):
    def __init__(self, is_enabled: bool = True, min_score_threshold: float = 65.0, min_cvd_score: float = 55.0):
        super().__init__(name="CVD Divergence Reversal", is_enabled=is_enabled)
        self.min_score_threshold = min_score_threshold
        self.min_cvd_score = min_cvd_score

    def evaluate(
        self,
        bundle: MarketEventBundle,
        current_price: float,
        atr_value: float,
        funding_rate: Optional[float] = None,
        htf_aligned: bool = False,
        **kwargs
    ) -> Optional[TradeSignal]:
        if not self.is_enabled or not bundle.cvd_divergences:
            return None

        for div in bundle.cvd_divergences:
            if div.strength_score < self.min_cvd_score:
                continue

            # 1. Bullish Absorption (Price lower low, CVD higher low) -> Long
            if div.divergence_type == CVDDivergenceType.BULLISH_CVD_ABSORPTION:
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.LONG,
                    current_price=current_price,
                    structural_extreme=div.price_swing_2,
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
                        id=f"CVD-LONG-{bundle.symbol}-{bundle.timestamp}",
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
                            f"Bullish CVD absorption divergence (Score: {div.strength_score:.1f}/100)",
                            f"Aggressive sellers absorbed at low ${div.price_swing_2:,.2f}"
                        ],
                        invalidation_condition=f"Price drops below swing low ${levels['stop_loss']:,.2f}"
                    )

            # 2. Bearish Absorption (Price higher high, CVD lower high) -> Short
            elif div.divergence_type == CVDDivergenceType.BEARISH_CVD_ABSORPTION:
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.SHORT,
                    current_price=current_price,
                    structural_extreme=div.price_swing_2,
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
                        id=f"CVD-SHORT-{bundle.symbol}-{bundle.timestamp}",
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
                            f"Bearish CVD absorption divergence (Score: {div.strength_score:.1f}/100)",
                            f"Aggressive buyers absorbed at high ${div.price_swing_2:,.2f}"
                        ],
                        invalidation_condition=f"Price exceeds swing high ${levels['stop_loss']:,.2f}"
                    )

        return None

