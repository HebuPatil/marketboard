#!/usr/bin/env python3
"""
Markets page: indexes, rates, credit/FX, commodities, FANG+ and the AI trade,
plus the economic calendar with release history.   ->  pages/markets.html

  python3 markets.py            # live (max 2 pulls/day)
  python3 markets.py --force    # ignore the limit
  python3 markets.py --demo     # fake data, offline preview
"""
import os, sys, datetime as dt
import numpy as np
import pandas as pd
from common import fetch_yf, fetch_fred, get_json, tail, tile, chg, zscore, run, FRED_API_KEY

# ----------------------------------------------------------------------------- CONFIG
# (id, label, source, kind)  kind: price = % moves, yield = bp moves, level = point moves
SERIES = {
    "risk": [
        ("^GSPC", "S&P 500", "yf", "price"),
        ("^NDX", "Nasdaq 100", "yf", "price"),
        ("^RUT", "Russell 2000", "yf", "price"),
        ("^DJI", "Dow", "yf", "price"),
        ("^VIX", "VIX", "yf", "level"),
        ("^MOVE", "MOVE", "yf", "level"),
    ],
    "rates": [
        ("DGS2", "2y yield", "fred", "yield"),
        ("DGS10", "10y yield", "fred", "yield"),
        ("DGS30", "30y yield", "fred", "yield"),
        ("T10Y2Y", "2s10s curve", "fred", "yield"),
        ("DFII10", "10y real yield", "fred", "yield"),
        ("T5YIE", "5y breakeven", "fred", "yield"),
    ],
    "credit": [
        ("BAMLC0A0CM", "IG spread (OAS)", "fred", "yield"),
        ("BAMLH0A0HYM2", "HY spread (OAS)", "fred", "yield"),
        ("HYG", "HYG", "yf", "price"),
        ("LQD", "LQD", "yf", "price"),
        ("DX-Y.NYB", "Dollar (DXY)", "yf", "price"),
        ("JPY=X", "USDJPY", "yf", "price"),
        ("EURUSD=X", "EURUSD", "yf", "price"),
    ],
    "commods": [
        ("CL=F", "WTI crude", "yf", "price"),
        ("BZ=F", "Brent crude", "yf", "price"),
        ("NG=F", "Nat gas", "yf", "price"),
        ("GC=F", "Gold", "yf", "price"),
        ("HG=F", "Copper", "yf", "price"),
    ],
    # QQQ = the Nasdaq 100 tracker. Then the single names you follow: the NYSE FANG+ 10
    # (META..MU; reconstituted quarterly, see https://www.ice.com/fangplus) plus TSM and ORCL.
    "equities": [
        ("QQQ", "QQQ", "yf", "price"),
        ("NVDA", "NVDA", "yf", "price"),
        ("AVGO", "AVGO", "yf", "price"),
        ("MU", "MU", "yf", "price"),
        ("TSM", "TSM", "yf", "price"),
        ("MSFT", "MSFT", "yf", "price"),
        ("GOOGL", "GOOGL", "yf", "price"),
        ("AMZN", "AMZN", "yf", "price"),
        ("META", "META", "yf", "price"),
        ("ORCL", "ORCL", "yf", "price"),
        ("AAPL", "AAPL", "yf", "price"),
        ("NFLX", "NFLX", "yf", "price"),
        ("PLTR", "PLTR", "yf", "price"),
    ],
}
# helpers pulled but not shown as tiles (used for ratios)
HELPERS = [("RSP", "yf"), ("SPY", "yf"), ("^SOX", "yf"), ("^TNX", "yf"), ("^TYX", "yf"), ("2YY=F", "yf")]
# If FRED is down, these Yahoo quotes stand in (same units: yield in %).
YF_FALLBACK = {"DGS10": "^TNX", "DGS30": "^TYX", "DGS2": "2YY=F"}

SOURCE_LINKS = [
    ("Fed", "FOMC calendar and statements", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
    ("CME", "FedWatch (priced cuts/hikes)", "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"),
    ("BLS", "Release schedule (CPI, jobs)", "https://www.bls.gov/schedule/news_release/"),
    ("BEA", "Release schedule (GDP, PCE)", "https://www.bea.gov/news/schedule"),
    ("Treasury", "Auction schedule and results", "https://www.treasurydirect.gov/auctions/upcoming/"),
    ("Treasury", "Quarterly refunding", "https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding"),
    ("EIA", "Weekly petroleum status report", "https://www.eia.gov/petroleum/supply/weekly/"),
    ("CFTC", "Commitments of Traders", "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm"),
    ("NY Fed", "ACM term premium", "https://www.newyorkfed.org/research/data_indicators/term-premia-tabs"),
    ("FINRA", "Margin statistics", "https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics"),
]
LOOKBACK_DAYS = 400
RELEASE_YEARS = 5           # history shown on each economic-release chart

# Optional: free key from https://fred.stlouisfed.org/docs/api/api_key.html gives exact
# upcoming dates for CPI / jobs / PCE / GDP. Without it those show approximate timing.
# Set it in common.py (FRED_API_KEY) or in Terminal:  export FRED_API_KEY=yourkey

# Fed calendar (revised Nov 12, 2026). Policy decision 2:00pm ET on these days.
# Oct 27, 2027 is a strategy-only meeting with no rate decision.
FOMC_DECISIONS = ["2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09",
                  "2027-07-28", "2027-09-15", "2027-11-17", "2028-01-26"]

# Each scheduled release: when it lands, what to chart, and how.
#   schedule: ("weekly", weekday 0=Mon) | ("first_friday",) | ("fred", release_id) | ("fomc",)
#   series:   (FRED id, label, transform)   transform: level | yoy | diff | k (divide by 1000)
RELEASES = [
    dict(id="fomc", name="FOMC rate decision", org="Fed", time="2:00pm", schedule=("fomc",),
         series=[("DFEDTARU", "Fed funds target (upper)", "level")], unit="%"),
    dict(id="cpi", name="CPI inflation", org="BLS", time="8:30am", schedule=("fred", 10),
         series=[("CPIAUCSL", "Headline CPI, y/y", "yoy"), ("CPILFESL", "Core CPI, y/y", "yoy")], unit="%"),
    dict(id="jobs", name="Jobs report", org="BLS", time="8:30am", schedule=("fred", 50),
         series=[("PAYEMS", "Payrolls added (thousands)", "diff"), ("UNRATE", "Unemployment rate", "level")], unit="k / %"),
    dict(id="claims", name="Initial jobless claims", org="Labor Dept", time="8:30am", schedule=("weekly", 3),
         series=[("ICSA", "Initial claims (thousands)", "k")], unit="k"),
    dict(id="pce", name="PCE inflation", org="BEA", time="8:30am", schedule=("fred", 54),
         series=[("PCEPILFE", "Core PCE, y/y", "yoy"), ("PCEPI", "Headline PCE, y/y", "yoy")], unit="%"),
    dict(id="gdp", name="GDP", org="BEA", time="8:30am", schedule=("fred", 53),
         series=[("A191RL1Q225SBEA", "Real GDP growth, annualized", "level")], unit="%"),
    dict(id="eia", name="EIA crude inventories", org="EIA", time="10:30am", schedule=("weekly", 2),
         series=[("WCESTUS1", "US crude stocks ex-SPR (million bbl)", "k")], unit="M bbl"),
    dict(id="cot", name="CFTC Commitments of Traders", org="CFTC", time="3:30pm", schedule=("weekly", 4),
         series=[], unit=""),
]
TREASURY_UPCOMING = "https://www.treasurydirect.gov/TA_WS/securities/upcoming?format=json"

# ----------------------------------------------------------------------------- LOAD
def load_live():
    yf_ids = [s[0] for g in SERIES.values() for s in g if s[2] == "yf"] + [h[0] for h in HELPERS]
    print("  prices: Yahoo (one batched request)...")
    px = fetch_yf(yf_ids, LOOKBACK_DAYS)              # ONE batched request for every ticker
    print("  rates and spreads: FRED...")
    data = {c: px[c].dropna() for c in px.columns}
    for g in SERIES.values():
        for sid, _, src, _ in g:
            if src == "fred":
                try:
                    data[sid] = fetch_fred(sid, LOOKBACK_DAYS)
                except Exception as e:
                    fb = YF_FALLBACK.get(sid)
                    if fb in data and len(data[fb]) > 30:
                        data[sid] = data[fb]; print(f"  {sid}: using Yahoo {fb} instead")
                    else:
                        if "skipped" not in str(e): print(f"  FRED {sid} failed: {e}", file=sys.stderr)
    if "T10Y2Y" not in data and "DGS10" in data and "DGS2" in data:
        data["T10Y2Y"] = (data["DGS10"] - data["DGS2"]).dropna()
    today = dt.date.today()
    print("  economic releases and calendar...")
    return data, {"releases": load_releases(today), "auctions": load_auctions(today)}

def load_demo():
    rng = np.random.default_rng(7)
    idx = pd.bdate_range(end=pd.Timestamp.today(), periods=270)
    base = {"^GSPC": 6500, "^NDX": 23000, "^RUT": 2300, "^DJI": 45000, "^VIX": 19, "^MOVE": 95,
            "DGS2": 3.6, "DGS10": 4.2, "DGS30": 4.8, "T10Y2Y": 0.6, "DFII10": 1.9, "T5YIE": 2.4,
            "BAMLC0A0CM": 0.85, "BAMLH0A0HYM2": 3.1, "HYG": 80, "LQD": 110, "DX-Y.NYB": 99,
            "JPY=X": 152, "EURUSD=X": 1.15, "CL=F": 62, "BZ=F": 66, "NG=F": 3.8, "GC=F": 3900,
            "HG=F": 5.0, "RSP": 185, "SPY": 650}
    data = {}
    for sid, b in base.items():
        vol = 0.012 if b > 10 else 0.03
        data[sid] = pd.Series(b * np.exp(np.cumsum(rng.normal(0, vol, len(idx)))), idx)
    for sid in [x[0] for g in SERIES.values() for x in g] + [h[0] for h in HELPERS]:
            if sid not in data:
                data[sid] = pd.Series(150 * np.exp(np.cumsum(rng.normal(0.0004, 0.022, len(idx)))), idx)
    today = dt.date.today()
    return data, {"releases": load_releases(today, demo=True), "auctions": load_auctions(today, demo=True)}

# ----------------------------------------------------------------------------- RELEASES
def fred_release_dates(rid):
    if not FRED_API_KEY: return None
    try:
        u = (f"https://api.stlouisfed.org/fred/release/dates?release_id={rid}&api_key={FRED_API_KEY}"
             f"&file_type=json&include_release_dates_with_no_data=true&sort_order=desc&limit=40")
        return sorted(d["date"] for d in get_json(u)["release_dates"])
    except Exception as e:
        print(f"  FRED release dates {rid} failed: {e}", file=sys.stderr); return None

def upcoming(rel, today, horizon=45):
    """Upcoming dates within horizon days -> (list of dates, exact?)."""
    kind = rel["schedule"][0]
    end = today + dt.timedelta(days=horizon)
    if kind == "weekly":
        wd = rel["schedule"][1]
        d = today + dt.timedelta(days=(wd - today.weekday()) % 7)
        out = []
        while d <= end: out.append(d); d += dt.timedelta(days=7)
        return out, True
    if kind == "fomc":
        return [dt.date.fromisoformat(x) for x in FOMC_DECISIONS if today <= dt.date.fromisoformat(x) <= end], True
    if kind == "fred":
        ds = fred_release_dates(rel["schedule"][1])
        if ds is not None:
            return [dt.date.fromisoformat(x) for x in ds if today <= dt.date.fromisoformat(x) <= end], True
        if rel["id"] == "jobs":                    # fallback: first Friday (usually right)
            out = []
            for m in range(3):
                first = (today.replace(day=1) + dt.timedelta(days=32 * m)).replace(day=1)
                d = first + dt.timedelta(days=(4 - first.weekday()) % 7)
                if today <= d <= end: out.append(d)
            return out, False
        return [], False
    return [], False

def transform(s, how):
    s = s.dropna()
    if how == "yoy":  return (s / s.shift(12) - 1).dropna() * 100
    if how == "diff": return s.diff().dropna()
    if how == "k":    return s / 1000
    return s

def load_releases(today, demo=False):
    out = []
    rng = np.random.default_rng(3)
    for rel in RELEASES:
        series = []
        for sid, label, how in rel["series"]:
            try:
                if demo:
                    n = 260 if how == "k" else 72
                    idx = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="W" if how == "k" else "MS")
                    raw = pd.Series(np.cumsum(rng.normal(0.2, 1, n)) + 100, idx)
                    s = transform(raw * (1000 if how == "k" else 1), how)
                else:
                    s = transform(fetch_fred(sid, days=365 * RELEASE_YEARS + 400), how)
                    s = s[s.index >= pd.Timestamp.today() - pd.DateOffset(years=RELEASE_YEARS)]
                series.append({"label": label, "kind": how, **tail(s, 400),
                               "last": round(float(s.iloc[-1]), 2), "prev": round(float(s.iloc[-2]), 2),
                               "asof": s.index[-1].strftime("%b %Y" if how != "k" else "%b %d")})
            except Exception as e:
                if "skipped" not in str(e): print(f"  release series {sid} failed: {e}", file=sys.stderr)
        dates, exact = ([], False) if demo and rel["schedule"][0] == "fred" else upcoming(rel, today)
        out.append({k: rel[k] for k in ("id", "name", "org", "time", "unit")} |
                   {"series": series, "next": [d.isoformat() for d in dates], "exact": exact})
    return out

def load_auctions(today, demo=False):
    """Upcoming Treasury coupon auctions (bills skipped: too many, too small a signal)."""
    if demo:
        return [{"date": (today + dt.timedelta(days=d)).isoformat(), "term": t, "type": "Note"}
                for d, t in [(1, "2-Year"), (2, "5-Year"), (3, "7-Year")]]
    try:
        rows = get_json(TREASURY_UPCOMING)
        out = []
        for r in rows:
            if r.get("securityType") in ("Note", "Bond", "TIPS", "FRN") or "TIPS" in r.get("securityTerm", ""):
                out.append({"date": r["auctionDate"][:10], "term": r.get("securityTerm", ""), "type": r.get("securityType", "")})
        return sorted(out, key=lambda x: x["date"])
    except Exception as e:
        print(f"  Treasury auctions failed: {e}", file=sys.stderr); return []

# ----------------------------------------------------------------------------- BUILD
def build_payload(data, extra):
    tiles = {}
    for grp, items in SERIES.items():
        tiles[grp] = []
        for sid, label, src, kind in items:
            s = data.get(sid)
            if s is None or len(s) < 2:
                tiles[grp].append({"id": sid, "label": label, "missing": True}); continue
            tiles[grp].append(tile(s, sid, label, kind, src))
    def ratio(a, b):
        if a in data and b in data:
            r = (data[a] / data[b]).dropna()
            return tail(r, 260)
    charts = {
        "ndx_real": {"a": tail(data["^NDX"], 260) if "^NDX" in data else None, "b": tail(data["DFII10"], 260) if "DFII10" in data else None},
        "rsp_spy": ratio("RSP", "SPY"),
        "sox_spx": ratio("^SOX", "^GSPC"),
        "cu_au": {"a": ratio("HG=F", "GC=F"), "b": tail(data["DGS10"], 260) if "DGS10" in data else None},
        "curve": tail(data["T10Y2Y"], 260) if "T10Y2Y" in data else None,
        "hy": tail(data["BAMLH0A0HYM2"], 260) if "BAMLH0A0HYM2" in data else None,
        "vix_move": {"a": tail(data["^VIX"], 260) if "^VIX" in data else None, "b": tail(data["^MOVE"], 260) if "^MOVE" in data else None},
    }
    # rolling 60d correlation: SPX daily returns vs 10y yield changes
    if "^GSPC" in data and "DGS10" in data:
        j = pd.concat([np.log(data["^GSPC"]).diff(), data["DGS10"].diff()], axis=1, join="inner").dropna()
        charts["stock_bond"] = tail(j.iloc[:, 0].rolling(60).corr(j.iloc[:, 1]).dropna(), 200)
    # breadth on your single names: share above 200d average
    tech = [t["id"] for t in tiles["equities"] if not t.get("missing") and t["id"] != "QQQ"]
    above = [t for t in tech if len(data[t]) >= 200 and data[t].iloc[-1] > data[t].iloc[-200:].mean()]
    breadth = {"n": len(tech), "above": len(above)}
    flat = [t for g in tiles.values() for t in g if not t.get("missing") and t.get("z1") is not None]
    movers = sorted(flat, key=lambda t: -abs(t["z1"]))[:10]
    return {"tiles": tiles, "charts": charts, "breadth": breadth,
            "movers": [{"id": t["id"], "label": t["label"], "d1": t["d1"], "z1": t["z1"], "kind": t["kind"]} for t in movers],
            "links": [{"org": o, "name": n, "url": u} for o, n, u in SOURCE_LINKS],
            "releases": extra["releases"], "auctions": extra["auctions"]}

def build(demo):
    data, extra = load_demo() if demo else load_live()
    return build_payload(data, extra)

if __name__ == "__main__":
    sys.exit(run("markets", build))
