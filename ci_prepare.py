#!/usr/bin/env python3
"""
Runs on GitHub Actions before each build.
1. Downloads the currently live pages, so a failed pull keeps yesterday's page instead of a blank one.
2. Decides whether to build: skip if the live site was already built within MIN_HOURS_BETWEEN hours.
Writes skip=true/false to $GITHUB_OUTPUT.
"""
import json, os, sys, datetime as dt, urllib.request
from pathlib import Path
from common import MIN_HOURS_BETWEEN

SITE = os.environ.get("SITE_URL", "").rstrip("/")
PAGES = ["markets", "news", "crypto", "sports"]
out = Path("pages"); out.mkdir(exist_ok=True)

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "dashboard-ci"}), timeout=15) as r:
        return r.read()

last = None
for p in PAGES:
    for ext in ("html", "json"):
        try:
            (out / f"{p}.{ext}").write_bytes(get(f"{SITE}/pages/{p}.{ext}"))
        except Exception as e:
            print(f"no live {p}.{ext} yet ({type(e).__name__})")
    if p == "markets":
        try: last = dt.datetime.fromisoformat(json.loads((out / "markets.json").read_text())["generated_iso"]).astimezone()
        except Exception: last = None

force = os.environ.get("FORCE", "false") == "true"
skip = (not force) and last is not None and dt.datetime.now().astimezone() - last < dt.timedelta(hours=MIN_HOURS_BETWEEN)
print(f"last build: {last}, force: {force} -> {'skip' if skip else 'build'}")
with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
    f.write(f"skip={'true' if skip else 'false'}\n")
