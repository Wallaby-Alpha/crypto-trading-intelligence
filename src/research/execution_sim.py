"""
Realistic Order Execution Simulator.
Strictly incorporates:
- Exchange taker fee: 0.05%
- Exchange maker fee: 0.02%
- Realistic market slippage: 0.02%
- Multi-tier partial profit taking:
  * TP1 (1.0R): takes off 33%, moves stop to Breakeven
  * TP2 (2.0R): takes off 33%, trails stop to TP1
  * TP3 (3.0R): takes off remaining 34%
- Zero look-ahead: Evaluates subsequent candles bar-by-bar checking Low/High bounds.
"""
from typing import List, Optional, Tuple
from src.core.models import Candle
from src.strategies.models import TradeSignal, SignalDirection, EntryMethod
from src.research.models import TradeRecord, TradeStatus, ExitReason


class ExecutionSimulator:
    def __init__(
        self,
        taker_fee_pct: float = 0.05,
        maker_fee_pct: float = 0.02,
        slippage_pct: float = 0.02,
        max_holding_candles: int = 120
    ):
        self.taker_fee_pct = taker_fee_pct
        self.maker_fee_pct = maker_fee_pct
        self.slippage_pct = slippage_pct
        self.max_holding_candles = max_holding_candles

    def simulate_trade(
        self,
        signal: TradeSignal,
        future_candles: List[Candle]
    ) -> Optional[TradeRecord]:
        """
        Simulates trade progression bar-by-bar across future candles.
        Never looks ahead: strictly processes each candle's High, Low, and Close in sequence.
        """
        if not future_candles:
            return None

        # 1. Calculate Entry Price with Slippage
        raw_entry = signal.proposed_entry
        slip_entry = raw_entry * (1.0 + (self.slippage_pct / 100.0) if signal.direction == SignalDirection.LONG else 1.0 - (self.slippage_pct / 100.0))

        risk_dist = abs(slip_entry - signal.stop_loss)
        if risk_dist <= 0:
            return None

        trade = TradeRecord(
            trade_id=f"TR-{signal.id}",
            signal_id=signal.id,
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            strategy_name=signal.strategy_name,
            direction=signal.direction,
            entry_timestamp=signal.timestamp,
            entry_datetime=signal.datetime,
            entry_price=slip_entry,
            stop_loss=signal.stop_loss,
            tp1=signal.tp1,
            tp2=signal.tp2,
            tp3=signal.tp3,
            initial_risk_usd=signal.position_size_usd * (risk_dist / slip_entry),
            position_size_usd=signal.position_size_usd,
            contracts=signal.contracts,
            signal_score=signal.score.total_score,
            signal_category=signal.score.category
        )

        current_sl = signal.stop_loss
        tp1_hit = False
        tp2_hit = False
        accumulated_r = 0.0
        active_fraction = 1.0

        entry_fee = trade.position_size_usd * (self.taker_fee_pct / 100.0)
        total_fees = entry_fee
        total_slippage = abs(slip_entry - raw_entry) * trade.contracts

        for bar_idx, candle in enumerate(future_candles):
            trade.holding_period_candles = bar_idx + 1

            # --- LONG SIMULATION ---
            if signal.direction == SignalDirection.LONG:
                # 1. Check Stop Loss
                if candle.low <= current_sl:
                    slip_exit = current_sl * (1.0 - (self.slippage_pct / 100.0))
                    total_fees += (active_fraction * trade.position_size_usd) * (self.taker_fee_pct / 100.0)
                    total_slippage += abs(current_sl - slip_exit) * (active_fraction * trade.contracts)

                    r_loss = (slip_exit - slip_entry) / risk_dist
                    accumulated_r += active_fraction * r_loss

                    trade.exit_timestamp = candle.timestamp
                    trade.exit_datetime = candle.datetime
                    trade.exit_price = slip_exit
                    trade.status = TradeStatus.CLOSED_STOP if not tp1_hit else TradeStatus.CLOSED_BREAKEVEN
                    trade.exit_reason = ExitReason.STOP_LOSS if not tp1_hit else ExitReason.BREAKEVEN
                    break

                # 2. Check TP1 (1.0R) -> Close 33%, move SL to Breakeven
                if not tp1_hit and candle.high >= signal.tp1:
                    tp1_hit = True
                    accumulated_r += 0.33 * 1.0
                    active_fraction -= 0.33
                    current_sl = slip_entry  # Move stop to Breakeven
                    total_fees += (0.33 * trade.position_size_usd) * (self.maker_fee_pct / 100.0)

                # 3. Check TP2 (2.0R) -> Close 33%, trail SL to TP1
                if tp1_hit and not tp2_hit and candle.high >= signal.tp2:
                    tp2_hit = True
                    accumulated_r += 0.33 * 2.0
                    active_fraction -= 0.33
                    current_sl = signal.tp1  # Trail stop to TP1
                    total_fees += (0.33 * trade.position_size_usd) * (self.maker_fee_pct / 100.0)

                # 4. Check TP3 (3.0R) -> Close remaining 34%
                if tp2_hit and candle.high >= signal.tp3:
                    accumulated_r += active_fraction * 3.0
                    total_fees += (active_fraction * trade.position_size_usd) * (self.maker_fee_pct / 100.0)
                    trade.exit_timestamp = candle.timestamp
                    trade.exit_datetime = candle.datetime
                    trade.exit_price = signal.tp3
                    trade.status = TradeStatus.CLOSED_TP3_FULL
                    trade.exit_reason = ExitReason.TAKE_PROFIT_3
                    break

            # --- SHORT SIMULATION ---
            else:
                # 1. Check Stop Loss
                if candle.high >= current_sl:
                    slip_exit = current_sl * (1.0 + (self.slippage_pct / 100.0))
                    total_fees += (active_fraction * trade.position_size_usd) * (self.taker_fee_pct / 100.0)
                    total_slippage += abs(slip_exit - current_sl) * (active_fraction * trade.contracts)

                    r_loss = (slip_entry - slip_exit) / risk_dist
                    accumulated_r += active_fraction * r_loss

                    trade.exit_timestamp = candle.timestamp
                    trade.exit_datetime = candle.datetime
                    trade.exit_price = slip_exit
                    trade.status = TradeStatus.CLOSED_STOP if not tp1_hit else TradeStatus.CLOSED_BREAKEVEN
                    trade.exit_reason = ExitReason.STOP_LOSS if not tp1_hit else ExitReason.BREAKEVEN
                    break

                # 2. Check TP1 (1.0R)
                if not tp1_hit and candle.low <= signal.tp1:
                    tp1_hit = True
                    accumulated_r += 0.33 * 1.0
                    active_fraction -= 0.33
                    current_sl = slip_entry  # Breakeven
                    total_fees += (0.33 * trade.position_size_usd) * (self.maker_fee_pct / 100.0)

                # 3. Check TP2 (2.0R)
                if tp1_hit and not tp2_hit and candle.low <= signal.tp2:
                    tp2_hit = True
                    accumulated_r += 0.33 * 2.0
                    active_fraction -= 0.33
                    current_sl = signal.tp1
                    total_fees += (0.33 * trade.position_size_usd) * (self.maker_fee_pct / 100.0)

                # 4. Check TP3 (3.0R)
                if tp2_hit and candle.low <= signal.tp3:
                    accumulated_r += active_fraction * 3.0
                    total_fees += (active_fraction * trade.position_size_usd) * (self.maker_fee_pct / 100.0)
                    trade.exit_timestamp = candle.timestamp
                    trade.exit_datetime = candle.datetime
                    trade.exit_price = signal.tp3
                    trade.status = TradeStatus.CLOSED_TP3_FULL
                    trade.exit_reason = ExitReason.TAKE_PROFIT_3
                    break

            # 5. Check Max Holding Period Timeout
            if bar_idx >= self.max_holding_candles:
                exit_p = candle.close
                dir_mult = 1.0 if signal.direction == SignalDirection.LONG else -1.0
                r_rem = dir_mult * (exit_p - slip_entry) / risk_dist
                accumulated_r += active_fraction * r_rem
                total_fees += (active_fraction * trade.position_size_usd) * (self.taker_fee_pct / 100.0)

                trade.exit_timestamp = candle.timestamp
                trade.exit_datetime = candle.datetime
                trade.exit_price = exit_p
                trade.status = TradeStatus.CLOSED_TIMEOUT
                trade.exit_reason = ExitReason.TIMEOUT
                break

        # Calculate final PnL and R multiple
        trade.r_multiple = round(accumulated_r, 2)
        trade.gross_pnl_usd = round(trade.initial_risk_usd * accumulated_r, 2)
        trade.commission_paid = round(total_fees, 2)
        trade.slippage_cost = round(total_slippage, 2)
        trade.net_pnl_usd = round(trade.gross_pnl_usd - trade.commission_paid, 2)

        return trade

