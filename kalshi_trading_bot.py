#!/usr/bin/env python3
"""
kalshi-trading-bot (v0.6.0)
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
  v0.6.0 (2026-07-30):
    - NEW: JSON config file support with a strict precedence chain:
      script defaults < config file < CLI flags. Default path
      kalshi_bot_config.json (searched next to the script first, then the
      CWD); --config-file PATH overrides the search. Flat JSON object keyed
      by module-global config names; unknown keys warn and are ignored,
      type errors warn and skip that key (never crash). Applied values are
      logged as "Config file (<path>): KEY=value | ..." at startup.
    - NEW: interactive config menu (--menu / --config). Pure-stdlib
      terminal menu that edits the config file and exits (no trading).
      Grouped sections, per-param defaults shown, reset-to-default, and a
      save that writes only values differing from script defaults.
    - NEW: multiple shots on goal (multi-entry per 15-min window).
      MAX_ENTRIES_PER_WINDOW replaces the hard single-shot block
      (MAX_TRADES_PER_SESSION deprecated; config-file values are copied
      over with a warning). Re-entries honor REENTRY_COOLDOWN_SECONDS,
      size-decay by REENTRY_SIZE_DECAY ** (N-1), optional same-side block
      after a losing exit (REENTRY_SAME_SIDE_ALLOWED), and an
      after-loss-only mode (REENTRY_AFTER_LOSS_ONLY). All five resolvable
      per-asset via ASSET_OVERRIDES, settable via config file, menu
      section 5, and CLI flags. New CLI: --max-entries-per-window,
      --reentry-cooldown, --reentry-size-decay, --reentry-same-side /
      --no-reentry-same-side, --reentry-after-loss-only /
      --no-reentry-after-loss-only, plus salvage flags
      --dc-salvage-min-flip / --dc-salvage-min-hold.
    - NEW: NEAR (KXNEAR15M) and ZEC (KXZEC15M) markets with Kraken/Binance
      symbol maps.
    - TUNE (backtest, 30d x 8 assets, 2026-06-30 -> 2026-07-30, Binance 1m):
      full config sweep (salvage on/off/tuned x shots 1/3 x conviction gate
      x min-delta x price cap x profit target). Findings -> new
      ASSET_OVERRIDES calibration:
        * Per-asset DC_MIN_DELTA_PCT is the strongest lever: a fixed global
          min-delta misfits every asset (BNB/BTC trade profitably at 0.02%
          deltas; high-vol assets need a bigger cushion). Overrides: SOL
          0.0004, ETH/XRP/NEAR 0.0006, DOGE 0.0008; BTC/BNB/ZEC keep the
          0.0002 global. 30d result vs v0.5.0: WR 56.5% -> 63.8%, modeled
          net -$24.21 -> -$2.62 (gross positive +$0.82; modeled prices are
          fair-value+premium, so gross-positive is a strong signal).
        * NEAR/ZEC get DC_MAX_ENTRY_PRICE 0.58 (modeled pricier entries on
          the two high-vol newcomers lose; keep them conservative until
          paper fills prove otherwise). Global stays 0.62 — the 2026-07-29
          live run banked 4 of 7 wins at 0.59-0.62 asks.
        * ATR caps recalibrated to 30d p75: global 0.0006 (BTC), ETH 0.0009,
          SOL 0.0010, XRP 0.0009, DOGE 0.0009, BNB 0.0006, NEAR 0.0015,
          ZEC 0.0018.
        * Salvage ON at current defaults beats OFF and tuned variants in
          every modeled cell (the v0.5.0 live "all losses were salvage
          exits" is survivorship — those trades lost more at settlement).
        * Multi-entry replay: re-entries essentially never fire under the
          current entry discipline — after a win the contract is too
          expensive for the caps, after a loss the flip side fails
          min-delta/price gates. The feature ships default single-shot
          (MAX_ENTRIES_PER_WINDOW=1); raising it is safe (gates still
          protect) and becomes active as soon as a window genuinely
          re-qualifies.
        * ZEC is the weakest modeled asset (61% WR but negative at every
          setting tested) — paper-only until live fills say otherwise.
  v0.5.0 (2026-07-29):
    - FIX (logging): stale MTF BLOCK lines. StrategyEngine.last_mtf_block was
      reset AFTER the MTF conviction-gate return in delta_capture(), so a veto
      from a previous window survived and evaluate_entry logged
      "MTF BLOCK | X signal vetoed" for windows the conviction gate actually
      killed — including contradictory "MTF BLOCK ... NEUTRAL score +0.01"
      lines (2026-07-28 paper run). last_mtf_block is now reset before ALL
      gate returns, and conviction-gate vetoes log on their own path:
      "MTF GATE | score ... below conviction threshold".
    - TUNE (backtest, 24h x 6 assets): the v0.4.0 paper
      session traded ZERO times in 18h; the replay confirms the config is
      over-constrained and that the binding constraint DIVERGES BY ASSET:
        * MTF_MIN_TRADE_SCORE 0.20 -> 0.10. At 0.20 the conviction gate alone
          vetoed ~all qualifiers (18h live: 0 trades). 7-day BTC backtest still
          supports filtering chop, so a light 0.10 gate is kept.
        * DC_ATR_MAX_PCT 0.00045 -> 0.0006 global + NEW ASSET_OVERRIDES
          per-asset ATR caps (ETH/SOL/XRP/DOGE 0.0010, BNB 0.0005). A single
          global ATR cap calibrated on BTC blocked ~90% of entry checks on
          ETH/SOL/XRP/DOGE (their median 1m ATR% is ~0.0007-0.0008 vs BTC
          ~0.0004-0.0006). Per-asset caps ~= p75 of each asset's 24h ATR%
          distribution. This is the main per-asset divergence found.
        * Raw signal quality is comparable across assets (63-80% WR, XRP
          weakest), so all other params stay global. 24h = 96 windows/asset:
          results are directional, not statistically significant.
    - NEW: full CLI. Every launch-relevant variable is overridable via
      argparse flags (run with --help); flags take precedence over the script
      defaults and are logged as "CLI override" at startup. --assets rebuilds
      all asset-driven state. --asset-overrides accepts a JSON object, e.g.
      --asset-overrides '{"ETH":{"MTF_MIN_TRADE_SCORE":0.15}}'.
    - NEW: ASSET_OVERRIDES dict + asset_param() resolver. StrategyEngine
      resolves every entry tunable as per-asset override with global fallback.
  v0.4.0 (2026-07-28):
    - FIX (CRITICAL, live): close_position could loop sell retries for 20+
      minutes ("CRITICAL: close_position failed after 6 attempts" repeating
      all session 2026-07-27/28). Root causes addressed:
        (a) sell-order rejection body was never logged — now logged every attempt;
        (b) sells are no longer attempted once the window has expired
            (mins_left <= 0.25) or the ticker has rolled — the position is
            resolved at settlement instead of hammering a dead orderbook;
        (c) EMERGENCY_EXIT retries are capped (EMERGENCY_MAX_RETRIES), then the
            bot falls back to settlement resolution instead of retrying forever;
        (d) reduce_only flag removed from exit orders (rejected on some Kalshi
            markets); exit side mapping made explicit.
    - FIX (CRITICAL, P&L): DOWN fill-price flip heuristic. Log proof:
      "ORDER ... BUY DOWN 1 @ 43c" followed by "IN POSITION | DOWN @ 0.57".
      verify_fill returned the no-side fill price (0.43) and the
      `side=="DOWN" and price<0.5 -> 1-price` heuristic flipped it to 0.57,
      corrupting entry price, P&L, stops and CSV records. Fill price is now
      resolved side-aware: no_price/fill count fields are preferred for DOWN
      orders and the blind 1-x flip is removed (kept only when the price is
      provably yes-denominated for a DOWN order).
    - FIX: paper mode no longer calls authenticated endpoints
      (has_existing_position/_get_balance) — avoids pointless 401s and
      rate-limit burn when running without keys.
    - FIX: "Sell retry 6/5" label (range(6) vs /5).
    - NEW: MTF conviction gate MTF_MIN_TRADE_SCORE (default 0.20). In a
      7-day 1-minute backtest (10,080 candles, Jul 21-28), trades taken with
      |MTF score| < 0.30 went 50% WR / negative P&L; |score| >= 0.30 went 75%.
      Entries now require |score| >= 0.20 (NEUTRAL-zone chop is skipped).
    - TUNE (backtest): DC_ATR_MAX_PCT 0.0005 -> 0.00045 and
      MTF_STRONG_SCORE 0.45 -> 0.40. Same-week backtest of the full config:
      baseline 24 trades / 62.5% WR / +$0.75 -> new config 12 trades /
      83.3% WR / +$1.67 (fewer, better trades).
    - TUNE: DC_SCALP_MAX_PRICE 0.60 -> 0.58 (best backtest bucket).
    - NEW: market strike taken from the Kalshi market object when present
      (floor_strike/strike fields), falling back to the Kraken-candle
      estimate — Kraken vs Kalshi benchmark diverges $40-70 at times, which
      skews delta readings.
    - NEW: fee-adjusted P&L estimate in trade CSV/log (Kalshi taker fee
      ~0.07 * C * P * (1-P) per contract), column FeeEst added.
  v0.3.0 (2026-07-27):
    - TUNE: entry-price discipline after 2026-07-26/27 paper session (12 trades,
      50% WR, -$1.16). Entries >= $0.64 netted -$1.53; entries <= $0.62 netted
      +$0.36. DC_MAX_ENTRY_PRICE lowered 0.70 -> 0.62 and MTF_TREND_MAX_PRICE
      0.75 -> 0.68 so every trade has >= ~1:1 payoff vs. the binary stake.
    - TUNE: MTF weights rebalanced. The 1d timeframe (weight 0.30) pinned the
      composite at +0.7 all session while price fell ~$260, forcing bias=UP in
      45 of 46 windows and suppressing DOWN setups. Weights now favor the
      timeframes that actually move within a 15-minute contract:
      1d 0.30->0.15, 4h 0.25->0.20, 15m 0.15->0.25, 5m 0.10->0.20.
    - TUNE: salvage exit thresholds raised (flip 0.02% -> 0.05%, min hold
      60s -> 120s). Both salvage exits in the session fired on noise-sized
      flips (~0.03%) and locked in losses before the window could recover.
    - FIX: MTFBLK log line now only fires when the MTF counter-trend gate
      actually vetoed an otherwise-qualifying signal (previously it logged on
      every signal-less window, implying MTF was the blocker when it usually
      was not). StrategyEngine exposes last_mtf_block for this.
    - FIX: terminal dashboard header hardcoded "v0.1"; now shows real version.
  v0.2.0 (2026-07-27):
    - NEW: Multi-Timeframe Momentum (MTF) engine. Evaluates 1d / 4h / 1h /
      15m / 5m klines (RSI + recent return + candle direction) into a
      weighted composite score in [-1, +1] with an UP/DOWN/NEUTRAL bias.
    - NEW: Counter-trend gate — delta_capture entries fighting the MTF bias
      are blocked (configurable via MTF_COUNTER_TREND_BLOCK).
    - NEW: Trend-aligned continuation entries. When MTF score >=
      MTF_STRONG_SCORE on the delta side, the max-delta cap relaxes to
      MTF_TREND_MAX_DELTA_PCT and the StochRSI dead-zone check is waived,
      so strong-trend windows (previously skipped for delta > 0.10%) trade.
    - NEW: Trend windows (delta beyond the relaxed cap, MTF strong) can enter
      at up to MTF_TREND_MAX_PRICE with reduced size (MTF_TREND_SIZE_MULT).
    - MTF score/bias added to ENTRY log lines and the terminal dashboard.
      Set MTF_ENABLED = False to restore exact v0.1.2 behavior.
  v0.1.2 (2026-07-27):
    - FIX: delta_capture no longer force-sells in the final minute. FORCED_CLOSE
      (aggressive, floor-priced) now applies to legacy strategies only; DC
      positions ride to settlement and are resolved via the market result.
    - FIX: salvage exit hair-trigger. A delta flip now requires (a) the flipped
      delta to exceed DC_SALVAGE_MIN_FLIP_PCT and (b) a minimum hold of
      DC_SALVAGE_MIN_HOLD_S, so a 20-second wobble can't dump a fresh entry.
    - FIX: _get_balance() cents heuristic could halve real balances > $100.
      Now prefers the balance_dollars field and only divides when the value
      is implausibly large for a dollar figure (> $100,000).
    - Added settlement resolution when the window expires but the ticker has
      not rolled yet (mins_left <= 0.25), using the market result API.
    - Parenthesized side-select expressions in evaluate_entry/manage_position
      to remove reliance on or/ternary operator precedence.
    - IN POSITION log line now includes the captured strike.
  v0.1.1 (2026-07-26):
    - FIX: paper-mode exits no longer record $0.00. close_position() previously
      bailed out on has_existing_position() (always False without API keys)
      BEFORE the paper-mode branch, so every paper exit was booked as a total
      loss — including PROFIT_TARGET wins. Paper exits now use the live
      contract price passed from manage_position().
    - FIX: window-roll settlement no longer checks the NEW window's price.
      Settlement is resolved from the OLD ticker's market result via the API,
      with price-vs-strike fallback using the strike captured at entry.
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

import os, sys, json, time, base64, argparse, logging, csv, random, math, copy
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
ASSETS = ["BTC"]                  # Any of: BTC ETH SOL XRP DOGE HYPE BNB NEAR ZEC
KALSHI_API_BASE = "https://external-api.kalshi.com"   # Production API
# KALSHI_API_BASE = "https://demo-api.kalshi.co"      # Uncomment for Kalshi demo

# --- API keys (read from subfolder) ---
API_KEYS_DIR = "api_keys"         # Folder holding apikey.json / privatekey.json
FORCE_PAPER_MODE = False          # True = paper-trade even if API keys exist

# --- Delta Capture strategy (default) — handoff Section 6 ---
DC_ENTRY_WINDOW_MIN = (3.0, 8.0)  # Only enter with 3-8 minutes left in window
DC_MIN_DELTA_PCT = 0.0002         # Min |price-strike|/strike (~0.02%, buy the winning side)
DC_MAX_DELTA_PCT = 0.0010         # Max delta — beyond this is a spike (mean-reversion risk)
DC_MAX_ENTRY_PRICE = 0.62         # Never pay more than 62c — entries above this
                                  # had negative expectancy in the 2026-07-26 session
DC_STOCH_K_LONG_MIN = 50.0        # UP entry: K must be above this...
DC_REQUIRE_K_GT_D = True          # ...and K > D (momentum confirmation)
DC_DEAD_ZONE = (45.0, 55.0)       # No-trade StochRSI K dead zone (no momentum read)
DC_ATR_MAX_PCT = 0.0006           # 1m ATR(14) above this = burst volatility, skip.
                                  # v0.5.0: 0.00045 -> 0.0006 (~p75 of BTC 24h ATR%);
                                  # high-vol assets get per-asset caps via ASSET_OVERRIDES
DC_MAX_SPREAD_CENTS = 4           # Skip if contract spread wider than this
DC_SCALP_ENABLED = True           # Early-window momentum scalp variant
DC_SCALP_WINDOW_MIN = (12.0, 14.0)  # Minutes-left range = minutes 1-3 of window
DC_SCALP_MIN_MOVE_PCT = 0.0005    # Scalp: price must already be >=0.05% from strike
DC_SCALP_MAX_PRICE = 0.58         # Scalp: max entry price (best backtest bucket)
DC_SCALP_K_UP = 60.0              # Scalp UP: K above this
DC_SCALP_K_DOWN = 40.0            # Scalp DOWN: K below this
DC_SCALP_SIZE_MULT = 0.5          # Scalp trades at half size
DC_SALVAGE_EXIT = True            # If delta flips sign with >5 min left, sell to cut loss
DC_SALVAGE_MIN_MINUTES = 5.0      # ...only if at least this many minutes remain
DC_SALVAGE_MIN_FLIP_PCT = 0.0005  # ...and the flipped delta exceeds this (~0.05%)
DC_SALVAGE_MIN_HOLD_S = 120       # ...and the position has been held this long

# --- Multi-Timeframe Momentum (MTF) engine — v0.2.0 ---
# Evaluates higher timeframes and blends them into one score in [-1, +1].
# Positive = upward momentum, negative = downward. Used to (a) block
# counter-trend entries and (b) unlock trend-aligned continuation entries
# that the plain delta cap (0.10%) would otherwise skip.
MTF_ENABLED = True                # False = exact v0.1.2 behavior
MTF_TIMEFRAMES = {                # timeframe -> (Binance interval, weight, klines to fetch)
    "1d":  ("1d",  0.15, 30),     # downweighted v0.3.0: daily RSI was sticky all
    "4h":  ("4h",  0.20, 30),     # session and overrode the timeframes that matter
    "1h":  ("1h",  0.20, 30),     # for a 15-minute contract
    "15m": ("15m", 0.25, 30),
    "5m":  ("5m",  0.20, 30),
}
MTF_RSI_LEN = 14                  # RSI period per timeframe
MTF_RET_BARS = 3                  # Return measured over last N closed bars
MTF_CACHE_TTL_S = 120             # Higher-TF data refreshes at most this often
MTF_COUNTER_TREND_BLOCK = True    # Block entries against the MTF bias
MTF_MIN_SCORE = 0.15              # |score| below this = NEUTRAL (no bias enforced)
MTF_STRONG_SCORE = 0.40           # >= this = strong trend; relaxes delta cap + dead zone
MTF_MIN_TRADE_SCORE = 0.10        # Conviction gate: skip ALL entries while |score| is
                                  # below this. 7-day backtest: |score|<0.30 trades went
                                  # 50% WR / negative P&L; >=0.30 went 75%. 0 = disable.
                                  # v0.5.0: 0.20 -> 0.10. 0.20 vetoed ~every qualifier in
                                  # the 18h v0.4.0 paper run (zero trades) and in the 24h
                                  # 6-asset replay; 0.10 keeps the chop filter without
                                  # killing all trade flow.
MTF_TREND_MAX_DELTA_PCT = 0.0025  # Trend-aligned entries allowed up to 0.25% delta
MTF_TREND_MAX_PRICE = 0.68        # Trend continuation entries may pay up to 68c
                                  # (still >= ~1:2 payoff vs. full stake)
MTF_TREND_SIZE_MULT = 0.5         # Continuation entries trade at reduced size

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
MAX_TRADES_PER_SESSION = 1        # DEPRECATED (v0.6.0): superseded by MAX_ENTRIES_PER_WINDOW.
                                  # Setting it via the config file copies the value into
                                  # MAX_ENTRIES_PER_WINDOW with a deprecation warning.
POST_TRADE_COOLDOWN_SECONDS = 90

# --- Multi-Entry / "Shots on Goal" (v0.6.0) ---
# Defaults preserve the v0.5.0 single-shot behavior: one entry per window.
MAX_ENTRIES_PER_WINDOW = 1        # Total entries allowed per 15-min window per asset
REENTRY_COOLDOWN_SECONDS = 120    # Min wait after an exit before re-entering the same window
REENTRY_SIZE_DECAY = 0.5          # Re-entry N gets size x (decay ** (N-1)) on top of decision.size_mult
REENTRY_SAME_SIDE_ALLOWED = False # After a losing exit, block re-entry on the SAME side that just failed
REENTRY_AFTER_LOSS_ONLY = False   # True = extra entries (2nd+) only allowed if the previous window trade lost

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
EMERGENCY_MAX_RETRIES = 3         # EMERGENCY_EXIT loops before falling back to settlement
KALSHI_TAKER_FEE_COEFF = 0.07     # fee = coeff * C * P * (1-P) per contract (estimate)

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
    "XRP": "KXXRP15M", "DOGE": "KXDOGE15M", "HYPE": "KXHYPE15M", "BNB": "KXBNB15M",
    "NEAR": "KXNEAR15M", "ZEC": "KXZEC15M",
}
ASSET_SYMBOL_MAP = {   # Exchange spot symbols (Kraken pair, Binance symbol)
    "BTC": ("XBTUSD", "BTCUSDT"), "ETH": ("ETHUSD", "ETHUSDT"),
    "SOL": ("SOLUSD", "SOLUSDT"), "XRP": ("XRPUSD", "XRPUSDT"),
    "DOGE": ("DOGEUSD", "DOGEUSDT"), "HYPE": ("HYPEUSD", "HYPEUSDT"),
    "BNB": ("BNBUSD", "BNBUSDT"),
    "NEAR": ("NEARUSD", "NEARUSDT"), "ZEC": ("ZECUSD", "ZECUSDT"),
}

# --- Per-asset parameter overrides (v0.5.0) ---
# Any entry-tunable global can be overridden per asset here; the engine
# resolves each value as override-with-global-fallback via asset_param().
# Basis: 24h x 6-asset backtest.
# The 1m ATR% level diverges ~2x across assets, so a single global ATR cap
# either strangles high-vol assets or protects low-vol ones too little.
# Caps below ~= p75 of each asset's 24h ATR% distribution (block the burstiest
# quartile only). HYPE has no Binance spot feed — untested, no override.
ASSET_OVERRIDES = {
    # ATR caps = p75 of each asset's 30d 1m ATR% distribution (2026-06-30..07-30).
    # Min-delta overrides = best cell in the 30d per-asset sweep (0.0002/0.0004/
    # 0.0006/0.0008): low-vol BTC/BNB/ZEC keep the 0.0002 global (their profitable
    # trades live at small deltas); DOGE (weakest) gets the biggest cushion.
    # NEAR/ZEC price cap 0.58: modeled pricier entries on the high-vol newcomers
    # lose; keep them conservative until paper fills prove otherwise.
    "ETH":  {"DC_ATR_MAX_PCT": 0.0009, "DC_MIN_DELTA_PCT": 0.0006},
    "SOL":  {"DC_ATR_MAX_PCT": 0.0010, "DC_MIN_DELTA_PCT": 0.0004},
    "XRP":  {"DC_ATR_MAX_PCT": 0.0009, "DC_MIN_DELTA_PCT": 0.0006},
    "DOGE": {"DC_ATR_MAX_PCT": 0.0009, "DC_MIN_DELTA_PCT": 0.0008},
    "BNB":  {"DC_ATR_MAX_PCT": 0.0006},
    "NEAR": {"DC_ATR_MAX_PCT": 0.0015, "DC_MIN_DELTA_PCT": 0.0006, "DC_MAX_ENTRY_PRICE": 0.58},
    "ZEC":  {"DC_ATR_MAX_PCT": 0.0018, "DC_MAX_ENTRY_PRICE": 0.58},
}


def asset_param(asset: str, name: str):
    """Resolve a tunable for an asset: ASSET_OVERRIDES first, else the module
    global (which CLI flags may already have overridden)."""
    ov = ASSET_OVERRIDES.get(asset)
    if ov and name in ov:
        return ov[name]
    return globals()[name]


# ============================================================================
# CONFIG FILE (v0.6.0) — precedence: script defaults < config file < CLI flags
# ============================================================================
CONFIG_FILE_DEFAULT = "kalshi_bot_config.json"
CONFIG_FILE_USED: Optional[str] = None   # set in main(); shown in the run() header

# Explicit allowlist of module globals settable via the config file / menu.
CONFIG_SETTABLE = {
    # Strategy & assets
    "STRATEGY", "ASSETS", "KALSHI_API_BASE", "API_KEYS_DIR", "FORCE_PAPER_MODE",
    # Delta Capture core
    "DC_ENTRY_WINDOW_MIN", "DC_MIN_DELTA_PCT", "DC_MAX_DELTA_PCT",
    "DC_MAX_ENTRY_PRICE", "DC_STOCH_K_LONG_MIN", "DC_REQUIRE_K_GT_D",
    "DC_DEAD_ZONE", "DC_ATR_MAX_PCT", "DC_MAX_SPREAD_CENTS",
    # Scalp
    "DC_SCALP_ENABLED", "DC_SCALP_WINDOW_MIN", "DC_SCALP_MIN_MOVE_PCT",
    "DC_SCALP_MAX_PRICE", "DC_SCALP_K_UP", "DC_SCALP_K_DOWN", "DC_SCALP_SIZE_MULT",
    # Salvage
    "DC_SALVAGE_EXIT", "DC_SALVAGE_MIN_MINUTES", "DC_SALVAGE_MIN_FLIP_PCT",
    "DC_SALVAGE_MIN_HOLD_S",
    # MTF momentum
    "MTF_ENABLED", "MTF_TIMEFRAMES", "MTF_RSI_LEN", "MTF_RET_BARS",
    "MTF_CACHE_TTL_S", "MTF_COUNTER_TREND_BLOCK", "MTF_MIN_SCORE",
    "MTF_STRONG_SCORE", "MTF_MIN_TRADE_SCORE", "MTF_TREND_MAX_DELTA_PCT",
    "MTF_TREND_MAX_PRICE", "MTF_TREND_SIZE_MULT",
    # Indicators
    "RSI_LEN", "STOCH_LEN", "STOCH_K_SMOOTH", "STOCH_D_SMOOTH", "ATR_LEN",
    "PRICE_HISTORY_MINUTES",
    # Legacy rsi_extreme
    "ENTRY_THRESHOLD", "EXIT_THRESHOLD", "RSI_MIN_FOR_UP", "RSI_MAX_FOR_DOWN",
    "STOCH_OVERBOUGHT", "STOCH_OVERSOLD", "REQUIRE_1H_ALIGNMENT",
    "MIN_TIMEFRAME_AGREEMENT", "ENTRY_CONFIRMATION_CYCLES", "MAX_PRICE_VELOCITY",
    # Legacy indicator strategies
    "RSI_PERIOD", "RSI_OVERSOLD", "RSI_OVERBOUGHT", "RSI_DIVERGENCE_THRESHOLD",
    # Sizing
    "ORDER_SIZE", "MAX_ORDER_SIZE", "MAX_RISK_PER_TRADE_PCT",
    "MAX_CONCURRENT_POSITIONS",
    # Risk gates
    "BANKROLL", "MAX_DAILY_LOSS", "MAX_DRAWDOWN_PERCENT",
    "MAX_CONSECUTIVE_LOSSES", "PAUSE_AFTER_LOSS_STREAK_MIN",
    "MAX_LOSS_PER_SESSION", "MAX_TRADES_PER_SESSION", "POST_TRADE_COOLDOWN_SECONDS",
    # Multi-Entry / Shots on Goal (v0.6.0)
    "MAX_ENTRIES_PER_WINDOW", "REENTRY_COOLDOWN_SECONDS", "REENTRY_SIZE_DECAY",
    "REENTRY_SAME_SIDE_ALLOWED", "REENTRY_AFTER_LOSS_ONLY",
    # Exit management
    "PROFIT_TARGET", "MAX_LOSS_PER_TRADE", "EARLY_TIME_STOP_SECONDS",
    "TIME_EXIT_MINUTES", "EMERGENCY_EXIT_PRICE", "STOP_LOSS_FLOOR_PRICE",
    "TRAILING_STOP_PCT", "MIN_PROFIT_FOR_TRAILING", "MIN_HOLD_SECONDS",
    "BREAKEVEN_TRIGGER_PROFIT", "BREAKEVEN_BUFFER", "MAX_HOLD_TIME_SECONDS",
    "NO_ENTRY_FINAL_SECONDS",
    # Order execution
    "BUY_PRICE_DIFF", "AGGRESSIVE_ENTRY", "FILL_BUFFER", "DYNAMIC_FILL_BUFFER",
    "ENTRY_TIME_IN_FORCE", "ORDER_TIMEOUT_SECONDS", "EMERGENCY_MAX_RETRIES",
    "KALSHI_TAKER_FEE_COEFF",
    # Polling / display
    "POLL_INTERVAL_MONITORING_S", "POLL_INTERVAL_RELAXED_S", "PRICE_POLL_SECONDS",
    "MARKET_REFRESH_MS", "KLINES_CACHE_TTL_S", "BALANCE_CACHE_TTL_S",
    "PRETTY_DISPLAY",
    # Per-asset overrides
    "ASSET_OVERRIDES",
}

# Immutable snapshot of the script defaults (import-time), used by the config
# loader for type coercion and by the menu for diffing/reset.
_SCRIPT_DEFAULTS = {name: copy.deepcopy(globals()[name]) for name in CONFIG_SETTABLE}

_STRATEGY_CHOICES = ["delta_capture", "delta_capture_scalp", "rsi_extreme",
                     "multi_tf_confluence", "mean_reversion",
                     "momentum_breakout", "divergence_play"]


def _coerce_config_value(value, default):
    """Coerce a JSON value to the type of the script default.
    Returns (ok, coerced). Never raises."""
    try:
        if isinstance(default, bool):
            return (True, value) if isinstance(value, bool) else (False, None)
        if isinstance(default, int):
            if isinstance(value, bool):
                return False, None
            return (True, value) if isinstance(value, int) else (False, None)
        if isinstance(default, float):
            if isinstance(value, bool):
                return False, None
            return (True, float(value)) if isinstance(value, (int, float)) else (False, None)
        if isinstance(default, str):
            return (True, value) if isinstance(value, str) else (False, None)
        if isinstance(default, tuple):
            if isinstance(value, (list, tuple)) and len(value) == len(default):
                return True, tuple(type(d)(v) for d, v in zip(default, value))
            return False, None
        if isinstance(default, list):
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                return True, [v.strip().upper() for v in value if v.strip()]
            return False, None
        if isinstance(default, dict):
            return (True, value) if isinstance(value, dict) else (False, None)
    except (TypeError, ValueError):
        return False, None
    return False, None


def find_config_file(cli_path: Optional[str]) -> Optional[str]:
    """Locate the config file: explicit --config-file wins; otherwise look next
    to the script first, then the CWD. Returns None if nothing exists."""
    if cli_path:
        return cli_path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(script_dir, CONFIG_FILE_DEFAULT),
                  os.path.join(os.getcwd(), CONFIG_FILE_DEFAULT)]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    return None


def load_config_file(path: Optional[str]):
    """Apply a JSON config file to module globals (called BEFORE CLI overrides).
    Returns (path_or_None, applied_labels, messages) where messages is a list
    of (level, msg) to log once logging is set up. Never raises on bad config."""
    messages: List[Tuple[int, str]] = []
    if not path:
        return None, [], [(logging.INFO, "No config file found (using script defaults)")]
    if not os.path.exists(path):
        return None, [], [(logging.WARNING, f"Config file {path} not found (using script defaults)")]
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        return path, [], [(logging.WARNING, f"Config file {path} unreadable ({e}) — using script defaults")]
    if not isinstance(data, dict):
        return path, [], [(logging.WARNING, f"Config file {path}: top-level must be a JSON object — ignored")]

    # Deprecation shim: legacy MAX_TRADES_PER_SESSION copies into the
    # authoritative MAX_ENTRIES_PER_WINDOW (v0.6.0) unless the new key is set.
    if "MAX_TRADES_PER_SESSION" in data:
        messages.append((logging.WARNING,
                         "Config file: MAX_TRADES_PER_SESSION is deprecated (v0.6.0) — "
                         "use MAX_ENTRIES_PER_WINDOW; copying value"))
        if "MAX_ENTRIES_PER_WINDOW" not in data:
            data["MAX_ENTRIES_PER_WINDOW"] = data["MAX_TRADES_PER_SESSION"]

    applied = []
    for key, value in data.items():
        if key.startswith("_"):
            continue  # "_comment" header etc.
        if key == "MAX_TRADES_PER_SESSION":
            continue  # handled by the deprecation shim above
        if key not in CONFIG_SETTABLE:
            messages.append((logging.WARNING, f"Config file ({path}): unknown key {key!r} ignored"))
            continue
        ok, coerced = _coerce_config_value(value, _SCRIPT_DEFAULTS[key])
        if not ok:
            messages.append((logging.WARNING,
                             f"Config file ({path}): {key} has wrong type ({value!r}) — skipped"))
            continue
        if key == "STRATEGY" and coerced not in _STRATEGY_CHOICES:
            messages.append((logging.WARNING,
                             f"Config file ({path}): unknown STRATEGY {coerced!r} — skipped"))
            continue
        if key == "ASSETS":
            unknown = [a for a in coerced if a not in ASSET_SERIES_MAP]
            if unknown:
                messages.append((logging.WARNING,
                                 f"Config file ({path}): unknown asset(s) {unknown} — dropped"))
                coerced = [a for a in coerced if a in ASSET_SERIES_MAP]
            if not coerced:
                messages.append((logging.WARNING, f"Config file ({path}): ASSETS empty — skipped"))
                continue
        if key == "ASSET_OVERRIDES":
            if not all(isinstance(v, dict) for v in coerced.values()):
                messages.append((logging.WARNING,
                                 f"Config file ({path}): ASSET_OVERRIDES must map asset -> object — skipped"))
                continue
            unknown = [a for a in coerced if a not in ASSET_SERIES_MAP]
            if unknown:
                messages.append((logging.WARNING,
                                 f"Config file ({path}): ASSET_OVERRIDES unknown asset(s) {unknown} — dropped"))
                coerced = {a: v for a, v in coerced.items() if a in ASSET_SERIES_MAP}
        globals()[key] = coerced
        applied.append(f"{key}={coerced}")
    return path, applied, messages


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
        (trade_file, ['Timestamp', 'Asset', 'Side', 'EntryPrice', 'ExitPrice', 'Reason', 'PnL', 'FeeEst', 'PnLAfterFees', 'Ticker', 'Session', 'Strategy']),
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

    def get_market(self, ticker: str) -> dict:
        """Single-market lookup (used to resolve settlement of a closed window)."""
        r = self.request("GET", f"/trade-api/v2/markets/{ticker}", authenticated=False)
        data = r.get("data", {})
        return data.get("market", data) if isinstance(data, dict) else {}

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

    # --- Multi-Timeframe Momentum (v0.2.0) ---
    def _fetch_klines(self, interval: str, limit: int) -> List[list]:
        """Generic Binance kline fetch, cached MTF_CACHE_TTL_S per interval."""
        key = f"mtf:{interval}:{limit}"
        now = time.time()
        if key in self._kline_cache and now - self._kline_cache[key][0] < MTF_CACHE_TTL_S:
            return self._kline_cache[key][1]
        try:
            r = self.session.get(self.BINANCE_URL,
                                 params={"symbol": self.binance_symbol,
                                         "interval": interval, "limit": limit},
                                 timeout=10)
            r.raise_for_status()
            data = r.json()
            self._kline_cache[key] = (now, data)
            return data
        except Exception as e:
            logging.getLogger("kalshi_bot").debug(f"MTF kline fetch {interval} failed: {e}")
            return self._kline_cache.get(key, (0, []))[1]

    def momentum_score(self) -> Tuple[float, str, str]:
        """Weighted multi-timeframe momentum.
        Returns (score in [-1,+1], bias 'UP'/'DOWN'/'NEUTRAL', detail string).
        Each timeframe contributes: RSI tilt ((RSI-50)/50) + recent-return tilt
        (capped at +/-0.5) + last-candle direction, averaged, then blended by
        MTF_TIMEFRAMES weights. Timeframes that fail to fetch are skipped and
        the remaining weights renormalize, so partial outages degrade gently."""
        if not MTF_ENABLED:
            return 0.0, "NEUTRAL", "off"
        total_w, total_v, parts = 0.0, 0.0, []
        for tf, (interval, weight, limit) in MTF_TIMEFRAMES.items():
            kl = self._fetch_klines(interval, limit)
            if not kl or len(kl) < MTF_RSI_LEN + MTF_RET_BARS + 2:
                continue
            closes = [float(k[4]) for k in kl[:-1]] or [float(k[4]) for k in kl]  # closed bars only
            if len(closes) < MTF_RSI_LEN + MTF_RET_BARS + 1:
                continue
            rsi = self.rsi_series(closes, MTF_RSI_LEN)
            rsi_tilt = max(-1.0, min(1.0, (rsi[-1] - 50.0) / 50.0))
            ret = (closes[-1] - closes[-1 - MTF_RET_BARS]) / closes[-1 - MTF_RET_BARS]
            ret_tilt = max(-1.0, min(1.0, ret / 0.005))  # 0.5% move = full tilt
            candle_dir = 1.0 if closes[-1] > float(kl[-2][1]) else (-1.0 if closes[-1] < float(kl[-2][1]) else 0.0)
            tf_score = (rsi_tilt + ret_tilt + candle_dir) / 3.0
            total_w += weight
            total_v += weight * tf_score
            parts.append(f"{tf}:{tf_score:+.2f}")
        if total_w <= 0:
            return 0.0, "NEUTRAL", "no-data"
        score = total_v / total_w
        min_score = asset_param(self.asset, "MTF_MIN_SCORE")
        bias = "UP" if score >= min_score else ("DOWN" if score <= -min_score else "NEUTRAL")
        return score, bias, " ".join(parts)

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
        self.asset = feed.asset
        self.last_mtf_block: Optional[str] = None  # set when MTF gate vetoes a qualifier
        # (score, threshold) when the MTF conviction gate vetoed — logged on a
        # separate path from last_mtf_block so the two gates are distinguishable
        self.last_conviction_veto: Optional[Tuple[float, float]] = None

    # --- DEFAULT: Delta Capture + StochRSI Confirm (+ MTF filter, v0.2.0) ---
    def delta_capture(self, price: float, strike: float, mins_left: float,
                      ask_up: float, ask_down: float, spread_cents: float,
                      mtf: Tuple[float, str, str] = (0.0, "NEUTRAL", "off")) -> Optional[EntryDecision]:
        k, d = self.feed.stoch_rsi_kd()
        atr = self.feed.atr_pct()
        mtf_score, mtf_bias, mtf_detail = mtf

        # Per-asset resolution: ASSET_OVERRIDES win over (CLI-overridable) globals
        atr_max = asset_param(self.asset, "DC_ATR_MAX_PCT")
        spread_max = asset_param(self.asset, "DC_MAX_SPREAD_CENTS")
        min_trade_score = asset_param(self.asset, "MTF_MIN_TRADE_SCORE")
        ct_block = asset_param(self.asset, "MTF_COUNTER_TREND_BLOCK")
        strong_score = asset_param(self.asset, "MTF_STRONG_SCORE")
        scalp_enabled = asset_param(self.asset, "DC_SCALP_ENABLED")
        scalp_window = asset_param(self.asset, "DC_SCALP_WINDOW_MIN")
        scalp_min_move = asset_param(self.asset, "DC_SCALP_MIN_MOVE_PCT")
        scalp_max_price = asset_param(self.asset, "DC_SCALP_MAX_PRICE")
        scalp_k_up = asset_param(self.asset, "DC_SCALP_K_UP")
        scalp_k_down = asset_param(self.asset, "DC_SCALP_K_DOWN")
        scalp_size_mult = asset_param(self.asset, "DC_SCALP_SIZE_MULT")
        entry_window = asset_param(self.asset, "DC_ENTRY_WINDOW_MIN")
        min_delta = asset_param(self.asset, "DC_MIN_DELTA_PCT")
        max_delta = asset_param(self.asset, "DC_MAX_DELTA_PCT")
        max_entry_price = asset_param(self.asset, "DC_MAX_ENTRY_PRICE")
        trend_max_delta = asset_param(self.asset, "MTF_TREND_MAX_DELTA_PCT")
        trend_max_price = asset_param(self.asset, "MTF_TREND_MAX_PRICE")
        trend_size_mult = asset_param(self.asset, "MTF_TREND_SIZE_MULT")
        stoch_k_long_min = asset_param(self.asset, "DC_STOCH_K_LONG_MIN")
        require_k_gt_d = asset_param(self.asset, "DC_REQUIRE_K_GT_D")

        # Reset veto flags BEFORE every gate return — v0.4.0 reset
        # last_mtf_block only after the conviction gate, so a stale veto from
        # an earlier window made evaluate_entry log "MTF BLOCK" for windows the
        # conviction gate actually killed.
        self.last_mtf_block = None
        self.last_conviction_veto = None

        # No-trade gates (apply to all entry variants)
        if atr > atr_max:
            return None                                   # Burst volatility / whipsaw
        if spread_cents > spread_max:
            return None                                   # Spread too wide
        # Conviction gate: chop (|score| < MTF_MIN_TRADE_SCORE) produced 50% WR /
        # negative P&L in the 7-day backtest — sit those windows out entirely.
        if MTF_ENABLED and min_trade_score > 0 and abs(mtf_score) < min_trade_score:
            self.last_conviction_veto = (mtf_score, min_trade_score)
            return None

        delta = (price - strike) / strike if strike > 0 else 0.0

        # MTF counter-trend gate: don't buy the side the higher timeframes oppose
        def fights_trend(side: str) -> bool:
            blocked = (MTF_ENABLED and ct_block
                       and mtf_bias in ("UP", "DOWN") and side != mtf_bias)
            if blocked:
                self.last_mtf_block = side
            return blocked

        # MTF trend strength relaxers
        strong_up = MTF_ENABLED and mtf_score >= strong_score
        strong_down = MTF_ENABLED and mtf_score <= -strong_score
        in_dead_zone = DC_DEAD_ZONE[0] <= k <= DC_DEAD_ZONE[1]

        # Momentum scalp variant: minutes 1-3 of window, price already moving
        if scalp_enabled and scalp_window[0] <= mins_left <= scalp_window[1]:
            if in_dead_zone and not (strong_up or strong_down):
                return None
            if abs(delta) >= scalp_min_move and abs(delta) <= max_delta:
                if (delta > 0 and k > scalp_k_up and k >= d and ask_up <= scalp_max_price
                        and not fights_trend("UP")):
                    return EntryDecision("UP", f"scalp delta={delta:.4%} K={k:.0f} mtf={mtf_score:+.2f}", scalp_size_mult)
                if (delta < 0 and k < scalp_k_down and k <= d and ask_down <= scalp_max_price
                        and not fights_trend("DOWN")):
                    return EntryDecision("DOWN", f"scalp delta={delta:.4%} K={k:.0f} mtf={mtf_score:+.2f}", scalp_size_mult)
            return None  # Outside scalp conditions in early window = no trade

        # Core entry: 3-8 minutes remaining
        lo, hi = entry_window
        if not (lo <= mins_left <= hi):
            return None
        if abs(delta) < min_delta:
            return None

        # Trend-aligned relaxation: with a strong MTF tailwind the delta cap
        # widens (0.10% -> MTF_TREND_MAX_DELTA_PCT) and the StochRSI dead zone
        # is waived. Counter-trend entries keep the strict 0.10% cap.
        max_delta_up = trend_max_delta if strong_up else max_delta
        max_delta_down = trend_max_delta if strong_down else max_delta

        # UP core entry
        if delta >= min_delta and delta <= max_delta_up and not fights_trend("UP"):
            k_ok = (k > stoch_k_long_min and (not require_k_gt_d or k >= d)) and not in_dead_zone
            k_ok = k_ok or (strong_up and k > DC_DEAD_ZONE[0])  # trend override: K just needs to lean up
            relaxed = delta > max_delta or (in_dead_zone and strong_up)
            price_cap = trend_max_price if relaxed else max_entry_price
            if k_ok and ask_up <= price_cap:
                mult = trend_size_mult if relaxed else 1.0
                tag = "trend" if relaxed else "core"
                return EntryDecision("UP", f"{tag} delta={delta:.4%} K={k:.0f}>=D={d:.0f} "
                                           f"ask={ask_up:.2f} mtf={mtf_score:+.2f}[{mtf_detail}]", mult)

        # DOWN core entry
        if delta <= -min_delta and delta >= -max_delta_down and not fights_trend("DOWN"):
            k_ok = (k < (100 - stoch_k_long_min) and (not require_k_gt_d or k <= d)) and not in_dead_zone
            k_ok = k_ok or (strong_down and k < DC_DEAD_ZONE[1])  # trend override: K just needs to lean down
            relaxed = abs(delta) > max_delta or (in_dead_zone and strong_down)
            price_cap = trend_max_price if relaxed else max_entry_price
            if k_ok and ask_down <= price_cap:
                mult = trend_size_mult if relaxed else 1.0
                tag = "trend" if relaxed else "core"
                return EntryDecision("DOWN", f"{tag} delta={delta:.4%} K={k:.0f}<D={d:.0f} "
                                             f"ask={ask_down:.2f} mtf={mtf_score:+.2f}[{mtf_detail}]", mult)
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
    strike: float = 0.0
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
    entries_this_window: int = 0      # v0.6.0 multi-entry ("shots on goal")
    last_exit_side: str = ""          # side of the last closed window trade
    last_exit_reason: str = ""        # reason of the last closed window trade
    last_exit_pnl: float = 0.0        # pnl of the last closed window trade
    last_trade_close_time: float = 0.0
    last_order_time: float = 0.0
    pending_order_id: str = ""
    entry_attempts: int = 0
    last_reconcile_time: float = 0.0
    confirmation_count: int = 0
    last_proposed_side: str = ""
    emergency_retries: int = 0
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
        # Prefer the market's own strike (Kalshi benchmark) over the
        # Kraken-candle estimate — the two diverge $40-70 at times.
        mkt_strike = 0.0
        for sk in ("floor_strike", "strike", "cap_strike"):
            v = self._safe_float(m.get(sk, 0))
            if v > 0:
                mkt_strike = v
                break
        snap = {"ticker": ticker, "up": up, "down": down,
                "up_bid": yes_bid, "up_ask": yes_ask, "down_bid": no_bid, "down_ask": no_ask,
                "minutes_left": self.minutes_left(m.get("close_time", "")),
                "status": m.get("status", "open"),
                "market_strike": mkt_strike}
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
        if not self.live_orders:
            return BANKROLL  # paper mode: skip the authenticated call entirely
        now = time.time()
        bal, ts = self._balance_cache
        if now - ts < BALANCE_CACHE_TTL_S and ts > 0:
            return bal
        r = self.api.get_balance()
        data = r.get("data", {}) if r.get("status") == 200 else {}
        # Prefer the explicit dollars field; fall back to legacy "balance"
        bal = self._safe_float(data.get("balance_dollars", 0))
        if bal <= 0:
            bal = self._safe_float(data.get("balance", 0))
            if bal > 100000:  # implausibly large for dollars -> treat as cents
                bal /= 100.0
        self._balance_cache = (bal, now)
        return bal

    def has_existing_position(self, ticker: str, force: bool = False) -> bool:
        if not self.live_orders:
            return False  # paper mode: no account positions exist; skip 401s
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

    def close_position(self, asset: str, reason: str, aggressive: bool = False,
                       paper_price: float = 0.0) -> Tuple[bool, float]:
        pos = self.positions.get(asset)
        if not pos:
            return True, 0.0
        floor = EMERGENCY_EXIT_PRICE if aggressive else STOP_LOSS_FLOOR_PRICE
        # Paper mode: no real position exists, so skip account checks entirely
        # and book the exit at the live contract price (or best bid - buffer).
        if not self.live_orders:
            exit_price = paper_price
            if exit_price <= 0:
                yes_bid, _, no_bid, _ = self._orderbook_best(pos.ticker)
                bid = yes_bid if pos.side == "UP" else no_bid
                exit_price = max(bid - FILL_BUFFER, floor) if bid > 0 else floor
            return True, exit_price
        self._pos_cache.pop(pos.ticker, None)
        if not self.has_existing_position(pos.ticker):
            return True, 0.0
        for attempt in range(6):
            yes_bid, _, no_bid, _ = self._orderbook_best(pos.ticker)
            bid = yes_bid if pos.side == "UP" else no_bid
            exit_price = max(bid - FILL_BUFFER, floor) if bid > 0 else floor
            if attempt >= 3:
                exit_price = floor  # marketable limit to guarantee fill
            cents = max(1, min(99, int(round(exit_price * 100))))
            result = self.api.place_order(ticker=pos.ticker, action="sell",
                                          side="yes" if pos.side == "UP" else "no",
                                          count=pos.size, price=cents,
                                          time_in_force="immediate_or_cancel")
            if result.get("status", 0) in (200, 201):
                time.sleep(1.0)
                self._pos_cache.pop(pos.ticker, None)
                if not self.has_existing_position(pos.ticker, force=True):
                    _, avg = self._parse_fills_price(self.api.get_fills(ticker=pos.ticker))
                    actual = avg if avg > 0 else exit_price
                    return True, actual
            else:
                # Log the rejection body — v0.3.0 retried blind for 20+ minutes
                body = result.get("response_body", {})
                self.log(f"{asset} Sell rejected HTTP {result.get('status')}: "
                         f"{body.get('message','') or body or result.get('error','')}", logging.WARNING)
            self._pos_cache.pop(pos.ticker, None)
            if not self.has_existing_position(pos.ticker, force=True):
                return True, exit_price
            backoff = min(2 ** attempt, 8)
            self.log(f"{asset} Sell retry {attempt+1}/6 (backoff {backoff}s)")
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
        # v0.6.0: remember the exit for re-entry gating (same-side block /
        # after-loss-only). Cleared on the next window roll.
        if pos:
            st.last_exit_side = pos.side
        st.last_exit_reason = reason
        st.last_exit_pnl = pnl
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
        # Kalshi taker-fee estimate: coeff * C * P * (1-P) per side; settlement
        # exits have no exit-side fee.
        fee_est = 0.0
        if pos:
            c = pos.size
            fee_est = KALSHI_TAKER_FEE_COEFF * c * pos.entry_price * (1 - pos.entry_price)
            if reason not in ("SETTLEMENT",) and 0 < exit_price < 1:
                fee_est += KALSHI_TAKER_FEE_COEFF * c * exit_price * (1 - exit_price)
        with open(self.trade_file, 'a', newline='') as f:
            csv.writer(f).writerow([datetime.now(timezone.utc).isoformat(), asset,
                                    pos.side if pos else "", pos.entry_price if pos else "",
                                    exit_price, reason, pnl, round(fee_est, 4), round(pnl - fee_est, 4),
                                    pos.ticker if pos else "",
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
        # v0.6.0 multi-entry gate ("shots on goal"): up to MAX_ENTRIES_PER_WINDOW
        # entries per 15-min window per asset (default 1 = v0.5.0 behavior).
        max_entries = asset_param(asset, "MAX_ENTRIES_PER_WINDOW")
        if st.entries_this_window >= max_entries:
            return
        reentry = st.entries_this_window >= 1
        # Re-entries must wait REENTRY_COOLDOWN_SECONDS after the last exit (and
        # never less than the standard post-trade cooldown). First entry in a
        # window keeps the plain POST_TRADE_COOLDOWN_SECONDS behavior, which also
        # covers a trade in a prior window (last_trade_close_time persists).
        cooldown = (max(asset_param(asset, "REENTRY_COOLDOWN_SECONDS"), POST_TRADE_COOLDOWN_SECONDS)
                    if reentry else POST_TRADE_COOLDOWN_SECONDS)
        if time.time() - st.last_trade_close_time < cooldown:
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
            mtf = self.feeds[asset].momentum_score()
            decision = self.engines[asset].delta_capture(
                price, strike, mins_left, snap["up_ask"] or snap["up"],
                snap["down_ask"] or snap["down"], spread * 100, mtf=mtf)
            if decision is None and self.engines[asset].last_conviction_veto is not None:
                # Conviction gate vetoed (|score| too low = chop). Distinct log
                # path from the counter-trend block below (v0.4.0 conflated them
                # via a stale last_mtf_block).
                veto_score, veto_thr = self.engines[asset].last_conviction_veto
                self.log_once(f"{asset}|MTFGATE{snap['ticker']}",
                              f"{asset} MTF GATE | score {veto_score:+.2f} below conviction "
                              f"threshold {veto_thr:.2f} — sitting out chop ({mtf[2]})")
            elif decision is None and self.engines[asset].last_mtf_block:
                # Log only when the counter-trend gate actually vetoed an
                # otherwise-qualifying signal — not on every signal-less window.
                blocked_side = self.engines[asset].last_mtf_block
                self.log_once(f"{asset}|MTFBLK{snap['ticker']}",
                              f"{asset} MTF BLOCK | {blocked_side} signal vetoed | MTF {mtf[1]} "
                              f"score {mtf[0]:+.2f} ({mtf[2]})")
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

        # v0.6.0 re-entry gates (after a decision is produced, before sizing)
        if reentry:
            if (not asset_param(asset, "REENTRY_SAME_SIDE_ALLOWED")
                    and st.last_exit_pnl < 0 and decision.side == st.last_exit_side):
                self.log_once(f"{asset}|REBLK{snap['ticker']}",
                              f"{asset} RE-ENTRY BLOCK | same side {decision.side} after "
                              f"{st.last_exit_reason} loss")
                return
            if asset_param(asset, "REENTRY_AFTER_LOSS_ONLY") and st.last_exit_pnl >= 0:
                return

        spread_max = asset_param(asset, "DC_MAX_SPREAD_CENTS")
        if spread > 0 and spread * 100 > spread_max:
            self.log_once(f"{asset}|SPREAD", f"{asset} spread {spread*100:.0f}c > {spread_max}c")
            return

        entry_ask = (snap["up_ask"] or snap["up"]) if decision.side == "UP" else (snap["down_ask"] or snap["down"])
        # Size decays per shot: entry N gets decision.size_mult x decay**(N-1)
        size_mult = decision.size_mult * (asset_param(asset, "REENTRY_SIZE_DECAY") ** st.entries_this_window)
        size = self.position_size(entry_ask, size_mult)
        if reentry:
            self.log(f"{asset} RE-ENTRY {st.entries_this_window + 1}/{max_entries} {decision.side} x{size} "
                     f"@ ~{entry_ask:.2f} | {STRATEGY} | {decision.reason}")
        else:
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
        # Fill price resolution (side-aware). The fills/orders API may return a
        # YES-denominated price even for DOWN (no-side) orders — v0.3.0 blindly
        # applied `1 - price` for DOWN when price < 0.5 and booked a real 43c
        # fill as 0.57. Our own submitted limit (order_price) is always
        # side-denominated, so trust it; accept the API fill price only when it
        # agrees within a few cents.
        tracked = order_price if order_price > 0 else entry_ask
        if fill_price > 0:
            if abs(fill_price - tracked) <= 0.05:
                tracked = fill_price  # side-denominated agreement — use actual
            elif decision.side == "DOWN" and abs((1.0 - fill_price) - tracked) <= 0.05:
                tracked = 1.0 - fill_price  # provably YES-denominated — flip once
            else:
                self.log(f"{asset} fill price {fill_price:.2f} disagrees with order "
                         f"{tracked:.2f} — booking order price", logging.WARNING)
        self.positions[asset] = Position(
            asset=asset, side=decision.side, entry_price=tracked, ticker=snap["ticker"],
            size=size, entry_time=datetime.now(timezone.utc), entry_order_id=order_id,
            strategy=STRATEGY, strike=strike or 0.0,
            stop_loss=max(EXIT_THRESHOLD, tracked - MAX_LOSS_PER_TRADE),
            highest_price=tracked)
        st.phase = "IN_POSITION"
        st.entries_this_window += 1
        st.last_order_time = time.time()
        self.log(f"{asset} IN POSITION | {decision.side} @ {tracked:.2f} | {snap['ticker']} | strike ~{strike or 0:.0f}")

    def _resolve_settlement(self, pos: Position, price: float) -> Optional[float]:
        """Resolve a held position's settlement value (1.0 win / 0.0 loss).
        Uses the OLD ticker's market result from the API; falls back to
        current spot price vs the strike captured at entry. None = unknown."""
        m = self.api.get_market(pos.ticker)
        if m:
            result = str(m.get("result", "")).lower()
            if result in ("yes", "no"):
                yes_won = (result == "yes")
                return 1.0 if yes_won == (pos.side == "UP") else 0.0
            status = str(m.get("status", "")).lower()
            if status in ("settled", "finalized", "closed", "determined"):
                ref = (self._parse_price(m.get("last_price_dollars", m.get("last_price")))
                       or self._parse_price(m.get("yes_bid_dollars", m.get("yes_bid"))))
                if ref >= 0.99 or (0 < ref <= 0.01):
                    yes_won = ref >= 0.99
                    return 1.0 if yes_won == (pos.side == "UP") else 0.0
        # Fallback: settle by spot price vs entry-captured strike
        if pos.strike > 0 and price > 0:
            yes_won = price >= pos.strike
            return 1.0 if yes_won == (pos.side == "UP") else 0.0
        return None

    # ------------------------------ position management ------------------------------
    def manage_position(self, asset: str, snap: dict, price: float, strike: Optional[float]):
        pos = self.positions[asset]
        st = self.states[asset]
        mins_left = snap["minutes_left"]
        current = (snap["up_bid"] or snap["up"]) if pos.side == "UP" else (snap["down_bid"] or snap["down"])
        pnl = (current - pos.entry_price) * pos.size
        pos.max_pnl = max(pos.max_pnl, pnl)
        pos.highest_price = max(pos.highest_price, current)
        hold = (datetime.now(timezone.utc) - pos.entry_time).total_seconds()
        use_dc = pos.strategy in ("delta_capture", "delta_capture_scalp")

        def do_close(reason, aggressive=False):
            closed, exit_price = self.close_position(asset, reason, aggressive,
                                                     paper_price=current)
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
        if mins_left <= 1.0 and not use_dc:
            self.log(f"{asset} FINAL EXIT | {mins_left:.1f}m left")
            return do_close("FORCED_CLOSE", aggressive=True)

        # DC: window expired but ticker hasn't rolled yet — resolve at settlement
        if use_dc and mins_left <= 0.25:
            final = self._resolve_settlement(pos, price)
            if final is not None:
                self.record_trade(asset, (final - pos.entry_price) * pos.size, "SETTLEMENT", final)
                del self.positions[asset]
                st.phase = "WAIT_WINDOW"
            return True

        # Market moved to a new ticker (window rolled) → resolve P&L at settlement
        if snap["ticker"] != pos.ticker:
            final = self._resolve_settlement(pos, price)
            if final is None:
                return True  # Resolution unknown yet — keep checking next loop
            self.record_trade(asset, (final - pos.entry_price) * pos.size, "SETTLEMENT", final)
            del self.positions[asset]
            st.phase = "WAIT_WINDOW"
            return True

        if use_dc:
            # Delta Capture: hold to settlement; optional salvage exit on delta flip
            salvage_on = asset_param(asset, "DC_SALVAGE_EXIT")
            salvage_min_flip = asset_param(asset, "DC_SALVAGE_MIN_FLIP_PCT")
            if (salvage_on and strike and price > 0
                    and mins_left > asset_param(asset, "DC_SALVAGE_MIN_MINUTES")
                    and hold >= asset_param(asset, "DC_SALVAGE_MIN_HOLD_S")):
                delta = (price - strike) / strike
                flipped = ((pos.side == "UP" and delta < -salvage_min_flip)
                           or (pos.side == "DOWN" and delta > salvage_min_flip))
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
                 f"|  kalshi-trading-bot v0.6.0  |  {now:<33}|",
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
            lines.append(f"|    MTF:{d.get('mtf',0):+.2f} bias:{d.get('mtf_bias','-'):<8}"[:width+1] + "|")
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
        self.log(f"kalshi-trading-bot v0.6.0 | Strategy: {STRATEGY}")
        self.log(f"Mode: {'LIVE ORDERS' if self.live_orders else 'PAPER/TEST'} | Assets: {ASSETS}")
        self.log(f"Config file: {CONFIG_FILE_USED or 'none'}")
        self.log(f"Multi-entry: max {MAX_ENTRIES_PER_WINDOW}/window | cooldown {REENTRY_COOLDOWN_SECONDS}s "
                 f"| size decay {REENTRY_SIZE_DECAY} | same-side {REENTRY_SAME_SIDE_ALLOWED} "
                 f"| after-loss-only {REENTRY_AFTER_LOSS_ONLY}")
        self.log(f"Delta Capture: window {DC_ENTRY_WINDOW_MIN}m | delta {DC_MIN_DELTA_PCT:.4%}-{DC_MAX_DELTA_PCT:.4%} "
                 f"| max entry ${DC_MAX_ENTRY_PRICE} | ATR cap {DC_ATR_MAX_PCT:.4%} | spread cap {DC_MAX_SPREAD_CENTS}c")
        self.log(f"Scalp: {'on' if DC_SCALP_ENABLED else 'off'} window {DC_SCALP_WINDOW_MIN}m | "
                 f"max ${DC_SCALP_MAX_PRICE} | size x{DC_SCALP_SIZE_MULT} | salvage: {'on' if DC_SALVAGE_EXIT else 'off'}")
        self.log(f"Risk: daily loss ${MAX_DAILY_LOSS} | drawdown {MAX_DRAWDOWN_PERCENT}% | "
                 f"{MAX_CONSECUTIVE_LOSSES} straight losses -> {PAUSE_AFTER_LOSS_STREAK_MIN}m pause "
                 f"| size {ORDER_SIZE} (cap {MAX_ORDER_SIZE}) | bankroll ${BANKROLL:.0f} | profit target ${PROFIT_TARGET}")
        if MTF_ENABLED:
            tfs = "/".join(MTF_TIMEFRAMES.keys())
            self.log(f"MTF momentum: {tfs} | block counter-trend: {MTF_COUNTER_TREND_BLOCK} | "
                     f"min trade score {MTF_MIN_TRADE_SCORE} | strong >= {MTF_STRONG_SCORE} "
                     f"(delta cap {MTF_TREND_MAX_DELTA_PCT:.4%}, max ${MTF_TREND_MAX_PRICE}, "
                     f"size x{MTF_TREND_SIZE_MULT})")
        if ASSET_OVERRIDES:
            self.log(f"Asset overrides: {json.dumps(ASSET_OVERRIDES)}")
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
                        strike = snap.get("market_strike") or self.feeds[asset].window_strike()
                        # New 15-min window → reset per-session state
                        session_key = f"{asset}_{snap['ticker']}"
                        if st.session_key != session_key:
                            st.session_key = session_key
                            st.session_trade_count = 0
                            st.session_pnl = 0.0
                            st.entries_this_window = 0     # v0.6.0 multi-entry reset
                            st.last_exit_side = ""
                            st.last_exit_reason = ""
                            st.last_exit_pnl = 0.0
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
                                pos = self.positions[asset]
                                # Near/past expiry: stop selling a dead orderbook —
                                # resolve at settlement instead (defined-risk binary).
                                final = None
                                if snap["minutes_left"] <= 0.25 or snap["ticker"] != pos.ticker:
                                    final = self._resolve_settlement(pos, price)
                                if final is not None:
                                    self.record_trade(asset, (final - pos.entry_price) * pos.size,
                                                      "SETTLEMENT", final)
                                    del self.positions[asset]
                                    st.phase = "WAIT_WINDOW"
                                    st.emergency_retries = 0
                                elif st.emergency_retries >= EMERGENCY_MAX_RETRIES:
                                    # Retries exhausted: leave the position to settle;
                                    # the mins_left<=0.25 / ticker-roll paths in
                                    # manage_position will resolve it.
                                    self.log(f"{asset} emergency retries exhausted — holding to settlement",
                                             logging.WARNING)
                                    st.phase = "IN_POSITION"
                                    st.emergency_retries = 0
                                else:
                                    closed, exit_price = self.close_position(asset, "emergency_retry", aggressive=True)
                                    if closed:
                                        self.record_trade(asset, (exit_price - pos.entry_price) * pos.size,
                                                          "EMERGENCY_CLOSE", exit_price)
                                        del self.positions[asset]
                                        st.phase = "WAIT_WINDOW"
                                        st.emergency_retries = 0
                                    else:
                                        st.emergency_retries += 1
                            else:
                                self.manage_position(asset, snap, price, strike)
                        elif not halted and st.phase != "HAS_POSITION":
                            self.evaluate_entry(asset, snap, price, strike)
                        if st.phase == "HAS_POSITION" and not self.has_existing_position(snap["ticker"]):
                            st.phase = "WAIT_WINDOW"
                        with self._display_lock:
                            k, d = self.feeds[asset].stoch_rsi_kd()
                            delta = ((price - strike) / strike) if (strike and price > 0) else 0.0
                            mtf = self.feeds[asset].momentum_score()
                            self.display_data[asset] = {
                                "ticker": snap["ticker"], "up": snap["up"], "down": snap["down"],
                                "price": price, "k": k, "d": d, "delta": delta, "mins": snap["minutes_left"],
                                "mtf": mtf[0], "mtf_bias": mtf[1]}
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


def build_arg_parser() -> argparse.ArgumentParser:
    """Full CLI. Every flag maps to a module-global config variable; flags take
    precedence over the script defaults (which stay the documented baseline)."""
    p = argparse.ArgumentParser(
        description="kalshi-trading-bot v0.6.0 — Kalshi 15-min crypto up/down bot",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--config-file", metavar="PATH",
                   help="JSON config file path (default: kalshi_bot_config.json next to "
                        "the script, then CWD). Precedence: script defaults < config file < CLI flags")
    p.add_argument("--menu", "--config", dest="menu", action="store_true",
                   help="Open the interactive config-file editor menu and exit (no trading)")
    p.add_argument("--strategy", choices=["delta_capture", "delta_capture_scalp", "rsi_extreme",
                                          "multi_tf_confluence", "mean_reversion",
                                          "momentum_breakout", "divergence_play"],
                   help="Entry strategy (STRATEGY)")
    p.add_argument("--assets", help="Comma list of assets, e.g. BTC,ETH (ASSETS)")
    p.add_argument("--paper", action="store_true", help="Force paper/test mode")
    p.add_argument("--force-paper", action="store_true",
                   help="Force paper mode persistently (FORCE_PAPER_MODE=True)")
    p.add_argument("--pretty", action="store_true", help="Live terminal dashboard")
    p.add_argument("--api-base", help="Kalshi API base URL (KALSHI_API_BASE)")
    p.add_argument("--dc-window", nargs=2, type=float, metavar=("LO", "HI"),
                   help="Core entry window, minutes left (DC_ENTRY_WINDOW_MIN)")
    p.add_argument("--dc-min-delta", type=float, help="Min |delta| fraction (DC_MIN_DELTA_PCT)")
    p.add_argument("--dc-max-delta", type=float, help="Max |delta| fraction (DC_MAX_DELTA_PCT)")
    p.add_argument("--dc-max-entry-price", type=float, help="Core max entry price (DC_MAX_ENTRY_PRICE)")
    p.add_argument("--dc-atr-max-pct", type=float, help="Global 1m ATR%% cap (DC_ATR_MAX_PCT)")
    p.add_argument("--dc-scalp-max-price", type=float, help="Scalp max entry price (DC_SCALP_MAX_PRICE)")
    p.add_argument("--dc-scalp", dest="dc_scalp", action="store_true", default=None,
                   help="Enable scalp entries (DC_SCALP_ENABLED=True)")
    p.add_argument("--no-dc-scalp", dest="dc_scalp", action="store_false", default=None,
                   help="Disable scalp entries (DC_SCALP_ENABLED=False)")
    p.add_argument("--mtf-min-trade-score", type=float, help="MTF conviction gate (MTF_MIN_TRADE_SCORE)")
    p.add_argument("--mtf-strong-score", type=float, help="MTF strong-trend threshold (MTF_STRONG_SCORE)")
    p.add_argument("--mtf-min-score", type=float, help="MTF NEUTRAL-zone half-width (MTF_MIN_SCORE)")
    p.add_argument("--counter-trend-block", dest="counter_trend_block", action="store_true",
                   default=None, help="Block entries against the MTF bias")
    p.add_argument("--no-counter-trend-block", dest="counter_trend_block", action="store_false", default=None,
                   help="Allow counter-trend entries")
    p.add_argument("--order-size", type=int, help="Contracts per trade (ORDER_SIZE)")
    p.add_argument("--max-order-size", type=int, help="Hard size cap (MAX_ORDER_SIZE)")
    p.add_argument("--bankroll", type=float, help="Fallback bankroll $ (BANKROLL)")
    p.add_argument("--max-daily-loss", type=float, help="Daily loss halt $ (MAX_DAILY_LOSS)")
    p.add_argument("--max-drawdown-pct", type=float, help="Drawdown halt %% (MAX_DRAWDOWN_PERCENT)")
    p.add_argument("--profit-target", type=float, help="Take-profit price (PROFIT_TARGET)")
    p.add_argument("--salvage", dest="salvage", action="store_true", default=None,
                   help="Enable delta-flip salvage exits (DC_SALVAGE_EXIT=True)")
    p.add_argument("--no-salvage", dest="salvage", action="store_false", default=None,
                   help="Disable salvage exits (DC_SALVAGE_EXIT=False)")
    p.add_argument("--dc-salvage-min-flip", type=float,
                   help="Salvage: min flipped |delta| fraction (DC_SALVAGE_MIN_FLIP_PCT)")
    p.add_argument("--dc-salvage-min-hold", type=float,
                   help="Salvage: min hold seconds before salvage exit (DC_SALVAGE_MIN_HOLD_S)")
    p.add_argument("--max-entries-per-window", type=int,
                   help="Entries allowed per 15-min window per asset (MAX_ENTRIES_PER_WINDOW)")
    p.add_argument("--reentry-cooldown", type=float,
                   help="Min seconds after an exit before re-entering the window (REENTRY_COOLDOWN_SECONDS)")
    p.add_argument("--reentry-size-decay", type=float,
                   help="Re-entry N size multiplier decay**(N-1) (REENTRY_SIZE_DECAY)")
    p.add_argument("--reentry-same-side", dest="reentry_same_side", action="store_true", default=None,
                   help="Allow re-entry on the same side after a losing exit")
    p.add_argument("--no-reentry-same-side", dest="reentry_same_side", action="store_false", default=None,
                   help="Block re-entry on the same side after a losing exit")
    p.add_argument("--reentry-after-loss-only", dest="reentry_after_loss_only", action="store_true",
                   default=None, help="Allow extra entries only after a losing window trade")
    p.add_argument("--no-reentry-after-loss-only", dest="reentry_after_loss_only", action="store_false",
                   default=None, help="Allow extra entries after any window trade")
    p.add_argument("--asset-overrides",
                   help="Per-asset overrides as JSON, e.g. "
                        '\'{"ETH":{"MTF_MIN_TRADE_SCORE":0.15}}\' (ASSET_OVERRIDES)')
    return p


def apply_cli_overrides(args: argparse.Namespace) -> List[str]:
    """Map parsed args onto module globals BEFORE bot construction.
    Returns a human-readable list of applied overrides for the startup log."""
    applied = []

    def setg(name, value, label=None):
        globals()[name] = value
        applied.append(f"{name}={value}" + (f" ({label})" if label else ""))

    if args.strategy is not None:
        setg("STRATEGY", args.strategy)
    if args.assets is not None:
        assets = [a.strip().upper() for a in args.assets.split(",") if a.strip()]
        unknown = [a for a in assets if a not in ASSET_SERIES_MAP]
        if unknown:
            raise SystemExit(f"--assets: unknown asset(s) {unknown}; valid: {sorted(ASSET_SERIES_MAP)}")
        if not assets:
            raise SystemExit("--assets: empty list")
        setg("ASSETS", assets)  # bot feeds/engines/states are built from this
    if args.api_base is not None:
        setg("KALSHI_API_BASE", args.api_base)
    if args.dc_window is not None:
        lo, hi = args.dc_window
        if not (0 <= lo < hi <= 15):
            raise SystemExit("--dc-window: need 0 <= LO < HI <= 15")
        setg("DC_ENTRY_WINDOW_MIN", (lo, hi))
    for arg_name, glob_name in [
            ("dc_min_delta", "DC_MIN_DELTA_PCT"), ("dc_max_delta", "DC_MAX_DELTA_PCT"),
            ("dc_max_entry_price", "DC_MAX_ENTRY_PRICE"), ("dc_atr_max_pct", "DC_ATR_MAX_PCT"),
            ("dc_scalp_max_price", "DC_SCALP_MAX_PRICE"),
            ("mtf_min_trade_score", "MTF_MIN_TRADE_SCORE"),
            ("mtf_strong_score", "MTF_STRONG_SCORE"), ("mtf_min_score", "MTF_MIN_SCORE"),
            ("order_size", "ORDER_SIZE"), ("max_order_size", "MAX_ORDER_SIZE"),
            ("bankroll", "BANKROLL"), ("max_daily_loss", "MAX_DAILY_LOSS"),
            ("max_drawdown_pct", "MAX_DRAWDOWN_PERCENT"), ("profit_target", "PROFIT_TARGET"),
            ("dc_salvage_min_flip", "DC_SALVAGE_MIN_FLIP_PCT"),
            ("dc_salvage_min_hold", "DC_SALVAGE_MIN_HOLD_S"),
            ("max_entries_per_window", "MAX_ENTRIES_PER_WINDOW"),
            ("reentry_cooldown", "REENTRY_COOLDOWN_SECONDS"),
            ("reentry_size_decay", "REENTRY_SIZE_DECAY")]:
        val = getattr(args, arg_name)
        if val is not None:
            setg(glob_name, val)
    if args.dc_scalp is not None:
        setg("DC_SCALP_ENABLED", args.dc_scalp)
    if args.counter_trend_block is not None:
        setg("MTF_COUNTER_TREND_BLOCK", args.counter_trend_block)
    if args.salvage is not None:
        setg("DC_SALVAGE_EXIT", args.salvage)
    if args.reentry_same_side is not None:
        setg("REENTRY_SAME_SIDE_ALLOWED", args.reentry_same_side)
    if args.reentry_after_loss_only is not None:
        setg("REENTRY_AFTER_LOSS_ONLY", args.reentry_after_loss_only)
    if args.force_paper:
        setg("FORCE_PAPER_MODE", True)
    if args.asset_overrides is not None:
        try:
            ov = json.loads(args.asset_overrides)
        except json.JSONDecodeError as e:
            raise SystemExit(f"--asset-overrides: invalid JSON: {e}")
        if not isinstance(ov, dict) or not all(isinstance(v, dict) for v in ov.values()):
            raise SystemExit("--asset-overrides: must be a JSON object of {asset: {PARAM: value}}")
        unknown = [a for a in ov if a not in ASSET_SERIES_MAP]
        if unknown:
            raise SystemExit(f"--asset-overrides: unknown asset(s) {unknown}")
        setg("ASSET_OVERRIDES", ov)
    return applied


# ============================================================================
# INTERACTIVE CONFIG MENU (v0.6.0) — pure stdlib; edits the config file and
# exits (never starts trading). Works with piped stdin; EOFError / Ctrl-C is
# treated as exit-without-saving.
# ============================================================================
MENU_SECTIONS = [
    ("Strategy & Assets", ["STRATEGY", "ASSETS", "FORCE_PAPER_MODE", "PRETTY_DISPLAY", "KALSHI_API_BASE"]),
    ("Delta Capture core", ["DC_ENTRY_WINDOW_MIN", "DC_MIN_DELTA_PCT", "DC_MAX_DELTA_PCT",
                            "DC_MAX_ENTRY_PRICE", "DC_STOCH_K_LONG_MIN", "DC_REQUIRE_K_GT_D",
                            "DC_DEAD_ZONE", "DC_ATR_MAX_PCT", "DC_MAX_SPREAD_CENTS"]),
    ("Scalp", ["DC_SCALP_ENABLED", "DC_SCALP_WINDOW_MIN", "DC_SCALP_MIN_MOVE_PCT",
               "DC_SCALP_MAX_PRICE", "DC_SCALP_K_UP", "DC_SCALP_K_DOWN", "DC_SCALP_SIZE_MULT"]),
    ("MTF momentum", ["MTF_ENABLED", "MTF_COUNTER_TREND_BLOCK", "MTF_MIN_SCORE", "MTF_STRONG_SCORE",
                      "MTF_MIN_TRADE_SCORE", "MTF_TREND_MAX_DELTA_PCT", "MTF_TREND_MAX_PRICE",
                      "MTF_TREND_SIZE_MULT"]),
    ("Multi-Entry / Shots on Goal", ["MAX_ENTRIES_PER_WINDOW", "REENTRY_COOLDOWN_SECONDS",
                                     "REENTRY_SIZE_DECAY", "REENTRY_SAME_SIDE_ALLOWED",
                                     "REENTRY_AFTER_LOSS_ONLY"]),
    ("Risk & Sizing", ["ORDER_SIZE", "MAX_ORDER_SIZE", "MAX_RISK_PER_TRADE_PCT", "BANKROLL",
                       "MAX_DAILY_LOSS", "MAX_DRAWDOWN_PERCENT", "MAX_CONSECUTIVE_LOSSES",
                       "PAUSE_AFTER_LOSS_STREAK_MIN", "POST_TRADE_COOLDOWN_SECONDS"]),
    ("Exits & Salvage", ["DC_SALVAGE_EXIT", "DC_SALVAGE_MIN_MINUTES", "DC_SALVAGE_MIN_FLIP_PCT",
                         "DC_SALVAGE_MIN_HOLD_S", "PROFIT_TARGET", "NO_ENTRY_FINAL_SECONDS"]),
    ("Per-Asset Overrides", None),  # special JSON editor for ASSET_OVERRIDES
]

_MENU_PRICE_PARAMS = {"DC_MAX_ENTRY_PRICE", "DC_SCALP_MAX_PRICE", "MTF_TREND_MAX_PRICE", "PROFIT_TARGET"}
_MENU_TUPLE_PARAMS = {"DC_ENTRY_WINDOW_MIN", "DC_DEAD_ZONE", "DC_SCALP_WINDOW_MIN"}


def _menu_fmt(v) -> str:
    return str(v)


def _menu_parse_value(name: str, text: str, default):
    """Parse user input according to the script default's type.
    Returns (ok, value_or_error_message). Never raises."""
    text = text.strip()
    if isinstance(default, bool):
        t = text.lower()
        if t in ("y", "yes", "true", "1"):
            return True, True
        if t in ("n", "no", "false", "0"):
            return True, False
        return False, "enter y/n/true/false/1/0"
    if isinstance(default, int):
        try:
            return True, int(text)
        except ValueError:
            return False, "enter an integer"
    if isinstance(default, float):
        try:
            return True, float(text)
        except ValueError:
            return False, "enter a number"
    if isinstance(default, str):
        return (True, text) if text else (False, "empty value")
    if isinstance(default, tuple):
        parts = [p for p in text.replace(",", " ").split() if p]
        if len(parts) != len(default):
            return False, f"enter {len(default)} numbers ('lo hi' or 'lo,hi')"
        try:
            return True, tuple(type(d)(p) for d, p in zip(default, parts))
        except (TypeError, ValueError):
            return False, "invalid number"
    if isinstance(default, list):
        vals = [p.strip().upper() for p in text.split(",") if p.strip()]
        return (True, vals) if vals else (False, "enter a comma-separated list")
    if isinstance(default, dict):
        try:
            v = json.loads(text)
        except json.JSONDecodeError as e:
            return False, f"invalid JSON: {e}"
        return (True, v) if isinstance(v, dict) else (False, "enter a JSON object")
    return False, "unsupported type"


def _menu_validate(name: str, value) -> Optional[str]:
    """Range validation where obvious. Returns an error string or None."""
    if name in _MENU_PRICE_PARAMS and not (0 < value < 1):
        return "price must satisfy 0 < price < 1"
    if name in _MENU_TUPLE_PARAMS and not (value[0] < value[1]):
        return "need LO < HI"
    if name == "STRATEGY" and value not in _STRATEGY_CHOICES:
        return f"unknown strategy; valid: {_STRATEGY_CHOICES}"
    if name == "ASSETS":
        unknown = [a for a in value if a not in ASSET_SERIES_MAP]
        if unknown:
            return f"unknown asset(s) {unknown}; valid: {sorted(ASSET_SERIES_MAP)}"
    if name == "MAX_ENTRIES_PER_WINDOW" and value < 1:
        return "must be >= 1"
    if name == "REENTRY_SIZE_DECAY" and not (0 < value <= 1):
        return "decay must satisfy 0 < decay <= 1"
    if name in ("REENTRY_COOLDOWN_SECONDS", "POST_TRADE_COOLDOWN_SECONDS",
                "DC_SALVAGE_MIN_HOLD_S", "NO_ENTRY_FINAL_SECONDS") and value < 0:
        return "must be >= 0"
    return None


def run_config_menu(cli_path: Optional[str]) -> Optional[str]:
    """Terminal menu that edits the JSON config file and exits. Returns the path
    written on save, None otherwise."""
    if cli_path:
        path = cli_path
    else:
        path = find_config_file(None) or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), CONFIG_FILE_DEFAULT)

    # Effective values = script defaults + existing config file (coerced).
    values = copy.deepcopy(_SCRIPT_DEFAULTS)
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    if k.startswith("_"):
                        continue
                    kk = "MAX_ENTRIES_PER_WINDOW" if k == "MAX_TRADES_PER_SESSION" else k
                    if kk in values:
                        ok, cv = _coerce_config_value(v, values[kk])
                        if ok:
                            values[kk] = cv
        except Exception as e:
            print(f"Warning: could not read {path}: {e}")

    def edit_section(title: str, names: List[str]):
        while True:
            print(f"\n--- {title} ---")
            for i, name in enumerate(names, 1):
                print(f"  {i}) {name} = {_menu_fmt(values[name])} "
                      f"(default: {_menu_fmt(_SCRIPT_DEFAULTS[name])})")
            print("  b) back")
            sel = input("Select parameter: ").strip().lower()
            if sel == "b":
                return
            if not sel.isdigit() or not (1 <= int(sel) <= len(names)):
                print("Invalid choice.")
                continue
            name = names[int(sel) - 1]
            while True:
                raw = input(f"New value for {name} (empty = cancel, r = reset to default): ").strip()
                if raw == "":
                    break
                if raw.lower() == "r":
                    values[name] = copy.deepcopy(_SCRIPT_DEFAULTS[name])
                    print(f"{name} reset to default {_menu_fmt(_SCRIPT_DEFAULTS[name])}")
                    break
                ok, v = _menu_parse_value(name, raw, _SCRIPT_DEFAULTS[name])
                if not ok:
                    print(f"Invalid: {v}")
                    continue
                err = _menu_validate(name, v)
                if err:
                    print(f"Invalid: {err}")
                    continue
                values[name] = v
                print(f"{name} = {_menu_fmt(v)}")
                break
            return  # back to the main menu after each edit

    def edit_overrides():
        while True:
            print("\n--- Per-Asset Overrides (ASSET_OVERRIDES) ---")
            ov = values["ASSET_OVERRIDES"]
            assets = sorted(set(ASSET_SERIES_MAP) | set(ov))
            for i, a in enumerate(assets, 1):
                print(f"  {i}) {a} = {json.dumps(ov.get(a, {}))}")
            print("  b) back")
            sel = input("Select asset (number or symbol): ").strip()
            if sel.lower() == "b":
                return
            if sel.isdigit() and 1 <= int(sel) <= len(assets):
                asset = assets[int(sel) - 1]
            else:
                asset = sel.upper()
                if asset not in ASSET_SERIES_MAP:
                    print(f"Unknown asset {asset!r}. Valid: {sorted(ASSET_SERIES_MAP)}")
                    continue
            while True:
                raw = input(f"JSON overrides for {asset} (empty = cancel, r = remove): ").strip()
                if raw == "":
                    break
                if raw.lower() == "r":
                    ov.pop(asset, None)
                    print(f"{asset} overrides removed")
                    break
                try:
                    v = json.loads(raw)
                except json.JSONDecodeError as e:
                    print(f"Invalid JSON: {e}")
                    continue
                if not isinstance(v, dict):
                    print('Must be a JSON object, e.g. {"DC_ATR_MAX_PCT": 0.001}')
                    continue
                bad = [k for k in v if k not in CONFIG_SETTABLE or k == "ASSET_OVERRIDES"]
                if bad:
                    print(f"Unknown param(s) {bad}")
                    continue
                ov[asset] = v
                print(f"{asset} = {json.dumps(v)}")
                break
            return  # back to the main menu after each edit

    def save() -> str:
        diff = {"_comment": "kalshi-trading-bot config file. Precedence: script defaults < "
                            "this file < CLI flags. Only values that differ from the script "
                            "defaults are stored here. Edit via: python3 kalshi_trading_bot.py --menu"}
        for name in sorted(values):
            if values[name] != _SCRIPT_DEFAULTS[name]:
                diff[name] = values[name]
        with open(path, "w") as f:
            json.dump(diff, f, indent=2)
            f.write("\n")
        print(f"Saved {path} ({len(diff) - 1} override(s))")
        return path

    try:
        while True:
            print("\n=== kalshi-trading-bot v0.6.0 — config editor ===")
            print(f"Target config file: {path}")
            for i, (title, _) in enumerate(MENU_SECTIONS, 1):
                print(f"  {i}) {title}")
            print("  9) Save & exit")
            print("  0) Exit without saving")
            choice = input("Select section: ").strip().lower()
            if choice == "9":
                return save()
            if choice == "0":
                print("Exiting without saving.")
                return None
            if choice.isdigit() and 1 <= int(choice) <= len(MENU_SECTIONS):
                title, names = MENU_SECTIONS[int(choice) - 1]
                if names is None:
                    edit_overrides()
                else:
                    edit_section(title, names)
            else:
                print("Invalid choice.")
    except (EOFError, KeyboardInterrupt):
        print("\nExiting without saving.")
        return None


def main():
    global PRETTY_DISPLAY, CONFIG_FILE_USED
    args = build_arg_parser().parse_args()
    if args.menu:
        run_config_menu(args.config_file)
        return
    # Precedence: script defaults < config file < CLI flags.
    cfg_path, cfg_applied, cfg_messages = load_config_file(find_config_file(args.config_file))
    CONFIG_FILE_USED = cfg_path
    cli_overrides = apply_cli_overrides(args)  # sets module globals pre-construction
    if args.pretty:
        PRETTY_DISPLAY = True
        cli_overrides.append("PRETTY_DISPLAY=True")

    logger, log_file, trade_file, perf_file = setup_logging(pretty_display=PRETTY_DISPLAY)
    logger.info(f"Log: {log_file} | Trades: {trade_file} | Perf: {perf_file}")
    for level, msg in cfg_messages:
        logger.log(level, msg)
    if cfg_applied:
        logger.info(f"Config file ({cfg_path}): {' | '.join(cfg_applied)}")
    if cli_overrides:
        logger.info(f"CLI override: {' | '.join(cli_overrides)}")

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
