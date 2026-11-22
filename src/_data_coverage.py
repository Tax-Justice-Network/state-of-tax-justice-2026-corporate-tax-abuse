"""Data coverage of each country's estimate, and the mark for estimates that rest on few observations.

This module counts, for every jurisdiction, the headquarter countries whose multinationals report activity there in
the latest year. A country's estimate for a year rests on these reports. Where fewer than three headquarter countries
report, the country tables mark the estimate (footnote [2], "few observations"). The mark is for presentation only.
The estimates are unchanged.

    few observations  <=>  fewer than 3 headquarter countries report activity in the country in the latest year

I count the foreign cells of the headline estimate of the reported-only sample (iso_parent != iso_partner). This is
the sample after the rule for partial reporters, so the count is the number of headquarter countries the estimate
rests on. The country tables show the latest year only, which is why the mark looks at that year alone. I use the
same counts for the tables of the sample with imputed rows, because imputed rows add no evidence. A jurisdiction
that appears only in imputed rows has no reporting headquarter country and is marked.

Usage:
    from _data_coverage import coverage_table, thin_iso_set
    cov = coverage_table()          # DataFrame indexed by iso_partner
    thin = thin_iso_set(cov)        # set of marked ISO3 codes
`coverage_table` also writes data_coverage_by_partner.csv to the country_overview folder across samples.
"""
# %% MARK: 1. Setup
import os
import sys

import pandas as pd

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SRC_DIR)
import config  # noqa: E402
from config import data_final  # noqa: E402

# %% MARK: 2. Threshold and footnote
PARENTS_MIN = 3                                  # headquarter countries that must report in the latest year
LATEST_YEAR = config.last_year
# The headline estimate: sales and employees with the market key, domestic and foreign effective tax rates, gains
# valued at the statutory rate.
HEADLINE = "sales_employees_destmnedds__etrdef_domfor__etrmax_inf__loss_cit_gain_etr"

FOOTNOTE_TEXT = (
    f"[2] Few observations: in {LATEST_YEAR}, the multinationals of fewer than {PARENTS_MIN} headquarter countries "
    "report activity in the country. Interpret the estimate with caution."
)


# %% MARK: 3. Coverage counts and the mark for few observations
def coverage_table(write=True):
    """Return the coverage counts per jurisdiction: the foreign cells and headquarter countries of the headline
    estimate over all years and in the latest year, and the mark thin_data."""
    path = os.path.join(str(config.estimates_dir("reported_only", "excl_resource")), "tables", "excl_resource",
                        f"misalignment__{HEADLINE}.csv")
    m = pd.read_csv(path, usecols=["iso_parent", "iso_partner", "year"], low_memory=False)
    f = m[m["iso_parent"] != m["iso_partner"]]
    latest = f[f["year"] == LATEST_YEAR]
    g = pd.DataFrame({
        "n_cells": f.groupby("iso_partner").size(),
        "n_parents": f.groupby("iso_partner")["iso_parent"].nunique(),
        "n_years": f.groupby("iso_partner")["year"].nunique(),
        "n_parents_latest": latest.groupby("iso_partner")["iso_parent"].nunique(),
    })
    # Jurisdictions that appear only in imputed rows have no cell in the reported-only sample. I add them with a
    # count of zero, so that the tables of the sample with imputed rows mark them.
    partners = pd.read_csv(f"{data_final}cbcr_main_disaggregated.csv", usecols=["iso_partner"],
                           low_memory=False)["iso_partner"].dropna().unique()
    countries = [p for p in partners if p not in config.non_countries]
    g = g.reindex(g.index.union(countries)).fillna(0).astype(int)
    g.index.name = "iso_partner"
    g["thin_data"] = g["n_parents_latest"] < PARENTS_MIN
    if write:
        tables_dir, _ = config.output_dirs("deliverables/country_sheet")
        out = os.path.join(tables_dir, "data_coverage_by_partner.csv")
        g.sort_values(["thin_data", "n_parents_latest", "n_cells"], ascending=[False, True, True]).to_csv(out)
    return g


def thin_iso_set(cov=None):
    """Return the ISO3 codes of the jurisdictions marked for few observations."""
    if cov is None:
        cov = coverage_table(write=False)
    return set(cov.index[cov["thin_data"]])
