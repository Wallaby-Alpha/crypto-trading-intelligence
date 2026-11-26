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
        Calculates contracts and total notional value for a de minimis order.
        Returns: (contracts, notional_usd)
        """
        target_notional = self.trade_margin_usd * self.default_leverage

        if target_notional < self.min_notional_usd:
            target_notional = self.min_notional_usd

        raw_contracts = target_notional / max(price, 1e-6)

        # Exchange precision & contract size rounding
        if market_meta:
            contract_size = market_meta.get("contractSize", 1.0) or 1.0
            precision_amount = market_meta.get("precision", {}).get("amount", 4)
            limits = market_meta.get("limits", {}).get("amount", {})
            min_amount = limits.get("min", 0.001) or 0.001

            # Adjust by contract size if linear/inverse
            effective_contracts = raw_contracts / contract_size
            step = 10 ** (-precision_amount) if isinstance(precision_amount, int) else float(precision_amount or 0.001)

            # Round down to precision step to avoid exchange rejection
            contracts = math.floor(effective_contracts / step) * step
            contracts = max(contracts, min_amount)
            contracts = round(contracts, precision_amount if isinstance(precision_amount, int) else 4)
        else:
            contracts = round(raw_contracts, 4)

        actual_notional = contracts * price
        return contracts, actual_notional

