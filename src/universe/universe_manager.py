"""
Asset Universe Manager.
Discovers, profiles, filters, and ranks up to 50 active perpetual markets.
Tracks volume, spread, volatility, and liquidity metrics with configurable constraints.
"""
import time
import json
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from src.adapters.base import BaseExchangeAdapter
from src.core.models import Ticker
from config.settings import settings

logger = logging.getLogger(__name__)


class AssetUniverseProfile(BaseModel):
    symbol: str
    exchange: str
    price: float
    volume_24h_usd: float
    bid_ask_spread_pct: float
    daily_volatility_pct: float
    open_interest_usd: Optional[float] = None
    is_priority: bool = False
    is_qualified: bool = True
    disqualification_reason: Optional[str] = None
    liquidity_rank: int = 999
    last_updated: int = Field(default_factory=lambda: int(time.time() * 1000))


class UniverseManager:
    def __init__(self, adapter: BaseExchangeAdapter, config: Optional[Dict[str, Any]] = None):
        self.adapter = adapter
        self.max_symbols = settings.universe.max_symbols
        self.min_volume_24h_usd = settings.universe.min_24h_volume_usd
        self.max_spread_pct = settings.universe.max_spread_pct
        self.min_volatility_pct = settings.universe.min_volatility_pct
        self.min_open_interest_usd = settings.universe.min_open_interest_usd
        self.priority_symbols = list(settings.universe.priority_symbols)

        # Dynamic universe state
        self._profiles: Dict[str, AssetUniverseProfile] = {}
        self._active_symbols: List[str] = []
        self._manual_inclusions: set = set()
        self._manual_exclusions: set = set()

    def add_symbol(self, symbol: str):
        """Dynamically add a symbol to the universe."""
        self._manual_inclusions.add(symbol)
        if symbol in self._manual_exclusions:
            self._manual_exclusions.remove(symbol)
        if symbol not in self._active_symbols:
            self._active_symbols.append(symbol)

    def remove_symbol(self, symbol: str):
        """Dynamically remove a symbol from the universe."""
        self._manual_exclusions.add(symbol)
        if symbol in self._manual_inclusions:
            self._manual_inclusions.remove(symbol)
        if symbol in self._active_symbols:
            self._active_symbols.remove(symbol)

    def get_active_symbols(self) -> List[str]:
        return list(self._active_symbols)

    def get_profile(self, symbol: str) -> Optional[AssetUniverseProfile]:
        return self._profiles.get(symbol)

    def get_all_profiles(self) -> Dict[str, AssetUniverseProfile]:
        return dict(self._profiles)

    def scan_and_rebalance(self) -> List[str]:
        """
        Scans all available perpetual futures on the exchange,
        evaluates volume, spread, volatility, and returns the top ranked up to 50 assets.
        """
        logger.info(f"Scanning {self.adapter.exchange_id} markets for universe selection...")
        markets = self.adapter.load_markets()
        
        # Filter for USDT perpetual swap contracts
        eligible_symbols = []
        for sym, m in markets.items():
            if not m.get('active', True):
                continue
            is_swap = m.get('swap', False) or m.get('type') == 'swap'
            quote = m.get('quote', '')
            if is_swap and quote == 'USDT':
                eligible_symbols.append(sym)

        logger.info(f"Discovered {len(eligible_symbols)} USDT perpetual contracts.")
        
        # Fetch tickers in batch
        tickers_map: Dict[str, Ticker] = {}
        try:
            tickers_map = self.adapter.fetch_tickers()
        except Exception as e:
            logger.warning(f"Batch fetch_tickers failed ({e}), falling back to priority list.")
            for sym in self.priority_symbols:
                try:
                    tickers_map[sym] = self.adapter.fetch_ticker(sym)
                except Exception:
                    continue

        profiles: List[AssetUniverseProfile] = []
        now_ts = int(time.time() * 1000)

        for sym in eligible_symbols:
            if sym in self._manual_exclusions:
                continue

            ticker = tickers_map.get(sym)
            if not ticker:
                continue

            vol_24h_usd = ticker.quote_volume_24h
            if vol_24h_usd <= 0 and ticker.volume_24h > 0:
                vol_24h_usd = ticker.volume_24h * ticker.last

            # Volatility calculation based on 24h high/low
            mid = (ticker.high_24h + ticker.low_24h) / 2.0 if (ticker.high_24h + ticker.low_24h) > 0 else ticker.last
            volatility_pct = ((ticker.high_24h - ticker.low_24h) / mid * 100.0) if mid > 0 else 0.0
            spread_pct = ticker.spread_pct

            is_priority = sym in self.priority_symbols or sym in self._manual_inclusions
            is_qualified = True
            reason = None

            # Evaluation criteria
            if not is_priority:
                if vol_24h_usd < self.min_volume_24h_usd:
                    is_qualified = False
                    reason = f"Volume {vol_24h_usd:,.0f} < {self.min_volume_24h_usd:,.0f}"
                elif spread_pct > self.max_spread_pct:
                    is_qualified = False
                    reason = f"Spread {spread_pct:.3f}% > {self.max_spread_pct:.3f}%"
                elif volatility_pct < self.min_volatility_pct:
                    is_qualified = False
                    reason = f"Volatility {volatility_pct:.2f}% < {self.min_volatility_pct:.2f}%"

            profile = AssetUniverseProfile(
                symbol=sym,
                exchange=self.adapter.exchange_id,
                price=ticker.last,
                volume_24h_usd=vol_24h_usd,
                bid_ask_spread_pct=spread_pct,
                daily_volatility_pct=volatility_pct,
                is_priority=is_priority,
                is_qualified=is_qualified,
                disqualification_reason=reason,
                last_updated=now_ts
            )
            profiles.append(profile)

        # Rank: Priority first, then by 24h USD volume descending
        profiles.sort(key=lambda p: (not p.is_priority, not p.is_qualified, -p.volume_24h_usd))

        # Assign liquidity rank
        for idx, p in enumerate(profiles):
            p.liquidity_rank = idx + 1
            self._profiles[p.symbol] = p

        # Select top up to max_symbols
        selected_symbols = [
            p.symbol for p in profiles if (p.is_qualified or p.is_priority)
        ][:self.max_symbols]

        # Ensure priority symbols are present if on exchange
        for p_sym in self.priority_symbols:
            if p_sym in self._profiles and p_sym not in selected_symbols and len(selected_symbols) < self.max_symbols:
                selected_symbols.append(p_sym)

        self._active_symbols = selected_symbols
        logger.info(f"Asset universe successfully selected {len(self._active_symbols)} symbols.")
        return self._active_symbols
