"""
Live WEEX Autonomous Trading Bot Controller.
Operates 24/7 on DigitalOcean Droplet:
1. Monitored Universe: Top liquid perpetual futures (BTC, ETH, SOL, SUI, DOGE, AVAX, LINK, NEAR, ADA, XRP).
2. Strategy Suite: Strictly uses validated alpha drivers:
   - Trend Pullback Sweep (ICT Trend-Aligned Reclaim)
   - Swing Failure Pattern Range Trap (SFP Reclaim)
3. Dynamic Higher Timeframe (HTF) Trend Bias (1H EMA20/EMA50).
4. De Minimis Position Governance: $10 - $25 margin, 2x-3x leverage, max 2 concurrent positions.
5. Autonomous Trade Management: Moves Stop Loss to Breakeven when TP1 is hit.
6. Full Telegram Telemetry: Entries, TP1 hits, SL triggers, and Daily PnL.
"""
import os
import sys
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from src.core.models import Candle
from src.core.database import DatabaseManager
from src.adapters.weex import WeexAdapter
from src.events.event_engine import EventEngine
from src.indicators.cvd import CVDEngine
from src.indicators.vwap import VWAPEngine
from src.indicators.volume_profile import VolumeProfileEngine
from src.indicators.volatility import VolatilityEngine
from src.strategies.strategy_coordinator import StrategyCoordinator
from src.strategies.trend_pullback_sweep import TrendPullbackSweepStrategy
from src.strategies.swing_failure_range import SwingFailureRangeTrapStrategy
from src.strategies.models import TradeSignal, SignalDirection
from src.execution.weex_execution import WeexExecutionAdapter
from src.notifications.telegram_bot import TelegramNotifier
from src.bot.risk_governor import RiskGovernor

logger = logging.getLogger("live_bot")


class ActiveLivePosition:
    def __init__(
        self,
        symbol: str,
        direction: SignalDirection,
        entry_price: float,
        stop_loss: float,
        tp1: float,
        tp2: float,
        tp3: float,
        contracts: float,
        notional_usd: float,
        order_id: Optional[str] = None,
        sl_order_id: Optional[str] = None,
        tp_order_id: Optional[str] = None
    ):
        self.symbol = symbol
        self.direction = direction
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.tp1 = tp1
        self.tp2 = tp2
        self.tp3 = tp3
        self.contracts = contracts
        self.notional_usd = notional_usd
        self.order_id = order_id
        self.sl_order_id = sl_order_id
        self.tp_order_id = tp_order_id
        self.tp1_hit: bool = False
        self.tp2_hit: bool = False
        self.entry_time = time.time()


class LiveTradingBot:
    def __init__(
        self,
        monitored_symbols: Optional[List[str]] = None,
        db_manager: Optional[DatabaseManager] = None,
        poll_interval_seconds: int = 20
    ):
        self.symbols = monitored_symbols or [
            "BTC/USDT:USDT",
            "ETH/USDT:USDT",
            "SOL/USDT:USDT",
            "DOGE/USDT:USDT",
            "SUI/USDT:USDT",
            "AVAX/USDT:USDT",
            "LINK/USDT:USDT",
            "NEAR/USDT:USDT",
            "ADA/USDT:USDT",
            "XRP/USDT:USDT"
        ]
        self.poll_interval = poll_interval_seconds
        self.is_running = False

        # Database & Exchange Adapters
        self.db = db_manager or DatabaseManager()
        self.weex_data = WeexAdapter()
        self.weex_exec = WeexExecutionAdapter()
        self.risk_governor = RiskGovernor()

        # Indicators & Event Engine
        self.cvd_engine = CVDEngine()
        self.vwap_engine = VWAPEngine()
        self.vp_engine = VolumeProfileEngine()
        self.vol_engine = VolatilityEngine()
        self.event_engine = EventEngine(db_manager=self.db)

        # Strategies: Exclusively activate the 2 verified alpha models
        self.coordinator = StrategyCoordinator(db_manager=self.db)
        self.coordinator.strategies = {
            "trend_pullback_sweep": TrendPullbackSweepStrategy(is_enabled=True),
            "swing_failure_range": SwingFailureRangeTrapStrategy(is_enabled=True)
        }

        # Telegram Notifier
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.telegram = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)

        # Active Positions State: symbol -> ActiveLivePosition
        self.active_positions: Dict[str, ActiveLivePosition] = {}
        self.market_metadata: Dict[str, Any] = {}

    async def initialize(self):
        """Loads exchange market limits and checks credentials."""
        logger.info("Initializing Live WEEX Trading Bot...")
        try:
            markets = await asyncio.to_thread(self.weex_data.load_markets)
            for sym, m in markets.items():
                self.market_metadata[sym] = m
            logger.info(f"Loaded metadata for {len(self.market_metadata)} markets on WEEX.")
        except Exception as e:
            logger.warning(f"Could not load full market metadata: {e}")

        balance_extra = ""
        if self.weex_exec.check_authorization():
            bal = await asyncio.to_thread(self.weex_exec.get_futures_balance)
            if bal.get("status") == "SUCCESS":
                u_free = bal.get("usdt_free", 0.0)
                balance_extra = f"\n• <b>Futures Balance:</b> <code>${u_free:,.2f} USDT</code>"
                if u_free < self.risk_governor.trade_margin_usd:
                    balance_extra += f"\n⚠️ <i>NOTE: Contract balance is low. Ensure USDT is transferred from Spot to USDT-M Futures.</i>"
            elif bal.get("status") == "ERROR":
                balance_extra = f"\n⚠️ <b>Balance API Error:</b> <code>{bal.get('error')}</code>"

        # Telegram startup greeting
        mode_str = "LIVE REAL-MONEY" if self.weex_exec.check_authorization() else "PAPER / DRY-RUN"
        msg = (
            f"🤖 <b>WEEX BOT ONLINE</b>\n"
            f"• <b>Mode:</b> <code>{mode_str}</code>\n"
            f"• <b>Margin/Trade:</b> <code>${self.risk_governor.trade_margin_usd:,.2f}</code>\n"
            f"• <b>Max Positions:</b> <code>{self.risk_governor.max_open_positions}</code>\n"
            f"• <b>Leverage:</b> <code>{self.risk_governor.default_leverage}x</code>\n"
            f"• <b>Monitored:</b> {len(self.symbols)} liquid markets"
            f"{balance_extra}"
        )
        await self.telegram.send_message(msg)

    async def calculate_htf_trend(self, symbol: str) -> str:
        """Calculates 1H EMA20 vs EMA50 trend direction with zero look-ahead bias."""
        try:
            candles_1h = await asyncio.to_thread(self.weex_data.fetch_ohlcv, symbol, timeframe="1h", limit=60)
            if len(candles_1h) < 50:
                return "NEUTRAL"

            import pandas as pd
            closes = pd.Series([c.close for c in candles_1h])
            ema20 = closes.ewm(span=20, adjust=False).mean().iloc[-1]
            ema50 = closes.ewm(span=50, adjust=False).mean().iloc[-1]
            last_close = candles_1h[-1].close

            if last_close > ema50 and ema20 > ema50:
                return "BULLISH"
            elif last_close < ema50 and ema20 < ema50:
                return "BEARISH"
            return "NEUTRAL"
        except Exception as e:
            logger.warning(f"Error computing HTF trend for {symbol}: {e}")
            return "NEUTRAL"

    async def scan_symbol(self, symbol: str):
        """Scans a single symbol for qualified orderflow setups."""
        try:
            # Check if symbol already has an open position
            if symbol in self.active_positions:
                return

            # Check Risk Governor capacity
            can_open, reason = self.risk_governor.can_open_position(len(self.active_positions))
            if not can_open:
                return

            # Fetch recent 15m candles
            candles_15m = await asyncio.to_thread(self.weex_data.fetch_ohlcv, symbol, timeframe="15m", limit=60)
            if len(candles_15m) < 35:
                return

            # Real-time indicators
            cvd_bars = self.cvd_engine.estimate_from_candles(candles_15m)
            vwap_bands = self.vwap_engine.calculate_anchored_vwap(candles_15m)
            vp = self.vp_engine.compute_profile(candles_15m[-50:])
            atr_series = self.vol_engine.calculate_atr(candles_15m)
            atr = atr_series[-1] if atr_series else max(0.01, candles_15m[-1].high - candles_15m[-1].low)

            current_candle = candles_15m[-1]
            current_price = current_candle.close

            # Compute HTF Trend
            htf_trend = await self.calculate_htf_trend(symbol)
            htf_aligned = (htf_trend != "NEUTRAL")

            # Detect Events & Evaluate Strategies
            bundle = self.event_engine.analyze_candle(
                candles=candles_15m,
                cvd_bars=cvd_bars,
                oi_metrics=None,
                vwap_bands=vwap_bands,
                vp_result=vp,
                atr_value=atr
            )

            signals = self.coordinator.evaluate_bundle(
                bundle=bundle,
                current_price=current_price,
                atr_value=atr,
                funding_rate=None,
                htf_aligned=htf_aligned,
                htf_trend=htf_trend
            )

            if not signals:
                return

            # Select top scoring setup
            best_signal = max(signals, key=lambda s: s.score.total_score)
            if best_signal.score.total_score < 65.0:
                return

            # Sizing via De Minimis Risk Governor
            meta = self.market_metadata.get(symbol)
            contracts, notional = self.risk_governor.calculate_position_size(symbol, current_price, meta)
            if contracts <= 0 or notional <= 0:
                logger.info(f"Skipping {symbol}: sizing safety bounds skipped trade.")
                return

            best_signal.contracts = contracts
            best_signal.position_size_usd = notional

            logger.info(
                f"🎯 [QUALIFIED SETUP] {best_signal.direction.value} {symbol} | "
                f"Strategy: {best_signal.strategy_name} | Score: {best_signal.score.total_score:.1f} | "
                f"Size: {contracts} contracts (${notional:,.2f})"
            )

            # Execute order via Adapter
            res = self.weex_exec.execute_signal(best_signal)
            order_id = res.get("order_id")
            sl_order_id = res.get("sl_order_id")
            tp_order_id = res.get("tp_order_id")

            if res.get("status") == "FAILED":
                err_msg = res.get("error", "Unknown exchange error")
                logger.error(f"❌ LIVE EXECUTION FAILED on WEEX for {symbol}: {err_msg}")
                try:
                    await self.telegram.send_message(
                        f"⚠️ <b>WEEX LIVE ORDER REJECTED!</b>\n"
                        f"• <b>Market:</b> <code>{symbol}</code>\n"
                        f"• <b>Error:</b> <code>{err_msg}</code>\n\n"
                        f"<i>Check futures account balance or API key permissions.</i>"
                    )
                except Exception as te:
                    logger.warning(f"Failed to send failure alert: {te}")

            # Register Active Position
            self.active_positions[symbol] = ActiveLivePosition(
                symbol=symbol,
                direction=best_signal.direction,
                entry_price=res.get("filled_price", best_signal.proposed_entry),
                stop_loss=best_signal.stop_loss,
                tp1=best_signal.tp1,
                tp2=best_signal.tp2,
                tp3=best_signal.tp3,
                contracts=contracts,
                notional_usd=notional,
                order_id=order_id,
                sl_order_id=sl_order_id,
                tp_order_id=tp_order_id
            )

            # Dispatch Telegram Alert
            alert_text = self.telegram.format_signal_alert(best_signal)
            await self.telegram.send_message(alert_text)

        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}", exc_info=True)

    async def monitor_positions(self):
        """Monitors open positions, trails Stop Loss to Breakeven at TP1, and handles exits."""
        if not self.active_positions:
            return

        symbols_to_remove = []

        for symbol, pos in self.active_positions.items():
            try:
                # Fetch current ticker price
                ticker = await asyncio.to_thread(self.weex_data.fetch_ticker, symbol)
                if not ticker:
                    continue

                curr_p = float(ticker.last if hasattr(ticker, "last") else (ticker.get("last") or 0.0))
                if not curr_p:
                    continue

                # Check Long Position
                if pos.direction == SignalDirection.LONG:
                    # 1. Stop Loss Hit
                    if curr_p <= pos.stop_loss:
                        pnl = (pos.stop_loss - pos.entry_price) * pos.contracts
                        logger.warning(f"🛑 [STOP LOSS HIT] {symbol} Long at ${curr_p:,.4f} | PnL: ${pnl:,.2f}")
                        # Market close on exchange to guarantee flat position
                        await asyncio.to_thread(self.weex_exec.close_position, symbol, pos.contracts, pos.direction)
                        self.risk_governor.record_trade_result(pnl)
                        symbols_to_remove.append(symbol)
                        await self.telegram.send_message(
                            f"🛑 <b>STOP LOSS TRIGGERED</b>\n"
                            f"• Asset: <code>{symbol}</code> LONG\n"
                            f"• Exit: <code>${curr_p:,.4f}</code>\n"
                            f"• Realized PnL: <b>${pnl:,.2f}</b>"
                        )
                        continue

                    # 2. TP1 Hit -> Move Stop to Breakeven
                    if not pos.tp1_hit and curr_p >= pos.tp1:
                        pos.tp1_hit = True
                        pos.stop_loss = pos.entry_price  # Breakeven
                        logger.info(f"💰 [TP1 HIT] {symbol} reached ${pos.tp1:,.4f}. Stop loss moved to Breakeven: ${pos.stop_loss:,.4f}")
                        # Update stop loss on WEEX exchange to Breakeven
                        await asyncio.to_thread(self.weex_exec.update_stop_loss, symbol, pos.contracts, pos.direction, pos.stop_loss)
                        await self.telegram.send_message(
                            f"💰 <b>TAKE PROFIT 1 (1.0R) HIT!</b>\n"
                            f"• Asset: <code>{symbol}</code> LONG\n"
                            f"• Target Reached: <code>${pos.tp1:,.4f}</code>\n"
                            f"• <b>Action:</b> Stop Loss moved to BREAKEVEN (<code>${pos.entry_price:,.4f}</code>) on exchange. Trade is now risk-free! 🛡️"
                        )

                    # 3. TP3 Full Exit Hit
                    if curr_p >= pos.tp3:
                        pnl = (pos.tp3 - pos.entry_price) * pos.contracts
                        logger.info(f"🏆 [TP3 FULL HIT] {symbol} Long reached final target ${pos.tp3:,.4f} | PnL: ${pnl:,.2f}")
                        # Market close on exchange to guarantee flat position
                        await asyncio.to_thread(self.weex_exec.close_position, symbol, pos.contracts, pos.direction)
                        self.risk_governor.record_trade_result(pnl)
                        symbols_to_remove.append(symbol)
                        await self.telegram.send_message(
                            f"🏆 <b>TP3 FINAL RUNNER EXECUTED!</b>\n"
                            f"• Asset: <code>{symbol}</code> LONG\n"
                            f"• Exit: <code>${curr_p:,.4f}</code>\n"
                            f"• Realized PnL: <b>+${pnl:,.2f}</b> 🎉"
                        )
                        continue

                # Check Short Position
                else:
                    # 1. Stop Loss Hit
                    if curr_p >= pos.stop_loss:
                        pnl = (pos.entry_price - pos.stop_loss) * pos.contracts
                        logger.warning(f"🛑 [STOP LOSS HIT] {symbol} Short at ${curr_p:,.4f} | PnL: ${pnl:,.2f}")
                        # Market close on exchange to guarantee flat position
                        await asyncio.to_thread(self.weex_exec.close_position, symbol, pos.contracts, pos.direction)
                        self.risk_governor.record_trade_result(pnl)
                        symbols_to_remove.append(symbol)
                        await self.telegram.send_message(
                            f"🛑 <b>STOP LOSS TRIGGERED</b>\n"
                            f"• Asset: <code>{symbol}</code> SHORT\n"
                            f"• Exit: <code>${curr_p:,.4f}</code>\n"
                            f"• Realized PnL: <b>${pnl:,.2f}</b>"
                        )
                        continue

                    # 2. TP1 Hit -> Move Stop to Breakeven
                    if not pos.tp1_hit and curr_p <= pos.tp1:
                        pos.tp1_hit = True
                        pos.stop_loss = pos.entry_price  # Breakeven
                        logger.info(f"💰 [TP1 HIT] {symbol} reached ${pos.tp1:,.4f}. Stop loss moved to Breakeven: ${pos.stop_loss:,.4f}")
                        # Update stop loss on WEEX exchange to Breakeven
                        await asyncio.to_thread(self.weex_exec.update_stop_loss, symbol, pos.contracts, pos.direction, pos.stop_loss)
                        await self.telegram.send_message(
                            f"💰 <b>TAKE PROFIT 1 (1.0R) HIT!</b>\n"
                            f"• Asset: <code>{symbol}</code> SHORT\n"
                            f"• Target Reached: <code>${pos.tp1:,.4f}</code>\n"
                            f"• <b>Action:</b> Stop Loss moved to BREAKEVEN (<code>${pos.entry_price:,.4f}</code>) on exchange. Trade is now risk-free! 🛡️"
                        )

                    # 3. TP3 Full Exit Hit
                    if curr_p <= pos.tp3:
                        pnl = (pos.entry_price - pos.tp3) * pos.contracts
                        logger.info(f"🏆 [TP3 FULL HIT] {symbol} Short reached final target ${pos.tp3:,.4f} | PnL: ${pnl:,.2f}")
                        # Market close on exchange to guarantee flat position
                        await asyncio.to_thread(self.weex_exec.close_position, symbol, pos.contracts, pos.direction)
                        self.risk_governor.record_trade_result(pnl)
                        symbols_to_remove.append(symbol)
                        await self.telegram.send_message(
                            f"🏆 <b>TP3 FINAL RUNNER EXECUTED!</b>\n"
                            f"• Asset: <code>{symbol}</code> SHORT\n"
                            f"• Exit: <code>${curr_p:,.4f}</code>\n"
                            f"• Realized PnL: <b>+${pnl:,.2f}</b> 🎉"
                        )
                        continue

            except Exception as e:
                logger.error(f"Error monitoring position {symbol}: {e}")

        for s in symbols_to_remove:
            if s in self.active_positions:
                del self.active_positions[s]

    async def run(self):
        """Continuous 24/7 trading event loop."""
        self.is_running = True
        await self.initialize()

        logger.info("Bot main loop running...")
        cycle = 0

        while self.is_running:
            try:
                cycle += 1
                start_t = time.time()

                # 1. Monitor active open positions first
                await self.monitor_positions()

                # 2. Scan universe for new qualified setups
                tasks = [self.scan_symbol(sym) for sym in self.symbols]
                await asyncio.gather(*tasks, return_exceptions=True)

                elapsed = time.time() - start_t
                sleep_t = max(1.0, self.poll_interval - elapsed)
                await asyncio.sleep(sleep_t)

            except asyncio.CancelledError:
                logger.info("Bot run loop cancelled.")
                break
            except Exception as e:
                logger.critical(f"Unexpected error in bot main loop: {e}", exc_info=True)
                await asyncio.sleep(5)

    def stop(self):
        """Stops the bot."""
        logger.info("Stopping live bot...")
        self.is_running = False
