import yfinance as yf
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

SECTORS = {
    "Energy": ["CEG", "VRT", "BE", "ETN"],
    "Memory": ["MU"],
    "Production + Operation": ["NVDA", "AMD", "ASML", "TSM", "ARM", "CDNS", "ANET"],
    "Decision + Chaos": ["ORCL", "MSFT", "GOOGL", "PLTR", "CRWD", "DDOG", "MDB"],
    "Automation": ["TSLA", "META", "AMZN", "SOFI", "HOOD"],
}

TICKER_TO_SECTOR = {}
for sector, tickers in SECTORS.items():
    for t in tickers:
        TICKER_TO_SECTOR[t] = sector

ALL_TICKERS = [t for tickers in SECTORS.values() for t in tickers]

W_VALUATION = 0.35
W_HEALTH = 0.35
W_MOMENTUM = 0.30


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


def risk_badge(score):
    if score >= 75:
        return ("Strong Buy", "#22c55e")
    if score >= 60:
        return ("Buy", "#a3e635")
    if score >= 45:
        return ("Hold", "#fbbf24")
    if score >= 30:
        return ("Cautious", "#f97316")
    return ("Sell", "#ef4444")


def risk_zone(score):
    if score >= 75:
        return "green"
    if score >= 60:
        return "gold"
    if score >= 45:
        return "amber"
    return "red"


def fetch_all_data():
    print(f"Fetching data for {len(ALL_TICKERS)} stocks...")
    end = datetime.now()
    start = end - timedelta(days=400)
    stocks = {}

    for ticker_sym in ALL_TICKERS:
        print(f"  {ticker_sym}...", end=" ", flush=True)
        try:
            tk = yf.Ticker(ticker_sym)
            info = tk.info or {}
            hist = tk.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
            quarterly = None
            try:
                quarterly = tk.quarterly_financials
            except Exception:
                pass
            balance = None
            try:
                balance = tk.balance_sheet
            except Exception:
                pass

            price = safe(info.get("currentPrice")) or safe(info.get("regularMarketPrice"))
            if price is None and len(hist) > 0:
                price = float(hist["Close"].iloc[-1])

            high_52 = safe(info.get("fiftyTwoWeekHigh"))
            low_52 = safe(info.get("fiftyTwoWeekLow"))
            ma_50 = safe(info.get("fiftyDayAverage"))
            ma_200 = safe(info.get("twoHundredDayAverage"))
            pe = safe(info.get("trailingPE"))
            fwd_pe = safe(info.get("forwardPE"))
            pb = safe(info.get("priceToBook"))
            peg = safe(info.get("pegRatio"))
            ev_ebitda = safe(info.get("enterpriseToEbitda"))
            mkt_cap = safe(info.get("marketCap"))
            rev = safe(info.get("totalRevenue"))
            rev_growth = safe(info.get("revenueGrowth"))
            earnings_growth = safe(info.get("earningsGrowth"))
            profit_margin = safe(info.get("profitMargins"))
            roe = safe(info.get("returnOnEquity"))
            de = safe(info.get("debtToEquity"))
            current_ratio = safe(info.get("currentRatio"))
            beta = safe(info.get("beta"))
            dividend_yield = safe(info.get("dividendYield"))
            short_name = info.get("shortName", ticker_sym)
            sector_yf = info.get("sector", "")
            industry = info.get("industry", "")

            prices_12m = []
            if len(hist) > 0:
                monthly = hist["Close"].resample("W").last().dropna()
                prices_12m = [round(float(p), 2) for p in monthly.values[-52:]]

            ret_3m = None
            ret_6m = None
            ret_1m = None
            if len(hist) > 20:
                close = hist["Close"]
                ret_1m = pct(float(close.iloc[-1]), float(close.iloc[-min(22, len(close))]))
                if len(close) > 63:
                    ret_3m = pct(float(close.iloc[-1]), float(close.iloc[-min(63, len(close))]))
                if len(close) > 126:
                    ret_6m = pct(float(close.iloc[-1]), float(close.iloc[-min(126, len(close))]))

            quarterly_data = []
            if quarterly is not None and not quarterly.empty:
                for col in quarterly.columns[:4]:
                    q_rev = safe(quarterly.loc["Total Revenue", col]) if "Total Revenue" in quarterly.index else None
                    q_ni = safe(quarterly.loc["Net Income", col]) if "Net Income" in quarterly.index else None
                    q_gp = safe(quarterly.loc["Gross Profit", col]) if "Gross Profit" in quarterly.index else None
                    quarterly_data.append({
                        "date": col.strftime("%Y-%m-%d"),
                        "quarter": f"Q{((col.month - 1) // 3) + 1} {col.year}",
                        "revenue": q_rev,
                        "net_income": q_ni,
                        "gross_profit": q_gp,
                    })

            stocks[ticker_sym] = {
                "ticker": ticker_sym,
                "name": short_name,
                "sector": TICKER_TO_SECTOR[ticker_sym],
                "industry": industry,
                "price": price,
                "mkt_cap": mkt_cap,
                "pe": pe,
                "fwd_pe": fwd_pe,
                "pb": pb,
                "peg": peg,
                "ev_ebitda": ev_ebitda,
                "rev_growth": rev_growth,
                "earnings_growth": earnings_growth,
                "profit_margin": profit_margin,
                "roe": roe,
                "de": de,
                "current_ratio": current_ratio,
                "beta": beta,
                "dividend_yield": dividend_yield,
                "high_52": high_52,
                "low_52": low_52,
                "ma_50": ma_50,
                "ma_200": ma_200,
                "ret_1m": ret_1m,
                "ret_3m": ret_3m,
                "ret_6m": ret_6m,
                "prices_12m": prices_12m,
                "quarterly": quarterly_data,
            }
            print("OK")
        except Exception as e:
            print(f"ERROR: {e}")
            stocks[ticker_sym] = {
                "ticker": ticker_sym,
                "name": ticker_sym,
                "sector": TICKER_TO_SECTOR[ticker_sym],
                "industry": "",
                "price": None,
                "mkt_cap": None,
                "pe": None, "fwd_pe": None, "pb": None, "peg": None, "ev_ebitda": None,
                "rev_growth": None, "earnings_growth": None, "profit_margin": None,
                "roe": None, "de": None, "current_ratio": None, "beta": None,
                "dividend_yield": None, "high_52": None, "low_52": None,
                "ma_50": None, "ma_200": None,
                "ret_1m": None, "ret_3m": None, "ret_6m": None,
                "prices_12m": [], "quarterly": [],
            }
    return stocks


def compute_sector_medians(stocks):
    medians = {}
    for sector, tickers in SECTORS.items():
        vals = {"pe": [], "pb": [], "peg": [], "ev_ebitda": [], "profit_margin": [], "roe": []}
        for t in tickers:
            s = stocks.get(t, {})
            for k in vals:
                v = s.get(k)
                if v is not None:
                    vals[k].append(v)
        medians[sector] = {}
        for k, arr in vals.items():
            if arr:
                arr.sort()
                mid = len(arr) // 2
                medians[sector][k] = arr[mid] if len(arr) % 2 else (arr[mid - 1] + arr[mid]) / 2
            else:
                medians[sector][k] = None
    return medians


def calculate_scores(stocks, medians):
    for ticker_sym, s in stocks.items():
        pe = s.get("pe")
        pb = s.get("pb")
        peg = s.get("peg")
        ev_ebitda = s.get("ev_ebitda")
        v1 = score_metric(pe, 5, 80, invert=True)
        v2 = score_metric(pb, 0.5, 20, invert=True)
        v3 = score_metric(peg, 0, 3, invert=True)
        v4 = score_metric(ev_ebitda, 5, 60, invert=True)
        val_score = round((v1 + v2 + v3 + v4) / 4)

        rev_g = (s.get("rev_growth") or 0) * 100
        earn_g = (s.get("earnings_growth") or 0) * 100
        pm = (s.get("profit_margin") or 0) * 100
        roe_v = (s.get("roe") or 0) * 100
        de_v = s.get("de") or 50
        cr = s.get("current_ratio") or 1.0
        h1 = score_metric(rev_g, -10, 60)
        h2 = score_metric(earn_g, -20, 80)
        h3 = score_metric(pm, -10, 40)
        h4 = score_metric(roe_v, -5, 40)
        h5 = score_metric(de_v, 0, 300, invert=True)
        h6 = score_metric(cr, 0.5, 3.0)
        health_score = round((h1 + h2 + h3 + h4 + h5 + h6) / 6)

        pct_52 = None
        if s.get("price") and s.get("high_52"):
            pct_52 = (s["price"] / s["high_52"]) * 100
        m1 = score_metric(pct_52, 50, 100)
        m2 = 50
        if s.get("ma_50") and s.get("ma_200") and s["ma_200"] != 0:
            ma_ratio = (s["ma_50"] / s["ma_200"] - 1) * 100
            m2 = score_metric(ma_ratio, -15, 15)
        m3 = score_metric(s.get("ret_3m"), -20, 30)
        m4 = score_metric(s.get("ret_6m"), -30, 50)
        momentum_score = round((m1 + m2 + m3 + m4) / 4)

        total = round(val_score * W_VALUATION + health_score * W_HEALTH + momentum_score * W_MOMENTUM)
        badge_label, badge_color = risk_badge(total)

        s["val_score"] = val_score
        s["health_score"] = health_score
        s["momentum_score"] = momentum_score
        s["total_score"] = total
        s["badge_label"] = badge_label
        s["badge_color"] = badge_color
        s["zone"] = risk_zone(total)

        sect = s["sector"]
        s["sector_medians"] = medians.get(sect, {})

    return stocks


def fmt_num(val, prefix="", suffix="", decimals=2):
    if val is None:
        return "N/A"
    if abs(val) >= 1e12:
        return f"{prefix}{val/1e12:.1f}T{suffix}"
    if abs(val) >= 1e9:
        return f"{prefix}{val/1e9:.1f}B{suffix}"
    if abs(val) >= 1e6:
        return f"{prefix}{val/1e6:.1f}M{suffix}"
    return f"{prefix}{val:.{decimals}f}{suffix}"


def fmt_pct(val):
    if val is None:
        return "N/A"
    return f"{val*100 if abs(val) < 5 else val:+.1f}%"


def color_tag(val, thresholds=(0, 20, 50), invert=False):
    if val is None:
        return "#6b7280"
    if invert:
        if val <= thresholds[0]:
            return "#22c55e"
        if val <= thresholds[1]:
            return "#fbbf24"
        return "#ef4444"
    if val >= thresholds[2]:
        return "#22c55e"
    if val >= thresholds[1]:
        return "#fbbf24"
    return "#ef4444"


def svg_price_chart(prices, width=600, height=160):
    if not prices or len(prices) < 2:
        return '<svg width="600" height="160"><text x="300" y="80" fill="#6b7280" text-anchor="middle" font-family="DM Sans">No price data</text></svg>'
    mn = min(prices)
    mx = max(prices)
    rng = mx - mn if mx != mn else 1
    pad = 10
    w = width - 2 * pad
    h = height - 2 * pad
    points = []
    for i, p in enumerate(prices):
        x = pad + (i / (len(prices) - 1)) * w
        y = pad + h - ((p - mn) / rng) * h
        points.append(f"{x:.1f},{y:.1f}")
    path = "M" + "L".join(points)
    fill_path = path + f"L{pad + w:.1f},{pad + h:.1f}L{pad:.1f},{pad + h:.1f}Z"
    start_p = prices[0]
    end_p = prices[-1]
    line_color = "#22c55e" if end_p >= start_p else "#ef4444"
    grad_id = f"grad_{hash(tuple(prices)) % 99999}"
    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
  <defs><linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="{line_color}" stop-opacity="0.3"/>
    <stop offset="100%" stop-color="{line_color}" stop-opacity="0.02"/>
  </linearGradient></defs>
  <path d="{fill_path}" fill="url(#{grad_id})" />
  <path d="{path}" fill="none" stroke="{line_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="{pad}" y="{height - 2}" fill="#6b7280" font-size="11" font-family="JetBrains Mono">${start_p:,.0f}</text>
  <text x="{width - pad}" y="{height - 2}" fill="#6b7280" font-size="11" font-family="JetBrains Mono" text-anchor="end">${end_p:,.0f}</text>
</svg>'''


def generate_stock_card(s):
    score = s["total_score"]
    badge_label = s["badge_label"]
    badge_color = s["badge_color"]
    zone = s["zone"]

    zone_colors = {"red": "#ef4444", "amber": "#f97316", "gold": "#fbbf24", "green": "#22c55e"}
    zone_c = zone_colors.get(zone, "#6b7280")

    pe_color = color_tag(s.get("pe"), (15, 25, 999), invert=True)
    pb_color = color_tag(s.get("pb"), (1, 5, 999), invert=True)
    peg_color = color_tag(s.get("peg"), (0.5, 1.5, 999), invert=True)

    rev_g_val = s.get("rev_growth")
    rev_g_color = color_tag(rev_g_val * 100 if rev_g_val else None, (0, 10, 25))
    pm_val = s.get("profit_margin")
    pm_color = color_tag(pm_val * 100 if pm_val else None, (0, 10, 20))
    roe_val = s.get("roe")
    roe_color = color_tag(roe_val * 100 if roe_val else None, (0, 10, 20))

    medians = s.get("sector_medians", {})

    def median_cmp(val, med_key, fmt_fn, invert=False):
        med = medians.get(med_key)
        if val is None or med is None:
            return ""
        diff_sym = "▲" if (val < med if invert else val > med) else "▼"
        diff_c = "#22c55e" if diff_sym == "▲" else "#ef4444"
        return f'<span style="color:{diff_c};font-size:12px;margin-left:6px" title="Sector median: {fmt_fn(med)}">{diff_sym} vs median</span>'

    chart_svg = svg_price_chart(s.get("prices_12m", []))

    quarterly_html = ""
    for q in s.get("quarterly", []):
        rev_q = q.get("revenue")
        ni_q = q.get("net_income")
        row_color = "#1a2e1a" if ni_q and ni_q > 0 else "#2e1a1a" if ni_q and ni_q < 0 else "#12131a"
        quarterly_html += f'''<tr style="background:{row_color}">
          <td style="padding:10px;font-family:JetBrains Mono;font-size:14px">{q["quarter"]}</td>
          <td style="padding:10px;font-family:JetBrains Mono;font-size:14px">{fmt_num(rev_q, "$")}</td>
          <td style="padding:10px;font-family:JetBrains Mono;font-size:14px">{fmt_num(ni_q, "$")}</td>
          <td style="padding:10px;font-family:JetBrains Mono;font-size:14px">{fmt_num(q.get("gross_profit"), "$")}</td>
        </tr>'''

    catalysts = []
    risks = []
    if s.get("rev_growth") and s["rev_growth"] > 0.15:
        catalysts.append(("Strong Revenue Growth", "HIGH IMPACT"))
    if s.get("earnings_growth") and s["earnings_growth"] > 0.20:
        catalysts.append(("Earnings Acceleration", "HIGH IMPACT"))
    if s.get("ma_50") and s.get("ma_200") and s["ma_50"] > s["ma_200"]:
        catalysts.append(("Golden Cross (50 > 200 MA)", "MEDIUM"))
    if s.get("ret_3m") and s["ret_3m"] > 15:
        catalysts.append(("Strong 3M Momentum", "MEDIUM"))
    if s.get("roe") and s["roe"] > 0.20:
        catalysts.append(("High Return on Equity", "MEDIUM"))

    if s.get("pe") and s["pe"] > 60:
        risks.append(("Elevated Valuation (P/E)", "HIGH IMPACT"))
    if s.get("de") and s["de"] > 200:
        risks.append(("High Debt-to-Equity", "HIGH IMPACT"))
    if s.get("beta") and s["beta"] > 1.5:
        risks.append(("High Volatility (Beta)", "MEDIUM"))
    if s.get("ret_3m") and s["ret_3m"] < -10:
        risks.append(("Negative 3M Momentum", "HIGH IMPACT"))
    if s.get("profit_margin") and s["profit_margin"] < 0:
        risks.append(("Unprofitable", "HIGH IMPACT"))
    if s.get("peg") and s["peg"] > 2.5:
        risks.append(("Overpriced vs Growth (PEG)", "MEDIUM"))

    if not catalysts:
        catalysts.append(("Stable Fundamentals", "MEDIUM"))
    if not risks:
        risks.append(("No Major Red Flags", "LOW"))

    catalyst_html = ""
    for label, severity in catalysts:
        sev_color = "#22c55e" if severity == "HIGH IMPACT" else "#fbbf24"
        catalyst_html += f'<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:#111827;border-radius:8px;margin-bottom:6px"><span style="color:#d1d5db;font-size:14px">{label}</span><span style="color:{sev_color};font-size:11px;font-weight:700;padding:3px 8px;border:1px solid {sev_color};border-radius:4px">{severity}</span></div>'

    risk_html = ""
    for label, severity in risks:
        sev_color = "#ef4444" if severity == "HIGH IMPACT" else "#f97316" if severity == "MEDIUM" else "#6b7280"
        risk_html += f'<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:#111827;border-radius:8px;margin-bottom:6px"><span style="color:#d1d5db;font-size:14px">{label}</span><span style="color:{sev_color};font-size:11px;font-weight:700;padding:3px 8px;border:1px solid {sev_color};border-radius:4px">{severity}</span></div>'

    verdict_text = f"{s['name']} scores {score}/100."
    if score >= 75:
        verdict_text += " Strong fundamentals with solid momentum. Attractive entry point."
    elif score >= 60:
        verdict_text += " Good overall profile. Consider on pullbacks."
    elif score >= 45:
        verdict_text += " Mixed signals. Watch for catalyst before entering."
    elif score >= 30:
        verdict_text += " Elevated risk profile. Wait for improvement in fundamentals."
    else:
        verdict_text += " Significant headwinds. Avoid until conditions improve."

    return f'''
    <div class="stock-card" id="card-{s["ticker"]}">
      <!-- HERO STRIP -->
      <div style="display:flex;align-items:center;gap:16px;padding:24px 28px;background:linear-gradient(135deg,#111827,#1f2937);border-radius:16px 16px 0 0;flex-wrap:wrap">
        <span style="font-family:Playfair Display;font-size:32px;font-weight:700;color:#f9fafb">{s["ticker"]}</span>
        <span style="font-size:15px;color:#9ca3af;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{s["name"]}</span>
        <span style="font-family:JetBrains Mono;font-size:28px;font-weight:700;color:#f9fafb;margin-left:auto">{score}</span>
        <span style="font-size:13px;color:#9ca3af">/100</span>
        <span style="padding:6px 14px;border-radius:20px;font-size:13px;font-weight:700;color:#000;background:{badge_color}">{badge_label}</span>
        <button onclick="copyCard('{s["ticker"]}')" style="margin-left:8px;background:none;border:1px solid #374151;color:#9ca3af;padding:6px 12px;border-radius:8px;cursor:pointer;font-size:12px" title="Copy to clipboard">📋</button>
      </div>

      <!-- SCORE BAR -->
      <div style="padding:0 28px;background:#111827">
        <div style="position:relative;height:28px;border-radius:14px;overflow:hidden;background:linear-gradient(to right,#ef4444 0%,#ef4444 30%,#f97316 30%,#f97316 45%,#fbbf24 45%,#fbbf24 60%,#22c55e 60%,#22c55e 100%)">
          <div style="position:absolute;left:{score}%;top:0;transform:translateX(-50%);width:4px;height:100%;background:#fff;border-radius:2px;box-shadow:0 0 8px rgba(255,255,255,0.8)"></div>
          <div style="position:absolute;left:{score}%;top:-2px;transform:translateX(-50%);font-size:11px;color:#fff;font-weight:700;text-shadow:0 1px 3px #000">{score}</div>
        </div>
        <div style="display:flex;justify-content:space-between;padding:4px 0;font-size:11px;color:#6b7280">
          <span>Sell</span><span>Cautious</span><span>Hold</span><span>Buy</span><span>Strong Buy</span>
        </div>
      </div>

      <!-- PAGE 1 -->
      <div style="padding:20px 28px;background:#0d1117">
        <!-- KPI STRIP -->
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin-bottom:20px">
          <div class="kpi"><span class="kpi-label">Price</span><span class="kpi-val">{f'${s["price"]:,.2f}' if s["price"] else "N/A"}</span></div>
          <div class="kpi"><span class="kpi-label">Mkt Cap</span><span class="kpi-val">{fmt_num(s["mkt_cap"], "$")}</span></div>
          <div class="kpi"><span class="kpi-label">P/E</span><span class="kpi-val">{fmt_num(s["pe"], decimals=1) if s["pe"] else "N/A"}</span></div>
          <div class="kpi"><span class="kpi-label">Beta</span><span class="kpi-val">{fmt_num(s["beta"], decimals=2) if s["beta"] else "N/A"}</span></div>
          <div class="kpi"><span class="kpi-label">Div Yield</span><span class="kpi-val">{fmt_pct(s["dividend_yield"]) if s["dividend_yield"] else "N/A"}</span></div>
          <div class="kpi"><span class="kpi-label">52W Range</span><span class="kpi-val">{fmt_num(s["low_52"], "$", decimals=0)}-{fmt_num(s["high_52"], "$", decimals=0)}</span></div>
        </div>

        <!-- 12-MONTH CHART -->
        <div style="background:#111827;border-radius:12px;padding:16px;margin-bottom:20px">
          <div style="font-family:Playfair Display;font-size:16px;color:#d1d5db;margin-bottom:8px">12-Month Price Chart</div>
          {chart_svg}
        </div>

        <!-- 6-CARD GRID -->
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-bottom:16px">
          <!-- Valuation Cards -->
          <div class="metric-card">
            <div class="metric-header">P/E Ratio <span class="tag" style="background:{pe_color}">{fmt_num(s["pe"], decimals=1)}</span></div>
            <div class="metric-sub">Forward P/E: {fmt_num(s["fwd_pe"], decimals=1)}{median_cmp(s.get("pe"), "pe", lambda v: f"{v:.1f}", invert=True)}</div>
            <details class="explainer"><summary>What is P/E?</summary><p>Price-to-Earnings ratio shows how much investors pay per dollar of earnings. Lower = cheaper relative to earnings.</p></details>
          </div>
          <div class="metric-card">
            <div class="metric-header">P/B Ratio <span class="tag" style="background:{pb_color}">{fmt_num(s["pb"], decimals=2)}</span></div>
            <div class="metric-sub">Book value comparison{median_cmp(s.get("pb"), "pb", lambda v: f"{v:.2f}", invert=True)}</div>
            <details class="explainer"><summary>What is P/B?</summary><p>Price-to-Book compares market price to net asset value. Below 1.0 may indicate undervaluation.</p></details>
          </div>
          <div class="metric-card">
            <div class="metric-header">PEG Ratio <span class="tag" style="background:{peg_color}">{fmt_num(s["peg"], decimals=2)}</span></div>
            <div class="metric-sub">Growth-adjusted valuation{median_cmp(s.get("peg"), "peg", lambda v: f"{v:.2f}", invert=True)}</div>
            <details class="explainer"><summary>What is PEG?</summary><p>PEG adjusts P/E for growth rate. Below 1.0 suggests undervalued relative to growth.</p></details>
          </div>

          <!-- Health & Growth Cards -->
          <div class="metric-card">
            <div class="metric-header">Revenue Growth <span class="tag" style="background:{rev_g_color}">{fmt_pct(s["rev_growth"])}</span></div>
            <div class="metric-sub">Year-over-year{median_cmp(s.get("rev_growth"), "profit_margin", lambda v: f"{v*100:.1f}%") if s.get("rev_growth") else ""}</div>
            <details class="explainer"><summary>Why it matters</summary><p>Revenue growth shows how fast the business is expanding. Consistent growth above 15% is strong.</p></details>
          </div>
          <div class="metric-card">
            <div class="metric-header">Profit Margin <span class="tag" style="background:{pm_color}">{fmt_pct(s["profit_margin"])}</span></div>
            <div class="metric-sub">Net margin{median_cmp(s.get("profit_margin"), "profit_margin", lambda v: f"{v*100:.1f}%")}</div>
            <details class="explainer"><summary>Why it matters</summary><p>Profit margin shows how much of each revenue dollar becomes profit. Higher = more efficient.</p></details>
          </div>
          <div class="metric-card">
            <div class="metric-header">ROE <span class="tag" style="background:{roe_color}">{fmt_pct(s["roe"])}</span></div>
            <div class="metric-sub">Return on equity{median_cmp(s.get("roe"), "roe", lambda v: f"{v*100:.1f}%")}</div>
            <details class="explainer"><summary>Why it matters</summary><p>ROE measures how effectively the company uses shareholders' money to generate profit. Above 15% is good.</p></details>
          </div>
        </div>

        <!-- SECTOR MEDIAN ROW -->
        <div style="background:#111827;border-radius:10px;padding:12px 16px;margin-bottom:16px;display:flex;gap:20px;flex-wrap:wrap;font-size:13px;color:#9ca3af">
          <span style="font-weight:600;color:#d1d5db">Sector Median ({s["sector"]}):</span>
          <span>P/E {fmt_num(medians.get("pe"), decimals=1)}</span>
          <span>P/B {fmt_num(medians.get("pb"), decimals=2)}</span>
          <span>Margin {fmt_pct(medians.get("profit_margin"))}</span>
          <span>ROE {fmt_pct(medians.get("roe"))}</span>
        </div>

        <!-- SCORE BREAKDOWN -->
        <div style="background:#111827;border-radius:12px;padding:16px;margin-bottom:8px">
          <div style="font-family:Playfair Display;font-size:16px;color:#d1d5db;margin-bottom:12px">Score Breakdown</div>
          <div class="score-row">
            <span class="score-label">Valuation (35%)</span>
            <div class="score-bar-bg"><div class="score-bar-fill" style="width:{s["val_score"]}%;background:#6366f1"></div></div>
            <span class="score-num">{s["val_score"]}</span>
          </div>
          <div class="score-row">
            <span class="score-label">Health & Growth (35%)</span>
            <div class="score-bar-bg"><div class="score-bar-fill" style="width:{s["health_score"]}%;background:#8b5cf6"></div></div>
            <span class="score-num">{s["health_score"]}</span>
          </div>
          <div class="score-row">
            <span class="score-label">Momentum (30%)</span>
            <div class="score-bar-bg"><div class="score-bar-fill" style="width:{s["momentum_score"]}%;background:#a78bfa"></div></div>
            <span class="score-num">{s["momentum_score"]}</span>
          </div>
        </div>
      </div>

      <!-- PAGE 2 -->
      <div style="padding:20px 28px;background:#0a0c12;border-radius:0 0 16px 16px">
        <!-- QUARTERLY TREND TABLE -->
        {f"""<div style="margin-bottom:20px">
          <div style="font-family:Playfair Display;font-size:16px;color:#d1d5db;margin-bottom:10px">Quarterly Trends</div>
          <table style="width:100%;border-collapse:collapse;border-radius:10px;overflow:hidden">
            <thead><tr style="background:#1f2937">
              <th style="padding:10px;text-align:left;color:#9ca3af;font-size:13px">Quarter</th>
              <th style="padding:10px;text-align:left;color:#9ca3af;font-size:13px">Revenue</th>
              <th style="padding:10px;text-align:left;color:#9ca3af;font-size:13px">Net Income</th>
              <th style="padding:10px;text-align:left;color:#9ca3af;font-size:13px">Gross Profit</th>
            </tr></thead>
            <tbody>{quarterly_html}</tbody>
          </table>
        </div>""" if quarterly_html else ""}

        <!-- CATALYSTS vs RISKS -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
          <div>
            <div style="font-family:Playfair Display;font-size:16px;color:#22c55e;margin-bottom:10px">Catalysts</div>
            {catalyst_html}
          </div>
          <div>
            <div style="font-family:Playfair Display;font-size:16px;color:#ef4444;margin-bottom:10px">Risks</div>
            {risk_html}
          </div>
        </div>

        <!-- BOTTOM LINE -->
        <div style="background:linear-gradient(135deg,#111827,#1e293b);border-radius:12px;padding:20px;border-left:4px solid {badge_color}">
          <div style="font-family:Playfair Display;font-size:18px;color:#f9fafb;margin-bottom:8px">Bottom Line</div>
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
            <div style="background:#1f2937;border-radius:8px;padding:8px 16px;flex-shrink:0">
              <span style="font-family:JetBrains Mono;font-size:24px;font-weight:700;color:{badge_color}">{score}</span>
              <span style="color:#6b7280;font-size:13px">/100</span>
            </div>
            <div style="flex:1;height:8px;border-radius:4px;background:linear-gradient(to right,#ef4444,#f97316,#fbbf24,#22c55e);position:relative">
              <div style="position:absolute;left:{score}%;top:-4px;width:16px;height:16px;border-radius:50%;background:{badge_color};border:2px solid #fff;transform:translateX(-50%)"></div>
            </div>
            <span style="padding:6px 14px;border-radius:20px;font-size:14px;font-weight:700;color:#000;background:{badge_color}">{badge_label}</span>
          </div>
          <p style="color:#d1d5db;font-size:14px;line-height:1.6;margin:0">{verdict_text}</p>
        </div>
      </div>
    </div>'''


def generate_html(stocks):
    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    sorted_stocks = sorted(stocks.values(), key=lambda s: s.get("total_score", 0), reverse=True)
    best = sorted_stocks[0] if sorted_stocks else None

    sector_nav = ""
    for sector in SECTORS:
        tickers = SECTORS[sector]
        sector_nav += f'<div class="sector-group"><div class="sector-title">{sector}</div><div class="sector-tickers">'
        for t in tickers:
            s = stocks.get(t, {})
            sc = s.get("total_score", 0)
            bc = s.get("badge_color", "#6b7280")
            sector_nav += f'<a href="#card-{t}" class="ticker-chip" style="border-color:{bc}">{t} <span style="color:{bc};font-weight:700">{sc}</span></a>'
        sector_nav += '</div></div>'

    cards_html = ""
    for s in sorted_stocks:
        cards_html += generate_stock_card(s)

    ranking_rows = ""
    for i, s in enumerate(sorted_stocks):
        ranking_rows += f'''<tr style="background:{"#111827" if i % 2 == 0 else "#0d1117"}">
          <td style="padding:10px;font-family:JetBrains Mono;color:#f9fafb;font-size:14px">#{i+1}</td>
          <td style="padding:10px"><a href="#card-{s["ticker"]}" style="color:#818cf8;text-decoration:none;font-weight:700;font-size:15px">{s["ticker"]}</a></td>
          <td style="padding:10px;color:#9ca3af;font-size:13px">{s["name"][:25]}</td>
          <td style="padding:10px;font-family:JetBrains Mono;font-size:14px;color:#f9fafb">{f'${s["price"]:,.2f}' if s["price"] else "N/A"}</td>
          <td style="padding:10px;text-align:center"><span style="padding:4px 10px;border-radius:12px;font-size:13px;font-weight:700;color:#000;background:{s["badge_color"]}">{s["total_score"]}</span></td>
          <td style="padding:10px;color:{s["badge_color"]};font-size:13px;font-weight:600">{s["badge_label"]}</td>
        </tr>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stock Risk Screener — {now}</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=DM+Sans:wght@400;500;700&family=Playfair+Display:wght@400;700&display=swap" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#08090d; color:#d1d5db; font-family:"DM Sans",sans-serif; line-height:1.5; }}
  .container {{ max-width:1100px; margin:0 auto; padding:20px 16px; }}
  h1 {{ font-family:"Playfair Display",serif; font-size:36px; color:#f9fafb; margin-bottom:4px; }}
  .subtitle {{ color:#6b7280; font-size:14px; margin-bottom:24px; }}
  .hero-best {{ background:linear-gradient(135deg,#111827 0%,#064e3b 100%); border-radius:16px; padding:28px; margin-bottom:24px; border:1px solid #22c55e33; }}
  .hero-best-title {{ font-family:"Playfair Display",serif; font-size:14px; color:#22c55e; text-transform:uppercase; letter-spacing:2px; margin-bottom:8px; }}
  .hero-best-row {{ display:flex; align-items:center; gap:16px; flex-wrap:wrap; }}
  .hero-best-ticker {{ font-family:"Playfair Display",serif; font-size:42px; font-weight:700; color:#f9fafb; }}
  .hero-best-score {{ font-family:"JetBrains Mono",monospace; font-size:36px; font-weight:700; color:#22c55e; }}

  .sector-group {{ margin-bottom:12px; }}
  .sector-title {{ font-family:"Playfair Display",serif; font-size:14px; color:#9ca3af; margin-bottom:6px; text-transform:uppercase; letter-spacing:1px; }}
  .sector-tickers {{ display:flex; flex-wrap:wrap; gap:8px; }}
  .ticker-chip {{ display:inline-flex; align-items:center; gap:6px; padding:6px 12px; border:1px solid #374151; border-radius:8px; color:#d1d5db; text-decoration:none; font-size:13px; font-family:"JetBrains Mono",monospace; transition:all 0.2s; }}
  .ticker-chip:hover {{ background:#1f2937; transform:translateY(-1px); }}

  .stock-card {{ background:#0d1117; border-radius:16px; margin-bottom:24px; border:1px solid #1e293b; overflow:hidden; transition:all 0.3s; }}
  .stock-card:hover {{ border-color:#374151; box-shadow:0 4px 24px rgba(0,0,0,0.4); }}

  .kpi {{ background:#111827; border-radius:10px; padding:12px 14px; }}
  .kpi-label {{ display:block; font-size:12px; color:#6b7280; margin-bottom:4px; text-transform:uppercase; letter-spacing:0.5px; }}
  .kpi-val {{ font-family:"JetBrains Mono",monospace; font-size:22px; font-weight:700; color:#f9fafb; }}

  .metric-card {{ background:#111827; border-radius:12px; padding:16px; }}
  .metric-header {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; font-size:15px; color:#d1d5db; font-weight:600; }}
  .metric-sub {{ font-size:12px; color:#6b7280; }}
  .tag {{ padding:3px 10px; border-radius:6px; font-family:"JetBrains Mono",monospace; font-size:13px; font-weight:700; color:#000; }}

  .explainer {{ margin-top:8px; }}
  .explainer summary {{ font-size:12px; color:#6b7280; cursor:pointer; user-select:none; }}
  .explainer summary:hover {{ color:#9ca3af; }}
  .explainer p {{ font-size:12px; color:#6b7280; margin-top:4px; padding:8px; background:#0d1117; border-radius:6px; }}

  .score-row {{ display:flex; align-items:center; gap:12px; margin-bottom:8px; }}
  .score-label {{ font-size:13px; color:#9ca3af; width:160px; flex-shrink:0; }}
  .score-bar-bg {{ flex:1; height:10px; background:#1f2937; border-radius:5px; overflow:hidden; }}
  .score-bar-fill {{ height:100%; border-radius:5px; transition:width 0.5s ease; }}
  .score-num {{ font-family:"JetBrains Mono",monospace; font-size:14px; font-weight:700; color:#f9fafb; width:32px; text-align:right; }}

  .ranking-table {{ width:100%; border-collapse:collapse; border-radius:12px; overflow:hidden; margin-bottom:28px; }}
  .ranking-table th {{ padding:12px; text-align:left; background:#1f2937; color:#9ca3af; font-size:12px; text-transform:uppercase; letter-spacing:0.5px; }}

  .filter-bar {{ display:flex; gap:8px; margin-bottom:20px; flex-wrap:wrap; }}
  .filter-btn {{ padding:8px 16px; border-radius:8px; border:1px solid #374151; background:transparent; color:#9ca3af; font-size:13px; cursor:pointer; transition:all 0.2s; }}
  .filter-btn:hover,.filter-btn.active {{ background:#1f2937; color:#f9fafb; border-color:#6366f1; }}

  @media(max-width:768px) {{
    .kpi-val {{ font-size:18px; }}
    .hero-best-ticker {{ font-size:32px; }}
    h1 {{ font-size:28px; }}
    .stock-card div[style*="grid-template-columns:1fr 1fr"] {{ grid-template-columns:1fr !important; }}
  }}

  @keyframes fadeIn {{ from {{ opacity:0; transform:translateY(10px); }} to {{ opacity:1; transform:translateY(0); }} }}
  .stock-card {{ animation:fadeIn 0.4s ease; }}
</style>
</head>
<body>
<div class="container">
  <h1>Stock Risk Screener</h1>
  <div class="subtitle">Generated {now} &bull; {len(ALL_TICKERS)} stocks &bull; 5 sectors &bull; Scores weighted: Valuation 35% / Health & Growth 35% / Momentum 30%</div>

  <!-- BEST STOCK HERO -->
  {f"""<div class="hero-best">
    <div class="hero-best-title">&#9733; Best Stock to Buy Today</div>
    <div class="hero-best-row">
      <span class="hero-best-ticker">{best["ticker"]}</span>
      <span style="font-size:18px;color:#d1d5db">{best["name"]}</span>
      <span class="hero-best-score" style="margin-left:auto">{best["total_score"]}</span>
      <span style="color:#6b7280;font-size:16px">/100</span>
      <span style="padding:8px 18px;border-radius:24px;font-size:14px;font-weight:700;color:#000;background:{best["badge_color"]}">{best["badge_label"]}</span>
    </div>
    <div style="margin-top:12px;font-size:14px;color:#9ca3af">
      Price: <span style="color:#f9fafb;font-family:JetBrains Mono">{f'${best["price"]:,.2f}' if best["price"] else "N/A"}</span> &bull;
      P/E: <span style="color:#f9fafb;font-family:JetBrains Mono">{fmt_num(best["pe"], decimals=1)}</span> &bull;
      Rev Growth: <span style="color:#f9fafb;font-family:JetBrains Mono">{fmt_pct(best["rev_growth"])}</span> &bull;
      Sector: <span style="color:#f9fafb">{best["sector"]}</span>
    </div>
  </div>""" if best else ""}

  <!-- SECTOR NAV -->
  <div style="margin-bottom:24px">{sector_nav}</div>

  <!-- FILTER BAR -->
  <div class="filter-bar">
    <button class="filter-btn active" onclick="filterCards('all')">All Stocks</button>
    {"".join(f'<button class="filter-btn" onclick="filterCards(&apos;{s}&apos;)">{s}</button>' for s in SECTORS)}
  </div>

  <!-- RANKING TABLE -->
  <table class="ranking-table">
    <thead><tr>
      <th>#</th><th>Ticker</th><th>Name</th><th>Price</th><th>Score</th><th>Rating</th>
    </tr></thead>
    <tbody>{ranking_rows}</tbody>
  </table>

  <!-- STOCK CARDS -->
  <div id="cards-container">{cards_html}</div>

  <div style="text-align:center;padding:40px;color:#374151;font-size:12px">
    Generated by Stock Risk Screener &bull; Data via yfinance &bull; Not financial advice
  </div>
</div>

<script>
const SECTORS = {json.dumps({s: t for s, t in SECTORS.items()})};

function filterCards(sector) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.stock-card').forEach(card => {{
    if (sector === 'all') {{ card.style.display = ''; return; }}
    const ticker = card.id.replace('card-','');
    const tickers = SECTORS[sector] || [];
    card.style.display = tickers.includes(ticker) ? '' : 'none';
  }});
}}

function copyCard(ticker) {{
  const card = document.getElementById('card-' + ticker);
  if (!card) return;
  const text = card.innerText;
  navigator.clipboard.writeText(text).then(() => {{
    const btn = card.querySelector('button');
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 1500);
  }});
}}

document.querySelectorAll('a[href^="#card-"]').forEach(a => {{
  a.addEventListener('click', e => {{
    e.preventDefault();
    const target = document.querySelector(a.getAttribute('href'));
    if (target) target.scrollIntoView({{ behavior:'smooth', block:'start' }});
  }});
}});
</script>
</body>
</html>'''
    return html


def main():
    print("=" * 60)
    print("  STOCK RISK SCREENER")
    print("=" * 60)

    stocks = fetch_all_data()
    medians = compute_sector_medians(stocks)
    stocks = calculate_scores(stocks, medians)

    html = generate_html(stocks)
    out_path = Path(__file__).parent / "dashboard.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\nDashboard saved to: {out_path}")

    sorted_stocks = sorted(stocks.values(), key=lambda s: s.get("total_score", 0), reverse=True)
    print("\n  TOP 5 STOCKS TODAY:")
    print("-" * 50)
    for i, s in enumerate(sorted_stocks[:5]):
        if s["price"]:
            print(f"  #{i+1}  {s['ticker']:6s}  Score: {s['total_score']:3d}  {s['badge_label']:12s}  ${s['price']:>10,.2f}")
        else:
            print(f"  #{i+1}  {s['ticker']:6s}  Score: {s['total_score']:3d}  {s['badge_label']}")
    print()

    data_path = Path(__file__).parent / "stock_data.json"
    export = {t: {k: v for k, v in s.items() if k != "prices_12m"} for t, s in stocks.items()}
    data_path.write_text(json.dumps(export, indent=2, default=str), encoding="utf-8")
    print(f"Data exported to: {data_path}")


if __name__ == "__main__":
    main()
