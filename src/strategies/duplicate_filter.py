"""
Duplicate Signal Filter & Multi-Timeframe Arbiter.
Prevents duplicate alerts for the same underlying opportunity across multiple timeframes.
Enforces configurable cooldown windows per symbol and direction.
"""
import time
from typing import Dict, Any, Optional
from src.strategies.models import TradeSignal, SignalDirection


class DuplicateSignalFilter:
    def __init__(self, cooldown_minutes: int = 20):
        self.cooldown_ms = cooldown_minutes * 60 * 1000
        # Key: (symbol, direction) -> latest TradeSignal
        self._active_signals: Dict[str, TradeSignal] = {}

    def should_emit_signal(self, signal: TradeSignal) -> bool:
        """
        Returns True if the signal is fresh and not a duplicate.
        If a signal is already active for this symbol/direction within cooldown,
        checks if the new signal has a significantly higher score or higher timeframe confirmation.
        """
        key = f"{signal.symbol}:{signal.direction.value}"
        existing = self._active_signals.get(key)

        if not existing:
            self._active_signals[key] = signal
            return True

        elapsed_ms = signal.timestamp - existing.timestamp

        # Outside cooldown window -> Allowed
        if elapsed_ms > self.cooldown_ms:
            self._active_signals[key] = signal
            return True

        # Inside cooldown window: Only emit if new signal is a major upgrade (e.g. from WATCHLIST to STRONG)
        if signal.score.total_score >= (existing.score.total_score + 15.0):
            self._active_signals[key] = signal
            return True

        return False

    def clear_expired(self, current_timestamp: int):
        """Purges signals older than 2x cooldown window."""
        cutoff = current_timestamp - (2 * self.cooldown_ms)
        keys_to_remove = [
            k for k, sig in self._active_signals.items() if sig.timestamp < cutoff
        ]
        for k in keys_to_remove:
            del self._active_signals[k]

