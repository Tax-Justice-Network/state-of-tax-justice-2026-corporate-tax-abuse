# %%
"""
4 — Correct CbCR profits & taxes for resource-related government payments.

This script corrects the disaggregated CbCR data for resource-related government payments and writes the
resources-excluded dataset of the unitary-taxation analysis, data/final/cbcr_main_excl_resource.csv. It takes
`cbcr_main_disaggregated.csv` and the (HQ, source, commodity, year) resource-payment panel. The output is
self-contained for running script 5.

I strip the resource profit base and the matching resource tax, so that unitary taxation applies to the
non-extractive corporate income only, and I recompute the non-resource ETR family on the result.
  profit_loss_excl_resource
     = profit_loss_before_income_tax_corrected − resource_profit_base_usd
  income_tax_paid_on_cash_basis_excl_resource
     = income_tax_paid_on_cash_basis − resource_tax_deduction_usd
The tax deduction is not the external post-profit payment figure, because payments that are not booked in the CbCR
income-tax line must not be deducted from it. I derive it from the CbCR tax line itself, per cell, and record the
method in `resource_correction_method`. ETR-gap cells strip the tax in excess of the statutory CIT. Inert cells strip
the payment-derived profit base at the cell's own reported effective tax rate. A negative post-profit payment (a net
refund) strips nothing. External payments shape the profit base (the larger of post-profit payments ÷ rate and
equity income), never the tax line directly.
ETR columns: etr_average_excl_resource / etr_partner_median_excl_resource / etr_partner_p25_excl_resource /
etr_partner_min_excl_resource / etr_parent_partner_excl_resource (a diagnostic, missing on distributed rows by
design).

Section outline (numbers match the cell headings below):
1. Setup.
2. Resources excluded (machinery).
   2.1 Tax measure of the variant accrued_tax.
3. Output writer.
4. Main.

Pipeline step 4 — after 2 (disaggregate) and the 3_extractive_prep chain, before 5 (estimation).

Reads:
  data/final/cbcr_main_disaggregated.csv                                  — disaggregated CbCR baseline (script 2)
  data/final/cbcr_main.csv                                                — the OECD sub-group panels, the base of the ETRs (script 1)
  data/intermediate/extractive/resource_payments_by_hq_source_yearly.csv  — (HQ, source, commodity, year) payment panel (3_31 → 3_33 → 3_38)
  data/raw/extractive/resource_profit_tax_rate.csv                        — effective resource profit-tax rate by source × commodity, with the statutory CIT as fallback
  data/raw/extractive/resource_country_parameters.csv                     — include flag, curated resource rate r, EITI flag (source of truth)
  data/raw/extractive/effective_resource_cit_rates.csv                    — combined effective resource rate r of the ETR gap
  data/intermediate/extractive/rents_combined_yearly.csv                  — layered rents per (iso3, year, category): EITI before EIA, BGS and WB
  data/intermediate/extractive/eiti_company_hq_map.csv /
    eiti_documented_source_hq_pairs.csv, operator_payments_by_hq_source_yearly.csv
                                                                          — documented extractive parents per source (ETR-floor gate)

Writes:
  data/final/cbcr_main_excl_resource.csv                                  — resources excluded (+ recomputed non-resource ETR family)
  data/intermediate/extractive/resource_correction_*.csv                  — unmatched-cell diagnostics and the per-country method table
A dataset variant (config.DATASET_VARIANTS) writes its own version of each of these files, with `__<variant>` before
the extension. The variant res_no_inferred_companies reads the 3_38 outputs of its own run, the others read the main
ones. The variant accrued_tax takes the tax accrued for the current year in place of the tax paid on a cash basis
(section 2.1).

Usage:
  python src/4_correcting_cbcr_for_resource_payments.py                              — the headline dataset
  UT_VARIANT=<variant> python src/4_correcting_cbcr_for_resource_payments.py         — the dataset of a dataset variant

Author: Tax Justice Network.
Created: 2026-06-03.  Last updated: 2026-11-23.
"""

# %% MARK: 1. Setup
# Setup: imports, paths and shared constants.
import os
import sys
import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import (first_year, last_year, data_raw, data_final, data_intermediate_extractive, TAX_HAVENS_FUNCTIONAL,
                    ETR_PROFIT_SUBGROUP, RESOURCE_INFERRED_OFF, TAX_MEASURE, variant_path)
from _etr_construction import compute_partner_year_etrs


def _resource_table(path):
    """Return the path of a 3_38 output: the variant's own version when the variant switches off the inferred
    company tables (3_38 reads them), the main version otherwise."""
    if "inferred_layers" in RESOURCE_INFERRED_OFF:
        own = variant_path(path)
        if not os.path.exists(own):
            raise FileNotFoundError(f"{own}: the variant needs its own 3_38 output")
        return str(own)
    return path


# The single disaggregated input (gravity-imputed activity and profitability-imputed profit).
CBCR = f"{data_final}cbcr_main_disaggregated.csv"
CBCR_MAIN = f"{data_final}cbcr_main.csv"      # script-1 output with the OECD sub-group panels (ETR base)
PAY = _resource_table(f"{data_intermediate_extractive}resource_payments_by_hq_source_yearly.csv")
RATE = f"{data_raw}extractive/resource_profit_tax_rate.csv"
ECR = f"{data_raw}extractive/effective_resource_cit_rates.csv"   # combined effective resource rate (r) for the ETR-gap
RENTS = f"{data_intermediate_extractive}rents_combined_yearly.csv"
PARAMS = f"{data_raw}extractive/resource_country_parameters.csv"   # consolidated source of truth: include flag, curated resource rate r, EITI flag
EITI_HQ_MAP = f"{data_intermediate_extractive}eiti_company_hq_map.csv"          # documented extractive parents (floor rule)
# The record-level map is not shipped, because it rests on Orbis. The package ships the (source,
# headquarters) country pairs that the map yields for the floor rule (companies with more than US$1m of
# payments and a known headquarters).
EITI_HQ_PAIRS = f"{data_intermediate_extractive}eiti_documented_source_hq_pairs.csv"
OPERATOR_PAY = f"{data_intermediate_extractive}operator_payments_by_hq_source_yearly.csv"

OUT_EXCL = str(variant_path(f"{data_final}cbcr_main_excl_resource.csv"))

PCOL = "profit_loss_before_income_tax_corrected"
TCOL = "income_tax_paid_on_cash_basis"
# The tax of the effective tax rates: the tax paid on a cash basis, or the tax accrued for the current year in the
# variant accrued_tax (section 2.1).
ACCRUED_TCOL = "income_tax_accrued_current_year"
ETR_TCOL = ACCRUED_TCOL if TAX_MEASURE == "accrued" else TCOL
RATE_MIN, RATE_MAX = 0.05, 0.95   # sanity bounds on the profit-tax divisor

# ETR family suffix on the resource-corrected (non-resource) ETRs.
ETR_SUFFIX = "excl_resource"
ETR_COLS_PARTNER = [
    f"etr_domestic_{ETR_SUFFIX}",
    f"etr_foreign_{ETR_SUFFIX}",
    f"etr_average_{ETR_SUFFIX}",
    f"etr_partner_median_{ETR_SUFFIX}",
    f"etr_partner_p25_{ETR_SUFFIX}",
    f"etr_partner_p10_{ETR_SUFFIX}",
    f"etr_partner_min_{ETR_SUFFIX}",
]
ETR_COL_PAIR = f"etr_parent_partner_{ETR_SUFFIX}"

# These ETR columns already exist on the disaggregated file. I drop them from the output file, because they
# were computed on the reported (pre-correction) profit and tax and have no methodological meaning once the
# profit and tax columns are resource-corrected.
ETR_COLS_TO_DROP = [
    "etr_domestic_corrected",
    "etr_foreign_corrected",
    "etr_average_corrected",
    "etr_partner_median_corrected",
    "etr_partner_p25_corrected",
    "etr_partner_p10_corrected",
    "etr_partner_min_corrected",
    "etr_parent_partner_corrected",
]




# %% MARK: 2. Resources excluded (machinery)
# The cell allocator, the non-resource ETR machinery and the resolvers of the resource profit-tax rate.

# %%
# This section holds the cell allocator, the non-resource ETR construction and the resolvers of the resource
# profit-tax rate. Here the payment-level corrections land on the CbCR cells, and the excl_resource (profit,
# tax) pair gets its partner-year ETR family.

def _allocate_payments_to_cbcr_cells(cbcr, agg, payment_cols):
    """Merge an (iso_parent, iso_partner, year)-keyed `agg` frame onto cbcr and split each cell-level
    payment across the cell's rows in proportion to each row's gross revenue (with an equal split as the
    fallback). Returns df with the merged payment columns. cbcr can have more than one row per cell, when
    the bad-reporter disaggregation appended a distributed row alongside the directly-reported one."""
    df = cbcr.merge(agg, on=["iso_parent", "iso_partner", "year"], how="left")
    for c in payment_cols:
        df[c] = df[c].fillna(0.0)

    cell = ["iso_parent", "iso_partner", "year"]
    rev = pd.to_numeric(df["total_revenues"], errors="coerce").fillna(0.0).abs()
    rev_sum = rev.groupby([df[c] for c in cell]).transform("sum")
    n_rows = df.groupby(cell)[PCOL].transform("size")
    w = np.where(rev_sum > 0, rev / rev_sum.replace(0, np.nan), 1.0 / n_rows)
    w = pd.Series(w, index=df.index).fillna(1.0 / n_rows)

    for c in payment_cols:
        df[c] = df[c] * w
    return df


def _compute_excl_resource_etrs(df):
    """Compute the non-resource ETR family on the OECD positive-profit panel
    (config.ETR_PROFIT_SUBGROUP), the same base that script 1 uses for the canonical `etr_*_corrected`
    family.

    For every directly-reported cell (is_distributed == 0) I take the resource strip computed above on the
    "Total (All sub-groups)" cell (resource_profit_base_usd, resource_tax_deduction_usd) off the cell's
    positive-profit sub-group profit and tax. I cap it at that sub-group's own values, since resource profit
    is positive by construction. I then pool the partner-year family (domestic, foreign and average, and the
    pair-based median, p25, p10 and minimum) over those positive-panel cells, as tax paid ÷ profit that was
    actually taxed. Pooling the all-sub-groups totals instead would let one large loss cell collapse a
    partner's pooled base to about zero and clip its rate to 100% (Malta, Jersey, Isle of Man, Gibraltar and
    the Faroe Islands, and a UK foreign rate of 30% against a 19% CIT).

    For partner-years without a positive-panel cell (the OECD suppresses the split for thin partners), I fall
    back to the totals-based family pooled over positive-net cells (positive-profit pooling). This is the
    analogue of script 1's domestic fallback to the totals panel, and it comes before the usual partner-mean
    and CIT fill in _fill_excl_resource_etrs. Imputed rows never enter.

    Returns (partner_year_df, pair_year_df), ready to merge back onto df. The pair ETR is NaN on distributed
    rows by design, because there is no real report for that (parent, partner, year) cell."""
    key = ["iso_parent", "iso_partner", "year"]
    reported = df[df["is_distributed"] == 0].copy()
    strip = (reported.groupby(key, as_index=False)
             .agg(_rp=("resource_profit_base_usd", "sum"),
                  _rt=("resource_tax_deduction_usd", "sum")))

    main = pd.read_csv(CBCR_MAIN, low_memory=False,
                       usecols=key + ["grouping", PCOL, ETR_TCOL])
    pos = main[main["grouping"] == ETR_PROFIT_SUBGROUP].drop(columns="grouping")
    pos = pos.merge(strip, on=key, how="inner")        # reported cells only
    p_pos = pd.to_numeric(pos[PCOL], errors="coerce")
    t_pos = pd.to_numeric(pos[ETR_TCOL], errors="coerce")
    pos["profit_loss_excl_resource"] = p_pos - np.minimum(pos["_rp"], p_pos.clip(lower=0))
    pos["income_tax_paid_on_cash_basis_excl_resource"] = t_pos - np.minimum(pos["_rt"], t_pos.clip(lower=0))
    partner_year, pair_year = compute_partner_year_etrs(
        pos,
        profit_col="profit_loss_excl_resource",
        tax_col="income_tax_paid_on_cash_basis_excl_resource",
        suffix=ETR_SUFFIX,
        window=2,
        pair_stats=True,
    )

    # For the partner-years the positive panel does not cover, I fall back to the all-sub-groups totals
    # pooled over positive-net cells.
    fb_partner, _ = compute_partner_year_etrs(
        reported,
        profit_col="profit_loss_excl_resource",
        tax_col="income_tax_paid_on_cash_basis_excl_resource",
        suffix=ETR_SUFFIX,
        window=2,
        pair_stats=True,
        pooling="positive",
    )
    merged = partner_year.merge(fb_partner, on=["iso_partner", "year"],
                                how="outer", suffixes=("", "__fb"))
    n_fb = 0
    for col in ETR_COLS_PARTNER:
        fb = f"{col}__fb"
        if fb in merged.columns:
            n_fb += int((merged[col].isna() & merged[fb].notna()).sum())
            merged[col] = merged[col].fillna(merged[fb])
            merged = merged.drop(columns=fb)
    n_cells_pos = len(pos)
    n_cells_rep = len(strip)
    print(f"  [excl_resource ETRs] pooled over the '{ETR_PROFIT_SUBGROUP}' panel: "
          f"{n_cells_pos:,} of {n_cells_rep:,} reported cells have a positive-profit "
          f"sub-group; {n_fb:,} partner-year × column values filled from the "
          f"positive-net totals fallback.")
    return merged, pair_year


def _attach_etrs(df, partner_year, pair_year):
    """Merge the non-resource ETR columns onto df.

    The partner-year statistics (domestic, foreign, average, median, p25 and minimum) merge on
    (iso_partner, year) and so apply to distributed rows too, because they are properties of the
    partner-year, not of the specific pair.

    The pair ETR merges on (iso_parent, iso_partner, year), and I then set it to NaN on distributed rows.
    The rolling window could pick up a real report of the same pair in another year, but the pair-ETR column
    is by design a diagnostic that carries a value only when the (parent, partner, year) cell itself was
    directly reported. Rows with is_distributed == 1 therefore get NaN."""
    df = df.merge(partner_year, on=["iso_partner", "year"], how="left")
    df = df.merge(pair_year, on=["iso_parent", "iso_partner", "year"], how="left")
    df.loc[df["is_distributed"] == 1, ETR_COL_PAIR] = np.nan
    return df


def _fill_excl_resource_etrs(df):
    """Mirror 1_clean.fill_missing_cit_and_corrected_etrs for the excl_resource ETR family.

    Where the measured partner-year ETR is undefined (NaN), for example because of the negligible or
    non-positive pooled-profit base guarded in _etr_construction (ETR_MIN_PROFIT_BASE_USD), I fall back to
    the partner's mean measured rate across years and then to the statutory CIT. This keeps the script-5
    revenue legs (which key off the excl_resource ETR family) from ever seeing a NaN rate. An undefined
    effective rate is treated as "taxed at the statutory rate" (so a thin-profit jurisdiction with a CIT
    above 15% reads as a non-haven), not as a zero-tax haven. I leave the pair ETR untouched, because it is
    a diagnostic (NaN on distributed rows by design)."""
    if "cit" not in df.columns:
        return df
    cit = pd.to_numeric(df["cit"], errors="coerce")
    for col in ETR_COLS_PARTNER:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        partner_mean = s.groupby(df["iso_partner"]).transform("mean")
        df[col] = s.fillna(partner_mean).fillna(cit).clip(lower=0, upper=1)
    return df


def _resolve_rate_by_year(rate, years, col):
    """Expand the per-commodity rate table to (source_iso3, commodity, year).

    Rows with a blank year_start / year_end are the sample-agnostic default and apply to every year. Rows
    with a range apply only within [year_start, year_end] and win over the agnostic row for those years.
    Returns a frame keyed on (source_iso3, commodity, year) that carries `col`, so that a downstream merge on
    that triple is one-to-one."""
    yrs = sorted(pd.to_numeric(pd.Series(years), errors="coerce").dropna().astype(int).unique())
    has_ys = (rate["year_start"].notna() if "year_start" in rate.columns
              else pd.Series(False, index=rate.index))
    ag = rate.loc[~has_ys, ["source_iso3", "commodity", col]]
    exp = (ag.assign(_k=1).merge(pd.DataFrame({"year": yrs, "_k": 1}), on="_k")
           .drop(columns="_k"))
    exp["_yspec"] = False
    if has_ys.any():
        ys = rate.loc[has_ys].copy()
        ys["year_start"] = pd.to_numeric(ys["year_start"], errors="coerce")
        ys["year_end"] = pd.to_numeric(ys["year_end"], errors="coerce")
        parts = [{"source_iso3": rr["source_iso3"], "commodity": rr["commodity"],
                  col: rr[col], "year": y, "_yspec": True}
                 for _, rr in ys.iterrows() for y in yrs
                 if rr["year_start"] <= y <= rr["year_end"]]
        if parts:
            exp = pd.concat([exp, pd.DataFrame(parts)], ignore_index=True)
    return (exp.sort_values("_yspec")
            .drop_duplicates(["source_iso3", "commodity", "year"], keep="last")
            .drop(columns="_yspec"))


def _resolve_partner_rate_by_year(rate, years, curated, combined):
    """Resolve the ETR-gap rate without applying a dated regime to every year.

    A country with dated per-commodity rows uses that table's complete resolved schedule, including its
    default rows outside the dated interval. Other countries keep the curated country rate, then the
    per-commodity maximum, then the combined-rate fallback. The maximum across commodities is an
    approximation: this function selects the rates of the year and does not attribute them to commodities.
    """
    col = "effective_resource_profit_tax_rate"
    resolved = _resolve_rate_by_year(rate, years, col)
    by_year = resolved.groupby(["source_iso3", "year"])[col].max()
    dated = set()
    if "year_start" in rate:
        dated = set(rate.loc[rate["year_start"].notna(), "source_iso3"])
    yrs = sorted(pd.to_numeric(pd.Series(years), errors="coerce")
                 .dropna().astype(int).unique())
    countries = sorted(set(curated.index) | set(combined.index)
                       | set(rate["source_iso3"]))
    out = pd.MultiIndex.from_product(
        [countries, yrs], names=["iso_partner", "year"]
    ).to_frame(index=False)
    commodity_rate = pd.Series(
        [by_year.get((iso, year), np.nan)
         for iso, year in zip(out.iso_partner, out.year)], index=out.index
    )
    country_rate = out.iso_partner.map(curated)
    out["resource_rate_partner"] = (
        commodity_rate.where(out.iso_partner.isin(dated), country_rate)
        .fillna(country_rate).fillna(commodity_rate)
        .fillna(out.iso_partner.map(combined))
    )
    return out


# %% MARK: 2.1 Tax measure of the variant accrued_tax
# The OECD data give both the tax paid on a cash basis in the year and the tax accrued for the year. The headline
# uses the tax paid. The variant accrued_tax uses the accrued tax in the effective tax rates (ETR_TCOL), in the loss
# cap and in the tax that multinationals pay. The resource strip stays the one computed on the tax paid, capped at
# the cell's accrued tax.
def _accrued_tax_measure(df):
    """Returns df with income_tax_paid_on_cash_basis_excl_resource holding the accrued tax net of the resource
    strip. The column keeps its name, because script 5 reads the tax under that name."""
    acc = pd.to_numeric(df[ACCRUED_TCOL], errors="coerce")
    ded = pd.to_numeric(df["resource_tax_deduction_usd"], errors="coerce").fillna(0.0)
    ded_capped = np.minimum(ded, acc.clip(lower=0).fillna(0.0))
    df["income_tax_paid_on_cash_basis_excl_resource"] = acc - ded_capped
    print(f"  [accrued_tax] tax column on accrued tax: resource strip {ded.sum() / 1e9:,.2f} bn, capped at the "
          f"accrued tax {ded_capped.sum() / 1e9:,.2f} bn")
    return df


# %% MARK: 3. Output writer

# %%

def _write_dataset(df, columns, out_path, label):
    out_cols = [c for c in columns if c in df.columns]
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise RuntimeError(f"{label}: missing columns {missing}")
    df[out_cols].to_csv(out_path, index=False)
    print(f"Wrote {out_path}  ({len(df):,} rows, {len(out_cols)} columns)")


# %% MARK: 4. Main
def correct_resource_payments():
    """Read the inputs, strip the resource profit and the resource tax from every cell and attach the non-resource
    ETR family. Return the corrected rows and the inputs that the output and the diagnostics need: the
    disaggregated rows as read (cbcr), the payment panel with its resource rates (pay), the resource economies
    (included_iso) and the reported profit and tax per row (P, T)."""
    cbcr = pd.read_csv(CBCR, low_memory=False, float_precision="round_trip")
    # I read with round_trip, which parses every float exactly (the default parser can be off in the last
    # bit). I drop the columns `etr_average_excl_resource` and `resource_factor_usd` if the file carries them,
    # so that they do not enter base_cols or collide (x/y suffixes) below.
    cbcr = cbcr.drop(columns=["resource_factor_usd", "etr_average_excl_resource"], errors="ignore")
    pay = pd.read_csv(PAY, comment="#")
    # A CbCR year without rows in the resource-payment panel would be zero-filled silently: it would get no
    # resource correction, but the ETR-gap strip would switch on for every included country, because nothing
    # is 'trusted'. I make that loud, because it means that the payment panel of the extractive prep
    # (3_25 … 3_38) does not cover every year of the CbCR data.
    _cb_years = sorted(pd.to_numeric(cbcr["year"], errors="coerce").dropna().astype(int).unique())
    _pay_years = set(pd.to_numeric(pay["year"], errors="coerce").dropna().astype(int))
    _no_pay = [y for y in _cb_years if y not in _pay_years]
    if _no_pay:
        print("\n" + "!" * 78)
        print(f"WARNING: resource-payment panel {os.path.basename(PAY)} has NO rows for CbCR year(s) "
              f"{_no_pay} (panel covers {min(_pay_years)}-{max(_pay_years)}).")
        print("         Those years get NO payment-based correction and the ETR-gap strip "
              "fires for every included country — results for them are PRELIMINARY.")
        print("         Rerun the extractive prep (3_25 -> 3_36 -> 3_38) first.")
        print("!" * 78 + "\n")
    rate = pd.read_csv(RATE, comment="#")
    rate = rate[rate["source_iso3"].str.len() == 3]   # drop non-country placeholders

    # The consolidated control table is the single source of truth. It decides which countries are genuine
    # resource economies (include), sets the curated resource profit-tax rate r and records whether the
    # country is covered by EITI. Excluded (non-resource) countries get no resource correction. The ETR-gap
    # fires only for included, non-EITI countries that carry a curated rate (see below).
    params = pd.read_csv(PARAMS)
    included_iso = set(params.loc[params["include"].astype(str).str.lower() == "yes", "iso3"])
    r_curated = pd.to_numeric(params.set_index("iso3")["resource_rate"], errors="coerce").dropna()

    # Source-aware trust. A (source, year) cell is "trusted" (I leave the correction to the actual payment
    # data and switch the ETR-gap strip off) only where its payment `data_source` for that year is genuine
    # EITI or hand-curated manual data. A country-level EITI flag alone would wrongly shield EITI-flagged
    # countries whose payments in the analysis window come from the GRD. I treat Saudi Arabian cells as
    # untrusted, because the manual Aramco CIT rate of 0.20 under-removes the resource tax (the researched
    # effective rate is 0.45, resource_country_parameters.csv). The gate decides only for cells without a
    # company anchor: the cells of a source country with a company table take the company figures (Norway
    # and Saudi Arabia among them).
    _ptrust = pay["data_source"].astype(str).str.contains("eiti|manual", case=False, na=False)
    trusted_year = {
        (str(i), int(y))
        for i, y in pay.loc[_ptrust, ["source_iso3", "year"]].dropna().to_numpy()
    }
    trusted_year -= {("SAU", y) for y in range(first_year, last_year + 1)}
    # United Arab Emirates. Among the foreign concession partners, the payments panel observes only OMV and
    # TotalEnergies. BP, CNPC, INPEX, ENI and the Indian consortium publish no payment reports, yet their
    # emirate concession income tax is in the CbCR tax line (residual non-resource ETRs of up to 0.44 where
    # the statutory rate is about zero). I therefore treat ARE as untrusted, so that the ETR-gap strips that
    # tax from the CbCR line itself at the curated r = 0.65. The emirate decrees set a 55% base rate with
    # bands up to 85%, and petroleum is exempt from the 9% federal CIT (IMF CR24, Annex VII).
    trusted_year -= {("ARE", y) for y in range(first_year, last_year + 1)}

    # Resource-dominated economies are the target set of the residual-ETR floor (applied to every economy
    # whose above-CIT residual ETR is genuinely unremoved resource tax). A country qualifies if its extractive
    # rents are at least 5% of GDP (structural resource dependence). I exclude diversified economies (UK,
    # Mexico, India, Turkey, Poland, South Africa, Ethiopia, Kenya, …), so that their above-CIT ETR, which
    # reflects withholding and minimum taxes rather than resources, is not misattributed to resources and
    # stripped. I also exclude tax havens. For them I use the functional set (config.TAX_HAVENS_FUNCTIONAL),
    # not the representation list, because the representation list only serves the presentation and must not
    # change the estimates.
    _rents = pd.to_numeric(params.set_index("iso3")["extractive_rents_pct_gdp"], errors="coerce")
    dominated_rents_iso = set(_rents[_rents >= 5.0].index)
    haven_iso = set(TAX_HAVENS_FUNCTIONAL)
    # The documented extractive parents per source country, for the floor rule: the EITI bilateral, operator
    # P2G and manual HQ-list rows of the payment panel, the EITI company-to-HQ map and the operator payments,
    # each worth at least US$1m over the window.
    _take = pay[["pre_profit_payments_usd", "post_profit_payments_usd", "equity_income_usd"]].fillna(0.0).sum(axis=1)
    _doc = pay["hq_share_basis"].isin(["eiti_bilateral", "eiti_operator", "manual_foreign"])
    _dp = _take[_doc].groupby([pay.loc[_doc, "source_iso3"], pay.loc[_doc, "hq_iso3"]]).sum()
    documented_pairs = set(_dp[_dp >= 1e6].index)
    if os.path.exists(EITI_HQ_MAP):
        _hm = pd.read_csv(EITI_HQ_MAP)
        _hm = _hm[(_hm["total_value_usd"] > 1e6) & _hm["hq_iso3"].notna()]
    else:
        _hm = pd.read_csv(EITI_HQ_PAIRS)
    documented_pairs |= set(zip(_hm["source_iso3"], _hm["hq_iso3"]))
    _ops = pd.read_csv(OPERATOR_PAY)
    _ops = _ops[_ops["value_usd"].abs() > 1e6]
    documented_pairs |= set(zip(_ops["source_iso3"], _ops["hq_iso3"]))

    # Year-aware rate resolution. Rows carrying year_start / year_end apply only within
    # [year_start, year_end] (e.g. the US rate of 35% before the TCJA in 2016-2017, or the UK's Energy
    # Profits Levy in 2022). Rows with a blank range are the sample-agnostic default. I expand the table to
    # (source, commodity, year) for the years present, with the year-specific value winning, and then merge
    # on the triple, so that no pay row is duplicated by a country that has both an agnostic and a
    # year-specific rate.
    pay = pay.merge(
        _resolve_rate_by_year(rate, pay["year"], "effective_resource_profit_tax_rate"),
        on=["source_iso3", "commodity", "year"], how="left",
    )
    stat_cit = (
        cbcr[["iso_partner", "year", "cit"]].drop_duplicates()
        .rename(columns={"iso_partner": "source_iso3", "cit": "statutory_cit"})
    )
    pay = pay.merge(stat_cit, on=["source_iso3", "year"], how="left")
    pay["rate"] = (
        pay["effective_resource_profit_tax_rate"].fillna(pay["statutory_cit"])
        .fillna(0.30).clip(lower=RATE_MIN, upper=RATE_MAX)
    )

    # The per-partner resource rate r for the ETR-gap correction below is the rate at which resource profit
    # is taxed. I use it to convert the CbCR tax in excess of the statutory rate into a resource profit base.
    # The gap operates on the CbCR income-tax line, so r must be the income-tax-based resource profit-tax
    # rate, i.e. the per-commodity `resource_profit_tax_rate.csv` (CIT plus profit-based special taxes). I
    # prefer that rate. The broader `combined_effective_rate`, which can fold in royalty or equity take that
    # is not in the CbCR income-tax line, is only a fallback where no per-commodity rate exists, followed by
    # the default of 0.30.
    ecr = pd.read_csv(ECR, comment="#")
    ecr = ecr[ecr["iso3"].astype(str).str.len() == 3]
    r_combined = ecr.set_index("iso3")["combined_effective_rate"]
    r_partner_tbl = _resolve_partner_rate_by_year(
        rate, cbcr["year"], r_curated, r_combined
    )

    post = pay["post_profit_payments_usd"].fillna(0.0)
    equity = pay["equity_income_usd"].fillna(0.0)
    # I floor a negative post-profit payment (a net tax refund) to a zero resource base. A refund must not be
    # divided back by the rate into an imputed resource loss that then adds profit back to the non-resource
    # base. Such a negative-relief path would only fire for MEX (the Pemex refund years), where it would
    # inflate Mexico's non-resource UT base by +$20.75bn (a $4.97bn refund ÷ 0.24). A positive post-profit
    # payment gives max(post / rate, equity).
    pay["resource_profit_base"] = np.where(
        post < 0, 0.0, np.maximum(post / pay["rate"], equity)
    )

    # The tax-side counterpart of resource_profit_base, kept symmetric with the profit-side branch that won:
    #   - If the post-profit branch wins, I deduct `post` from the cash tax. Since
    #     `post = (post / rate) × rate`, this equals base × rate.
    #   - If the equity branch wins, I deduct `equity × rate` from the cash tax. This treats equity_income as
    #     a profit base of size equity and removes the CIT that *would* be due on it at the project rate.
    #     Without this symmetry the ETR on the excl_resource pair would be biased: I would subtract the
    #     equity slice from profit but not the corresponding CIT from the tax line.
    #   - In the negative-post case I floor the deduction to zero, symmetric with the zero profit base
    #     above. A net refund strips nothing rather than adding tax back. (No negative-post relief is
    #     applied. In practice it would only fire for MEX.)
    equity_binds = (post >= 0) & (equity > post / pay["rate"])
    pay["resource_tax_deduction"] = np.where(
        equity_binds, equity * pay["rate"], np.maximum(post, 0.0)
    )

    pay["pre_profit"] = pay["pre_profit_payments_usd"].fillna(0.0)


    # ---- (1) Resources excluded ----
    # I aggregate the payment-level corrections to (parent, partner, year), allocate them onto the CbCR cells
    # and then run the per-cell decomposition.
    agg = (
        pay.groupby(["hq_iso3", "source_iso3", "year"], as_index=False)
        .agg(
            pre_profit_payments_usd=("pre_profit", "sum"),
            post_profit_payments_usd=("post_profit_payments_usd", "sum"),
            equity_income_usd=("equity_income_usd", "sum"),
            resource_profit_base_usd=("resource_profit_base", "sum"),
            resource_tax_deduction_usd=("resource_tax_deduction", "sum"),
        )
        .rename(columns={"hq_iso3": "iso_parent", "source_iso3": "iso_partner"})
    )
    for c in agg.columns:
        if c.endswith("_usd"):
            agg[c] = pd.to_numeric(agg[c], errors="coerce").fillna(0.0)

    payment_cols = [
        "pre_profit_payments_usd", "post_profit_payments_usd",
        "equity_income_usd", "resource_profit_base_usd",
        "resource_tax_deduction_usd",
    ]

    # ---- Diagnostic ----
    # Corrections whose (parent, partner, year) cell has no CbCR line would be lost silently in
    # the left merge below. I make that loss visible: I write the unmatched cells and their US$ volume, so that
    # mis-attributed HQ shares (payments assigned to HQs with no line in the source country) can be audited.
    _cells = cbcr[["iso_parent", "iso_partner", "year"]].drop_duplicates()
    _chk = agg.merge(_cells, on=["iso_parent", "iso_partner", "year"], how="left", indicator=True)
    _unm = _chk[_chk["_merge"] == "left_only"].drop(columns="_merge")
    _diag_path = variant_path(f"{data_intermediate_extractive}resource_correction_unmatched_cells.csv")
    _bkt = ["pre_profit_payments_usd", "post_profit_payments_usd", "equity_income_usd"]
    if len(_unm):
        _tot = _unm[_bkt].sum().sum()
        _dom = _unm[_unm.iso_parent == _unm.iso_partner][_bkt].sum().sum()
        print(f"  [diag] {len(_unm):,} correction cells have NO CbCR line and are dropped: "
              f"${_tot/1e9:,.1f}B total (${_dom/1e9:,.1f}B domestic non-reporter, "
              f"${(_tot-_dom)/1e9:,.1f}B foreign) → {_diag_path}")
        _unm.sort_values(_bkt[0], ascending=False).to_csv(_diag_path, index=False)
    else:
        print("  [diag] every correction cell matched a CbCR line")

    df = _allocate_payments_to_cbcr_cells(cbcr, agg, payment_cols)

    # I drop the reported-profit ETR columns from the resource-corrected outputs. The disaggregated file keeps
    # them, and the resource-corrected files get the non-resource family computed below.
    df = df.drop(columns=[c for c in ETR_COLS_TO_DROP if c in df.columns])
    df = df.merge(r_partner_tbl, on=["iso_partner", "year"], how="left",
                  validate="many_to_one")

    P = pd.to_numeric(df[PCOL], errors="coerce").fillna(0.0)
    T = pd.to_numeric(df[TCOL], errors="coerce").fillna(0.0)

    # ---- Resource decomposition: the ETR gap unified with the external estimate ----
    # The non-resource portion of a cell is taxed at the statutory CIT `c`. Any tax *in excess* of that
    # (observed ETR > c) must come from resource activity taxed at the higher resource rate `r`. So:
    #     resource_profit = (T − c·P) / (r − c),   resource_tax = r · resource_profit
    # hard-capped at the cell's reported profit and tax. For zero-CIT jurisdictions (UAE, Bahrain) the gap
    # equals all reported tax. This correctly strips the petroleum tax of the foreign oil majors, which the
    # external path with domestic_share would misplace onto the domestic cell with a tax of about zero.
    #
    # I hard-cap both legs. A profit-only cap that scaled the tax deduction by the profit-cap ratio would never
    # cap the tax at the reported tax, which would leave a negative residual non-resource tax for heavily taxed
    # resource cells (36 countries). Where the gap is inert (observed ETR ≤ statutory CIT, typical for high-CIT
    # cells with exempt or loss-netted profit), I fall back to the external estimate, hard-capped per cell. A
    # negative post-profit payment (a net refund) strips nothing (see the base construction above).
    c = pd.to_numeric(df["cit"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=0.60)
    r = pd.to_numeric(df["resource_rate_partner"], errors="coerce").fillna(0.30).clip(RATE_MIN, RATE_MAX)

    # The eligibility for the ETR-gap strip comes from the consolidated control table:
    #   • included_cell: a genuine resource economy (include=yes). Excluded (non-resource) countries get no
    #     correction at all (see below). This prevents false positives. Without the gate, Ireland, France,
    #     Belgium, Singapore, … would be pulled in by trivial WB rent-proxy panel rows and stripped of huge
    #     spurious amounts.
    #   • not EITI: the EITI panel is authoritative and comprehensive for EITI countries, so the gap is off for
    #     them. Resource profit is removed only on the EITI (source, HQ) pairs that carry a panel amount
    #     (through the external path below), and nothing is removed elsewhere.
    #   • a curated rate: the gap fires only where I actually have a researched resource rate r to convert the
    #     tax gap into a resource profit base.
    # Elsewhere an above-statutory ETR is not necessarily resource-related (it can reflect withholding taxes,
    # one-off settlements, etc.), so the gap must not fire.
    included_cell = df["iso_partner"].isin(included_iso)
    # The source-aware trust gate works per year, not with a country-level EITI flag. A cell is trusted (gap
    # off) only if its actual (iso_partner, year) payment source is EITI or manual data (see `trusted_year`
    # above). An EITI-flagged country with GRD data in the window is therefore not trusted and does get the
    # ETR-gap correction.
    _cellkey = list(zip(df["iso_partner"].astype(str), df["year"].astype("Int64").astype("int64")))
    trusted_cell = pd.Series([k in trusted_year for k in _cellkey], index=df.index) & included_cell
    # The UAE is a hybrid. The premise of the gap (the state's capture flows through the income-tax line)
    # holds for the foreign concession partners (55-85% emirate income tax) but not for ADNOC's domestic cell,
    # whose capture is royalties and dividends outside the tax line. The domestic ARE cell therefore stays
    # trusted (the external route: max(post ÷ r, equity), with the IMF-grounded equity fractions), while the
    # foreign ARE cells use the gap.
    trusted_cell |= ((df["iso_partner"] == "ARE") & (df["iso_parent"] == "ARE")
                     & included_cell)
    has_curated_rate = df["iso_partner"].isin(set(r_curated.index))
    gap_eligible = included_cell & (~trusted_cell) & has_curated_rate
    gap_active = gap_eligible & (r > c) & (T > c * P)
    if "etr_gap" in RESOURCE_INFERRED_OFF:              # switch: no strip inferred from the ETR gap
        gap_active = gap_active & False
    with np.errstate(divide="ignore", invalid="ignore"):
        rp_gap_raw = np.where(gap_active, (T - c * P) / (r - c), 0.0)
    rp_gap = np.clip(rp_gap_raw, 0.0, np.where(P > 0, P, 0.0))
    # The tax stripped by the gap is all the tax in excess of the statutory CIT that would be due on the
    # residual non-resource profit (P − resource_profit). For a fully resource-based cell (rp_gap close to P)
    # this removes all the tax, so zero-CIT producers (UAE, Bahrain) end with a non-resource ETR of about zero
    # and stay havens regardless of r. (Using `min(r·rp_gap, T)` instead would leave r·P of tax behind on
    # full-resource cells and lift the UAE's non-resource ETR to about 0.19.) For partial cells the residual
    # ETR equals the statutory rate c, as intended.
    rt_gap = np.where(gap_active, np.clip(T - c * (P - rp_gap), 0.0, T), 0.0)

    base_raw = df["resource_profit_base_usd"]
    tax_raw = df["resource_tax_deduction_usd"]
    neg_relief = (tax_raw < 0).to_numpy()

    # Inert resource cells have an observed ETR at or below the statutory rate, so the gap finds no
    # differentially taxed resource profit. There I cannot reliably identify the resource tax, and the external
    # tax estimate over-strips high-CIT countries (e.g. COD, with a statutory rate of 31.7% and a reported
    # foreign ETR of 10.9%), pushing them below their own reported rate. I therefore strip the external resource
    # profit base at the cell's own reported ETR. This removes the resource activity from the pool while
    # leaving the residual non-resource ETR equal to the reported ETR, so high-CIT economies are not turned
    # into havens artificially.
    reported_etr = np.where(P > 0, T / P, 0.0)
    rp_ext = np.where(P > 0, np.minimum(base_raw, P), 0.0)
    rt_ext = np.clip(rp_ext * reported_etr, 0.0, np.maximum(T, 0.0))

    use_gap = gap_active.to_numpy() & (rp_gap > 0)
    relief_use = neg_relief & (~use_gap)
    rp = np.where(use_gap, rp_gap, rp_ext)
    rt = np.where(use_gap, rt_gap, rt_ext)
    # The negative-post relief is inert. `resource_tax_deduction` is floored at 0, so `relief_use` is always
    # False and these lines are no-ops: a negative post-profit payment strips nothing (see the base
    # construction).
    rp = np.where(relief_use, base_raw, rp)
    rt = np.where(relief_use, tax_raw, rt)

    # ---- Company-anchored strips (3_38 build_company_anchors) ----
    # Where a few documented companies are a source country's resource sector (Saudi Arabia: Saudi Aramco), I
    # read the strip per (parent, source, year) from the company's audited accounts (profit = the upstream
    # segment result, tax = the Saudi income tax and zakat settled on it), capped at the cell's positive profit
    # and tax. Every other cell of an anchored source gets no strip, because only the documented operators are
    # resource activity. This route replaces the ETR-gap and payment routes there and is exempt from the
    # floors.
    _anc_path = _resource_table(f"{data_intermediate_extractive}company_anchored_strips.csv")
    anchored_cell = np.zeros(len(df), dtype=bool)
    df["resource_anchor_tax_inferred"] = False
    df["resource_anchor_tax_prorata_usd"] = 0.0
    if os.path.exists(_anc_path):
        _anc = pd.read_csv(_anc_path)
        if len(_anc):
            _key = df[["iso_parent", "iso_partner", "year"]].copy()
            _key["year"] = pd.to_numeric(_key["year"], errors="coerce").astype("Int64")
            _anc["year"] = pd.to_numeric(_anc["year"], errors="coerce").astype("Int64")
            _anc_keys = ["iso_parent", "iso_partner", "year"]
            if _anc[_anc_keys].isna().any().any():
                raise ValueError("Company anchors contain missing parent/source/year keys")
            # Where the file has no anchor mode or no column for the profit with undocumented tax, I take
            # country mode and zero. I aggregate the anchors to one row per cell, so that several groups in
            # one cell do not expand the CbCR merge. Missing facts stay missing until the final application,
            # where they imply no documented deduction.
            if "anchor_mode" not in _anc.columns:
                _anc["anchor_mode"] = "country"
            _anc["anchor_mode"] = _anc["anchor_mode"].fillna("country")
            if "profit_tax_undocumented_usd" not in _anc.columns:
                _anc["profit_tax_undocumented_usd"] = 0.0
            _anc = _anc.groupby(_anc_keys, as_index=False).agg(
                profit_removed_usd=("profit_removed_usd", lambda s: s.sum(min_count=1)),
                tax_removed_usd=("tax_removed_usd", lambda s: s.sum(min_count=1)),
                profit_tax_undocumented_usd=("profit_tax_undocumented_usd", "sum"),
                anchor_mode=("anchor_mode", "first"),
            )
            _m = _key.merge(_anc[["iso_parent", "iso_partner", "year", "profit_removed_usd", "tax_removed_usd",
                                  "profit_tax_undocumented_usd", "anchor_mode"]],
                            on=_anc_keys, how="left", validate="many_to_one")
            # In country mode every cell of the source is anchored (undocumented cells strip nothing). In
            # cell mode (UAE) only the listed cells are anchored, and the source's other cells keep the
            # inferred route.
            country_src = set(_anc.loc[_anc["anchor_mode"] == "country", "iso_partner"])
            cell_mode = (_m["anchor_mode"] == "cell").to_numpy()
            anchored_cell = df["iso_partner"].isin(country_src).to_numpy() | cell_mode
            _ap = _m["profit_removed_usd"].fillna(0.0).to_numpy()
            _at = _m["tax_removed_usd"].fillna(0.0).to_numpy()
            P_pos_a, T_pos_a = np.where(P > 0, P, 0.0), np.where(T > 0, T, 0.0)
            rp = np.where(anchored_cell, np.clip(_ap, 0.0, P_pos_a), rp)
            # For a cell-mode anchor with documented profit but no documented tax (e.g. the Japanese and
            # Korean UAE partners), I infer the tax side as in the ETR-gap route: the residual profit is left
            # taxed at the statutory CIT c, and the rest of the cell's tax is resource tax.
            tax_inferred = cell_mode & _m["tax_removed_usd"].isna().to_numpy() & _m["profit_removed_usd"].notna().to_numpy()
            _at_inf = np.clip(T - c.to_numpy() * np.clip(P - rp, 0.0, None), 0.0, T_pos_a)
            # Where a group's profit is documented but its tax is not, I remove the same share of the cell's tax as
            # of its profit, because a missing tax figure does not mean that no tax was paid. The share is the
            # removed profit of these groups over the cell's profit. Their part of the removed profit is taken in
            # proportion to their part of the documented profit, so that the cap at the cell's profit applies to
            # both parts alike. A tax of zero that a source states stays zero.
            _undoc = _m["profit_tax_undocumented_usd"].fillna(0.0).to_numpy()
            with np.errstate(divide="ignore", invalid="ignore"):
                _undoc_share = np.where(_ap > 0, np.clip(_undoc / _ap, 0.0, 1.0), 0.0)
                _at_pro = np.where(P_pos_a > 0, T_pos_a * rp * _undoc_share / P_pos_a, 0.0)
            _at_pro = np.where(anchored_cell & ~tax_inferred, _at_pro, 0.0)
            rt = np.where(anchored_cell,
                          np.where(tax_inferred, _at_inf, np.clip(np.clip(_at, 0.0, None) + _at_pro, 0.0, T_pos_a)),
                          rt)
            df["resource_anchor_tax_inferred"] = tax_inferred
            df["resource_anchor_tax_prorata_usd"] = _at_pro
            print(f"  [company anchors] {sorted(set(_anc['iso_partner']))}: profit removed "
                  f"${rp[anchored_cell].sum()/1e9:,.1f}B, tax ${rt[anchored_cell].sum()/1e9:,.1f}B "
                  f"({int((anchored_cell & (rp > 0)).sum())} anchored cells with a strip), of which tax removed "
                  f"in proportion to undocumented profit ${_at_pro.sum()/1e9:,.1f}B")

    # ---- Residual-ETR floor for resource-dominated economies ----
    # I apply the floor to every resource-dominated economy whose residual non-resource ETR still exceeds the
    # statutory CIT after the paths above. In those cells the payment data under-removed the resource tax
    # (weak manual, EITI or GRD coverage, or a too-low assumed rate), leaving unremoved resource profit taxed
    # above the statutory rate. I strip that residual tax in excess of the CIT and the matching resource profit
    # in lockstep at the rate rr (at least the CIT), so that the residual non-resource ETR lands at the
    # statutory rate c. The floor is gated to resource-dominated, non-haven cells, so that it does not touch
    # diversified economies (UK, Mexico, India, …) whose above-CIT ETR comes from withholding and minimum taxes,
    # not from resources.
    resid_P = P - rp
    resid_T = T - rt
    # The floor reads an ETR above the CIT as unstripped resource tax. That reading holds only under three
    # conditions. First, resource profit must be taxed above the CIT (r > c). Where r <= c, the fallback of c + 5
    # percentage points below would turn each point of excess ETR into 20% of the cell's profit. Second, the
    # economy must be structurally resource-dependent (rents of at least 5% of GDP). A test on the resource share
    # of the country's CbCR profit would be fed by the payment route itself and would let in Egypt, Indonesia,
    # Ecuador and Tanzania. Third, the group must be documented as extractive there (or the cell must be the
    # domestic cell). The floor is not meant for whole cells of banks, retailers or carmakers.
    documented_or_domestic = np.array(
        [(s, h) in documented_pairs for s, h in zip(df["iso_partner"], df["iso_parent"])]
    ) | (df["iso_parent"] == df["iso_partner"]).to_numpy()
    dominated = (
        (~anchored_cell)
        & included_cell.to_numpy()
        & (~df["iso_partner"].isin(haven_iso).to_numpy())
        & df["iso_partner"].isin(dominated_rents_iso).to_numpy()
        & (r.to_numpy() > c.to_numpy() + 1e-9)
        & documented_or_domestic
    )
    over_floor = dominated & (~neg_relief) & (resid_P > 0) & (resid_T > c * resid_P)
    if "etr_floor" in RESOURCE_INFERRED_OFF:            # switch: no resource-dominated ETR floor
        over_floor = over_floor & False
    rr_floor = np.maximum(r, c + 0.05)   # remove strictly above CIT so the strip converges
    with np.errstate(divide="ignore", invalid="ignore"):
        add_rp = np.where(over_floor, np.clip((resid_T - c * resid_P) / (rr_floor - c), 0.0, resid_P), 0.0)
    add_rt = np.where(over_floor, np.clip(resid_T - c * (resid_P - add_rp), 0.0, resid_T), 0.0)
    floored_cell = add_rp > 0
    rp = rp + add_rp
    rt = rt + add_rt
    if floored_cell.any():
        _fc = sorted(set(df.loc[pd.Series(floored_cell, index=df.index), "iso_partner"]))
        print(f"  [resource-dominated ETR floor] capped residual non-resource ETR at "
              f"statutory CIT on {int(floored_cell.sum()):,} cell(s) across "
              f"{len(_fc)} economies: {_fc}; extra profit stripped "
              f"${add_rp.sum()/1e9:.1f}B, extra tax ${add_rt.sum()/1e9:.1f}B.")

    # ---- Manual resource-rent correction for under-corrected producers ----
    # For Equatorial Guinea (GNQ) and Papua New Guinea (PNG), the standard correction under-removes the
    # resource profit, and that profit drives their loss under unitary taxation. Malaysia (MYS) is in the set
    # as well, but its cells are anchored on company figures, so the floor does not reach them. For these
    # producers, the state take ÷ the assumed statutory rate falls far short of the actual resource economic
    # profit (a weak fiscal regime, in which a large slice of the oil and gas profit is retained by the
    # companies and lightly taxed). The residual resource profit therefore stays in the pool and is
    # reallocated away by the activity formula. I floor their stripped base at the country's resource rent
    # (the layered best estimate of rents_combined_yearly.csv, EITI before EIA, BGS and WB), capped at the
    # cell's reported profit. This is equivalent to backing the resource profit out at the country's actual
    # effective rate (take ÷ rent) rather than at the assumed statutory rate. Because of the cap, a diversified
    # producer loses only its resource-rent share, not its manufacturing profit. I remove the extra profit at
    # the cell's reported ETR, so the residual non-resource ETR is unchanged. This is a named manual
    # correction, not a general floor, and it never touches any other economy.
    RENTFLOOR_MANUAL_ISO = {"GNQ", "PNG", "MYS"}
    _rent = pd.read_csv(RENTS)
    _rent["_r"] = pd.to_numeric(_rent["rent_best_usd"], errors="coerce").fillna(0.0)
    _rent_sy = _rent.groupby(["iso3", "year"], as_index=False)["_r"].sum()
    _rent_map = {(str(i), int(y)): float(v) for i, y, v
                 in zip(_rent_sy["iso3"], _rent_sy["year"], _rent_sy["_r"])}
    rent_cell = np.array([_rent_map.get((str(i), int(y)), 0.0)
                          for i, y in zip(df["iso_partner"], df["year"])], dtype=float)
    _g = [df["iso_partner"], df["year"]]
    cur_rp_sy = pd.Series(rp, index=df.index).groupby(_g).transform("sum").to_numpy()
    P_pos = np.where(P > 0, P, 0.0)
    P_sy = pd.Series(P_pos, index=df.index).groupby(_g).transform("sum").to_numpy()
    # target stripped base per (source, year) = min(max(current, rent), booked profit)
    target_sy = np.minimum(np.maximum(cur_rp_sy, rent_cell), P_sy)
    gap_sy = np.maximum(target_sy - cur_rp_sy, 0.0)
    w_pos = np.where(P_sy > 0, P_pos / P_sy, 0.0)     # share the gap by positive profit
    rentfloor_gate = (~anchored_cell) & df["iso_partner"].isin(RENTFLOOR_MANUAL_ISO).to_numpy()
    add_rp_rent = np.where(rentfloor_gate, gap_sy * w_pos, 0.0)
    add_rp_rent = np.clip(add_rp_rent, 0.0, np.maximum(P_pos - rp, 0.0))   # never exceed remaining profit
    add_rt_rent = add_rp_rent * reported_etr                              # remove at reported ETR
    rentfloor_cell = add_rp_rent > 1.0
    rp = rp + add_rp_rent
    rt = rt + add_rt_rent
    if rentfloor_cell.any():
        _rf = sorted(set(df.loc[pd.Series(rentfloor_cell, index=df.index), "iso_partner"]))
        print(f"  [manual resource-rent correction] raised the stripped base to the resource "
              f"rent on {int(rentfloor_cell.sum()):,} cell(s) across {len(_rf)} named producers: "
              f"{_rf}; extra profit stripped ${add_rp_rent.sum()/1e9:.1f}B.")

    # I enforce the no-negative-relief rule on every inferred layer. np.clip(x, 0, T) returns T when T < 0
    # (reversed bounds), which would erase a reported refund even when no resource profit was removed. I keep
    # the signed reported and source facts. Deductions can only remove positive bases.
    rp = np.clip(rp, 0.0, P_pos)
    rt = np.clip(rt, 0.0, np.maximum(T, 0.0))

    # Excluded (non-resource) countries get no resource correction at all. Their excl_resource profit and tax
    # equal the reported baseline.
    excluded_cell = (~included_cell).to_numpy()
    rp = np.where(excluded_cell, 0.0, rp)
    rt = np.where(excluded_cell, 0.0, rt)
    df["resource_profit_base_usd"] = rp
    df["resource_tax_deduction_usd"] = rt
    df["resource_company_anchor_applied"] = anchored_cell & ~excluded_cell
    df["resource_anchor_tax_inferred"] = df["resource_anchor_tax_inferred"].astype(bool) & ~excluded_cell
    df["resource_anchor_tax_prorata_usd"] = np.where(excluded_cell, 0.0, df["resource_anchor_tax_prorata_usd"])
    df["resource_residual_etr_floor_applied"] = floored_cell & ~excluded_cell
    df["resource_rent_floor_applied"] = rentfloor_cell & ~excluded_cell
    df["resource_correction_method"] = np.where(
        excluded_cell, "excluded_non_resource",
        np.where(anchored_cell & df["resource_anchor_tax_inferred"].to_numpy(), "company_anchor_tax_inferred",
        np.where(anchored_cell, "company_anchor",
        np.where(rentfloor_cell, "manual_resource_rent_floor",
        np.where(floored_cell & ~excluded_cell, "resource_dominated_etr_floor",
        np.where(use_gap, "etr_gap",
                 np.where(relief_use, "external_relief", "external_reported_etr")))))),
    )

    # excl_resource: I strip resource_profit_base from the profit and the matching resource_tax_deduction from
    # the cash tax. The deduction follows whichever branch (post or equity) won on the profit side, so the ratio
    # `excl_tax / excl_profit` is symmetric in either case.
    df["profit_loss_excl_resource"] = P - df["resource_profit_base_usd"]
    df["income_tax_paid_on_cash_basis_excl_resource"] = (
        T - df["resource_tax_deduction_usd"]
    )

    # The per-parent-year totals (the UT pools).
    grp = df.groupby(["iso_parent", "year"])
    df["total_profit_loss_excl_resource"] = (
        grp["profit_loss_excl_resource"].transform("sum")
    )

    if TAX_MEASURE == "accrued":
        df = _accrued_tax_measure(df)

    # The non-resource ETR family, computed on the excl_resource pair.
    partner_year, pair_year = _compute_excl_resource_etrs(df)
    df = _attach_etrs(df, partner_year, pair_year)
    df = _fill_excl_resource_etrs(df)
    return df, {"cbcr": cbcr, "pay": pay, "included_iso": included_iso, "P": P, "T": T}


def main():
    df, inputs = correct_resource_payments()
    cbcr, P, T = inputs["cbcr"], inputs["P"], inputs["T"]

    # ---- Columns of the output file ----
    base_cols = [c for c in cbcr.columns if c not in ETR_COLS_TO_DROP]
    etr_cols = ETR_COLS_PARTNER + [ETR_COL_PAIR]

    excl_cols = (
        base_cols
        + [
            "resource_rate_partner",
            "resource_correction_method",
            "resource_company_anchor_applied",
            "resource_anchor_tax_inferred",
            "resource_anchor_tax_prorata_usd",
            "resource_residual_etr_floor_applied",
            "resource_rent_floor_applied",
            "resource_profit_base_usd",
            "resource_tax_deduction_usd",
            "post_profit_payments_usd",
            "equity_income_usd",
            "profit_loss_excl_resource",
            "income_tax_paid_on_cash_basis_excl_resource",
            "total_profit_loss_excl_resource",
        ]
        + etr_cols
    )

    _write_dataset(df, excl_cols, OUT_EXCL, "cbcr_main_excl_resource.csv")

    # ---- Headline diagnostics ----
    print()
    sum_p = P.sum() / 1e9
    sum_t = T.sum() / 1e9
    print(f"Σ reported profit:                   ${sum_p:>10,.0f} B")
    print(f"Σ reported cash tax:                 ${sum_t:>10,.0f} B")
    print()
    sum_excl_p = df["profit_loss_excl_resource"].sum() / 1e9
    sum_excl_t = df["income_tax_paid_on_cash_basis_excl_resource"].sum() / 1e9
    sum_base = df["resource_profit_base_usd"].sum() / 1e9
    sum_dedn = df["resource_tax_deduction_usd"].sum() / 1e9
    print("excl_resource:")
    print(f"  profit_loss_excl_resource                = reported − ${sum_base:,.0f} B base   → ${sum_excl_p:,.0f} B")
    print(f"  income_tax_paid_on_cash_basis_excl_resource = reported − ${sum_dedn:,.0f} B tax-dedn  → ${sum_excl_t:,.0f} B")
    if "resource_correction_method" in df.columns:
        ms = df.groupby("resource_correction_method")["resource_tax_deduction_usd"].sum() / 1e9
        print("    tax deduction by method (USD B): "
              + ", ".join(f"{k}={v:,.0f}" for k, v in ms.items()))
        # I write which method removed how much, per source country and year.
        mt = (df[df["resource_profit_base_usd"] > 0]
              .groupby(["iso_partner", "year", "resource_correction_method"], as_index=False)
              [["resource_profit_base_usd", "resource_tax_deduction_usd"]].sum())
        mt.to_csv(variant_path(f"{data_intermediate_extractive}resource_correction_methods.csv"), index=False)
    n_dist_nan_pair = df.loc[df["is_distributed"] == 1, ETR_COL_PAIR].isna().sum()
    n_rep_nonnan_pair = df.loc[df["is_distributed"] == 0, ETR_COL_PAIR].notna().sum()
    print()
    print(f"ETR sanity ({ETR_COL_PAIR}):")
    print(f"  distributed rows with NaN: {n_dist_nan_pair:,}/{(df['is_distributed']==1).sum():,}")
    print(f"  reported rows with value:  {n_rep_nonnan_pair:,}/{(df['is_distributed']==0).sum():,}")


if __name__ == "__main__":
    main()
