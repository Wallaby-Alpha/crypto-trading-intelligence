"""
Multi-Asset 50-Symbol Continuous Scanner Daemon.
Coordinates real-time asynchronous monitoring across the top 50 perpetual futures markets.
Runs:
- Universe rebalancing and market filtering
- Multi-timeframe ingestion (1m, 5m, 15m, 1h, 4h)
- Quantitative indicator updates (CVD, OI deltas, VWAP, Volume Profile, Volatility)
- Trading event detection (Sweeps, MSS, CVD Divergence, OI Regimes, VWAP Reclaims)
- Multi-factor scoring (0-100) and risk sizing
- Duplicate filtering and multi-timeframe confluence upgrading
- SQLite persistence
- Telegram notification dispatch
- Diagnostics & health telemetry
"""
import sys
import os
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional

from config.settings import settings
from src.core.database import DatabaseManager
from src.adapters.weex import WeexAdapter
from src.universe.universe_manager import UniverseManager
from src.data_pipeline import DataPipeline
from src.events.event_engine import EventEngine
from src.strategies.strategy_coordinator import StrategyCoordinator
from src.strategies.models import TradeSignal
from src.notifications.telegram_bot import TelegramNotifier

logger = logging.getLogger("scanner_daemon")


class ScannerDaemon:
    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        adapter: Optional[WeexAdapter] = None,
        max_symbols: int = 50,
        concurrency: int = 4,
        scan_interval_seconds: int = 60,
        min_score_alert: float = 65.0
    ):
        self.db = db or DatabaseManager()
        self.adapter = adapter or WeexAdapter(rate_limit=True)
        self.universe_manager = UniverseManager(self.adapter)
        self.pipeline = DataPipeline(self.adapter, self.db, self.universe_manager)
        self.event_engine = EventEngine(db=self.db)
        self.strategy_coordinator = StrategyCoordinator()
        self.telegram = TelegramNotifier(
            bot_token=settings.telegram.bot_token,
            chat_id=settings.telegram.chat_id,
            min_score_to_alert=min_score_alert
        )

        self.max_symbols = max_symbols
        self.concurrency = concurrency
        self.scan_interval = scan_interval_seconds
        self.semaphore = asyncio.Semaphore(concurrency)
        self.is_running = False

        # Telemetry & Diagnostics
        self.cycle_count = 0
        self.last_cycle_start = 0.0
        self.last_cycle_duration = 0.0
        self.total_signals_detected = 0
        self.monitored_symbols: List[str] = []

    def refresh_universe(self) -> List[str]:
        """
        Discovers and ranks up to 50 active perpetual markets.
        """
        logger.info("Scanning and rebalancing universe...")
        selected = self.universe_manager.scan_and_rebalance()
        self.monitored_symbols = selected[: self.max_symbols]
        logger.info(f"Monitoring {len(self.monitored_symbols)} symbols: {self.monitored_symbols[:6]}...")
        return self.monitored_symbols

    async def scan_single_symbol(self, symbol: str) -> List[TradeSignal]:
        """
        Asynchronously processes a single cryptocurrency market:
        1. Ingests data across timeframes
        2. Detects events
        3. Evaluates strategies & multi-factor scoring
        4. Dispatches alerts for qualified opportunities
        """
        async with self.semaphore:
            loop = asyncio.get_running_loop()
            try:
                # 1. Sync data across multi-timeframes via thread pool
                sync_res = await loop.run_in_executor(None, self.pipeline.sync_symbol_full, symbol)
                if not sync_res or "timeframes" not in sync_res:
                    return []

                # Primary trigger timeframe: 5m; Higher timeframe context: 15m, 1h
                candles_5m = self.db.get_candle_models(symbol, "5m", limit=120)
                candles_15m = self.db.get_candle_models(symbol, "15m", limit=120)
                candles_1h = self.db.get_candle_models(symbol, "1h", limit=120)

                if len(candles_5m) < 30:
                    return []

                current_price = candles_5m[-1].close
                tf_5m_data = sync_res["timeframes"].get("5m", {})
                atr_5m = tf_5m_data.get("current_atr", 1.0)
                vwap_bands = tf_5m_data.get("vwap_bands", [])
                vp = tf_5m_data.get("volume_profile")
                cvd_bars = tf_5m_data.get("cvd_bars", [])
                oi_metrics = sync_res.get("oi")
                funding = sync_res.get("funding")
                funding_rate = funding.get("funding_rate") if funding else None

                # Check Higher Timeframe (15m/1h) bias and trend
                htf_aligned = False
                htf_trend = "NEUTRAL"
                if len(candles_15m) >= 20 and len(candles_1h) >= 20:
                    # Aligned if 15m and 1h moving in same structural direction
                    htf_aligned = (candles_15m[-1].close > candles_15m[-10].close and candles_1h[-1].close > candles_1h[-10].close) or \
                                  (candles_15m[-1].close < candles_15m[-10].close and candles_1h[-1].close < candles_1h[-10].close)

                if len(candles_1h) >= 50:
                    import pandas as pd
                    closes_1h = pd.Series([c.close for c in candles_1h])
                    ema20 = closes_1h.ewm(span=20, adjust=False).mean().iloc[-1]
                    ema50 = closes_1h.ewm(span=50, adjust=False).mean().iloc[-1]
                    last_c = candles_1h[-1].close
                    if last_c > ema50 and ema20 > ema50:
                        htf_trend = "BULLISH"
                    elif last_c < ema50 and ema20 < ema50:
                        htf_trend = "BEARISH"

                # 2. Detect Trading Events on 5m (persists automatically to db)
                bundle = self.event_engine.analyze_candle(
                    candles=candles_5m,
                    cvd_bars=cvd_bars,
                    oi_metrics=oi_metrics,
                    vwap_bands=vwap_bands,
                    vp_result=vp,
                    atr_value=atr_5m
                )

                # 3. Evaluate Strategy Suite & Calculate 0-100 Multi-Factor Scores
                signals = self.strategy_coordinator.evaluate_bundle(
                    bundle=bundle,
                    current_price=current_price,
                    atr_value=atr_5m,
                    funding_rate=funding_rate,
                    htf_aligned=htf_aligned,
                    htf_trend=htf_trend
                )

                # Filter duplicates and check score threshold
                qualified_signals = []
                for sig in signals:
                    passed = self.strategy_coordinator.duplicate_filter.filter_and_update(sig)
                    if passed:
                        qualified_signals.append(sig)
                        # Dispatch Telegram notification
                        await self.telegram.notify_signal(sig)

                # Persist signals
                if qualified_signals:
                    self.strategy_coordinator.save_signals_to_db(qualified_signals, self.db)
                    self.total_signals_detected += len(qualified_signals)

                return qualified_signals

            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}", exc_info=True)
                return []

    async def run_scan_cycle(self) -> Dict[str, Any]:
        """
        Executes one full scan cycle across all monitored assets.
        """
        self.cycle_count += 1
        self.last_cycle_start = time.time()
        logger.info(f"--- Starting Scan Cycle #{self.cycle_count} across {len(self.monitored_symbols)} symbols ---")

        tasks = [self.scan_single_symbol(sym) for sym in self.monitored_symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_signals: List[TradeSignal] = []
        for r in results:
            if isinstance(r, list):
                all_signals.extend(r)

        self.last_cycle_duration = time.time() - self.last_cycle_start
        logger.info(f"--- Cycle #{self.cycle_count} Finished in {self.last_cycle_duration:.2f}s | Signals Detected: {len(all_signals)} ---")

        return {
            "cycle": self.cycle_count,
            "duration_seconds": self.last_cycle_duration,
            "symbols_scanned": len(self.monitored_symbols),
            "signals_detected": len(all_signals),
            "signals": all_signals
        }

    async def start(self, single_run: bool = False):
        """
        Starts the scanner loop.
        """
        self.is_running = True
        logger.info("Initializing Scanner Daemon...")

        # Initial universe load
        self.refresh_universe()

        while self.is_running:
            cycle_res = await self.run_scan_cycle()

            if single_run:
                break

            # Periodically rebalance universe every 30 cycles
            if self.cycle_count % 30 == 0:
                self.refresh_universe()

            # Sleep remaining time until next scan interval
            sleep_duration = max(5.0, self.scan_interval - cycle_res["duration_seconds"])
            logger.info(f"Sleeping {sleep_duration:.1f}s until next cycle...")
            await asyncio.sleep(sleep_duration)

    def stop(self):
        self.is_running = False
        logger.info("Scanner Daemon stopped.")
