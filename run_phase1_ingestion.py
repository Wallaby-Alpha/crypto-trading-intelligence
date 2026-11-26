"""
Phase 1 Execution & Verification Script.
Initializes WEEX adapter, scans the top 50 perpetual markets,
runs live ingestion across multi-timeframes (1m, 5m, 15m, 1h, 4h),
calculates tick CVD, Open Interest deltas, VWAP, Volume Profile, and ATR,
stores data in SQLite WAL, and prints comprehensive diagnostics.
"""
import sys
import time
from pathlib import Path
from tabulate import tabulate

# Ensure project root is in python path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import settings
from src.core.database import DatabaseManager
from src.adapters.weex import WeexAdapter
from src.universe.universe_manager import UniverseManager
from src.data_pipeline import DataPipeline


def main():
    print("=" * 80)
    print(" CRYPTO TRADING INTELLIGENCE SYSTEM - PHASE 1 VERIFICATION")
    print(" Multi-Asset Liquidity & Derivatives Data Pipeline")
    print("=" * 80)

    # 1. Initialize Database
    db_path = settings.db.db_path
    print(f"\n[1] Initializing Persistent Database at: {db_path}")
    db = DatabaseManager(db_path)
    print("    Database initialized with WAL mode & multi-timeframe indexing.")

    # 2. Initialize WEEX Adapter
    print("\n[2] Initializing WEEX Exchange Adapter...")
    adapter = WeexAdapter(rate_limit=True)
    markets = adapter.load_markets()
    swaps = adapter.get_swap_symbols()
    print(f"    Connected to WEEX: {len(markets)} total markets, {len(swaps)} perpetual swaps available.")

    # 3. Universe Discovery & Ranking
    print("\n[3] Scanning and Filtering Asset Universe (Up to 50 Assets)...")
    universe = UniverseManager(adapter)
    active_symbols = universe.scan_and_rebalance()
    print(f"    Active Monitored Universe: {len(active_symbols)} symbols selected.")
    
    # Print sample top 10 universe assets
    profiles = [universe.get_profile(s) for s in active_symbols[:10]]
    headers = ["Rank", "Symbol", "Price", "24h Vol ($M)", "Spread %", "Daily Volat %", "Priority"]
    table_data = []
    for p in profiles:
        if p:
            table_data.append([
                p.liquidity_rank,
                p.symbol,
                f"${p.price:,.4f}" if p.price < 10 else f"${p.price:,.2f}",
                f"${p.volume_24h_usd / 1e6:,.1f}M",
                f"{p.bid_ask_spread_pct:.3f}%",
                f"{p.daily_volatility_pct:.2f}%",
                "YES" if p.is_priority else "NO"
            ])
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

    # 4. Ingest and Verify Data on Priority Core Assets
    print("\n[4] Running Multi-Timeframe Data Ingestion & Indicator Calculations...")
    pipeline = DataPipeline(adapter, db, universe)
    
    test_symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    results = []

    for sym in test_symbols:
        print(f"    --> Syncing {sym} across [1m, 5m, 15m, 1h, 4h], CVD, OI, and Funding...")
        t0 = time.time()
        res = pipeline.sync_symbol_full(sym)
        elapsed = time.time() - t0
        
        m5 = res["timeframes"].get("5m", {})
        oi = res.get("oi")
        funding = res.get("funding")

        results.append({
            "Symbol": sym,
            "1m": res["timeframes"].get("1m", {}).get("candle_count", 0),
            "5m": m5.get("candle_count", 0),
            "15m": res["timeframes"].get("15m", {}).get("candle_count", 0),
            "1h": res["timeframes"].get("1h", {}).get("candle_count", 0),
            "4h": res["timeframes"].get("4h", {}).get("candle_count", 0),
            "CVD Bars": m5.get("cvd_bar_count", 0),
            "VWAP": f"${m5.get('current_vwap', 0):,.2f}" if m5.get('current_vwap') else "N/A",
            "POC": f"${m5.get('poc_price', 0):,.2f}" if m5.get('poc_price') else "N/A",
            "ATR": f"${m5.get('current_atr', 0):,.2f}" if m5.get('current_atr') else "N/A",
            "OI": f"{oi['current_oi']:,.1f}" if oi else "N/A",
            "Funding": f"{funding['funding_rate'] * 100:.4f}%" if funding else "N/A",
            "Sync (s)": f"{elapsed:.2f}s"
        })

    print("\n[5] Ingestion Verification Summary:")
    print(tabulate(results, headers="keys", tablefmt="grid"))

    # 5. Verify Database Records
    print("\n[6] Database Persistence Integrity Check:")
    with db.get_connection() as conn:
        cur = conn.cursor()
        c_count = cur.execute("SELECT count(*) FROM candles;").fetchone()[0]
        t_count = cur.execute("SELECT count(*) FROM trades;").fetchone()[0]
        oi_count = cur.execute("SELECT count(*) FROM open_interest;").fetchone()[0]
        cvd_count = cur.execute("SELECT count(*) FROM cvd_records;").fetchone()[0]
        f_count = cur.execute("SELECT count(*) FROM funding_rates;").fetchone()[0]
        q_count = cur.execute("SELECT count(*) FROM data_quality_logs;").fetchone()[0]

        print(f"    - Total Stored Candles:       {c_count:,}")
        print(f"    - Total Stored Raw Trades:    {t_count:,}")
        print(f"    - Total Stored OI Records:    {oi_count:,}")
        print(f"    - Total Stored CVD Records:   {cvd_count:,}")
        print(f"    - Total Stored Funding Rates: {f_count:,}")
        print(f"    - Data Quality Anomalies:     {q_count:,}")

    print("\n" + "=" * 80)
    print(" PHASE 1 VERIFICATION COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    main()
