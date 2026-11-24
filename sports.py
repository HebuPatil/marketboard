#!/usr/bin/env python3
"""
Sports page (placeholder until the Kalshi setup).   ->  pages/sports.html
Same pattern as markets.py: a CONFIG block, a build(demo) that returns a dict,
and templates/sports.html that renders it.
"""
import sys
from common import run

def build(demo):
    return {"title": "Sports", "note": "Placeholder. Built when we set up Kalshi."}

if __name__ == "__main__":
    sys.exit(run("sports", build))
