"""
Pulls recurring market data from three sources:
  - RentCast   : per-zip rent/sale market stats        (needs RENTCAST_API_KEY)
  - FRED       : national mortgage rate, home price index, state unemployment  (needs FRED_API_KEY, free)
  - Census PEP : county population estimates for growth rate   (CENSUS_API_KEY optional)

Writes:
  data/markets_data.json   - one entry per configured market
  data/macro_data.json     - national-level snapshot

Uses only the Python standard library (no pip installs required).
Designed to run from GitHub Actions on a schedule, but works fine run locally too:
    RENTCAST_API_KEY=xxx FRED_API_KEY=yyy python scripts/fetch_data.py

NOTE: I could not test these API calls live while building this (no internet
access in my working environment). Endpoint shapes and field names are based
on current published docs as of July 2026 -- verify the first run and adjust
field names below if a provider has changed something.
"""
import os, json, time, sys
from datetime import datetime, timezone
import urllib.request
import urllib.parse
import urllib.error

RENTCAST_KEY = os.environ.get("RENTCAST_API_KEY", "")
FRED_KEY = os.environ.get("FRED_API_KEY", "")
CENSUS_KEY = os.environ.get("CENSUS_API_KEY", "")  # optional, raises Census rate limits

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "markets.json")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)


def http_get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode())


def fetch_rentcast_market(zip_code):
    if not RENTCAST_KEY:
        return None
    url = f"https://api.rentcast.io/v1/markets?zipCode={zip_code}"
    headers = {"X-Api-Key": RENTCAST_KEY, "Accept": "application/json"}
    try:
        return http_get_json(url, headers)
    except urllib.error.HTTPError as e:
        print(f"[warn] RentCast HTTP {e.code} for zip {zip_code}: {e.reason}")
    except Exception as e:
        print(f"[warn] RentCast fetch failed for zip {zip_code}: {e}")
    return None


def fetch_fred_series(series_id, limit=1):
    if not FRED_KEY:
        return []
    params = urllib.parse.urlencode({
        "series_id": series_id,
        "api_key": FRED_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    })
    url = f"https://api.stlouisfed.org/fred/series/observations?{params}"
    try:
        data = http_get_json(url)
        return data.get("observations", [])
    except Exception as e:
        print(f"[warn] FRED fetch failed for {series_id}: {e}")
        return []


def fetch_census_population(state_fips, county_fips_full, year):
    # Census Population Estimates Program (PEP). Vintage availability lags
    # the current year by ~1-2 years; if a given `year` 404s, try year-1.
    county_only = county_fips_full[-3:]
    url = (f"https://api.census.gov/data/{year}/pep/population"
           f"?get=POP_{year},NAME&for=county:{county_only}&in=state:{state_fips}")
    if CENSUS_KEY:
        url += f"&key={CENSUS_KEY}"
    try:
        rows = http_get_json(url)
        if len(rows) > 1:
            header, values = rows[0], rows[1]
            return dict(zip(header, values))
    except Exception as e:
        print(f"[warn] Census fetch failed for state {state_fips} county {county_fips_full} year {year}: {e}")
    return None


def main():
    with open(CONFIG_PATH) as f:
        markets = json.load(f)

    now = datetime.now(timezone.utc).isoformat()
    market_results = []
    this_year = datetime.now(timezone.utc).year

    for m in markets:
        entry = {"name": m["name"], "state": m["state"]}

        rc = fetch_rentcast_market(m["zip"])
        if rc:
            entry["rentcast_raw"] = rc
            # RentCast's /markets response nests rental/sale stats; pull the
            # common top-line figures if present, but keep the raw payload
            # too since exact field names can shift between plan tiers.
            rental_stats = rc.get("rentalData", {}) or rc.get("rental", {})
            if isinstance(rental_stats, dict):
                entry["avg_rent"] = rental_stats.get("averageRent") or rental_stats.get("median")
            sale_stats = rc.get("saleData", {}) or rc.get("sale", {})
            if isinstance(sale_stats, dict):
                entry["avg_price"] = sale_stats.get("averagePrice") or sale_stats.get("median")

        # State unemployment rate as a job-market proxy, e.g. series "OHUR", "INUR"
        obs = fetch_fred_series(f'{m["state"]}UR', limit=1)
        if obs:
            entry["state_unemployment_rate"] = obs[0].get("value")
            entry["state_unemployment_date"] = obs[0].get("date")

        # Population growth: compare two consecutive PEP vintages
        state_fips = m["county_fips"][:2]
        pop_a = fetch_census_population(state_fips, m["county_fips"], this_year - 2)
        pop_b = fetch_census_population(state_fips, m["county_fips"], this_year - 3)
        if pop_a and pop_b:
            try:
                p_a = float(pop_a.get(f"POP_{this_year-2}", 0))
                p_b = float(pop_b.get(f"POP_{this_year-3}", 0))
                if p_b:
                    entry["population_growth_pct_yoy"] = round((p_a - p_b) / p_b * 100, 2)
                entry["population"] = p_a
            except Exception as e:
                print(f"[warn] population calc failed for {m['name']}: {e}")

        market_results.append(entry)
        time.sleep(1)  # be polite to free-tier rate limits

    with open(os.path.join(DATA_DIR, "markets_data.json"), "w") as f:
        json.dump({"updated": now, "markets": market_results}, f, indent=2)

    # National macro snapshot
    macro = {"updated": now}
    mort = fetch_fred_series("MORTGAGE30US", limit=1)
    hpi = fetch_fred_series("CSUSHPINSA", limit=13)  # ~13 monthly obs for YoY calc
    unrate = fetch_fred_series("UNRATE", limit=1)

    if mort:
        macro["mortgage_rate_30yr"] = mort[0].get("value")
        macro["mortgage_rate_date"] = mort[0].get("date")
    if unrate:
        macro["national_unemployment_rate"] = unrate[0].get("value")
        macro["national_unemployment_date"] = unrate[0].get("date")
    if len(hpi) >= 13:
        try:
            latest = float(hpi[0]["value"])
            year_ago = float(hpi[12]["value"])
            macro["home_price_index_yoy_pct"] = round((latest - year_ago) / year_ago * 100, 2)
            macro["home_price_index_date"] = hpi[0]["date"]
        except Exception as e:
            print(f"[warn] HPI calc failed: {e}")

    with open(os.path.join(DATA_DIR, "macro_data.json"), "w") as f:
        json.dump(macro, f, indent=2)

    print("Done -> data/markets_data.json, data/macro_data.json")


if __name__ == "__main__":
    if not (RENTCAST_KEY or FRED_KEY):
        print("[warn] No API keys found in environment. Set RENTCAST_API_KEY / FRED_API_KEY "
              "(and optionally CENSUS_API_KEY) before running, or this will write mostly-empty data.")
    main()
