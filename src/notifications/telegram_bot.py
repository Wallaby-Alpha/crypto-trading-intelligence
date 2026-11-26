"""
Telegram Notification Engine & Formatter.
Adheres strictly to the specification in Section 12:
- Actionable alert format (Entry, SL, TP1-3, R:R, Score, Confirmations, HTF Alignment)
- Lifecycle updates (Triggered, TP1 hit, Stopped out, Invalidated)
- Rate limiting and duplicate alert prevention
- Graceful mock mode when TELEGRAM_BOT_TOKEN / CHAT_ID are not set
"""
import logging
import asyncio
import time
from typing import Optional, Dict, Any, List
import aiohttp
from src.strategies.models import TradeSignal, SignalDirection, SignalCategory

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        min_score_to_alert: float = 65.0,
        rate_limit_seconds: float = 3.0
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.min_score_to_alert = min_score_to_alert
        self.rate_limit_seconds = rate_limit_seconds
        self.last_sent_timestamp: float = 0.0
        self.is_configured = bool(bot_token and chat_id and bot_token != "YOUR_TELEGRAM_BOT_TOKEN")
        self._sent_alert_ids = set()

        if self.is_configured:
            logger.info("TelegramNotifier initialized in LIVE mode.")
        else:
            logger.info("TelegramNotifier initialized in SIMULATION/LOGGING mode (credentials not configured).")

    def format_signal_alert(self, signal: TradeSignal) -> str:
        """
        Formats a high-probability trade signal into the exact Section 12 alert layout.
        """
        dir_emoji = "🟢" if signal.direction == SignalDirection.LONG else "🔴"
        cat_badge = signal.category.value
        symbol_clean = signal.symbol.split(":")[0] if ":" in signal.symbol else signal.symbol

        lines = [
            f"{dir_emoji} <b>[{cat_badge}] {signal.direction.value} SETUP DETECTED</b>",
            f"<b>Asset:</b> <code>{symbol_clean}</code> | <b>Timeframe:</b> <code>{signal.timeframe}</code>",
            f"<b>Strategy:</b> {signal.strategy_name}",
            f"<b>Confluence Score:</b> <b>{signal.score.total_score:.1f} / 100</b>",
            "",
            "🎯 <b>EXECUTION LEVELS:</b>",
            f"• <b>Entry:</b> <code>${signal.entry_price:,.4f}</code>",
            f"• <b>Stop Loss:</b> <code>${signal.stop_loss:,.4f}</code> ({abs(signal.entry_price - signal.stop_loss) / signal.entry_price * 100:.2f}%)",
            f"• <b>Take Profit 1:</b> <code>${signal.tp1:,.4f}</code> (1.0R - 33% exit)",
            f"• <b>Take Profit 2:</b> <code>${signal.tp2:,.4f}</code> (2.0R - 33% exit)",
            f"• <b>Take Profit 3:</b> <code>${signal.tp3:,.4f}</code> (3.0R - 34% runner)",
            f"• <b>Risk-to-Reward:</b> <code>1 : {signal.risk_reward:.1f}</code>",
            f"• <b>Recommended Pos:</b> <code>${signal.position_size_usd:,.0f}</code> (1% account risk)",
            "",
            "🔍 <b>CONFIRMATION FACTORS:</b>",
        ]

        # Breakdowns
        bd = signal.score
        lines.append(f"• Liquidity Sweep: <code>{bd.liquidity_quality:.1f}/15</code>")
        lines.append(f"• Market Structure: <code>{bd.market_structure:.1f}/15</code>")
        lines.append(f"• Open Interest: <code>{bd.oi_behavior:.1f}/15</code>")
        lines.append(f"• Cumulative Delta: <code>{bd.cvd_confirmation:.1f}/15</code>")
        lines.append(f"• Volume & VWAP: <code>{bd.volume_displacement + bd.vwap_context:.1f}/20</code>")
        lines.append(f"• HTF Confluence: <code>{bd.htf_alignment:.1f}/10</code>")

        if signal.confirmations:
            lines.append("")
            lines.append("⚡ <b>KEY TRIGGERS:</b>")
            for c in signal.confirmations[:5]:
                lines.append(f"  ✓ {c}")

        lines.append("")
        lines.append(f"<i>Time: {signal.datetime or 'N/A'} | ID: {signal.signal_id[:8]}</i>")
        return "\n".join(lines)

    def format_lifecycle_update(
        self,
        signal_id: str,
        symbol: str,
        direction: str,
        event_type: str,
        details: str
    ) -> str:
        """
        Formats trade lifecycle updates: TRIGGERED, TP1_HIT, STOPPED, INVALIDATED.
        """
        symbol_clean = symbol.split(":")[0] if ":" in symbol else symbol
        emoji_map = {
            "TRIGGERED": "🚀",
            "TP1_HIT": "💰",
            "TP2_HIT": "💰💰",
            "TP3_FULL": "🏆",
            "STOP_LOSS": "🛑",
            "BREAKEVEN": "🛡️",
            "INVALIDATED": "⚠️"
        }
        icon = emoji_map.get(event_type, "ℹ️")

        lines = [
            f"{icon} <b>TRADE UPDATE: {event_type}</b>",
            f"<b>Asset:</b> <code>{symbol_clean}</code> | <b>Side:</b> {direction}",
            f"<b>Details:</b> {details}",
            f"<i>Signal ID: {signal_id[:8]}</i>"
        ]
        return "\n".join(lines)

    async def send_message(self, text: str) -> bool:
        """
        Sends HTML formatted text to the configured Telegram chat.
        Rate-limited to prevent flooding.
        """
        # Respect rate limit
        now = time.time()
        elapsed = now - self.last_sent_timestamp
        if elapsed < self.rate_limit_seconds:
            await asyncio.sleep(self.rate_limit_seconds - elapsed)

        if not self.is_configured:
            logger.info(f"[TELEGRAM SIMULATION]\n{text}\n" + "-" * 50)
            self.last_sent_timestamp = time.time()
            return True

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8.0)) as resp:
                    if resp.status == 200:
                        self.last_sent_timestamp = time.time()
                        return True
                    else:
                        err_body = await resp.text()
                        logger.error(f"Telegram API error HTTP {resp.status}: {err_body}")
                        return False
        except Exception as e:
            logger.error(f"Failed to deliver Telegram notification: {e}")
            return False

    async def notify_signal(self, signal: TradeSignal) -> bool:
        """
        Checks score threshold and deduplication before sending.
        """
        if signal.score.total_score < self.min_score_to_alert:
            return False

        if signal.signal_id in self._sent_alert_ids:
            return False

        self._sent_alert_ids.add(signal.signal_id)
        msg = self.format_signal_alert(signal)
        return await self.send_message(msg)

    async def notify_lifecycle(
        self,
        signal_id: str,
        symbol: str,
        direction: str,
        event_type: str,
        details: str
    ) -> bool:
        msg = self.format_lifecycle_update(signal_id, symbol, direction, event_type, details)
        return await self.send_message(msg)
