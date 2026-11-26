"""
WEEX Exchange Adapter implementation using CCXT with custom optimizations.
Provides robust fetching of Candles, Trades, Tickers, Open Interest, and Funding Rates.
"""
import time
import ccxt
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from src.adapters.base import BaseExchangeAdapter
from src.core.models import (
    Candle, Trade, Ticker, OpenInterestRecord, FundingRateRecord,
    OrderBook, TradeSide, DataQualityStatus
)


class WeexAdapter(BaseExchangeAdapter):
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        rate_limit: bool = True,
        timeout_ms: int = 15000
    ):
        super().__init__(exchange_id="weex")
        self.client = ccxt.weex({
            'apiKey': api_key or '',
            'secret': api_secret or '',
            'password': passphrase or '',
            'enableRateLimit': rate_limit,
            'timeout': timeout_ms,
            'options': {
                'defaultType': 'swap',  # Default to perpetual swap
            }
        })
        self._markets_cache = {}

    def load_markets(self, reload: bool = False) -> Dict[str, Any]:
        if not self._markets_cache or reload:
            self._markets_cache = self.client.load_markets(reload=reload)
        return self._markets_cache

    def get_swap_symbols(self) -> List[str]:
        markets = self.load_markets()
        return [
            symbol for symbol, m in markets.items()
            if m.get('swap', False) or m.get('type') == 'swap'
        ]

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100, since: Optional[int] = None) -> List[Candle]:
        raw_candles = self.client.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
        results: List[Candle] = []
        now_ms = int(time.time() * 1000)

        # Approximate timeframe duration in ms to check if candle is closed
        tf_ms_map = {
            '1m': 60 * 1000,
            '5m': 5 * 60 * 1000,
            '15m': 15 * 60 * 1000,
            '30m': 30 * 60 * 1000,
            '1h': 60 * 60 * 1000,
            '4h': 4 * 60 * 60 * 1000,
            '1d': 24 * 60 * 60 * 1000,
        }
        candle_duration = tf_ms_map.get(timeframe, 60 * 1000)

        for c in raw_candles:
            # c: [timestamp, open, high, low, close, volume]
            ts = int(c[0])
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
            is_closed = (now_ms >= ts + candle_duration)
            
            results.append(Candle(
                symbol=symbol,
                exchange=self.exchange_id,
                timeframe=timeframe,
                timestamp=ts,
                datetime=dt,
                open=float(c[1]),
                high=float(c[2]),
                low=float(c[3]),
                close=float(c[4]),
                volume=float(c[5]),
                quote_volume=None,
                is_closed=is_closed,
                quality_status=DataQualityStatus.VALID
            ))
        return results

    def fetch_trades(self, symbol: str, limit: int = 100, since: Optional[int] = None) -> List[Trade]:
        raw_trades = self.client.fetch_trades(symbol, since=since, limit=limit)
        results: List[Trade] = []
        for t in raw_trades:
            side_raw = t.get('side', '')
            if side_raw == 'buy':
                side = TradeSide.BUY
            elif side_raw == 'sell':
                side = TradeSide.SELL
            else:
                side = TradeSide.UNKNOWN

            ts = int(t.get('timestamp') or time.time() * 1000)
            dt = t.get('datetime') or datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()

            results.append(Trade(
                id=str(t.get('id', '')),
                symbol=symbol,
                exchange=self.exchange_id,
                timestamp=ts,
                datetime=dt,
                price=float(t.get('price', 0.0)),
                amount=float(t.get('amount', 0.0)),
                cost=float(t.get('cost', 0.0)) if t.get('cost') is not None else float(t.get('price', 0.0)) * float(t.get('amount', 0.0)),
                side=side,
                is_buyer_maker=t.get('maker', None)
            ))
        return results

    def fetch_ticker(self, symbol: str) -> Ticker:
        raw = self.client.fetch_ticker(symbol)
        ts = int(raw.get('timestamp') or time.time() * 1000)
        dt = raw.get('datetime') or datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
        
        bid = float(raw.get('bid') or raw.get('last') or 0.0)
        ask = float(raw.get('ask') or raw.get('last') or 0.0)
        spread = max(0.0, ask - bid)
        mid = (ask + bid) / 2.0 if (ask + bid) > 0 else 1.0
        spread_pct = (spread / mid) * 100.0

        return Ticker(
            symbol=symbol,
            exchange=self.exchange_id,
            timestamp=ts,
            datetime=dt,
            last=float(raw.get('last') or 0.0),
            bid=bid,
            ask=ask,
            spread=spread,
            spread_pct=spread_pct,
            volume_24h=float(raw.get('baseVolume') or 0.0),
            quote_volume_24h=float(raw.get('quoteVolume') or 0.0),
            high_24h=float(raw.get('high') or 0.0),
            low_24h=float(raw.get('low') or 0.0),
            percentage_24h=float(raw.get('percentage') or 0.0),
            quality_status=DataQualityStatus.VALID
        )

    def fetch_tickers(self, symbols: Optional[List[str]] = None) -> Dict[str, Ticker]:
        raw_map = self.client.fetch_tickers(symbols)
        result = {}
        for sym, raw in raw_map.items():
            try:
                ts = int(raw.get('timestamp') or time.time() * 1000)
                dt = raw.get('datetime') or datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
                bid = float(raw.get('bid') or raw.get('last') or 0.0)
                ask = float(raw.get('ask') or raw.get('last') or 0.0)
                spread = max(0.0, ask - bid)
                mid = (ask + bid) / 2.0 if (ask + bid) > 0 else 1.0
                spread_pct = (spread / mid) * 100.0
                
                result[sym] = Ticker(
                    symbol=sym,
                    exchange=self.exchange_id,
                    timestamp=ts,
                    datetime=dt,
                    last=float(raw.get('last') or 0.0),
                    bid=bid,
                    ask=ask,
                    spread=spread,
                    spread_pct=spread_pct,
                    volume_24h=float(raw.get('baseVolume') or 0.0),
                    quote_volume_24h=float(raw.get('quoteVolume') or 0.0),
                    high_24h=float(raw.get('high') or 0.0),
                    low_24h=float(raw.get('low') or 0.0),
                    percentage_24h=float(raw.get('percentage') or 0.0),
                    quality_status=DataQualityStatus.VALID
                )
            except Exception:
                continue
        return result

    def fetch_open_interest(self, symbol: str) -> OpenInterestRecord:
        raw = self.client.fetch_open_interest(symbol)
        ts = int(raw.get('timestamp') or time.time() * 1000)
        dt = raw.get('datetime') or datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
        amount = float(raw.get('openInterestAmount') or 0.0)
        usd = float(raw.get('openInterestValue')) if raw.get('openInterestValue') is not None else None
        
        return OpenInterestRecord(
            symbol=symbol,
            exchange=self.exchange_id,
            timestamp=ts,
            datetime=dt,
            open_interest_amount=amount,
            open_interest_usd=usd,
            price_at_timestamp=None,
            quality_status=DataQualityStatus.VALID
        )

    def fetch_funding_rate(self, symbol: str) -> FundingRateRecord:
        raw = self.client.fetch_funding_rate(symbol)
        ts = int(raw.get('timestamp') or time.time() * 1000)
        dt = raw.get('datetime') or datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
        rate = float(raw.get('fundingRate') or 0.0)
        next_rate = float(raw.get('nextFundingRate')) if raw.get('nextFundingRate') is not None else None
        next_ts = int(raw.get('nextFundingTimestamp')) if raw.get('nextFundingTimestamp') is not None else None

        return FundingRateRecord(
            symbol=symbol,
            exchange=self.exchange_id,
            timestamp=ts,
            datetime=dt,
            funding_rate=rate,
            predicted_funding_rate=next_rate,
            funding_interval_hours=8,
            next_funding_timestamp=next_ts,
            percentile_30d=None,
            quality_status=DataQualityStatus.VALID
        )

    def fetch_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        raw = self.client.fetch_order_book(symbol, limit=limit)
        ts = int(raw.get('timestamp') or time.time() * 1000)
        dt = raw.get('datetime') or datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
        bids = [[float(p), float(a)] for p, a in raw.get('bids', [])[:limit]]
        asks = [[float(p), float(a)] for p, a in raw.get('asks', [])[:limit]]
        
        best_bid = bids[0][0] if bids else 0.0
        best_ask = asks[0][0] if asks else 0.0
        spread = max(0.0, best_ask - best_bid)
        mid = (best_ask + best_bid) / 2.0 if (best_ask + best_bid) > 0 else 1.0
        spread_pct = (spread / mid) * 100.0

        return OrderBook(
            symbol=symbol,
            exchange=self.exchange_id,
            timestamp=ts,
            datetime=dt,
            bids=bids,
            asks=asks,
            spread=spread,
            spread_pct=spread_pct
        )

