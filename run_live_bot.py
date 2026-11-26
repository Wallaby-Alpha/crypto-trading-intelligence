"""
Command Line Runner for the WEEX Live Trading Bot.
Usage:
  # Run in paper/dry-run mode (safe default, logs setups, checks live orderbook):
  python run_live_bot.py --paper

  # Run with real money on WEEX (requires WEEX API keys in .env):
  python run_live_bot.py --live --margin 15 --leverage 2

  # Emergency Kill Switch: Cancel all orders & close all positions immediately:
  python run_live_bot.py --kill
"""
import os
import sys
import argparse
import asyncio
import logging
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("live_bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("bot_runner")


def parse_args():
    parser = argparse.ArgumentParser(description="Autonomous WEEX Perpetual Trading Bot")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--live", action="store_true", help="Enable REAL-MONEY execution on WEEX")
    group.add_argument("--paper", action="store_true", default=True, help="Run in paper/dry-run mode (default)")
    group.add_argument("--kill", action="store_true", help="Activate EMERGENCY KILL SWITCH to close all positions")

    parser.add_argument("--margin", type=float, default=None, help="Margin USD allocation per trade (default from .env: $15)")
    parser.add_argument("--leverage", type=int, default=None, help="Isolated margin leverage (default from .env: 2x)")
    parser.add_argument("--max-positions", type=int, default=None, help="Max concurrent positions (default: 2)")

    return parser.parse_args()


async def main():
    args = parse_args()

    # Handle Kill Switch command
    if args.kill:
        from src.execution.weex_execution import WeexExecutionAdapter
        logger.critical("🚨 ACTIVATING EMERGENCY KILL SWITCH VIA CLI...")
        adapter = WeexExecutionAdapter()
        res = adapter.emergency_kill_switch()
        print(f"Kill Switch Result: {res}")
        return

    # Configure Environment Overrides
    if args.live:
        os.environ["ENABLE_LIVE_TRADING"] = "true"
        logger.warning("=" * 60)
        logger.warning("⚠️  STARTING BOT IN LIVE REAL-MONEY EXECUTION MODE! ⚠️")
        logger.warning("=" * 60)
    else:
        os.environ["ENABLE_LIVE_TRADING"] = "false"
        logger.info("Starting bot in PAPER / DRY-RUN mode.")

    if args.margin:
        os.environ["TRADE_AMOUNT_USD"] = str(args.margin)
    if args.leverage:
        os.environ["DEFAULT_LEVERAGE"] = str(args.leverage)
    if args.max_positions:
        os.environ["MAX_CONCURRENT_POSITIONS"] = str(args.max_positions)

    from src.bot.live_bot import LiveTradingBot

    bot = LiveTradingBot()

    try:
        await bot.run()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutting down gracefully...")
        bot.stop()


if __name__ == "__main__":
    asyncio.run(main())

