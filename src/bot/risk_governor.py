"""
Risk Governor & De Minimis Position Sizer.
Enforces strict portfolio safety controls for live trading:
1. Fixed de minimis margin allocation per trade ($10 - $25).
2. Maximum concurrent open positions (default: 2-3) to eliminate correlated portfolio drawdown.
3. Daily loss circuit breaker: halts trading if cumulative daily loss exceeds threshold.
4. Exchange minimum notional check and precision rounding for WEEX contract specifications.
"""
import os
import logging
import math
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone

logger = logging.getLogger("risk_governor")


class RiskGovernor:
    def __init__(
        self,
        trade_margin_usd: float = 15.0,
        default_leverage: int = 2,
        max_open_positions: int = 2,
        max_daily_loss_usd: float = 30.0,
        min_notional_usd: float = 5.0
    ):
        self.trade_margin_usd = float(os.getenv("TRADE_AMOUNT_USD", trade_margin_usd))
        self.default_leverage = int(os.getenv("DEFAULT_LEVERAGE", default_leverage))
        self.max_open_positions = int(os.getenv("MAX_CONCURRENT_POSITIONS", max_open_positions))
        self.max_daily_loss_usd = float(os.getenv("MAX_DAILY_LOSS_USD", max_daily_loss_usd))
        self.min_notional_usd = min_notional_usd

        # State tracking
        self.daily_realized_pnl: float = 0.0
        self.last_reset_date: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.circuit_breaker_tripped: bool = False

    def check_daily_reset(self):
        """Resets the daily PnL counter at 00:00 UTC."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self.last_reset_date:
            logger.info(f"Daily reset triggered. Previous Day PnL: ${self.daily_realized_pnl:,.2f}")
            self.daily_realized_pnl = 0.0
            self.last_reset_date = today
            self.circuit_breaker_tripped = False

    def record_trade_result(self, realized_pnl_usd: float):
        """Records realized PnL and trips circuit breaker if loss limit exceeded."""
        self.check_daily_reset()
        self.daily_realized_pnl += realized_pnl_usd
        logger.info(f"Updated Daily PnL: ${self.daily_realized_pnl:,.2f}")

        if self.daily_realized_pnl <= -abs(self.max_daily_loss_usd):
            self.circuit_breaker_tripped = True
            logger.critical(
                f"🚨 CIRCUIT BREAKER TRIPPED! Daily loss ${abs(self.daily_realized_pnl):,.2f} "
                f"exceeds limit ${self.max_daily_loss_usd:,.2f}. Halting new entries for today."
            )

    def can_open_position(self, current_open_count: int) -> Tuple[bool, str]:
        """Validates whether a new position may be opened."""
        self.check_daily_reset()

        if self.circuit_breaker_tripped:
            return False, f"Daily loss limit reached (${self.daily_realized_pnl:,.2f} <= -${self.max_daily_loss_usd:,.2f})"

        if current_open_count >= self.max_open_positions:
            return False, f"Maximum concurrent positions reached ({current_open_count}/{self.max_open_positions})"

        return True, "OK"

    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        market_meta: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, float]:
        """
        Calculates quantity (in base currency / coins for CCXT) and total notional USD.
        Properly handles exchange step size, lot limits, and enforces safety bounds.
        Returns: (amount, notional_usd)
        """
        target_notional = self.trade_margin_usd * self.default_leverage

        if target_notional < self.min_notional_usd:
            target_notional = self.min_notional_usd

        raw_amount = target_notional / max(price, 1e-6)

        if market_meta:
            # CCXT precision['amount'] or contractSize defines the step size
            precision_amount = market_meta.get("precision", {}).get("amount")
            contract_size = market_meta.get("contractSize", 1.0) or 1.0

            if precision_amount is not None:
                if isinstance(precision_amount, (int, float)) and precision_amount < 1.0:
                    step = float(precision_amount)
                elif isinstance(precision_amount, int):
                    step = 10 ** (-precision_amount)
                else:
                    step = float(precision_amount)
            else:
                step = float(contract_size) if contract_size else 0.001

            limits = market_meta.get("limits", {}).get("amount", {})
            min_amount = float(limits.get("min") or step or 0.001)

            # Sizing in terms of discrete steps
            num_steps = round(raw_amount / step) if step > 0 else 1
            amount = max(num_steps * step, min_amount)

            # Round to precision decimal places
            decimals = 0 if step >= 1.0 else len(str(step).split(".")[1]) if "." in str(step) else 4
            amount = round(amount, decimals)
        else:
            amount = round(raw_amount, 4)

        actual_notional = amount * price

        # Safety Guard: Ensure actual notional never balloons above target notional by more than 1.5x
        max_allowed_notional = target_notional * 1.5
        if actual_notional > max_allowed_notional:
            logger.warning(
                f"Sizing safety cap triggered for {symbol}: actual notional ${actual_notional:,.2f} "
                f"exceeds max allowable ${max_allowed_notional:,.2f} (target: ${target_notional:,.2f}). "
                f"Skipping trade to protect account."
            )
            return 0.0, 0.0

        return amount, actual_notional

