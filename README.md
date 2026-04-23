# StockLens

A multi-page Streamlit app for equity research, comparison, and portfolio construction. Built for self-directed investors and MBA-level finance students who want transparent, rules-based output rather than black-box scores.

Fundamentals come direct from **SEC EDGAR** (authoritative XBRL from 10-K/10-Q filings) for US issuers. Prices, macro tickers, and anything EDGAR doesn't cover (ADRs, foreign issuers) use [`yfinance`](https://github.com/ranaroussi/yfinance). No paid API keys required — just a User-Agent contact email (see [EDGAR configuration](#sec-edgar-configuration)).

## What's inside

**Market Pulse (home)** — the morning dashboard. Macro regime strip (VIX, 10Y yield, S&P 500 level), 11-tile SPDR sector heatmap colored by 1-day % change, watchlist snippet with live price vs. target status, top gainers and losers.

**Stock Analysis** — the research hub. For any ticker:
- Buy / Hold / Avoid verdict with a **transparent rubric** (valuation, quality, momentum, macro) calibrated to one of four investor profiles (Balanced, Value, Growth, Income)
- Expandable "How was this calculated?" panel showing every component score and its inputs
- Tabs for Overview, Fundamentals (with optional sector-percentile context), Technicals (RSI, MACD, Bollinger Bands, moving averages), Risk (Sharpe, Sortino, MaxDD, VaR, rolling vol, return distribution), and Price & Events (earnings / dividend / outlier-day overlays)

**Stock Screener** — scan the S&P 500 against your filters. Composite score is **investor-profile-aware**: the Value profile reweights toward cheap multiples, Growth leans on revenue growth, etc. Add top-N matches to the watchlist in one click.

**Compare Stocks** — pick 2–5 tickers. SPY benchmark overlay on the normalized price chart, best-in-cohort highlighting on the fundamentals table, prescription-engine verdicts up top, correlation matrix with a diversification read.

**Portfolio Risk** — enter holdings and weights (or load your watchlist). See portfolio return / vol / Sharpe / drawdown / VaR, alpha and beta vs. SPY, per-holding risk contributions, sector allocation breakdown with concentration alerts, and suggested alternative weight schemes (equal-weight, inverse-volatility).

**Watchlist** — persistent tracking (JSON file at `.watchlist.json`). Live price vs. 1d/5d moves, RSI bucket, 52-week range position, days tracked, next earnings, and alert banners when targets are hit, RSI flips extreme, or earnings land this week.

## Quickstart

```bash
# 1. Clone and enter the directory
git clone <your-repo-url>
cd Stocks

# 2. (Recommended) create a virtual environment
python -m venv .venv
source .venv/bin/activate     # macOS / Linux
# .venv\Scripts\activate      # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
streamlit run streamlit_app.py
```

Streamlit opens the app at http://localhost:8501.

## SEC EDGAR configuration (optional)

The app runs out of the box with no setup — it identifies itself to SEC
using the repo URL as its User-Agent. SEC accepts that as a valid contact
channel (they can reach the maintainer via GitHub issues), so requests go
through under normal loads.

If you want to be a good citizen or plan to hit EDGAR heavily (e.g. running
the screener across many tickers back-to-back), you can register a real
contact email in either of two ways:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# then edit .streamlit/secrets.toml and fill in your email
```

Or set an environment variable: `export EDGAR_USER_AGENT="YourApp/1.0 you@example.com"`.

**What happens if SEC throttles us?** The request fails fast (≤1 s extra
latency), the chain falls back to yfinance for that call, and the page
renders normally. Companyfacts responses are cached locally for 7 days in
`.edgar_cache/` (gitignored) so a given ticker only hits SEC once per week.

## How the verdict engine works

For a given ticker, four sub-scores (each 0–100) are computed from transparent rules:

1. **Valuation** — P/E, P/B, EV/EBITDA, PEG mapped to scores via "good" and "bad" anchor points (e.g. P/E of 15 → 100, P/E of 40 → 0). Linear between.
2. **Quality** — ROE, profit margin, operating margin, debt/equity, current ratio, free cash flow sign.
3. **Momentum** — derived from the technicals engine (trend direction × strength from MACD / RSI / moving-average crosses).
4. **Macro** — VIX level and 10Y yield mapped to a regime score.

The **composite** is a weighted sum; weights depend on the chosen investor profile:

| Profile  | Valuation | Quality | Momentum | Macro |
|----------|-----------|---------|----------|-------|
| Balanced | 30%       | 30%     | 25%      | 15%   |
| Value    | 45%       | 30%     | 10%      | 15%   |
| Growth   | 15%       | 30%     | 40%      | 15%   |
| Income   | 25%       | 40%     | 10%      | 25%   |

The composite maps to a verdict band (Buy / Hold / Avoid) plus a confidence level. The full breakdown is visible on the Stock Analysis page behind the "How was this calculated?" expander — there are no hidden inputs.

## Project structure

```
Stocks/
├── streamlit_app.py          # Market Pulse home page
├── pages/
│   ├── 1_Stock_Screener.py
│   ├── 2_Stock_Analysis.py
│   ├── 3_Compare_Stocks.py
│   ├── 4_Portfolio_Risk.py
│   ├── 5_Watchlist.py
│   └── archive/              # Legacy pages, preserved
├── utils/
│   ├── data.py               # Data façade; dispatches to providers (cached)
│   ├── providers/            # SEC EDGAR (primary) + yfinance (fallback)
│   │   ├── edgar_client.py   # HTTP client — rate limit, retries, disk cache
│   │   ├── edgar_provider.py # Statements / dividends / earnings from XBRL
│   │   ├── xbrl_concepts.py  # Concept aliases + fact-series resolver
│   │   └── ticker_cik.py     # Ticker → CIK lookup
│   ├── financials.py         # Statement-derived analytics (DuPont, ROIC, etc.)
│   ├── metrics.py            # return / risk / technical calculations
│   ├── prescription.py       # verdict engine + investor profiles
│   └── watchlist.py          # JSON-backed persistence
├── requirements.txt
└── README.md
```

## Data sources

| Capability                             | Primary        | Fallback | Notes |
|----------------------------------------|----------------|----------|-------|
| Financial statements (IS / BS / CF)    | **EDGAR** XBRL | yfinance | authoritative 10-K / 10-Q |
| Historical earnings dates              | **EDGAR**      | yfinance | yfinance fills forward dates |
| Dividends per share                    | **EDGAR**      | yfinance |       |
| Bulk fundamentals (screener)           | yfinance       | —        | EDGAR `/frames/` rewrite planned |
| Per-ticker `.info` (sector, multiples) | yfinance       | —        | price-derived fields stay here |
| Price history / macro / heatmap        | yfinance       | —        | not in EDGAR |

All fetches go through `utils/data.py` with TTL caches so repeat usage is fast:

| Data                              | Cache TTL |
|-----------------------------------|-----------|
| Macro snapshot (VIX, 10Y, SPY)    | 1 hour    |
| Bulk daily changes (heatmap etc.) | 30 minutes|
| Dividends                         | 6 hours   |
| Price history                     | 6 hours   |
| Earnings dates                    | 12 hours  |
| Single-ticker `.info`             | 6 hours   |
| S&P 500 bulk fundamentals         | 12 hours  |
| Financial statements              | 24 hours  |
| EDGAR companyfacts (disk)         | 7 days    |
| EDGAR submissions (disk)          | 6 hours   |

The Screener's first run fetches fundamentals for all 500 names and takes 3–8 minutes today. A planned rewrite onto EDGAR's `/frames/` endpoint will drop this to well under a minute.

## Data caveats

- EDGAR covers US issuers only. ADRs and foreign private issuers fall back to yfinance automatically.
- XBRL concept tagging varies between filers. The concept-alias resolver in `utils/providers/xbrl_concepts.py` handles the common variants; unusual small-caps may still surface gaps.
- Yahoo fundamentals can differ from broker dashboards (vendor differences, fiscal-period cutoffs).
- Don't use this for real trading decisions without cross-checking against a primary source.

## Disclaimer

This app is for research and education. It is not investment advice. The verdict engine is a transparent heuristic, not a forecast. Past performance is not predictive of future returns.

## License

MIT (or whatever you prefer — update this line before publishing).
