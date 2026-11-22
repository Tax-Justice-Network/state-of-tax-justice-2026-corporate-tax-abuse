# %%
"""
1b (pass 2 — presence) — Distinct-group (hq_iso3, market_iso3) presence matrix.

This script builds the matrix of distinct groups per headquarters country and market
that the extrapolation test of the market key in 1a_destination_based_sales.py uses
(its Orbis-presence variable), and it is the only place that builds it. I derive the matrix from the entity universe
(cbcr_universe_entities.csv, written by the pass-2 assemble step) rather than
streaming the Links file again. Every member entity already carries its in-scope GUO
and the ISO3 codes of both the member and the GUO, so the matrix is a single group-by.

    n_groups   = COUNT(DISTINCT guo_bvd_id) per (hq_iso3, market_iso3)
                 = distinct in-scope (>=EUR 750M consolidated) GUO groups headquartered
                   in `hq` with at least one entity in `market`.
    n_entities = number of member entities (QA only).

I count distinct groups on purpose. Two subsidiaries of one group in a market count
once, so n_groups measures how many groups are present in a market, not the size of
the full ownership universe.

Section outline (numbers match the cell headings below):
1. Setup.
2. Config.
3. Build matrix.

Pipeline step 1b (Orbis CbCR-universe) — final pass: groups the entity universe of
the pass-2 assemble step into the matrix that 1a uses.

Reads:
  data/intermediate/extractive/cbcr_universe_entities.csv   — member-entity universe (pass-2 assemble)

Writes:
  data/intermediate/extractive/cbcr_universe_presence.csv   — presence matrix; columns hq_iso3, market_iso3, n_groups, n_entities

Usage:
  python src/1b_orbis_universe/1b_4_presence.py

Author: Tax Justice Network (based on the method of García-Bernardo and Janský).
Last updated: 2026-11-23.
"""
# %% MARK: 1. Setup
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

from _paths import EXT_INT

# %% MARK: 2. Config
ENT = EXT_INT / "cbcr_universe_entities.csv"
OUT = EXT_INT / "cbcr_universe_presence.csv"


# %% MARK: 3. Build matrix
def main():
    ent = pd.read_csv(ENT, usecols=["hq_iso3", "country_iso3", "guo_bvd_id"])
    print(f"entity universe: {len(ent):,} rows  ({ENT})", flush=True)

    pres = (
        ent.groupby(["hq_iso3", "country_iso3"])
        .agg(n_groups=("guo_bvd_id", "nunique"), n_entities=("guo_bvd_id", "size"))
        .reset_index()
        .rename(columns={"country_iso3": "market_iso3"})
        .sort_values(["hq_iso3", "market_iso3"])
    )

    pres.to_csv(OUT, index=False)
    print(
        f"wrote {OUT}\n  {len(pres):,} (hq_iso3, market_iso3) pairs; "
        f"{pres['hq_iso3'].nunique()} HQ countries, "
        f"{pres['market_iso3'].nunique()} market countries; "
        f"total distinct groups summed = {pres['n_groups'].sum():,}",
        flush=True,
    )


if __name__ == "__main__":
    main()
