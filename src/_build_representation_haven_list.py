"""Re-evaluate the TAX_HAVENS_REPRESENTATION rule on the current headline run.

This script re-evaluates the rule by which config.py shows a jurisdiction as a tax haven (the
"tax_haven" income group). A jurisdiction is shown as a tax haven if and only if
  (1) it is on the GB cleaning list (TAX_HAVENS_CLEANING), or
  (2) its CTHI-2025 Haven Score is at least CTHI_MIN and it booked inward-shifted profit
      (reported_profit - theoretical_profit > 0) in at least MIN_YEARS years of the multi-year window
      config.PAPER_YEARS (the analysis years excluding 2020) on the headline specification
      (reported-only / excl_resource / sales_employees_destmnedds / etrdef_domfor / etrmax_inf), or
  (3) it is a manual substance keep (config._EXTRA_MANUAL).

The outcome leg (2) is hard-coded in config.py (`_EXTRA_CTHI_GE65_2YR_SHIFT`) because the list feeds no
estimate. This script evaluates the rule on the headline run and reports where the result differs from
the hard-coded set. It does not edit config.py: any change to the list is made there by hand.

Usage (from the repository root, after 5_estimate_profit_shifting.py has run
the headline specification on the reported-only excl_resource dataset and 6 has
consolidated it):
    python src/_build_representation_haven_list.py

Writes output/diagnostics/haven_list_reevaluation/tables/
    inward_shift_years_by_jurisdiction.csv   per-jurisdiction shift years, CTHI, verdict
It prints the proposed list and its differences from config.py.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from config import (PAPER_YEARS, TAX_HAVENS_CLEANING, TAX_HAVENS_REPRESENTATION,  # noqa: E402
                    _EXTRA_CTHI_GE65_2YR_SHIFT, _EXTRA_MANUAL, data_raw, estimates_dir,
                    output_dirs)

CTHI_MIN = 65
MIN_YEARS = 2
SAMPLE, SCENARIO = "reported_only", "excl_resource"
SPEC = "sales_employees_destmnedds__etrdef_domfor__etrmax_inf__loss_cit_gain_etr"
CTHI_FILE = Path(data_raw) / "country_info" / "tjn_cthi_2025_scores.csv"


def main():
    tables, _ = output_dirs("diagnostics/haven_list_reevaluation")
    f = estimates_dir(SAMPLE, SCENARIO) / "tables" / SCENARIO / f"country_estimates__{SPEC}.csv"
    if not f.exists():
        sys.exit(f"headline country_estimates file not found: {f}\n"
                 "run 5_estimate_profit_shifting.py (RUN_DATASET=excl_resource, REPORTED_ONLY=1) first")
    ce = pd.read_csv(f, usecols=["iso_partner", "partner_jurisdiction", "year",
                                 "reported_profit", "theoretical_profit"])
    ce = ce[ce["year"].isin(PAPER_YEARS)].copy()
    ce["shift_musd"] = ce["reported_profit"] - ce["theoretical_profit"]
    ce["inward"] = ce["shift_musd"] > 0
    g = ce.groupby(["iso_partner", "partner_jurisdiction"]).agg(
        n_years_in_sample=("year", "nunique"),
        n_inward_years=("inward", "sum"),
        inward_years=("year", lambda s: " ".join(str(y) for y in sorted(s[ce.loc[s.index, "inward"]]))),
        max_inward_musd=("shift_musd", "max"),
        pooled_shift_musd=("shift_musd", "sum"),
    ).reset_index()
    cthi = pd.read_csv(CTHI_FILE, comment="#").rename(columns={"iso3": "iso_partner"})
    g = g.merge(cthi, on="iso_partner", how="left")
    g["in_gb_list"] = g["iso_partner"].isin(TAX_HAVENS_CLEANING)
    g["manual_keep"] = g["iso_partner"].isin(_EXTRA_MANUAL)
    g["passes_outcome_leg"] = (g["cthi_2025_score"] >= CTHI_MIN) & (g["n_inward_years"] >= MIN_YEARS)
    g["proposed_haven"] = g["in_gb_list"] | g["manual_keep"] | g["passes_outcome_leg"]
    g["currently_in_config"] = g["iso_partner"].isin(TAX_HAVENS_REPRESENTATION)
    g["verdict"] = np.select(
        [g["proposed_haven"] & ~g["currently_in_config"], ~g["proposed_haven"] & g["currently_in_config"]],
        ["ADD", "DROP"], "")
    g = g.sort_values(["proposed_haven", "cthi_2025_score", "n_inward_years"], ascending=[False, False, False])
    g.to_csv(tables / "inward_shift_years_by_jurisdiction.csv", index=False)

    proposed_outcome = set(g.loc[g["passes_outcome_leg"] & ~g["in_gb_list"], "iso_partner"])
    # Jurisdictions that are in config's list but absent from the run (no rows) would drop out
    # silently, so I list them explicitly.
    not_in_run = sorted(set(TAX_HAVENS_REPRESENTATION) - set(g["iso_partner"]))
    adds = sorted(proposed_outcome - _EXTRA_CTHI_GE65_2YR_SHIFT)
    drops = sorted(_EXTRA_CTHI_GE65_2YR_SHIFT - proposed_outcome)
    print(f"Rule: GB list | (CTHI-2025 >= {CTHI_MIN} and inward shift in >= {MIN_YEARS} of {len(PAPER_YEARS)} "
          f"window years) | manual {sorted(_EXTRA_MANUAL)}")
    print(f"Outcome leg, proposed: {sorted(proposed_outcome)}")
    print(f"Outcome leg, frozen in config (_EXTRA_CTHI_GE65_2YR_SHIFT): {sorted(_EXTRA_CTHI_GE65_2YR_SHIFT)}")
    print(f"ADD: {adds or '-'}   DROP: {drops or '-'}   config members with no rows in the run: {not_in_run or '-'}")
    print(f"wrote {tables / 'inward_shift_years_by_jurisdiction.csv'}")
    if adds or drops:
        print("\n>>> The frozen outcome set in config.py differs from the re-evaluation. "
              "Update `_EXTRA_CTHI_GE65_2YR_SHIFT` in config.py if you adopt it.")


if __name__ == "__main__":
    main()
