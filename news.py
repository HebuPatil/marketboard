#!/usr/bin/env python3
"""
News page: Bloomberg headlines + primary sources (Fed, BLS, EIA) in one feed,
ranked into a top 5 and a shortlist of ~25 worth checking.   ->  pages/news.html

Ranking: a keyword score from INTERESTS / KEYWORDS below, plus a boost for headlines
about today's market movers (from the Markets page) and for primary sources.

RSS gives headlines and links only. Clicking opens the article on bloomberg.com,
where your subscription lets you read it.

  python3 news.py            # live (max 2 pulls/day)
  python3 news.py --force
  python3 news.py --demo
"""
import re, sys, datetime as dt
from common import fetch_feed, read_page_data, run

# ----------------------------------------------------------------------------- CONFIG
# (source, section, url, is_primary_source). Add or remove freely.
FEEDS = [
    ("Bloomberg", "Markets", "https://feeds.bloomberg.com/markets/news.rss", False),
    ("Bloomberg", "Economics", "https://feeds.bloomberg.com/economics/news.rss", False),
    ("Bloomberg", "Technology", "https://feeds.bloomberg.com/technology/news.rss", False),
    ("Bloomberg", "Politics", "https://feeds.bloomberg.com/politics/news.rss", False),
    ("Fed", "Press releases", "https://www.federalreserve.gov/feeds/press_all.xml", True),
    ("Fed", "Speeches", "https://www.federalreserve.gov/feeds/speeches.xml", True),
    ("BLS", "Latest releases", "https://www.bls.gov/feed/bls_latest.rss", True),
    ("EIA", "Today in energy", "https://www.eia.gov/rss/todayinenergy.xml", True),
]
HOURS_BACK = 36            # only headlines from the last 36 hours
TOP_N, SHORTLIST_N = 5, 25

# What you care about (notes for you; KEYWORDS below does the actual scoring).
INTERESTS = """
I'm starting as a quant researcher on a fixed income / systematic macro desk.
Priorities, highest first:
1. Fed policy, rates, Treasury yields and auctions, inflation and jobs data, term premium, fiscal/supply.
2. The AI trade and possible tech bubble: hyperscaler capex, chips (NVDA, AVGO, TSM, MU), AI financing
   and debt issuance, valuations, concentration, FANG+ names.
3. Credit spreads, funding stress, the dollar, yen and carry trades.
4. Commodities: oil, OPEC, natural gas, gold, copper.
5. Big cross-asset moves and anything that could move prediction markets on macro data.
Skip: personal finance, lifestyle, single-company stories outside tech/AI unless they move markets.
"""
KEYWORDS = {   # weight: words (lowercase, matched as whole words or prefixes)
    3: ["fed", "fomc", "powell", "warsh", "rate cut", "rate hike", "treasur", "yield", "bond", "inflation",
        "cpi", "pce", "payroll", "jobs report", "unemployment", "auction", "term premium", "deficit"],
    3.5: ["nvidia", "ai ", "artificial intelligence", "capex", "data center", "chip", "semiconductor",
          "broadcom", "tsmc", "micron", "hyperscaler", "openai", "bubble"],
    2: ["credit", "spread", "junk", "high-yield", "default", "dollar", "yen", "carry", "liquidity",
        "oil", "opec", "crude", "natural gas", "gold", "copper", "tariff", "recession", "gdp"],
    1.5: ["microsoft", "alphabet", "google", "amazon", "meta", "apple", "netflix", "palantir", "oracle",
          "stocks", "s&p", "nasdaq", "selloff", "rally", "volatility", "vix"],
}

# ----------------------------------------------------------------------------- LOAD
def load(demo):
    if demo:
        now = dt.datetime.now(dt.timezone.utc)
        samples = ["Treasury yields climb as traders pare Fed cut bets after hot CPI",
                   "Nvidia suppliers signal another leg up in AI data center spending",
                   "Oil slips as OPEC+ weighs output increase", "Junk bond spreads widen most since spring",
                   "Yen surges, sparking carry-trade unwind fears", "Oracle taps bond market again to fund AI build-out",
                   "Fed's Waller says policy is in a good place", "Gold hits record as real yields fall",
                   "Retailers brace for slow holiday season", "Microsoft capex guidance tops estimates"]
        items = [{"src": "Bloomberg" if i % 4 else "Fed", "section": "Markets", "title": samples[i % 10] + ("" if i < 10 else f" ({i})"),
                  "link": "#", "summary": "", "when": (now - dt.timedelta(hours=i)).isoformat(), "primary": i % 4 == 0}
                 for i in range(34)]
        return items, []
    items, errors, dead = [], [], set()
    for src, section, url, primary in FEEDS:
        host = url.split("/")[2]
        if host in dead:                       # same site already failed: don't wait on it again
            errors.append(f"{src} {section}: skipped"); continue
        print(f"  {src} {section}...")
        try:
            for it in fetch_feed(url):
                items.append(dict(it, src=src, section=section, primary=primary))
        except Exception as e:
            dead.add(host); errors.append(f"{src} {section}: {type(e).__name__}")
    if not items:
        raise RuntimeError("every feed failed: " + "; ".join(errors))
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=HOURS_BACK)
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x["when"] or "", reverse=True):
        key = re.sub(r"\W+", "", it["title"].lower())[:80]
        if key in seen or not it["title"]: continue
        if it["when"] and dt.datetime.fromisoformat(it["when"]) < cutoff and not it["primary"]: continue
        seen.add(key); out.append(it)
    return out, errors

# ----------------------------------------------------------------------------- RANK
def keyword_rank(items, movers):
    mover_words = [m["label"].split(" (")[0].lower() for m in movers]
    now = dt.datetime.now(dt.timezone.utc)
    for it in items:
        t = " " + it["title"].lower() + " "
        score, hits = 0.0, []
        for w, words in KEYWORDS.items():
            for k in words:
                if re.search(r"\b" + re.escape(k), t):
                    score += w; hits.append(k.strip())
        for m in mover_words:
            if len(m) > 2 and m in t: score += 3; hits.append(m + " (mover)")
        if it["primary"]: score += 1.5
        if it["when"]:
            age = (now - dt.datetime.fromisoformat(it["when"])).total_seconds() / 3600
            score += max(0, 2 - age / 12)          # small freshness bonus
        it["score"], it["why"] = round(score, 1), ("Matches: " + ", ".join(dict.fromkeys(hits))[:120]) if hits else ""
    ranked = sorted(items, key=lambda x: -x["score"])
    return ranked[:TOP_N], ranked[TOP_N:TOP_N + SHORTLIST_N], "keywords"

def build(demo):
    items, errors = load(demo)
    mk = read_page_data("markets") or {}
    movers = mk.get("movers", [])
    top, short, how = keyword_rank(items, movers)
    for it in items: it.pop("summary", None)
    return {"top": top, "shortlist": short, "all": items, "ranked_by": how, "errors": errors,
            "keywords": [{"weight": w, "words": [k.strip() for k in ws]} for w, ws in sorted(KEYWORDS.items(), reverse=True)],
            "interests": INTERESTS.strip(),
            "movers": movers, "feeds": [{"src": s, "section": n, "primary": p} for s, n, _, p in FEEDS]}

if __name__ == "__main__":
    sys.exit(run("news", build))
