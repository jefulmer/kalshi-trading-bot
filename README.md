# kalshi-trading-bot

**v0.1.0-beta** — An automated trading bot for Kalshi's 15-minute cryptocurrency up/down
binary markets (BTC by default; ETH, SOL, XRP, DOGE, HYPE, BNB supported).

The default strategy is **Delta Capture + StochRSI Confirm**: instead of guessing direction
at the start of a 15-minute window (which backtests below 50% win rate), the bot waits until
3–8 minutes remain, checks whether the live price is already on one side of the window's
strike, and only enters when the contract is still priced below what live conditions imply —
with 1-minute StochRSI confirming short-term momentum.

> **Disclaimer:** Trading involves risk of loss. This software is provided as-is, with no
> warranty. Start in paper mode, validate on the Kalshi demo environment, and never risk
> money you cannot afford to lose.

---

## Download & Install

```bash
# Clone the repository
git clone https://github.com/jefulmer/kalshi-trading-bot.git
cd kalshi-trading-bot

# Install dependencies (Python 3.9+)
pip install requests cryptography
```

Or download the ZIP from GitHub: **Code → Download ZIP**, extract it, and open a terminal
in that folder.

## Quick Start (Paper Mode — No Account Needed)

```bash
python3 kalshi_trading_bot.py
```

With no API keys present, the bot automatically runs in **PAPER/TEST mode**: it connects to
live market data, evaluates every rule, and logs what it *would* have traded. No orders are
sent. Watch the console or the files in `logs/` to see every decision.

Stop the bot any time with **Ctrl+C** — it prints a session summary on exit.

## Adding API Keys (Live Trading)

1. Log in to [Kalshi](https://kalshi.com) → **Settings → API** → generate an API key
   (an API Key ID plus an RSA private key file).
2. In the folder containing `kalshi_trading_bot.py`, create a subfolder named `api_keys`:

   ```
   kalshi-trading-bot/
   ├── kalshi_trading_bot.py
   └── api_keys/
       ├── apikey.json        ← your API Key ID
       └── privatekey.json    ← your RSA private key
   ```

3. File formats — either JSON with a `code` field or raw text:

   **`api_keys/apikey.json`**
   ```json
   {"code": "your-api-key-id-here"}
   ```

   **`api_keys/privatekey.json`** — paste the full PEM private key, or save it as raw text
   (e.g. `privatekey.txt` also works; any file with "privatekey"/"secret" in the name):

   ```
   -----BEGIN RSA PRIVATE KEY-----
   ...
   -----END RSA PRIVATE KEY-----
   ```

4. Run the bot. On startup it logs which mode it selected:

   - `API keys found in api_keys/ — LIVE ORDER MODE enabled` → real orders, real money.
   - `No API keys in api_keys/ — defaulting to PAPER/TEST MODE` → simulation only.

**Safety overrides:**

- Set `FORCE_PAPER_MODE = True` in the script to paper-trade even with keys present.
- Or run with `python3 kalshi_trading_bot.py --paper`.
- To use the Kalshi **demo** environment, change `KALSHI_API_BASE` to
  `https://demo-api.kalshi.co` and use demo API keys.

## Configuration — No Config File, Edit the Script

All settings are variables in the clearly marked `CONFIGURATION` block at the top of
`kalshi_trading_bot.py`, each with a comment. Save the file and restart the bot to apply.
The bot logs every active setting at startup (check `logs/`), so you can always confirm
what is running.

### Choosing a strategy

| Variable | Values | Effect |
|---|---|---|
| `STRATEGY` | `"delta_capture"` (default) | Delta Capture + StochRSI Confirm — timed entries vs. strike |
| | `"delta_capture_scalp"` | Same, emphasizing the early-window momentum scalp variant |
| | `"rsi_extreme"` | Legacy: enter strong favorites (≥ `ENTRY_THRESHOLD`) with RSI/StochRSI filters |
| | `"multi_tf_confluence"` | 15m RSI oversold → UP / overbought → DOWN |
| | `"mean_reversion"` | Bollinger-band break + RSI extreme |
| | `"momentum_breakout"` | RSI crossing 50 with momentum |
| | `"divergence_play"` | Price/RSI divergence |

### Key variables and what they change

**Market & mode**
- `ASSETS` — list of coins to trade (e.g. `["BTC"]` or `["BTC", "ETH"]`).
- `KALSHI_API_BASE` — production or demo API URL.
- `FORCE_PAPER_MODE` — `True` forces simulation regardless of API keys.

**Delta Capture strategy (default)**
- `DC_ENTRY_WINDOW_MIN = (3.0, 8.0)` — only enter when 3–8 minutes remain in the window.
- `DC_MIN_DELTA_PCT / DC_MAX_DELTA_PCT` — how far price must be from strike (0.02%–0.10%).
  Widen the minimum in choppy markets; the maximum blocks spike-chasing.
- `DC_MAX_ENTRY_PRICE = 0.70` — never pay more than 70¢. Lower = pickier, better R/R.
- `DC_ATR_MAX_PCT` — skips entries during burst volatility.
- `DC_MAX_SPREAD_CENTS` — skips thin/wide order books.
- `DC_SCALP_*` — the optional early-window momentum scalp (half size).
- `DC_SALVAGE_EXIT` — sell early if the delta flips against you with >5 min left.

**Sizing & risk**
- `ORDER_SIZE` / `MAX_ORDER_SIZE` — contracts per trade (hard safety cap: 1 by default).
- `MAX_RISK_PER_TRADE_PCT = 2.0` — per-trade risk capped at 2% of bankroll.
- `MAX_DAILY_LOSS` — halt all entries after losing this much in a day.
- `MAX_DRAWDOWN_PERCENT` — halt if daily loss exceeds this % of balance.
- `MAX_CONSECUTIVE_LOSSES` + `PAUSE_AFTER_LOSS_STREAK_MIN` — 3 straight losses → 60-min pause.
- `MAX_TRADES_PER_SESSION` — trades allowed per 15-min window.

**Exits (legacy strategies; Delta Capture holds to settlement)**
- `PROFIT_TARGET`, `TRAILING_STOP_PCT`, `MAX_LOSS_PER_TRADE`, `TIME_EXIT_MINUTES`,
  `EMERGENCY_EXIT_PRICE`, `STOP_LOSS_FLOOR_PRICE` — exit ladder and worst-case slippage floors.

**Polling (leave at defaults to stay within API rate limits)**
- `PRICE_POLL_SECONDS`, `MARKET_REFRESH_MS`, `POLL_INTERVAL_*` — request pacing with
  built-in caching and 429/5xx retry backoff.

## Logging & Troubleshooting

Everything is written to the `logs/` subfolder (created automatically):

| File | Contents |
|---|---|
| `logs/kalshi_bot_<timestamp>.log` | Full verbose log: complete config dump at startup, per-asset status every 60s (price, strike, delta, K/D, ATR, order book, time left), every entry decision and every block reason, order placement/fill details, exits, and risk-gate triggers |
| `logs/trades_<timestamp>.csv` | One row per closed trade: side, entry/exit price, reason, P&L, strategy |
| `logs/perf_<timestamp>.csv` | Running performance per asset: trades, wins, win rate, cumulative P&L |

If something looks wrong, open the newest `kalshi_bot_*.log` first — the config dump at the
top shows exactly what was running, and `STATUS` lines show why the bot did or didn't trade.

Optional live dashboard:

```bash
python3 kalshi_trading_bot.py --pretty
```

## Command-Line Options

```
python3 kalshi_trading_bot.py [--paper] [--pretty]
```

- `--paper` — force paper/test mode even if API keys exist.
- `--pretty` — live terminal dashboard instead of scrolling logs.

## Recommended Rollout

1. **Paper mode** for at least 100 windows (~25 hours) — confirm win rate ≥ 57% at average
   entry ≤ 0.65 in `logs/perf_*.csv` before going live.
2. **Kalshi demo** with demo API keys to verify order placement and fill handling.
3. **Live** with `MAX_ORDER_SIZE = 1` and conservative `MAX_DAILY_LOSS` until 50+ live
   trades confirm the paper results.
