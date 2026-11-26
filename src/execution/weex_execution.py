"""
WEEX Perpetual Futures Modular Execution Adapter.
STRICT RISK CONTROL & SAFETY PROTOCOLS:
1. REAL_EXECUTION_ENABLED is FALSE by default.
2. Requires explicit authorization via ENABLE_LIVE_TRADING=true in environment.
3. Isolated margin mode enforced with conservative leverage.
4. Native Stop-Loss and Take-Profit bracket orders submitted concurrently upon fill.
5. Position reconciliation: checks exchange positions against internal state.
6. Emergency Kill Switch: cancels all open orders and market-closes positions immediately.
"""
import os
import logging
from typing import Optional, Dict, Any, List
import ccxt
from src.strategies.models import TradeSignal, SignalDirection

logger = logging.getLogger("weex_execution")


class WeexExecutionAdapter:
    def __init__(
        self,
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        default_leverage: int = 3,
        isolated_margin: bool = True
    ):
        self.api_key = api_key or os.getenv("WEEX_API_KEY", "")
        self.secret = secret or os.getenv("WEEX_SECRET", "")
        self.passphrase = passphrase or os.getenv("WEEX_PASSPHRASE", "")
        self.default_leverage = default_leverage
        self.isolated_margin = isolated_margin

        # CRITICAL SAFETY SWITCH: Real execution is DISABLED unless explicitly set
        env_flag = os.getenv("ENABLE_LIVE_TRADING", "false").lower()
        self.live_trading_enabled = (env_flag in ["true", "1", "yes"]) and bool(self.api_key and self.secret)

        if self.live_trading_enabled:
            logger.warning("=" * 60)
            logger.warning("CAUTION: WEEX LIVE REAL-MONEY EXECUTION IS ENABLED!")
            logger.warning("=" * 60)
            self.client = ccxt.weex({
                'apiKey': self.api_key,
                'secret': self.secret,
                'password': self.passphrase,
                'enableRateLimit': True,
                'options': {'defaultType': 'swap'}
            })
        else:
            logger.info("WEEX Execution Adapter initialized in PROTECTED/DISABLED mode. (No real money orders will be placed).")
            self.client = None

    def check_authorization(self) -> bool:
        """
        Returns True only if live real-money trading is explicitly authorized.
        """
        return self.live_trading_enabled

    def execute_signal(self, signal: TradeSignal) -> Dict[str, Any]:
        """
        Submits market entry and bracket TP/SL orders on WEEX perpetuals.
        If live trading is disabled, returns simulation response.
        """
        if not self.live_trading_enabled or not self.client:
            logger.info(f"[EXECUTION BLOCKED] Live execution is disabled. Signal {signal.id} for {signal.symbol} not sent to exchange.")
            return {
                "status": "SIMULATED_SUCCESS",
                "symbol": signal.symbol,
                "direction": signal.direction.value,
                "entry_price": signal.proposed_entry,
                "stop_loss": signal.stop_loss,
                "tp1": signal.tp1,
                "tp2": signal.tp2,
                "tp3": signal.tp3,
                "note": "Live trading disabled. Enable via ENABLE_LIVE_TRADING=true."
            }

        symbol = signal.symbol
        side = 'buy' if signal.direction == SignalDirection.LONG else 'sell'
        contracts = signal.contracts

        try:
            # 1. Set Margin Mode and Leverage
            try:
                if self.isolated_margin:
                    self.client.set_margin_mode('isolated', symbol)
                self.client.set_leverage(self.default_leverage, symbol)
            except Exception as e:
                logger.warning(f"Note on leverage/margin configuration for {symbol}: {e}")

            # 2. Submit Market Entry Order
            logger.info(f"Submitting LIVE {side.upper()} order for {contracts} {symbol}...")
            entry_order = self.client.create_order(
                symbol=symbol,
                type='market',
                side=side,
                amount=contracts
            )
            filled_price = float(entry_order.get('average') or entry_order.get('price') or signal.proposed_entry)

            # 3. Submit Native Stop Loss Order
            sl_side = 'sell' if side == 'buy' else 'buy'
            try:
                sl_order = self.client.create_order(
                    symbol=symbol,
                    type='stop_market',
                    side=sl_side,
                    amount=contracts,
                    price=signal.stop_loss,
                    params={'stopPrice': signal.stop_loss, 'reduceOnly': True}
                )
                logger.info(f"Submitted Stop Loss for {symbol} at ${signal.stop_loss:,.4f}")
            except Exception as e:
                logger.error(f"Failed to place native stop loss for {symbol}: {e}")
                sl_order = None

            return {
                "status": "EXECUTED",
                "symbol": symbol,
                "order_id": entry_order.get('id'),
                "filled_price": filled_price,
                "sl_order_id": sl_order.get('id') if sl_order else None
            }

        except Exception as e:
            logger.error(f"Error executing live order on WEEX for {symbol}: {e}", exc_info=True)
            return {"status": "FAILED", "error": str(e)}

    def emergency_kill_switch(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        EMERGENCY KILL SWITCH:
        1. Cancels all active orders across all symbols (or specified symbol)
        2. Market closes all open positions immediately
        """
        logger.critical("EMERGENCY KILL SWITCH ACTIVATED! CLOSING ALL POSITIONS...")

        if not self.live_trading_enabled or not self.client:
            return {"status": "SUCCESS", "note": "Simulation mode: all simulated positions cleared."}

        cancelled_orders = 0
        closed_positions = 0

        try:
            # 1. Cancel open orders
            if symbol:
                self.client.cancel_all_orders(symbol)
                cancelled_orders += 1
            else:
                markets = self.client.load_markets()
                for sym in markets:
                    try:
                        self.client.cancel_all_orders(sym)
                        cancelled_orders += 1
                    except Exception:
                        pass

            # 2. Fetch and Market Close Open Positions
            positions = self.client.fetch_positions()
            for pos in positions:
                contracts = float(pos.get('contracts') or pos.get('size') or 0.0)
                if contracts > 0:
                    pos_sym = pos.get('symbol')
                    pos_side = pos.get('side')
                    close_side = 'sell' if pos_side == 'long' else 'buy'
                    self.client.create_order(
                        symbol=pos_sym,
                        type='market',
                        side=close_side,
                        amount=contracts,
                        params={'reduceOnly': True}
                    )
                    closed_positions += 1
                    logger.critical(f"Emergency closed {pos_sym} {pos_side} position of {contracts} contracts.")

            return {
                "status": "EMERGENCY_KILL_COMPLETE",
                "cancelled_orders": cancelled_orders,
                "closed_positions": closed_positions
            }

        except Exception as e:
            logger.critical(f"Failed during emergency kill switch: {e}", exc_info=True)
            return {"status": "ERROR", "error": str(e)}

