"""This script fetches the canonical GDP series (WB WDI NY.GDP.MKTP.CD, GDP in current
US$) for the CbCR window and writes the single GDP file used across the repository.

It is the one GDP series per country and year in the repository: `1_clean.py` and
`1a_destination_based_sales.py` read it through `config.canonical_gdp_data`.
The file is a *dated* snapshot, so the pipeline stays reproducible between
refreshes. To refresh it, point `config.canonical_gdp_data` at a new dated file
name and run this script, which writes to that path.

    python src/_fetch_canonical_gdp.py

Writes: the file named by `config.canonical_gdp_data`
  (currently data/raw/macro_variables/wb_gdp_current_usd_2026-08.csv, with columns iso3, year, gdp_current_usd)
"""
import csv
import json
import os
import urllib.request
from datetime import date

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys as _sys
_sys.path.insert(0, os.path.join(_ROOT, "src"))
import config as _cfg
OUT = os.path.join(_ROOT, "data", "raw", os.path.relpath(_cfg.canonical_gdp_data, _cfg.data_raw))
INDICATOR = "NY.GDP.MKTP.CD"
YEARS = f"{_cfg.first_year}:{_cfg.last_year}"   # the analysis window, from config


def main():
    rows, page = [], 1
    while True:
        url = (f"https://api.worldbank.org/v2/country/all/indicator/{INDICATOR}"
               f"?format=json&per_page=8000&date={YEARS}&page={page}")
        with urllib.request.urlopen(url) as r:
            meta, data = json.load(r)
        for x in data or []:
            if x["value"] is not None:
                rows.append((x["countryiso3code"], int(x["date"]), x["value"]))
        if page >= meta["pages"]:
            break
        page += 1

    import pycountry
    iso_ok = {c.alpha_3 for c in pycountry.countries}
    rows = sorted(t for t in rows if t[0] in iso_ok)   # drop WB aggregate rows

    hdr = (
        f"# Canonical GDP: World Bank WDI indicator {INDICATOR} (GDP, current US$),\n"
        f"# all reporting countries, {YEARS.replace(':', '-')}. Fetched {date.today()} from\n"
        f"# https://api.worldbank.org/v2/country/all/indicator/{INDICATOR} . WB aggregate\n"
        "# rows dropped (iso3 filtered against pycountry). SINGLE canonical GDP for the repo\n"
        "# (CbCR pipeline + extractive WB-GDP reference). Refresh: re-run this script.\n"
    )
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        f.write(hdr)
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["iso3", "year", "gdp_current_usd"])
        w.writerows(rows)
    print(f"wrote {OUT}: {len(rows)} rows")


if __name__ == "__main__":
    main()
