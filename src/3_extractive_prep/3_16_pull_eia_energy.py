# %%
"""
3_16 — Pull EIA energy production.

This script pulls the annual production of crude oil, natural gas and coal from the EIA
International Energy Statistics, by country, for 2016-2023.

It reads EIA_API_KEY from .env at the repository root (gitignored) or from an environment
variable. A free key can be registered at https://www.eia.gov/opendata/register.php (instant).

Notes:
  - EIA uses ISO3-like three-letter codes for countries and special codes such as 'WORL',
    'OPEC' or 'R...' for aggregates, which I filter out.
  - Crude oil is reported in MBBL/D (thousand barrels per day, annual average). The
    downstream rent calculation multiplies it by 365 to get the annual barrels.
  - Natural gas is in BCF (billion cubic feet) per year.
  - Coal is in thousand metric tonnes per year (EIA unit MT).

Section outline (numbers match the cell headings below):
1. Setup.
2. Load EIA_API_KEY from .env if it is not already in the environment.
3. Config and fuels.
4. Fetch production series.
5. Run and write output.

Pipeline: Extractive prep, stage 3_16 — ingests EIA energy production and feeds
the 3_2x rent-combination stage.

Reads:
  https://api.eia.gov/v2/international/data/  — EIA International Energy Statistics API (needs EIA_API_KEY)

Writes:
  data/raw/extractive/eia_energy_production.csv  — iso3, year, fuel, production, unit, source

Usage:
  python src/3_extractive_prep/3_16_pull_eia_energy.py

Author: Tax Justice Network.
Last updated: 2026-07-25.
"""

# %% MARK: 1. Setup
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# %% MARK: 2. Load EIA_API_KEY from .env if it is not already in the environment
def _load_dotenv(repo_root: Path):
    f = repo_root / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


REPO_ROOT = Path(__file__).resolve().parents[2]
_load_dotenv(REPO_ROOT)

API_KEY = os.environ.get("EIA_API_KEY")
if not API_KEY:
    sys.exit(
        "EIA_API_KEY not found. Add a line `EIA_API_KEY=...` to "
        f"{REPO_ROOT / '.env'} (free key at "
        "https://www.eia.gov/opendata/register.php)."
    )

# %% MARK: 3. Config and fuels
from _paths import RAW

OUT = RAW / "extractive" / "eia_energy_production.csv"
BASE = "https://api.eia.gov/v2/international/data/"
UA = "tjn-research/0.1"

# product_id -> (fuel_label, unit_filter, unit_label). I found the productIds through
# /v2/international/data/?facets[activityId][]=1 (production) on a 2021 sample. EIA returns
# each series in several units, and I pick one unit per fuel.
FUELS = {
    "53": ("crude_oil_lease_condensate", "TBPD", "thousand_barrels_per_day"),
    "26": ("natural_gas_dry",            "BCF",  "billion_cubic_feet"),
    "7":  ("coal_total",                 "MT",   "thousand_tonnes"),
    "11": ("coal_anthracite",            "MT",   "thousand_tonnes"),
    "12": ("coal_bituminous",            "MT",   "thousand_tonnes"),
    "14": ("coal_lignite",               "MT",   "thousand_tonnes"),
}
YEARS = set(range(2016, 2024))


# %% MARK: 4. Fetch production series
def fetch(product_id: str, unit: str):
    rows = []
    offset = 0
    page = 5000
    while True:
        qs = [
            ("api_key", API_KEY),
            ("frequency", "annual"),
            ("data[0]", "value"),
            ("facets[productId][]", product_id),
            ("facets[activityId][]", "1"),  # production
            ("facets[unit][]", unit),
            ("start", "2016"),
            ("end", "2023"),
            ("offset", str(offset)),
            ("length", str(page)),
            ("sort[0][column]", "period"),
            ("sort[0][direction]", "asc"),
        ]
        url = BASE + "?" + urllib.parse.urlencode(qs, doseq=True)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    payload = json.loads(r.read())
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
        data = payload.get("response", {}).get("data", [])
        total = int(payload.get("response", {}).get("total", 0) or 0)
        rows.extend(data)
        offset += len(data)
        if not data or offset >= total:
            break
        time.sleep(0.25)
    return rows


# %% MARK: 5. Run and write output
def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n_total = 0
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["iso3", "year", "fuel", "production", "unit", "source"])
        for pid, (fuel, unit_filter, unit_label) in FUELS.items():
            print(f"  Fetching {fuel} (productId={pid}, unit={unit_filter})...",
                  end="", flush=True)
            rows = fetch(pid, unit_filter)
            n_kept = 0
            for row in rows:
                cc = (row.get("countryRegionId") or "").strip()
                if len(cc) != 3 or not cc.isalpha():
                    continue
                try:
                    year = int(row.get("period"))
                except (TypeError, ValueError):
                    continue
                if year not in YEARS:
                    continue
                val = row.get("value")
                if val in (None, "", "--", "NA"):
                    continue
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    continue
                w.writerow([cc.upper(), year, fuel, val, unit_label,
                            f"EIA_INTL_v2:productId={pid}"])
                n_kept += 1
            print(f" {n_kept} rows kept (of {len(rows)} returned)")
            n_total += n_kept
    print(f"\nWrote {n_total:,} rows -> {OUT}")


if __name__ == "__main__":
    main()
