#!/usr/bin/env python3
"""
kalshi-trading-bot (v0.1.0)
===========================
Automated trading bot for Kalshi 15-minute crypto up/down markets
(default: BTC, series KXBTC15M).

DEFAULT STRATEGY: "Delta Capture + StochRSI Confirm"
  Enter inside a 15-min window (3-8 min remaining) only when price is already
  on your side of the strike, the contract is underpriced relative to live
  conditions, and 1-minute StochRSI confirms short-term momentum.
  (Derived from 24h Kraken BTC analysis: signal-at-window-open strategies
  backtested < 50%; the structural edge is entry timing vs. strike.)

ALTERNATIVE STRATEGIES (selectable via STRATEGY below):
  "delta_capture_scalp"   - default rules + early-window momentum scalp (50% size)
  "rsi_extreme"           - legacy threshold strategy (RSI/StochRSI filtered,
                            entry when contract price >= ENTRY_THRESHOLD)
  "multi_tf_confluence"   - multi-timeframe RSI oversold/overbought agreement
  "mean_reversion"        - Bollinger-style band break + RSI extreme
  "momentum_breakout"     - RSI midline cross with momentum
  "divergence_play"       - price/RSI divergence

MODES:
  - API keys found in ./api_keys/  -> LIVE orders (real money)
  - No API keys found              -> PAPER/TEST mode automatically
  - Set FORCE_PAPER_MODE = True to override and always paper-trade.

CHANGELOG:
  v0.1.0 (2026-07-26):
    - Project renamed to kalshi-trading-bot (all legacy branding removed).
    - Config file removed; all settings are variables at the top of this file.
    - Default entry logic replaced with Delta Capture + StochRSI Confirm.
    - Added 1-minute price feed (Kraken primary, Binance fallback) with
      rolling 60-minute deque for StochRSI/ATR computation.
    - New risk gate: 3 consecutive losses -> 60-minute pause.
    - Kept: Kalshi auth/signing, order placement, fill verification,
      emergency exits, drawdown halt, daily loss limit, CSV logging.
    - Rate-limit-safe: response caching, adaptive poll intervals, automatic
      retry with backoff on 429/5xx.
"""

import os, sys, json, time, base64, argparse, logging, csv, random, math
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from collections import deque
import threading, signal

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

# ============================================================================
# CONFIGURATION — EDIT THESE VARIABLES TO TUNE THE BOT (no config file needed)
# ============================================================================

# --- Strategy selection ---
STRATEGY = "delta_capture"        # "delta_capture" (default, recommended),
                                  # "delta_capture_scalp", "rsi_extreme",
                                  # "multi_tf_confluence", "mean_reversion",
                                  # "momentum_breakout", "divergence_play"

# --- Assets & markets ---
ASSETS = ["BTC"]                  # Any of: BTC ETH SOL XRP DOGE HYPE BNB
KALSHI_API_BASE = "https://external-api.kalshi.com"   # Production API
# KALSHI_API_BASE = "https://demo-api.kalshi.co"      # Uncomment for Kalshi demo

# --- API keys (read from subfolder) ---
API_KEYS_DIR = "api_keys"         # Folder holding apikey.json / privatekey.json
FORCE_PAPER_MODE = False          # True = paper-trade even if API keys exist

# --- Delta Capture strategy (default) — handoff Section 6 ---
DC_ENTRY_WINDOW_MIN = (3.0, 8.0)  # Only enter with 3-8 minutes left in window
DC_MIN_DELTA_PCT = 0.0002         # Min |price-strike|/strike (~0.02%, buy the winning side)
DC_MAX_DELTA_PCT = 0.0010         # Max delta — beyond this is a spike (mean-reversion risk)
DC_MAX_ENTRY_PRICE = 0.70         # Never pay more than 70c for a contract
DC_STOCH_K_LONG_MIN = 50.0        # UP entry: K must be above this...
DC_REQUIRE_K_GT_D = True          # ...and K > D (momentum confirmation)
DC_DEAD_ZONE = (45.0, 55.0)       # No-trade StochRSI K dead zone (no momentum read)
DC_ATR_MAX_PCT = 0.0005           # 1m ATR(14) above this = burst volatility, skip
DC_MAX_SPREAD_CENTS = 4           # Skip if contract spread wider than this
DC_SCALP_ENABLED = True           # Early-window momentum scalp variant
DC_SCALP_WINDOW_MIN = (12.0, 14.0)  # Minutes-left range = minutes 1-3 of window
DC_SCALP_MIN_MOVE_PCT = 0.0005    # Scalp: price must already be >=0.05% from strike
DC_SCALP_MAX_PRICE = 0.60         # Scalp: max entry price
DC_SCALP_K_UP = 60.0              # Scalp UP: K above this
DC_SCALP_K_DOWN = 40.0            # Scalp DOWN: K below this
DC_SCALP_SIZE_MULT = 0.5          # Scalp trades at half size
DC_SALVAGE_EXIT = True            # If delta flips sign with >5 min left, sell to cut loss
DC_SALVAGE_MIN_MINUTES = 5.0      # ...only if at least this many minutes remain

# --- StochRSI indicator settings (1-minute closes) ---
RSI_LEN = 14                      # RSI period
STOCH_LEN = 14                    # Stochastic lookback over RSI
STOCH_K_SMOOTH = 3                # %K = SMA(3) of raw stoch
STOCH_D_SMOOTH = 3                # %D = SMA(3) of %K
ATR_LEN = 14                      # ATR period on 1m candles
PRICE_HISTORY_MINUTES = 90        # Rolling 1m candle buffer (>= RSI+STOCH+smoothing)

# --- Legacy "rsi_extreme" strategy settings ---
ENTRY_THRESHOLD = 0.72            # Enter when contract ask >= this (strong favorite)
EXIT_THRESHOLD = 0.65             # Stop-loss floor reference
RSI_MIN_FOR_UP = 42.0             # 1m RSI must be above this to buy UP
RSI_MAX_FOR_DOWN = 58.0           # 1m RSI must be below this to buy DOWN
STOCH_OVERBOUGHT = 80.0           # Block UP if 1m StochRSI above this
STOCH_OVERSOLD = 20.0             # Block DOWN if 1m StochRSI below this
REQUIRE_1H_ALIGNMENT = True       # Block entries fighting the 1h RSI trend
MIN_TIMEFRAME_AGREEMENT = 2       # Min RSI timeframes agreeing with the side
ENTRY_CONFIRMATION_CYCLES = 3     # Same side must persist N eval cycles
MAX_PRICE_VELOCITY = 0.10         # Block entries after >$0.10 move in 60s

# --- Legacy indicator-strategy settings (multi_tf / mean_reversion / etc.) ---
RSI_PERIOD = 14
RSI_OVERSOLD = 30.0
RSI_OVERBOUGHT = 70.0
RSI_DIVERGENCE_THRESHOLD = 5.0

# --- Position sizing ---
ORDER_SIZE = 1                    # Contracts per trade (hard cap: MAX_ORDER_SIZE)
MAX_ORDER_SIZE = 1                # Hard safety cap — never exceed
MAX_RISK_PER_TRADE_PCT = 2.0      # Cap per-trade risk at 2% of bankroll
MAX_CONCURRENT_POSITIONS = 3

# --- Risk gates ---
BANKROLL = 1000.0                 # Fallback bankroll if API balance unavailable
MAX_DAILY_LOSS = 10.0             # Halt for the day beyond this loss ($)
MAX_DRAWDOWN_PERCENT = 15.0       # Halt if daily loss exceeds this % of balance
MAX_CONSECUTIVE_LOSSES = 3        # After N straight losses...
PAUSE_AFTER_LOSS_STREAK_MIN = 60  # ...pause this many minutes
MAX_LOSS_PER_SESSION = 2.0        # Per-window session loss cap ($)
MAX_TRADES_PER_SESSION = 1        # Trades allowed per 15-min window
POST_TRADE_COOLDOWN_SECONDS = 90

# --- Exit management (binary: default is hold to settlement) ---
PROFIT_TARGET = 0.92              # Take profit if contract reaches this
MAX_LOSS_PER_TRADE = 0.15         # Early time-stop loss threshold ($/contract)
EARLY_TIME_STOP_SECONDS = 90      # ...evaluated after this hold time
TIME_EXIT_MINUTES = 3.0           # Force exit this many minutes before close
EMERGENCY_EXIT_PRICE = 0.05       # Marketable-limit floor for emergency exits
STOP_LOSS_FLOOR_PRICE = 0.15      # Marketable-limit floor for stop-loss exits
TRAILING_STOP_PCT = 0.35          # Give back at most 35% of peak profit
MIN_PROFIT_FOR_TRAILING = 0.08    # Trailing activates above this peak profit
MIN_HOLD_SECONDS = 45             # Min hold before dynamic exits
BREAKEVEN_TRIGGER_PROFIT = 0.06   # Move stop to breakeven above this profit
BREAKEVEN_BUFFER = 0.02
MAX_HOLD_TIME_SECONDS = 180       # Hard max hold (legacy strategies)
NO_ENTRY_FINAL_SECONDS = 120      # Never enter this close to settlement

# --- Order execution ---
BUY_PRICE_DIFF = 0.02             # Extra cents over ask when AGGRESSIVE_ENTRY
AGGRESSIVE_ENTRY = False
FILL_BUFFER = 0.02                # Limit buffer to improve fill odds
DYNAMIC_FILL_BUFFER = True        # Scale buffer with live spread
ENTRY_TIME_IN_FORCE = "good_till_canceled"   # or "immediate_or_cancel"
ORDER_TIMEOUT_SECONDS = 15

# --- Polling / rate-limit safety (do not lower; Kalshi + exchange limits) ---
POLL_INTERVAL_MONITORING_S = 1.0  # Loop cadence while in/near a position
POLL_INTERVAL_RELAXED_S = 3.0     # Loop cadence while idle
PRICE_POLL_SECONDS = 8            # 1m price feed poll (handoff suggests 5-10s)
MARKET_REFRESH_MS = 5000          # Kalshi market snapshot cache
KLINES_CACHE_TTL_S = 30           # Exchange kline cache
BALANCE_CACHE_TTL_S = 60          # Balance cache
PRETTY_DISPLAY = False            # True = live terminal dashboard

# ============================================================================
# INTERNALS BELOW — normally no need to edit
# ============================================================================

ASSET_SERIES_MAP = {
    "BTC": "KXBTC15M", "ETH": "KXETH15M", "SOL": "KXSOL15M",
    "XRP": "KXXRP15M", "DOGE": "KXDOGE15M", "HYPE": "KXHYPE15M", "BNB": "KXBNB15M"
}
ASSET_SYMBOL_MAP = {   # Exchange spot symbols (Kraken pair, Binance symbol)
    "BTC": ("XBTUSD", "BTCUSDT"), "ETH": ("ETHUSD", "ETHUSDT"),
    "SOL": ("SOLUSD", "SOLUSDT"), "XRP": ("XRPUSD", "XRPUSDT"),
    "DOGE": ("DOGEUSD", "DOGEUSDT"), "HYPE": ("HYPEUSD", "HYPEUSDT"),
    "BNB": ("BNBUSD", "BNBUSDT"),
}


# ============================================================================
# LOGGING
# ============================================================================
def setup_logging(log_dir: str = "logs", pretty_display: bool = False):
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"kalshi_bot_{ts}.log")
    trade_file = os.path.join(log_dir, f"trades_{ts}.csv")
    perf_file = os.path.join(log_dir, f"perf_{ts}.csv")
    logger = logging.getLogger("kalshi_bot")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.WARNING if pretty_display else logging.INFO)
    console.setFormatter(logging.Formatter('%(asctime)s | %(message)s', '%Y-%m-%d %H:%M:%S'))
    logger.addHandler(console)
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
    logger.addHandler(fh)
    for f, headers in [
        (trade_file, ['Timestamp', 'Asset', 'Side', 'EntryPrice', 'ExitPrice', 'Reason', 'PnL', 'Ticker', 'Session', 'Strategy']),
        (perf_file, ['Timestamp', 'Asset', 'TotalTrades', 'Wins', 'Losses', 'WinRate', 'TotalPnL', 'ConsecutiveLosses'])]:
        with open(f, 'w', newline='') as out:
            csv.writer(out).writerow(headers)
    return logger, log_file, trade_file, perf_file


# ============================================================================
# KALSHI API (RSA-signed, v2 field names, 429/5xx retry with backoff)
# ============================================================================
class KalshiAPI:
    def __init__(self, api_key_id: str = "", private_key_path: str = "", api_base: str = ""):
        self.api_base = api_base
        self.api_key_id = api_key_id
        self.private_key_path = private_key_path
        self.session = requests.Session()
        # Respect rate limits: automatic retry with exponential backoff on 429/5xx
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._private_key_cache: Optional[str] = None
        self._load_credentials()

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key_id) and bool(self.private_key_path) and os.path.exists(self.private_key_path)

    def _load_credentials(self):
        logger = logging.getLogger("kalshi_bot")
        if self.api_key_id and self.private_key_path:
            return
        is_demo = "demo" in self.api_base.lower()
        key_files = ["apikey_demo.json", "apikey.json"] if is_demo else ["apikey.json", "apikey_demo.json"]
        pk_files = ["privatekey_demo.json", "privatekey.json"] if is_demo else ["privatekey.json", "privatekey_demo.json"]
        search_dirs = [API_KEYS_DIR, "."]
        if not self.api_key_id:
            for d in search_dirs:
                for name in key_files:
                    path = os.path.join(d, name)
                    if os.path.exists(path):
                        try:
                            raw = open(path).read().strip()
                            try:
                                data = json.loads(raw)
                                self.api_key_id = (data.get('code', '') if isinstance(data, dict) else str(data)).strip()
                            except json.JSONDecodeError:
                                self.api_key_id = raw
                            if self.api_key_id:
                                logger.info(f"API key loaded from {path}")
                                break
                        except Exception as e:
                            logger.debug(f"Failed reading {path}: {e}")
                if self.api_key_id:
                    break
        if not self.private_key_path or not os.path.exists(self.private_key_path):
            for d in search_dirs:
                for name in pk_files:
                    path = os.path.join(d, name)
                    if os.path.exists(path):
                        self.private_key_path = path
                        logger.info(f"Private key loaded from {path}")
                        break
                if self.private_key_path and os.path.exists(self.private_key_path):
                    break

    def _load_private_key(self) -> str:
        if self._private_key_cache is not None:
            return self._private_key_cache
        if not self.private_key_path or not os.path.exists(self.private_key_path):
            return ""
        try:
            raw = open(self.private_key_path).read().strip()
            try:
                data = json.loads(raw)
                key = data.get('code', '') if isinstance(data, dict) else str(data)
            except json.JSONDecodeError:
                key = raw
            self._private_key_cache = key.replace(r'\/', '/')
        except Exception as e:
            logging.getLogger("kalshi_bot").warning(f"Failed to read private key: {e}")
            self._private_key_cache = ""
        return self._private_key_cache

    def _sign_request(self, method: str, path: str) -> Tuple[str, str]:
        timestamp = str(int(time.time() * 1000))
        message = timestamp + method + path.split('?')[0]
        private_key = self._load_private_key()
        if not private_key:
            return timestamp, ""
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            key = serialization.load_pem_private_key(private_key.encode(), password=None)
            signature = key.sign(
                message.encode('utf-8'),
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                hashes.SHA256()
            )
            return timestamp, base64.b64encode(signature).decode()
        except Exception as e:
            logging.getLogger("kalshi_bot").warning(f"Signing failed: {e}")
            return timestamp, ""

    def request(self, method: str, endpoint: str, params: dict = None, body: dict = None, authenticated: bool = True) -> dict:
        url = f"{self.api_base}{endpoint}"
        body_str = json.dumps(body) if body else ""
        headers = {"User-Agent": "kalshi-trading-bot/6.0", "Accept": "application/json", "Content-Type": "application/json"}
        if authenticated and self.api_key_id:
            timestamp, signature = self._sign_request(method, endpoint)
            headers["KALSHI-ACCESS-KEY"] = self.api_key_id
            headers["KALSHI-ACCESS-TIMESTAMP"] = timestamp
            if signature:
                headers["KALSHI-ACCESS-SIGNATURE"] = signature
        try:
            response = self.session.request(method=method, url=url, params=params,
                                            data=body_str if body else None, headers=headers, timeout=30)
            response.raise_for_status()
            return {"status": response.status_code, "data": response.json()}
        except requests.exceptions.HTTPError as e:
            try:
                error_body = response.json()
            except Exception:
                error_body = {"text": response.text[:500]}
            return {"status": response.status_code, "error": str(e), "data": {}, "response_body": error_body}
        except requests.exceptions.RequestException as e:
            return {"status": 0, "error": str(e), "data": {}}

    def get_markets(self, series_ticker: str, status: str = "open", limit: int = 1) -> List[dict]:
        r = self.request("GET", "/trade-api/v2/markets",
                         params={"series_ticker": series_ticker, "status": status, "limit": limit},
                         authenticated=False)
        return r.get("data", {}).get("markets", [])

    def get_orderbook(self, ticker: str, depth: int = 3) -> dict:
        r = self.request("GET", f"/trade-api/v2/markets/{ticker}/orderbook",
                         params={"depth": depth}, authenticated=False)
        return r.get("data", {})

    def get_balance(self) -> dict:
        return self.request("GET", "/trade-api/v2/portfolio/balance")

    def get_positions(self, ticker: str = None) -> List[dict]:
        params = {"ticker": ticker} if ticker else {}
        for endpoint in ["/trade-api/v2/portfolio/positions", "/trade-api/v2/portfolio/events/positions"]:
            r = self.request("GET", endpoint, params=params)
            data = r.get("data", {})
            positions = []
            if isinstance(data, list):
                positions = data
            elif isinstance(data, dict):
                for key in ["positions", "market_positions", "event_positions", "results", "data"]:
                    if key in data and isinstance(data[key], list):
                        positions = data[key]
                        break
                    elif key in data and isinstance(data[key], dict) and "positions" in data[key]:
                        positions = data[key]["positions"]
                        break
            if positions:
                return positions
        return []

    def get_fills(self, order_id: str = None, ticker: str = None, try_fallback: bool = True) -> list:
        params = {}
        if order_id: params["order_id"] = order_id
        if ticker: params["ticker"] = ticker
        r = self.request("GET", "/trade-api/v2/portfolio/fills", params=params)
        data = r.get("data", {})
        fills = data.get("fills", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not fills and try_fallback:
            r2 = self.request("GET", "/trade-api/v2/portfolio/events/fills", params=params)
            data2 = r2.get("data", {})
            fills = data2.get("fills", []) if isinstance(data2, dict) else (data2 if isinstance(data2, list) else [])
        return fills

    def get_order(self, order_id: str) -> dict:
        for endpoint in [f"/trade-api/v2/portfolio/orders/{order_id}",
                         f"/trade-api/v2/portfolio/events/orders/{order_id}"]:
            r = self.request("GET", endpoint)
            data = r.get("data", {})
            if isinstance(data, dict) and (data.get("order") or data.get("order_id") or data.get("status")):
                return data.get("order", data)
            if isinstance(data, dict) and any(k in data for k in ["status", "filled_count", "count", "ticker"]):
                return data
        return {}

    def place_order(self, ticker: str, action: str, side: str, count: int, price: int,
                    order_type: str = "limit", reduce_only: bool = False,
                    time_in_force: str = None, client_order_id: str = None) -> dict:
        is_buy = action.lower() == "buy"
        is_yes = side == "yes"
        v2_side = "bid" if (is_buy == is_yes) else "ask"
        v2_price_cents = (100 - price) if side == "no" else price
        tif = time_in_force or ("immediate_or_cancel" if reduce_only else "good_till_canceled")
        payload = {
            "ticker": ticker, "side": v2_side, "count": f"{count:.2f}",
            "price": f"{v2_price_cents / 100:.4f}", "time_in_force": tif,
            "self_trade_prevention_type": "taker_at_cross",
        }
        if reduce_only:
            payload["reduce_only"] = True
        if client_order_id:
            payload["client_order_id"] = client_order_id
        return self.request("POST", "/trade-api/v2/portfolio/events/orders", body=payload)

    def cancel_order(self, order_id: str) -> dict:
        return self.request("DELETE", f"/trade-api/v2/portfolio/events/orders/{order_id}")


# ============================================================================
# PRICE FEED — 1-minute candles (Kraken primary, Binance fallback)
# Polls every PRICE_POLL_SECONDS into a rolling deque; rate-limit safe.
# ============================================================================
class PriceFeed:
    KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"
    BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"

    def __init__(self, asset: str):
        self.asset = asset
        self.kraken_pair, self.binance_symbol = ASSET_SYMBOL_MAP.get(asset, ("XBTUSD", "BTCUSDT"))
        self.session = requests.Session()
        retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        # Rolling buffer of 1-minute candles: (minute_ts, open, high, low, close)
        self.candles: deque = deque(maxlen=PRICE_HISTORY_MINUTES)
        self._last_poll = 0.0
        self._last_price = 0.0
        self._kline_cache: Dict[str, Tuple[float, Any]] = {}

    def poll(self) -> float:
        """Poll spot price at most every PRICE_POLL_SECONDS; returns last price."""
        now = time.time()
        if now - self._last_poll < PRICE_POLL_SECONDS:
            return self._last_price
        self._last_poll = now
        candles = self._fetch_kraken() or self._fetch_binance()
        if candles:
            for c in candles:
                if not self.candles or c[0] > self.candles[-1][0]:
                    self.candles.append(c)
                elif c[0] == self.candles[-1][0]:
                    self.candles[-1] = c  # Update the still-forming current candle
            self._last_price = self.candles[-1][4]
        return self._last_price

    def _fetch_kraken(self) -> List[Tuple[int, float, float, float, float]]:
        try:
            r = self.session.get(self.KRAKEN_URL,
                                 params={"pair": self.kraken_pair, "interval": 1}, timeout=10)
            r.raise_for_status()
            result = r.json().get("result", {})
            rows = result.get(self.kraken_pair) or next((v for k, v in result.items() if k != "last"), [])
            return [(int(row[0]) // 60 * 60, float(row[1]), float(row[2]), float(row[3]), float(row[4]))
                    for row in rows[-PRICE_HISTORY_MINUTES:]]
        except Exception as e:
            logging.getLogger("kalshi_bot").debug(f"Kraken fetch failed: {e}")
            return []

    def _fetch_binance(self) -> List[Tuple[int, float, float, float, float]]:
        try:
            r = self.session.get(self.BINANCE_URL,
                                 params={"symbol": self.binance_symbol, "interval": "1m",
                                         "limit": PRICE_HISTORY_MINUTES}, timeout=10)
            r.raise_for_status()
            return [(int(k[0]) // 60000 * 60, float(k[1]), float(k[2]), float(k[3]), float(k[4]))
                    for k in r.json()]
        except Exception as e:
            logging.getLogger("kalshi_bot").debug(f"Binance fetch failed: {e}")
            return []

    def get_klines_15m(self, limit: int = 50) -> List[list]:
        """15-minute klines for legacy strategies (Binance, cached KLINES_CACHE_TTL_S)."""
        key = f"15m:{limit}"
        now = time.time()
        if key in self._kline_cache and now - self._kline_cache[key][0] < KLINES_CACHE_TTL_S:
            return self._kline_cache[key][1]
        try:
            r = self.session.get(self.BINANCE_URL,
                                 params={"symbol": self.binance_symbol, "interval": "15m", "limit": limit},
                                 timeout=10)
            r.raise_for_status()
            data = r.json()
            self._kline_cache[key] = (now, data)
            return data
        except Exception:
            return self._kline_cache.get(key, (0, []))[1]

    # --- Indicator math (1m closes) ---
    @staticmethod
    def rsi_series(closes: List[float], period: int) -> List[float]:
        if len(closes) < period + 1:
            return [50.0] * len(closes)
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(d, 0) for d in deltas]
        losses = [max(-d, 0) for d in deltas]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        out = [50.0] * period
        for i in range(period, len(closes)):
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
            out.append(100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss)))
        return out

    @staticmethod
    def sma(values: List[float], period: int) -> List[float]:
        if len(values) < period:
            return []
        return [sum(values[i - period:i]) / period for i in range(period, len(values) + 1)]

    def stoch_rsi_kd(self) -> Tuple[float, float]:
        """Returns (%K, %D) on 1m closes. Defaults to (50, 50) if insufficient data."""
        closes = [c[4] for c in self.candles]
        need = RSI_LEN + STOCH_LEN + STOCH_K_SMOOTH + STOCH_D_SMOOTH
        if len(closes) < need:
            return 50.0, 50.0
        rsi = self.rsi_series(closes, RSI_LEN)
        raw = []
        for i in range(STOCH_LEN, len(rsi) + 1):
            window = rsi[i - STOCH_LEN:i]
            lo, hi = min(window), max(window)
            raw.append(50.0 if hi == lo else 100.0 * (rsi[i - 1] - lo) / (hi - lo))
        k_series = self.sma(raw, STOCH_K_SMOOTH)
        d_series = self.sma(k_series, STOCH_D_SMOOTH)
        if not k_series or not d_series:
            return 50.0, 50.0
        return k_series[-1], d_series[-1]

    def atr_pct(self) -> float:
        """1m ATR(ATR_LEN) as a fraction of price."""
        rows = list(self.candles)
        if len(rows) < ATR_LEN + 1:
            return 0.0
        trs = []
        for i in range(1, len(rows)):
            h, l, pc = rows[i][2], rows[i][3], rows[i - 1][4]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr = sum(trs[-ATR_LEN:]) / ATR_LEN
        price = rows[-1][4]
        return atr / price if price > 0 else 0.0

    def window_strike(self) -> Optional[float]:
        """Strike = close of the 1m candle that opened the current 15-min window."""
        now = datetime.now(timezone.utc)
        window_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
        # Strike is the close of the candle one minute before window start,
        # i.e. the price AT window open.
        target_ts = int(window_start.timestamp()) - 60
        for c in reversed(self.candles):
            if c[0] <= target_ts:
                return c[4]
        return None


# ============================================================================
# STRATEGY ENGINE
# Default: Delta Capture + StochRSI Confirm (handoff Section 4-5).
# Legacy strategies retained and selectable via STRATEGY variable.
# ============================================================================
@dataclass
class EntryDecision:
    side: str            # "UP" or "DOWN"
    reason: str
    size_mult: float = 1.0


class StrategyEngine:
    def __init__(self, feed: PriceFeed):
        self.feed = feed

    # --- DEFAULT: Delta Capture + StochRSI Confirm ---
    def delta_capture(self, price: float, strike: float, mins_left: float,
                      ask_up: float, ask_down: float, spread_cents: float) -> Optional[EntryDecision]:
        k, d = self.feed.stoch_rsi_kd()
        atr = self.feed.atr_pct()

        # No-trade gates (apply to both entries and the scalp variant)
        if atr > DC_ATR_MAX_PCT:
            return None                                   # Burst volatility / whipsaw
        if spread_cents > DC_MAX_SPREAD_CENTS:
            return None                                   # Spread too wide
        if DC_DEAD_ZONE[0] <= k <= DC_DEAD_ZONE[1]:
            return None                                   # StochRSI dead zone

        delta = (price - strike) / strike if strike > 0 else 0.0

        # Momentum scalp variant: minutes 1-3 of window, price already moving
        if DC_SCALP_ENABLED and DC_SCALP_WINDOW_MIN[0] <= mins_left <= DC_SCALP_WINDOW_MIN[1]:
            if abs(delta) >= DC_SCALP_MIN_MOVE_PCT and abs(delta) <= DC_MAX_DELTA_PCT:
                if delta > 0 and k > DC_SCALP_K_UP and k >= d and ask_up <= DC_SCALP_MAX_PRICE:
                    return EntryDecision("UP", f"scalp delta={delta:.4%} K={k:.0f}", DC_SCALP_SIZE_MULT)
                if delta < 0 and k < DC_SCALP_K_DOWN and k <= d and ask_down <= DC_SCALP_MAX_PRICE:
                    return EntryDecision("DOWN", f"scalp delta={delta:.4%} K={k:.0f}", DC_SCALP_SIZE_MULT)
            return None  # Outside scalp conditions in early window = no trade

        # Core entry: 3-8 minutes remaining
        lo, hi = DC_ENTRY_WINDOW_MIN
        if not (lo <= mins_left <= hi):
            return None
        if abs(delta) > DC_MAX_DELTA_PCT or abs(delta) < DC_MIN_DELTA_PCT:
            return None
        if delta >= DC_MIN_DELTA_PCT and k > DC_STOCH_K_LONG_MIN and (not DC_REQUIRE_K_GT_D or k >= d):
            if ask_up <= DC_MAX_ENTRY_PRICE:
                return EntryDecision("UP", f"delta={delta:.4%} K={k:.0f}>=D={d:.0f} ask={ask_up:.2f}")
        if delta <= -DC_MIN_DELTA_PCT and k < (100 - DC_STOCH_K_LONG_MIN) and (not DC_REQUIRE_K_GT_D or k <= d):
            if ask_down <= DC_MAX_ENTRY_PRICE:
                return EntryDecision("DOWN", f"delta={delta:.4%} K={k:.0f}<D={d:.0f} ask={ask_down:.2f}")
        return None

    # --- LEGACY strategies (15m klines) ---
    def legacy_signal(self, strategy: str) -> Optional[EntryDecision]:
        klines = self.feed.get_klines_15m(limit=50)
        if not klines or len(klines) < 20:
            return None
        closes = [float(k[4]) for k in klines]
        rsi = self.feed.rsi_series(closes, RSI_PERIOD)
        cur = rsi[-1] if rsi else 50.0

        if strategy == "multi_tf_confluence":
            if cur < RSI_OVERSOLD:
                return EntryDecision("UP", f"15m RSI oversold {cur:.1f}")
            if cur > RSI_OVERBOUGHT:
                return EntryDecision("DOWN", f"15m RSI overbought {cur:.1f}")

        elif strategy == "mean_reversion":
            sma = self.feed.sma(closes, 20)
            if sma:
                window = closes[-20:]
                mean = sma[-1]
                std = math.sqrt(sum((x - mean) ** 2 for x in window) / 20)
                if closes[-1] < mean - 2 * std and cur < RSI_OVERSOLD:
                    return EntryDecision("UP", f"below lower band, RSI {cur:.1f}")
                if closes[-1] > mean + 2 * std and cur > RSI_OVERBOUGHT:
                    return EntryDecision("DOWN", f"above upper band, RSI {cur:.1f}")

        elif strategy == "momentum_breakout":
            if len(rsi) >= 2:
                prev, mom = rsi[-2], cur - rsi[-2]
                if prev < 50 < cur and mom > 3:
                    return EntryDecision("UP", f"RSI crossed 50 (+{mom:.1f})")
                if prev > 50 > cur and -mom > 3:
                    return EntryDecision("DOWN", f"RSI crossed below 50 ({mom:.1f})")

        elif strategy == "divergence_play":
            if len(closes) >= 20 and len(rsi) >= 10:
                rp, rr = closes[-10:], rsi[-10:]
                p1, p2 = sum(rp[:5]) / 5, sum(rp[5:]) / 5
                r1, r2 = sum(rr[:5]) / 5, sum(rr[5:]) / 5
                if p2 < p1 and r2 - r1 >= RSI_DIVERGENCE_THRESHOLD:
                    return EntryDecision("UP", f"bullish divergence {r2 - r1:.1f}")
                if p2 > p1 and r1 - r2 >= RSI_DIVERGENCE_THRESHOLD:
                    return EntryDecision("DOWN", f"bearish divergence {r1 - r2:.1f}")
        return None


# ============================================================================
# STATE
# ============================================================================
@dataclass
class Position:
    asset: str
    side: str
    entry_price: float
    ticker: str
    size: int
    entry_time: datetime
    entry_order_id: str = ""
    strategy: str = ""
    max_pnl: float = 0.0
    stop_loss: float = 0.0
    highest_price: float = 0.0
    breakeven_active: bool = False


@dataclass
class AssetState:
    phase: str = "WAIT_WINDOW"     # WAIT_WINDOW MONITORING IN_POSITION EMERGENCY_EXIT HAS_POSITION
    session_key: str = ""
    consecutive_losses: int = 0
    loss_pause_until: float = 0.0
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    total_pnl: float = 0.0
    session_trade_count: int = 0
    session_pnl: float = 0.0
    last_trade_close_time: float = 0.0
    last_order_time: float = 0.0
    pending_order_id: str = ""
    entry_attempts: int = 0
    last_reconcile_time: float = 0.0
    confirmation_count: int = 0
    last_proposed_side: str = ""
    price_history: deque = field(default_factory=lambda: deque(maxlen=20))


# ============================================================================
# MAIN BOT
# ============================================================================
class KalshiTradingBot:
    def __init__(self, logger: logging.Logger, trade_file: str, perf_file: str,
                 live_orders: bool, pretty_display: bool = False):
        self.logger = logger
        self.trade_file = trade_file
        self.perf_file = perf_file
        self.live_orders = live_orders
        self.pretty_display = pretty_display
        self.api = KalshiAPI(api_base=KALSHI_API_BASE)
        self.feeds: Dict[str, PriceFeed] = {a: PriceFeed(a) for a in ASSETS}
        self.engines: Dict[str, StrategyEngine] = {a: StrategyEngine(self.feeds[a]) for a in ASSETS}
        self.positions: Dict[str, Position] = {}
        self.states: Dict[str, AssetState] = {a: AssetState() for a in ASSETS}
        self.active_orders: Dict[str, dict] = {}
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.last_daily_reset = ""
        self.log_once_keys: set = set()
        self.running = True
        self._pos_cache: Dict[str, Tuple[bool, float]] = {}
        self._balance_cache: Tuple[float, float] = (0.0, 0.0)
        self._snapshot_cache: Dict[str, Tuple[float, dict]] = {}
        self.display_data: Dict[str, dict] = {}
        self._display_lock = threading.Lock()
        if self.pretty_display:
            threading.Thread(target=self._display_loop, daemon=True).start()

    # ------------------------------ helpers ------------------------------
    def log(self, msg: str, level: int = logging.INFO):
        self.logger.log(level, msg)

    def log_once(self, key: str, msg: str):
        if key not in self.log_once_keys:
            self.log_once_keys.add(key)
            self.log(msg)

    def _parse_price(self, v) -> float:
        if v is None: return 0.0
        if isinstance(v, (int, float)):
            return v / 100.0 if v > 1 else float(v)
        try: return float(v)
        except (ValueError, TypeError): return 0.0

    def _safe_float(self, v) -> float:
        try: return float(v)
        except (TypeError, ValueError): return 0.0

    def minutes_left(self, close_time_str: str) -> float:
        if close_time_str:
            try:
                ct = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                return max(0.0, (ct - datetime.now(timezone.utc)).total_seconds() / 60.0)
            except Exception:
                pass
        now = datetime.now(timezone.utc)
        return 15 - (now.minute % 15) - now.second / 60.0

    # ------------------------------ market data ------------------------------
    def get_snapshot(self, asset: str) -> Optional[dict]:
        now = time.time() * 1000
        cached = self._snapshot_cache.get(asset)
        if cached and now - cached[0] < MARKET_REFRESH_MS and cached[1].get("minutes_left", 0) > 0.5:
            return cached[1]
        series = ASSET_SERIES_MAP.get(asset)
        if not series:
            return None
        markets = self.api.get_markets(series, status="open", limit=1)
        if not markets:
            return None
        m = markets[0]
        ticker = m.get("ticker", "")
        if not ticker:
            return None
        yes_bid, yes_ask, no_bid, no_ask = self._orderbook_best(ticker)
        up = yes_ask or self._parse_price(m.get("yes_ask_dollars", m.get("yes_ask")))
        down = no_ask or self._parse_price(m.get("no_ask_dollars", m.get("no_ask")))
        if up <= 0: up = self._parse_price(m.get("last_price_dollars", m.get("last_price")))
        if up <= 0 and down > 0: up = 1.0 - down
        if down <= 0 and up > 0: down = 1.0 - up
        snap = {"ticker": ticker, "up": up, "down": down,
                "up_bid": yes_bid, "up_ask": yes_ask, "down_bid": no_bid, "down_ask": no_ask,
                "minutes_left": self.minutes_left(m.get("close_time", "")),
                "status": m.get("status", "open")}
        self._snapshot_cache[asset] = (now, snap)
        return snap

    def _orderbook_best(self, ticker: str) -> Tuple[float, float, float, float]:
        ob = self.api.get_orderbook(ticker, depth=3)

        def extract(arr):
            out = []
            for p in arr or []:
                if isinstance(p, (list, tuple)) and p:
                    v = float(p[0]); out.append(v / 100.0 if v > 1 else v)
                elif isinstance(p, dict):
                    v = float(p.get("price", 0)); out.append(v / 100.0 if v > 1 else v)
            return out

        yes_bid = no_bid = 0.0
        fp = ob.get("orderbook_fp", {})
        std = ob.get("orderbook", {})
        for src, yk, nk in ((fp, "yes_dollars", "no_dollars"), (std, "yes", "no")):
            yp, np_ = extract(src.get(yk, [])), extract(src.get(nk, []))
            if yp: yes_bid = max(yes_bid, max(yp))
            if np_: no_bid = max(no_bid, max(np_))
        yes_ask = 1.0 - no_bid if no_bid > 0 else 0.0
        no_ask = 1.0 - yes_bid if yes_bid > 0 else 0.0
        # Coherence check: bids and asks must each sum ~1.0
        if yes_bid > 0 and no_bid > 0 and abs(yes_bid + no_bid - 1.0) > 0.05:
            return 0.0, 0.0, 0.0, 0.0
        return yes_bid, yes_ask, no_bid, no_ask

    def _get_balance(self) -> float:
        now = time.time()
        bal, ts = self._balance_cache
        if now - ts < BALANCE_CACHE_TTL_S and ts > 0:
            return bal
        r = self.api.get_balance()
        bal = self._safe_float(r.get("data", {}).get("balance", 0)) if r.get("status") == 200 else 0.0
        if bal > 100:  # some API versions return cents
            bal /= 100.0
        self._balance_cache = (bal, now)
        return bal

    def has_existing_position(self, ticker: str, force: bool = False) -> bool:
        now = time.time()
        if not force and ticker in self._pos_cache and now - self._pos_cache[ticker][1] < 5:
            return self._pos_cache[ticker][0]
        result = False
        for pos in self.api.get_positions():
            pt = pos.get("ticker", pos.get("market_ticker", pos.get("event_ticker", "")))
            if pt and pt != ticker:
                continue
            size = 0.0
            for key in ["position", "count", "size", "position_fp", "count_fp", "quantity", "contracts"]:
                if key in pos and pos[key] is not None:
                    size = self._safe_float(pos[key])
                    if size != 0:
                        break
            if abs(size) > 0:
                result = True
                break
        self._pos_cache[ticker] = (result, now)
        return result

    # ------------------------------ orders ------------------------------
    def _parse_fills_price(self, fills: list) -> Tuple[float, float]:
        total_count = total_cost = 0.0
        for f in fills:
            count = 0.0
            for ck in ["filled_count", "count", "size", "count_fp", "quantity", "contracts"]:
                if ck in f and f[ck] is not None:
                    count = self._safe_float(f[ck]); break
            price = 0.0
            for pk in ["price", "filled_price", "avg_price", "price_dollars", "yes_price", "no_price"]:
                if pk in f and f[pk] is not None:
                    price = self._safe_float(f[pk])
                    if price > 0: break
            if price > 1.0: price /= 100.0
            total_count += count
            total_cost += count * price
        return total_count, (total_cost / total_count if total_count > 0 else 0.0)

    def _order_fill_price(self, info: dict) -> float:
        for key in ["avg_price", "filled_price", "price", "price_dollars", "yes_price", "no_price"]:
            if key in info and info[key] is not None:
                v = self._safe_float(info[key])
                if v > 0:
                    return v / 100.0 if v > 1.0 else v
        return 0.0

    def verify_fill(self, order_id: str, ticker: str, expected: int, tif: str) -> Tuple[bool, float]:
        if not self.live_orders:
            return True, 0.0
        is_ioc = tif.lower() in ("immediate_or_cancel", "ioc")
        deadline = time.time() + (3 if is_ioc else ORDER_TIMEOUT_SECONDS)
        while time.time() < deadline:
            info = self.api.get_order(order_id)
            status = str(info.get("status", "")).lower()
            if status == "filled":
                price = self._order_fill_price(info)
                if price <= 0:
                    _, price = self._parse_fills_price(self.api.get_fills(order_id=order_id, ticker=ticker))
                return True, price
            if status in ("cancelled", "rejected", "expired"):
                filled, price = self._parse_fills_price(self.api.get_fills(order_id=order_id, ticker=ticker))
                return (filled >= expected * 0.95), price
            if not info and self.has_existing_position(ticker, force=True):
                return True, 0.0
            time.sleep(0.5 if is_ioc else 1.0)
        # Final fallbacks
        if self.has_existing_position(ticker, force=True):
            return True, 0.0
        filled, price = self._parse_fills_price(self.api.get_fills(order_id=order_id, ticker=ticker))
        return (filled >= expected * 0.95), price

    def place_buy(self, asset: str, ticker: str, side: str, price: float, size: int) -> Tuple[Optional[str], float]:
        if not self.live_orders:
            return "paper-order", price
        if self.has_existing_position(ticker):
            return None, 0.0
        yes_bid, yes_ask, no_bid, no_ask = self._orderbook_best(ticker)
        spread = (yes_ask - yes_bid) if yes_ask > 0 and yes_bid > 0 else 0.0
        buf = max(FILL_BUFFER, spread * 0.6) if DYNAMIC_FILL_BUFFER and spread > 0 else FILL_BUFFER
        extra = BUY_PRICE_DIFF if AGGRESSIVE_ENTRY else 0.0
        if side == "UP":
            base = yes_ask if yes_ask > 0 else price
            cents = max(1, min(99, int(round(min(base + buf + extra, 0.99) * 100))))
        else:
            base_yes = yes_bid if yes_bid > 0 else (1.0 - price)
            target_yes = max(base_yes - buf - extra, 0.01)
            cents = max(1, min(99, int(round((1.0 - target_yes) * 100))))
        coid = f"KTB-{int(time.time()*1000)%1000000}-{random.randint(100,999)}"
        self.log(f"ORDER | {ticker} BUY {side} {size} @ {cents}c | COID:{coid}")
        result = self.api.place_order(ticker=ticker, action="buy", side="yes" if side == "UP" else "no",
                                      count=size, price=cents, time_in_force=ENTRY_TIME_IN_FORCE,
                                      client_order_id=coid)
        if result.get("status", 0) not in (200, 201):
            body = result.get("response_body", {})
            self.log(f"Order failed HTTP {result.get('status')}: {body.get('message','') or result.get('error','')}", logging.WARNING)
            return None, 0.0
        data = result.get("data", {})
        obj = data.get("order", data) if isinstance(data, dict) else {}
        order_id = obj.get("order_id", "") if isinstance(obj, dict) else ""
        time.sleep(0.5)  # brief rest before verification; avoids hammering the API
        if not order_id:
            return (ticker if self.has_existing_position(ticker, force=True) else None), cents / 100.0
        return order_id, cents / 100.0

    def close_position(self, asset: str, reason: str, aggressive: bool = False) -> Tuple[bool, float]:
        pos = self.positions.get(asset)
        if not pos:
            return True, 0.0
        self._pos_cache.pop(pos.ticker, None)
        if not self.has_existing_position(pos.ticker):
            return True, 0.0
        floor = EMERGENCY_EXIT_PRICE if aggressive else STOP_LOSS_FLOOR_PRICE
        for attempt in range(6):
            yes_bid, _, no_bid, _ = self._orderbook_best(pos.ticker)
            bid = yes_bid if pos.side == "UP" else no_bid
            exit_price = max(bid - FILL_BUFFER, floor) if bid > 0 else floor
            if attempt >= 3:
                exit_price = floor  # marketable limit to guarantee fill
            if not self.live_orders:
                return True, exit_price
            cents = max(1, min(99, int(round(exit_price * 100))))
            result = self.api.place_order(ticker=pos.ticker, action="sell",
                                          side="yes" if pos.side == "UP" else "no",
                                          count=pos.size, price=cents,
                                          time_in_force="immediate_or_cancel", reduce_only=True)
            if result.get("status", 0) in (200, 201):
                time.sleep(1.0)
                self._pos_cache.pop(pos.ticker, None)
                if not self.has_existing_position(pos.ticker, force=True):
                    _, avg = self._parse_fills_price(self.api.get_fills(ticker=pos.ticker))
                    actual = avg if avg > 0 else exit_price
                    if pos.side == "DOWN" and 0 < actual < 0.5:
                        actual = 1.0 - actual
                    return True, actual
            self._pos_cache.pop(pos.ticker, None)
            if not self.has_existing_position(pos.ticker, force=True):
                return True, exit_price
            backoff = min(2 ** attempt, 8)
            self.log(f"{asset} Sell retry {attempt+1}/5 (backoff {backoff}s)")
            time.sleep(backoff)
        self.log(f"{asset} CRITICAL: close_position failed after 6 attempts", logging.ERROR)
        return False, 0.0

    # ------------------------------ stats & risk ------------------------------
    def record_trade(self, asset: str, pnl: float, reason: str, exit_price: float):
        st = self.states[asset]
        pos = self.positions.get(asset)
        self.daily_pnl += pnl
        self.daily_trades += 1
        st.total_trades += 1
        st.total_pnl += pnl
        st.session_trade_count += 1
        st.session_pnl += pnl
        st.last_trade_close_time = time.time()
        if pnl >= 0:
            st.win_count += 1
            self.daily_wins += 1
            st.consecutive_losses = 0
            outcome = "WIN"
        else:
            st.loss_count += 1
            self.daily_losses += 1
            st.consecutive_losses += 1
            outcome = "LOSS"
            if st.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                st.loss_pause_until = time.time() + PAUSE_AFTER_LOSS_STREAK_MIN * 60
                self.log(f"{asset} PAUSE {PAUSE_AFTER_LOSS_STREAK_MIN}m after {st.consecutive_losses} consecutive losses")
        self.log(f"{asset} {reason} {outcome} | P&L: ${pnl:.2f} | Total: ${st.total_pnl:.2f}")
        with open(self.trade_file, 'a', newline='') as f:
            csv.writer(f).writerow([datetime.now(timezone.utc).isoformat(), asset,
                                    pos.side if pos else "", pos.entry_price if pos else "",
                                    exit_price, reason, pnl, pos.ticker if pos else "",
                                    st.session_trade_count, pos.strategy if pos else STRATEGY])
        with open(self.perf_file, 'a', newline='') as f:
            wr = st.win_count / st.total_trades * 100 if st.total_trades else 0
            csv.writer(f).writerow([datetime.now(timezone.utc).isoformat(), asset, st.total_trades,
                                    st.win_count, st.loss_count, wr, st.total_pnl, st.consecutive_losses])

    def risk_halted(self) -> bool:
        if self.daily_pnl <= -MAX_DAILY_LOSS:
            self.log_once("DAILY_LOSS", f"Daily loss limit hit (${self.daily_pnl:.2f}) — halting entries")
            return True
        if MAX_DRAWDOWN_PERCENT > 0:
            balance = self._get_balance() or BANKROLL
            dd_pct = abs(min(self.daily_pnl, 0)) / balance * 100 if balance > 0 else 0
            if dd_pct >= MAX_DRAWDOWN_PERCENT:
                self.log_once("DRAWDOWN", f"Drawdown halt: {dd_pct:.1f}% of balance")
                return True
        return False

    def position_size(self, entry_price: float, size_mult: float = 1.0) -> int:
        """Fixed size with 2%-of-bankroll cap and hard cap at MAX_ORDER_SIZE."""
        size = max(1, int(ORDER_SIZE * size_mult))
        balance = self._get_balance() or BANKROLL
        if entry_price > 0 and size * entry_price > balance * (MAX_RISK_PER_TRADE_PCT / 100.0):
            size = max(1, int(balance * (MAX_RISK_PER_TRADE_PCT / 100.0) / entry_price))
        return max(1, min(size, MAX_ORDER_SIZE))

    def check_daily_reset(self):
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        if self.last_daily_reset and today != self.last_daily_reset:
            self.log(f"=== DAILY RESET === P&L ${self.daily_pnl:.2f} | Trades:{self.daily_trades} "
                     f"| W:{self.daily_wins} L:{self.daily_losses}")
            self.daily_pnl = self.daily_trades = self.daily_wins = self.daily_losses = 0
            for st in self.states.values():
                st.consecutive_losses = 0
        self.last_daily_reset = today

    # ------------------------------ entry ------------------------------
    def evaluate_entry(self, asset: str, snap: dict, price: float, strike: Optional[float]):
        st = self.states[asset]
        if st.pending_order_id or asset in self.positions:
            return
        if time.time() < st.loss_pause_until:
            self.log_once(f"{asset}|PAUSE", f"{asset} paused after loss streak")
            return
        if st.session_trade_count >= MAX_TRADES_PER_SESSION:
            return
        if time.time() - st.last_trade_close_time < POST_TRADE_COOLDOWN_SECONDS:
            return
        if time.time() - st.last_order_time < 60 and st.last_order_time > 0:
            return
        if st.entry_attempts >= 2:
            return
        mins_left = snap["minutes_left"]
        if mins_left * 60 < NO_ENTRY_FINAL_SECONDS:
            return
        if self.has_existing_position(snap["ticker"]):
            st.phase = "HAS_POSITION"
            return

        spread = (snap["up_ask"] - snap["up_bid"]) if snap["up_ask"] > 0 and snap["up_bid"] > 0 else 0.0
        decision: Optional[EntryDecision] = None
        use_dc = STRATEGY in ("delta_capture", "delta_capture_scalp")

        if use_dc:
            if price <= 0 or not strike:
                return
            decision = self.engines[asset].delta_capture(
                price, strike, mins_left, snap["up_ask"] or snap["up"],
                snap["down_ask"] or snap["down"], spread * 100)
        else:
            # Legacy strategies: require contract to be a strong favorite first
            decision = self.engines[asset].legacy_signal(STRATEGY)
            if decision:
                ask = snap["up"] if decision.side == "UP" else snap["down"]
                if ask < ENTRY_THRESHOLD:
                    self.log_once(f"{asset}|WEAK", f"{asset} {decision.side} signal but ask {ask:.2f} < {ENTRY_THRESHOLD}")
                    return
                if ask > DC_MAX_ENTRY_PRICE and STRATEGY != "rsi_extreme":
                    return
                if STRATEGY == "rsi_extreme":
                    ask_cap = 0.80
                    if ask > ask_cap:
                        return
                # Price-velocity filter
                now = time.time()
                st.price_history.append({"time": now, "px": ask})
                recent = [p for p in st.price_history if now - p["time"] <= 60]
                if len(recent) >= 2 and ask - recent[0]["px"] > MAX_PRICE_VELOCITY:
                    self.log_once(f"{asset}|VELOCITY", f"{asset} blocked: +${ask - recent[0]['px']:.2f} in 60s")
                    return
                # 1m StochRSI extreme guard
                k, _ = self.feeds[asset].stoch_rsi_kd()
                if decision.side == "UP" and k > STOCH_OVERBOUGHT:
                    return
                if decision.side == "DOWN" and k < STOCH_OVERSOLD:
                    return
                # Consecutive confirmation
                if ENTRY_CONFIRMATION_CYCLES > 1:
                    if st.last_proposed_side == decision.side:
                        st.confirmation_count += 1
                    else:
                        st.confirmation_count = 1
                        st.last_proposed_side = decision.side
                    if st.confirmation_count < ENTRY_CONFIRMATION_CYCLES:
                        return

        if not decision:
            return
        if spread > 0 and spread * 100 > DC_MAX_SPREAD_CENTS:
            self.log_once(f"{asset}|SPREAD", f"{asset} spread {spread*100:.0f}c > {DC_MAX_SPREAD_CENTS}c")
            return

        entry_ask = snap["up_ask"] or snap["up"] if decision.side == "UP" else snap["down_ask"] or snap["down"]
        size = self.position_size(entry_ask, decision.size_mult)
        self.log(f"{asset} ENTRY {decision.side} x{size} @ ~{entry_ask:.2f} | {STRATEGY} | {decision.reason}")

        order_id, order_price = self.place_buy(asset, snap["ticker"], decision.side, entry_ask, size)
        st.pending_order_id = order_id or ""
        if not order_id:
            st.entry_attempts += 1
            return
        filled, fill_price = self.verify_fill(order_id, snap["ticker"], size, ENTRY_TIME_IN_FORCE)
        st.pending_order_id = ""
        if not filled:
            if self.has_existing_position(snap["ticker"], force=True):
                filled = True
            else:
                try:
                    if self.live_orders:
                        self.api.cancel_order(order_id)
                except Exception:
                    pass
                st.entry_attempts += 1
                self.log(f"{asset} Order did not fill ({st.entry_attempts}/2)")
                return
        st.entry_attempts = 0
        tracked = fill_price if fill_price > 0 else (order_price or entry_ask)
        if decision.side == "DOWN" and 0 < tracked < 0.5:
            tracked = 1.0 - tracked
        self.positions[asset] = Position(
            asset=asset, side=decision.side, entry_price=tracked, ticker=snap["ticker"],
            size=size, entry_time=datetime.now(timezone.utc), entry_order_id=order_id,
            strategy=STRATEGY, stop_loss=max(EXIT_THRESHOLD, tracked - MAX_LOSS_PER_TRADE),
            highest_price=tracked)
        st.phase = "IN_POSITION"
        st.last_order_time = time.time()
        self.log(f"{asset} IN POSITION | {decision.side} @ {tracked:.2f} | {snap['ticker']}")

    # ------------------------------ position management ------------------------------
    def manage_position(self, asset: str, snap: dict, price: float, strike: Optional[float]):
        pos = self.positions[asset]
        st = self.states[asset]
        mins_left = snap["minutes_left"]
        current = snap["up_bid"] or snap["up"] if pos.side == "UP" else snap["down_bid"] or snap["down"]
        pnl = (current - pos.entry_price) * pos.size
        pos.max_pnl = max(pos.max_pnl, pnl)
        pos.highest_price = max(pos.highest_price, current)
        hold = (datetime.now(timezone.utc) - pos.entry_time).total_seconds()
        use_dc = pos.strategy in ("delta_capture", "delta_capture_scalp")

        def do_close(reason, aggressive=False):
            closed, exit_price = self.close_position(asset, reason, aggressive)
            if closed:
                self.record_trade(asset, (exit_price - pos.entry_price) * pos.size, reason, exit_price)
                del self.positions[asset]
                st.phase = "WAIT_WINDOW"
                return True
            st.phase = "EMERGENCY_EXIT"
            return False

        # Settlement / forced exit near close — always, any strategy
        if mins_left <= TIME_EXIT_MINUTES and not use_dc:
            self.log(f"{asset} TIME EXIT | {mins_left:.1f}m left")
            return do_close("TIME_EXIT", aggressive=True)
        if mins_left <= 1.0:
            self.log(f"{asset} FINAL EXIT | {mins_left:.1f}m left")
            return do_close("FORCED_CLOSE", aggressive=True)

        # Market moved to a new ticker (window rolled) → resolve P&L at settlement
        if snap["ticker"] != pos.ticker:
            final = 1.0 if (snap["up"] >= 0.99 and pos.side == "UP") or (snap["down"] >= 0.99 and pos.side == "DOWN") else 0.0
            if snap["up"] >= 0.99:
                final = 1.0 if pos.side == "UP" else 0.0
            elif snap["down"] >= 0.99:
                final = 1.0 if pos.side == "DOWN" else 0.0
            self.record_trade(asset, (final - pos.entry_price) * pos.size, "SETTLEMENT", final)
            del self.positions[asset]
            st.phase = "WAIT_WINDOW"
            return True

        if use_dc:
            # Delta Capture: hold to settlement; optional salvage exit on delta flip
            if DC_SALVAGE_EXIT and strike and price > 0 and mins_left > DC_SALVAGE_MIN_MINUTES:
                delta = (price - strike) / strike
                flipped = (pos.side == "UP" and delta < 0) or (pos.side == "DOWN" and delta > 0)
                if flipped:
                    self.log(f"{asset} SALVAGE EXIT | delta flipped to {delta:.4%}")
                    return do_close("DELTA_FLIP_SALVAGE")
            # Profit target still honored
            if current >= PROFIT_TARGET:
                return do_close("PROFIT_TARGET")
            # Otherwise: defined-risk binary — hold to settlement.
            return True

        # ---- Legacy strategy exit management ----
        if st.session_pnl <= -MAX_LOSS_PER_SESSION:
            return do_close("SESSION_LOSS_LIMIT", aggressive=True)
        if not pos.breakeven_active and (pnl / max(pos.size, 1)) >= BREAKEVEN_TRIGGER_PROFIT:
            pos.breakeven_active = True
            pos.stop_loss = pos.entry_price + BREAKEVEN_BUFFER
            self.log(f"{asset} BREAKEVEN stop -> {pos.stop_loss:.2f}")
        if not pos.breakeven_active and hold >= EARLY_TIME_STOP_SECONDS and pnl < -MAX_LOSS_PER_TRADE * pos.size:
            return do_close("EARLY_TIME_STOP", aggressive=True)
        if current < pos.stop_loss:
            return do_close("STOP_LOSS", aggressive=(pos.stop_loss - current) > 0.05)
        if current >= PROFIT_TARGET:
            return do_close("PROFIT_TARGET")
        if hold >= MAX_HOLD_TIME_SECONDS:
            return do_close("MAX_HOLD_TIME", aggressive=True)
        if hold >= MIN_HOLD_SECONDS and pos.max_pnl >= MIN_PROFIT_FOR_TRAILING * pos.size:
            if pos.max_pnl > 0 and pnl < pos.max_pnl * (1 - TRAILING_STOP_PCT):
                self.log(f"{asset} TRAILING STOP | peak ${pos.max_pnl:.2f} now ${pnl:.2f}")
                return do_close("TRAILING_STOP", aggressive=True)
        return True

    # ------------------------------ dashboard ------------------------------
    def _display_loop(self):
        while self.running:
            try:
                self._render()
            except Exception:
                pass
            time.sleep(1.0)

    def _render(self):
        width = 68
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = ["+" + "-" * width + "+",
                 f"|  kalshi-trading-bot v0.1  |  {now:<35}|",
                 "+" + "-" * width + "+"]
        mode = "LIVE" if self.live_orders else "PAPER"
        wr = self.daily_wins / max(1, self.daily_trades) * 100
        lines.append(f"|  Mode:{mode:<6} Strategy:{STRATEGY:<18} P&L:${self.daily_pnl:>7.2f} W:{self.daily_wins}/{self.daily_trades} ({wr:.0f}%)"[:width+1] + "|")
        lines.append("+" + "-" * width + "+")
        with self._display_lock:
            data = dict(self.display_data)
        for asset in ASSETS:
            d = data.get(asset, {})
            st = self.states[asset]
            pos = self.positions.get(asset)
            pos_line = (f"{pos.side}@{pos.entry_price:.2f} x{pos.size}" if pos else "flat")
            lines.append(f"|  {asset:<4} {st.phase:<14} {d.get('ticker','-')[:24]:<24} {pos_line:<18}|"[:width+1] + "|")
            lines.append(f"|    UP:{d.get('up',0):.2f} DN:{d.get('down',0):.2f} px:{d.get('price',0):.0f} "
                         f"K:{d.get('k',0):.0f} D:{d.get('d',0):.0f} d:{d.get('delta',0):+.4%} left:{d.get('mins',0):.1f}m"[:width+1] + "|")
            lines.append("+" + "-" * width + "+")
        esc = chr(27)
        sys.stdout.write(esc + "[2J" + esc + "[H" + chr(10).join(lines) + chr(10))
        sys.stdout.flush()

    def _print_summary(self):
        wins = sum(s.win_count for s in self.states.values())
        losses = sum(s.loss_count for s in self.states.values())
        trades = sum(s.total_trades for s in self.states.values())
        pnl = sum(s.total_pnl for s in self.states.values())
        self.log("=" * 60)
        self.log(f"SESSION SUMMARY | Trades:{trades} W:{wins} L:{losses} "
                 f"WR:{wins/max(1,trades)*100:.1f}% | P&L: ${pnl:.2f}")
        self.log("=" * 60)

    # ------------------------------ run loop ------------------------------
    def run(self):
        self.log("=" * 60)
        self.log(f"kalshi-trading-bot v0.1.0 | Strategy: {STRATEGY}")
        self.log(f"Mode: {'LIVE ORDERS' if self.live_orders else 'PAPER/TEST'} | Assets: {ASSETS}")
        self.log(f"Delta Capture: window {DC_ENTRY_WINDOW_MIN}m | delta {DC_MIN_DELTA_PCT:.4%}-{DC_MAX_DELTA_PCT:.4%} "
                 f"| max entry ${DC_MAX_ENTRY_PRICE} | ATR cap {DC_ATR_MAX_PCT:.4%} | spread cap {DC_MAX_SPREAD_CENTS}c")
        self.log(f"Risk: daily loss ${MAX_DAILY_LOSS} | drawdown {MAX_DRAWDOWN_PERCENT}% | "
                 f"{MAX_CONSECUTIVE_LOSSES} straight losses -> {PAUSE_AFTER_LOSS_STREAK_MIN}m pause | size cap {MAX_ORDER_SIZE}")
        self.log("=" * 60)
        try:
            while self.running:
                try:
                    self.check_daily_reset()
                    halted = self.risk_halted()
                    any_active = False
                    for asset in ASSETS:
                        if not self.running:
                            break
                        st = self.states[asset]
                        snap = self.get_snapshot(asset)
                        if not snap:
                            self.log_once(f"{asset}|NO_MKT", f"{asset} waiting for market data")
                            continue
                        price = self.feeds[asset].poll()
                        strike = self.feeds[asset].window_strike()
                        # New 15-min window → reset per-session state
                        session_key = f"{asset}_{snap['ticker']}"
                        if st.session_key != session_key:
                            st.session_key = session_key
                            st.session_trade_count = 0
                            st.session_pnl = 0.0
                            st.entry_attempts = 0
                            st.confirmation_count = 0
                            st.last_proposed_side = ""
                            if st.phase not in ("IN_POSITION", "EMERGENCY_EXIT"):
                                st.phase = "WAIT_WINDOW"
                            self.log(f"{asset} New window: {snap['ticker']} | strike ~{strike or 0:.0f}")
                        # Position management
                        if asset in self.positions:
                            any_active = True
                            if st.phase == "EMERGENCY_EXIT":
                                closed, exit_price = self.close_position(asset, "emergency_retry", aggressive=True)
                                if closed:
                                    pos = self.positions[asset]
                                    self.record_trade(asset, (exit_price - pos.entry_price) * pos.size,
                                                      "EMERGENCY_CLOSE", exit_price)
                                    del self.positions[asset]
                                    st.phase = "WAIT_WINDOW"
                            else:
                                self.manage_position(asset, snap, price, strike)
                        elif not halted and st.phase != "HAS_POSITION":
                            self.evaluate_entry(asset, snap, price, strike)
                        if st.phase == "HAS_POSITION" and not self.has_existing_position(snap["ticker"]):
                            st.phase = "WAIT_WINDOW"
                        with self._display_lock:
                            k, d = self.feeds[asset].stoch_rsi_kd()
                            delta = ((price - strike) / strike) if (strike and price > 0) else 0.0
                            self.display_data[asset] = {
                                "ticker": snap["ticker"], "up": snap["up"], "down": snap["down"],
                                "price": price, "k": k, "d": d, "delta": delta, "mins": snap["minutes_left"]}
                    time.sleep(POLL_INTERVAL_MONITORING_S if any_active or self.positions else POLL_INTERVAL_RELAXED_S)
                except Exception as e:
                    self.log(f"Loop error: {e}", logging.ERROR)
                    time.sleep(5)
        except KeyboardInterrupt:
            pass
        finally:
            self._print_summary()
            self.running = False


# ============================================================================
# MAIN
# ============================================================================
def load_api_keys_from_dir() -> Tuple[str, str]:
    """Read Kalshi credentials from the api_keys/ subfolder.
    Accepts apikey.json/apikey.txt and privatekey.json/privatekey.txt
    (JSON with a 'code' field, or raw text)."""
    api_key, pk_path = "", ""
    if not os.path.isdir(API_KEYS_DIR):
        return "", ""
    for fname in os.listdir(API_KEYS_DIR):
        fp = os.path.join(API_KEYS_DIR, fname)
        if not os.path.isfile(fp):
            continue
        try:
            raw = open(fp).read().strip()
            low = fname.lower()
            if "apikey" in low or "api_key" in low:
                try:
                    data = json.loads(raw)
                    api_key = (data.get("code", "") if isinstance(data, dict) else str(data)).strip()
                except json.JSONDecodeError:
                    api_key = raw
            elif "privatekey" in low or "private_key" in low or "secret" in low:
                pk_path = fp
        except Exception:
            pass
    return api_key, pk_path


def main():
    global PRETTY_DISPLAY
    parser = argparse.ArgumentParser(description="kalshi-trading-bot v0.1.0")
    parser.add_argument("--paper", action="store_true", help="Force paper/test mode")
    parser.add_argument("--pretty", action="store_true", help="Live terminal dashboard")
    args = parser.parse_args()
    if args.pretty:
        PRETTY_DISPLAY = True

    logger, log_file, trade_file, perf_file = setup_logging(pretty_display=PRETTY_DISPLAY)
    logger.info(f"Log: {log_file} | Trades: {trade_file} | Perf: {perf_file}")

    api_key, pk_path = load_api_keys_from_dir()
    have_keys = bool(api_key) and bool(pk_path)
    live = have_keys and not FORCE_PAPER_MODE and not args.paper
    if live:
        logger.info("API keys found in api_keys/ — LIVE ORDER MODE enabled")
    elif have_keys:
        logger.info("API keys found but paper mode forced — PAPER/TEST MODE")
    else:
        logger.info("No API keys in api_keys/ — defaulting to PAPER/TEST MODE")

    bot = KalshiTradingBot(logger, trade_file, perf_file, live_orders=live,
                           pretty_display=PRETTY_DISPLAY)
    if live:
        bot.api.api_key_id = api_key
        bot.api.private_key_path = pk_path

    def shutdown(signum, frame):
        logger.info("Shutdown signal received")
        bot.running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    bot.run()


if __name__ == "__main__":
    main()
