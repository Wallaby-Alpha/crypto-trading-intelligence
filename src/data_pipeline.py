"""
Master Data Pipeline & Ingestion Engine.
Coordinates data ingestion across 50 assets and multiple timeframes (1m, 5m, 15m, 1h, 4h).
Calculates and persists:
- OHLCV candles
- Trades & tick CVD
- Open Interest & multi-horizon deltas
- Funding rates & percentiles
- VWAP & Volume Profile
- Data quality verification
"""
import time
import logging
from typing import List, Dict, Any, Optional
from src.adapters.base import BaseExchangeAdapter
from src.universe.universe_manager import UniverseManager
from src.core.database import DatabaseManager
from src.core.quality import DataQualityMonitor
from src.indicators.cvd import CVDEngine, CVDBar
from src.indicators.oi import OpenInterestEngine
from src.indicators.vwap import VWAPEngine
from src.indicators.volume_profile import VolumeProfileEngine
from src.indicators.volatility import VolatilityEngine
from src.core.models import (
    Candle, Trade, OpenInterestRecord, FundingRateRecord,
    CVDRecord, OpenInterestMetrics, DataQualityStatus
)
from config.settings import settings

logger = logging.getLogger(__name__)


class DataPipeline:
    def __init__(
        self,
        adapter: BaseExchangeAdapter,
        db_manager: DatabaseManager,
        universe_manager: Optional[UniverseManager] = None
    ):
        self.adapter = adapter
        self.db = db_manager
        self.universe = universe_manager or UniverseManager(adapter)
        self.quality = DataQualityMonitor(db_manager)

        # Indicator engines
        self.cvd_engine = CVDEngine(momentum_window=5)
        self.oi_engine = OpenInterestEngine(baseline_lookback=60)
        self.vwap_engine = VWAPEngine(session_anchor_hours=24)
        self.vp_engine = VolumeProfileEngine(num_bins=50, value_area_pct=0.70)
        self.vol_engine = VolatilityEngine(atr_period=14)

        self.timeframes = settings.collector.timeframes

    def ingest_symbol_candles(self, symbol: str, timeframe: str, limit: int = 100) -> List[Candle]:
        """
        Fetches, validates, and stores OHLCV candles for a symbol and timeframe.
        """
        try:
            candles = self.adapter.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not candles:
                return []

            tf_min_map = {'1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240, '1d': 1440}
            tf_min = tf_min_map.get(timeframe, 1)

            validated_candles = self.quality.validate_candles_series(candles, timeframe_minutes=tf_min)
            # Store validated candles
            self.db.save_candles(validated_candles)
            return validated_candles
        except Exception as e:
            logger.error(f"Failed to ingest candles for {symbol} {timeframe}: {e}")
            return []

    def ingest_symbol_trades_and_cvd(self, symbol: str, candles: List[Candle], limit: int = 100) -> List[CVDBar]:
        """
        Fetches raw trades, calculates tick-level CVD, and stores both trades and CVD records.
        """
        try:
            trades = self.adapter.fetch_trades(symbol, limit=limit)
            if trades:
                self.db.save_trades(trades)
                cvd_bars = self.cvd_engine.compute_from_trades(trades, candles)
            else:
                # Fallback to candle estimation if trade stream empty
                cvd_bars = self.cvd_engine.estimate_from_candles(candles)

            # Convert to CVDRecords for storage
            records = [
                CVDRecord(
                    symbol=symbol,
                    exchange=self.adapter.exchange_id,
                    timeframe=candles[0].timeframe if candles else "1m",
                    timestamp=b.timestamp,
                    datetime=b.datetime,
                    buy_volume=b.buy_volume,
                    sell_volume=b.sell_volume,
                    delta=b.delta,
                    cumulative_delta=b.cumulative_delta,
                    cvd_momentum=b.cvd_momentum,
                    is_exchange_provided=b.is_exchange_provided,
                    quality_status=DataQualityStatus.VALID
                )
                for b in cvd_bars
            ]
            self.db.save_cvd_records(records)
            return cvd_bars
        except Exception as e:
            logger.error(f"Failed to ingest trades and CVD for {symbol}: {e}")
            return []

    def ingest_symbol_open_interest(self, symbol: str, current_price: Optional[float] = None) -> Optional[OpenInterestMetrics]:
        """
        Fetches current OI, validates quality, appends to database, and calculates multi-horizon metrics.
        """
        try:
            oi_record = self.adapter.fetch_open_interest(symbol)
            is_valid, checked_oi, issue = self.quality.validate_open_interest(oi_record)
            
            # Save raw OI
            self.db.save_open_interest(checked_oi)

            # Query recent history to calculate metrics
            history_rows = self.db.get_latest_oi_history(symbol, limit=60)
            hist_records = [
                OpenInterestRecord(
                    symbol=r['symbol'],
                    exchange=r['exchange'],
                    timestamp=r['timestamp'],
                    datetime=r['datetime'],
                    open_interest_amount=r['open_interest_amount'],
                    open_interest_usd=r['open_interest_usd'],
                    price_at_timestamp=r['price_at_timestamp'],
                    quality_status=DataQualityStatus(r['quality_status'])
                )
                for r in history_rows
            ]

            metrics = self.oi_engine.compute_metrics(hist_records, current_price=current_price)
            if metrics:
                self.db.save_oi_metrics(metrics)
            return metrics
        except Exception as e:
            logger.error(f"Failed to ingest OI for {symbol}: {e}")
            return None

    def ingest_symbol_funding(self, symbol: str) -> Optional[FundingRateRecord]:
        """
        Fetches funding rate, validates, and stores.
        """
        try:
            fr = self.adapter.fetch_funding_rate(symbol)
            is_valid, checked_fr, issue = self.quality.validate_funding_rate(fr)
            self.db.save_funding_rate(checked_fr)
            return checked_fr
        except Exception as e:
            logger.error(f"Failed to ingest funding rate for {symbol}: {e}")
            return None

    def sync_symbol_full(self, symbol: str) -> Dict[str, Any]:
        """
        Executes a complete data sync for a single symbol across all timeframes.
        """
        result = {"symbol": symbol, "timeframes": {}, "oi": None, "funding": None}
        
        # 1. Ticker for current price & spread
        try:
            ticker = self.adapter.fetch_ticker(symbol)
            curr_price = ticker.last
        except Exception:
            curr_price = None

        # 2. Multi-timeframe OHLCV
        for tf in self.timeframes:
            candles = self.ingest_symbol_candles(symbol, timeframe=tf, limit=100)
            result["timeframes"][tf] = {
                "candle_count": len(candles),
                "latest_close": candles[-1].close if candles else None
            }
            # For 5m, compute CVD and Volume Profile
            if tf == "5m" and candles:
                cvd_bars = self.ingest_symbol_trades_and_cvd(symbol, candles, limit=100)
                vp = self.vp_engine.compute_profile(candles)
                vwap_bands = self.vwap_engine.calculate_anchored_vwap(candles)
                atr_vals = self.vol_engine.calculate_atr(candles)
                
                result["timeframes"][tf].update({
                    "cvd_bar_count": len(cvd_bars),
                    "poc_price": vp.poc_price if vp else None,
                    "val_price": vp.val_price if vp else None,
                    "vah_price": vp.vah_price if vp else None,
                    "current_vwap": vwap_bands[-1].vwap if vwap_bands else None,
                    "current_atr": atr_vals[-1] if atr_vals else None
                })

        # 3. Open interest
        oi_metrics = self.ingest_symbol_open_interest(symbol, current_price=curr_price)
        result["oi"] = oi_metrics.model_dump() if oi_metrics else None

        # 4. Funding rate
        funding = self.ingest_symbol_funding(symbol)
        result["funding"] = funding.model_dump() if funding else None

        return result
