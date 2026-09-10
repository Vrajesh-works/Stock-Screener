# Stock Screener

Two standalone screeners. Each is a single Python file that pulls market data,
scores a universe, and writes a self-contained HTML dashboard plus a JSON export.

```bash
pip install -r requirements.txt
```

## `screener.py` — sector risk screener

Scores a fixed 5-sector universe (Energy, Memory, Production + Operation,
Decision + Chaos, Automation) on valuation, financial health, and momentum,
weighted 35/35/30. Metrics are compared against sector medians.

```bash
python screener.py
```

Writes `dashboard.html` and `stock_data.json`.

## `anthropic_screener.py` — Anthropic exposure screener

Ranks public companies by how much of their value is tied to Anthropic ahead of
its expected IPO. Built because the headline dollar figures in financial media
("Amazon's stake is worth $190B!") say nothing about whether a stake actually
moves a stock. What matters is **exposure divided by market cap**.

```bash
python anthropic_screener.py
```

Writes `anthropic_dashboard.html` and `anthropic_exposure.json`.

### Two kinds of exposure, deliberately kept separate

| Type | Meaning | Scales with Anthropic's valuation? |
|---|---|---|
| `equity` | A stake on the balance sheet | Yes, linearly from the Series H mark |
| `revenue` | Contracted or attributable sales | No |

Revenue rows carry a `duration_years`. Leverage is computed off the **annualized**
figure, because a 20-year lease total and a one-year revenue estimate are not
comparable — without this, TeraWulf's $19B/20yr lease scored 234% of market cap
and ranked first.

The two units are still not equivalent even after annualizing (a balance-sheet
asset vs. an income flow). Read the exposure basis on each card before comparing
across types.

### Scoring

Six criteria, weighted:

| Criterion | Weight | Source |
|---|---|---|
| Leverage | 25% | **Computed** — annual exposure / market cap |
| Valuation | 20% | **Computed** — forward P/E (negative P/E scores 15, not 100) |
| Directness | 20% | Analyst judgment |
| Durability | 15% | Analyst judgment |
| Re-rating trigger | 10% | Analyst judgment |
| Data quality | 10% | Analyst judgment |

The four judgment inputs are hand-set in `EXPOSURE` and encode a specific view
from the 2026-09-10 research pass. They are labelled `JUDGMENT` in the dashboard.
Edit them if you disagree — the ranking will follow.

### Valuation scenarios

The dashboard has a toggle for Anthropic at the Series H mark ($965B), $1.2T,
$1.5T and $2T. Equity leverage recomputes client-side. The ranking changes
materially between scenarios, which is the point: at $965B the mega-caps lead on
absolute dollars, and at $2T the high-leverage small caps take over.

### Data provenance

Every row carries a `confidence` flag:

- **`filing`** — from a 10-Q or 8-K (Amazon, Alphabet, Zoom, Salesforce, TeraWulf, Snowflake)
- **`estimate`** — sell-side (Broadcom via Mizuho, SK Telecom, CoreWeave, Nvidia, Microsoft)
- **`undisclosed`** — a real relationship with no public number (Micron, Morgan Stanley)

Market caps and multiples come live from yfinance, with researched fallbacks so
the dashboard renders offline. Any row using a fallback market cap is flagged in
the card footer.

### Caveats

Stake values are **point-in-time marks that go stale every quarter** — re-verify
against the latest filings before relying on any row. Anthropic's actual cap
table is not public; Amazon's ownership is estimated anywhere from 7.8% to 21%
depending on the derivation, so the leverage math for several rows will shift
when the S-1 is published.

**Not investment advice.** This is research tooling. It computes exposure ratios;
it does not recommend positions and deliberately says nothing about position
sizing.
