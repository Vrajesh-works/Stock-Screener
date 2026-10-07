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
    start = end - timedelta(days=6 * 365)
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
            prices_5y_w = []
            dates_5y_w = []
            ohlc_6m = {"o": [], "h": [], "l": [], "c": [], "d": []}
            if len(hist) > 0:
                monthly = hist["Close"].resample("W").last().dropna()
                prices_12m = [round(float(p), 2) for p in monthly.values[-52:]]
                w5 = hist["Close"].resample("W").last().dropna()
                prices_5y_w = [round(float(p), 2) for p in w5.values[-260:]]
                dates_5y_w = [d.strftime("%Y-%m-%d") for d in w5.index[-260:]]
                d6 = hist.tail(130)
                for idx, row in d6.iterrows():
                    o, h, l, c = (safe(row["Open"]), safe(row["High"]),
                                  safe(row["Low"]), safe(row["Close"]))
                    if None in (o, h, l, c):
                        continue
                    ohlc_6m["o"].append(round(o, 2))
                    ohlc_6m["h"].append(round(h, 2))
                    ohlc_6m["l"].append(round(l, 2))
                    ohlc_6m["c"].append(round(c, 2))
                    ohlc_6m["d"].append(idx.strftime("%Y-%m-%d"))
            tgt_mean = safe(info.get("targetMeanPrice"))
            tgt_high = safe(info.get("targetHighPrice"))
            tgt_low = safe(info.get("targetLowPrice"))
            tgt_med = safe(info.get("targetMedianPrice"))
            rec_key = info.get("recommendationKey", "") or ""
            rec_mean = safe(info.get("recommendationMean"))
            num_analysts = safe(info.get("numberOfAnalystOpinions"))

            day_chg = None
            day_chg_pct = None
            if len(hist) > 1:
                _last = float(hist["Close"].iloc[-1])
                _prev = float(hist["Close"].iloc[-2])
                day_chg = _last - _prev
                day_chg_pct = pct(_last, _prev)
            volume = safe(info.get("volume")) or safe(info.get("regularMarketVolume"))
            avg_volume = safe(info.get("averageVolume")) or safe(info.get("averageDailyVolume10Day"))

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
                "day_chg": day_chg,
                "day_chg_pct": day_chg_pct,
                "volume": volume,
                "avg_volume": avg_volume,
                "prices_12m": prices_12m,
                "prices_5y_w": prices_5y_w,
                "dates_5y_w": dates_5y_w,
                "ohlc_6m": ohlc_6m,
                "tgt_mean": tgt_mean,
                "tgt_high": tgt_high,
                "tgt_low": tgt_low,
                "tgt_med": tgt_med,
                "rec_key": rec_key,
                "rec_mean": rec_mean,
                "num_analysts": num_analysts,
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
                "day_chg": None, "day_chg_pct": None,
                "volume": None, "avg_volume": None,
                "prices_12m": [], "prices_5y_w": [], "dates_5y_w": [],
                "ohlc_6m": {"o": [], "h": [], "l": [], "c": [], "d": []},
                "tgt_mean": None, "tgt_high": None, "tgt_low": None,
                "tgt_med": None, "rec_key": "", "rec_mean": None,
                "num_analysts": None, "quarterly": [],
            }
    return stocks


def fetch_indices():
    print("Fetching market indices...")
    out = {}
    for sym, name in [("^GSPC", "SPX"), ("^IXIC", "CCMP"), ("^DJI", "INDU"), ("^RUT", "RTY"), ("^VIX", "VIX")]:
        try:
            h = yf.Ticker(sym).history(period="5d")
            if len(h) >= 2:
                last = float(h["Close"].iloc[-1])
                prev = float(h["Close"].iloc[-2])
                out[name] = {"price": last, "chg": last - prev, "chg_pct": pct(last, prev)}
            elif len(h) == 1:
                out[name] = {"price": float(h["Close"].iloc[-1]), "chg": 0.0, "chg_pct": 0.0}
            print(f"  {name}... OK")
        except Exception as e:
            print(f"  {name}... ERROR: {e}")
    return out


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


TERM_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
:root{--amber:#ffa02f;--amber-dk:#6e4a15;--up:#3ddc84;--dn:#ff5252;--tx:#d8d8d8;--dim:#7c7c7c;--line:#1b1b1b;--panel:#050505}
html{background:#000}
body{background:#000;color:var(--tx);font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px;line-height:1.45;-webkit-font-smoothing:antialiased}
a{color:var(--amber)}
.term-top{background:var(--amber);color:#000;font-weight:700;padding:6px 14px;display:flex;justify-content:space-between;align-items:center;font-size:13px;letter-spacing:1px}
.term-top .rt{font-weight:400;font-size:12px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#000;margin-right:6px;animation:blink 1.6s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}
.tape-wrap{border-bottom:1px solid var(--amber-dk);overflow:hidden;white-space:nowrap;background:#000}
.tape{display:inline-block;padding:6px 0;animation:tape 70s linear infinite;will-change:transform}
.tape-wrap:hover .tape{animation-play-state:paused}
@keyframes tape{from{transform:translateX(0)}to{transform:translateX(-50%)}}
.titem{display:inline-block;padding:0 20px;border-right:1px solid var(--line);font-size:12px}
.titem b{color:var(--amber)}
.mkt{display:flex;border-bottom:1px solid var(--line);background:var(--panel);flex-wrap:wrap}
.mcell{padding:8px 18px;border-right:1px solid var(--line);font-size:12px}
.mcell .n{color:var(--dim);font-size:10px;letter-spacing:1px;display:block}
.mcell .p{font-size:15px;font-weight:700}
.funcbar{display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid var(--line);background:#000;position:sticky;top:0;z-index:20;flex-wrap:wrap}
.fbtn{background:#000;border:1px solid var(--amber-dk);color:var(--amber);padding:6px 14px;cursor:pointer;font:inherit;font-size:12px;letter-spacing:1px}
.fbtn.on,.fbtn:hover{background:var(--amber);color:#000;font-weight:700}
.fkey{opacity:.6;margin-right:6px}
.search{margin-left:auto;background:#050505;border:1px solid var(--line);color:var(--tx);padding:7px 12px;font:inherit;font-size:12px;width:280px}
.search:focus{outline:none;border-color:var(--amber-dk)}
.wrap{padding:0 14px 60px;max-width:1560px;margin:0 auto}
table.blot{width:100%;border-collapse:collapse;font-size:12px}
table.blot thead th{position:sticky;top:53px;background:#0a0a0a;color:var(--amber);text-align:right;padding:9px 10px;border-bottom:1px solid var(--amber-dk);white-space:nowrap;font-weight:700;font-size:11px;letter-spacing:1px;cursor:pointer;z-index:10}
table.blot thead th.l,table.blot td.l{text-align:left}
table.blot thead th:hover{color:#fff}
table.blot td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
table.blot tbody tr{cursor:pointer}
table.blot tbody tr:hover{background:#101010}
.ticker{color:var(--amber);font-weight:700}
.up{color:var(--up)}.dn{color:var(--dn)}.dim{color:var(--dim)}
.sect-hd td{background:#0a0a0a!important;color:var(--amber);font-weight:700;letter-spacing:2px;font-size:11px;cursor:default!important}
.rtg{font-weight:700;padding:2px 8px;border:1px solid currentColor;font-size:11px;white-space:nowrap}
.sect-block{margin:18px 0 28px;border:1px solid var(--line)}
.sect-block-h{background:#0a0a0a;color:var(--amber);padding:8px 14px;font-weight:700;letter-spacing:2px;font-size:12px;border-bottom:1px solid var(--line)}
.chips{display:flex;flex-wrap:wrap;gap:8px;padding:14px}
.chip{border:1px solid var(--amber-dk);padding:8px 12px;cursor:pointer;font-size:12px;background:#000}
.chip:hover{background:#141414}
.chip b{color:var(--amber);margin-right:8px}
.chip .sc{font-weight:700}
.pick{display:grid;grid-template-columns:44px 90px 1fr 220px 130px 90px;gap:12px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--line);cursor:pointer}
.pick:hover{background:#101010}
.pick .rk{color:var(--dim);font-size:12px}
.bar{height:10px;background:#161616;position:relative}
.bar i{position:absolute;left:0;top:0;bottom:0;background:var(--amber)}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.94);z-index:50;overflow:auto;padding:28px 16px;display:none}
.dpanel{max-width:1120px;margin:0 auto;background:#000;border:1px solid var(--amber-dk);display:none}
.d-head{background:var(--amber);color:#000;padding:9px 16px;font-weight:700;display:flex;gap:14px;align-items:baseline;font-size:15px}
.d-head .nm{font-weight:400;font-size:12px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.d-head button{background:#000;color:var(--amber);border:none;font:inherit;font-weight:700;padding:4px 14px;cursor:pointer}
.d-sec{border-bottom:1px solid var(--line);padding:16px}
.d-sec-t{color:var(--amber);font-size:11px;letter-spacing:2px;margin-bottom:12px;font-weight:700}
.d-price{font-size:30px;font-weight:700}
.d-price .chg{font-size:16px;margin-left:12px}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:1px;background:var(--line);border:1px solid var(--line)}
.stat{background:#000;padding:9px 12px}
.stat .k{font-size:10px;color:var(--dim);letter-spacing:1px}
.stat .v{font-size:14px;font-weight:700;margin-top:2px}
.mrow{display:grid;grid-template-columns:170px 1fr 52px;gap:12px;align-items:center;margin-bottom:10px;font-size:12px}
.mrow .bl{color:var(--dim)}
.mbar{height:12px;background:#141414;position:relative}
.mbar i{position:absolute;left:0;top:0;bottom:0}
.mrow .nv{text-align:right;font-weight:700}
.d2{display:grid;grid-template-columns:1fr 1fr;gap:0;border:1px solid var(--line)}
.d2>div{padding:14px}
.d2>div:first-child{border-right:1px solid var(--line)}
.ci{border:1px solid var(--line);padding:8px 12px;margin-bottom:8px;font-size:12px;display:flex;justify-content:space-between;gap:10px}
.ci .sev{font-size:10px;letter-spacing:1px;flex-shrink:0}
table.q{width:100%;border-collapse:collapse;font-size:12px}
table.q th{text-align:left;color:var(--dim);font-size:10px;letter-spacing:1px;padding:8px 10px;border-bottom:1px solid var(--line);font-weight:400}
table.q td{padding:8px 10px;border-bottom:1px solid var(--line)}
.verdict{border-left:3px solid var(--amber);padding:4px 0 4px 14px;font-size:13px;line-height:1.7}
.statusbar{position:fixed;left:0;right:0;bottom:0;background:#0a0a0a;border-top:1px solid var(--amber-dk);color:var(--dim);font-size:11px;padding:6px 14px;display:flex;justify-content:space-between;z-index:40}
.statusbar b{color:var(--amber);font-weight:400}
.hint{color:var(--dim);font-size:11px;padding:10px 0}
@media(max-width:900px){.d2{grid-template-columns:1fr}.d2>div:first-child{border-right:none;border-bottom:1px solid var(--line)}.pick{grid-template-columns:36px 70px 1fr 90px}}

.filterbar{display:flex;align-items:center;gap:14px;padding:8px 14px;border-bottom:1px solid var(--line);background:#050505;flex-wrap:wrap;font-size:11px}
.fb-t{color:var(--amber);letter-spacing:2px;font-size:10px;font-weight:700}
.filterbar label{color:var(--dim);display:flex;align-items:center;gap:6px;white-space:nowrap}
.filterbar input[type=number]{width:64px;background:#000;border:1px solid var(--line);color:var(--tx);padding:5px 8px;font:inherit;font-size:11px}
.filterbar input:focus{outline:none;border-color:var(--amber-dk)}
.filterbar select{background:#000;border:1px solid var(--line);color:var(--tx);padding:5px 8px;font:inherit;font-size:11px}
#f-count{margin-left:auto;letter-spacing:1px}
.chartctl{display:flex;gap:6px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
.cbtn{background:#000;border:1px solid var(--line);color:var(--dim);padding:4px 12px;cursor:pointer;font:inherit;font-size:11px;letter-spacing:1px}
.cbtn.on,.cbtn:hover{border-color:var(--amber);color:var(--amber)}
.chartbox{background:#050505;border:1px solid var(--line);padding:10px;margin-bottom:6px}
.cmpchk{accent-color:var(--amber);cursor:pointer;width:14px;height:14px}
.fbtn:disabled{opacity:.35;cursor:not-allowed}
.fbtn:disabled:hover{background:#000;color:var(--amber)}
.an-bar{position:relative;height:14px;background:#141414;margin:12px 0 6px}
.an-bar .zone{position:absolute;top:0;bottom:0;background:#1e2a1e;border-left:1px solid #3ddc84;border-right:1px solid #3ddc84}
.an-bar .mk{position:absolute;top:-4px;width:2px;height:22px;background:var(--amber)}
.an-bar .mk span{position:absolute;top:-16px;left:-14px;font-size:10px;color:var(--amber);white-space:nowrap}
.an-bar .px{position:absolute;top:-4px;width:2px;height:22px;background:#fff}
.an-bar .px span{position:absolute;top:20px;left:-14px;font-size:10px;color:#fff;white-space:nowrap}
.an-meta{display:flex;gap:24px;flex-wrap:wrap;font-size:12px;color:var(--dim)}
.an-meta b{color:var(--tx)}
#cmp-ovl .dpanel{max-width:1240px}
.cmp-grid{display:grid;grid-template-columns:180px repeat(4,1fr);gap:1px;background:var(--line);border:1px solid var(--line);font-size:12px}
.cmp-grid>div{background:#000;padding:9px 12px}
.cmp-grid .ch{background:#0a0a0a;color:var(--amber);font-weight:700}
.cmp-grid .rl{color:var(--dim)}
#cmp-legend{display:flex;gap:18px;margin-top:8px;font-size:12px;flex-wrap:wrap}
#cmp-legend i{display:inline-block;width:18px;height:3px;margin-right:6px;vertical-align:middle}
"""

TERM_JS = """
function tab(n){
  ['all','top','sec'].forEach(function(t){
    document.getElementById('tab-'+t).style.display = t===n?'':'none';
  });
  document.querySelectorAll('.fbtn').forEach(function(b){
    b.classList.toggle('on', b.dataset.tab===n);
  });
}
document.addEventListener('keydown',function(e){
  if(e.key==='1')tab('all');
  else if(e.key==='2')tab('top');
  else if(e.key==='3')tab('sec');
  else if(e.key==='Escape')closeD();
  else if(e.key==='/'){e.preventDefault();document.getElementById('q').focus();}
});
var sortDir={};
function sortBy(th){
  var i=+th.dataset.i, type=th.dataset.t, tb=document.getElementById('blot-body');
  var rows=Array.prototype.slice.call(tb.rows);
  var dir=sortDir[i]==='a'?'d':'a'; sortDir[i]=dir;
  rows.sort(function(a,b){
    var av=a.cells[i].dataset.v, bv=b.cells[i].dataset.v;
    var c = type==='n' ? (parseFloat(av)-parseFloat(bv)) : (''+av).localeCompare(''+bv);
    return dir==='a'?c:-c;
  });
  rows.forEach(function(r){tb.appendChild(r);});
  document.querySelectorAll('#blot-head th').forEach(function(h){h.textContent=h.textContent.replace(/ [▲▼]$/,'');});
  th.textContent+=' '+(dir==='a'?'▲':'▼');
}
function openD(t){
  document.getElementById('ovl').style.display='block';
  document.querySelectorAll('.dpanel').forEach(function(p){p.style.display='none';});
  var p=document.getElementById('d-'+t);
  if(p){p.style.display='block';}
  document.getElementById('ovl').scrollTop=0;
}
function closeD(){document.getElementById('ovl').style.display='none';}
document.getElementById('ovl').addEventListener('click',function(e){if(e.target===this)closeD();});
document.getElementById('q').addEventListener('input',function(e){
  var q=e.target.value.trim().toUpperCase();
  document.querySelectorAll('#blot-body tr').forEach(function(r){
    if(r.className==='sect-hd')return;
    var t=(r.dataset.ticker||'')+' '+(r.dataset.name||'');
    r.style.display = !q || t.toUpperCase().indexOf(q)>=0 ? '' : 'none';
  });
});
function tick(){
  var d=new Date();
  var el=document.getElementById('clock');
  if(el){el.textContent=('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2)+':'+('0'+d.getSeconds()).slice(-2);}
}
setInterval(tick,1000);tick();

var chartState={};
function chartInit(t){ if(!chartState[t]) chartState[t]={range:'1Y',type:'line'}; }
function setRange(t,r){ chartInit(t); var st=chartState[t]; st.range=r;
  if(st.type==='candle'&&(r==='1Y'||r==='5Y')) st.range='6M';
  syncChartBtns(t); renderChart(t); }
function setType(t,ty){ chartInit(t); var st=chartState[t]; st.type=ty;
  if(ty==='candle'&&(st.range==='1Y'||st.range==='5Y')) st.range='6M';
  syncChartBtns(t); renderChart(t); }
function syncChartBtns(t){ var st=chartState[t]||{range:'1Y',type:'line'};
  var p=document.getElementById('d-'+t); if(!p) return;
  Array.prototype.forEach.call(p.querySelectorAll('.cbtn[data-r]'),function(b){ b.classList.toggle('on',b.dataset.r===st.range); });
  Array.prototype.forEach.call(p.querySelectorAll('.cbtn[data-ty]'),function(b){ b.classList.toggle('on',b.dataset.ty===st.type); });
}
function lineSeries(D,range){
  if(range==='1M') return {v:D.cc.slice(-22),l:D.cd.slice(-22)};
  if(range==='3M') return {v:D.cc.slice(-66),l:D.cd.slice(-66)};
  if(range==='6M') return {v:D.cc.slice(-126),l:D.cd.slice(-126)};
  if(range==='1Y') return {v:D.w.slice(-52),l:D.wd.slice(-52)};
  return {v:D.w,l:D.wd};
}
function candleSlices(D,range){
  var n=range==='1M'?22:range==='3M'?66:126;
  return {o:D.co.slice(-n),h:D.ch.slice(-n),l:D.cl.slice(-n),c:D.cc.slice(-n),d:D.cd.slice(-n)};
}
function renderChart(t){
  chartInit(t);
  var D=CHARTS[t]; if(!D) return;
  var box=document.getElementById('ch-'+t); if(!box) return;
  var st=chartState[t], W=1000,H=240,pl=8,pr=72,pt=26,pb=22,iw=W-pl-pr,ih=H-pt-pb;
  function yOf(v,mn,rng){ return pt+ih-((v-mn)/rng)*ih; }
  var grid='';
  for(var g=0;g<5;g++){ var gy=(pt+ih*g/4).toFixed(1);
    grid+='<line x1="'+pl+'" y1="'+gy+'" x2="'+(pl+iw)+'" y2="'+gy+'" stroke="#1b1b1b" stroke-width="1"/>'; }
  var body='',hiLbl='',loLbl='',xLbl='';
  if(st.type==='line'){
    var s=lineSeries(D,st.range),vals=s.v,labels=s.l;
    if(!vals||vals.length<2){ box.innerHTML='<div class="dim">NO DATA</div>'; return; }
    var mn=Math.min.apply(null,vals),mx=Math.max.apply(null,vals),rng=(mx-mn)||1;
    var pts=vals.map(function(v,i){ return (pl+(i/(vals.length-1))*iw).toFixed(1)+','+yOf(v,mn,rng).toFixed(1); });
    var line='M'+pts.join('L');
    var area=line+'L'+(pl+iw).toFixed(1)+','+(pt+ih).toFixed(1)+'L'+pl.toFixed(1)+','+(pt+ih).toFixed(1)+'Z';
    var up=vals[vals.length-1]>=vals[0],c=up?'#ffa02f':'#ff5252';
    body='<path d="'+area+'" fill="'+c+'" opacity="0.08"/><path d="'+line+'" fill="none" stroke="'+c+'" stroke-width="2"/>';
    hiLbl='<text x="'+(pl+iw+6)+'" y="'+(yOf(mx,mn,rng)+4).toFixed(1)+'" fill="#7c7c7c" font-size="11" font-family="monospace">$'+mx.toFixed(0)+'</text>';
    loLbl='<text x="'+(pl+iw+6)+'" y="'+(yOf(mn,mn,rng)+4).toFixed(1)+'" fill="#7c7c7c" font-size="11" font-family="monospace">$'+mn.toFixed(0)+'</text>';
    xLbl='<text x="'+pl+'" y="'+(H-6)+'" fill="#7c7c7c" font-size="11" font-family="monospace">'+labels[0]+'</text><text x="'+(pl+iw)+'" y="'+(H-6)+'" fill="#7c7c7c" font-size="11" font-family="monospace" text-anchor="end">'+labels[labels.length-1]+'</text>';
  } else {
    var k=candleSlices(D,st.range),n=k.c.length;
    if(n<2){ box.innerHTML='<div class="dim">NO DATA</div>'; return; }
    var all=k.h.concat(k.l),mn2=Math.min.apply(null,all),mx2=Math.max.apply(null,all),rng2=(mx2-mn2)||1;
    var cw=iw/n,bw=Math.max(1.5,cw*0.55);
    for(var i=0;i<n;i++){
      var x=pl+i*cw+cw/2,yo=yOf(k.o[i],mn2,rng2),yc=yOf(k.c[i],mn2,rng2),yh=yOf(k.h[i],mn2,rng2),yl=yOf(k.l[i],mn2,rng2);
      var upc=k.c[i]>=k.o[i],cc=upc?'#3ddc84':'#ff5252',top=Math.min(yo,yc),hh=Math.max(1,Math.abs(yo-yc));
      body+='<line x1="'+x.toFixed(1)+'" y1="'+yh.toFixed(1)+'" x2="'+x.toFixed(1)+'" y2="'+yl.toFixed(1)+'" stroke="'+cc+'" stroke-width="1"/>';
      body+='<rect x="'+(x-bw/2).toFixed(1)+'" y="'+top.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+hh.toFixed(1)+'" fill="'+cc+'"/>';
    }
    hiLbl='<text x="'+(pl+iw+6)+'" y="'+(yOf(mx2,mn2,rng2)+4).toFixed(1)+'" fill="#7c7c7c" font-size="11" font-family="monospace">$'+mx2.toFixed(0)+'</text>';
    loLbl='<text x="'+(pl+iw+6)+'" y="'+(yOf(mn2,mn2,rng2)+4).toFixed(1)+'" fill="#7c7c7c" font-size="11" font-family="monospace">$'+mn2.toFixed(0)+'</text>';
    xLbl='<text x="'+pl+'" y="'+(H-6)+'" fill="#7c7c7c" font-size="11" font-family="monospace">'+k.d[0]+'</text><text x="'+(pl+iw)+'" y="'+(H-6)+'" fill="#7c7c7c" font-size="11" font-family="monospace" text-anchor="end">'+k.d[n-1]+'</text>';
  }
  box.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto;display:block">'+grid+body+hiLbl+loLbl+xLbl+'</svg>';
}
var _openD=openD;
openD=function(t){ _openD(t); chartInit(t); syncChartBtns(t); renderChart(t); };
(function(){ var o=document.getElementById('q'); if(o){ var n=o.cloneNode(true); o.parentNode.replaceChild(n,o);
  n.addEventListener('input',refreshRows); } })();
function refreshRows(){
  var q=document.getElementById('q').value.trim().toUpperCase();
  var minS=parseFloat(document.getElementById('f-score').value)||0;
  var maxPE=parseFloat(document.getElementById('f-pe').value);
  var minMC=parseFloat(document.getElementById('f-mcap').value);
  var minDV=parseFloat(document.getElementById('f-div').value);
  var sec=document.getElementById('f-sec').value, rat=document.getElementById('f-rat').value;
  var vis=0;
  Array.prototype.forEach.call(document.querySelectorAll('#blot-body tr[data-ticker]'),function(r){
    var show=true, txt=((r.dataset.ticker||'')+' '+(r.dataset.name||'')).toUpperCase();
    if(q&&txt.indexOf(q)<0) show=false;
    if(parseFloat(r.dataset.score)<minS) show=false;
    if(!isNaN(maxPE)){ var pe=parseFloat(r.dataset.pe); if(isNaN(pe)||pe>maxPE) show=false; }
    if(!isNaN(minMC)){ var mc=parseFloat(r.dataset.mcap); if(isNaN(mc)||mc<minMC*1e9) show=false; }
    if(!isNaN(minDV)){ var dv=parseFloat(r.dataset.div); if(isNaN(dv)||dv<minDV) show=false; }
    if(sec&&r.dataset.sector!==sec) show=false;
    if(rat&&r.dataset.rating!==rat) show=false;
    r.style.display=show?'':'none'; if(show) vis++;
  });
  Array.prototype.forEach.call(document.querySelectorAll('#blot-body tr.sect-hd'),function(h){
    var n=h.nextElementSibling,any=false;
    while(n&&!n.classList.contains('sect-hd')){ if(n.style.display!=='none') any=true; n=n.nextElementSibling; }
    h.style.display=any?'':'none';
  });
  document.getElementById('f-count').textContent=vis+' SHOWN';
}
function resetFilters(){
  document.getElementById('f-score').value='0';
  ['f-pe','f-mcap','f-div'].forEach(function(id){ document.getElementById(id).value=''; });
  document.getElementById('f-sec').value=''; document.getElementById('f-rat').value='';
  document.getElementById('q').value=''; refreshRows();
}
var compareSet=[];
function toggleCmp(t,cb){
  if(cb.checked){ if(compareSet.indexOf(t)<0&&compareSet.length<4) compareSet.push(t); else cb.checked=false; }
  else compareSet=compareSet.filter(function(x){ return x!==t; });
  updateCmpBtn();
}
function updateCmpBtn(){ var b=document.getElementById('cmp-btn');
  b.textContent='COMPARE ('+compareSet.length+')'; b.disabled=compareSet.length<2; }
function jfmt(v,dec){ if(v==null||isNaN(v)) return 'N/A'; return (+v).toFixed(dec==null?2:dec); }
function jmcap(v){ if(v==null||isNaN(v)) return 'N/A'; if(v>=1e12) return '$'+(v/1e12).toFixed(1)+'T';
  if(v>=1e9) return '$'+(v/1e9).toFixed(1)+'B'; if(v>=1e6) return '$'+(v/1e6).toFixed(1)+'M'; return '$'+(+v).toFixed(0); }
function openCmp(){
  if(compareSet.length<2) return;
  var cols=['#ffa02f','#3ddc84','#ff5252','#6aa8ff'];
  document.getElementById('cmp-tickers').textContent=compareSet.join('  vs  ');
  var W=1000,H=260,pl=8,pr=70,pt=26,pb=22,iw=W-pl-pr,ih=H-pt-pb;
  var series=compareSet.map(function(t){ var w=(CHARTS[t]||{}).w||[]; var b=w[0]||1;
    return {t:t,w:w.map(function(v){ return v/b*100; }),d:(CHARTS[t]||{}).wd||[]}; });
  var gmin=Infinity,gmax=-Infinity;
  series.forEach(function(s){ s.w.forEach(function(v){ if(v<gmin)gmin=v; if(v>gmax)gmax=v; }); });
  var grng=(gmax-gmin)||1, pad=grng*0.08; gmin-=pad; gmax+=pad; grng=(gmax-gmin)||1;
  function yy(v){ return pt+ih-((v-gmin)/grng)*ih; }
  var grid='';
  for(var g=0;g<5;g++){ var gy=(pt+ih*g/4).toFixed(1);
    grid+='<line x1="'+pl+'" y1="'+gy+'" x2="'+(pl+iw)+'" y2="'+gy+'" stroke="#1b1b1b" stroke-width="1"/>'; }
  var paths='',legend='';
  series.forEach(function(s,i){
    if(!s.w.length) return;
    var pts=s.w.map(function(v,j){ return (pl+(j/(s.w.length-1))*iw).toFixed(1)+','+yy(v).toFixed(1); });
    paths+='<path d="M'+pts.join('L')+'" fill="none" stroke="'+cols[i]+'" stroke-width="2"/>';
    legend+='<span><i style="background:'+cols[i]+'"></i>'+s.t+'</span>';
  });
  var d0=(series[0]&&series[0].d[0])||'',d1=(series[0]&&series[0].d[series[0].d.length-1])||'';
  var svg='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto;display:block">'+grid+paths
    +'<text x="'+pl+'" y="'+(H-6)+'" fill="#7c7c7c" font-size="11" font-family="monospace">'+d0+'</text>'
    +'<text x="'+(pl+iw)+'" y="'+(H-6)+'" fill="#7c7c7c" font-size="11" font-family="monospace" text-anchor="end">'+d1+'</text></svg>';
  document.getElementById('cmp-chart').innerHTML=svg;
  document.getElementById('cmp-legend').innerHTML=legend;
  var rows=[['LAST',function(m){return m.price!=null?'$'+(+m.price).toFixed(2):'N/A';}],
    ['DAY CHG %',function(m){return m.chgp!=null?(+m.chgp).toFixed(2)+'%':'N/A';}],
    ['MKT CAP',function(m){return jmcap(m.mcap);}],
    ['P/E',function(m){return jfmt(m.pe,1);}],
    ['DIV YLD %',function(m){return jfmt(m.div,2);}],
    ['52W HIGH',function(m){return m.hi!=null?'$'+(+m.hi).toFixed(0):'N/A';}],
    ['52W LOW',function(m){return m.lo!=null?'$'+(+m.lo).toFixed(0):'N/A';}],
    ['VAL SCORE',function(m){return jfmt(m.vs,0);}],
    ['HLTH SCORE',function(m){return jfmt(m.hs,0);}],
    ['MOM SCORE',function(m){return jfmt(m.ms,0);}],
    ['TOTAL',function(m){return jfmt(m.ts,0);}],
    ['RATING',function(m){return m.badge||'N/A';}]];
  var html='<div class="cmp-grid"><div class="ch">METRIC</div>'+compareSet.map(function(t){return '<div class="ch">'+t+'</div>';}).join('')+'</div>';
  rows.forEach(function(r){
    html+='<div class="cmp-grid"><div class="rl">'+r[0]+'</div>'+compareSet.map(function(t){return '<div>'+r[1](META[t]||{})+'</div>';}).join('')+'</div>';
  });
  document.getElementById('cmp-table').innerHTML=html;
  document.getElementById('cmp-ovl').style.display='block';
}
function closeCmp(){ document.getElementById('cmp-ovl').style.display='none'; }
document.getElementById('cmp-ovl').addEventListener('click',function(e){ if(e.target===this) closeCmp(); });
document.addEventListener('keydown',function(e){ if(e.key==='Escape') closeCmp(); });
function exportCSV(){
  var head=['Ticker','Name','Sector','Price','DayChg','DayChgPct','MktCap','PE','DivYldPct','High52','Low52','Score','Rating'];
  function q(s){ s=''+(s==null?'':s); return '"'+s.replace(/"/g,'""')+'"'; }
  var lines=[head.join(',')];
  Array.prototype.forEach.call(document.querySelectorAll('#blot-body tr[data-ticker]'),function(r){
    if(r.style.display==='none') return;
    var c=r.cells;
    lines.push([q(r.dataset.ticker),q(r.dataset.name),q(r.dataset.sector),
      c[3].dataset.v,c[4].dataset.v,c[5].dataset.v,c[7].dataset.v,c[8].dataset.v,
      r.dataset.div,r.dataset.hi,r.dataset.lo,r.dataset.score,q(r.dataset.rating)].join(','));
  });
  var a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([lines.join('\\n')],{type:'text/csv'}));
  a.download='equity-screener.csv'; document.body.appendChild(a); a.click(); a.remove();
}
async function fetchCustom(sym,silent){
  if(document.querySelector('#blot-body tr[data-ticker="'+sym+'"]')){ if(!silent) alert(sym+' is already on the board.'); return; }
  try{
    var qtxt=await (await fetch('https://stooq.com/q/l/?s='+encodeURIComponent(sym.toLowerCase()+'.us')+'&f=sd2t2ohlcv&h&e=csv')).text();
    var qp=qtxt.trim().split('\\n');
    if(qp.length<2) throw new Error('no quote');
    var qr=qp[1].split(','),close=parseFloat(qr[6]);
    if(!close||isNaN(close)) throw new Error('no quote');
    var open=parseFloat(qr[3]),vol=parseFloat(qr[7])||0;
    var htxt=await (await fetch('https://stooq.com/q/d/l/?s='+encodeURIComponent(sym.toLowerCase()+'.us')+'&i=d')).text();
    var lines=htxt.trim().split('\\n').slice(1).filter(function(l){ var p=l.split(','); return p.length>=6&&p[4].indexOf('N/D')<0; });
    if(lines.length<10) throw new Error('no history');
    var o=[],h=[],l=[],c=[],d=[];
    lines.forEach(function(ln){ var p=ln.split(','); o.push(+p[1]); h.push(+p[2]); l.push(+p[3]); c.push(+p[4]); d.push(p[0]); });
    var tail=c.slice(-260),hi=Math.max.apply(null,tail),lo=Math.min.apply(null,tail);
    var chg=close-open, chgp=open?chg/open*100:0;
    CHARTS[sym]={w:c.slice(-260),wd:d.slice(-260),co:o.slice(-130),ch:h.slice(-130),cl:l.slice(-130),cc:c.slice(-130),cd:d.slice(-130)};
    META[sym]={name:sym,sector:'CUSTOM',price:close,chgp:chgp,mcap:NaN,pe:NaN,div:NaN,hi:hi,lo:lo,vs:NaN,hs:NaN,ms:NaN,ts:NaN,badge:'CUSTOM'};
    insertCustomRow(sym,close,chg,chgp,vol,hi,lo,c.slice(-52));
    document.getElementById('ovl').insertAdjacentHTML('beforeend',customPanel(sym,close,chg,chgp,vol,hi,lo));
    var saved=[]; try{ saved=JSON.parse(localStorage.getItem('et_custom')||'[]'); }catch(e){}
    if(saved.indexOf(sym)<0){ saved.push(sym); try{ localStorage.setItem('et_custom',JSON.stringify(saved)); }catch(e){} }
    refreshRows();
  }catch(e){ if(!silent) alert('Could not fetch '+sym+'. Check the symbol (US-listed stocks).'); }
}
function addTicker(){ var v=document.getElementById('add-t').value.trim().toUpperCase().replace(/[^A-Z.]/g,'');
  document.getElementById('add-t').value=''; if(v) fetchCustom(v,false); }
document.getElementById('add-t').addEventListener('keydown',function(e){ if(e.key==='Enter') addTicker(); e.stopPropagation(); });
function sparkMini(vals){
  if(!vals||vals.length<2) return '';
  var mn=Math.min.apply(null,vals),mx=Math.max.apply(null,vals),rng=(mx-mn)||1,w=110,hh=26;
  var pts=vals.map(function(v,i){ return (2+(i/(vals.length-1))*(w-4)).toFixed(1)+','+(2+(hh-4)-((v-mn)/rng)*(hh-4)).toFixed(1); });
  var up=vals[vals.length-1]>=vals[0],cc=up?'#3ddc84':'#ff5252';
  return '<svg width="'+w+'" height="'+hh+'" viewBox="0 0 '+w+' '+hh+'"><polyline points="'+pts.join(' ')+'" fill="none" stroke="'+cc+'" stroke-width="1.5"/></svg>';
}
function insertCustomRow(sym,price,chg,chgp,vol,hi,lo,spark){
  var tb=document.getElementById('blot-body');
  if(!document.getElementById('sect-custom')){
    tb.insertAdjacentHTML('afterbegin','<tr class="sect-hd" id="sect-custom"><td class="l" colspan="14">▸ CUSTOM</td></tr>');
  }
  var cls=chgp>0?'up':chgp<0?'dn':'dim',tri=chgp>0?'▲':chgp<0?'▼':'';
  var html='<tr data-ticker="'+sym+'" data-name="'+sym+'" data-sector="CUSTOM" data-rating="CUSTOM" data-score="0" data-pe="" data-mcap="" data-div="" data-hi="'+hi.toFixed(0)+'" data-lo="'+lo.toFixed(0)+'" onclick="openD(\\''+sym+'\\')">'
    +'<td class="l"><input type="checkbox" class="cmpchk" onclick="event.stopPropagation();toggleCmp(\\''+sym+'\\',this)"></td>'
    +'<td class="l"><span class="ticker">'+sym+'</span></td><td class="l dim">'+sym+'</td>'
    +'<td data-v="'+price+'">'+price.toFixed(2)+'</td>'
    +'<td data-v="'+chg+'" class="'+cls+'">'+(chg>=0?'+':'')+chg.toFixed(2)+'</td>'
    +'<td data-v="'+chgp+'" class="'+cls+'">'+tri+' '+(chgp>=0?'+':'')+chgp.toFixed(2)+'%</td>'
    +'<td>'+sparkMini(spark)+'</td><td data-v="-1" class="dim">N/A</td><td data-v="9999" class="dim">N/A</td>'
    +'<td class="dim">'+hi.toFixed(0)+'</td><td class="dim">'+lo.toFixed(0)+'</td>'
    +'<td data-v="0" class="dim">-</td><td class="l"><span class="rtg" style="color:#7c7c7c">CUSTOM</span></td></tr>';
  document.getElementById('sect-custom').insertAdjacentHTML('afterend',html);
}
function customPanel(sym,price,chg,chgp,vol,hi,lo){
  var cls=chgp>0?'up':chgp<0?'dn':'dim';
  return '<div class="dpanel" id="d-'+sym+'">'
    +'<div class="d-head"><span>'+sym+'</span><span class="nm">CUSTOM TICKER - LIVE VIA STOOQ</span><button onclick="closeD()">ESC</button></div>'
    +'<div class="d-sec"><div class="d-price">'+price.toFixed(2)+'<span class="chg '+cls+'">'+(chg>=0?'+':'')+chg.toFixed(2)+' ('+(chgp>=0?'+':'')+chgp.toFixed(2)+'%)</span></div>'
    +'<div class="hint">FUNDAMENTALS NOT AVAILABLE FOR CUSTOM TICKERS - PRICE DATA ONLY</div>'
    +'<div class="chartctl"><button class="cbtn" data-r="1M" onclick="setRange(\\''+sym+'\\',\\'1M\\')">1M</button>'
    +'<button class="cbtn" data-r="3M" onclick="setRange(\\''+sym+'\\',\\'3M\\')">3M</button>'
    +'<button class="cbtn" data-r="6M" onclick="setRange(\\''+sym+'\\',\\'6M\\')">6M</button>'
    +'<button class="cbtn on" data-r="1Y" onclick="setRange(\\''+sym+'\\',\\'1Y\\')">1Y</button>'
    +'<button class="cbtn" data-r="5Y" onclick="setRange(\\''+sym+'\\',\\'5Y\\')">5Y</button>'
    +'<span class="dim" style="margin:0 8px">|</span>'
    +'<button class="cbtn on" data-ty="line" onclick="setType(\\''+sym+'\\',\\'line\\')">LINE</button>'
    +'<button class="cbtn" data-ty="candle" onclick="setType(\\''+sym+'\\',\\'candle\\')">CANDLES</button></div>'
    +'<div class="chartbox" id="ch-'+sym+'"></div></div>'
    +'<div class="d-sec"><div class="d-sec-t">PRICE STATISTICS</div><div class="stat-grid">'
    +'<div class="stat"><div class="k">VOLUME</div><div class="v">'+(vol>=1e6?(vol/1e6).toFixed(1)+'M':Math.round(vol))+'</div></div>'
    +'<div class="stat"><div class="k">52W HIGH</div><div class="v">$'+hi.toFixed(0)+'</div></div>'
    +'<div class="stat"><div class="k">52W LOW</div><div class="v">$'+lo.toFixed(0)+'</div></div>'
    +'</div></div></div>';
}
(function(){ var saved=[]; try{ saved=JSON.parse(localStorage.getItem('et_custom')||'[]'); }catch(e){}
  saved.forEach(function(s){ fetchCustom(s,true); }); })();
"""


def fmt_chg(v, decimals=2):
    if v is None:
        return "N/A"
    return f"{v:+.{decimals}f}%"


def chg_cls(v):
    if v is None:
        return "dim"
    return "up" if v > 0 else "dn" if v < 0 else "dim"


def tri(v):
    if v is None or v == 0:
        return ""
    return "▲" if v > 0 else "▼"


def spark_svg(prices, w=110, h=26):
    if not prices or len(prices) < 2:
        return ""
    mn, mx = min(prices), max(prices)
    rng = mx - mn if mx != mn else 1
    pts = []
    for i, p in enumerate(prices):
        x = 2 + (i / (len(prices) - 1)) * (w - 4)
        y = 2 + (h - 4) - ((p - mn) / rng) * (h - 4)
        pts.append(f"{x:.1f},{y:.1f}")
    up = prices[-1] >= prices[0]
    c = "#3ddc84" if up else "#ff5252"
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{c}" stroke-width="1.5"/></svg>')


def term_chart(prices, w=1040, h=230):
    if not prices or len(prices) < 2:
        return '<div class="dim">NO PRICE DATA</div>'
    mn, mx = min(prices), max(prices)
    rng = mx - mn if mx != mn else 1
    pad_l, pad_r, pad_t, pad_b = 8, 64, 10, 18
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    pts = []
    for i, p in enumerate(prices):
        x = pad_l + (i / (len(prices) - 1)) * iw
        y = pad_t + ih - ((p - mn) / rng) * ih
        pts.append((x, y))
    line = "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = line + f"L{pad_l+iw:.1f},{pad_t+ih:.1f}L{pad_l:.1f},{pad_t+ih:.1f}Z"
    up = prices[-1] >= prices[0]
    c = "#ffa02f" if up else "#ff5252"
    grid = "".join(
        f'<line x1="{pad_l}" y1="{pad_t+ih*i/4:.1f}" x2="{pad_l+iw}" y2="{pad_t+ih*i/4:.1f}" stroke="#1b1b1b" stroke-width="1"/>'
        for i in range(5))
    hi_y = pad_t + ih - ((mx - mn) / rng) * ih
    lo_y = pad_t + ih - ((mn - mn) / rng) * ih
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="width:100%;height:auto">'
            f"{grid}"
            f'<path d="{area}" fill="{c}" opacity="0.08"/>'
            f'<path d="{line}" fill="none" stroke="{c}" stroke-width="2"/>'
            f'<text x="{pad_l+iw+6}" y="{hi_y+4:.1f}" fill="#7c7c7c" font-size="11" font-family="monospace">${mx:,.0f}</text>'
            f'<text x="{pad_l+iw+6}" y="{lo_y+4:.1f}" fill="#7c7c7c" font-size="11" font-family="monospace">${mn:,.0f}</text>'
            f'<text x="{pad_l}" y="{h-4}" fill="#7c7c7c" font-size="11" font-family="monospace">52W WEEKLY</text>'
            "</svg>")


def model_lists(s):
    catalysts, risks = [], []
    if s.get("rev_growth") and s["rev_growth"] > 0.15:
        catalysts.append(("STRONG REVENUE GROWTH", "HIGH"))
    if s.get("earnings_growth") and s["earnings_growth"] > 0.20:
        catalysts.append(("EARNINGS ACCELERATION", "HIGH"))
    if s.get("ma_50") and s.get("ma_200") and s["ma_50"] > s["ma_200"]:
        catalysts.append(("GOLDEN CROSS 50D>200D", "MED"))
    if s.get("ret_3m") and s["ret_3m"] > 15:
        catalysts.append(("STRONG 3M MOMENTUM", "MED"))
    if s.get("roe") and s["roe"] > 0.20:
        catalysts.append(("HIGH RETURN ON EQUITY", "MED"))
    if s.get("pe") and s["pe"] > 60:
        risks.append(("ELEVATED VALUATION (P/E)", "HIGH"))
    if s.get("de") and s["de"] > 200:
        risks.append(("HIGH DEBT-TO-EQUITY", "HIGH"))
    if s.get("beta") and s["beta"] > 1.5:
        risks.append(("HIGH VOLATILITY (BETA)", "MED"))
    if s.get("ret_3m") and s["ret_3m"] < -10:
        risks.append(("NEGATIVE 3M MOMENTUM", "HIGH"))
    if s.get("profit_margin") and s["profit_margin"] < 0:
        risks.append(("UNPROFITABLE", "HIGH"))
    if s.get("peg") and s["peg"] > 2.5:
        risks.append(("OVERPRICED VS GROWTH (PEG)", "MED"))
    if not catalysts:
        catalysts.append(("STABLE FUNDAMENTALS", "MED"))
    if not risks:
        risks.append(("NO MAJOR RED FLAGS", "LOW"))
    return catalysts, risks


def verdict_text(s):
    score = s["total_score"]
    t = f"{s['name']} scores {score}/100. "
    if score >= 75:
        t += "Strong fundamentals with solid momentum. Attractive entry."
    elif score >= 60:
        t += "Good overall profile. Consider on pullbacks."
    elif score >= 45:
        t += "Mixed signals. Wait for a catalyst."
    elif score >= 30:
        t += "Elevated risk. Wait for fundamental improvement."
    else:
        t += "Significant headwinds. Avoid until conditions improve."
    return t


def stat_cells(s):
    def m(v, pre="", suf="", decimals=2):
        return fmt_num(v, pre, suf, decimals) if v is not None else "N/A"
    return [
        ("MKT CAP", m(s.get("mkt_cap"), "$")),
        ("P/E TTM", m(s.get("pe"), decimals=1)),
        ("FWD P/E", m(s.get("fwd_pe"), decimals=1)),
        ("P/B", m(s.get("pb"), decimals=2)),
        ("PEG", m(s.get("peg"), decimals=2)),
        ("EV/EBITDA", m(s.get("ev_ebitda"), decimals=1)),
        ("BETA", m(s.get("beta"), decimals=2)),
        ("DIV YLD", fmt_pct(s.get("dividend_yield")) if s.get("dividend_yield") else "N/A"),
        ("52W HIGH", m(s.get("high_52"), "$")),
        ("52W LOW", m(s.get("low_52"), "$")),
        ("50D MA", m(s.get("ma_50"), "$")),
        ("200D MA", m(s.get("ma_200"), "$")),
        ("REV GR (YOY)", fmt_pct(s.get("rev_growth")) if s.get("rev_growth") is not None else "N/A"),
        ("EARN GR (YOY)", fmt_pct(s.get("earnings_growth")) if s.get("earnings_growth") is not None else "N/A"),
        ("PROFIT MARGIN", fmt_pct(s.get("profit_margin")) if s.get("profit_margin") is not None else "N/A"),
        ("ROE", fmt_pct(s.get("roe")) if s.get("roe") is not None else "N/A"),
        ("DEBT/EQUITY", m(s.get("de"), decimals=0)),
        ("CURR RATIO", m(s.get("current_ratio"), decimals=2)),
        ("VOLUME", m(s.get("volume"), decimals=0)),
        ("AVG VOLUME", m(s.get("avg_volume"), decimals=0)),
    ]


def _clean_num(x):
    try:
        f = float(x)
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return round(f, 2)
    except (TypeError, ValueError):
        return None

def _clean_list(xs):
    return [_clean_num(x) for x in (xs or [])]


def detail_panel(s):
    t = s["ticker"]
    dc, dcp = s.get("day_chg"), s.get("day_chg_pct")
    cls = chg_cls(dcp)
    price = f"${s['price']:,.2f}" if s.get("price") else "N/A"
    chg_txt = f"{dc:+,.2f} ({fmt_chg(dcp)}) {tri(dcp)}" if dc is not None else "N/A"
    stats = "".join(
        f'<div class="stat"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in stat_cells(s))
    bars = "".join(
        f'<div class="mrow"><span class="bl">{label}</span>'
        f'<div class="mbar"><i style="width:{val}%;background:{"#ffa02f" if val >= 60 else "#7c7c7c"}"></i></div>'
        f'<span class="nv">{val}</span></div>'
        for label, val in [("VALUATION 35%", s["val_score"]),
                           ("HEALTH+GROWTH 35%", s["health_score"]),
                           ("MOMENTUM 30%", s["momentum_score"])])
    catalysts, risks = model_lists(s)
    cat_html = "".join(
        f'<div class="ci"><span class="up">+ {label}</span><span class="sev" style="color:{"#3ddc84" if sev == "HIGH" else "#ffa02f"}">{sev}</span></div>'
        for label, sev in catalysts)
    risk_html = "".join(
        f'<div class="ci"><span class="dn">- {label}</span><span class="sev" style="color:{"#ff5252" if sev == "HIGH" else "#ffa02f" if sev == "MED" else "#7c7c7c"}">{sev}</span></div>'
        for label, sev in risks)
    q_rows = ""
    for q in s.get("quarterly", []):
        q_rows += (f'<tr><td>{q["quarter"]}</td><td>{fmt_num(q.get("revenue"), "$")}</td>'
                   f'<td>{fmt_num(q.get("net_income"), "$")}</td>'
                   f'<td>{fmt_num(q.get("gross_profit"), "$")}</td></tr>')
    q_html = (f'<div class="d-sec"><div class="d-sec-t">EARNINGS TREND - QUARTERLY</div>'
              f'<table class="q"><thead><tr><th>QUARTER</th><th>REVENUE</th><th>NET INCOME</th><th>GROSS PROFIT</th></tr></thead>'
              f'<tbody>{q_rows}</tbody></table></div>') if q_rows else ""
    med = s.get("sector_medians", {})
    med_line = (f'<div class="hint">SECTOR MEDIAN [{s["sector"]}]: '
                f'P/E {fmt_num(med.get("pe"), decimals=1)} - P/B {fmt_num(med.get("pb"), decimals=2)} - '
                f'MARGIN {fmt_pct(med.get("profit_margin"))} - ROE {fmt_pct(med.get("roe"))}</div>')

    # analyst consensus
    an_html = ""
    tm, th, tl = s.get("tgt_mean"), s.get("tgt_high"), s.get("tgt_low")
    na, rk, rm = s.get("num_analysts"), s.get("rec_key", ""), s.get("rec_mean")
    if tm is not None or th is not None:
        lo = tl if tl is not None else (tm * 0.8 if tm else 0)
        hi = th if th is not None else (tm * 1.2 if tm else 1)
        span = (hi - lo) or 1
        def _pos(v):
            return max(0, min(100, (v - lo) / span * 100))
        px = s.get("price")
        mean_mk = (f'<div class="mk" style="left:{_pos(tm):.1f}%"><span>TGT {tm:,.0f}</span></div>'
                   if tm else "")
        px_mk = (f'<div class="px" style="left:{_pos(px):.1f}%"><span>PX {px:,.0f}</span></div>'
                 if px else "")
        rec_txt = rk.replace("_", " ").upper() if rk else "N/A"
        an_html = (f'<div class="d-sec"><div class="d-sec-t">ANALYST CONSENSUS</div>'
                   f'<div class="an-bar"><div class="zone" style="left:{_pos(lo):.1f}%;width:{_pos(hi) - _pos(lo):.1f}%"></div>'
                   f'{mean_mk}{px_mk}</div>'
                   f'<div class="an-meta"><span>TARGET RANGE <b>${lo:,.0f} - ${hi:,.0f}</b></span>'
                   f'<span>MEAN TARGET <b>{"$" + f"{tm:,.0f}" if tm else "N/A"}</b></span>'
                   f'<span>RECOMMENDATION <b>{rec_txt}</b>'
                   f'{" (" + f"{rm:.1f}/5" + ")" if rm else ""}</span>'
                   f'<span>ANALYSTS <b>{int(na) if na else "N/A"}</b></span></div></div>')

    ctl = "".join(
        f'<button class="cbtn{" on" if r == "1Y" else ""}" data-r="{r}" onclick="setRange(\'{t}\',\'{r}\')">{r}</button>'
        for r in ["1M", "3M", "6M", "1Y", "5Y"])
    return f'''
<div class="dpanel" id="d-{t}">
  <div class="d-head"><span>{t}</span><span class="nm">{s["name"]} - {s["industry"] or s["sector"]}</span><button onclick="closeD()">ESC</button></div>
  <div class="d-sec">
    <div class="d-price">{price}<span class="chg {cls}">{chg_txt}</span></div>
    <div class="chartctl" style="margin-top:12px">{ctl}<span class="dim" style="margin:0 8px">|</span>
      <button class="cbtn on" data-ty="line" onclick="setType(\'{t}\',\'line\')">LINE</button>
      <button class="cbtn" data-ty="candle" onclick="setType(\'{t}\',\'candle\')">CANDLES</button>
    </div>
    <div class="chartbox" id="ch-{t}"></div>
  </div>
  <div class="d-sec"><div class="d-sec-t">DESCRIPTIVE STATISTICS</div><div class="stat-grid">{stats}</div>{med_line}</div>
  {an_html}
  <div class="d-sec"><div class="d-sec-t">QUANT MODEL - SCORE {s["total_score"]}/100 <span class="rtg" style="color:{s["badge_color"]}">{s["badge_label"].upper()}</span></div>
    {bars}
    <div class="verdict" style="margin-top:12px">{verdict_text(s)}</div>
  </div>
  <div class="d-sec"><div class="d-sec-t">CATALYSTS / RISKS</div>
    <div class="d2"><div>{cat_html}</div><div>{risk_html}</div></div>
  </div>
  {q_html}
</div>'''


def generate_html(stocks, indices):
    now = datetime.now()
    now_str = now.strftime("%d-%b-%Y %H:%M ET").upper()
    sorted_stocks = sorted(stocks.values(), key=lambda x: x.get("total_score", 0), reverse=True)

    tape_items = []
    for s in sorted(stocks.values(), key=lambda x: x["ticker"]):
        if s.get("price") is None:
            continue
        cls = chg_cls(s.get("day_chg_pct"))
        tape_items.append(
            f'<span class="titem"><b>{s["ticker"]}</b> {s["price"]:,.2f} '
            f'<span class="{cls}">{fmt_chg(s.get("day_chg_pct"))} {tri(s.get("day_chg_pct"))}</span></span>')
    tape = "".join(tape_items)

    mkt = ""
    for name in ["SPX", "CCMP", "INDU", "RTY", "VIX"]:
        d = indices.get(name)
        if not d:
            continue
        cls = chg_cls(d["chg_pct"]) if name != "VIX" else chg_cls(-d["chg_pct"] if d["chg_pct"] else None)
        mkt += (f'<div class="mcell"><span class="n">{name}</span>'
                f'<span class="p">{d["price"]:,.2f}</span> '
                f'<span class="{cls}">{fmt_chg(d["chg_pct"])}</span></div>')

    # blotter rows
    rows = ""
    for sector in SECTORS:
        rows += f'<tr class="sect-hd"><td class="l" colspan="14">▸ {sector.upper()}</td></tr>'
        for s in sorted_stocks:
            if s["sector"] != sector:
                continue
            dc, dcp = s.get("day_chg"), s.get("day_chg_pct")
            cls = chg_cls(dcp)
            price = f"{s['price']:,.2f}" if s.get("price") else "N/A"
            pv = s["price"] if s.get("price") is not None else -1
            mcv = s["mkt_cap"] if s.get("mkt_cap") is not None else -1
            pev = s["pe"] if s.get("pe") is not None else 9999
            divp = s["dividend_yield"] * 100 if s.get("dividend_yield") else None
            hi = f"{s['high_52']:,.0f}" if s.get("high_52") else "-"
            lo = f"{s['low_52']:,.0f}" if s.get("low_52") else "-"
            rows += (
                f'<tr data-ticker="{s["ticker"]}" data-name="{s["name"]}" data-sector="{s["sector"]}" '
                f'data-rating="{s["badge_label"]}" data-score="{s["total_score"]}" '
                f'data-pe="{pev if s.get("pe") is not None else ""}" '
                f'data-mcap="{mcv if s.get("mkt_cap") is not None else ""}" '
                f'data-div="{f"{divp:.2f}" if divp is not None else ""}" '
                f'data-hi="{s["high_52"] or ""}" data-lo="{s["low_52"] or ""}" '
                f'onclick="openD(\'{s["ticker"]}\')">'
                f'<td class="l" onclick="event.stopPropagation()"><input type="checkbox" class="cmpchk" onclick="event.stopPropagation();toggleCmp(\'{s["ticker"]}\',this)"></td>'
                f'<td class="l"><span class="ticker">{s["ticker"]}</span></td>'
                f'<td class="l dim">{s["name"][:28]}</td>'
                f'<td data-v="{pv}">{price}</td>'
                f'<td data-v="{dc if dc is not None else -999999}" class="{cls}">{f"{dc:+,.2f}" if dc is not None else "N/A"}</td>'
                f'<td data-v="{dcp if dcp is not None else -999999}" class="{cls}">{tri(dcp)} {fmt_chg(dcp)}</td>'
                f'<td>{spark_svg(s.get("prices_12m", []))}</td>'
                f'<td data-v="{mcv}" class="dim">{fmt_num(s.get("mkt_cap"), "$")}</td>'
                f'<td data-v="{pev}" class="dim">{fmt_num(s.get("pe"), decimals=1) if s.get("pe") else "N/A"}</td>'
                f'<td class="dim">{hi}</td><td class="dim">{lo}</td>'
                f'<td data-v="{s["total_score"]}" style="font-weight:700;color:{s["badge_color"]}">{s["total_score"]}</td>'
                f'<td class="l"><span class="rtg" style="color:{s["badge_color"]}">{s["badge_label"].upper()}</span></td>'
                "</tr>")

    picks = ""
    for i, s in enumerate(sorted_stocks[:10], 1):
        cls = chg_cls(s.get("day_chg_pct"))
        picks += (
            f'<div class="pick" onclick="openD(\'{s["ticker"]}\')">'
            f'<span class="rk">{i:02d}</span>'
            f'<span class="ticker">{s["ticker"]}</span>'
            f'<span class="dim">{s["name"][:34]}</span>'
            f'<span class="bar"><i style="width:{s["total_score"]}%"></i></span>'
            f'<span style="font-weight:700;color:{s["badge_color"]}">{s["total_score"]} - {s["badge_label"].upper()}</span>'
            f'<span class="{cls}">{fmt_chg(s.get("day_chg_pct"))}</span>'
            "</div>")

    sec_html = ""
    for sector, tickers in SECTORS.items():
        chips = ""
        for t in tickers:
            s = stocks.get(t, {})
            sc = s.get("total_score", 0)
            bc = s.get("badge_color", "#7c7c7c")
            chips += (f'<div class="chip" onclick="openD(\'{t}\')"><b>{t}</b>'
                      f'<span class="sc" style="color:{bc}">{sc}</span></div>')
        sec_html += f'<div class="sect-block"><div class="sect-block-h">{sector.upper()} [{len(tickers)}]</div><div class="chips">{chips}</div></div>'

    panels = "".join(detail_panel(s) for s in sorted_stocks)

    # embedded datasets
    charts, meta = {}, {}
    for s in sorted_stocks:
        o = s.get("ohlc_6m") or {}
        t = s["ticker"]
        charts[t] = {
            "w": _clean_list(s.get("prices_5y_w", [])),
            "wd": s.get("dates_5y_w", []),
            "co": _clean_list(o.get("o", [])), "ch": _clean_list(o.get("h", [])),
            "cl": _clean_list(o.get("l", [])), "cc": _clean_list(o.get("c", [])),
            "cd": o.get("d", []),
        }
        meta[t] = {
            "name": s["name"], "sector": s["sector"],
            "price": _clean_num(s.get("price")), "chgp": _clean_num(s.get("day_chg_pct")),
            "mcap": _clean_num(s.get("mkt_cap")), "pe": _clean_num(s.get("pe")),
            "div": _clean_num(s["dividend_yield"] * 100) if s.get("dividend_yield") else None,
            "hi": _clean_num(s.get("high_52")), "lo": _clean_num(s.get("low_52")),
            "vs": s.get("val_score"), "hs": s.get("health_score"),
            "ms": s.get("momentum_score"), "ts": s.get("total_score"),
            "badge": s.get("badge_label"),
        }
    data_js = "var CHARTS=" + json.dumps(charts) + ";\nvar META=" + json.dumps(meta) + ";"

    sec_opts = "".join(f'<option value="{sec}">{sec.upper()}</option>' for sec in SECTORS)
    rat_opts = "".join(f'<option>{r}</option>' for r in ["Strong Buy", "Buy", "Hold", "Cautious", "Sell"])

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EQUITY TERMINAL - {now_str}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><rect width='16' height='16' fill='%23ffa02f'/></svg>">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>{TERM_CSS}</style>
</head>
<body>
<div class="term-top"><span>≡ EQUITY TERMINAL</span><span class="rt"><span class="dot"></span>{now_str} · <span id="clock">--:--:--</span> · FEED OK</span></div>
<div class="tape-wrap"><div class="tape">{tape}{tape}</div></div>
<div class="mkt">{mkt}</div>
<div class="funcbar">
  <button class="fbtn on" data-tab="all" onclick="tab('all')"><span class="fkey">1</span>ALL SECURITIES</button>
  <button class="fbtn" data-tab="top" onclick="tab('top')"><span class="fkey">2</span>TOP PICKS</button>
  <button class="fbtn" data-tab="sec" onclick="tab('sec')"><span class="fkey">3</span>SECTORS</button>
  <input id="q" class="search" placeholder="TICKER SEARCH  [ / ]" autocomplete="off">
  <input id="add-t" class="search" style="width:150px" placeholder="ADD TICKER" autocomplete="off">
  <button class="fbtn" onclick="addTicker()">+ ADD</button>
  <button class="fbtn" id="cmp-btn" onclick="openCmp()" disabled>COMPARE (0)</button>
  <button class="fbtn" onclick="exportCSV()">CSV ↓</button>
</div>
<div class="filterbar">
  <span class="fb-t">FILTERS</span>
  <label>SCORE ≥ <input id="f-score" type="number" value="0" min="0" max="100"></label>
  <label>P/E ≤ <input id="f-pe" type="number" min="0" placeholder="any"></label>
  <label>MKT CAP ≥ $B <input id="f-mcap" type="number" min="0" placeholder="any"></label>
  <label>DIV YLD ≥ % <input id="f-div" type="number" min="0" placeholder="any"></label>
  <label>SECTOR <select id="f-sec"><option value="">ALL</option>{sec_opts}</select></label>
  <label>RATING <select id="f-rat"><option value="">ALL</option>{rat_opts}</select></label>
  <button class="fbtn" onclick="resetFilters()">RESET</button>
  <span id="f-count" class="dim"></span>
</div>
<div class="wrap">
  <div id="tab-all">
    <div class="hint">CLICK ROW FOR DETAIL · CLICK HEADER TO SORT · CHECK BOXES TO COMPARE · {len(sorted_stocks)} SECURITIES</div>
    <table class="blot">
      <thead id="blot-head"><tr>
        <th class="l"></th>
        <th class="l" data-i="1" data-t="s" onclick="sortBy(this)">TICKER</th><th class="l">SECURITY NAME</th>
        <th data-i="3" data-t="n" onclick="sortBy(this)">LAST</th>
        <th data-i="4" data-t="n" onclick="sortBy(this)">NET CHG</th>
        <th data-i="5" data-t="n" onclick="sortBy(this)">% CHG</th>
        <th>12M TREND</th>
        <th data-i="7" data-t="n" onclick="sortBy(this)">MKT CAP</th>
        <th data-i="8" data-t="n" onclick="sortBy(this)">P/E</th>
        <th>52W HI</th><th>52W LO</th>
        <th data-i="11" data-t="n" onclick="sortBy(this)">SCORE</th>
        <th class="l">RTG</th>
      </tr></thead>
      <tbody id="blot-body">{rows}</tbody>
    </table>
  </div>
  <div id="tab-top" style="display:none">
    <div class="hint">TOP 10 BY QUANT SCORE · CLICK FOR DETAIL</div>
    {picks}
  </div>
  <div id="tab-sec" style="display:none">
    <div class="hint">COVERAGE UNIVERSE · {len(SECTORS)} SECTORS</div>
    {sec_html}
  </div>
</div>
<div class="overlay" id="ovl">{panels}</div>
<div class="overlay" id="cmp-ovl" style="display:none">
  <div class="dpanel" id="cmp-panel" style="display:block;max-width:1240px;margin:0 auto">
    <div class="d-head"><span>COMPARE</span><span class="nm" id="cmp-tickers"></span><button onclick="closeCmp()">ESC</button></div>
    <div class="d-sec"><div class="d-sec-t">NORMALIZED PRICE - 5Y WEEKLY, REBASED TO 100</div><div id="cmp-chart"></div><div id="cmp-legend"></div></div>
    <div class="d-sec"><div class="d-sec-t">HEAD-TO-HEAD</div><div id="cmp-table"></div></div>
  </div>
</div>
<div class="statusbar"><span><b>SRC</b> YFINANCE + STOOQ · <b>GEN</b> {now_str} · <b>UNIVERSE</b> {len(sorted_stocks)} SECURITIES</span><span>EDUCATIONAL USE ONLY - NOT FINANCIAL ADVICE</span></div>
<script>{TERM_JS}</script>
<script>{data_js}</script>
</body>
</html>'''


def main():
    print("=" * 60)
    print("  STOCK RISK SCREENER")
    print("=" * 60)

    stocks = fetch_all_data()
    indices = fetch_indices()
    medians = compute_sector_medians(stocks)
    stocks = calculate_scores(stocks, medians)

    html = generate_html(stocks, indices)
    out_path = Path(__file__).parent / "index.html"
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
    _skip = {"prices_12m", "prices_5y_w", "dates_5y_w", "ohlc_6m"}
    export = {t: {k: v for k, v in s.items() if k not in _skip} for t, s in stocks.items()}
    data_path.write_text(json.dumps(export, indent=2, default=str), encoding="utf-8")
    print(f"Data exported to: {data_path}")


if __name__ == "__main__":
    main()
