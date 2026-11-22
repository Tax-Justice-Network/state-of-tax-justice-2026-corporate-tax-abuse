# %%
"""
3_11 — Parse EITI country revenues.

This script combines the EITI payment-level revenue line items with the EITI API summary
totals into a clean country x year table of total government revenue, with a breakdown by
revenue stream (GFS category).

I use the payment-level line items, not the API alone, because the `/revenue` endpoint of
the EITI API does not consistently fill the payment-type breakdowns for many reporting
countries. The API alone therefore misses the royalty and CIT breakdowns of more than 40
countries. To refresh the old bulk file, download the latest bulk CSV from EITI's data
portal and overwrite the manual-download file below.

Pipeline: Extractive prep, stage 3_11 — ingests the EITI country-revenue
product (the first EITI ingest) and feeds the 3_2x rent-combination stage.

Sources, per (country, year), in this order:
  1. the EITI database export (eiti-database.eiti.org, launched 2026-09-03, covering 1999-2024),
  2. FY2023 revenues read from the EITI reports where neither (1) nor summary data exist
     (PDF extraction, 33 countries),
  3. the old bulk CSV (ends 2019) for everything else.
Where the API has no summary total (years covered only by the PDF extraction), I set
revenue_government_total_usd to the sum of the streams and flag this in total_source.

Section outline (numbers match the cell headings below):
1. Setup.
2. Config and paths.
3. Fetch API data.
4. Build and write table.

Reads:
  data/raw/extractive/eiti_database_government_revenues_2026-10-13.csv — EITI database export
  data/raw/extractive/eiti_reports/_fy2023_pdf_extraction/*_government_revenues.csv — FY2023 from reports
  data/raw/extractive/eiti_revenues_manual_download.csv  — EITI bulk payment-level download (manual)
  https://api.eiti.org/api/v2.0/summary_data              — EITI API summary totals + sector info

Writes:
  data/intermediate/extractive/eiti_revenues.csv          — country x year revenue by GFS stream

Usage:
  python src/3_extractive_prep/3_11_parse_eiti_country_revenues.py

Author: Tax Justice Network.
Last updated: 2026-10-13.
"""

# %% MARK: 1. Setup
import csv
import os
import requests
import time
import json
from collections import defaultdict

# %% MARK: 2. Config and paths
from _paths import RAW, EXT_INT  # noqa: E402
RAW_CSV = RAW / "extractive" / "eiti_revenues_manual_download.csv"          # external download (ends 2019)
DB_CSV = RAW / "extractive" / "eiti_database_government_revenues_2026-10-13.csv"   # EITI database export
PDF_DIR = RAW / "extractive" / "eiti_reports" / "_fy2023_pdf_extraction"           # FY2023 read from reports
# I rename the columns of the database export and the PDF extraction to the bulk CSV's names used below.
DB_RENAME = {"country_iso3": "iso3", "country_name": "country", "gfs_name": "gfs_description",
             "revenue_value_usd": "value_reported_as_USD"}


# In the FY2023 report extraction, I convert the reports that state no exchange rate (PHL, TGO,
# TJK, TTO, UKR, KGZ, NER, ALB, CIV, DEU) at the World Bank official annual rate (PA.NUS.FCRF) of
# the year in which the fiscal year ends. I leave out KAZ FY2023 because its report contradicts
# itself (Tengizchevroil alone is above the all-company total).
PDF_EXCLUDE = {("KAZ", "2023")}


def _wb_fx():
    import csv as _csv
    path = RAW / "macro_variables" / "wb_fx_official_rate_2026-02.csv"
    lines = open(path, encoding="utf-8-sig").readlines()
    fx = {}
    for row in _csv.DictReader(lines[4:]):
        for k, v in row.items():
            if k and k.isdigit() and v:
                fx[(row["Country Code"], int(k))] = float(v)
    return fx
OUTPUT_CSV = EXT_INT / "eiti_revenues.csv"                   # processed output (intermediate folder)
BASE_URL = "https://api.eiti.org/api/v2.0"


# %% MARK: 3. Fetch API data
def fetch_summary_data():
    """Fetches all summary_data records from the EITI API, page by page."""
    session = requests.Session()
    all_data = []
    page = 1
    total = None

    while True:
        url = f"{BASE_URL}/summary_data?page={page}"
        for attempt in range(5):
            try:
                r = session.get(url, timeout=30)
                r.raise_for_status()
                break
            except Exception as e:
                if attempt < 4:
                    time.sleep(2 ** attempt)
                else:
                    raise

        data = r.json()
        if total is None:
            total = data.get("count", 0)
            print(f"  Total summary records: {total}")

        records = data.get("data", [])
        if not records:
            break

        all_data.extend(records)
        page += 1
        print(f"  Fetched {len(all_data)} / {total}...", end="\r")

        # I stop when there is no next page.
        if "next" not in data or not data["next"]:
            break

    print(f"  Fetched {len(all_data)} / {total} - done.")
    return all_data


# %% MARK: 4. Build and write table
def main():
    # Step 1: I fetch the summary data from the API for the totals and the sector information.
    print("Step 1: Fetching summary data from EITI API...")
    summaries = fetch_summary_data()

    summary_lookup = {}
    for s in summaries:
        iso3 = s.get("country.iso3", "")
        country_name = s.get("country.label", "")
        # I take the year from the ID (e.g. "AF2009" gives "2009").
        sid = s.get("id", "")
        year = sid[2:] if len(sid) > 2 else ""

        summary_lookup[(iso3, year)] = {
            "country_name": country_name,
            "country_iso2": s.get("country.iso2", ""),
            "country_iso3": iso3,
            "year": year,
            "revenue_government_total_usd": s.get("revenue_government_sum"),
            "local_currency": s.get("currency"),
            "currency_rate_to_usd": s.get("currency_rate"),
            "sector_oil": s.get("sector_oil"),
            "sector_gas": s.get("sector_gas"),
            "sector_mining": s.get("sector_mining"),
        }

    print(f"  {len(summary_lookup)} country-year records from API.\n")

    # Step 2: I read the revenue line items. The database export comes first, then the FY2023 report
    # extraction, then the old bulk CSV.
    print("Step 2: Reading revenue line items...")

    def _read(path, rename=None, tag=""):
        out = []
        with open(path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if rename:
                    row = {rename.get(k, k): v for k, v in row.items()}
                row["_source"] = tag
                out.append(row)
        return out

    db_rows = _read(DB_CSV, DB_RENAME, "eiti_database") if DB_CSV.exists() else []
    pdf_rows = []
    for fp in sorted(PDF_DIR.glob("*_government_revenues.csv")) if PDF_DIR.exists() else []:
        pdf_rows += _read(fp, DB_RENAME, "eiti_report_pdf")
    old_rows = _read(RAW_CSV, None, "bulk_csv_2019")
    have_db = {(r.get("iso3", ""), str(r.get("year", ""))) for r in db_rows}
    pdf_rows = [r for r in pdf_rows if (r.get("iso3", ""), str(r.get("year", ""))) not in have_db]
    pdf_rows = [r for r in pdf_rows if (r.get("iso3", ""), str(r.get("year", ""))) not in PDF_EXCLUDE]
    _fx, n_fx = _wb_fx(), 0
    for r in pdf_rows:                       # no rate in the report: I use the World Bank annual rate
        if not (r.get("value_reported_as_USD") or "").strip() and (r.get("revenue_value") or "").strip():
            cur = (r.get("reporting_currency") or r.get("currency_code") or "").upper()
            yr = int(float(r.get("year") or 0))
            rate = 1.0 if cur == "USD" else _fx.get((r.get("iso3", ""), yr))
            if rate:
                r["value_reported_as_USD"] = str(float(r["revenue_value"]) / rate)
                r["_source"] = "eiti_report_pdf_wbfx"
                n_fx += 1
    print(f"  report extraction: {n_fx} rows converted at the World Bank rate (no rate in the report)")
    have_new = have_db | {(r.get("iso3", ""), str(r.get("year", ""))) for r in pdf_rows}
    old_rows = [r for r in old_rows if (r.get("iso3", ""), str(r.get("year", ""))) not in have_new]
    rev_rows = db_rows + pdf_rows + old_rows
    source_of = {}
    for r in rev_rows:
        source_of.setdefault((r.get("iso3", ""), str(r.get("year", ""))), r["_source"])
    print(f"  {len(rev_rows)} revenue line items (database {len(db_rows)}, report extraction "
          f"{len(pdf_rows)}, old bulk CSV {len(old_rows)}).\n")

    # Step 3: I aggregate by country, year and GFS description (revenue stream).
    print("Step 3: Aggregating revenues by country, year, and revenue stream...")

    # I use the GFS description as the revenue category and aggregate at that level, which is broader
    # than the individual stream names.
    country_year_totals = defaultdict(float)
    country_year_streams = defaultdict(lambda: defaultdict(float))
    country_year_info = {}
    gfs_freq = defaultdict(int)

    for row in rev_rows:
        iso3 = row.get("iso3", "")
        year = row.get("year", "")
        country = row.get("country", "")
        gfs_desc = row.get("gfs_description", "").strip()
        if not gfs_desc:
            gfs_desc = "Unclassified"

        try:
            value_usd = float(row.get("value_reported_as_USD", 0) or 0)
        except (ValueError, TypeError):
            value_usd = 0.0

        key = (iso3, year)
        country_year_totals[key] += value_usd
        country_year_streams[key][gfs_desc] += value_usd

        if key not in country_year_info:
            country_year_info[key] = {
                "country_name": country,
                "country_iso3": iso3,
                "year": year,
            }

        gfs_freq[gfs_desc] += 1

    print(f"  {len(country_year_totals)} country-year combinations from bulk CSV.")
    print(f"  {len(gfs_freq)} distinct GFS categories.\n")

    # I sort the GFS categories by frequency.
    sorted_gfs = sorted(gfs_freq.items(), key=lambda x: -x[1])
    print("  GFS revenue categories (by frequency):")
    for cat, freq in sorted_gfs:
        print(f"    {cat}: {freq} line items")

    # Every GFS category becomes a column.
    gfs_columns = [cat for cat, _ in sorted_gfs]

    # Step 4: I merge the line items with the API summary data and write the output.
    print(f"\nStep 4: Writing output CSV...")

    # I collect the country-year keys of both sources.
    all_keys = set(country_year_totals.keys()) | set(summary_lookup.keys())

    base_cols = [
        "country_name", "country_iso2", "country_iso3", "year",
        "revenue_government_total_usd", "total_source", "line_item_source",
        "revenue_from_csv_sum_usd",
        "local_currency", "currency_rate_to_usd",
        "sector_oil", "sector_gas", "sector_mining",
    ]
    all_cols = base_cols + gfs_columns

    rows = []
    for key in sorted(all_keys, key=lambda k: (country_year_info.get(k, summary_lookup.get(k, {})).get("country_name", ""), k[1])):
        iso3, year = key
        api_info = summary_lookup.get(key, {})
        csv_info = country_year_info.get(key, {})

        row = {}
        row["country_name"] = api_info.get("country_name") or csv_info.get("country_name", "")
        row["country_iso2"] = api_info.get("country_iso2", "")
        row["country_iso3"] = iso3
        row["year"] = year
        row["revenue_government_total_usd"] = api_info.get("revenue_government_total_usd", "")
        row["total_source"] = "eiti_api_summary" if row["revenue_government_total_usd"] not in ("", None) else ""
        if row["total_source"] == "" and country_year_totals.get(key):   # PDF-only / database-only years
            row["revenue_government_total_usd"] = country_year_totals[key]
            row["total_source"] = "sum_of_line_items"
        row["line_item_source"] = source_of.get(key, "")
        row["revenue_from_csv_sum_usd"] = country_year_totals.get(key, "")
        row["local_currency"] = api_info.get("local_currency", "")
        row["currency_rate_to_usd"] = api_info.get("currency_rate_to_usd", "")
        row["sector_oil"] = api_info.get("sector_oil", "")
        row["sector_gas"] = api_info.get("sector_gas", "")
        row["sector_mining"] = api_info.get("sector_mining", "")

        for gfs in gfs_columns:
            val = country_year_streams.get(key, {}).get(gfs, "")
            row[gfs] = val if val != 0 else ""

        rows.append(row)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone! Saved {len(rows)} rows to:")
    print(f"  {OUTPUT_CSV}")
    print(f"\nColumns ({len(all_cols)} total):")
    for c in all_cols:
        print(f"  - {c}")

    # Quick summary statistics
    print(f"\nSummary statistics:")
    countries = set(r["country_name"] for r in rows)
    years = set(r["year"] for r in rows)
    print(f"  Countries: {len(countries)}")
    print(f"  Year range: {min(years)} - {max(years)}")
    print(f"  Total rows: {len(rows)}")


if __name__ == "__main__":
    main()
