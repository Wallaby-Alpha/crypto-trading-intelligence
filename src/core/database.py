"""
High-performance persistent SQLite database layer with WAL mode and indexing.
Ensures zero data loss, sub-millisecond writes, and robust query capabilities.
"""
import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from config.settings import settings
from src.core.models import (
    Candle, Trade, Ticker, OpenInterestRecord, OpenInterestMetrics,
    FundingRateRecord, CVDRecord, DataQualityStatus
)


class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.db.db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=settings.db.timeout_seconds)
        conn.row_factory = sqlite3.Row
        if settings.db.wal_mode:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            cur = conn.cursor()

            # 1. Candles
            cur.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                datetime TEXT,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                quote_volume REAL,
                buy_volume REAL,
                sell_volume REAL,
                is_closed INTEGER NOT NULL DEFAULT 1,
                source TEXT NOT NULL DEFAULT 'direct',
                quality_status TEXT NOT NULL DEFAULT 'VALID',
                UNIQUE(symbol, exchange, timeframe, timestamp)
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(symbol, timeframe, timestamp);")

            # 2. Trades
            cur.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                datetime TEXT,
                price REAL NOT NULL,
                amount REAL NOT NULL,
                cost REAL,
                side TEXT NOT NULL,
                is_buyer_maker INTEGER,
                UNIQUE(symbol, exchange, trade_id, timestamp)
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_lookup ON trades(symbol, timestamp);")

            # 3. Open Interest
            cur.execute("""
            CREATE TABLE IF NOT EXISTS open_interest (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                datetime TEXT,
                open_interest_amount REAL NOT NULL,
                open_interest_usd REAL,
                price_at_timestamp REAL,
                source TEXT NOT NULL DEFAULT 'direct',
                quality_status TEXT NOT NULL DEFAULT 'VALID',
                UNIQUE(symbol, exchange, timestamp)
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_oi_lookup ON open_interest(symbol, timestamp);")

            # 4. Open Interest Metrics
            cur.execute("""
            CREATE TABLE IF NOT EXISTS oi_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                current_oi REAL NOT NULL,
                oi_change_1m REAL,
                oi_change_5m REAL,
                oi_change_15m REAL,
                oi_change_30m REAL,
                oi_change_60m REAL,
                oi_pct_change_1m REAL,
                oi_pct_change_5m REAL,
                oi_pct_change_15m REAL,
                oi_pct_change_30m REAL,
                oi_pct_change_60m REAL,
                oi_acceleration REAL,
                oi_divergence_flag TEXT,
                quality_status TEXT NOT NULL DEFAULT 'VALID',
                UNIQUE(symbol, exchange, timestamp)
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_oi_metrics_lookup ON oi_metrics(symbol, timestamp);")

            # 5. CVD records
            cur.execute("""
            CREATE TABLE IF NOT EXISTS cvd_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                datetime TEXT,
                buy_volume REAL NOT NULL,
                sell_volume REAL NOT NULL,
                delta REAL NOT NULL,
                cumulative_delta REAL NOT NULL,
                cvd_momentum REAL,
                is_exchange_provided INTEGER NOT NULL DEFAULT 0,
                quality_status TEXT NOT NULL DEFAULT 'VALID',
                UNIQUE(symbol, exchange, timeframe, timestamp)
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cvd_lookup ON cvd_records(symbol, timeframe, timestamp);")

            # 6. Funding Rates
            cur.execute("""
            CREATE TABLE IF NOT EXISTS funding_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                datetime TEXT,
                funding_rate REAL NOT NULL,
                predicted_funding_rate REAL,
                funding_interval_hours INTEGER DEFAULT 8,
                next_funding_timestamp INTEGER,
                percentile_30d REAL,
                source TEXT NOT NULL DEFAULT 'direct',
                quality_status TEXT NOT NULL DEFAULT 'VALID',
                UNIQUE(symbol, exchange, timestamp)
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_funding_lookup ON funding_rates(symbol, timestamp);")

            # 7. Quality anomaly logs
            cur.execute("""
            CREATE TABLE IF NOT EXISTS data_quality_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                issue_type TEXT NOT NULL,
                details TEXT NOT NULL
            );
            """)

            # 8. Universe snapshots
            cur.execute("""
            CREATE TABLE IF NOT EXISTS universe_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                active_symbols_json TEXT NOT NULL,
                total_active INTEGER NOT NULL
            );
            """)

            # 9. Trade signals
            cur.execute("""
            CREATE TABLE IF NOT EXISTS trade_signals (
                id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                direction TEXT NOT NULL,
                state TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                current_price REAL NOT NULL,
                total_score REAL NOT NULL,
                category TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                tp1 REAL NOT NULL,
                tp2 REAL NOT NULL,
                tp3 REAL NOT NULL,
                risk_reward REAL NOT NULL,
                position_size_usd REAL NOT NULL,
                confirmations_json TEXT NOT NULL
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_signals_lookup ON trade_signals(symbol, timestamp);")

            conn.commit()

    def save_candles(self, candles: List[Candle]) -> int:
        if not candles:
            return 0
        with self.get_connection() as conn:
            cur = conn.cursor()
            rows = [
                (
                    c.symbol, c.exchange, c.timeframe, c.timestamp, c.datetime,
                    c.open, c.high, c.low, c.close, c.volume, c.quote_volume,
                    c.buy_volume, c.sell_volume, 1 if c.is_closed else 0,
                    c.source, c.quality_status.value
                )
                for c in candles
            ]
            cur.executemany("""
            INSERT INTO candles (
                symbol, exchange, timeframe, timestamp, datetime,
                open, high, low, close, volume, quote_volume,
                buy_volume, sell_volume, is_closed, source, quality_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, timeframe, timestamp) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume,
                quote_volume=excluded.quote_volume,
                buy_volume=excluded.buy_volume,
                sell_volume=excluded.sell_volume,
                is_closed=excluded.is_closed,
                quality_status=excluded.quality_status;
            """, rows)
            conn.commit()
            return len(rows)

    def save_trades(self, trades: List[Trade]) -> int:
        if not trades:
            return 0
        with self.get_connection() as conn:
            cur = conn.cursor()
            rows = [
                (
                    t.id, t.symbol, t.exchange, t.timestamp, t.datetime,
                    t.price, t.amount, t.cost, t.side.value,
                    1 if t.is_buyer_maker else 0 if t.is_buyer_maker is not None else None
                )
                for t in trades
            ]
            cur.executemany("""
            INSERT OR IGNORE INTO trades (
                trade_id, symbol, exchange, timestamp, datetime,
                price, amount, cost, side, is_buyer_maker
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, rows)
            conn.commit()
            return len(rows)

    def save_open_interest(self, record: OpenInterestRecord):
        with self.get_connection() as conn:
            conn.execute("""
            INSERT INTO open_interest (
                symbol, exchange, timestamp, datetime, open_interest_amount,
                open_interest_usd, price_at_timestamp, source, quality_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, timestamp) DO UPDATE SET
                open_interest_amount=excluded.open_interest_amount,
                open_interest_usd=excluded.open_interest_usd,
                price_at_timestamp=excluded.price_at_timestamp,
                quality_status=excluded.quality_status;
            """, (
                record.symbol, record.exchange, record.timestamp, record.datetime,
                record.open_interest_amount, record.open_interest_usd,
                record.price_at_timestamp, record.source, record.quality_status.value
            ))
            conn.commit()

    def save_oi_metrics(self, m: OpenInterestMetrics):
        with self.get_connection() as conn:
            conn.execute("""
            INSERT INTO oi_metrics (
                symbol, exchange, timestamp, current_oi,
                oi_change_1m, oi_change_5m, oi_change_15m, oi_change_30m, oi_change_60m,
                oi_pct_change_1m, oi_pct_change_5m, oi_pct_change_15m, oi_pct_change_30m, oi_pct_change_60m,
                oi_acceleration, oi_divergence_flag, quality_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, timestamp) DO UPDATE SET
                current_oi=excluded.current_oi,
                oi_change_1m=excluded.oi_change_1m,
                oi_change_5m=excluded.oi_change_5m,
                oi_change_15m=excluded.oi_change_15m,
                oi_change_30m=excluded.oi_change_30m,
                oi_change_60m=excluded.oi_change_60m,
                oi_pct_change_1m=excluded.oi_pct_change_1m,
                oi_pct_change_5m=excluded.oi_pct_change_5m,
                oi_pct_change_15m=excluded.oi_pct_change_15m,
                oi_pct_change_30m=excluded.oi_pct_change_30m,
                oi_pct_change_60m=excluded.oi_pct_change_60m,
                oi_acceleration=excluded.oi_acceleration,
                oi_divergence_flag=excluded.oi_divergence_flag,
                quality_status=excluded.quality_status;
            """, (
                m.symbol, m.exchange, m.timestamp, m.current_oi,
                m.oi_change_1m, m.oi_change_5m, m.oi_change_15m, m.oi_change_30m, m.oi_change_60m,
                m.oi_pct_change_1m, m.oi_pct_change_5m, m.oi_pct_change_15m, m.oi_pct_change_30m, m.oi_pct_change_60m,
                m.oi_acceleration, m.oi_divergence_flag, m.quality_status.value
            ))
            conn.commit()

    def save_cvd_records(self, records: List[CVDRecord]) -> int:
        if not records:
            return 0
        with self.get_connection() as conn:
            cur = conn.cursor()
            rows = [
                (
                    r.symbol, r.exchange, r.timeframe, r.timestamp, r.datetime,
                    r.buy_volume, r.sell_volume, r.delta, r.cumulative_delta,
                    r.cvd_momentum, 1 if r.is_exchange_provided else 0, r.quality_status.value
                )
                for r in records
            ]
            cur.executemany("""
            INSERT INTO cvd_records (
                symbol, exchange, timeframe, timestamp, datetime,
                buy_volume, sell_volume, delta, cumulative_delta,
                cvd_momentum, is_exchange_provided, quality_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, timeframe, timestamp) DO UPDATE SET
                buy_volume=excluded.buy_volume,
                sell_volume=excluded.sell_volume,
                delta=excluded.delta,
                cumulative_delta=excluded.cumulative_delta,
                cvd_momentum=excluded.cvd_momentum,
                quality_status=excluded.quality_status;
            """, rows)
            conn.commit()
            return len(rows)

    def save_funding_rate(self, record: FundingRateRecord):
        with self.get_connection() as conn:
            conn.execute("""
            INSERT INTO funding_rates (
                symbol, exchange, timestamp, datetime, funding_rate,
                predicted_funding_rate, funding_interval_hours, next_funding_timestamp,
                percentile_30d, source, quality_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, timestamp) DO UPDATE SET
                funding_rate=excluded.funding_rate,
                predicted_funding_rate=excluded.predicted_funding_rate,
                next_funding_timestamp=excluded.next_funding_timestamp,
                percentile_30d=excluded.percentile_30d,
                quality_status=excluded.quality_status;
            """, (
                record.symbol, record.exchange, record.timestamp, record.datetime,
                record.funding_rate, record.predicted_funding_rate,
                record.funding_interval_hours, record.next_funding_timestamp,
                record.percentile_30d, record.source, record.quality_status.value
            ))
            conn.commit()

    def log_quality_issue(self, symbol: str, exchange: str, timestamp: int, issue_type: str, details: str):
        with self.get_connection() as conn:
            conn.execute("""
            INSERT INTO data_quality_logs (symbol, exchange, timestamp, issue_type, details)
            VALUES (?, ?, ?, ?, ?);
            """, (symbol, exchange, timestamp, issue_type, details))
            conn.commit()

    def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT * FROM candles
            WHERE symbol = ? AND timeframe = ?
            ORDER BY timestamp DESC
            LIMIT ?;
            """, (symbol, timeframe, limit))
            rows = cur.fetchall()
            return [dict(r) for r in reversed(rows)]

    def get_candle_models(self, symbol: str, timeframe: str, limit: int = 200) -> List[Candle]:
        dicts = self.get_candles(symbol, timeframe, limit)
        models: List[Candle] = []
        for d in dicts:
            try:
                models.append(Candle(
                    symbol=d["symbol"],
                    exchange=d["exchange"],
                    timeframe=d["timeframe"],
                    timestamp=d["timestamp"],
                    datetime=d.get("datetime") or "",
                    open=float(d["open"]),
                    high=float(d["high"]),
                    low=float(d["low"]),
                    close=float(d["close"]),
                    volume=float(d["volume"]),
                    quote_volume=float(d["quote_volume"]) if d.get("quote_volume") is not None else None,
                    buy_volume=float(d["buy_volume"]) if d.get("buy_volume") is not None else None,
                    sell_volume=float(d["sell_volume"]) if d.get("sell_volume") is not None else None,
                    is_closed=bool(d.get("is_closed", True)),
                    source=d.get("source", "weex"),
                    quality_status=DataQualityStatus(d.get("quality_status", "VALID"))
                ))
            except Exception:
                pass
        return models

    def get_latest_oi_history(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT * FROM open_interest
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?;
            """, (symbol, limit))
            rows = cur.fetchall()
            return [dict(r) for r in reversed(rows)]

    def get_latest_funding_history(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT * FROM funding_rates
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?;
            """, (symbol, limit))
            rows = cur.fetchall()
            return [dict(r) for r in reversed(rows)]
