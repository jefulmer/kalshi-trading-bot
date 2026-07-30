# kalshi-trading-bot (v0.7.0)

Automated trading bot for **Kalshi 15-minute crypto up/down markets** (BTC, ETH, SOL, XRP, DOGE, HYPE, BNB, NEAR, ZEC). Single-file Python, paper-trading by default.

**Default strategy — Delta Capture + StochRSI Confirm:** enter inside a 15-min window (3–8 min remaining) only when price is already on your side of the strike, the contract is underpriced relative to live conditions, and 1-minute StochRSI confirms short-term momentum. A multi-timeframe (5m→1d) momentum score gates chop and relaxes caps for trend-aligned entries.

## Setup

- Python **3.8+**, one dependency: `pip install requests`
- **Live trading:** put your Kalshi credentials in `./api_keys/` (`apikey.json` + `privatekey.json`; JSON with a `code` field or raw text). No keys found → automatic **paper/test mode**.
- Optional: `pip install cryptography` for RSA request signing (required for live orders).

## Quickstart

```bash
# Paper trade, all 9 assets (no keys needed)
python3 kalshi_trading_bot.py --paper --assets BTC,ETH,SOL,XRP,DOGE,HYPE,BNB,NEAR,ZEC

# Live (keys in api_keys/)
python3 kalshi_trading_bot.py --assets BTC,ETH

# Interactive config editor (writes kalshi_bot_config.json, then exits)
python3 kalshi_trading_bot.py --menu

# Full CLI
python3 kalshi_trading_bot.py --help
```

## Assets & price feeds

| Asset | Kalshi series | Spot feed | MTF klines |
|---|---|---|---|
| BTC | KXBTC15M | Kraken → Binance | Binance → Kraken |
| ETH / SOL / XRP / DOGE / BNB / NEAR / ZEC | KX{asset}15M | Kraken → Binance | Binance → Kraken |
| HYPE | KXHYPE15M | Kraken → **Hyperliquid** allMids → Binance | **Hyperliquid** candleSnapshot → Binance → Kraken |

Binance has no HYPEUSDT spot market, so HYPE routes to the Hyperliquid info API (`ASSET_FEED_MAP`). Every asset also has a generic Kraken OHLC fallback when Binance klines fail.

## Configuration

Three layers, in order of precedence: **script defaults < config file < CLI flags**.

- **Script defaults** — all tunables are documented variables at the top of `kalshi_trading_bot.py`.
- **Config file** — `kalshi_bot_config.json` (searched next to the script, then CWD; `--config-file PATH` overrides). Flat JSON keyed by config names; unknown keys warn and are ignored. Edit by hand or via `--menu` (grouped sections, per-param defaults, reset-to-default, saves diffs only).
- **CLI flags** — `--help` lists everything; applied values are logged at startup.

Per-asset tuning lives in `ASSET_OVERRIDES` (menu section 9, or `--asset-overrides '{"ETH":{...}}'`). Resolution is override-with-global-fallback.

## Market health (v0.7.0)

During Kalshi weekly maintenance the orderbook returns **zero prices**, and without guards the bot booked phantom entries at 0.00 that "settled" as fake wins (observed 14 fake trades, 2026-07-30 05:22–06:30 UTC). The market-health layer (all on by default via `MARKET_HEALTH_ENABLED`):

- **Entry veto** when the market is not in a trading status, either side has no positive ask, the spot feed is stale (`FEED_STALE_SECONDS`, 45s), or a scheduled blackout is active — throttled logging plus one `MARKET HEALTHY — resuming` line on recovery. Kalshi market objects report `status: "active"` while trading (the `GET /markets?status=open` filter maps to `active` objects); the bot accepts `active`/`open` via `KALSHI_TRADING_STATUSES` and treats `inactive`/`closed`/`determined`/`finalized`/etc. as not trading. Logs distinguish `MARKET NOT TRADING` (bad status) from `BOOK EMPTY` (trading status, no usable quotes). Zero prices are never traded.
- **Zero-price guards** in the strategy, entry resolution, exit evaluation, and paper close paths — a position is never force-closed at floor prices just because the book is empty; settlement resolution is unaffected.
- **`MAINTENANCE_WINDOWS`** — optional UTC entry blackouts `[[weekday, "HH:MM", "HH:MM"], ...]` (weekday 0=Mon). Ships `[["3", "05:00", "08:00"]]` (Thursday 05:00–08:00 UTC, observed Kalshi maintenance incl. overruns). Dynamic zero-price detection is the real guard; the blackout is belt-and-braces — adjust to your exchange notice.

Set `MARKET_HEALTH_ENABLED=false` for exact pre-0.7.0 behavior.

## Multi-entry

`MAX_ENTRIES_PER_WINDOW` allows up to N entries per 15-min window per asset (default 1 = single-shot). Re-entries honor `REENTRY_COOLDOWN_SECONDS`, size decay (`REENTRY_SIZE_DECAY ** (N-1)`), an optional same-side block after a losing exit (`REENTRY_SAME_SIDE_ALLOWED`), and after-loss-only mode (`REENTRY_AFTER_LOSS_ONLY`). All per-asset overridable.

## Risk gates

Daily loss halt (`MAX_DAILY_LOSS`), drawdown halt (`MAX_DRAWDOWN_PERCENT`), consecutive-loss pause (`MAX_CONSECUTIVE_LOSSES` → `PAUSE_AFTER_LOSS_STREAK_MIN`), per-window session loss cap, post-trade cooldown, 2%-of-bankroll per-trade risk cap, hard size cap (`MAX_ORDER_SIZE`), and no entries in the final `NO_ENTRY_FINAL_SECONDS` of a window.

## Files

| File | Purpose |
|---|---|
| `kalshi_trading_bot.py` | The bot (single file) |
| `kalshi_bot_config.json` | Config file — overrides script defaults (CLI overrides both) |
| `api_keys/` | Your Kalshi credentials (you create this — see below) |
| `logs/` | Runtime logs + trade/perf CSVs (created on run) |

## Notes

- HYPE parameters are model-derived guesses — **paper-only until ≥20 real fills**.
- ZEC remains the weakest modeled asset — paper-only.
- Paper mode never calls authenticated endpoints; it books entries/exits at live orderbook prices.

## Safety rails (unchanged)

Paper mode auto without keys · `FORCE_PAPER_MODE` · daily loss halt ($10) · drawdown halt (15%) · 3 consecutive losses → 60m pause · hard size cap · per-trade risk ≤2% of bankroll · fee-adjusted P&L logging · rate-limit-safe polling with 429/5xx backoff.

**ZEC and NEAR are backtest-calibrated but have no live fill data — paper-test them before going live.** DOGE is effectively opt-in now (very high min-delta bar).

## Disclaimer

Experimental software. Prediction-market binaries can go to zero. Start in paper mode, size small, and never trade money you can't afford to lose.
