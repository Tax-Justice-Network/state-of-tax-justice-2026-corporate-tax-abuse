# %%
"""
3_17 — Pull BGS mineral production.

This script pulls the annual production volumes of the British Geological Survey (BGS)
World Mineral Statistics for 2016-2023 through the BGS OGC API and writes them to a long
CSV.

Endpoint: https://ogcapi.bgs.ac.uk/collections/world-mineral-statistics/items
   - The filter `bgs_statistic_type_trans=Production` drops trade, refining and the other
     statistic types.
   - The per-year filter `year=YYYY-01-01T00:00:00` works (an RFC3339-like prefix).
     Generic datetime range filtering is broken on this API as of 2026-04, so I iterate
     over the years 2016 to 2023.
   - Pagination works with `?offset=N&limit=K`. The server fails on large limits (1000 or
     more resets the connection), while 200-500 is reliable.

I use BGS because the other mineral sources of the combined-rent panel (3_24) leave gaps.
EITI has mineral templates for only about 30 countries, and WB has not published 2022 for
all countries. BGS publishes an annual mineral yearbook that covers more than 200 countries
with about 80 commodities and is current to about 2023. It is therefore the best replacement
for the 2022 gap in mineral coverage (and a good cross-check elsewhere).

I map `hs_code` from `bgs_commodity_trans` to the same HS-4 buckets that the rest of the
pipeline uses (see HS_TO_CATEGORY in 3_12_parse_eiti_production_volumes.py). Commodities
outside the pricing table (cement, salt, aggregates, ferro-alloys, refined-metal stages,
etc.) get hs_code='' so that 3_24 can filter them out.

Section outline (numbers match the cell headings below):
1. Setup.
2. Config and HS mapping.
3. Fetch production records.
4. Parse, write, and report.

Pipeline: Extractive prep, stage 3_17 — ingests BGS mineral production and feeds
the 3_2x rent-combination stage.

Reads:
  https://ogcapi.bgs.ac.uk/collections/world-mineral-statistics/items  — BGS World Mineral Statistics OGC API

Writes:
  data/raw/extractive/bgs_mineral_production.csv  — iso3, year, commodity, sub_commodity,
      bgs_commodity_code, hs_code, production, unit, source

Usage:
  python src/3_extractive_prep/3_17_pull_bgs_minerals.py

Author: Tax Justice Network.
Last updated: 2026-11-23.
"""

# %% MARK: 1. Setup
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import RAW

# %% MARK: 2. Config and HS mapping
OUT_PATH = RAW / "extractive" / "bgs_mineral_production.csv"

API_BASE = "https://ogcapi.bgs.ac.uk/collections/world-mineral-statistics/items"
UA = "tjn-research/0.1"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}

YEARS = list(range(2016, 2024))   # 2016 to 2023 inclusive
PAGE_LIMIT = 500                    # the server is stable at 200-500 and resets at 1000 or more
MAX_RETRIES = 4

# ---- BGS commodity (`bgs_commodity_trans`) -> HS-4 mineral code ----
# Only the commodities whose HS bucket is priced in MINERAL_PRICES (3_24) get a non-empty
# hs_code, so that they flow into the rent estimate. I keep the rest in the CSV (with
# hs_code="") for completeness and later use.
#
# HS reference (matches HS_TO_CATEGORY in 3_12_parse_eiti_production_volumes.py):
#   2510 phosphates    2601 iron ore      2602 manganese
#   2603 copper        2604 nickel        2605 cobalt
#   2606 bauxite       2607 lead          2608 zinc
#   2609 tin           2610 chromium      2611 tungsten
#   2613 molybdenum    2614 titanium      2615 Nb/Ta/V/Zr
#   2616 precious-mtl  2617 other ores    7102 diamonds
#   7106 silver        7108 gold          7110 PGM
#
# I point each BGS "X, mine" / "X ore" row at the HS code of the ore stage of the contained
# metal, so that volume × USD per tonne of metal content matches MINERAL_PRICES in 3_24. I
# deliberately do not map the refined-metal rows ("X, refined", "X, smelter", "iron, pig",
# "steel, crude", "alumina", "aluminium primary"), because (a) they double-count the primary
# mine stage already counted under "X, mine" / "bauxite" / "iron ore", and (b) MINERAL_PRICES
# anchors on the ore price, not on the refined-metal price.
BGS_TO_HS = {
    # Iron / steel — keep ore stage, drop pig iron and crude steel
    "iron ore":                   "2601",
    # Manganese
    "manganese ore":              "2602",
    # Copper — mine production (metal content)
    "copper, mine":               "2603",
    # Nickel — mine production (metal content)
    "nickel, mine":               "2604",
    # Cobalt — mine production (metal content)
    "cobalt, mine":               "2605",
    # Bauxite (aluminium ore)
    "bauxite":                    "2606",
    # Lead
    "lead, mine":                 "2607",
    # Zinc
    "zinc, mine":                 "2608",
    # Tin
    "tin, mine":                  "2609",
    # Chromium
    "chromium ores and concentrates": "2610",
    # Tungsten
    "tungsten, mine":             "2611",
    # Molybdenum
    "molybdenum, mine":           "2613",
    # Titanium
    "titanium minerals":          "2614",
    # Nb/Ta/V/Zr group (HS 2615)
    "tantalum and niobium minerals": "2615",
    "vanadium, mine":             "2615",
    "zirconium minerals":         "2615",
    # Other ores bucket (HS 2617). Antimony, bismuth and uranium have no dedicated 4-digit
    # HS code but belong in 2617.
    "antimony, mine":             "2617",
    "bismuth, mine":              "2617",
    "uranium":                    "2617",
    # Phosphates
    "phosphate rock":             "2510",
    # Precious stones / metals
    "diamond":                    "7102",
    "silver, mine":               "7106",
    "gold, mine":                 "7108",
    "platinum group metals, mine": "7110",
    # Lithium and rare earths have no priced HS bucket in the pipeline. I leave them blank
    # so that they stay informational.
}


# %% MARK: 3. Fetch production records
def fetch_year(year: int):
    """Returns all production records of one calendar year.

    The stream of all Production records times out at BGS (the unfiltered query is too
    large to compute on the server). The per-year filter format `year=YYYY-01-01T00:00:00`
    works for some years (2016, 2022 and 2023 in practice) and returns non-JSON for others.
    I try each year, tolerate the failure of a year, and report what I got.
    """
    rows = []
    offset = 0
    total = None
    while True:
        qs = [
            ("bgs_statistic_type_trans", "Production"),
            ("year", f"{year}-01-01T00:00:00"),
            ("limit", str(PAGE_LIMIT)),
            ("offset", str(offset)),
        ]
        url = API_BASE + "?" + urllib.parse.urlencode(qs)
        req = urllib.request.Request(url, headers=HEADERS)

        for attempt in range(MAX_RETRIES):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    raw = r.read()
                payload = json.loads(raw)
                break
            except json.JSONDecodeError as exc:
                # The server returned HTML or an error page for this year, so I give up on it.
                print(f"    [skip] year={year}: non-JSON response (BGS year "
                      f"filter rejection)")
                return rows
            except Exception as exc:
                if attempt == MAX_RETRIES - 1:
                    print(f"    [fail] year={year} offset={offset}: {exc}")
                    return rows
                wait = 2 ** attempt
                print(f"    [retry {attempt+1}] year={year} offset={offset}: "
                      f"{exc} (sleeping {wait}s)")
                time.sleep(wait)

        feats = payload.get("features", [])
        if total is None:
            total = int(payload.get("numberMatched", 0) or 0)
        if not feats:
            break
        rows.extend(feats)
        offset += len(feats)
        if offset >= total:
            break
        time.sleep(0.2)  # be nice to the server
    return rows


# %% MARK: 4. Parse, write, and report
def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    all_rows = []
    by_year = Counter()
    YEARS_SET = set(YEARS)

    print(f"Pulling BGS Production records year-by-year for "
          f"{YEARS[0]}-{YEARS[-1]} (limit={PAGE_LIMIT})...")
    feats_all = []
    for y in YEARS:
        print(f"  year={y}...", end="", flush=True)
        feats = fetch_year(y)
        print(f" {len(feats):>5} records returned")
        for f in feats:
            f.setdefault("_year_hint", y)
        feats_all.extend(feats)
    print(f"  Total returned: {len(feats_all):,}")

    for f in feats_all:
        p = f.get("properties", {}) or {}
        iso3 = (p.get("country_iso3_code") or "").strip().upper()
        if len(iso3) != 3 or not iso3.isalpha():
            continue
        # year is a date-time string like '2017-01-01T00:00:00'. I take its first four
        # characters.
        yr_str = (p.get("year") or "")[:4]
        try:
            y = int(yr_str)
        except ValueError:
            y = f.get("_year_hint")
            if y is None:
                continue
        if y not in YEARS_SET:
            continue
        commodity = p.get("bgs_commodity_trans")
        if commodity is None:
            continue
        sub = p.get("bgs_sub_commodity_trans") or ""
        qty = p.get("quantity")
        if qty is None:
            continue
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            # I drop the true zero and not-produced rows. Keeping them would only bloat the
            # CSV and confuse the downstream coverage statistics.
            continue
        unit = p.get("units") or ""
        code = p.get("bgs_commodity_code")
        hs = BGS_TO_HS.get(str(commodity).strip().lower(), "")
        all_rows.append({
            "iso3": iso3,
            "year": y,
            "commodity": commodity,
            "sub_commodity": sub,
            "bgs_commodity_code": code if code is not None else "",
            "hs_code": hs,
            "production": qty,
            "unit": unit,
            "source": "BGS_WMS",
        })
        by_year[y] += 1

    if not all_rows:
        print("No rows produced; aborting.")
        return

    cols = ["iso3", "year", "commodity", "sub_commodity",
            "bgs_commodity_code", "hs_code", "production", "unit", "source"]
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in all_rows:
            w.writerow(r)
    print(f"\nWrote {len(all_rows):,} rows -> {OUT_PATH}")

    # ---- Coverage statistics ----
    print("\nRows kept by year:")
    for y in YEARS:
        print(f"  {y}: {by_year[y]:>6,}")

    # Top 20 commodities by row count
    by_commod = Counter()
    by_hs = Counter()
    for r in all_rows:
        by_commod[r["commodity"]] += 1
        by_hs[r["hs_code"] or "(unmapped)"] += 1
    print("\nTop 20 commodities by row count:")
    for c, n in by_commod.most_common(20):
        hs = BGS_TO_HS.get(str(c).strip().lower(), "")
        tag = f"HS {hs}" if hs else "(no HS)"
        print(f"  {n:>6,}  {c:<35s}  {tag}")

    print("\nRows by HS bucket (the priced ones flow into 3_24 rent calc):")
    for hs, n in sorted(by_hs.items()):
        print(f"  {hs:<12s}  {n:>6,}")

    # Spot-check African mineral producers in 2022
    afr = ["COD", "GIN", "MRT", "MLI", "BFA", "GHA", "TZA", "ZMB",
           "ZAF", "NER", "NGA", "MOZ", "MDG"]
    print("\nAfrican producer 2022 spot check (commodity counts, mapped HS only):")
    for iso in afr:
        cs = sorted({
            r["commodity"] for r in all_rows
            if r["iso3"] == iso and r["year"] == 2022 and r["hs_code"]
        })
        if cs:
            print(f"  {iso}: {len(cs):>2}  {', '.join(cs)}")
        else:
            print(f"  {iso}: (none)")


if __name__ == "__main__":
    main()
