"""
Tests for UniverseManager.
"""
from unittest.mock import MagicMock
from src.universe.universe_manager import UniverseManager
from src.core.models import Ticker, DataQualityStatus


def test_universe_selection_and_ranking():
    mock_adapter = MagicMock()
    mock_adapter.exchange_id = "weex"
    mock_adapter.load_markets.return_value = {
        "BTC/USDT:USDT": {"swap": True, "quote": "USDT", "active": True},
        "ETH/USDT:USDT": {"swap": True, "quote": "USDT", "active": True},
        "LOWVOL/USDT:USDT": {"swap": True, "quote": "USDT", "active": True},
        "WIDE_SPREAD/USDT:USDT": {"swap": True, "quote": "USDT", "active": True},
    }

    mock_adapter.fetch_tickers.return_value = {
        "BTC/USDT:USDT": Ticker(
            symbol="BTC/USDT:USDT", exchange="weex", timestamp=1000, datetime="",
            last=50000.0, bid=49999.0, ask=50001.0, spread=2.0, spread_pct=0.004,
            volume_24h=1000.0, quote_volume_24h=50_000_000.0, high_24h=52000.0, low_24h=49000.0, percentage_24h=2.0
        ),
        "ETH/USDT:USDT": Ticker(
            symbol="ETH/USDT:USDT", exchange="weex", timestamp=1000, datetime="",
            last=3000.0, bid=2999.5, ask=3000.5, spread=1.0, spread_pct=0.033,
            volume_24h=5000.0, quote_volume_24h=15_000_000.0, high_24h=3100.0, low_24h=2900.0, percentage_24h=1.5
        ),
        "LOWVOL/USDT:USDT": Ticker(
            symbol="LOWVOL/USDT:USDT", exchange="weex", timestamp=1000, datetime="",
            last=1.0, bid=0.999, ask=1.001, spread=0.002, spread_pct=0.2,
            volume_24h=100.0, quote_volume_24h=500.0, high_24h=1.005, low_24h=0.995, percentage_24h=0.1
        ),
        "WIDE_SPREAD/USDT:USDT": Ticker(
            symbol="WIDE_SPREAD/USDT:USDT", exchange="weex", timestamp=1000, datetime="",
            last=10.0, bid=9.0, ask=11.0, spread=2.0, spread_pct=20.0,
            volume_24h=50000.0, quote_volume_24h=50_000_000.0, high_24h=12.0, low_24h=8.0, percentage_24h=5.0
        )
    }

    manager = UniverseManager(mock_adapter)
    active = manager.scan_and_rebalance()

    # BTC and ETH must be qualified and active
    assert "BTC/USDT:USDT" in active
    assert "ETH/USDT:USDT" in active

    # LOWVOL and WIDE_SPREAD should be disqualified
    lowvol_prof = manager.get_profile("LOWVOL/USDT:USDT")
    assert lowvol_prof.is_qualified is False
    assert "Volume" in lowvol_prof.disqualification_reason

    wide_prof = manager.get_profile("WIDE_SPREAD/USDT:USDT")
    assert wide_prof.is_qualified is False
    assert "Spread" in wide_prof.disqualification_reason
