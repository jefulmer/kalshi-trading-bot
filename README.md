# kalshi-trading-bot

Automated trading bot for **Kalshi 15-minute crypto up/down markets** (default: BTC, series `KXBTC15M`).
Single-file Python 3 script — no config file; all settings are variables at the top of `kalshi_trading_bot.py`.

**Current version: v0.4.0** (2026-07-28)

## Strategy — "Delta Capture + StochRSI Confirm" (+ MTF engine)

1. **Strike capture** — the window strike is read from the Kalshi market object (fallback: Kraken 1m candle close at window open).
2. **Core entry (3–8 min left)** — enter only when spot is already on your side of the strike by 0.02%–0.10%, the contract ask is ≤ $0.62, 1-minute StochRSI confirms momentum, and the **MTF conviction gate** (|multi-timeframe score| ≥ 0.20) shows the market is trending, not chopping.
3. **Momentum scalp (12–14 min left)** — half-size early entries when price is already moving (ask ≤ $0.58).
4. **MTF trend relaxation** — with a strong multi-timeframe tailwind (score ≥ 0.40) the delta cap widens to 0.25% and entries up to $0.68 are allowed at half size.
5. **Counter-trend gate** — entries fighting the higher-timeframe bias are vetoed.
6. **Exits** — binary defined-risk: positions ride to settlement by default. Optional salvage exit on a confirmed delta flip; profit target at $0.92. Emergency exits are capped and fall back to settlement resolution (no more infinite sell-retry loops).

## Quick start

```bash
pip install requests cryptography
python3 kalshi_trading_bot.py            # auto paper mode if no keys
python3 kalshi_trading_bot.py --pretty   # live terminal dashboard
python3 kalshi_trading_bot.py --paper    # force paper even with keys present
```

### API keys (for LIVE trading)

Create `api_keys/` next to the script:

```
api_keys/
├── apikey.json        # {"code": "your-kalshi-api-key-id"}  (or raw text)
└── privatekey.json    # {"code": "-----BEGIN PRIVATE KEY-----\n..."}  (or raw PEM text)
```

- Keys found → **LIVE ORDER MODE** (real money). No keys → paper/test mode.
- Set `FORCE_PAPER_MODE = True` in the script to always paper-trade.
- Demo environment: switch `KALSHI_API_BASE` to `https://demo-api.kalshi.co` and use `apikey_demo.json` / `privatekey_demo.json`.

## Output

Runtime files land in `logs/`:

| File | Contents |
|---|---|
| `kalshi_bot_<ts>.log` | Full event log (windows, entries, exits, MTF vetoes, order rejections) |
| `trades_<ts>.csv` | Per-trade record incl. **FeeEst** and **PnLAfterFees** columns |
| `perf_<ts>.csv` | Running totals, win rate, consecutive losses |

## Risk controls (defaults)

- `MAX_ORDER_SIZE = 1` contract hard cap; per-trade risk ≤ 2% of bankroll
- `MAX_DAILY_LOSS = $10` halt; `MAX_DRAWDOWN_PERCENT = 15%` halt
- 3 consecutive losses → 60-minute pause
- 1 trade per 15-min window; 90s post-trade cooldown; max 2 entry attempts per window

## Key config (top of script)

| Variable | Default | Notes |
|---|---|---|
| `STRATEGY` | `delta_capture` | Legacy strategies still selectable |
| `DC_ENTRY_WINDOW_MIN` | (3.0, 8.0) | Core entry window (minutes left) |
| `DC_MAX_ENTRY_PRICE` | 0.62 | Never pay more — expectancy gate |
| `DC_ATR_MAX_PCT` | 0.00045 | Skip burst volatility (tuned on 7-day backtest) |
| `MTF_MIN_TRADE_SCORE` | 0.20 | **New v0.4.0** conviction gate — biggest win-rate lever |
| `MTF_STRONG_SCORE` | 0.40 | Trend-relaxation threshold |
| `MTF_COUNTER_TREND_BLOCK` | True | Veto entries against the bias |
| `EMERGENCY_MAX_RETRIES` | 3 | **New v0.4.0** — then hold to settlement |

## Rate-limit safety

- Kalshi: market snapshot cached 5s, balance cached 60s, positions cached 5s; automatic retry with exponential backoff on 429/5xx.
- Price feeds: Kraken polled ≤ every 8s, Binance klines cached 30–120s.
- Paper mode makes **zero** authenticated calls (fixed in v0.4.0).

## Before going live

1. Paper-run ≥ 24h on v0.4.0; confirm entries respect price caps (0.62 core / 0.58 scalp / 0.68 trend).
2. Grep the log for `Sell rejected` — v0.4.0 logs order-rejection bodies; there should be none in normal operation.
3. Grep for `MTF BLOCK` — vetoes should align with the trend direction.
4. Verify DOWN fills book at the ordered price (no more `1 - price` flips; disagreements log a WARNING).
5. Go live with `MAX_ORDER_SIZE = 1` and watch the first 5 fills.

## Disclaimer

Trading involves risk of loss. This bot is provided as-is; paper-test thoroughly before connecting real funds.
