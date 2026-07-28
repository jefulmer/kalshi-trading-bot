# kalshi-trading-bot

Automated trading bot for Kalshi 15-minute crypto up/down markets (default: BTC, series `KXBTC15M`). Single-file Python script — no config files, all settings are variables at the top of `kalshi_trading_bot.py`.

**Current version: v0.3.0**

## Strategy: Delta Capture + StochRSI Confirm + MTF filter

The bot enters inside a live 15-minute window (3–8 minutes remaining) only when:

1. Spot price is already on your side of the window strike (delta 0.02%–0.10%),
2. 1-minute StochRSI confirms short-term momentum,
3. The contract ask is cheap enough to be worth the risk (**≤ $0.62** as of v0.3.0 — expensive favorites have negative expectancy),
4. The Multi-Timeframe Momentum (MTF) composite (1d/4h/1h/15m/5m, weighted toward the short timeframes) doesn't oppose the trade,
5. Spread ≤ 4¢ and 1m ATR is below the burst-volatility cap.

Positions are defined-risk binaries: default behavior is hold to settlement. Optional salvage exit fires only on a meaningful delta flip (>0.05%, held >120s).

Extras:

- **Momentum scalp** variant in minutes 1–3 of the window at half size.
- **Trend-aligned relaxation**: with a strong MTF tailwind (score ≥ 0.45) the delta cap widens to 0.25% and entries up to $0.68 are allowed at reduced size.
- **Risk gates**: daily loss limit, drawdown halt, 3 consecutive losses → 60-minute pause, per-window trade cap, post-trade cooldown.
- Legacy strategies (`rsi_extreme`, `multi_tf_confluence`, `mean_reversion`, `momentum_breakout`, `divergence_play`) remain selectable via the `STRATEGY` variable.

## Requirements

- Python 3.10+
- `pip install requests cryptography`

## Setup

1. Clone/download this repo.
2. **Paper mode:** run as-is — no keys needed.
3. **Live mode:** create an `api_keys/` subfolder with:
   - `apikey.json` — your Kalshi API key ID (JSON with a `code` field, or raw text)
   - `privatekey.json` — your RSA private key (PEM, JSON with a `code` field, or raw text)

   For the Kalshi demo environment, uncomment the demo `KALSHI_API_BASE` line and/or use `apikey_demo.json` / `privatekey_demo.json`.

## Run

```bash
python3 kalshi_trading_bot.py            # auto: live if keys found, else paper
python3 kalshi_trading_bot.py --paper    # force paper mode
python3 kalshi_trading_bot.py --pretty   # live terminal dashboard
```

Typical VPS deployment (Debian):

```bash
nohup python3 kalshi_trading_bot.py > bot.out 2>&1 &
tail -f logs/kalshi_bot_*.log
```

## Key settings (top of script)

| Setting | Default | Notes |
|---|---|---|
| `DC_MAX_ENTRY_PRICE` | 0.62 | Do not raise without win-rate evidence — see handoff |
| `DC_ENTRY_WINDOW_MIN` | (3.0, 8.0) | Minutes-left entry window |
| `MTF_ENABLED` | True | False = exact v0.1.2 behavior |
| `MTF_COUNTER_TREND_BLOCK` | True | Veto entries against the MTF bias |
| `MTF_STRONG_SCORE` | 0.45 | Threshold for trend-relaxed entries |
| `MAX_ORDER_SIZE` | 1 | Hard safety cap on contracts per trade |
| `MAX_DAILY_LOSS` | 10.0 | $ daily halt |
| `FORCE_PAPER_MODE` | False | True = always paper-trade |

## Output

All runtime files land in `logs/`:

- `kalshi_bot_<ts>.log` — full event log (entries, exits, MTF blocks, halts)
- `trades_<ts>.csv` — one row per closed trade with entry/exit/reason/P&L
- `perf_<ts>.csv` — running performance snapshot per trade

## Changelog highlights

- **v0.3.0** — Entry-price cap 0.70→0.62 (expensive entries had negative expectancy); MTF weights rebalanced toward 15m/5m (sticky 1d pinned bias all session); salvage-exit noise trigger fixed; MTF-block logging now accurate.
- **v0.2.0** — Multi-Timeframe Momentum engine (counter-trend gate + trend-aligned relaxation).
- **v0.1.2** — DC positions ride to settlement; salvage hair-trigger fix; balance-parsing fix.
- **v0.1.1** — Paper-mode exit accounting fix; window-roll settlement fix.

## Disclaimer

Trading involves risk of loss. This bot is provided as-is; paper-test thoroughly before connecting real funds.
