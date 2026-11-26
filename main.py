"""
Master Command-Line Interface (CLI).
Unified entrypoint for the Cryptocurrency Liquidity & Derivatives Trading Intelligence System.

Usage:
  python main.py scan              # Runs continuous 50-asset live scanner daemon
  python main.py scan --single     # Runs one full 50-asset scanning cycle and exits
  python main.py backtest          # Runs historical backtests & research lab experiments
  python main.py dashboard         # Starts interactive Streamlit web dashboard
  python main.py kill              # Activates emergency execution kill-switch
"""
import sys
import os
import argparse
import asyncio
import subprocess
from pathlib import Path

# Ensure project root is in python path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.scanner.scanner_daemon import ScannerDaemon
from src.execution.weex_execution import WeexExecutionAdapter


def cmd_scan(args):
    print("=" * 80)
    print("STARTING 50-ASSET CRYPTO INTELLIGENCE SCANNER DAEMON")
    print("=" * 80)
    daemon = ScannerDaemon(max_symbols=50, scan_interval_seconds=60)
    try:
        asyncio.run(daemon.start(single_run=args.single))
    except KeyboardInterrupt:
        daemon.stop()
        print("\nScanner daemon cleanly shutdown.")


def cmd_backtest(args):
    print("=" * 80)
    print("RUNNING HISTORICAL BACKTESTING & RESEARCH LABORATORY")
    print("=" * 80)
    script_path = ROOT_DIR / "run_phase4_backtest.py"
    subprocess.run([sys.executable, str(script_path)])


def cmd_dashboard(args):
    print("=" * 80)
    print("LAUNCHING STREAMLIT TRADING INTELLIGENCE DASHBOARD")
    print("=" * 80)
    app_path = ROOT_DIR / "dashboard" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", "8501"])


def cmd_kill(args):
    print("=" * 80)
    print("ACTIVATING EMERGENCY KILL-SWITCH")
    print("=" * 80)
    adapter = WeexExecutionAdapter()
    res = adapter.emergency_kill_switch()
    print(f"Result: {res}")


def main():
    parser = argparse.ArgumentParser(
        description="Multi-Asset Crypto Liquidity & Derivatives Trading Intelligence System"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = subparsers.add_parser("scan", help="Run 50-asset live scanner daemon")
    p_scan.add_argument("--single", action="store_true", help="Run single cycle and exit")
    p_scan.set_defaults(func=cmd_scan)

    # backtest
    p_bt = subparsers.add_parser("backtest", help="Run historical backtests and research lab")
    p_bt.set_defaults(func=cmd_backtest)

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Start Streamlit web dashboard")
    p_dash.set_defaults(func=cmd_dashboard)

    # kill
    p_kill = subparsers.add_parser("kill", help="Emergency Kill-Switch (cancel all orders & market close)")
    p_kill.set_defaults(func=cmd_kill)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

