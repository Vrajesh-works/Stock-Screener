# Stock-Screener

**Live demo:** https://vrajesh-works.github.io/Stock-Screener/

A Python stock screener that scores a curated watchlist on valuation, financial health, and price momentum, then renders the results as an interactive HTML dashboard with Strong Buy / Buy / Hold / Cautious / Sell badges.

## How it works

1. Pulls ~400 days of price history and fundamentals for each ticker via `yfinance`
2. Scores every stock on three weighted factors (valuation 35%, financial health 35%, momentum 30%), benchmarked against sector medians
3. Generates `index.html` with ranked results and risk badges
4. Exports the raw scores to `stock_data.json`

## Usage

```bash
pip install -r requirements.txt
python screener.py
```

Then open `index.html` in a browser to explore the results.

Data is refreshed by re-running the screener; the dashboard is dated with the run time.

## Watchlist

Tickers are grouped into thematic sectors (Energy, Memory, Production + Operation, Decision + Chaos, Automation) covering names like NVDA, AMD, TSM, MSFT, GOOGL, TSLA, and META. Edit the `SECTORS` dict in `screener.py` to screen your own tickers.

## Terminal features

The dashboard is a Bloomberg-style terminal with:

- **Ticker tape + market monitor** - live-scrolling watchlist, S&P 500 / Nasdaq / Dow / Russell 2000 / VIX
- **Sortable blotter** - click any header to sort; sparklines in every row
- **Screener filters** - filter by score, P/E, market cap, dividend yield, sector, rating
- **Compare mode** - check 2-4 stocks for a side-by-side stat sheet and overlaid normalized charts
- **Chart timeframes** - 1M / 3M / 6M / 1Y / 5Y views on every security detail chart
- **Candlesticks** - toggle between line and OHLC candle rendering
- **Analyst consensus** - price target range, mean target, recommendation, analyst count
- **Add any ticker** - type any US symbol for live price data via Stooq (price data only, no fundamentals)
- **CSV export** - download the filtered blotter
- **Security detail** - click any row for stats grid, quant model breakdown, catalysts/risks, quarterly earnings
- **Keyboard** - `1/2/3` switch views, `/` focuses search, `Esc` closes panels

## Refreshing the data

```bash
pip install yfinance
python screener.py
```

Then upload the regenerated `index.html` to the repo (GitHub web UI: Add file > Upload files).
`SECTORS` in `screener.py` defines the coverage universe; add tickers there for full
quant scoring. All data via yfinance (free, no API key).

## Disclaimer

For educational purposes only. Not financial advice.
