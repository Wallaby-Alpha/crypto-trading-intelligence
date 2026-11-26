"""
Model 3: Swing Failure Pattern & Range Trap Strategy (SFP).
Institutional Logic:
- In consolidating or ranging markets, liquidity pools build up above range highs and below range lows.
- Price pierces outside the range, triggering breakout orders and stop-losses, but fails to maintain acceptance.
- As price re-enters the range, breakout traders are trapped off-side, fueling a rapid rotation across the range.

Rules:
1. Failed Acceptance / SFP detected at a significant Range High or Range Low.
2. Candle closes back strictly inside the range boundary.
3. Tight Stop Loss placed just outside the false breakout wick (0.20 ATR buffer).
4. Targets: TP1 = 1.0R (33%), TP2 = 2.0R (33%), TP3 = 3.0R (34% rotation runner).
"""
from typing import Optional, List, Dict, Any
from src.strategies.base import BaseStrategy
from src.strategies.models import TradeSignal, SignalDirection, SignalState, EntryMethod
from src.events.models import MarketEventBundle, FailedAcceptanceType


class SwingFailureRangeTrapStrategy(BaseStrategy):
    def __init__(self, is_enabled: bool = True, min_score_threshold: float = 65.0):
        super().__init__(name="Swing Failure Range Trap", is_enabled=is_enabled)
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
        if not self.is_enabled or not bundle.failed_acceptances:
            return None

        for fa in bundle.failed_acceptances:
            # -------------------------------------------------------------
            # Bullish SFP / Bear Trap (Failed breakdown below support)
            # -------------------------------------------------------------
            if fa.event_type == FailedAcceptanceType.FAILED_BREAKDOWN_BELOW:
                if htf_trend == "BEARISH":
                    # In strong downtrends, failed breakdowns can still fail
                    continue

                level = fa.level_price
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.LONG,
                    current_price=current_price,
                    structural_extreme=fa.extreme_price,
                    atr_value=atr_value,
                    entry_method=EntryMethod.LIMIT_SWEPT_LEVEL,
                    swept_level=level
                )

                score = self.scorer.calculate_score(
                    direction=SignalDirection.LONG,
                    bundle=bundle,
                    risk_reward_ratio=levels["risk_reward_tp2"],
                    htf_aligned=(htf_trend != "BEARISH"),
                    funding_rate=funding_rate
                )
                score.total_score = max(score.total_score, 74.0)

                return TradeSignal(
                    id=f"SFP-LONG-{bundle.symbol}-{bundle.timestamp}",
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
                        f"Failed Breakdown SFP at support ${level:,.4f}",
                        f"Price failed acceptance beyond level and closed back inside range",
                        "Bear trap rotation setup"
                    ],
                    invalidation_condition=f"15m close below support wick ${levels['stop_loss']:,.4f}"
                )

            # -------------------------------------------------------------
            # Bearish SFP / Bull Trap (Failed breakout above resistance)
            # -------------------------------------------------------------
            elif fa.event_type == FailedAcceptanceType.FAILED_BREAKOUT_ABOVE:
                if htf_trend == "BULLISH":
                    # In strong uptrends, do not fade breakouts!
                    continue

                level = fa.level_price
                levels = self.risk_sizer.calculate_trade_levels(
                    direction=SignalDirection.SHORT,
                    current_price=current_price,
                    structural_extreme=fa.extreme_price,
                    atr_value=atr_value,
                    entry_method=EntryMethod.LIMIT_SWEPT_LEVEL,
                    swept_level=level
                )

                score = self.scorer.calculate_score(
                    direction=SignalDirection.SHORT,
                    bundle=bundle,
                    risk_reward_ratio=levels["risk_reward_tp2"],
                    htf_aligned=(htf_trend != "BULLISH"),
                    funding_rate=funding_rate
                )
                score.total_score = max(score.total_score, 74.0)

                return TradeSignal(
                    id=f"SFP-SHORT-{bundle.symbol}-{bundle.timestamp}",
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
                        f"Failed Breakout SFP at resistance ${level:,.4f}",
                        f"Price failed acceptance beyond level and closed back inside range",
                        "Bull trap rotation setup"
                    ],
                    invalidation_condition=f"15m close above resistance wick ${levels['stop_loss']:,.4f}"
                )

        return None
