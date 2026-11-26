"""
Unified Multi-Factor Signal Scoring Engine (0-100).
Configurable weights:
- Liquidity event quality: 15
- Market structure confirmation: 15
- OI behavior: 15
- CVD confirmation: 15
- Volume/displacement: 10
- VWAP/volume profile context: 10
- Higher timeframe alignment: 10
- Funding/positioning context: 5
- Risk/reward potential: 5
Categorization:
- 0–49: No actionable signal
- 50–64: Watchlist
- 65–79: Qualified setup
- 80–89: Strong setup
- 90–100: Exceptional setup
"""
from typing import Optional, List, Dict, Any
from src.strategies.models import ScoreBreakdown, SignalCategory, SignalDirection
from src.events.models import MarketEventBundle, LiquidityLevelType, MarketStructureType, OIRegimeType, CVDDivergenceType


class SignalScorer:
    def __init__(
        self,
        w_liquidity: float = 15.0,
        w_structure: float = 15.0,
        w_oi: float = 15.0,
        w_cvd: float = 15.0,
        w_volume: float = 10.0,
        w_vwap: float = 10.0,
        w_htf: float = 10.0,
        w_funding: float = 5.0,
        w_rr: float = 5.0
    ):
        self.w_liquidity = w_liquidity
        self.w_structure = w_structure
        self.w_oi = w_oi
        self.w_cvd = w_cvd
        self.w_volume = w_volume
        self.w_vwap = w_vwap
        self.w_htf = w_htf
        self.w_funding = w_funding
        self.w_rr = w_rr

    def calculate_score(
        self,
        direction: SignalDirection,
        bundle: MarketEventBundle,
        risk_reward_ratio: float,
        htf_aligned: bool = False,
        funding_rate: Optional[float] = None
    ) -> ScoreBreakdown:
        """
        Calculates unified multi-factor score (0-100) for a directional setup.
        """
        # 1. Liquidity Quality (0 to w_liquidity)
        score_liq = 0.0
        if bundle.sweeps:
            for s in bundle.sweeps:
                base = 8.0
                # Premium for high-tier liquidity pools (Equal Highs/Lows, Session extremes)
                if s.level_swept_type in [LiquidityLevelType.EQUAL_HIGHS, LiquidityLevelType.EQUAL_LOWS, LiquidityLevelType.SESSION_HIGH, LiquidityLevelType.SESSION_LOW]:
                    base += 4.0
                # Premium for strong wick rejection (>70%)
                if s.rejection_strength_pct >= 70.0:
                    base += 3.0
                score_liq = max(score_liq, min(self.w_liquidity, base))
        elif bundle.failed_acceptances:
            score_liq = min(self.w_liquidity, 10.0)

        # 2. Market Structure Confirmation (0 to w_structure)
        score_struct = 0.0
        if bundle.structure_events:
            for m in bundle.structure_events:
                if direction == SignalDirection.LONG and m.current_trend == "BULLISH":
                    if m.event_type == MarketStructureType.MSS_BULLISH:
                        score_struct = max(score_struct, self.w_structure)
                    elif m.event_type in [MarketStructureType.CHOCH_BULLISH, MarketStructureType.BOS_BULLISH]:
                        score_struct = max(score_struct, self.w_structure * 0.8)
                elif direction == SignalDirection.SHORT and m.current_trend == "BEARISH":
                    if m.event_type == MarketStructureType.MSS_BEARISH:
                        score_struct = max(score_struct, self.w_structure)
                    elif m.event_type in [MarketStructureType.CHOCH_BEARISH, MarketStructureType.BOS_BEARISH]:
                        score_struct = max(score_struct, self.w_structure * 0.8)

        # 3. OI Behavior (0 to w_oi)
        score_oi = 0.0
        if bundle.oi_events:
            for o in bundle.oi_events:
                if direction == SignalDirection.LONG:
                    if o.regime in [OIRegimeType.PRICE_DOWN_OI_DOWN, OIRegimeType.PRICE_UP_OI_UP]:
                        score_oi = self.w_oi if o.is_unusual_expansion else (self.w_oi * 0.75)
                elif direction == SignalDirection.SHORT:
                    if o.regime in [OIRegimeType.PRICE_UP_OI_DOWN, OIRegimeType.PRICE_DOWN_OI_UP]:
                        score_oi = self.w_oi if o.is_unusual_expansion else (self.w_oi * 0.75)
        else:
            score_oi = self.w_oi * 0.4  # Neutral baseline

        # 4. CVD Confirmation (0 to w_cvd)
        score_cvd = 0.0
        if bundle.cvd_divergences:
            for c in bundle.cvd_divergences:
                if direction == SignalDirection.LONG and c.divergence_type == CVDDivergenceType.BULLISH_CVD_ABSORPTION:
                    score_cvd = max(score_cvd, (c.strength_score / 100.0) * self.w_cvd)
                elif direction == SignalDirection.SHORT and c.divergence_type == CVDDivergenceType.BEARISH_CVD_ABSORPTION:
                    score_cvd = max(score_cvd, (c.strength_score / 100.0) * self.w_cvd)
        else:
            score_cvd = self.w_cvd * 0.35  # Moderate baseline when no divergence detected

        # 5. Volume / Displacement (0 to w_volume)
        score_vol = 0.0
        has_disp = any(m.displacement_ratio >= 1.2 for m in bundle.structure_events)
        has_high_vol = any(v.volume_ratio >= 1.5 for v in bundle.vwap_events)
        if has_disp and has_high_vol:
            score_vol = self.w_volume
        elif has_disp or has_high_vol:
            score_vol = self.w_volume * 0.7
        else:
            score_vol = self.w_volume * 0.4

        # 6. VWAP / Volume Profile Context (0 to w_vwap)
        score_vwap = 0.0
        if bundle.vwap_events:
            score_vwap = min(self.w_vwap, 4.0 * len(bundle.vwap_events))
        else:
            score_vwap = self.w_vwap * 0.5

        # 7. HTF Alignment (0 to w_htf)
        score_htf = self.w_htf if htf_aligned else (self.w_htf * 0.3)

        # 8. Funding Context (0 to w_funding)
        score_funding = 0.0
        if funding_rate is not None:
            # Favorable funding: negative funding for longs (shorts pay longs)
            if direction == SignalDirection.LONG:
                if funding_rate < -0.0001:
                    score_funding = self.w_funding
                elif funding_rate < 0.0002:
                    score_funding = self.w_funding * 0.6
                else:
                    score_funding = self.w_funding * 0.2
            elif direction == SignalDirection.SHORT:
                if funding_rate > 0.0003:
                    score_funding = self.w_funding
                elif funding_rate > -0.0001:
                    score_funding = self.w_funding * 0.6
                else:
                    score_funding = self.w_funding * 0.2
        else:
            score_funding = self.w_funding * 0.5

        # 9. Risk / Reward Potential (0 to w_rr)
        score_rr = 0.0
        if risk_reward_ratio >= 3.0:
            score_rr = self.w_rr
        elif risk_reward_ratio >= 2.0:
            score_rr = self.w_rr * 0.8
        elif risk_reward_ratio >= 1.5:
            score_rr = self.w_rr * 0.5
        else:
            score_rr = self.w_rr * 0.2

        total = (
            score_liq + score_struct + score_oi + score_cvd +
            score_vol + score_vwap + score_htf + score_funding + score_rr
        )
        total = round(min(100.0, max(0.0, total)), 1)

        # Categorize
        if total >= 90.0:
            category = SignalCategory.EXCEPTIONAL
        elif total >= 80.0:
            category = SignalCategory.STRONG
        elif total >= 65.0:
            category = SignalCategory.QUALIFIED
        elif total >= 50.0:
            category = SignalCategory.WATCHLIST
        else:
            category = SignalCategory.NO_SIGNAL

        return ScoreBreakdown(
            liquidity_quality=round(score_liq, 1),
            market_structure=round(score_struct, 1),
            oi_behavior=round(score_oi, 1),
            cvd_confirmation=round(score_cvd, 1),
            volume_displacement=round(score_vol, 1),
            vwap_context=round(score_vwap, 1),
            htf_alignment=round(score_htf, 1),
            funding_context=round(score_funding, 1),
            risk_reward=round(score_rr, 1),
            total_score=total,
            category=category
        )

