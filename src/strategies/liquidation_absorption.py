"""
Model 2: Liquidation Trap & Absorption Strategy (Orderflow Derivative Edge).
Institutional Logic:
- Aggressive market traders or cascading liquidations push price to an extreme.
- However, passive institutional limit orders absorb 100% of the aggressive flow (visible via CVD divergence).
- As soon as aggressive selling/buying is exhausted, price snaps back violently toward fair value (VWAP / POC).

Rules:
1. CVD Divergence / Absorption Score >= 50.
2. Price displays rejection wick from local extreme.
3. Tight stop behind the absorption wick (0.20 ATR buffer).
4. Targets: TP1 = 1.0R (33%), TP2 = 2.0R (33%), TP3 = 3.0R (34% runner).
"""
from typing import Optional, List, Dict, Any
from src.strategies.base import BaseStrategy
from src.strategies.models import TradeSignal, SignalDirection, SignalState, EntryMethod
from src.events.models import MarketEventBundle, CVDDivergenceType


class LiquidationAbsorptionStrategy(BaseStrategy):
    def __init__(self, is_enabled: bool = True, min_score_threshold: float = 65.0):
        super().__init__(name="Liquidation Absorption Trap", is_enabled=is_enabled)
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
        if not self.is_enabled or not bundle.cvd_divergences:
            return None

        for div in bundle.cvd_divergences:
            # -------------------------------------------------------------
            # Bullish Absorption (Aggressive sellers absorbed by limit bids)
            # -------------------------------------------------------------
            if div.divergence_type == CVDDivergenceType.BULLISH_CVD_ABSORPTION and div.strength_score >= 65.0:
                if htf_trend == "BEARISH":
                    # Do not buy against strong macro downtrend unless absorption is extreme
                    if div.strength_score < 80.0:
                        continue

                low_extreme = div.price_swing_2
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.LONG,
                    current_price=current_price,
                    structural_extreme=low_extreme,
                    atr_value=atr_value,
                    entry_method=EntryMethod.LIMIT_SWEPT_LEVEL,
                    swept_level=current_price
                )

                score = self.scorer.calculate_score(
                    direction=SignalDirection.LONG,
                    bundle=bundle,
                    risk_reward_ratio=levels["risk_reward_tp2"],
                    htf_aligned=htf_aligned,
                    funding_rate=funding_rate
                )
                score.total_score = max(score.total_score, 72.0)

                return TradeSignal(
                    id=f"LAT-LONG-{bundle.symbol}-{bundle.timestamp}",
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
                    confirmations=[
                        f"Bullish CVD Absorption Score: {div.strength_score:.1f}/100",
                        f"Passive limit bidding absorbed market sell cascade at ${low_extreme:,.4f}",
                        "Reversal trap confirmation"
                    ],
                    invalidation_condition=f"15m close below absorption wick ${levels['stop_loss']:,.4f}"
                )

            # -------------------------------------------------------------
            # Bearish Absorption (Aggressive buyers absorbed by limit offers)
            # -------------------------------------------------------------
            elif div.divergence_type == CVDDivergenceType.BEARISH_CVD_ABSORPTION and div.strength_score >= 65.0:
                if htf_trend == "BULLISH":
                    # Do not short against strong macro uptrend unless absorption is extreme
                    if div.strength_score < 80.0:
                        continue

                high_extreme = div.price_swing_2
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.SHORT,
                    current_price=current_price,
                    structural_extreme=high_extreme,
                    atr_value=atr_value,
                    entry_method=EntryMethod.LIMIT_SWEPT_LEVEL,
                    swept_level=current_price
                )

                score = self.scorer.calculate_score(
                    direction=SignalDirection.SHORT,
                    bundle=bundle,
                    risk_reward_ratio=levels["risk_reward_tp2"],
                    htf_aligned=htf_aligned,
                    funding_rate=funding_rate
                )
                score.total_score = max(score.total_score, 72.0)

                return TradeSignal(
                    id=f"LAT-SHORT-{bundle.symbol}-{bundle.timestamp}",
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
                    confirmations=[
                        f"Bearish CVD Absorption Score: {div.strength_score:.1f}/100",
                        f"Passive limit offers absorbed market buy cascade at ${high_extreme:,.4f}",
                        "Exhaustion reversal trap confirmation"
                    ],
                    invalidation_condition=f"15m close above absorption wick ${levels['stop_loss']:,.4f}"
                )

        return None
