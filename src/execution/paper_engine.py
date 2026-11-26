"""
Live Paper Trading & Execution Simulator Engine.
Continuously runs in real-time alongside market data:
- Fills signals with realistic fees (0.05%) and slippage (0.02%)
- Tracks open positions, margin, mark price, and unrealized PnL
- Multi-stage exits: TP1 (33%), TP2 (33%), TP3 (34%)
- Dynamic breakeven trailing stop upon TP1 fill
- Dispatches lifecycle events to Telegram
- Maintains portfolio equity curve and drawdown stats
"""
import uuid
import time
import logging
from typing import Dict, List, Optional, Any
from src.core.models import Candle
from src.strategies.models import TradeSignal, SignalDirection
from src.execution.models import PositionRecord, PositionStatus
from src.notifications.telegram_bot import TelegramNotifier

logger = logging.getLogger("paper_engine")


class PaperTradingEngine:
    def __init__(
        self,
        initial_capital_usd: float = 10000.0,
        taker_fee_pct: float = 0.0005,      # 0.05%
        slippage_pct: float = 0.0002,       # 0.02%
        max_open_positions: int = 5,
        telegram_notifier: Optional[TelegramNotifier] = None
    ):
        self.initial_capital = initial_capital_usd
        self.capital = initial_capital_usd
        self.taker_fee = taker_fee_pct
        self.slippage = slippage_pct
        self.max_open_positions = max_open_positions
        self.notifier = telegram_notifier

        # Portfolio state
        self.open_positions: Dict[str, PositionRecord] = {}
        self.closed_positions: List[PositionRecord] = []
        self.peak_equity = initial_capital_usd
        self.max_drawdown_usd = 0.0
        self.max_drawdown_pct = 0.0

    @property
    def current_equity(self) -> float:
        unrealized = sum(p.unrealized_pnl_usd for p in self.open_positions.values())
        return self.capital + unrealized

    def open_position_from_signal(self, signal: TradeSignal) -> Optional[PositionRecord]:
        """
        Creates and executes a new paper position from an incoming trade signal.
        """
        if len(self.open_positions) >= self.max_open_positions:
            logger.info(f"Max open positions reached ({self.max_open_positions}). Skipping {signal.symbol}.")
            return None

        # Check if already holding position in same symbol
        for pos in self.open_positions.values():
            if pos.symbol == signal.symbol:
                logger.info(f"Already holding position in {signal.symbol}. Skipping.")
                return None

        # Apply entry slippage
        if signal.direction == SignalDirection.LONG:
            filled_entry = signal.proposed_entry * (1.0 + self.slippage)
        else:
            filled_entry = signal.proposed_entry * (1.0 - self.slippage)

        # Calculate contracts based on 1% portfolio risk
        risk_per_contract = abs(filled_entry - signal.stop_loss)
        if risk_per_contract <= 0:
            return None

        risk_capital = self.capital * 0.01  # 1% risk
        contracts = risk_capital / risk_per_contract
        position_notional = contracts * filled_entry
        leverage = 3.0
        margin_required = position_notional / leverage

        if margin_required > self.capital * 0.5:
            # Cap position size to 50% max margin allocation
            contracts = (self.capital * 0.5 * leverage) / filled_entry
            position_notional = contracts * filled_entry
            margin_required = position_notional / leverage

        # Taker fee
        fee = position_notional * self.taker_fee
        self.capital -= fee

        pos_id = f"pos_{uuid.uuid4().hex[:10]}"
        pos = PositionRecord(
            position_id=pos_id,
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=signal.direction,
            status=PositionStatus.OPEN,
            entry_time=int(time.time() * 1000),
            entry_price=filled_entry,
            current_price=filled_entry,
            stop_loss=signal.stop_loss,
            tp1=signal.tp1,
            tp2=signal.tp2,
            tp3=signal.tp3,
            initial_contracts=contracts,
            remaining_contracts=contracts,
            allocated_margin_usd=margin_required,
            leverage=leverage,
            total_fees_usd=fee
        )

        self.open_positions[pos_id] = pos
        logger.info(f"[PAPER FILL] {signal.direction.value} {contracts:.4f} {signal.symbol} @ ${filled_entry:,.4f}")

        # Dispatch Telegram lifecycle notification
        if self.notifier:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.notifier.notify_lifecycle(
                        signal_id=signal.id,
                        symbol=signal.symbol,
                        direction=signal.direction.value,
                        event_type="TRIGGERED",
                        details=f"Paper Entry filled at ${filled_entry:,.4f}. Pos Size: ${position_notional:,.0f}. Initial SL: ${signal.stop_loss:,.4f}"
                    ))
            except Exception:
                pass

        return pos

    def update_positions(self, candle: Candle):
        """
        Updates open positions against the incoming candle:
        - Evaluates Stop-Loss
        - Evaluates TP1, TP2, TP3
        - Trailing Breakeven logic
        - Unrealized PnL calculation
        """
        symbol = candle.symbol
        positions_to_close = []

        for pos_id, pos in list(self.open_positions.items()):
            if pos.symbol != symbol:
                continue

            pos.current_price = candle.close

            if pos.direction == SignalDirection.LONG:
                # 1. Check Stop Loss
                if candle.low <= pos.stop_loss:
                    exit_price = pos.stop_loss * (1.0 - self.slippage)
                    fee = (pos.remaining_contracts * exit_price) * self.taker_fee
                    loss = (exit_price - pos.entry_price) * pos.remaining_contracts - fee
                    pos.realized_pnl_usd += loss
                    pos.total_fees_usd += fee
                    self.capital += loss
                    pos.status = PositionStatus.CLOSED
                    pos.exit_price = exit_price
                    pos.exit_time = candle.timestamp
                    pos.exit_reason = "STOP_LOSS"
                    positions_to_close.append(pos_id)
                    logger.info(f"[PAPER STOP] LONG {pos.symbol} hit SL at ${exit_price:,.4f} | Loss: ${loss:.2f}")
                    continue

                # 2. Check Take Profit 1 (33% exit + SL to Breakeven)
                if not pos.tp1_hit and candle.high >= pos.tp1:
                    pos.tp1_hit = True
                    close_qty = pos.initial_contracts * 0.33
                    exit_price = pos.tp1 * (1.0 - self.slippage)
                    gain = (exit_price - pos.entry_price) * close_qty
                    fee = (close_qty * exit_price) * self.taker_fee
                    pos.realized_pnl_usd += (gain - fee)
                    pos.total_fees_usd += fee
                    self.capital += (gain - fee)
                    pos.remaining_contracts -= close_qty
                    # Move SL to Breakeven
                    pos.stop_loss = pos.entry_price
                    pos.status = PositionStatus.PARTIALLY_CLOSED
                    logger.info(f"[PAPER TP1] LONG {pos.symbol} hit TP1 ${exit_price:,.4f} | Closed 33% | SL moved to Breakeven ${pos.stop_loss:,.4f}")

                # 3. Check Take Profit 2 (33% exit)
                if pos.tp1_hit and not pos.tp2_hit and candle.high >= pos.tp2:
                    pos.tp2_hit = True
                    close_qty = pos.initial_contracts * 0.33
                    exit_price = pos.tp2 * (1.0 - self.slippage)
                    gain = (exit_price - pos.entry_price) * close_qty
                    fee = (close_qty * exit_price) * self.taker_fee
                    pos.realized_pnl_usd += (gain - fee)
                    pos.total_fees_usd += fee
                    self.capital += (gain - fee)
                    pos.remaining_contracts -= close_qty
                    logger.info(f"[PAPER TP2] LONG {pos.symbol} hit TP2 ${exit_price:,.4f} | Closed 33%")

                # 4. Check Take Profit 3 (Remaining 34% runner exit)
                if pos.tp2_hit and not pos.tp3_hit and candle.high >= pos.tp3:
                    pos.tp3_hit = True
                    close_qty = pos.remaining_contracts
                    exit_price = pos.tp3 * (1.0 - self.slippage)
                    gain = (exit_price - pos.entry_price) * close_qty
                    fee = (close_qty * exit_price) * self.taker_fee
                    pos.realized_pnl_usd += (gain - fee)
                    pos.total_fees_usd += fee
                    self.capital += (gain - fee)
                    pos.remaining_contracts = 0.0
                    pos.status = PositionStatus.CLOSED
                    pos.exit_price = exit_price
                    pos.exit_time = candle.timestamp
                    pos.exit_reason = "TAKE_PROFIT_3"
                    positions_to_close.append(pos_id)
                    logger.info(f"[PAPER TP3] LONG {pos.symbol} hit TP3 ${exit_price:,.4f} | Position fully closed")
                    continue

                # Calculate current unrealized PnL
                pos.unrealized_pnl_usd = (candle.close - pos.entry_price) * pos.remaining_contracts

            else:
                # SHORT POSITION
                # 1. Check Stop Loss
                if candle.high >= pos.stop_loss:
                    exit_price = pos.stop_loss * (1.0 + self.slippage)
                    fee = (pos.remaining_contracts * exit_price) * self.taker_fee
                    loss = (pos.entry_price - exit_price) * pos.remaining_contracts - fee
                    pos.realized_pnl_usd += loss
                    pos.total_fees_usd += fee
                    self.capital += loss
                    pos.status = PositionStatus.CLOSED
                    pos.exit_price = exit_price
                    pos.exit_time = candle.timestamp
                    pos.exit_reason = "STOP_LOSS"
                    positions_to_close.append(pos_id)
                    logger.info(f"[PAPER STOP] SHORT {pos.symbol} hit SL at ${exit_price:,.4f} | Loss: ${loss:.2f}")
                    continue

                # 2. Check Take Profit 1
                if not pos.tp1_hit and candle.low <= pos.tp1:
                    pos.tp1_hit = True
                    close_qty = pos.initial_contracts * 0.33
                    exit_price = pos.tp1 * (1.0 + self.slippage)
                    gain = (pos.entry_price - exit_price) * close_qty
                    fee = (close_qty * exit_price) * self.taker_fee
                    pos.realized_pnl_usd += (gain - fee)
                    pos.total_fees_usd += fee
                    self.capital += (gain - fee)
                    pos.remaining_contracts -= close_qty
                    pos.stop_loss = pos.entry_price
                    pos.status = PositionStatus.PARTIALLY_CLOSED
                    logger.info(f"[PAPER TP1] SHORT {pos.symbol} hit TP1 ${exit_price:,.4f} | Closed 33% | SL to Breakeven")

                # 3. Check Take Profit 2
                if pos.tp1_hit and not pos.tp2_hit and candle.low <= pos.tp2:
                    pos.tp2_hit = True
                    close_qty = pos.initial_contracts * 0.33
                    exit_price = pos.tp2 * (1.0 + self.slippage)
                    gain = (pos.entry_price - exit_price) * close_qty
                    fee = (close_qty * exit_price) * self.taker_fee
                    pos.realized_pnl_usd += (gain - fee)
                    pos.total_fees_usd += fee
                    self.capital += (gain - fee)
                    pos.remaining_contracts -= close_qty
                    logger.info(f"[PAPER TP2] SHORT {pos.symbol} hit TP2 ${exit_price:,.4f} | Closed 33%")

                # 4. Check Take Profit 3
                if pos.tp2_hit and not pos.tp3_hit and candle.low <= pos.tp3:
                    pos.tp3_hit = True
                    close_qty = pos.remaining_contracts
                    exit_price = pos.tp3 * (1.0 + self.slippage)
                    gain = (pos.entry_price - exit_price) * close_qty
                    fee = (close_qty * exit_price) * self.taker_fee
                    pos.realized_pnl_usd += (gain - fee)
                    pos.total_fees_usd += fee
                    self.capital += (gain - fee)
                    pos.remaining_contracts = 0.0
                    pos.status = PositionStatus.CLOSED
                    pos.exit_price = exit_price
                    pos.exit_time = candle.timestamp
                    pos.exit_reason = "TAKE_PROFIT_3"
                    positions_to_close.append(pos_id)
                    logger.info(f"[PAPER TP3] SHORT {pos.symbol} hit TP3 ${exit_price:,.4f} | Position fully closed")
                    continue

                pos.unrealized_pnl_usd = (pos.entry_price - candle.close) * pos.remaining_contracts

        # Move closed positions
        for pid in positions_to_close:
            p = self.open_positions.pop(pid)
            self.closed_positions.append(p)

        # Track Drawdown
        eq = self.current_equity
        if eq > self.peak_equity:
            self.peak_equity = eq
        dd = self.peak_equity - eq
        if dd > self.max_drawdown_usd:
            self.max_drawdown_usd = dd
            self.max_drawdown_pct = (dd / self.peak_equity) * 100.0 if self.peak_equity > 0 else 0.0

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Returns full portfolio accounting metrics.
        """
        eq = self.current_equity
        unrealized = sum(p.unrealized_pnl_usd for p in self.open_positions.values())
        realized = sum(p.realized_pnl_usd for p in self.closed_positions)
        total_pnl = (eq - self.initial_capital)
        total_pct = (total_pnl / self.initial_capital) * 100.0

        return {
            "initial_capital_usd": self.initial_capital,
            "current_equity_usd": round(eq, 2),
            "cash_balance_usd": round(self.capital, 2),
            "unrealized_pnl_usd": round(unrealized, 2),
            "realized_pnl_usd": round(realized, 2),
            "total_return_usd": round(total_pnl, 2),
            "total_return_pct": round(total_pct, 2),
            "open_positions_count": len(self.open_positions),
            "closed_trades_count": len(self.closed_positions),
            "peak_equity_usd": round(self.peak_equity, 2),
            "max_drawdown_usd": round(self.max_drawdown_usd, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2)
        }

