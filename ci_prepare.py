#!/usr/bin/env python3
"""
Runs on GitHub Actions before each build. The workflow fires every hour on weekdays (GitHub
sometimes skips scheduled runs, so many chances = reliable). This script decides whether
this particular run should build:

  * Two update slots per weekday (Pacific): 5:00am (before the open) and 1:15pm (after the close).
  * Build if the live site hasn't been built since the most recent slot. Otherwise skip.
  So the first run after each slot builds, and every later run that half-day skips in seconds.

It also downloads the currently live pages, so a failed pull keeps the old page instead of a blank one.
Writes skip=true/false to $GITHUB_OUTPUT.
"""
import json, os, datetime as dt, urllib.request
from pathlib import Path

SLOTS = [(5, 0), (13, 15)]          # local (Pacific) times of the two daily updates
SITE = os.environ.get("SITE_URL", "").rstrip("/")
PAGES = ["markets", "news", "crypto", "sports"]

def latest_slot(now):
    """Most recent weekday slot at or before now."""
    day = now
    for _ in range(8):
        if day.weekday() < 5:
            for h, m in sorted(SLOTS, reverse=True):
                t = day.replace(hour=h, minute=m, second=0, microsecond=0)
                if t <= now:
                    return t
        day = (day - dt.timedelta(days=1)).replace(hour=23, minute=59)
    return now

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "dashboard-ci"}), timeout=15) as r:
        return r.read()

def main():
    out = Path("pages"); out.mkdir(exist_ok=True)
    last = None
    for p in PAGES:
        for ext in ("html", "json"):
            try:
                (out / f"{p}.{ext}").write_bytes(get(f"{SITE}/pages/{p}.{ext}"))
            except Exception as e:
                print(f"no live {p}.{ext} yet ({type(e).__name__})")
        if p == "markets":
            try:
                last = dt.datetime.fromisoformat(json.loads((out / "markets.json").read_text())["generated_iso"]).astimezone()
            except Exception:
                last = None
    now = dt.datetime.now().astimezone()
    slot = latest_slot(now)
    force = os.environ.get("FORCE", "false") == "true"
    skip = (not force) and last is not None and last >= slot
    print(f"now {now:%a %H:%M}, latest slot {slot:%a %H:%M}, last build {last}, force {force} -> {'skip' if skip else 'build'}")
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
        f.write(f"skip={'true' if skip else 'false'}\n")

if __name__ == "__main__":
    main()
