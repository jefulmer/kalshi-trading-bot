# kalshi-trading-bot

Automated trading bot for Kalshi 15-minute crypto up/down markets (default: BTC, series `KXBTC15M`).

**Version:** 0.2.0 (2026-07-27)

## Overview

The default strategy is **Delta Capture + StochRSI Confirm**: enter a 15-minute window with 3–8 minutes remaining, only when spot price is already on your side of the strike, the contract is underpriced relative to live conditions, and 1-minute StochRSI confirms short-term momentum. Positions are treated as defined-risk binaries and held to settlement, with an optional salvage exit if the price delta flips decisively against the position.

Six legacy strategies are retained and selectable via the `STRATEGY` variable at the top of the script.

## Features

- Paper/test mode automatically when no API keys are present (accurate paper P&L booked at live market prices)
- Live trading with RSA-signed Kalshi API requests, fill verification, and order retry logic
- 1-minute price feed (Kraken primary, Binance fallback) with rolling buffer for StochRSI/ATR
- Risk gates: daily loss limit, drawdown halt, 3-consecutive-loss 60-minute pause, per-window trade cap, post-trade cooldown
- Rate-limit-safe: response caching, adaptive polling, automatic retry with backoff on 429/5xx
- CSV logging of every trade and running performance stats
- Optional live terminal dashboard (`--pretty`)

## Requirements

- Python 3.10+
- `pip install requests cryptography`

## Setup

1. Clone the repo and install dependencies:
   ```bash
   pip install requests cryptography
   ```
2. **Paper mode:** do nothing — with no keys present the bot paper-trades automatically.
3. **Live mode:** create an `api_keys/` folder next to the script containing:
   - `apikey.json` — your Kalshi API key ID (JSON with a `code` field, or raw text)
   - `privatekey.json` — your RSA private key PEM (JSON with a `code` field, or raw text)

   Keep `api_keys/` out of version control (it is in `.gitignore` — never commit keys).

## Usage

```bash
python3 kalshi_trading_bot.py            # normal run
python3 kalshi_trading_bot.py --paper    # force paper mode even if keys exist
python3 kalshi_trading_bot.py --pretty   # live terminal dashboard
```

Stop with `Ctrl+C` — a session summary (trades, win rate, P&L) is printed on exit.

## Configuration

All settings are variables at the top of `kalshi_trading_bot.py` (no config file). Key groups:

| Group | Highlights |
|---|---|
| Strategy | `STRATEGY`, `ASSETS` |
| Delta Capture | entry window 3–8 min, delta band 0.02%–0.10%, max entry $0.70, ATR/spread caps, scalp variant, salvage-exit tuning |
| Sizing | `ORDER_SIZE`, `MAX_ORDER_SIZE`, 2%-of-bankroll risk cap |
| Risk gates | `MAX_DAILY_LOSS`, `MAX_DRAWDOWN_PERCENT`, `MAX_CONSECUTIVE_LOSSES`, `PAUSE_AFTER_LOSS_STREAK_MIN` |
| Exits | `PROFIT_TARGET`, `TIME_EXIT_MINUTES`, stop/trailing settings (legacy strategies) |
| Polling | conservative defaults — do not lower (Kalshi + exchange rate limits) |

## Output

All output lands in `logs/`:

- `kalshi_bot_<timestamp>.log` — full DEBUG log
- `trades_<timestamp>.csv` — one row per closed trade (side, entry/exit, reason, P&L)
- `perf_<timestamp>.csv` — running win/loss and P&L snapshot per trade

## Exit reasons

| Reason | Meaning |
|---|---|
| `SETTLEMENT` | Held to window close; resolved from the market result (or price vs. strike fallback) |
| `PROFIT_TARGET` | Contract bid reached `PROFIT_TARGET` |
| `DELTA_FLIP_SALVAGE` | Delta flipped decisively against the position with time left — cut early |
| `TIME_EXIT` / `FORCED_CLOSE` | Legacy strategies only: forced exit near window close |
| `STOP_LOSS` / `TRAILING_STOP` / `EARLY_TIME_STOP` / `MAX_HOLD_TIME` | Legacy strategy exits |

## Disclaimer

For educational purposes. Trading prediction markets involves substantial risk of loss. Test thoroughly in paper mode before enabling live orders.
