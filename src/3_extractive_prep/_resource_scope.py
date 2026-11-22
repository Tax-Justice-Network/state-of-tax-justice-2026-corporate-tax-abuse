"""Documented payer exclusions from the upstream petroleum and mining scope.

This module loads the cited table of payers that fall outside the upstream petroleum and mining scope
(data/raw/extractive/resource_payer_scope_exclusions.csv) and tells whether a payer is in scope in a given year.

Author: Tax Justice Network. Last updated: 2026-10-07.
"""
import csv
from pathlib import Path

SCOPE_EXCLUSIONS = (Path(__file__).resolve().parents[2] / "data/raw/extractive"
                    / "resource_payer_scope_exclusions.csv")


def load_scope_exclusions(path=SCOPE_EXCLUSIONS):
    """Loads the exclusion table. I keep the original payment facts and control their use through this cited
    table. Every row must give the source country, the company name, the reason and the source URL. A missing start
    or end year leaves the range open on that side."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if not all(row.get(k) for k in ("source_iso3", "company_name", "reason", "source_url")):
            raise ValueError(f"Incomplete resource payer exclusion: {row}")
        row["year_start"] = float(row.get("year_start") or "-inf")
        row["year_end"] = float(row.get("year_end") or "inf")
        if row["year_start"] > row["year_end"]:
            raise ValueError(f"Reversed exclusion years: {row}")
    return rows


def payer_in_scope(source_iso3, company_name, year, exclusions):
    try:
        year = float(year)
    except (ValueError, TypeError):
        return True
    return not any(
        source_iso3 == row["source_iso3"]
        and str(company_name).strip().casefold() == row["company_name"].strip().casefold()
        and row["year_start"] <= year <= row["year_end"]
        for row in exclusions
    )
