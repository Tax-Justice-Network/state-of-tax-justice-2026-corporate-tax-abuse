# %%
"""
5 — Estimate profit shifting via unitary-taxation formulary apportionment.

This script estimates profit shifting by unitary-taxation formulary
apportionment. On the resources-excluded dataset of script 4 (DATASET_CONFIGS), I
compute, for every specification that the report and the methodology note use
(formula × ETR definition × tax-rate mode), each jurisdiction's misaligned profit
(reported minus formula-implied profit) and the change in tax revenue from taxing
profits where the real activity is.

Headline specification (State of Tax Justice 2026):
  dataset   = excl_resource (resources excluded)
  sample    = reported-only (REPORTED_ONLY=1, is_distributed == 0). Parent-years
              with more than 50% of their foreign unrelated-party revenues in
              aggregates are dropped (the partial-reporter rule).
  formula   = sales_employees_destmnedds  (50% employees, 50% sales, with the
              sales slot filled by the destination-based key: all-sector MNE
              local sales plus the MNE share of digitally deliverable services
              imports, built in 1a_destination_based_sales.py)
  ETR       = domfor (cell-matched domestic or foreign effective rate)
  rate mode = loss_cit_gain_etr (UT gainers priced at the statutory CIT, UT
              losers at their ETR capped at the statutory CIT, or at zero
              where there is no corporate income tax)
  threshold = etrmax_inf (always: full reapportionment without a minimum-rate
              filter. The naming tag is fixed, see the ETR_THRESHOLD note.)
The other specifications (section 6.1):
  - the three other apportionment formulas with the same destination-based sales
    factor (CCCTB, three factors, double-weighted sales), in every run, for the
    formula comparison of the methodology note;
  - the headline formula with sales by origin, in the two main runs, for the
    comparison of origin and destination;
  - in the main reported-only run, the headline formula with effective rates on
    both sides (the conservative bound) and with the havens' bottom-10% rate and
    partner-average rates (the optimistic bound).
Amounts are in US$ million at the current prices of each year and unscaled. The
exhibit scripts convert them to constant 2025 US$ and scale the aggregates.

Section outline (numbers match the cell headings below):
1. Imports.
2. Dataset configuration (RUN_DATASET).
3. Formula specifications.
4. Destination-based sales (headline).
5. ETR specifications.
   5.1 ETR fallback substitution.
6. Tax rates applied to reallocated profit.
   6.1 Specifications of a run.
7. Input samples.
8. Technical helpers.
   8.1 Validation helpers.
   8.2 Sample preparation helpers.
   8.3 Column ordering helpers.
9. Core estimation functions.
10. Load and validate input samples.
   10.1 Define years to run.
11. Run all specifications.
12. Save and display run summary.

Pipeline step 5 — after 4 (resource correction), before 6 (consolidation).

Reads:
  data/final/cbcr_main_excl_resource.csv                      — the resources-excluded dataset (script 4); a dataset
                                                                variant reads its own version, cbcr_main_excl_resource__<variant>.csv
  data/intermediate/destination_based_sales_mkt_own_{jpn,can}.csv — the destination keys of the variants mkt_own_jpn and mkt_own_can (1a)
  data/intermediate/irs_low_tax_destinations{,_ge30}.csv      — the destination sets of the variants irs15_gate and irs15_gate30 (script 1)

Writes (per specification, into the run's output topic, with "_reported" appended when REPORTED_ONLY):
  output/<topic>/tables/<sample>/country_estimates__<spec>.csv — per-country UT gain or loss and revenue change
  output/<topic>/tables/<sample>/misalignment__<spec>.csv      — cell-level misalignment detail (variant runs: the
                                                                 four destination formulas only)
  output/<topic>/tables/<sample>/run_summary.csv               — the specifications of this run, which decide what
                                                                 script 6 consolidates

Usage:
  python src/5_estimate_profit_shifting.py                   — the headline sample (REPORTED_ONLY=1, the default)
  REPORTED_ONLY=0 python src/5_estimate_profit_shifting.py   — the sample with imputed rows
  (The output topic is unitary_taxation_excl_resource[_reported], placed by config.output_dirs.)

Author: Tax Justice Network (based on the method of García-Bernardo and Janský).
Created: 2026-07-17.  Last updated: 2026-11-23.
"""

# %% MARK: 1. Imports
import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from itertools import product

# On Windows, stdout defaults to cp1252 and crashes when a printed line contains
# non-ASCII characters (the long run_summary table at the end prints rows that
# contain the absolute file paths). I switch to UTF-8 with error replacement, so
# that printing cannot stop the run.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import *

pd.set_option("display.max_columns", None)
pd.options.display.float_format = "{:,.2f}".format


# %% MARK: 2. Dataset configuration (RUN_DATASET)
# This section sets the input file this run estimates on: the resources-excluded dataset of script 4. Its
# entry in `DATASET_CONFIGS` names the input file, the profit and tax columns to use, the ETR-column suffix
# (from which the four partner-year ETR columns and the diagnostic pair-ETR column are derived) and the
# output topic that drives `output_dirs(...)`.
DATASET_CONFIGS = {
    "excl_resource": {
        "input_file": "cbcr_main_excl_resource.csv",
        "profit_var": "profit_loss_excl_resource",
        "tax_var": "income_tax_paid_on_cash_basis_excl_resource",
        "etr_suffix": "excl_resource",
        "output_topic": "unitary_taxation_excl_resource",
    },
}

RUN_DATASET = os.environ.get("RUN_DATASET", "excl_resource")

# REPORTED_ONLY: when True, I keep only the input CbCR rows with
# `is_distributed == 0`, i.e. the directly reported country rows, and drop all
# rows that came from disaggregating the aggregates of bad reporters. This gives
# a view of every scenario without imputation. Bad reporters (Ireland, UK, Korea,
# Sweden, etc.) whose non-domestic data are entirely in aggregates essentially
# disappear from the analysis. The output goes to a topic with the suffix
# `_reported`, so that it does not overwrite the run with imputed rows.
REPORTED_ONLY = os.environ.get("REPORTED_ONLY", "1") not in ("0", "false", "False", "")

# Partial-reporter rule for the reported-only sample: I drop a parent-year
# entirely when the share of its foreign unrelated-party revenues reported in
# aggregates exceeds this threshold. Keeping only its few real partner rows would
# present a mostly aggregated filing as a bilateral one (the Netherlands held
# 81–98% of its foreign revenues in aggregates in 2018–22). I measure the share on
# the distributed rows (is_distributed == 1), which carry exactly the activity that
# comes from aggregates.
PARTIAL_REPORTER_MAX_AGG_SHARE = 0.5

_cfg = dict(DATASET_CONFIGS[RUN_DATASET])
PROFIT_VAR = _cfg["profit_var"]
TAX_VAR = _cfg["tax_var"]
ETR_SUFFIX = _cfg["etr_suffix"]
_OUTPUT_TOPIC = _cfg["output_topic"] + ("_reported" if REPORTED_ONLY else "")

# Partner-year ETR columns derived from the active suffix. The parent-partner pair
# ETR is a diagnostic that is never used in UT. I keep it available for the column
# ordering and the validation, but not in ETR_SPECS.
ETR_FAMILY_PARTNER = [
    f"etr_average_{ETR_SUFFIX}",
    f"etr_partner_median_{ETR_SUFFIX}",
    f"etr_partner_p25_{ETR_SUFFIX}",
    f"etr_partner_p10_{ETR_SUFFIX}",
    f"etr_partner_min_{ETR_SUFFIX}",
]
ETR_COL_PAIR = f"etr_parent_partner_{ETR_SUFFIX}"
ETR_COL_DOMESTIC = f"etr_domestic_{ETR_SUFFIX}"
ETR_COL_FOREIGN = f"etr_foreign_{ETR_SUFFIX}"
ETR_COL_AVERAGE = f"etr_average_{ETR_SUFFIX}"
ETR_COL_MEDIAN = f"etr_partner_median_{ETR_SUFFIX}"
ETR_COL_P25 = f"etr_partner_p25_{ETR_SUFFIX}"
ETR_COL_P10 = f"etr_partner_p10_{ETR_SUFFIX}"
ETR_COL_MIN = f"etr_partner_min_{ETR_SUFFIX}"
# Cell-matched domestic or foreign rate (derived in ensure_tax_rate_columns): the
# partner's domestic ETR on the home cells of its own MNEs (iso_parent ==
# iso_partner) and its foreign ETR on the cells of foreign MNEs, i.e. the rate the
# profit in that cell actually bears. The fallback is the average-ETR family, then
# the CIT.
ETR_COL_DOMFOR = f"etr_domfor_{ETR_SUFFIX}"

# The UT estimation is always full reapportionment: no minimum-ETR threshold.
# The file names carry the tag `etrmax_inf`, and the output files carry the
# metadata column `etr_threshold` (constant inf). The downstream scripts read
# both.
ETR_THRESHOLD = np.inf

OUTPUT_TABLES, OUTPUT_FIGURES = output_dirs(_OUTPUT_TOPIC)
# OUTPUT_ROOT is the folder that holds the tables of each sample.
OUTPUT_ROOT = OUTPUT_TABLES

# %% MARK: 3. Formula specifications
# The formula families. The weights refer to [n_employees, unrelated_party_revenues
# (sales), tangible_assets_except_cash, payroll]. The headline family comes first, then
# the three other apportionment designs that the methodology note compares with it.
FORMULA_FAMILIES = [
    # Headline family: 50% employees and 50% sales.
    {"name": "sales_employees", "weights": [0.5, 0.5, 0.0, 0.0]},
    # EU CCCTB: 1/6 employees, 1/6 payroll, 1/3 sales, 1/3 assets.
    {"name": "ccctb", "weights": [1 / 6, 1 / 3, 1 / 3, 1 / 6]},
    # 25% employees, 50% sales, 25% assets.
    {"name": "double_weighted_sales", "weights": [0.25, 0.5, 0.25, 0.0]},
    # 1/3 employees, 1/3 sales, 1/3 assets.
    {"name": "three_factors", "weights": [1 / 3, 1 / 3, 1 / 3, 0.0]},
]
FACTOR_VARS = ["n_employees", "unrelated_party_revenues", "tangible_assets_except_cash", "payroll"]


# %% MARK: 4. Destination-based sales (headline)
# The headline sales factor is destination-based: it counts where the customers are,
# not where the selling entity sits. For each formula family I fill the sales slot with
# the destination share `mne_plus_dds_share`, built in 1a_destination_based_sales.py and
# merged into the dataset by script 2: the local sales of multinationals in all sectors
# (OECD AAMNE) plus the multinationals' share of the imports of digitally deliverable
# services without charges for intellectual property (OECD-WTO BaTIS). The plain
# `unrelated_party_revenues` factor is origin-based. I keep it for the headline family
# only, as the comparison of origin and destination.
DEST_TAG = "destmnedds"
DEST_SHARE_COL = "mne_plus_dds_share"
HEADLINE_FORMULA = f"sales_employees_{DEST_TAG}"
ORIGIN_FORMULA = "sales_employees"

FORMULAS = []
for _fam in FORMULA_FAMILIES:
    _fv = list(FACTOR_VARS)
    _fv[_fv.index("unrelated_party_revenues")] = DEST_SHARE_COL
    FORMULAS.append({"name": f"{_fam['name']}_{DEST_TAG}", "formula_vars": _fv,
                     "weights": list(_fam["weights"])})
FORMULAS.append({"name": ORIGIN_FORMULA, "formula_vars": list(FACTOR_VARS),
                 "weights": list(FORMULA_FAMILIES[0]["weights"])})


# %%
def _attach_destination_factors(df):
    """Prepares the destination-based sales factor for the UT formulas.

    The share column comes from 1a_destination_based_sales.py and is merged into the
    dataset in script 2. I coerce it to numbers. In the variants mkt_own_jpn and
    mkt_own_can, the parents that the variant's key covers take it in place of the
    market key. The within-parent normalisation in `_compute_share_economy` turns the
    share column into a destination distribution over that parent's partners, so no
    rescaling to the parent's CbCR total is needed here.
    """
    if DEST_SHARE_COL not in df.columns:
        df[DEST_SHARE_COL] = np.nan
    df[DEST_SHARE_COL] = pd.to_numeric(df[DEST_SHARE_COL], errors="coerce")

    # Every parent that the variant's key covers takes it in place of the market key, and
    # every other parent keeps the market key. I switch whole parent-years, never single
    # cells, because the two keys have different scales and are only comparable after the
    # within-parent normalisation.
    if HQ_DEST_KEY_FILE:
        _k = pd.read_csv(os.path.join(data_intermediate, HQ_DEST_KEY_FILE),
                         usecols=["iso_parent", "iso_partner", "year", "hq_dest_key"])
        _keys = df[["iso_parent", "iso_partner", "year"]].astype({"year": int})
        _v = _keys.merge(_k, on=["iso_parent", "iso_partner", "year"], how="left")["hq_dest_key"].to_numpy()
        _cov = set(map(tuple, _k[["iso_parent", "year"]].drop_duplicates().values))
        _hit = np.array([(p, y) in _cov for p, y in zip(_keys["iso_parent"], _keys["year"])])
        df.loc[_hit, DEST_SHARE_COL] = _v[_hit]
        _np = df.loc[_hit, "iso_parent"].nunique()
        _miss = sorted(set(df.loc[~_hit, "iso_parent"]))
        print(f"[{UT_VARIANT}] variant key on {int(_hit.sum()):,} rows of {_np} parents; "
              f"market key for {len(_miss)} parents: {_miss[:25]}")
    return df


# %% MARK: 5. ETR specifications
# I build the ETR specifications from the active ETR_SUFFIX.
# etr_parent_partner_{suffix} is intentionally not a UT specification: it is
# missing on distributed rows (is_distributed = 1) by design. The column still
# flows through the pipeline as a diagnostic (kept in validate_input_data,
# load_input_samples and the output column ordering), but not as an ETR over which
# the UT estimates are computed.
# The cell-matched rate is the headline: the domestic ETR on the domestic cell and the
# foreign ETR on the cells of foreign MNEs, the rate each cell's profit actually bears.
# The partner-wide average ETR serves only the optimistic bound (section 6.1).
ETR_DOMFOR = {"name": "domfor", "etr_col": ETR_COL_DOMFOR}
ETR_AVERAGE = {"name": "average", "etr_col": ETR_COL_AVERAGE}
ETR_SPECS = [ETR_DOMFOR, ETR_AVERAGE]


# %% MARK: 5.1 ETR fallback substitution
# ETR fallback substitution (method, not plumbing). I replace an undefined
# ETR (from a negligible or non-positive profit base) by the partner's mean
# measured rate, then by the statutory CIT, so that no jurisdiction enters
# the estimation with a spurious rate.

# %%
def ensure_tax_rate_columns(df):
    """Fills missing values in the partner-year UT ETR columns from each other
    (with cit as the last resort), so that UT can run on every row, and derives
    the cell-matched domestic or foreign rate (`etr_domfor_*`). The pair-ETR
    column is a diagnostic and is never imputed here. Distributed rows keep NaN
    by design."""
    out = df.copy()

    out = fill_column_with_fallbacks(
        out,
        ETR_COL_MEDIAN,
        [ETR_COL_P25, ETR_COL_MIN, ETR_COL_AVERAGE, "cit"],
    )
    out = fill_column_with_fallbacks(
        out,
        ETR_COL_P25,
        [ETR_COL_MEDIAN, ETR_COL_MIN, ETR_COL_AVERAGE, "cit"],
    )
    out = fill_column_with_fallbacks(
        out,
        ETR_COL_MIN,
        [ETR_COL_P25, ETR_COL_MEDIAN, ETR_COL_AVERAGE, "cit"],
    )
    out = fill_column_with_fallbacks(
        out,
        ETR_COL_AVERAGE,
        [ETR_COL_MEDIAN, ETR_COL_P25, ETR_COL_MIN, "cit"],
    )

    # Cell-matched rate: the partner's domestic ETR on the home cell of its own MNEs
    # and its foreign ETR on the cells of foreign MNEs, the rate that the cell's
    # profit actually bears. Where the matched rate is not measured (non-reporters
    # have no domestic ETR, thin partners no foreign ETR), I fall back to the already
    # back-filled average (which ends in the CIT), so that no row is left without a
    # rate.
    _dom = (pd.to_numeric(out[ETR_COL_DOMESTIC], errors="coerce")
            if ETR_COL_DOMESTIC in out.columns else pd.Series(np.nan, index=out.index))
    _for = (pd.to_numeric(out[ETR_COL_FOREIGN], errors="coerce")
            if ETR_COL_FOREIGN in out.columns else pd.Series(np.nan, index=out.index))
    out[ETR_COL_DOMFOR] = np.where(out["iso_parent"] == out["iso_partner"], _dom, _for)
    out = fill_column_with_fallbacks(out, ETR_COL_DOMFOR, [ETR_COL_AVERAGE, "cit"])

    return out


def ensure_current_tax_source_column(df):
    out = df.copy()

    if TAX_VAR not in out.columns:
        out[TAX_VAR] = np.nan
    else:
        out[TAX_VAR] = pd.to_numeric(out[TAX_VAR], errors="coerce")

    return out


# %% MARK: 6. Tax rates applied to reallocated profit
# The tax rate that turns misaligned profit into revenue effects. Each mode
# pairs two choices. The first is the rate at which a country that gains
# profit under unitary taxation would tax what returns to it
# (`loss_rate_kind`, priced on its negative misalignment). The second is the
# rate at which a country that loses profit (a haven) forgoes revenue
# (`gain_rate_kind`, priced on its positive misalignment). In the headline
# mode loss_cit_gain_etr, gainers tax returning profit at the statutory CIT.
# An effective rate above the statutory rate comes from taxes that do not
# scale with an extra dollar of apportioned profit (withholding and minimum
# taxes on gross bases, resource taxes the correction leaves behind, timing),
# so it never replaces the CIT. Havens forgo only their observed effective
# rate, and at most their statutory rate, for the same reason. Havens without
# a corporate income tax (NO_CIT_JURISDICTIONS) forgo nothing in any mode,
# because the tax reported there was paid to other countries, mostly as
# withholding tax.
MODE_HEADLINE = {"name": "loss_cit_gain_etr", "loss_rate_kind": "cit", "gain_rate_kind": "etr"}
# Conservative bound: UT gainers tax the returning profit at their effective rate.
MODE_CONSERVATIVE = {"name": "loss_etr_gain_etr", "loss_rate_kind": "etr", "gain_rate_kind": "etr"}
# Optimistic bound: UT losers (the havens) give up the partner's bottom-10% pair ETR, and
# UT gainers tax the returning profit at the ETR of the specification (the partner
# average, see section 6.1). Slot semantics (easy to get backwards): `loss_rate_kind`
# prices the base of the countries with negative misalignment, which gain under UT, and
# `gain_rate_kind` prices the positive misalignment of the havens, which lose under UT.
# The "p10" kind resolves to the partner-level column regardless of the ETR
# specification (see resolve_rate_mode).
MODE_OPTIMISTIC = {"name": "losers_p10_gainers_avgetr", "loss_rate_kind": "etr", "gain_rate_kind": "p10"}
RATE_MODE_TEMPLATES = [MODE_HEADLINE, MODE_CONSERVATIVE, MODE_OPTIMISTIC]


# %% MARK: 6.1 Specifications of a run
# The two main runs (no UT_VARIANT) estimate the four destination formulas and the
# headline formula with sales by origin. The main reported-only run adds the two bounds of
# the headline. Variant runs estimate the four destination formulas.
MAIN_RUN = UT_VARIANT is None


def run_specifications(formulas):
    """Return the (formula, ETR specification, rate-mode template) triples of this run,
    from the formulas available in the sample."""
    specs = [(f, ETR_DOMFOR, MODE_HEADLINE) for f in formulas
             if MAIN_RUN or f["name"] != ORIGIN_FORMULA]
    if MAIN_RUN and REPORTED_ONLY:
        head = next(f for f in formulas if f["name"] == HEADLINE_FORMULA)
        specs += [(head, ETR_DOMFOR, MODE_CONSERVATIVE), (head, ETR_AVERAGE, MODE_OPTIMISTIC)]
    return specs


# %% MARK: 7. Input samples
# A single input sample per run, set by RUN_DATASET.
INPUT_SAMPLES = {
    RUN_DATASET: variant_path(Path(data_final) / _cfg["input_file"]),
}


# %% MARK: 8. Technical helpers
# Technical helpers for naming, formatting, validation and I/O only. The
# functions with methodological content live in their concept sections above
# (5.1, the ETR fallbacks).
def make_file_stub(formula_name, etr_name, rate_mode_name):
    # "etrmax_inf" is a fixed naming component (full reapportionment, see the
    # ETR_THRESHOLD note above).
    return (
        f"{formula_name}"
        f"__etrdef_{etr_name}"
        f"__etrmax_inf"
        f"__{rate_mode_name}"
    )


def ensure_output_dir(sample_name):
    output_dir = OUTPUT_ROOT / sample_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _longpath(p):
    """On Windows, this function prefixes paths longer than 240 characters with the
    \\\\?\\ long-path namespace, so that open() bypasses the legacy 260-character
    MAX_PATH limit. Deep project roots can push some country_estimates file names
    over that limit. On other systems it changes nothing."""
    s = os.fspath(p)
    if sys.platform == "win32" and len(s) > 240 and not s.startswith("\\\\?\\"):
        s = "\\\\?\\" + os.path.abspath(s)
    return s


def _rate_col_for_kind(kind, etr_spec):
    """Maps a rate 'kind' to the column that carries the rate.

    "etr" follows the active etr_spec. "cit" is the statutory rate. "median" and
    "p10" pin the partner-level pair-ETR statistics irrespective of the etr_spec
    (used by the headline-only sensitivity modes)."""
    if kind == "etr":
        return etr_spec["etr_col"]
    if kind == "cit":
        return "cit"
    if kind == "median":
        return ETR_COL_MEDIAN
    if kind == "p10":
        return ETR_COL_P10
    raise ValueError(f"Unknown rate kind: {kind!r}")


def resolve_rate_mode(rate_mode_template, etr_spec):
    loss_rate_col = _rate_col_for_kind(rate_mode_template["loss_rate_kind"], etr_spec)
    gain_rate_col = _rate_col_for_kind(rate_mode_template["gain_rate_kind"], etr_spec)

    return {
        "name": rate_mode_template["name"],
        "loss_rate_col": loss_rate_col,
        "gain_rate_col": gain_rate_col,
        "loss_rate_kind": rate_mode_template["loss_rate_kind"],
        "gain_rate_kind": rate_mode_template["gain_rate_kind"],
    }


def classify_income_group(value):
    if pd.isna(value):
        return "other_or_missing"

    s = str(value).strip().lower()
    s = s.replace(" ", "_").replace("-", "_")

    if s == "low_income":
        return "low_income"

    if s in {"lower_middle_income", "upper_middle_income", "middle_income"}:
        return "middle_income"

    if s == "high_income":
        return "high_income"

    return "other_or_missing"


AGGREGATE_INCOME_GROUPS = [
    "global",
    "low_income",
    "middle_income",
    "high_income",
    "other_or_missing",
]


INCOME_LABELS = {
    "global": "Global",
    "low_income": "Low income",
    "middle_income": "Middle income",
    "high_income": "High income",
    "other_or_missing": "Other / missing",
}


def safe_series_sum(series):
    return series.sum(min_count=1)


def make_aggregate_row(
    df,
    year,
    formula_name,
    etr_name,
    etr_col,
    etr_threshold,
    threshold_rate_col,
    rate_mode_name,
    loss_rate_col,
    gain_rate_col,
    sample_name,
    income_group_bucket,
):
    if df.empty:
        n_countries = 0
        total_shifted_musd = 0
        total_tax_loss_musd = 0
        total_tax_gain_musd = 0
        total_revenue_gain_from_ut_musd = 0
        mean_revenue_gain_from_ut_musd = np.nan
        total_current_tax_paid_cash_musd = np.nan
        revenue_gain_from_ut_pct_of_current_tax_paid = np.nan
        tax_revenue_loss_pct_of_current_tax_paid = np.nan
        tax_revenue_gain_pct_of_current_tax_paid = np.nan
    else:
        n_countries = df["iso_partner"].nunique()
        total_shifted_musd = df["positive_misalignment"].sum()
        total_tax_loss_musd = df["tax_revenue_loss"].sum()
        total_tax_gain_musd = df["tax_revenue_gain"].sum()
        total_revenue_gain_from_ut_musd = df["revenue_gain_from_ut"].sum()
        mean_revenue_gain_from_ut_musd = df["revenue_gain_from_ut"].mean()
        total_current_tax_paid_cash_musd = safe_series_sum(
            df["current_tax_paid_cash_musd"]
        )

        if (
            pd.notna(total_current_tax_paid_cash_musd)
            and total_current_tax_paid_cash_musd > 0
        ):
            revenue_gain_from_ut_pct_of_current_tax_paid = (
                100 * total_revenue_gain_from_ut_musd / total_current_tax_paid_cash_musd
            )
            tax_revenue_loss_pct_of_current_tax_paid = (
                100 * total_tax_loss_musd / total_current_tax_paid_cash_musd
            )
            tax_revenue_gain_pct_of_current_tax_paid = (
                100 * total_tax_gain_musd / total_current_tax_paid_cash_musd
            )
        else:
            revenue_gain_from_ut_pct_of_current_tax_paid = np.nan
            tax_revenue_loss_pct_of_current_tax_paid = np.nan
            tax_revenue_gain_pct_of_current_tax_paid = np.nan

    return {
        "sample_name": sample_name,
        "formula_name": formula_name,
        "etr_name": etr_name,
        "etr_col": etr_col,
        "etr_threshold": etr_threshold,
        "threshold_rate_col": threshold_rate_col,
        "rate_mode": rate_mode_name,
        "loss_rate_col": loss_rate_col,
        "gain_rate_col": gain_rate_col,
        "year": year,
        "income_group_bucket": income_group_bucket,
        "n_countries": n_countries,
        "total_shifted_musd": total_shifted_musd,
        "total_tax_loss_musd": total_tax_loss_musd,
        "total_tax_gain_musd": total_tax_gain_musd,
        "total_revenue_gain_from_ut_musd": total_revenue_gain_from_ut_musd,
        "mean_revenue_gain_from_ut_musd": mean_revenue_gain_from_ut_musd,
        "total_current_tax_paid_cash_musd": total_current_tax_paid_cash_musd,
        "revenue_gain_from_ut_pct_of_current_tax_paid": revenue_gain_from_ut_pct_of_current_tax_paid,
        "tax_revenue_loss_pct_of_current_tax_paid": tax_revenue_loss_pct_of_current_tax_paid,
        "tax_revenue_gain_pct_of_current_tax_paid": tax_revenue_gain_pct_of_current_tax_paid,
    }


def build_aggregate_rows(
    country_results,
    year,
    formula_name,
    etr_name,
    etr_col,
    etr_threshold,
    threshold_rate_col,
    rate_mode_name,
    loss_rate_col,
    gain_rate_col,
    sample_name,
):
    df = country_results.copy()
    df["income_group_bucket"] = df["wb_income_group"].apply(classify_income_group)

    rows = []

    rows.append(
        make_aggregate_row(
            df=df,
            year=year,
            formula_name=formula_name,
            etr_name=etr_name,
            etr_col=etr_col,
            etr_threshold=etr_threshold,
            threshold_rate_col=threshold_rate_col,
            rate_mode_name=rate_mode_name,
            loss_rate_col=loss_rate_col,
            gain_rate_col=gain_rate_col,
            sample_name=sample_name,
            income_group_bucket="global",
        )
    )

    for bucket in AGGREGATE_INCOME_GROUPS:
        if bucket == "global":
            continue

        subset = df.loc[df["income_group_bucket"] == bucket].copy()

        rows.append(
            make_aggregate_row(
                df=subset,
                year=year,
                formula_name=formula_name,
                etr_name=etr_name,
                etr_col=etr_col,
                etr_threshold=etr_threshold,
                threshold_rate_col=threshold_rate_col,
                rate_mode_name=rate_mode_name,
                loss_rate_col=loss_rate_col,
                gain_rate_col=gain_rate_col,
                sample_name=sample_name,
                income_group_bucket=bucket,
            )
        )

    return pd.DataFrame(rows)


# %% MARK: 8.1 Validation helpers
def validate_formula_spec(formula_spec):
    if "name" not in formula_spec:
        raise ValueError("Each formula specification must have a 'name'.")
    if "formula_vars" not in formula_spec or "weights" not in formula_spec:
        raise ValueError(
            f"Formula '{formula_spec.get('name', 'UNKNOWN')}' must define "
            "'formula_vars' and 'weights'."
        )
    if len(formula_spec["formula_vars"]) != len(formula_spec["weights"]):
        raise ValueError(
            f"Formula '{formula_spec['name']}' has different lengths for "
            "'formula_vars' and 'weights'."
        )
    if sum(formula_spec["weights"]) <= 0:
        raise ValueError(
            f"Formula '{formula_spec['name']}' must have at least one positive weight."
        )


def validate_etr_spec(etr_spec):
    if "name" not in etr_spec or "etr_col" not in etr_spec:
        raise ValueError("Each ETR specification must define 'name' and 'etr_col'.")


def validate_input_data(cbcr_data, sample_name):
    required_cols = [
        "year",
        "iso_parent",
        "iso_partner",
        "partner_jurisdiction",
        PROFIT_VAR,
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
        "cit",
        "n_employees",
        "unrelated_party_revenues",
        "tangible_assets_except_cash",
        "payroll",
        "region_tjn",
        "wb_income_group",
        "ukt",
        "oecd",
        "oecd_oct",
        "eu27",
        "wage_monthly",
    ]

    missing_cols = [col for col in required_cols if col not in cbcr_data.columns]
    if missing_cols:
        raise ValueError(
            f"Missing required columns in sample '{sample_name}': {missing_cols}"
        )


# %% MARK: 8.2 Sample preparation helpers
def keep_actual_country_rows(df):
    out = df.copy()

    out = out.loc[out["iso_partner"].notna()].copy()
    out = out.loc[~out["iso_partner"].isin(non_countries)].copy()

    if "year" in out.columns:
        out["year"] = pd.to_numeric(out["year"], errors="coerce")

    return out


def coerce_numeric_columns(df, columns):
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def fill_column_with_fallbacks(df, target_col, fallback_cols):
    out = df.copy()

    if target_col not in out.columns:
        return out

    for fallback_col in fallback_cols:
        if fallback_col not in out.columns:
            continue
        missing = out[target_col].isna()
        out.loc[missing, target_col] = out.loc[missing, fallback_col]

    return out


def load_input_samples():
    numeric_cols = [
        "year",
        PROFIT_VAR,
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
        "cit",
        "n_employees",
        "unrelated_party_revenues",
        "tangible_assets_except_cash",
        "payroll",
        "wage_monthly",
        TAX_VAR,
    ]

    samples = {}

    for sample_name, file_path in INPUT_SAMPLES.items():
        df = pd.read_csv(file_path)
        df = keep_actual_country_rows(df)
        if REPORTED_ONLY:
            n_before = len(df)
            # Partial-reporter rule: I measure each parent-year's share of foreign
            # unrelated-party revenues in aggregates on the full frame (the
            # distributed rows carry the activity that comes from aggregates), then
            # drop the flagged parent-years entirely from the reported sample.
            _f = df[df["iso_partner"] != df["iso_parent"]]
            _upr = pd.to_numeric(_f["unrelated_party_revenues"], errors="coerce").fillna(0.0)
            _agg = _upr.where(_f["is_distributed"] == 1, 0.0)
            _tot = _upr.groupby([_f["iso_parent"], _f["year"]]).sum()
            _sh = _agg.groupby([_f["iso_parent"], _f["year"]]).sum() / _tot.where(_tot > 0)
            _flagged = set(_sh[_sh > PARTIAL_REPORTER_MAX_AGG_SHARE].index)
            if _flagged:
                _key = pd.MultiIndex.from_arrays([df["iso_parent"], df["year"]])
                df = df[~_key.isin(_flagged)].copy()
                _n_partial = len({p for p, _ in _flagged})
                print(f"  partial-reporter rule (> {PARTIAL_REPORTER_MAX_AGG_SHARE:.0%} of foreign "
                      f"unrelated-party revenues in aggregates): dropped "
                      f"{len(_flagged)} parent-years across {_n_partial} parents.")
            df = df[df["is_distributed"] == 0].copy()
            n_after_dist = len(df)
            # I drop the "bad reporters": parents whose only remaining row is the
            # domestic row (iso_partner == iso_parent). They have no cross-border
            # country-level data left after the keep_actual_country_rows and
            # is_distributed == 0 filters. Mathematically they contribute nothing to
            # the misalignment (the formula factors collapse to 100% in the parent's
            # own country, so theoretical profit equals reported profit). Dropping
            # them explicitly shrinks the parent universe to the population that
            # actually reports.
            cross_border_parents = (
                df.loc[df["iso_partner"] != df["iso_parent"], "iso_parent"].unique()
            )
            n_parents_before = df["iso_parent"].nunique()
            df = df[df["iso_parent"].isin(cross_border_parents)].copy()
            n_parents_after = df["iso_parent"].nunique()
            print(f"  REPORTED_ONLY filter: kept {n_after_dist:,} of {n_before:,} rows "
                  f"after is_distributed==0; then dropped {n_parents_before - n_parents_after} "
                  f"bad-reporter parents (no cross-border country data after filter), "
                  f"leaving {len(df):,} rows for {n_parents_after} parents.")
        df = coerce_numeric_columns(df, numeric_cols)
        df = ensure_tax_rate_columns(df)
        df = ensure_current_tax_source_column(df)
        validate_input_data(df, sample_name)

        print(f"\nLoaded sample: {sample_name}{' (reported-only)' if REPORTED_ONLY else ''}")
        print(f"  Rows: {len(df):,}")
        print(f"  Years: {sorted(df['year'].dropna().astype(int).unique())}")

        for etr_spec in ETR_SPECS:
            n_missing = df[etr_spec["etr_col"]].isna().sum()
            print(f"  Missing {etr_spec['etr_col']}: {n_missing:,}")

        n_missing_cit = df["cit"].isna().sum()
        print(f"  Missing cit: {n_missing_cit:,}")

        if TAX_VAR in df.columns:
            n_missing_tax_paid = df[TAX_VAR].isna().sum()
            print(f"  Missing {TAX_VAR}: {n_missing_tax_paid:,}")

        df = _attach_destination_factors(df)

        samples[sample_name] = df

    return samples


# %% MARK: 8.3 Column ordering helpers
def order_columns(df, preferred_cols):
    if df.empty:
        return df.copy()

    preferred_existing = [c for c in preferred_cols if c in df.columns]
    remaining = sorted([c for c in df.columns if c not in preferred_existing])
    return df[preferred_existing + remaining].copy()


def order_country_columns(df):
    preferred = [
        "iso_partner",
        "partner_jurisdiction",
        "year",
        "sample_name",
        "formula_name",
        "etr_name",
        "etr_col",
        "etr_threshold",
        "threshold_rate_col",
        "rate_mode",
        "loss_rate_col",
        "gain_rate_col",
        "wb_income_group",
        "region_tjn",
        "ukt",
        "oecd",
        "oecd_oct",
        "eu27",
        "cit",
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
        "current_tax_paid_cash_usd_raw",
        "current_tax_paid_cash_musd",
        "negative_misalignment",
        "positive_misalignment",
        "theoretical_profit",
        "reported_profit",
        "tax_revenue_loss",
        "tax_revenue_gain",
        "tax_revenue_gain_uncapped",
        "revenue_gain_from_ut",
        "tax_revenue_loss_caused_musd",
        "tax_revenue_loss_caused_pct_of_total",
        "tax_revenue_loss_suffered_pct_of_total",
        "revenue_gain_from_ut_pct_of_current_tax_paid",
        "tax_revenue_loss_pct_of_current_tax_paid",
        "tax_revenue_gain_pct_of_current_tax_paid",
        "wage_monthly",
    ]
    return order_columns(df, preferred)


def order_aggregate_columns(df):
    preferred = [
        "year",
        "sample_name",
        "formula_name",
        "etr_name",
        "etr_col",
        "etr_threshold",
        "threshold_rate_col",
        "rate_mode",
        "loss_rate_col",
        "gain_rate_col",
        "income_group_bucket",
        "n_countries",
        "total_shifted_musd",
        "total_tax_loss_musd",
        "total_tax_gain_musd",
        "total_revenue_gain_from_ut_musd",
        "mean_revenue_gain_from_ut_musd",
        "total_current_tax_paid_cash_musd",
        "revenue_gain_from_ut_pct_of_current_tax_paid",
        "tax_revenue_loss_pct_of_current_tax_paid",
        "tax_revenue_gain_pct_of_current_tax_paid",
    ]
    return order_columns(df, preferred)


def order_misalignment_columns(df):
    preferred = [
        "iso_parent",
        "iso_partner",
        "partner_jurisdiction",
        "year",
        "sample_name",
        "formula_name",
        "etr_name",
        "etr_col",
        "etr_threshold",
        "threshold_rate_col",
        "rate_mode",
        "loss_rate_col",
        "gain_rate_col",
        PROFIT_VAR,
        "theoretical_profit",
        "misaligned_profit",
        "positive_misalignment_musd_row",
        "negative_misalignment_musd_row",
        "tax_revenue_loss_suffered_musd_row",
        "tax_revenue_loss_caused_musd_row",
        "cit",
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
        TAX_VAR,
        "n_employees",
        "unrelated_party_revenues",
        "tangible_assets_except_cash",
        "payroll",
        "economic_activity_partner_of_parent",
        "share_economy_partner_of_parent",
        "wb_income_group",
        "region_tjn",
        "ukt",
        "oecd",
        "oecd_oct",
        "eu27",
    ]
    return order_columns(df, preferred)


def order_run_summary_columns(df):
    preferred = [
        "sample_name",
        "formula_name",
        "etr_name",
        "etr_col",
        "etr_threshold",
        "threshold_rate_col",
        "rate_mode",
        "loss_rate_col",
        "gain_rate_col",
        "n_country_rows",
        "n_misalignment_rows",
        "n_years",
        "total_shifted_musd_all_years",
        "total_tax_loss_musd_all_years",
        "total_tax_gain_musd_all_years",
        "total_revenue_gain_from_ut_musd_all_years",
        "total_current_tax_paid_cash_musd_all_years",
        "revenue_gain_from_ut_pct_of_current_tax_paid_all_years",
        "total_revenue_gain_from_ut_low_income_musd_all_years",
        "total_revenue_gain_from_ut_middle_income_musd_all_years",
        "country_file",
        "misalignment_file",
        "n_bilateral_rows",
        "bilateral_file",
    ]
    return order_columns(df, preferred)


# %% MARK: 9. Core estimation functions
def _compute_share_economy(df, formula_vars, weights, share_prefix=""):
    """Computes share_economy_partner_of_parent for one formula specification.

    Returns the pair (share_col_name, df with the new column). The function
    changes df in place.
    """
    active_specs = []
    for var, weight in zip(formula_vars, weights):
        if var is None or weight <= 0:
            continue
        if var not in df.columns:
            raise ValueError(f"Formula variable '{var}' not found in input data.")

        df[var] = pd.to_numeric(df[var], errors="coerce")
        df.loc[df[var] < 0, var] = 0

        # A missing factor counts as zero: the cell stays in the apportionment on its
        # other factors. Otherwise a NaN would drop the cell from the shares while its
        # profit stayed in the parent's pool, so the other partners would absorb it
        # (e.g. GBR→BMU 2023, CHE→BMU 2017). The column itself keeps its NaN for the
        # outputs.
        x = df[var].fillna(0.0)
        total_by_parent = x.groupby(df["iso_parent"]).transform("sum")
        share_col = f"share_{share_prefix}{var}"
        df[share_col] = np.where(total_by_parent > 0, x / total_by_parent, 0)
        active_specs.append((share_col, weight))

    if not active_specs:
        raise ValueError("No active variables with positive weights found.")

    activity_col = f"economic_activity_{share_prefix}partner_of_parent"
    df[activity_col] = 0.0
    for share_col, weight in active_specs:
        df[activity_col] += df[share_col] * weight

    total_activity = df.groupby("iso_parent")[activity_col].transform("sum")
    out_col = f"share_economy_{share_prefix}partner_of_parent"
    df[out_col] = np.where(total_activity > 0, df[activity_col] / total_activity, 0)
    return out_col, df


# Reported-direction sign guard: the imputed (distributed) rows may amplify the
# profit-shifting direction implied by the directly reported rows alone, but must
# not reverse it or, where nothing is reported, manufacture one. A partner whose
# reported-only net misalignment is below REPORTED_SIGN_EPS_USD in magnitude (or
# who has no reported rows at all) counts as having "no reported anchor". The anchor
# is the directly reported cells (is_distributed == 0) of the same sample in the same
# year, so the disaggregated estimate cannot reverse the reported direction within any
# year.
REPORTED_SIGN_EPS_USD = 5e6

# Destination gate, for variant runs only (config.DEST_GATE, set by UT_VARIANT).
# Profit can be shifted only into low-tax destinations. I keep a positive
# misalignment only where (iso_partner, year) is in the destination set (IRS CbCR
# Table 4: more than 50% of US groups' positive profit there taxed below 15%, see
# section 6.7 of src/1_clean.py) and rescale each parent's negative side to
# the surviving positive side. This works like a minimum-rate haven test, with the
# IRS set in place of the CbCR-ETR test.
DEST_GATE_SET = None
if DEST_GATE is not None:
    _g = pd.read_csv(Path(data_intermediate) / DEST_GATE["file"])
    _g = _g[_g["qualifies"].astype(bool) & ~_g["iso_partner"].isin(DEST_GATE["exclude"])]
    DEST_GATE_SET = set(zip(_g["iso_partner"], _g["year"].astype(int)))
    print(f"[gate] variant {UT_VARIANT}: {len(DEST_GATE_SET)} destination jurisdiction-years"
          f" (excluded: {list(DEST_GATE['exclude']) or 'none'})")

def calculate_misalignment(
    cbcr_data,
    formula_vars,
    weights,
    profit_var=None,
    loss_rate_col=None,
    reported_sign_guard=True,
):
    """Computes the misalignment of reported profit against formulary-apportioned
    profit.

    I allocate all of each parent's profit by `(formula_vars, weights)`.
    """
    # When the caller omits it, I take the profit column from the dataset
    # configuration.
    if profit_var is None:
        profit_var = PROFIT_VAR
    df = cbcr_data.copy()

    # The ETR columns are the dataset's own family, taken as passed. An undefined
    # ETR (from a negligibly small or non-positive profit base) is replaced upstream
    # by the partner-mean measured rate and then by the statutory CIT, so it never
    # arrives here as NaN.

    if profit_var not in df.columns:
        raise ValueError(f"Profit variable '{profit_var}' not found in input data.")

    if loss_rate_col is not None and loss_rate_col not in df.columns:
        raise ValueError(f"Loss rate column '{loss_rate_col}' not found in input data.")

    # Reported-direction reference for the sign guard. I compute this specification's
    # misalignment on the directly reported rows alone (is_distributed == 0) and take
    # each partner's net sign. Below, I remove any full-sample misalignment that
    # conflicts with it. This is only active on a full input that mixes reported and
    # imputed rows. The recursion is one level deep (reported_sign_guard=False on the
    # inner call).
    reported_sign = None
    if (
        reported_sign_guard
        and "is_distributed" in df.columns
        and (df["is_distributed"] == 1).any()
        and (df["is_distributed"] == 0).any()
    ):
        _rep = calculate_misalignment(
            df[df["is_distributed"] == 0],
            formula_vars,
            weights,
            profit_var=profit_var,
            loss_rate_col=loss_rate_col,
            reported_sign_guard=False,
        )
        _rep_net = _rep.groupby("iso_partner")["misaligned_profit"].sum()
        # A |net| below the epsilon (or a partner absent from the reported rows)
        # counts as "no reported anchor": its sign is 0, and the estimate is clipped
        # to 0.
        reported_sign = np.sign(
            _rep_net.where(_rep_net.abs() >= REPORTED_SIGN_EPS_USD, 0.0)
        )

    primary_col, df = _compute_share_economy(df, formula_vars, weights, share_prefix="")
    df["share_economy_partner_of_parent"] = df[primary_col]

    total_profit_by_parent = df.groupby("iso_parent")[profit_var].transform("sum")
    # I floor the parent's worldwide profit pool at 0 for the UT apportionment. When
    # a parent's worldwide pool is not positive, I skip the apportionment for that
    # parent, and its partners keep their reported values (theoretical = reported,
    # misalignment = 0). This prevents UT from redistributing a negative aggregate
    # pro rata across all partners, which would drag non-resource partners further
    # into the negative (Somalia, for example).
    parent_positive = total_profit_by_parent > 0
    df["theoretical_profit"] = np.where(
        parent_positive,
        df["share_economy_partner_of_parent"] * total_profit_by_parent,
        df[profit_var],
    )
    # Misalignment = reported minus apportioned profit. It nets to zero per parent.
    df["misaligned_profit"] = df[profit_var] - df["theoretical_profit"]

    # Destination gate (variant runs): I remove positive misalignment outside the
    # low-tax destination set. adjust_misalignment rescales the negative side to
    # match.
    if DEST_GATE_SET is not None:
        _dest = pd.Series(
            [k in DEST_GATE_SET for k in zip(df["iso_partner"], df["year"].astype(int))],
            index=df.index,
        )
        df.loc[(df["misaligned_profit"] > 0) & ~_dest, "misaligned_profit"] = 0

    # Reported-direction sign guard. I remove any imputed-row misalignment whose
    # sign would conflict with the partner's reported-only direction:
    #   reported net < 0: drop positive imputed misalignment (cannot become a winner)
    #   reported net > 0: drop negative imputed misalignment (cannot become a loser)
    #   reported net about 0: drop both (no reported anchor, and I do not
    #   manufacture one)
    # Rows of fully reporting parents are never clipped. Clipping them would delete a
    # whole side of a partner's gross flows when its reported net is near zero, e.g.
    # China's own domestic row (+238bn in 2019), so that a wobble of ±5bn in the
    # reported net would flip the partner-year between about −310bn and +258bn. The
    # purpose of the guard is that imputed rows may amplify but not reverse the
    # reported direction. Reported rows are the anchor. The clip breaks the
    # within-parent identity neg − pos == theoretical − reported, so I restore the
    # conservation in adjust_misalignment, which rescales the negative side by total
    # positive ÷ total negative.
    if reported_sign is not None:
        _rs = df["iso_partner"].map(reported_sign)
        _rs = _rs.where(_rs.notna(), 0.0)
        _conflict = (
            ((df["misaligned_profit"] > 0) & (_rs <= 0))
            | ((df["misaligned_profit"] < 0) & (_rs >= 0))
        )
        if "is_distributed" in df.columns:
            # The rows I may clip are the imputed rows, plus every row of a parent
            # whose data are partly imputed this year (a bad reporter). The
            # misalignment of such a parent's reported rows (e.g. of its domestic row)
            # exists only because imputed foreign activity enters the parent's pool
            # (Korea would reverse otherwise). Rows of fully reporting parents are the
            # anchor and are never clipped. A "bad reporter" is defined as in the
            # partial-reporter rule (more than 50% of the parent's foreign
            # unrelated-party revenues in imputed rows), which gives exactly the
            # parent-years the reported-only sample drops. ("Any imputed row" would
            # flag nearly every parent, because most have some distributed residual
            # aggregates.)
            _imp = df["is_distributed"] == 1
            _for = df["iso_partner"] != df["iso_parent"]
            _upr = pd.to_numeric(df["unrelated_party_revenues"], errors="coerce").fillna(0.0).where(_for, 0.0)
            _tot = _upr.groupby(df["iso_parent"]).transform("sum")
            _agg = _upr.where(_imp, 0.0).groupby(df["iso_parent"]).transform("sum")
            _parent_imp = (_agg / _tot.where(_tot > 0)) > PARTIAL_REPORTER_MAX_AGG_SHARE
            _conflict &= _imp | _parent_imp
        df.loc[_conflict, "misaligned_profit"] = 0

    def adjust_misalignment(group):
        total_neg = group.loc[group["misaligned_profit"] < 0, "misaligned_profit"].sum()
        total_pos = group.loc[group["misaligned_profit"] > 0, "misaligned_profit"].sum()

        # I restore the within-parent conservation (Σ misaligned == 0) after the sign
        # guard or the destination gate may have zeroed some rows.
        _gated = DEST_GATE_SET is not None
        if _gated or (reported_sign is not None and "is_distributed" in group.columns):
            # The clip leaves Σ misaligned ≠ 0. I restore the conservation by scaling
            # the negative side by total positive ÷ total negative. The signs are
            # preserved, so the guard is respected, and the factor is 1.0 when nothing
            # was clipped. The rescale is always proportional. Scaling only the
            # imputed rows by f = -reported_net / imputed_net would be unstable: f
            # divides two small nets of large gross flows, so it swings (USA 2018:
            # ×3.0) and reacts to small changes in the inputs. The gross ratio is
            # stable (median 1.00, 0.72–1.01 for the largest parents) and continuous.
            # Reported rows are scaled by it too.
            if total_neg != 0:
                fac = total_pos / (-total_neg)
                if _gated:
                    # Without a surviving destination nothing was shifted away.
                    fac = max(fac, 0.0)
                if fac > 0 or _gated:
                    group.loc[group["misaligned_profit"] < 0, "misaligned_profit"] *= fac

        if loss_rate_col is not None:
            group["positive_misalignment_musd_row"] = np.where(
                group["misaligned_profit"] > 0,
                group["misaligned_profit"] / 1e6,
                0.0,
            )
            group["negative_misalignment_musd_row"] = np.where(
                group["misaligned_profit"] < 0,
                -group["misaligned_profit"] / 1e6,
                0.0,
            )
            group["tax_revenue_loss_suffered_musd_row"] = (
                group["negative_misalignment_musd_row"] * group[loss_rate_col]
            )

            total_positive_musd = group["positive_misalignment_musd_row"].sum()
            total_tax_loss_suffered_musd = group[
                "tax_revenue_loss_suffered_musd_row"
            ].sum()

            group["tax_revenue_loss_caused_musd_row"] = np.where(
                total_positive_musd > 0,
                (
                    group["positive_misalignment_musd_row"]
                    / total_positive_musd
                    * total_tax_loss_suffered_musd
                ),
                0.0,
            )

        return group

    adjusted_parts = []
    for _, group in df.groupby("iso_parent", sort=False):
        adjusted_parts.append(adjust_misalignment(group.copy()))

    df = pd.concat(adjusted_parts, ignore_index=True)
    if DEST_GATE_SET is not None:
        # Gated counterfactual: reported profit minus the misalignment that survives.
        df["theoretical_profit"] = df[profit_var] - df["misaligned_profit"]
    return df


def apply_multiyear_loss_cap(df):
    """Loss cap: a country cannot lose more tax than it currently collects from
    these multinationals, summed over the whole sample period.

    The forgone leg is priced as positive misalignment × rate, and a cell's
    positive misalignment can exceed its reported profit whenever the group's
    apportioned (theoretical) profit is negative (loss-making groups). Pricing
    that excess implies refunding tax that was never paid and produces net
    "losses" above 100% of current tax (Malta, Jersey, ...). The cap binds on
    the net change summed over all years of the run:
    sum(net) >= -sum(cash tax). I deliberately do not apply it year by year,
    because tax is routinely shifted across years under the current system
    (loss carry-forwards, timing of cash payments), so a single year's cash tax
    is not a meaningful ceiling. Capping the gross forgone leg instead would be
    wrong: a haven with large flows both ways (Malta, Jersey) would keep its
    full recovered leg and turn into a net gainer. Where the cap binds, I remove
    the excess from the forgone leg in proportion to each year's forgone
    revenue, so that net = tax_revenue_loss - tax_revenue_gain holds every year.
    I keep the untrimmed leg in tax_revenue_gain_uncapped for audit. Countries
    without cash-tax information are not capped. The cell-level
    (misalignment_*) files and the aggregate (income-group) rows are not capped.

    I evaluate the cap over the multi-year window config.PAPER_YEARS (the
    analysis years excluding 2020, the COVID outlier). Summing over all sample
    years instead would let the anomalous year 2020 mask the bound (Malta's 2020
    swing would leave its six-year average at -835% of current tax). Rows
    outside the window (2020) are left untouched."""
    if df.empty:
        return df
    df = df.copy()
    df["tax_revenue_gain_uncapped"] = df["tax_revenue_gain"]
    _cap_years = globals().get("PAPER_YEARS")
    in_win = df["year"].isin(_cap_years) if _cap_years else pd.Series(True, index=df.index)
    # I evaluate the bound in constant BASE_YEAR dollars, the units in which every
    # deliverable sums. A nominal bound can still show less than -100% after
    # deflation when a country's losses sit in early years (with a high weight) and
    # its offsetting gains in late years (with a low weight). With a nominal cap,
    # Malta shows -157% on the 2016–2023 window.
    _defl_fn = globals().get("deflator_to_base")
    w = df["year"].map(_defl_fn()).fillna(1.0) if _defl_fn else pd.Series(1.0, index=df.index)
    cash = pd.to_numeric(df["current_tax_paid_cash_musd"], errors="coerce").where(in_win)
    key = df["iso_partner"]
    net_tot = (df["revenue_gain_from_ut"] * w).where(in_win, 0.0).groupby(key).transform("sum")
    gain_w = (df["tax_revenue_gain"] * w).where(in_win, 0.0)
    gain_tot = gain_w.groupby(key).transform("sum")
    cash_tot = (cash * w).fillna(0.0).groupby(key).transform("sum")
    has_cash = cash.notna().groupby(key).transform("any")
    excess = (-cash_tot - net_tot).clip(lower=0.0)     # by how much net must rise (constant $)
    bind = in_win & has_cash & (excess > 0) & (gain_tot > 0)
    # I trim each year's forgone leg in proportion to its (deflated) size:
    # nominal trim_y = t * gain_y with t = excess / sum_y(w_y * gain_y)
    t = np.where(gain_tot > 0, excess / gain_tot, 0.0)
    trim = np.where(bind, t * df["tax_revenue_gain"], 0.0)
    df["tax_revenue_gain"] = df["tax_revenue_gain"] - trim
    df["revenue_gain_from_ut"] = df["tax_revenue_loss"] - df["tax_revenue_gain"]
    pos = df["current_tax_paid_cash_musd"] > 0
    for col, src in (
        ("revenue_gain_from_ut_pct_of_current_tax_paid", "revenue_gain_from_ut"),
        ("tax_revenue_gain_pct_of_current_tax_paid", "tax_revenue_gain"),
    ):
        df[col] = np.where(pos, 100 * df[src] / df["current_tax_paid_cash_musd"], np.nan)
    n_bind = int(df.loc[bind, "iso_partner"].nunique())
    if n_bind:
        print(f"  [loss cap] multi-year net loss capped at current tax for {n_bind} countries "
              f"(forgone leg trimmed by {float(trim.sum()):,.0f}M USD in total)")
    return df


def aggregate_country_results(
    misalignment_df,
    year,
    loss_rate_col,
    gain_rate_col,
    formula_name,
    etr_name,
    etr_col,
    etr_threshold,
    threshold_rate_col,
    rate_mode_name,
    sample_name,
):
    metadata_cols = [
        "partner_jurisdiction",
        "cit",
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
        "region_tjn",
        "wb_income_group",
        "ukt",
        "oecd",
        "oecd_oct",
        "eu27",
        "wage_monthly",
    ]

    unique_partners = misalignment_df.groupby("iso_partner", as_index=False)[
        metadata_cols
    ].first()

    # I value the revenue legs at row level, so that the cell-level rate columns
    # (etr_domfor_*: the domestic rate on the domestic cell, the foreign rate on the
    # cells of foreign MNEs) price each cell's misalignment at the rate the cell's
    # profit actually bears. For the rate columns that are constant per partner
    # (average, median, p25, minimum, cit), this is numerically identical to
    # computing at partner level.
    _loss_rate_row = pd.to_numeric(misalignment_df[loss_rate_col], errors="coerce")
    _gain_rate_row = pd.to_numeric(misalignment_df[gain_rate_col], errors="coerce")
    # A jurisdiction without a corporate income tax collects nothing on the profit
    # shifted into it. The tax reported there was paid to other countries.
    _gain_rate_row = _gain_rate_row.mask(misalignment_df["iso_partner"].isin(NO_CIT_JURISDICTIONS), 0.0)
    # A jurisdiction forgoes at most its statutory rate on the profit shifted into it. An
    # effective rate above that rate comes from taxes that do not fall on the shifted profit
    # (withholding and minimum taxes on gross bases, resource taxes the correction leaves
    # behind, timing), so I cap the rate at the CIT. Where the CIT in the data is zero (Jersey,
    # Guernsey, the Isle of Man, the United Arab Emirates, Bahrain, Gibraltar and a few small
    # territories), I keep the effective rate, because part of the tax reported there is their
    # own.
    _cit_row = pd.to_numeric(misalignment_df["cit"], errors="coerce")
    _gain_rate_row = _gain_rate_row.where(~(_cit_row > 0), np.minimum(_gain_rate_row, _cit_row))
    _mis = misalignment_df["misaligned_profit"]
    misalignment_df = misalignment_df.assign(
        _tax_revenue_loss_row=np.where(_mis < 0, -_mis / 1e6, 0.0) * _loss_rate_row,
        _tax_revenue_gain_row=np.where(_mis > 0, _mis / 1e6, 0.0) * _gain_rate_row,
    )

    country_results = misalignment_df.groupby("iso_partner", as_index=False).agg(
        negative_misalignment=("misaligned_profit", lambda x: x[x < 0].sum()),
        positive_misalignment=("misaligned_profit", lambda x: x[x > 0].sum()),
        theoretical_profit=("theoretical_profit", "sum"),
        reported_profit=(PROFIT_VAR, "sum"),
        tax_revenue_loss_caused_musd=("tax_revenue_loss_caused_musd_row", "sum"),
        tax_revenue_loss=("_tax_revenue_loss_row", "sum"),
        tax_revenue_gain=("_tax_revenue_gain_row", "sum"),
    )

    current_tax_paid = misalignment_df.groupby("iso_partner", as_index=False).agg(
        current_tax_paid_cash_usd_raw=(
            TAX_VAR,
            lambda x: x.sum(min_count=1),
        )
    )

    country_results["negative_misalignment"] = (
        -country_results["negative_misalignment"] / 1e6
    )
    country_results["positive_misalignment"] = (
        country_results["positive_misalignment"] / 1e6
    )
    country_results["theoretical_profit"] = country_results["theoretical_profit"] / 1e6
    country_results["reported_profit"] = country_results["reported_profit"] / 1e6

    country_results = country_results.merge(
        unique_partners, on="iso_partner", how="left"
    )
    country_results = country_results.merge(
        current_tax_paid, on="iso_partner", how="left"
    )

    total_loss = country_results["tax_revenue_loss"].sum()

    country_results["current_tax_paid_cash_musd"] = np.where(
        country_results["current_tax_paid_cash_usd_raw"].notna(),
        country_results["current_tax_paid_cash_usd_raw"].clip(lower=0) / 1e6,
        np.nan,
    )

    # I apply the multi-year loss cap (a country cannot lose more tax than it
    # currently collects) once all years of the specification are assembled (see
    # apply_multiyear_loss_cap()). This per-year frame is uncapped.
    country_results["revenue_gain_from_ut"] = (
        country_results["tax_revenue_loss"] - country_results["tax_revenue_gain"]
    )

    country_results["tax_revenue_loss_caused_pct_of_total"] = np.where(
        total_loss > 0,
        country_results["tax_revenue_loss_caused_musd"] / total_loss,
        0,
    )
    country_results["tax_revenue_loss_suffered_pct_of_total"] = np.where(
        total_loss > 0,
        country_results["tax_revenue_loss"] / total_loss,
        0,
    )

    country_results["revenue_gain_from_ut_pct_of_current_tax_paid"] = np.where(
        country_results["current_tax_paid_cash_musd"] > 0,
        100
        * country_results["revenue_gain_from_ut"]
        / country_results["current_tax_paid_cash_musd"],
        np.nan,
    )

    country_results["tax_revenue_loss_pct_of_current_tax_paid"] = np.where(
        country_results["current_tax_paid_cash_musd"] > 0,
        100
        * country_results["tax_revenue_loss"]
        / country_results["current_tax_paid_cash_musd"],
        np.nan,
    )

    country_results["tax_revenue_gain_pct_of_current_tax_paid"] = np.where(
        country_results["current_tax_paid_cash_musd"] > 0,
        100
        * country_results["tax_revenue_gain"]
        / country_results["current_tax_paid_cash_musd"],
        np.nan,
    )

    country_results["year"] = year
    country_results["formula_name"] = formula_name
    country_results["etr_name"] = etr_name
    country_results["etr_col"] = etr_col
    country_results["etr_threshold"] = etr_threshold
    country_results["threshold_rate_col"] = threshold_rate_col
    country_results["rate_mode"] = rate_mode_name
    country_results["loss_rate_col"] = loss_rate_col
    country_results["gain_rate_col"] = gain_rate_col
    country_results["sample_name"] = sample_name

    return country_results


def run_estimation_year(
    year,
    cbcr_data,
    formula_spec,
    etr_spec,
    rate_mode,
    etr_threshold,
    sample_name,
):
    cbcr_year = cbcr_data.loc[cbcr_data["year"] == year].copy()

    if cbcr_year.empty:
        return None, None, None

    misalignment = calculate_misalignment(
        cbcr_data=cbcr_year,
        formula_vars=formula_spec["formula_vars"],
        weights=formula_spec["weights"],
        profit_var=PROFIT_VAR,
        loss_rate_col=rate_mode["loss_rate_col"],
    )
    misalignment["year"] = year
    misalignment["formula_name"] = formula_spec["name"]
    misalignment["etr_name"] = etr_spec["name"]
    misalignment["etr_col"] = etr_spec["etr_col"]
    misalignment["etr_threshold"] = etr_threshold
    misalignment["threshold_rate_col"] = etr_spec["etr_col"]
    misalignment["rate_mode"] = rate_mode["name"]
    misalignment["loss_rate_col"] = rate_mode["loss_rate_col"]
    misalignment["gain_rate_col"] = rate_mode["gain_rate_col"]
    misalignment["sample_name"] = sample_name

    country_results = aggregate_country_results(
        misalignment_df=misalignment,
        year=year,
        loss_rate_col=rate_mode["loss_rate_col"],
        gain_rate_col=rate_mode["gain_rate_col"],
        formula_name=formula_spec["name"],
        etr_name=etr_spec["name"],
        etr_col=etr_spec["etr_col"],
        etr_threshold=etr_threshold,
        threshold_rate_col=etr_spec["etr_col"],
        rate_mode_name=rate_mode["name"],
        sample_name=sample_name,
    )

    aggregate_rows = build_aggregate_rows(
        country_results=country_results,
        year=year,
        formula_name=formula_spec["name"],
        etr_name=etr_spec["name"],
        etr_col=etr_spec["etr_col"],
        etr_threshold=etr_threshold,
        threshold_rate_col=etr_spec["etr_col"],
        rate_mode_name=rate_mode["name"],
        loss_rate_col=rate_mode["loss_rate_col"],
        gain_rate_col=rate_mode["gain_rate_col"],
        sample_name=sample_name,
    )

    return misalignment, country_results, aggregate_rows


# %% MARK: 10. Load and validate input samples
for formula_spec in FORMULAS:
    validate_formula_spec(formula_spec)

for etr_spec in ETR_SPECS:
    validate_etr_spec(etr_spec)

samples = load_input_samples()


# %% MARK: 10.1 Define years to run
years_requested = list(range(first_year, first_year + n_years))

sample_years = {}
for sample_name, df in samples.items():
    years_available = sorted(df["year"].dropna().astype(int).unique())
    years_to_run = [year for year in years_requested if year in years_available]

    sample_years[sample_name] = years_to_run

    print(f"\nSample: {sample_name}")
    print(f"  Years requested: {years_requested}")
    print(f"  Years run: {years_to_run}")


# %% MARK: 11. Run all specifications
run_summary_rows = []

for sample_name, df in samples.items():
    print("\n" + "=" * 100)
    print(f"RUNNING SAMPLE: {sample_name}")
    print("=" * 100)

    output_dir = ensure_output_dir(sample_name)

    # I skip formulas whose factor columns are absent from this sample.
    available_cols = set(df.columns)
    formulas_for_sample = [f for f in FORMULAS if all(v in available_cols for v in f["formula_vars"])]
    skipped = [f["name"] for f in FORMULAS if f not in formulas_for_sample]
    if skipped:
        print(f"  [skip {len(skipped)} formulas not applicable to this sample] "
              f"{', '.join(skipped)}")

    _spec_combos = [(f, e, ETR_THRESHOLD, r) for f, e, r in run_specifications(formulas_for_sample)]
    for formula_spec, etr_spec, etr_threshold, rate_mode_template in _spec_combos:
        rate_mode = resolve_rate_mode(rate_mode_template, etr_spec)

        file_stub = make_file_stub(
            formula_name=formula_spec["name"],
            etr_name=etr_spec["name"],
            rate_mode_name=rate_mode["name"],
        )

        print("\n" + "-" * 100)
        print(
            f"Formula: {formula_spec['name']} | "
            f"ETR definition: {etr_spec['name']} ({etr_spec['etr_col']}) | "
            f"ETR max: {etr_threshold} | "
            f"Rate mode: {rate_mode['name']}"
        )
        print("-" * 100)

        results_country = []
        results_misalignment = []
        results_aggregate = []

        for year in sample_years[sample_name]:
            misalignment, country_results, aggregate_rows = run_estimation_year(
                year=year,
                cbcr_data=df,
                formula_spec=formula_spec,
                etr_spec=etr_spec,
                rate_mode=rate_mode,
                etr_threshold=etr_threshold,
                sample_name=sample_name,
            )

            if country_results is not None:
                results_country.append(country_results)
                results_misalignment.append(misalignment)
                results_aggregate.append(aggregate_rows)

                global_row = aggregate_rows.loc[
                    aggregate_rows["income_group_bucket"] == "global"
                ].iloc[0]

                print(
                    f"  {year}: shifted {global_row['total_shifted_musd']:,.0f}M USD | "
                    f"tax loss {global_row['total_tax_loss_musd']:,.0f}M USD | "
                    f"tax gain {global_row['total_tax_gain_musd']:,.0f}M USD"
                )
            else:
                print(f"  {year}: no data")

        if results_country:
            country_all_years = pd.concat(results_country, ignore_index=True)
        else:
            country_all_years = pd.DataFrame()

        if results_misalignment:
            misalignment_all_years = pd.concat(results_misalignment, ignore_index=True)
        else:
            misalignment_all_years = pd.DataFrame()

        if results_aggregate:
            aggregate_df = pd.concat(results_aggregate, ignore_index=True)
        else:
            aggregate_df = pd.DataFrame()

        country_all_years = apply_multiyear_loss_cap(country_all_years)
        country_all_years = order_country_columns(country_all_years)
        misalignment_all_years = order_misalignment_columns(misalignment_all_years)
        aggregate_df = order_aggregate_columns(aggregate_df)

        country_file = output_dir / f"country_estimates__{file_stub}.csv"
        misalignment_file = output_dir / f"misalignment__{file_stub}.csv"

        country_all_years.to_csv(_longpath(country_file), index=False)
        # Variant runs keep the row-level misalignment detail only for the formulas the
        # exhibits read. Otherwise a variant takes about 160 GB.
        if UT_VARIANT is None or formula_spec["name"] in VARIANT_MISALIGNMENT_FORMULAS:
            misalignment_all_years.to_csv(_longpath(misalignment_file), index=False)

        if not aggregate_df.empty:
            aggregate_global_df = aggregate_df.loc[
                aggregate_df["income_group_bucket"] == "global"
            ].copy()

            aggregate_low_df = aggregate_df.loc[
                aggregate_df["income_group_bucket"] == "low_income"
            ].copy()

            aggregate_middle_df = aggregate_df.loc[
                aggregate_df["income_group_bucket"] == "middle_income"
            ].copy()
        else:
            aggregate_global_df = pd.DataFrame()
            aggregate_low_df = pd.DataFrame()
            aggregate_middle_df = pd.DataFrame()

        total_current_tax_paid_cash_musd_all_years = (
            safe_series_sum(aggregate_global_df["total_current_tax_paid_cash_musd"])
            if not aggregate_global_df.empty
            and "total_current_tax_paid_cash_musd" in aggregate_global_df.columns
            else np.nan
        )

        if (
            pd.notna(total_current_tax_paid_cash_musd_all_years)
            and total_current_tax_paid_cash_musd_all_years > 0
        ):
            revenue_gain_from_ut_pct_of_current_tax_paid_all_years = (
                100
                * aggregate_global_df["total_revenue_gain_from_ut_musd"].sum()
                / total_current_tax_paid_cash_musd_all_years
            )
        else:
            revenue_gain_from_ut_pct_of_current_tax_paid_all_years = np.nan

        run_summary_rows.append(
            {
                "sample_name": sample_name,
                "formula_name": formula_spec["name"],
                "etr_name": etr_spec["name"],
                "etr_col": etr_spec["etr_col"],
                "etr_threshold": etr_threshold,
                "threshold_rate_col": etr_spec["etr_col"],
                "rate_mode": rate_mode["name"],
                "loss_rate_col": rate_mode["loss_rate_col"],
                "gain_rate_col": rate_mode["gain_rate_col"],
                "n_country_rows": len(country_all_years),
                "n_misalignment_rows": len(misalignment_all_years),
                "n_years": (
                    aggregate_global_df["year"].nunique()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_shifted_musd_all_years": (
                    aggregate_global_df["total_shifted_musd"].sum()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_tax_loss_musd_all_years": (
                    aggregate_global_df["total_tax_loss_musd"].sum()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_tax_gain_musd_all_years": (
                    aggregate_global_df["total_tax_gain_musd"].sum()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_revenue_gain_from_ut_musd_all_years": (
                    aggregate_global_df["total_revenue_gain_from_ut_musd"].sum()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_current_tax_paid_cash_musd_all_years": total_current_tax_paid_cash_musd_all_years,
                "revenue_gain_from_ut_pct_of_current_tax_paid_all_years": revenue_gain_from_ut_pct_of_current_tax_paid_all_years,
                "total_revenue_gain_from_ut_low_income_musd_all_years": (
                    aggregate_low_df["total_revenue_gain_from_ut_musd"].sum()
                    if not aggregate_low_df.empty
                    else 0
                ),
                "total_revenue_gain_from_ut_middle_income_musd_all_years": (
                    aggregate_middle_df["total_revenue_gain_from_ut_musd"].sum()
                    if not aggregate_middle_df.empty
                    else 0
                ),
                "country_file": str(country_file),
                "misalignment_file": str(misalignment_file),
            }
        )


# %% MARK: 12. Save and display run summary
run_summary = pd.DataFrame(run_summary_rows)
run_summary = order_run_summary_columns(run_summary)

# The run summary lists exactly the specifications of this run. Script 6 consolidates
# only the files it lists, so files of earlier runs in the same folder never enter the
# summaries.
_rs_path = OUTPUT_ROOT / "run_summary.csv"
run_summary.to_csv(_rs_path, index=False)

print("\n" + "=" * 100)
print("RUN SUMMARY")
print("=" * 100)

if not run_summary.empty:
    print(run_summary.to_string(index=False))
else:
    print("No results produced.")
