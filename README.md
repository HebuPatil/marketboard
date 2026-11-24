# Dashboard

Hosted free on GitHub Pages and rebuilt by GitHub Actions: you just open the website.
(You can also run everything locally; see "Local use".)

## Put it online (one time, ~15 minutes)
1. Make a GitHub account if you don't have one. Create a new **public** repository named `dashboard`
   (free GitHub Pages needs a public repo; nothing personal is in these files, so keep it that way).
2. In Terminal, from this folder:
       git init && git add . && git commit -m "dashboard"
       git branch -M main
       git remote add origin https://github.com/YOUR-USERNAME/dashboard.git
       git push -u origin main
3. On GitHub, in the repo: Settings > Pages > Build and deployment > Source: **GitHub Actions**.
4. Settings > Secrets and variables > Actions > New repository secret:
   name `FRED_API_KEY`, value your free key (https://fred.stlouisfed.org/docs/api/api_key.html).
5. Actions tab > "Build dashboard" > Run workflow (tick "force") for the first build (~2 minutes).
6. Open https://YOUR-USERNAME.github.io/dashboard/ and bookmark it (on iPhone: Share > Add to Home Screen).

### How it stays fresh
- GitHub runs the build at about 5:30am and 1:30pm Pacific on weekdays (.github/workflows/build.yml).
- Each run first checks the live site: if it was built in the last 6 hours, it does nothing.
  Otherwise it pulls fresh data, builds every page, and replaces the old site.
- If a page's pull fails, the previous version of that page stays up.
- The top bar shows when the data is from, and says "stale" if a build was missed.
- Want fresh data right now? Actions tab > Build dashboard > Run workflow.
- To change anything (tickers, feeds, keywords): edit the file, then `git commit -am "update" && git push`.
  The next build uses it.

### Things to know
- GitHub pauses scheduled builds if the repo has no commits for 60 days. It emails you first;
  re-enable with one click in the Actions tab (or push any small change).
- Yahoo sometimes throttles requests from GitHub's servers. If Markets tiles go missing, run the
  workflow again later, or build locally for that day.
- The site is public at that URL (unlisted, but not private). Keep personal data out of it.

    dashboard/
      index.html          the shell you open (tabs: Markets, News, Crypto, Sports)
      run_all.py          builds every page
      ci_prepare.py       GitHub-only: fetches the live site, decides whether to rebuild
      .github/workflows/build.yml   the GitHub schedule
      common.py           shared: fetching, rate limits, math, writing pages
      markets.py          -> pages/markets.html   (Daily, Weekly, Calendar)
      news.py             -> pages/news.html      (Top 5, shortlist, all headlines)
      crypto.py           -> pages/crypto.html    (placeholder until Kalshi)
      sports.py           -> pages/sports.html    (placeholder until Kalshi)
      templates/<page>.html   the layout + key text for that page only
      assets/style.css, ui.js shared look and chart code
      pages/              generated output, don't edit by hand

## Local use
    pip3 install yfinance pandas numpy
    python3 run_all.py --force      # first build
    open index.html
    python3 run_all.py              # every page, max 2 pulls per page per day, 6h apart
    python3 run_all.py news --force # one page, ignoring the limit
    python3 run_all.py --demo       # fake data, offline

A failed pull keeps the previous page. Pages are written atomically.

Locally, set the key in Terminal first: `export FRED_API_KEY=yourkey` (add it to ~/.zshrc to keep it).
Never paste the key into the code: the repo is public. On GitHub it lives in the secret.

## FRED key (free, strongly recommended)
FRED's public download can be slow or time out. With a free key the dashboard uses FRED's
official API instead, which is fast and also gives exact CPI / jobs / PCE / GDP dates.
1. Get one: https://fred.stlouisfed.org/docs/api/api_key.html
2. Add it as the FRED_API_KEY GitHub secret (and `export FRED_API_KEY=...` for local runs).
If FRED is unreachable anyway, the run gives up on FRED after 2 failures (no long hangs),
and 2y/10y/30y yields fall back to Yahoo quotes.

## Editing
- Markets: SERIES, SOURCE_LINKS, RELEASES, FOMC_DECISIONS at the top of markets.py.
  FANG+ reconstitutes after the 3rd Friday of Mar/Jun/Sep/Dec (next: Dec 18, 2026); update the "fang" list.
- News: FEEDS and KEYWORDS at the top of news.py (shown read-only on the News > Keywords tab).
- Key text for a page: the KEY object in templates/<page>.html.

## Adding a page
1. Copy sports.py -> newpage.py; build(demo) returns a dict.
2. Copy templates/sports.html -> templates/newpage.html; render D (that dict).
3. Add "newpage" to ORDER in run_all.py and to PAGES in index.html.
