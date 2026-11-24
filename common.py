"""
Shared plumbing for every dashboard page: fetching, rate limits, math helpers, writing pages.
Page scripts (markets.py, news.py, crypto.py, sports.py) import from here.
"""
import io, json, os, sys, time, datetime as dt, urllib.request, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
TEMPLATES, PAGES, STATE = ROOT / "templates", ROOT / "pages", ROOT / ".state"

MAX_RUNS_PER_DAY = 2        # hard cap on live pulls per page per calendar day
MIN_HOURS_BETWEEN = 6       # and at least this long between pulls
UA = {"User-Agent": "Mozilla/5.0 (personal dashboard)"}
ATOM = "{http://www.w3.org/2005/Atom}"

# ----------------------------------------------------------------------------- fetching
def get_bytes(url, timeout=20, retries=1):
    """Polite GET: ~1 request/second, one retry."""
    for attempt in range(retries + 1):
        try:
            time.sleep(1)
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception:
            if attempt == retries: raise
            time.sleep(5)

def get_json(url):
    return json.loads(get_bytes(url))

# FRED: uses the official API when FRED_API_KEY is set (fast, reliable), else the public CSV.
# Circuit breaker: after 2 failures in a row, every remaining FRED call this run is skipped
# instantly instead of each one hanging on a timeout.
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")   # set as a GitHub secret / env var; never paste it here (the repo is public)
_fred = {"fails": 0, "down": False}

def fetch_fred(sid, days=400):
    if _fred["down"]:
        raise RuntimeError("skipped (FRED unreachable this run)")
    start = (pd.Timestamp.today() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        if FRED_API_KEY:
            j = json.loads(get_bytes("https://api.stlouisfed.org/fred/series/observations?series_id="
                                     f"{sid}&observation_start={start}&file_type=json&api_key={FRED_API_KEY}",
                                     timeout=10, retries=0))
            s = pd.Series({pd.Timestamp(o["date"]): (float(o["value"]) if o["value"] != "." else np.nan)
                           for o in j["observations"]})
        else:
            raw = get_bytes(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}",
                            timeout=8, retries=0)
            s = pd.read_csv(io.BytesIO(raw), index_col=0, parse_dates=True, na_values=".").iloc[:, 0]
    except Exception:
        _fred["fails"] += 1
        if _fred["fails"] >= 2:
            _fred["down"] = True
            print("  FRED unreachable: skipping the rest of FRED this run"
                  + ("" if FRED_API_KEY else " (a free FRED_API_KEY usually fixes this, see README)"), file=sys.stderr)
        raise
    _fred["fails"] = 0
    return s[s.index >= pd.Timestamp(start)].astype(float).dropna()

def fetch_yf(tickers, days=400):
    import yfinance as yf
    df = yf.download(tickers, period=f"{days}d", auto_adjust=True, progress=False)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(tickers[0])
    if df is None or df.dropna(how="all").empty:
        raise RuntimeError("Yahoo returned no prices (rate limited or offline)")
    return df

def _when(txt):
    try:
        d = parsedate_to_datetime(txt)
    except Exception:
        try: d = dt.datetime.fromisoformat(txt.replace("Z", "+00:00"))
        except Exception: return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)

def fetch_feed(url, n=40):
    """RSS or Atom -> [{title, link, when (ISO, UTC), summary}]. Raises on failure."""
    root = ET.fromstring(get_bytes(url, timeout=10, retries=0))
    items = root.findall(".//item") or root.findall(f".//{ATOM}entry")
    out = []
    for it in items[:n]:
        g = lambda tag: (it.findtext(tag) or it.findtext(ATOM + tag) or "").strip()
        link = g("link")
        if not link and it.find(ATOM + "link") is not None:
            link = it.find(ATOM + "link").get("href", "")
        w = _when(g("pubDate") or g("updated") or g("published"))
        out.append({"title": g("title"), "link": link, "summary": g("description")[:300],
                    "when": w.astimezone(dt.timezone.utc).isoformat() if w else None})
    return out

# ----------------------------------------------------------------------------- math
def chg(s, n, kind):
    if len(s) <= n: return None
    a, b = s.iloc[-1], s.iloc[-1 - n]
    return round((a - b) * 100, 1) if kind == "yield" else round(a - b, 2) if kind == "level" else round((a / b - 1) * 100, 2)

def zscore(s, kind, n=1):
    """n-day move divided by its normal size (20d realized vol scaled to n days)."""
    d = (s.diff() if kind in ("yield", "level") else np.log(s).diff()).dropna()
    if len(d) < 25: return None
    vol = d.iloc[-21:-1].std() * np.sqrt(n)
    return round(float(d.iloc[-n:].sum() / vol), 2) if vol > 0 else None

def tail(s, n):
    s = s.dropna().iloc[-n:]
    return {"d": [x.strftime("%Y-%m-%d") for x in s.index], "v": [round(float(x), 4) for x in s.values]}

def tile(s, sid, label, kind, src):
    """Standard tile payload for a price/yield series."""
    s = s.dropna()
    return {"id": sid, "label": label, "kind": kind, "src": src,
            "last": round(float(s.iloc[-1]), 4), "asof": s.index[-1].strftime("%b %d"),
            "d1": chg(s, 1, kind), "w1": chg(s, 5, kind), "m1": chg(s, 21, kind), "y1": chg(s, 252, kind),
            "z1": zscore(s, kind, 1), "z5": zscore(s, kind, 5), "spark": tail(s, 30)["v"]}

def now_label():
    return dt.datetime.now().strftime("%a %b %d %Y, %I:%M %p")

# ----------------------------------------------------------------------------- rate limit
def _runs(name):
    try: return [dt.datetime.fromisoformat(x) for x in json.loads((STATE / f"{name}.json").read_text())["runs"]]
    except Exception: return []

def should_skip(name):
    if not (PAGES / f"{name}.html").exists():
        return None
    runs, now = _runs(name), dt.datetime.now()
    today = [r for r in runs if r.date() == now.date()]
    if len(today) >= MAX_RUNS_PER_DAY:
        return f"already pulled {len(today)}x today (max {MAX_RUNS_PER_DAY})"
    if runs and now - max(runs) < dt.timedelta(hours=MIN_HOURS_BETWEEN):
        return f"last pull was {max(runs):%I:%M %p}, less than {MIN_HOURS_BETWEEN}h ago"
    return None

def record_run(name):
    STATE.mkdir(exist_ok=True)
    runs = [r for r in _runs(name) if r > dt.datetime.now() - dt.timedelta(days=7)] + [dt.datetime.now()]
    (STATE / f"{name}.json").write_text(json.dumps({"runs": [r.isoformat(timespec="seconds") for r in runs]}))

# ----------------------------------------------------------------------------- output
def write_page(name, payload):
    """templates/<name>.html + payload -> pages/<name>.html (and pages/<name>.json). Atomic."""
    PAGES.mkdir(exist_ok=True)
    tpl = (TEMPLATES / f"{name}.html").read_text()
    for ext, body in (("json", json.dumps(payload)),
                      ("html", tpl.replace("__DATA__", json.dumps(payload).replace("</", "<\\/")))):
        tmp = PAGES / f"{name}.{ext}.tmp"
        tmp.write_text(body)
        os.replace(tmp, PAGES / f"{name}.{ext}")

def read_page_data(name):
    """Another page's last payload (e.g. news reads today's market movers)."""
    try: return json.loads((PAGES / f"{name}.json").read_text())
    except Exception: return None

def run(name, build, argv=None):
    """Standard entry point. build(demo: bool) -> payload dict."""
    import argparse
    ap = argparse.ArgumentParser(description=f"Build pages/{name}.html")
    ap.add_argument("--demo", action="store_true", help="fake data, no network")
    ap.add_argument("--force", action="store_true", help="ignore the twice-a-day limit")
    a = ap.parse_args(argv)
    if not a.demo and not a.force:
        why = should_skip(name)
        if why:
            print(f"[{name}] skipped: {why}. Use --force to pull anyway.")
            return 0
    print(f"[{name}] loading {'demo' if a.demo else 'live'} data...")
    try:
        payload = build(a.demo)
    except Exception as e:
        keep = (PAGES / f"{name}.html").exists()
        print(f"[{name}] pull failed ({type(e).__name__}: {e}). " +
              ("Kept the previous page." if keep else "No page built yet; try again later."), file=sys.stderr)
        return 1
    payload.setdefault("generated", now_label())
    payload.setdefault("generated_iso", dt.datetime.now().astimezone().isoformat(timespec="minutes"))
    payload.setdefault("demo", a.demo)
    write_page(name, payload)
    if not a.demo:
        record_run(name)
    print(f"[{name}] wrote {PAGES / (name + '.html')}")
    return 0
