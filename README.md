# kalshi-trading-bot

Automated trading bot for **Kalshi 15-minute crypto up/down markets** (default: BTC, series `KXBTC15M`; also ETH, SOL, XRP, DOGE, BNB — HYPE has no Binance spot feed).
Single-file Python 3 script — no config file; all settings are variables at the top of `kalshi_trading_bot.py`, and **every launch-relevant variable can be overridden from the command line**.

**Current version: v0.5.0** (2026-07-29)

## Strategy — "Delta Capture + StochRSI Confirm" (+ MTF engine)

1. **Strike capture** — the window strike is read from the Kalshi market object (fallback: Kraken 1m candle close at window open).
2. **Core entry (3–8 min left)** — enter only when spot is already on your side of the strike by 0.02%–0.10%, the contract ask is ≤ $0.62, 1-minute StochRSI confirms momentum, and the **MTF conviction gate** (|multi-timeframe score| ≥ 0.10) shows the market is trending, not chopping.
3. **Momentum scalp (12–14 min left)** — half-size early entries when price is already moving (ask ≤ $0.58).
4. **MTF trend relaxation** — with a strong multi-timeframe tailwind (score ≥ 0.40) the delta cap widens to 0.25% and entries up to $0.68 are allowed at half size.
5. **Counter-trend gate** — entries fighting the higher-timeframe bias are vetoed.
6. **Per-asset ATR caps (v0.5.0)** — the 1m ATR filter is resolved per asset (`ASSET_OVERRIDES`): high-vol assets (ETH/SOL/XRP/DOGE) get 0.0010, BNB 0.0005, global default 0.0006. A single BTC-calibrated cap blocked 84–98% of entry checks on the high-vol assets in the 24h backtest.
7. **Exits** — binary defined-risk: positions ride to settlement by default. Optional salvage exit on a confirmed delta flip; profit target at $0.92. Emergency exits are capped and fall back to settlement resolution.

## Quick start

```bash
pip install requests cryptography
python3 kalshi_trading_bot.py            # auto paper mode if no keys
python3 kalshi_trading_bot.py --pretty   # live terminal dashboard
python3 kalshi_trading_bot.py --paper    # force paper even with keys present
python3 kalshi_trading_bot.py --help     # full CLI
```

### API keys (for LIVE trading)

Create `api_keys/` next to the script:

```
api_keys/
├── apikey.json        # {"code": "your-kalshi-api-key-id"}  (or raw text)
└── privatekey.json    # {"code": "-----BEGIN PRIVATE KEY-----\n..."}  (or raw PEM text)
```

- Keys found → **LIVE ORDER MODE** (real money). No keys → paper/test mode.
- Set `FORCE_PAPER_MODE = True` in the script (or pass `--force-paper`) to always paper-trade.
- Demo environment: `--api-base https://demo-api.kalshi.co` and use `apikey_demo.json` / `privatekey_demo.json`.

## CLI flags (v0.5.0)

Flags take precedence over the script defaults; every applied flag is logged as `CLI override:` at startup and reflected in the run header.

| Flag | Sets | Example |
|---|---|---|
| `--strategy` | `STRATEGY` | `--strategy delta_capture_scalp` |
| `--assets` | `ASSETS` (rebuilds all asset state) | `--assets BTC,ETH` |
| `--paper` / `--force-paper` | paper mode | `--paper` |
| `--pretty` | `PRETTY_DISPLAY` | `--pretty` |
| `--api-base` | `KALSHI_API_BASE` | `--api-base https://demo-api.kalshi.co` |
| `--dc-window LO HI` | `DC_ENTRY_WINDOW_MIN` | `--dc-window 3 8` |
| `--dc-min-delta` / `--dc-max-delta` | `DC_MIN_DELTA_PCT` / `DC_MAX_DELTA_PCT` | `--dc-min-delta 0.0002` |
| `--dc-max-entry-price` | `DC_MAX_ENTRY_PRICE` | `--dc-max-entry-price 0.62` |
| `--dc-atr-max-pct` | `DC_ATR_MAX_PCT` (global; per-asset overrides still win) | `--dc-atr-max-pct 0.0006` |
| `--dc-scalp-max-price` | `DC_SCALP_MAX_PRICE` | `--dc-scalp-max-price 0.58` |
| `--dc-scalp` / `--no-dc-scalp` | `DC_SCALP_ENABLED` | `--no-dc-scalp` |
| `--mtf-min-trade-score` | `MTF_MIN_TRADE_SCORE` | `--mtf-min-trade-score 0.10` |
| `--mtf-strong-score` | `MTF_STRONG_SCORE` | `--mtf-strong-score 0.40` |
| `--mtf-min-score` | `MTF_MIN_SCORE` | `--mtf-min-score 0.15` |
| `--counter-trend-block` / `--no-counter-trend-block` | `MTF_COUNTER_TREND_BLOCK` | `--no-counter-trend-block` |
| `--order-size` / `--max-order-size` | `ORDER_SIZE` / `MAX_ORDER_SIZE` | `--order-size 1 --max-order-size 2` |
| `--bankroll` | `BANKROLL` | `--bankroll 500` |
| `--max-daily-loss` | `MAX_DAILY_LOSS` | `--max-daily-loss 10` |
| `--max-drawdown-pct` | `MAX_DRAWDOWN_PERCENT` | `--max-drawdown-pct 15` |
| `--profit-target` | `PROFIT_TARGET` | `--profit-target 0.92` |
| `--salvage` / `--no-salvage` | `DC_SALVAGE_EXIT` | `--no-salvage` |
| `--asset-overrides` | `ASSET_OVERRIDES` (JSON) | `--asset-overrides '{"ETH":{"MTF_MIN_TRADE_SCORE":0.15}}'` |

Examples:

```bash
python3 kalshi_trading_bot.py --paper --assets BTC,ETH --mtf-min-trade-score 0.10
python3 kalshi_trading_bot.py --paper --assets BTC,SOL,XRP --dc-atr-max-pct 0.0008 --no-dc-scalp
python3 kalshi_trading_bot.py --paper --asset-overrides '{"ETH":{"MTF_MIN_TRADE_SCORE":0.15},"SOL":{"DC_ATR_MAX_PCT":0.0012}}'
```

## Key config (top of script)

| Variable | Default | Notes |
|---|---|---|
| `STRATEGY` | `delta_capture` | Legacy strategies still selectable |
| `DC_ENTRY_WINDOW_MIN` | (3.0, 8.0) | Core entry window (minutes left) |
| `DC_MAX_ENTRY_PRICE` | 0.62 | Never pay more — expectancy gate |
| `DC_ATR_MAX_PCT` | **0.0006** | v0.5.0: was 0.00045 (BTC-tuned, strangled other assets) |
| `ASSET_OVERRIDES` | ATR caps for ETH/SOL/XRP/DOGE/BNB | **New v0.5.0** — per-asset tunables with global fallback |
| `MTF_MIN_TRADE_SCORE` | **0.10** | v0.5.0: was 0.20 — vetoed ~every qualifier (zero-trade 18h session) |
| `MTF_STRONG_SCORE` | 0.40 | Trend-relaxation threshold |
| `MTF_COUNTER_TREND_BLOCK` | True | Veto entries against the bias |
| `EMERGENCY_MAX_RETRIES` | 3 | Then hold to settlement |

## Backtest summary (v0.5.0 tuning basis)

`backtest_kalshi.py` replays the bot's actual engine over the last 24h of Binance 1m data for all assets (96 windows/asset). Full details in `BACKTEST_REPORT.md`; headline:

- **v0.4.0 config: 0 trades on all 6 assets** — reproduces the zero-trade 18h live paper session. ATR cap blocks 84–98% of checks on ETH/SOL/XRP/DOGE; the 0.20 conviction gate blocks 34–46% on BTC/BNB.
- **Raw signal (all gates off): 315 trades, 73% WR overall** — BTC 80%, SOL 74%, BNB 74%, DOGE 73%, ETH 71%, XRP 63%. The edge exists on every asset; the constraints were suppressing it differently per asset.
- **v0.5.0 recommended config:** 19 trades, 63% WR, +$1.35 after modeled fees in the same window (directional only — 96 windows/asset is a small sample; the entry-price model overstates real Kalshi asks, especially on low-vol assets).

## Output

Runtime files land in `logs/`:

| File | Contents |
|---|---|
| `kalshi_bot_<ts>.log` | Full event log (windows, entries, exits, MTF vetoes, order rejections) |
| `trades_<ts>.csv` | Per-trade record incl. **FeeEst** and **PnLAfterFees** columns |
| `perf_<ts>.csv` | Running totals, win rate, consecutive losses |

Log vocabulary (v0.5.0): `MTF GATE` = conviction-gate veto (score too low, chop); `MTF BLOCK` = counter-trend veto of an otherwise-qualifying signal. v0.4.0 conflated these via a stale flag.

## Risk controls (defaults)

- `MAX_ORDER_SIZE = 1` contract hard cap; per-trade risk ≤ 2% of bankroll
- `MAX_DAILY_LOSS = $10` halt; `MAX_DRAWDOWN_PERCENT = 15%` halt
- 3 consecutive losses → 60-minute pause
- 1 trade per 15-min window; 90s post-trade cooldown; max 2 entry attempts per window

## Rate-limit safety

- Kalshi: market snapshot cached 5s, balance cached 60s, positions cached 5s; automatic retry with exponential backoff on 429/5xx.
- Price feeds: Kraken polled ≤ every 8s, Binance klines cached 30–120s.
- Paper mode makes **zero** authenticated calls.

## Before going live

1. Paper-run ≥ 24h on v0.5.0 across the assets you intend to trade; confirm trades actually happen now (v0.4.0 traded zero times in 18h).
2. Confirm entries respect price caps (0.62 core / 0.58 scalp / 0.68 trend) and that `MTF GATE`/`MTF BLOCK` lines are correctly attributed.
3. Grep the log for `Sell rejected` — there should be none in normal operation.
4. Verify DOWN fills book at the ordered price (disagreements log a WARNING).
5. Go live with `MAX_ORDER_SIZE = 1` and watch the first 5 fills.

## Disclaimer

Trading involves risk of loss. This bot is provided as-is; paper-test thoroughly before connecting real funds.
