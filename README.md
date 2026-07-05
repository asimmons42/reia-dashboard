# Investor Dashboard — Automated Setup

A live dashboard that refreshes market data weekly on its own, hosted for free.

## What's in here
```
index.html                          the dashboard (this becomes your live website)
config/markets.json                 your candidate markets — edit this list anytime
config/rss_feeds.json               trusted RSS sources for the headline carousel — edit anytime
scripts/fetch_data.py               pulls RentCast + FRED + Census, writes data/*.json
scripts/fetch_rss.py                pulls headlines from config/rss_feeds.json, writes data/rss_data.json
scripts/generate_insights.py        calls the Claude API (with web search) to rewrite the 4 insight cards
data/markets_data.json              output — per-market rent/price/unemployment/population
data/macro_data.json                output — national mortgage rate / price index / unemployment
data/rss_data.json                  output — rotating headline items
data/insights_data.json             output — the 4 narrative cards
.github/workflows/update-data.yml       weekly: market/macro data + RSS headlines
.github/workflows/update-insights.yml   monthly: regenerates the narrative insight cards
```

### Trusted RSS sources included by default
HousingWire, Calculated Risk, The Mortgage Reports, Norada Real Estate Investments, BiggerPockets Blog, and Inman. All are real, publicly syndicated feeds — add or remove any in `config/rss_feeds.json`. If a feed's format ever changes and breaks parsing, `fetch_rss.py` logs a warning and skips just that source rather than failing the whole run.

## One-time setup (about 15 minutes)

### 1. Get your API keys
- **RentCast**: sign up at rentcast.io → free tier gives 50 calls/month, which is plenty for 10 markets checked weekly (~40 calls/month). Grab your API key from the dashboard.
- **FRED**: sign up at fred.stlouisfed.org (Federal Reserve, free, no cost ever) → request an API key, it's issued instantly.
- **Census** (optional but recommended): sign up at api.census.gov/data/key_signup.html → free, raises your rate limit for population data.
- **Anthropic** (optional — only needed for the monthly AI-regenerated insight cards): create a key at console.anthropic.com. This one is usage-based, not free — expect cents to a few dollars a month at this volume (one call a month, with web search). Skip it and the dashboard just keeps showing its bundled default insight cards.

RSS headlines need no API key at all — they're public feeds.

### 2. Create a GitHub repository
If you don't already have a GitHub account, create one free at github.com. Then create a new **public** repository (public is required for free GitHub Pages) and upload every file in this folder, keeping the folder structure intact.

### 3. Add your API keys as repository secrets
In your new repo: **Settings → Secrets and variables → Actions → New repository secret**. Add:
- `RENTCAST_API_KEY`
- `FRED_API_KEY`
- `CENSUS_API_KEY` (optional)
- `ANTHROPIC_API_KEY` (optional — only if you want the monthly AI-regenerated insights)

These are encrypted by GitHub and never appear in your code or logs.

### 4. Turn on GitHub Pages
**Settings → Pages → Source: Deploy from a branch → Branch: main, folder: / (root) → Save.**
GitHub will give you a live URL like `https://yourusername.github.io/reia-dashboard/` within a minute or two. That's your dashboard, permanently.

### 5. Run both workflows for the first time
Go to the **Actions** tab:
- Click **Update Market Data** → **Run workflow** (covers RentCast, FRED, Census, and RSS headlines — this is the one you'll want to trigger for a quick test).
- If you set up the Anthropic key, also click **Regenerate Insight Cards** → **Run workflow**.

Watch them run — if a step fails, click into the logs; the scripts print a `[warn]` line for anything they couldn't fetch rather than crashing, so partial results are normal on a first run.

After they finish, refresh your live dashboard URL — Market Pulse should show live macro numbers, a rotating headline, and (if you ran it) fresh insight cards, each with a "synced"/"refreshed" timestamp.

## Ongoing
- Market/macro/RSS data re-runs automatically every Monday.
- Insight cards regenerate automatically on the 1st of each month.
- Add or remove markets anytime by editing `config/markets.json`; add or remove RSS sources in `config/rss_feeds.json`. Push the change and the next scheduled run picks it up.
- Your Portfolio, Deals, and scoring weights live in your browser's local storage — they're private to you and won't reset when the data refreshes.

## Honest caveats
- I wrote and syntax-checked this code without live internet access, so I could not test the actual API responses. RentCast's exact field names in particular may need a small tweak once you see real output — check the Action's logs and the raw `rentcast_raw` field saved in `data/markets_data.json` if something looks off, and I can help you fix field names on the spot.
- Census population data lags by 1–2 years by nature of how the Census Bureau releases estimates — that's expected, not a bug.
- If you want more markets, more frequent refreshes, or additional data sources (ATTOM, ‌ ‌Zillow-adjacent aggregators, ​BLS metro-level job data), tell me and I'll extend the script.
