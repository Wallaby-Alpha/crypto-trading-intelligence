"""
Risk Management, Position Sizing, and Entry/Stop/TP Engine.
Calculates:
- Protective Stop Loss (anchored to structural extreme with ATR buffer)
- Take Profit Targets (TP1 = 1.0R, TP2 = 2.0R, TP3 = 3.0R)
- Risk-to-Reward ratio
- Account risk position sizing (e.g. 1% account risk)
"""
from typing import Dict, Any, Tuple, Optional
from src.strategies.models import SignalDirection, EntryMethod


class RiskSizer:
    def __init__(
        self,
        account_equity_usd: float = 10_000.0,
        risk_pct_per_trade: float = 1.0,
        atr_buffer_mult: float = 0.15,
        max_position_leverage: float = 10.0
    ):
        self.account_equity_usd = account_equity_usd
        self.risk_pct_per_trade = risk_pct_per_trade
        self.atr_buffer_mult = atr_buffer_mult
        self.max_position_leverage = max_position_leverage

    def calculate_trade_levels(
        self,
        direction: SignalDirection,
        current_price: float,
        structural_extreme: float,
        atr_value: float,
        entry_method: EntryMethod = EntryMethod.MARKET_CONFIRMATION,
        swept_level: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Calculates entry, stop loss, and tiered take profit targets (TP1, TP2, TP3).
        """
        buffer = max(atr_value * 0.20, current_price * 0.001)

        # 1. Proposed Entry
        if entry_method == EntryMethod.MARKET_CONFIRMATION:
            entry_price = current_price
        elif entry_method == EntryMethod.LIMIT_RETRACEMENT:
            entry_price = current_price * 0.998 if direction == SignalDirection.LONG else current_price * 1.002
        elif entry_method == EntryMethod.LIMIT_SWEPT_LEVEL and swept_level is not None:
            if direction == SignalDirection.LONG:
                entry_price = min(current_price, swept_level + 0.10 * atr_value)
            else:
                entry_price = max(current_price, swept_level - 0.10 * atr_value)
        else:
            entry_price = current_price

        # 2. Protective Stop Loss
        if direction == SignalDirection.LONG:
            # Stop loss strictly below the low extreme
            stop_loss = structural_extreme - buffer
            if stop_loss >= entry_price:
                stop_loss = entry_price - (atr_value * 1.0)
            risk_dist = entry_price - stop_loss
            tp1 = entry_price + (1.0 * risk_dist)
            tp2 = entry_price + (2.0 * risk_dist)
            tp3 = entry_price + (3.0 * risk_dist)
        else:
            # Stop loss strictly above the high extreme
            stop_loss = structural_extreme + buffer
            if stop_loss <= entry_price:
                stop_loss = entry_price + (atr_value * 1.0)
            risk_dist = stop_loss - entry_price
            tp1 = entry_price - (1.0 * risk_dist)
            tp2 = entry_price - (2.0 * risk_dist)
            tp3 = entry_price - (3.0 * risk_dist)

        risk_reward_tp2 = 2.0
        risk_pct_of_price = (risk_dist / entry_price) * 100.0

        # 3. Position Sizing
        risk_capital_usd = self.account_equity_usd * (self.risk_pct_per_trade / 100.0)
        pos_size_usd = risk_capital_usd / max(risk_dist / entry_price, 1e-4)

        # Cap at maximum permissible leverage
        max_allowable_pos = self.account_equity_usd * self.max_position_leverage
        pos_size_usd = min(pos_size_usd, max_allowable_pos)
        contracts = pos_size_usd / entry_price

        return {
            "entry_price": round(entry_price, 4),
            "stop_loss": round(stop_loss, 4),
            "tp1": round(tp1, 4),
            "tp2": round(tp2, 4),
            "tp3": round(tp3, 4),
            "risk_dist": round(risk_dist, 4),
            "risk_reward_tp2": risk_reward_tp2,
            "risk_pct_of_price": round(risk_pct_of_price, 2),
            "position_size_usd": round(pos_size_usd, 2),
            "contracts": round(contracts, 4)
        }

