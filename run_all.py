#!/usr/bin/env python3
"""
Build every page, in order (news uses today's market movers, so markets runs first).
Each page keeps its own twice-a-day limit.

  python3 run_all.py            # what cron runs
  python3 run_all.py --force    # pull everything now
  python3 run_all.py --demo     # fake data for every page
  python3 run_all.py markets    # just one page (any flags still apply)
"""
import importlib, sys
from common import run

ORDER = ["markets", "news", "crypto", "sports"]   # add new pages here

if __name__ == "__main__":
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or ORDER
    codes = [run(n, importlib.import_module(n).build, flags) for n in names]
    sys.exit(max(codes))
