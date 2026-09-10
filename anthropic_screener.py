"""Anthropic exposure screener.

Ranks publicly traded companies by how much of their value is tied to
Anthropic, either through an equity stake or through contracted revenue.

Stake values are hardcoded because they come from SEC filings and analyst
notes, not from any market data feed. Market caps and multiples are pulled
live from yfinance, with researched fallbacks so the dashboard still renders
offline. Every hardcoded figure carries its source and as-of date.

Research date: 2026-09-10. Re-verify marks after each earnings season.
"""

import yfinance as yf
import json
import math
from datetime import datetime
from pathlib import Path

# Anthropic Series H post-money, May 2026. Equity stakes below are marked
# against this valuation, so scaling to a scenario is linear from here.
ANTHROPIC_MARK_BASE = 965e9

SCENARIOS = [
    ("Series H (965B)", 965e9),
    ("1.2T", 1.2e12),
    ("1.5T", 1.5e12),
    ("2T", 2.0e12),
]

TIER_CORE = "Core"
TIER_BENCH = "Bench"
TIER_CUT = "Cut"

# exposure_type:  "equity" scales with Anthropic's valuation.
#                 "revenue" does not - it is contracted or attributable sales.
# duration_years: only for revenue rows. exposure_usd is the TOTAL over this
#                 many years, so leverage is computed off total/duration. A
#                 20-year lease and a one-year revenue estimate are otherwise
#                 not comparable, which is what made TeraWulf score 234 pct.
# confidence:     "filing" = 10-Q/8-K, "estimate" = sell-side, "undisclosed".
# The four judgment fields (directness/durability/rerating/data_quality) are
# analyst inputs from the 2026-09-10 research pass, not computed values. They
# are labelled as such in the dashboard.
EXPOSURE = {
    "AVGO": {
        "label": "Broadcom",
        "tier": TIER_CORE,
        "exposure_type": "revenue",
        "exposure_usd": 42e9,
        "exposure_basis": "Est. FY2027 Anthropic-attributable revenue",
        "duration_years": 1,
        "as_of": "2026-09",
        "source": "Mizuho est.; Broadcom Q3 FY26 call",
        "confidence": "estimate",
        "cost_basis": None,
        "ownership": None,
        "mkt_cap_fallback": 1.753e12,
        "fwd_pe_fallback": 19.03,
        "target_fallback": 533.41,
        "directness": 95,
        "durability": 95,
        "rerating": 70,
        "data_quality": 70,
        "note": "CEO named Anthropic largest XPU customer 2027-28. 1GW Ironwood 2026, "
                "5GW TPU v8i 2027, 10GW 2028. AI semi revenue guided 58B/115B/230B FY26-28.",
    },
    "AMZN": {
        "label": "Amazon",
        "tier": TIER_CORE,
        "exposure_type": "equity",
        "exposure_usd": 190.4e9,
        "exposure_basis": "Convertible notes 97.9B plus nonvoting preferred 92.5B",
        "duration_years": None,
        "as_of": "2026-06-30",
        "source": "Q2 2026 10-Q",
        "confidence": "filing",
        "cost_basis": 13e9,
        "ownership": "15-21 pct (disputed)",
        "mkt_cap_fallback": 2.77e12,
        "fwd_pe_fallback": 26.0,
        "target_fallback": None,
        "directness": 90,
        "durability": 85,
        "rerating": 95,
        "data_quality": 85,
        "note": "Q2 pre-tax Anthropic gain of 53.4B was ~66 pct of pre-tax income, above "
                "operating profit. Also >100B AWS commitment, Project Rainier, 1M+ Trainium2.",
    },
    "GOOGL": {
        "label": "Alphabet",
        "tier": TIER_CORE,
        "exposure_type": "equity",
        "exposure_usd": 124.3e9,
        "exposure_basis": "Private company holdings, primarily Anthropic",
        "duration_years": None,
        "as_of": "2026-06-30",
        "source": "Q2 2026 disclosure",
        "confidence": "filing",
        "cost_basis": 3e9,
        "ownership": "~14 pct, capped at 15",
        "mkt_cap_fallback": 4.04e12,
        "fwd_pe_fallback": 25.39,
        "target_fallback": 428.07,
        "directness": 95,
        "durability": 90,
        "rerating": 85,
        "data_quality": 90,
        "note": "Triple transmission: equity, designs the TPUs, and Google Cloud hosts. "
                "Stake contractually capped so it cannot grow. No voting rights or board seats.",
    },
    "ZM": {
        "label": "Zoom",
        "tier": TIER_CORE,
        "exposure_type": "equity",
        "exposure_usd": 3.13e9,
        "exposure_basis": "Series C investment, marked to Series H",
        "duration_years": None,
        "as_of": "2026-07-31",
        "source": "FQ2 2026 10-Q",
        "confidence": "filing",
        "cost_basis": 51e6,
        "ownership": None,
        "mkt_cap_fallback": 28.14e9,
        "fwd_pe_fallback": 15.79,
        "target_fallback": 118.24,
        "directness": 70,
        "durability": 40,
        "rerating": 75,
        "data_quality": 95,
        "note": "Net cash 7.19B (24.64/sh) plus stake 3.13B is ~37 pct of market cap. "
                "WARNING: trailing P/E of ~9x is inflated by the Anthropic markup. Use forward.",
    },
    "SKM": {
        "label": "SK Telecom",
        "tier": TIER_CORE,
        "exposure_type": "equity",
        "exposure_usd": 1.9e9,
        "exposure_basis": "Midpoint of 1.2-2.6B range; BofA marks at KRW 1.7tn",
        "duration_years": None,
        "as_of": "2026",
        "source": "Sell-side estimates (0.27-0.40 pct ownership)",
        "confidence": "estimate",
        "cost_basis": 100e6,
        "ownership": "0.27-0.40 pct (est.)",
        "mkt_cap_fallback": 9.09e9,
        "fwd_pe_fallback": 19.11,
        "target_fallback": None,
        "directness": 70,
        "durability": 40,
        "rerating": 80,
        "data_quality": 40,
        "note": "Highest leverage in the theme, worst entry price. Already re-rated hard. "
                "New Street and UBS both at Neutral. ~6B net debt. Stake size still an estimate.",
    },
    "CRM": {
        "label": "Salesforce",
        "tier": TIER_BENCH,
        "exposure_type": "equity",
        "exposure_usd": 5.1e9,
        "exposure_basis": "45 pct of strategic investment portfolio",
        "duration_years": None,
        "as_of": "2026-07-31",
        "source": "FQ2 2026 10-Q",
        "confidence": "filing",
        "cost_basis": 50e6,
        "ownership": None,
        "mkt_cap_fallback": 230e9,
        "fwd_pe_fallback": 22.25,
        "target_fallback": None,
        "directness": 75,
        "durability": 60,
        "rerating": 60,
        "data_quality": 95,
        "note": "Benched on leverage: only ~2 pct of market cap. Drove 2.7B of gains in FQ2.",
    },
    "WULF": {
        "label": "TeraWulf",
        "tier": TIER_BENCH,
        "exposure_type": "revenue",
        "exposure_usd": 19e9,
        "exposure_basis": "Total contracted revenue, 20-year Anthropic lease",
        "duration_years": 20,
        "as_of": "2026-07",
        "source": "8-K / company release",
        "confidence": "filing",
        "cost_basis": None,
        "ownership": None,
        "mkt_cap_fallback": 9.14e9,
        "fwd_pe_fallback": None,
        "target_fallback": None,
        "directness": 95,
        "durability": 80,
        "rerating": 70,
        "data_quality": 85,
        "note": "Best contracted-revenue leverage anywhere: 19B backlog against a ~9B market "
                "cap. Benched on risk class - bitcoin miner pivoting to HPC, 52wk 4.69-29.82.",
    },
    "CRWV": {
        "label": "CoreWeave",
        "tier": TIER_CUT,
        "exposure_type": "revenue",
        "exposure_usd": 5.5e9,
        "exposure_basis": "Midpoint of 4-7B est. over 5 years; terms undisclosed",
        "duration_years": 5,
        "as_of": "2026-04",
        "source": "Wells Fargo / Citi / Morgan Stanley est.",
        "confidence": "estimate",
        "cost_basis": None,
        "ownership": None,
        "mkt_cap_fallback": None,
        "fwd_pe_fallback": None,
        "target_fallback": None,
        "directness": 50,
        "durability": 55,
        "rerating": 40,
        "data_quality": 35,
        "note": "Anthropic is ~5 pct of a 104.2B backlog dominated by Microsoft. Three "
                "customers are 72 pct of revenue. 35.6B debt at 9.0 pct, 640M quarterly interest.",
    },
    "MU": {
        "label": "Micron",
        "tier": TIER_CUT,
        "exposure_type": "revenue",
        "exposure_usd": None,
        "exposure_basis": "Multi-year HBM/DRAM/SSD supply plus Series H equity, undisclosed",
        "duration_years": None,
        "as_of": "2026-06-22",
        "source": "Company release",
        "confidence": "undisclosed",
        "cost_basis": None,
        "ownership": None,
        "mkt_cap_fallback": 1.0e12,
        "fwd_pe_fallback": None,
        "target_fallback": None,
        "directness": 60,
        "durability": 70,
        "rerating": 40,
        "data_quality": 25,
        "note": "Real agreement but unquantifiable. ~1T market cap after a ~900 pct one-year run.",
    },
    "NVDA": {
        "label": "Nvidia",
        "tier": TIER_CUT,
        "exposure_type": "equity",
        "exposure_usd": 10e9,
        "exposure_basis": "Up to 10B committed Nov 2025; deployment schedule unclear",
        "duration_years": None,
        "as_of": "2025-11-18",
        "source": "Company announcement",
        "confidence": "estimate",
        "cost_basis": None,
        "ownership": None,
        "mkt_cap_fallback": None,
        "fwd_pe_fallback": None,
        "target_fallback": None,
        "directness": 60,
        "durability": 85,
        "rerating": 30,
        "data_quality": 60,
        "note": "Both investor and supplier. Circular: invests in Anthropic, which buys its compute.",
    },
    "MSFT": {
        "label": "Microsoft",
        "tier": TIER_CUT,
        "exposure_type": "equity",
        "exposure_usd": 5e9,
        "exposure_basis": "Up to 5B committed Nov 2025",
        "duration_years": None,
        "as_of": "2025-11-18",
        "source": "Company announcement",
        "confidence": "estimate",
        "cost_basis": None,
        "ownership": None,
        "mkt_cap_fallback": None,
        "fwd_pe_fallback": None,
        "target_fallback": None,
        "directness": 50,
        "durability": 80,
        "rerating": 30,
        "data_quality": 60,
        "note": "Anthropic committed 30B of Azure purchases against a 5B investment.",
    },
    "MS": {
        "label": "Morgan Stanley",
        "tier": TIER_CUT,
        "exposure_type": "revenue",
        "exposure_usd": None,
        "exposure_basis": "Left-lead underwriting fees, undisclosed",
        "duration_years": None,
        "as_of": "2026-09",
        "source": "Press reports",
        "confidence": "undisclosed",
        "cost_basis": None,
        "ownership": None,
        "mkt_cap_fallback": None,
        "fwd_pe_fallback": None,
        "target_fallback": None,
        "directness": 60,
        "durability": 20,
        "rerating": 50,
        "data_quality": 50,
        "note": "Left lead on possibly the largest IPO ever, plus the ~15B revolver. A fee event.",
    },
    "SNOW": {
        "label": "Snowflake",
        "tier": TIER_CUT,
        "exposure_type": "revenue",
        "exposure_usd": 0.2e9,
        "exposure_basis": "Multi-year Claude distribution agreement",
        "duration_years": 3,
        "as_of": "2025-12",
        "source": "Company announcement",
        "confidence": "filing",
        "cost_basis": None,
        "ownership": None,
        "mkt_cap_fallback": None,
        "fwd_pe_fallback": None,
        "target_fallback": None,
        "directness": 55,
        "durability": 50,
        "rerating": 30,
        "data_quality": 80,
        "note": "200M deal putting Claude in front of 12,600+ Snowflake customers.",
    },
}

ALL_TICKERS = list(EXPOSURE.keys())

W_LEVERAGE = 0.25
W_VALUATION = 0.20
W_DIRECTNESS = 0.20
W_DURABILITY = 0.15
W_RERATING = 0.10
W_DATA_QUALITY = 0.10

CONFIDENCE_STYLE = {
    "filing": ("SEC filing", "#22c55e"),
    "estimate": ("Sell-side est.", "#fbbf24"),
    "undisclosed": ("Undisclosed", "#ef4444"),
}


def safe(val, default=None):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    return val


def pct(a, b):
    if b is None or b == 0:
        return None
    return ((a - b) / abs(b)) * 100


def score_metric(val, low, high, invert=False):
    if val is None:
        return 50
    clamped = max(low, min(high, val))
    normalized = (clamped - low) / (high - low) if high != low else 0.5
    if invert:
        normalized = 1 - normalized
    return round(normalized * 100)


def exposure_badge(score):
    if score >= 75:
        return ("Top exposure", "#22c55e")
    if score >= 60:
        return ("Strong", "#a3e635")
    if score >= 45:
        return ("Moderate", "#fbbf24")
    if score >= 30:
        return ("Weak", "#f97316")
    return ("Negligible", "#ef4444")


def scaled_exposure(row, anthropic_valuation):
    """Total exposure. Equity scales with Anthropic's valuation; revenue does not."""
    if row["exposure_usd"] is None:
        return None
    if row["exposure_type"] == "equity":
        return row["exposure_usd"] * (anthropic_valuation / ANTHROPIC_MARK_BASE)
    return row["exposure_usd"]


def annual_exposure(row, anthropic_valuation):
    """The figure leverage is computed against.

    Equity is a balance-sheet asset, so the full stake counts. Revenue is a
    flow, so a multi-year total has to be divided down to an annual run-rate -
    otherwise a 20-year lease looks 20x better than a one-year estimate.
    """
    total = scaled_exposure(row, anthropic_valuation)
    if total is None:
        return None
    if row["exposure_type"] == "equity":
        return total
    return total / (row.get("duration_years") or 1)


def leverage_pct(row, mkt_cap, anthropic_valuation):
    exposure = annual_exposure(row, anthropic_valuation)
    if exposure is None or not mkt_cap:
        return None
    return (exposure / mkt_cap) * 100


def score_valuation(fwd_pe):
    """A negative forward P/E means forward losses, not a bargain.

    score_metric would clamp a negative to the low bound and invert it to 100,
    which scored loss-making companies as the cheapest names in the universe.
    """
    if fwd_pe is None:
        return 50
    if fwd_pe <= 0:
        return 15
    return score_metric(fwd_pe, 10, 45, invert=True)


def fetch_market_data():
    print(f"Fetching market data for {len(ALL_TICKERS)} tickers...")
    rows = {}

    for ticker_sym in ALL_TICKERS:
        row = dict(EXPOSURE[ticker_sym])
        row["ticker"] = ticker_sym
        print(f"  {ticker_sym}...", end=" ", flush=True)

        price = None
        mkt_cap = None
        fwd_pe = None
        trailing_pe = None
        target = None
        ret_1y = None

        try:
            tk = yf.Ticker(ticker_sym)
            info = tk.info or {}
            price = safe(info.get("currentPrice")) or safe(info.get("regularMarketPrice"))
            mkt_cap = safe(info.get("marketCap"))
            fwd_pe = safe(info.get("forwardPE"))
            trailing_pe = safe(info.get("trailingPE"))
            target = safe(info.get("targetMeanPrice"))

            # fiftyTwoWeekChange is frequently absent, so compute the one-year
            # return from price history instead of trusting the info dict.
            change_1y = safe(info.get("fiftyTwoWeekChange"))
            if change_1y is not None:
                ret_1y = change_1y * 100
            else:
                hist = tk.history(period="1y")
                if len(hist) > 2:
                    close = hist["Close"]
                    ret_1y = pct(float(close.iloc[-1]), float(close.iloc[0]))

            print("OK" if mkt_cap else "no market cap")
        except Exception as e:
            print(f"ERROR: {e}")

        # Fall back to researched values so the dashboard renders offline.
        row["mkt_cap"] = mkt_cap if mkt_cap else row["mkt_cap_fallback"]
        row["mkt_cap_is_live"] = bool(mkt_cap)
        row["fwd_pe"] = fwd_pe if fwd_pe else row["fwd_pe_fallback"]
        row["fwd_pe_is_live"] = bool(fwd_pe)
        row["target"] = target if target else row["target_fallback"]
        row["price"] = price
        row["trailing_pe"] = trailing_pe
        row["ret_1y"] = ret_1y
        row["is_live"] = bool(mkt_cap)
        row["upside_to_target"] = pct(row["target"], price) if (row["target"] and price) else None

        rows[ticker_sym] = row

    return rows


def calculate_scores(rows, anthropic_valuation=ANTHROPIC_MARK_BASE):
    for row in rows.values():
        lev = leverage_pct(row, row["mkt_cap"], anthropic_valuation)
        row["leverage_pct"] = lev
        row["exposure_scaled"] = scaled_exposure(row, anthropic_valuation)
        row["exposure_annual"] = annual_exposure(row, anthropic_valuation)

        # 25 pct of market cap or more is a full score on leverage.
        row["s_leverage"] = score_metric(lev, 0, 25)
        row["s_valuation"] = score_valuation(row["fwd_pe"])
        row["s_directness"] = row["directness"]
        row["s_durability"] = row["durability"]
        row["s_rerating"] = row["rerating"]
        row["s_data_quality"] = row["data_quality"]

        total = (
            row["s_leverage"] * W_LEVERAGE
            + row["s_valuation"] * W_VALUATION
            + row["s_directness"] * W_DIRECTNESS
            + row["s_durability"] * W_DURABILITY
            + row["s_rerating"] * W_RERATING
            + row["s_data_quality"] * W_DATA_QUALITY
        )
        row["total_score"] = round(total)
        label, color = exposure_badge(row["total_score"])
        row["badge_label"] = label
        row["badge_color"] = color

    return rows


def fmt_num(val, prefix="", suffix="", decimals=2):
    if val is None:
        return "N/A"
    if abs(val) >= 1e12:
        return f"{prefix}{val/1e12:.2f}T{suffix}"
    if abs(val) >= 1e9:
        return f"{prefix}{val/1e9:.1f}B{suffix}"
    if abs(val) >= 1e6:
        return f"{prefix}{val/1e6:.0f}M{suffix}"
    return f"{prefix}{val:.{decimals}f}{suffix}"


def fmt_pct(val, decimals=1):
    if val is None:
        return "N/A"
    return f"{val:.{decimals}f}%"


def build_payload(rows):
    """Everything the client needs to recompute leverage on the fly."""
    payload = {}
    for ticker_sym, row in rows.items():
        payload[ticker_sym] = {
            "ticker": ticker_sym,
            "label": row["label"],
            "tier": row["tier"],
            "exposure_type": row["exposure_type"],
            "exposure_usd": row["exposure_usd"],
            "exposure_basis": row["exposure_basis"],
            "duration_years": row["duration_years"],
            "mkt_cap": row["mkt_cap"],
            "fwd_pe": row["fwd_pe"],
            "confidence": row["confidence"],
            "as_of": row["as_of"],
            "source": row["source"],
            "ownership": row["ownership"],
            "cost_basis": row["cost_basis"],
            "note": row["note"],
            "price": row["price"],
            "target": row["target"],
            "upside_to_target": row["upside_to_target"],
            "ret_1y": row["ret_1y"],
            "is_live": row["is_live"],
            "mkt_cap_is_live": row["mkt_cap_is_live"],
            "fwd_pe_is_live": row["fwd_pe_is_live"],
            "directness": row["directness"],
            "durability": row["durability"],
            "rerating": row["rerating"],
            "data_quality": row["data_quality"],
        }
    return payload


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Anthropic Exposure Screener &mdash; __NOW__</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=DM+Sans:wght@400;500;700&family=Playfair+Display:wght@400;700&display=swap" rel="stylesheet">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#08090d; color:#d1d5db; font-family:"DM Sans",sans-serif; line-height:1.5; }
  .container { max-width:1180px; margin:0 auto; padding:20px 16px 60px; }
  h1 { font-family:"Playfair Display",serif; font-size:36px; color:#f9fafb; margin-bottom:4px; }
  .subtitle { color:#6b7280; font-size:14px; margin-bottom:20px; }
  .disclaimer { background:#1f1205; border:1px solid #f9731644; border-radius:10px; padding:12px 16px; margin-bottom:24px; font-size:13px; color:#fdba74; }

  .controls { background:#0d1117; border:1px solid #1e293b; border-radius:14px; padding:18px 20px; margin-bottom:24px; }
  .controls-label { font-size:12px; color:#6b7280; text-transform:uppercase; letter-spacing:1px; margin-bottom:10px; }
  .scenario-row { display:flex; flex-wrap:wrap; gap:8px; }
  .scenario-btn { padding:8px 16px; border:1px solid #374151; border-radius:8px; background:#111827; color:#d1d5db; font-family:"JetBrains Mono",monospace; font-size:13px; cursor:pointer; transition:all 0.2s; }
  .scenario-btn:hover { background:#1f2937; }
  .scenario-btn.active { background:#22c55e; border-color:#22c55e; color:#000; font-weight:700; }
  .scenario-hint { margin-top:10px; font-size:12px; color:#6b7280; }

  .section-title { font-family:"Playfair Display",serif; font-size:22px; color:#f9fafb; margin:32px 0 12px; }
  .tier-note { font-size:13px; color:#6b7280; margin-bottom:12px; }

  table { width:100%; border-collapse:collapse; background:#0d1117; border-radius:12px; overflow:hidden; }
  th { background:#111827; padding:10px 8px; text-align:left; font-size:11px; color:#9ca3af; text-transform:uppercase; letter-spacing:0.5px; font-weight:700; }
  td { padding:10px 8px; font-size:13px; border-top:1px solid #161b22; vertical-align:middle; }
  .mono { font-family:"JetBrains Mono",monospace; }
  .tk { font-weight:700; font-size:15px; color:#818cf8; }
  .score-pill { display:inline-block; padding:3px 10px; border-radius:12px; font-size:13px; font-weight:700; color:#000; font-family:"JetBrains Mono",monospace; }
  .conf { display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:700; }

  .card { background:#0d1117; border:1px solid #1e293b; border-radius:14px; padding:18px 20px; margin-bottom:14px; }
  .card-head { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin-bottom:12px; }
  .card-tk { font-family:"Playfair Display",serif; font-size:26px; font-weight:700; color:#f9fafb; }
  .card-name { color:#9ca3af; font-size:14px; }
  .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin-bottom:12px; }
  .kpi { background:#111827; border-radius:10px; padding:10px 12px; }
  .kpi-label { display:block; font-size:11px; color:#6b7280; margin-bottom:3px; text-transform:uppercase; letter-spacing:0.5px; }
  .kpi-val { font-family:"JetBrains Mono",monospace; font-size:19px; font-weight:700; color:#f9fafb; }
  .bars { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:8px; margin-bottom:12px; }
  .bar-row { font-size:12px; }
  .bar-label { display:flex; justify-content:space-between; color:#9ca3af; margin-bottom:3px; }
  .bar-track { height:6px; background:#1f2937; border-radius:3px; overflow:hidden; }
  .bar-fill { height:100%; border-radius:3px; }
  .note { font-size:13px; color:#9ca3af; border-left:2px solid #374151; padding-left:12px; margin-top:10px; }
  .src { font-size:11px; color:#4b5563; margin-top:8px; font-family:"JetBrains Mono",monospace; }
  .judgment-tag { font-size:10px; color:#f97316; text-transform:uppercase; letter-spacing:0.5px; }
  .footer { margin-top:40px; padding-top:20px; border-top:1px solid #1e293b; font-size:12px; color:#4b5563; }
</style>
</head>
<body>
<div class="container">
  <h1>Anthropic Exposure Screener</h1>
  <div class="subtitle">Ranked by how much of each company's value is tied to Anthropic &middot; generated __NOW__</div>

  <div class="disclaimer">
    <strong>Not investment advice.</strong> This is research tooling. Stake values are point-in-time
    marks from SEC filings and sell-side estimates, and they go stale every quarter. Position sizing
    is deliberately not addressed here &mdash; that is a question for a licensed advisor. The public
    S-1 will change several of these inputs; re-verify before relying on any row.
  </div>

  <div class="controls">
    <div class="controls-label">Anthropic valuation scenario</div>
    <div class="scenario-row" id="scenarios"></div>
    <div class="scenario-hint">
      Equity stakes scale linearly from the Series H mark of $965B. Revenue exposure does not scale &mdash;
      it is contracted or attributable sales, shown against market cap for comparison only.
      The two units are not equivalent; read the exposure basis on each card.
    </div>
  </div>

  <div class="section-title">Ranking</div>
  <div class="tier-note">Weighted score: leverage 25%, valuation 20%, directness 20%, durability 15%, re-rating 10%, data quality 10%.</div>
  <table>
    <thead><tr>
      <th>#</th><th>Ticker</th><th>Company</th><th>Tier</th>
      <th>Exposure</th><th>Leverage</th><th>Fwd P/E</th><th>1Y</th><th>Data</th><th>Score</th>
    </tr></thead>
    <tbody id="ranking"></tbody>
  </table>

  <div class="section-title">Detail</div>
  <div id="cards"></div>

  <div class="footer">
    Sources are noted per row. Equity marks: Amazon Q2 2026 10-Q, Alphabet Q2 2026 disclosure,
    Zoom and Salesforce FQ2 2026 10-Qs. Revenue figures: Broadcom Q3 FY26 earnings call plus Mizuho
    estimates, TeraWulf 8-K. SK Telecom, CoreWeave, Nvidia and Microsoft figures are estimates or
    commitments, not marks. Research date 2026-09-10.<br><br>
    The four judgment scores (directness, durability, re-rating, data quality) are hand-set analyst
    inputs, not derived from market data. They encode a view and should be edited in
    <span class="mono">anthropic_screener.py</span> if you disagree with it.
  </div>
</div>

<script>
const DATA = __PAYLOAD__;
const SCENARIOS = __SCENARIOS__;
const MARK_BASE = __MARK_BASE__;
const W = {leverage:0.25, valuation:0.20, directness:0.20, durability:0.15, rerating:0.10, data_quality:0.10};
const CONF = {filing:["SEC filing","#22c55e"], estimate:["Sell-side est.","#fbbf24"], undisclosed:["Undisclosed","#ef4444"]};
let current = MARK_BASE;

function fmtNum(v, prefix) {
  if (v === null || v === undefined) return "N/A";
  prefix = prefix || "";
  const a = Math.abs(v);
  if (a >= 1e12) return prefix + (v/1e12).toFixed(2) + "T";
  if (a >= 1e9) return prefix + (v/1e9).toFixed(1) + "B";
  if (a >= 1e6) return prefix + (v/1e6).toFixed(0) + "M";
  return prefix + v.toFixed(2);
}
function fmtPct(v) { return (v === null || v === undefined) ? "N/A" : v.toFixed(1) + "%"; }
function fmtSigned(v) { return (v === null || v === undefined) ? "N/A" : (v >= 0 ? "+" : "") + v.toFixed(1) + "%"; }

function scaledExposure(d, val) {
  if (d.exposure_usd === null) return null;
  return d.exposure_type === "equity" ? d.exposure_usd * (val / MARK_BASE) : d.exposure_usd;
}
// Revenue is a flow, so a multi-year total is divided to an annual run-rate.
// Equity is a balance-sheet asset, so the full stake counts.
function annualExposure(d, val) {
  const total = scaledExposure(d, val);
  if (total === null) return null;
  if (d.exposure_type === "equity") return total;
  return total / (d.duration_years || 1);
}
function leverage(d, val) {
  const e = annualExposure(d, val);
  if (e === null || !d.mkt_cap) return null;
  return (e / d.mkt_cap) * 100;
}
function scoreMetric(v, lo, hi, invert) {
  if (v === null || v === undefined) return 50;
  let n = (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo);
  if (invert) n = 1 - n;
  return Math.round(n * 100);
}
// A negative forward P/E is forward losses, not a bargain.
function scoreValuation(fwdPe) {
  if (fwdPe === null || fwdPe === undefined) return 50;
  if (fwdPe <= 0) return 15;
  return scoreMetric(fwdPe, 10, 45, true);
}
function totalScore(d, val) {
  const lev = scoreMetric(leverage(d, val), 0, 25, false);
  return Math.round(lev*W.leverage + scoreValuation(d.fwd_pe)*W.valuation
    + d.directness*W.directness + d.durability*W.durability
    + d.rerating*W.rerating + d.data_quality*W.data_quality);
}
function badge(s) {
  if (s >= 75) return ["Top exposure","#22c55e"];
  if (s >= 60) return ["Strong","#a3e635"];
  if (s >= 45) return ["Moderate","#fbbf24"];
  if (s >= 30) return ["Weak","#f97316"];
  return ["Negligible","#ef4444"];
}
function levColor(v) {
  if (v === null) return "#6b7280";
  if (v >= 15) return "#22c55e";
  if (v >= 7) return "#a3e635";
  if (v >= 3) return "#fbbf24";
  return "#f97316";
}

function render() {
  const rows = Object.values(DATA).map(function(d) {
    const s = totalScore(d, current);
    return {d:d, score:s, lev:leverage(d, current), exp:scaledExposure(d, current),
            ann:annualExposure(d, current), badge:badge(s)};
  }).sort(function(a,b) { return b.score - a.score; });

  document.getElementById("ranking").innerHTML = rows.map(function(r,i) {
    const d = r.d, c = CONF[d.confidence];
    return '<tr>'
      + '<td class="mono" style="color:#6b7280">' + (i+1) + '</td>'
      + '<td><a href="#c-' + d.ticker + '" class="tk" style="text-decoration:none">' + d.ticker + '</a></td>'
      + '<td style="color:#9ca3af">' + d.label + '</td>'
      + '<td style="color:#6b7280;font-size:12px">' + d.tier + '</td>'
      + '<td class="mono">' + fmtNum(r.ann,"$") + ' <span style="color:#4b5563;font-size:11px">' + d.exposure_type + (d.duration_years > 1 ? "/yr" : "") + '</span></td>'
      + '<td class="mono" style="color:' + levColor(r.lev) + ';font-weight:700">' + fmtPct(r.lev) + '</td>'
      + '<td class="mono">' + (d.fwd_pe ? d.fwd_pe.toFixed(1)+"x" : "N/A") + '</td>'
      + '<td class="mono" style="color:' + (d.ret_1y >= 0 ? "#22c55e" : "#ef4444") + '">' + fmtSigned(d.ret_1y) + '</td>'
      + '<td><span class="conf" style="background:' + c[1] + '22;color:' + c[1] + '">' + c[0] + '</span></td>'
      + '<td><span class="score-pill" style="background:' + r.badge[1] + '">' + r.score + '</span></td>'
      + '</tr>';
  }).join("");

  document.getElementById("cards").innerHTML = rows.map(function(r) {
    const d = r.d, c = CONF[d.confidence];
    const bars = [
      ["Leverage (computed)", scoreMetric(r.lev,0,25,false), false],
      ["Valuation (computed)", scoreValuation(d.fwd_pe), false],
      ["Directness", d.directness, true],
      ["Durability", d.durability, true],
      ["Re-rating trigger", d.rerating, true],
      ["Data quality", d.data_quality, true]
    ];
    const barHtml = bars.map(function(b) {
      return '<div class="bar-row"><div class="bar-label"><span>' + b[0]
        + (b[2] ? ' <span class="judgment-tag">judgment</span>' : '')
        + '</span><span class="mono">' + b[1] + '</span></div>'
        + '<div class="bar-track"><div class="bar-fill" style="width:' + b[1] + '%;background:' + badge(b[1])[1] + '"></div></div></div>';
    }).join("");
    return '<div class="card" id="c-' + d.ticker + '">'
      + '<div class="card-head">'
      + '<span class="card-tk">' + d.ticker + '</span>'
      + '<span class="card-name">' + d.label + '</span>'
      + '<span class="score-pill" style="background:' + r.badge[1] + '">' + r.score + ' &middot; ' + r.badge[0] + '</span>'
      + '<span class="conf" style="background:' + c[1] + '22;color:' + c[1] + '">' + c[0] + ' &middot; ' + d.as_of + '</span>'
      + '</div><div class="kpis">'
      + '<div class="kpi"><span class="kpi-label">Exposure' + (d.duration_years > 1 ? " (total)" : "") + '</span><span class="kpi-val">' + fmtNum(r.exp,"$") + '</span></div>'
      + (d.duration_years > 1 ? '<div class="kpi"><span class="kpi-label">Annualized</span><span class="kpi-val">' + fmtNum(r.ann,"$") + '</span></div>' : '')
      + '<div class="kpi"><span class="kpi-label">Market cap</span><span class="kpi-val">' + fmtNum(d.mkt_cap,"$") + '</span></div>'
      + '<div class="kpi"><span class="kpi-label">Leverage</span><span class="kpi-val" style="color:' + levColor(r.lev) + '">' + fmtPct(r.lev) + '</span></div>'
      + '<div class="kpi"><span class="kpi-label">Fwd P/E</span><span class="kpi-val">' + (d.fwd_pe ? d.fwd_pe.toFixed(1)+"x" : "N/A") + '</span></div>'
      + '<div class="kpi"><span class="kpi-label">Cons. target</span><span class="kpi-val">' + (d.target ? "$"+d.target.toFixed(0) : "N/A") + '</span></div>'
      + '<div class="kpi"><span class="kpi-label">To target</span><span class="kpi-val">' + fmtSigned(d.upside_to_target) + '</span></div>'
      + '</div><div class="bars">' + barHtml + '</div>'
      + '<div class="note">' + d.note + '</div>'
      + '<div class="src">Basis: ' + d.exposure_basis + ' &middot; Source: ' + d.source
      + (d.ownership ? ' &middot; Ownership: ' + d.ownership : '')
      + (d.cost_basis ? ' &middot; Cost basis: ' + fmtNum(d.cost_basis,"$") : '')
      + (!d.mkt_cap_is_live ? ' &middot; MARKET CAP FROM RESEARCH FALLBACK, NOT LIVE' : '')
      + '</div></div>';
  }).join("");
}

document.getElementById("scenarios").innerHTML = SCENARIOS.map(function(s) {
  return '<button class="scenario-btn' + (s[1] === MARK_BASE ? " active" : "")
    + '" data-val="' + s[1] + '">' + s[0] + '</button>';
}).join("");
document.querySelectorAll(".scenario-btn").forEach(function(b) {
  b.addEventListener("click", function() {
    current = parseFloat(b.dataset.val);
    document.querySelectorAll(".scenario-btn").forEach(function(x) { x.classList.remove("active"); });
    b.classList.add("active");
    render();
  });
});
render();
</script>
</body>
</html>
"""


def generate_html(rows):
    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    html = HTML_TEMPLATE
    html = html.replace("__PAYLOAD__", json.dumps(build_payload(rows), default=str))
    html = html.replace("__SCENARIOS__", json.dumps(SCENARIOS))
    html = html.replace("__MARK_BASE__", repr(ANTHROPIC_MARK_BASE))
    html = html.replace("__NOW__", now)
    return html


def print_ranking(rows, label):
    ranked = sorted(rows.values(), key=lambda r: r.get("total_score", 0), reverse=True)
    print()
    print(f"  RANKING AT ANTHROPIC = {label}")
    print("-" * 78)
    print(f"  {'#':<3} {'TICKER':<7} {'TIER':<7} {'EXP/YR':>10} {'LEVERAGE':>9} {'FWD PE':>7} {'SCORE':>6}")
    print("-" * 78)
    for i, r in enumerate(ranked):
        lev = fmt_pct(r["leverage_pct"]) if r["leverage_pct"] is not None else "N/A"
        fpe = f"{r['fwd_pe']:.1f}x" if r["fwd_pe"] else "N/A"
        print(
            f"  {i+1:<3} {r['ticker']:<7} {r['tier']:<7} "
            f"{fmt_num(r['exposure_annual'], '$'):>10} {lev:>9} {fpe:>7} {r['total_score']:>6}"
        )
    print("-" * 78)


def main():
    print("=" * 78)
    print("  ANTHROPIC EXPOSURE SCREENER")
    print("  Not investment advice. Marks are point-in-time and go stale quarterly.")
    print("=" * 78)

    rows = fetch_market_data()

    stale = [t for t, r in rows.items() if not r["mkt_cap_is_live"]]
    if stale:
        print(f"\n  NOTE: using researched fallback market caps for: {', '.join(stale)}")

    rows = calculate_scores(rows, ANTHROPIC_MARK_BASE)
    print_ranking(rows, "SERIES H ($965B)")

    core = {t: dict(r) for t, r in rows.items() if r["tier"] == TIER_CORE}
    calculate_scores(core, 2.0e12)
    print_ranking(core, "$2T (CORE TIER ONLY)")

    out_path = Path(__file__).parent / "anthropic_dashboard.html"
    out_path.write_text(generate_html(rows), encoding="utf-8")
    print(f"\n  Dashboard: {out_path}")

    data_path = Path(__file__).parent / "anthropic_exposure.json"
    export = {
        "generated": datetime.now().isoformat(),
        "anthropic_mark_base": ANTHROPIC_MARK_BASE,
        "research_date": "2026-09-10",
        "disclaimer": "Not investment advice. Point-in-time marks; re-verify against filings.",
        "rows": build_payload(rows),
    }
    data_path.write_text(json.dumps(export, indent=2, default=str), encoding="utf-8")
    print(f"  Data:      {data_path}")
    print()


if __name__ == "__main__":
    main()
