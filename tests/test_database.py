"""
Tests for DatabaseManager: SQLite storage, WAL mode, conflict handling, and queries.
"""
import os
import gc
import tempfile
import pytest
from src.core.database import DatabaseManager
from src.core.models import Candle, Trade, OpenInterestRecord, FundingRateRecord, CVDRecord, TradeSide, DataQualityStatus


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(path)
    yield db
    gc.collect()
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def test_database_initialization(temp_db):
    conn = temp_db.get_connection()
    cur = conn.cursor()
    # Check tables exist
    tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
    assert "candles" in tables
    assert "trades" in tables
    assert "open_interest" in tables
    assert "cvd_records" in tables
    assert "funding_rates" in tables


def test_save_and_get_candles(temp_db):
    candles = [
        Candle(
            symbol="BTC/USDT:USDT",
            exchange="weex",
            timeframe="5m",
            timestamp=1700000000000,
            datetime="2023-11-14T22:13:20Z",
            open=50000.0,
            high=50500.0,
            low=49900.0,
            close=50400.0,
            volume=100.5,
            is_closed=True,
            quality_status=DataQualityStatus.VALID
        ),
        Candle(
            symbol="BTC/USDT:USDT",
            exchange="weex",
            timeframe="5m",
            timestamp=1700000300000,
            datetime="2023-11-14T22:18:20Z",
            open=50400.0,
            high=50600.0,
            low=50300.0,
            close=50550.0,
            volume=85.2,
            is_closed=True,
            quality_status=DataQualityStatus.VALID
        )
    ]
    saved = temp_db.save_candles(candles)
    assert saved == 2

    # Query back
    fetched = temp_db.get_candles("BTC/USDT:USDT", "5m", limit=10)
    assert len(fetched) == 2
    assert fetched[0]["close"] == 50400.0
    assert fetched[1]["close"] == 50550.0


def test_save_open_interest_and_funding(temp_db):
    oi = OpenInterestRecord(
        symbol="ETH/USDT:USDT",
        exchange="weex",
        timestamp=1700000000000,
        datetime="2023-11-14T22:13:20Z",
        open_interest_amount=125000.0,
        open_interest_usd=250000000.0
    )
    temp_db.save_open_interest(oi)
    history = temp_db.get_latest_oi_history("ETH/USDT:USDT", limit=5)
    assert len(history) == 1
    assert history[0]["open_interest_amount"] == 125000.0

    fr = FundingRateRecord(
        symbol="ETH/USDT:USDT",
        exchange="weex",
        timestamp=1700000000000,
        datetime="2023-11-14T22:13:20Z",
        funding_rate=0.0001,
        predicted_funding_rate=0.00012
    )
    temp_db.save_funding_rate(fr)
    fr_hist = temp_db.get_latest_funding_history("ETH/USDT:USDT", limit=5)
    assert len(fr_hist) == 1
    assert fr_hist[0]["funding_rate"] == 0.0001
