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

## Disclaimer

For educational purposes only. Not financial advice.
