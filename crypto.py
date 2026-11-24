#!/usr/bin/env python3
"""
Crypto page (placeholder until the Kalshi setup).   ->  pages/crypto.html
Same pattern as markets.py: a CONFIG block, a build(demo) that returns a dict,
and templates/crypto.html that renders it.
"""
import sys
from common import run

def build(demo):
    return {"title": "Crypto", "note": "Placeholder. Built when we set up Kalshi."}

if __name__ == "__main__":
    sys.exit(run("crypto", build))
