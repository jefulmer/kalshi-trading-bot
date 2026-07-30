# kalshi-trading-bot v0.6.0

Automated trading bot for Kalshi 15-minute crypto up/down markets: **BTC, ETH, SOL, XRP, DOGE, BNB, HYPE, NEAR, ZEC** (new in v0.6.0: NEAR, ZEC).

**Strategy:** Delta Capture + StochRSI Confirm with a Multi-Timeframe (MTF) momentum filter. Inside a 15-min window (core: 3–8 min left; scalp: 12–14 min left), enter only when price is already on your side of the strike, the contract is under the price cap, 1m StochRSI confirms, volatility is under the per-asset ATR cap, and higher-timeframe momentum doesn't oppose the trade.

## Files

| File | Purpose |
|---|---|
| `kalshi_trading_bot.py` | The bot (single file) |
| `kalshi_bot_config.json` | Config file — overrides script defaults (CLI overrides both) |
| `api_keys/` | Your Kalshi credentials (you create this — see below) |
| `logs/` | Runtime logs + trade/perf CSVs (created on run) |

## Setup

```bash
pip install requests cryptography numpy scipy   # numpy/scipy only needed for the backtester

# Live trading: put credentials in ./api_keys/
#   api_keys/apikey.json       -> {"code": "your-key-id"}  (or raw text)
#   api_keys/privatekey.json   -> {"code": "-----BEGIN PRIVATE KEY-----\n..."} (or raw .pem text)
# No api_keys/ folder -> automatic PAPER mode.
```

## Run

```bash
python3 kalshi_trading_bot.py                                   # paper mode, BTC only (defaults)
python3 kalshi_trading_bot.py --paper --assets BTC,ETH,SOL,XRP,DOGE,BNB,NEAR,ZEC
python3 kalshi_trading_bot.py --pretty                          # live terminal dashboard
```

## Configuration: three layers

**Script defaults < `kalshi_bot_config.json` < CLI flags.** Startup logs show each layer applied, so you can always see which value won.

```bash
# 1) Edit the config file interactively (grouped menu, validates input,
#    writes only diffs from defaults, 'r' resets a param to default):
python3 kalshi_trading_bot.py --menu          # or --config
python3 kalshi_trading_bot.py --menu --config-file /path/to/alt.json

# 2) Or hand-edit kalshi_bot_config.json — flat JSON keyed by the variable
#    names in the script header, e.g.:
#    {"MAX_ENTRIES_PER_WINDOW": 3, "DC_MAX_ENTRY_PRICE": 0.60,
#     "ASSET_OVERRIDES": {"SOL": {"DC_MIN_DELTA_PCT": 0.0005}}}

# 3) CLI always wins, one-off experiments:
python3 kalshi_trading_bot.py --paper --max-entries-per-window 3 --dc-max-entry-price 0.60
```

### Multiple shots on goal (multi-entry, new in v0.6.0)

| Variable | Default | Meaning |
|---|---|---|
| `MAX_ENTRIES_PER_WINDOW` | 1 | Total entries allowed per 15-min window per asset |
| `REENTRY_COOLDOWN_SECONDS` | 120 | Min wait after an exit before re-entering the same window |
| `REENTRY_SIZE_DECAY` | 0.5 | Re-entry N trades at size × decay^(N−1) |
| `REENTRY_SAME_SIDE_ALLOWED` | False | After a losing exit, block re-entering the side that just failed |
| `REENTRY_AFTER_LOSS_ONLY` | False | True = extra shots only after a loss (no adding after wins) |

Shipped `kalshi_bot_config.json` sets `MAX_ENTRIES_PER_WINDOW: 2`. Backtest note: with the current entry discipline, second shots fire only on windows that genuinely re-qualify.

### Per-asset tuning

`ASSET_OVERRIDES` (script, config file, menu section 8, or `--asset-overrides '{"ETH":{...}}'`) overrides any entry tunable per asset. v0.6.0 ships 30-day-calibrated per-asset min-deltas, ATR caps, and NEAR/ZEC price caps.

## Safety rails (unchanged)

Paper mode auto without keys · `FORCE_PAPER_MODE` · daily loss halt ($10) · drawdown halt (15%) · 3 consecutive losses → 60m pause · hard size cap · per-trade risk ≤2% of bankroll · fee-adjusted P&L logging · rate-limit-safe polling with 429/5xx backoff.

**ZEC and NEAR are backtest-calibrated but have no live fill data — paper-test them before going live.** DOGE is effectively opt-in now (very high min-delta bar).

## Disclaimer

Experimental software. Prediction-market binaries can go to zero. Start in paper mode, size small, and never trade money you can't afford to lose.
