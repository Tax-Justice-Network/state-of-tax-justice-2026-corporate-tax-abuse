# %%
"""
1 — Clean and merge the OECD CbCR panel and its auxiliary data.

This script cleans the aggregate country-by-country reports (CbCR) that the OECD publishes and merges them with the
auxiliary data that the later scripts need. It drops the partner rows that are not jurisdictions (stateless entities
and the reporters' own totals) and the submissions that cannot be used, corrects reporting errors and applies the
corrections for dividends counted twice (García-Bernardo, Janský and Zucman). It then computes the effective tax
rates (ETRs) on reported profit with _etr_construction.compute_partner_year_etrs and merges the statutory corporate
income tax (CIT) rates, GDP and population, wages, regions and the World Bank income groups, which include the
tax-haven flag. Finally, it classifies every jurisdiction-year by the share of US groups' positive profit that is
taxed below 15%, from the country-by-country statistics of the US Internal Revenue Service (IRS SOI), and writes the
destination sets of the irs15_gate variants of script 5.

Section outline (numbers match the cell headings below):
1. Setup.
2. Read the country-by-country data.
   2.1 Read and reshape the OECD file.
   2.2 Rows that are not jurisdictions and unusable submissions.
   2.3 Column names, analysis window and checks.
   2.4 Rest-of-world (WXD) rows.
3. Correct reporting errors.
   3.1 Denmark 2023: swapped profit panels.
   3.2 Implausible units and inflated cells.
   3.3 US groups' employees in 2023.
   3.4 Saudi Arabia 2021 and 2023.
   3.5 Tax entered with the wrong sign (Cepsa, Maersk).
   3.6 Listed cells.
   3.7 Loss swings in tax havens.
4. Corrected profit.
   4.1 Dividends counted twice (García-Bernardo, Janský and Zucman).
   4.2 The UK's domestic profit in 2023.
   4.3 Rest-of-world rows after the corrections.
   4.4 Log variables.
5. Effective tax rates.
6. Other variables.
   6.1 Manual values and the country-year grid.
   6.2 Corporate income tax rates.
   6.3 GDP and population.
   6.4 Wages from the ILO data.
   6.5 Wages predicted from GDP and population, payroll.
   6.6 Regions and World Bank income groups.
   6.7 US groups' profit taxed below 15% (IRS).
7. Merge, save and check.
   7.1 Merge.
   7.2 Save.
   7.3 Final checks.

Pipeline step 1 — first step, before 1a.

Reads:
  {data_raw}cbcr/oecd_cbcr_tableI_2026-08.csv.gz             — OECD CbCR Table I (main input, config.cbcr_data)
  {data_raw}tax_rates/oecd_cit_rates_2026-02.csv             — OECD statutory CIT rates
  {data_raw}tax_rates/taxfoundation_cit_rates_1980-2023.xlsx — Tax Foundation CIT rates (fills OECD gaps)
  {data_raw}tax_rates/irs_soi_cbcr_table4/<yy>it04cbc.xlsx   — IRS SOI CbCR Table 4 (by sub-group ETR), 2017–2023
  {data_raw}tax_rates/irs_soi_cbcr_table4/<yy>it01bcbc.xlsx  — IRS SOI CbCR Table 1B (positive-profit sub-groups),
                                                               2017–2023
  {data_raw}macro_variables/manual_imputation_values.csv     — hand-curated GDP, population, CIT and wage values with
                                                               their sources
  {data_raw}macro_variables/wb_gdp_population_2026-02.csv    — World Bank population (DataBank export)
  {data_raw}macro_variables/wb_gdp_current_usd_2026-08.csv   — World Bank GDP snapshot (the single GDP source)
  {data_raw}macro_variables/ilo_wages_ear4mth_2025-08.csv    — monthly wages of the International Labour
                                                               Organization (ILO)
  {data_raw}macro_variables/wb_cpi_2026-04.csv               — national consumer price indices (to extrapolate wages)
  {data_raw}macro_variables/wb_fx_official_rate_2026-02.csv  — exchange rates (to extrapolate wages)
  {data_raw}macro_variables/bea_mofa_employment_by_country_2022-2023.csv — employment of US groups' foreign
                                                               affiliates, US Bureau of Economic Analysis (BEA) (3.3)
  {data_raw}extractive/source_tables/SAU_aramco_financials_2016_2024.csv — Saudi Aramco's figures (3.4)
  {data_raw}extractive/source_tables/SAU_other_groups_yearly_sums_2018_2023.csv — other Saudi groups (3.4)
  {data_raw}country_info/tjn_portal_unilateral_cross_2024-06.csv — regions (region_tjn) and membership flags
  {data_raw}country_info/wb_income_groups_2026-07.csv        — pinned snapshot of the World Bank income groups
                                                               (created from the World Bank API if absent, then reused)

Writes:
  {data_final}/cbcr_main.csv                    — all profit groupings with the merged auxiliary columns
  {data_final}/cbcr_main_allsubgroupsonly.csv   — the "Total (All sub-groups)" panel only, the working sample that 1a
                                                  and 2 read
  {data_intermediate}irs_low_tax_destinations.csv — destination set of the irs15_gate variants: one row per
                                                  (iso_partner, year) with profit by ETR band, the share below 15%
                                                  (or its bounds), method and `qualifies` (share > 50%)
  {data_intermediate}irs_low_tax_destinations_ge30.csv — the same with share ≥ 30%
  {data_intermediate}irs_soi_cbcr_table4_long.csv — IRS SOI CbCR Table 4 as parsed: one row per tax year × ETR
                                                  band × listed jurisdiction (profit, tax), for the figure scripts
  {data_intermediate}cbcr_reporter_detail.csv  — partner detail of every submission in the OECD file (2.2), for the
                                                  tables of limited-detail reporters in script 2
  {output_root}/diagnostics/stateless_in_wxd/stateless_removed_from_wxd.csv — stateless amounts taken off WXD (2.2)
  {output_root}/diagnostics/haven_loss_swings/haven_loss_swings.csv    — loss panels reset in tax havens (3.7)
  {output_root}/diagnostics/cbcr_profit_imputation/uk_domestic_profit_carryforward.csv — the filled UK cell (4.2)
  {data_raw}country_info/wb_income_groups_2026-07.csv — written only if it is absent (pinned snapshot from the
                                                  World Bank API)

Usage:
  python src/1_clean.py
  Before running, activate the conda environment (environment.yml) and set first_year / n_years and the raw-data
  paths in config.py. When updating to a new CbCR vintage, consult the OECD disclaimer and country notes for
  reporting anomalies:
    https://www.oecd.org/tax/tax-policy/anonymised-and-aggregated-cbcr-statistics-disclaimer.pdf
    https://www.oecd.org/tax/tax-policy/COUNTRY-cbcr-country-specific-analysis.pdf

Author: Tax Justice Network (based on the method of García-Bernardo and Janský).
Created: 2023-08-04.  Last updated: 2026-11-23.
"""

# %% MARK: 1. Setup
# This cell holds the imports and two technical helpers (checks for duplicates and missing values). I define the
# functions with methodological content in their sections below, right before I use them.

import re
import sys
from pathlib import Path as _Path

import pandas as pd
import numpy as np
import requests
import statsmodels.formula.api as smf

# Windows consoles often default to a legacy code page (for example cp1252) that cannot print the non-ASCII
# characters this script emits (accented country names, dashes in messages), and the script would then stop with a
# UnicodeEncodeError. I therefore force UTF-8 output. This is harmless on other systems.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

import pycountry

from config import *
from _etr_construction import compute_partner_year_etrs
from _uk_domestic_profit_imputation import fill_uk_domestic_profit
from _column_order import COLUMNS_STAGE_1, apply_canonical_order

analysis_years = list(range(first_year, first_year + n_years))
last_year = analysis_years[-1]

CBCR_NUMERIC_VARS = [
    "profit_loss_before_income_tax_corrected",
    "profit_loss_before_income_tax",
    "income_tax_paid_on_cash_basis",
    "income_tax_accrued_current_year",
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
    "stated_capital",
    "total_revenues",
    "related_party_revenues",
    "holding_or_managing_ip",
    "n_entities",
]


def check_missing_values(df, critical_columns):
    """
    Print the number and share of missing values in the selected columns.
    If a column is absent, I say so explicitly.
    """
    total_observations = len(df)

    for column in critical_columns:
        if column not in df.columns:
            print(f"Column '{column}' is not present in the DataFrame.")
            continue

        count = df[column].isna().sum()
        if count > 0:
            percentage = (
                (count / total_observations) * 100 if total_observations > 0 else np.nan
            )
            print(
                f"{count} missing values found in column '{column}' "
                f"({percentage:.2f}% of total observations)."
            )
        else:
            print(f"No missing values found in column '{column}'.")


def check_duplicates(df, name, subset=None):
    """
    Print whether duplicates are present.
    """
    if df.duplicated(subset=subset).any():
        print(f"Warning: {name} contains duplicate rows.")
    else:
        print(f"No duplicates found in {name}.")


# %% MARK: 2. Read the country-by-country data
# The input is OECD CbCR Table I (aggregate country-by-country reports, an SDMX bulk export, config.cbcr_data). It
# has one row per reporting (parent) jurisdiction, partner jurisdiction, profit grouping (all sub-groups, sub-groups
# with positive profits, sub-groups with negative profits) and fiscal year.

# %% MARK: 2.1 Read and reshape the OECD file

cbcr_variables = [
    "REF_AREA",
    "Reference area",
    "COUNTERPART_AREA",
    "Counterpart area",
    "Profit grouped by",
    "TIME_PERIOD",
    "Unrelated party revenues",
    "Profit (loss) before income tax",
    "Adjusted profit (loss) before income tax",
    "Income tax paid (on cash basis)",
    "Income tax accrued - current year",
    "Employees",
    "Tangible assets other than cash and cash equivalents",
    "Stated capital",
    "Total revenues",
    "Related party revenues",
    "Holding or managing intellectual property business activity",
    "Multinational enterprise groups",
    "Multinational enterprise sub-groups",
    "Entities",
]

cbcr_long = pd.read_csv(cbcr_data)

# Guard against duplicates. The default aggfunc of pivot_table silently averages duplicate rows, so the selected
# measures must be unique per (parent, partner, grouping, year) cell. The raw file already carries duplicate cells
# on measures I do not select (ETR percentiles, distinguished only by STATISTICAL_OPERATION). A future vintage that
# adds such a dimension to a selected measure would therefore corrupt the data without this check.
_pivot_index_cols = {
    "REF_AREA", "Reference area", "COUNTERPART_AREA", "Counterpart area",
    "Profit grouped by", "TIME_PERIOD",
}
_value_measures = [m for m in cbcr_variables if m not in _pivot_index_cols]
_n_dup_cells = int(
    cbcr_long.loc[cbcr_long["Measure"].isin(_value_measures)]
    .duplicated(
        subset=["REF_AREA", "COUNTERPART_AREA", "Profit grouped by",
                "TIME_PERIOD", "Measure"]
    )
    .sum()
)
if _n_dup_cells:
    raise ValueError(
        f"{_n_dup_cells} duplicate (cell, measure) rows among the selected CbCR "
        "measures — pivot_table would silently average them; inspect the vintage."
    )

cbcr_wide = pd.pivot_table(
    cbcr_long,
    index=[
        "REF_AREA",
        "Reference area",
        "COUNTERPART_AREA",
        "Counterpart area",
        "Profit grouped by",
        "TIME_PERIOD",
    ],
    values="OBS_VALUE",
    columns="Measure",
).reset_index()

cbcr = cbcr_wide[cbcr_variables].copy()

# I keep the observation status of the raw profit measure, independently of any later estimate of corrected profit.
# In particular, the suppressed UK cell of FY2023 keeps its status Q even when its corrected Total receives the
# flagged imputation.
_profit_status_keys = ["REF_AREA", "COUNTERPART_AREA", "Profit grouped by", "TIME_PERIOD"]
_profit_status = cbcr_long.loc[
    cbcr_long["MEASURE"].eq("PROFIT"), _profit_status_keys + ["OBS_STATUS"]
].rename(columns={"OBS_STATUS": "profit_observation_status"})
cbcr = cbcr.merge(_profit_status, on=_profit_status_keys, how="left", validate="one_to_one")

# I keep only the configured analysis window (config.first_year / n_years). The OECD bulk file carries every fiscal
# year the dataflow holds. Without this filter, a new vintage would silently add years without CIT, GDP or wage
# coverage downstream, and they would only be dropped in script 5.
_n_before = len(cbcr)
cbcr = cbcr[cbcr["TIME_PERIOD"].astype(int).isin(analysis_years)].copy()
print(f"CbCR years kept {analysis_years}: {len(cbcr):,} of {_n_before:,} rows "
      f"(years in file: {sorted(cbcr_wide['TIME_PERIOD'].astype(int).unique())})")

# %% MARK: 2.2 Rows that are not jurisdictions and unusable submissions
# I drop four counterpart codes outright. This is the only place where the pipeline excludes partner rows.
#   ANT_F  Netherlands Antilles  — dissolved in 2010, no longer a jurisdiction.
#   BVT    Bouvet Island         — uninhabited dependency, not a real market.
#   STLS   Stateless             — see below.
#   W      World (all partners)  — the reporter's own grand total. Keeping it would count every partner row twice.
#
# Stateless entities (STLS). The OECD data report a separate "Stateless" partner row per reporter for the
# sub-entities that the parent could not assign to any tax jurisdiction. I drop these rows entirely and do not
# redistribute their profit or activity to any country. Stateless profit has no real location, so there is no
# geographic basis for reallocating it. Importantly, the OECD flags stateless income as a known source of double
# counting with the partner rows (the same profit can appear both here and under a named partner), so dropping it
# is part of how I deal with duplicate profits. The misalignment and unitary-taxation calculations then work only
# with profit booked in identifiable jurisdictions.
#
# Stateless amounts inside the raw WXD row (config.REMOVE_STATELESS_FROM_WXD). In 90 of the 102 parent-years with a
# STLS row, the reporter's "World excluding domestic" (WXD) row also contains the stateless amount. For the USA in
# 2016–2020, for example, WXD minus all other foreign rows equals STLS, US$120–204bn of profit a year. Dropping only
# the STLS row would then leave the stateless amount in the WXD residual, which script 2 spreads over countries in
# the gravity sample. Where the WXD profit residual of a block equals its STLS profit (within 2% of WXD plus US$1m),
# I take the STLS money and headcount values off the WXD row as well. Group counts stay as reported.
_STLS_WXD_MEASURES = ["Profit (loss) before income tax", "Adjusted profit (loss) before income tax",
                      "Income tax paid (on cash basis)", "Income tax accrued - current year",
                      "Unrelated party revenues", "Related party revenues", "Total revenues", "Employees",
                      "Tangible assets other than cash and cash equivalents", "Stated capital"]


def remove_stateless_from_wxd(cbcr):
    if not REMOVE_STATELESS_FROM_WXD:
        print("  [stateless] STLS amounts left inside WXD (config.REMOVE_STATELESS_FROM_WXD = False)")
        return cbcr
    P = "Profit (loss) before income tax"
    meas = [c for c in _STLS_WXD_MEASURES if c in cbcr.columns]
    log = []
    for (p, y, g), b in cbcr.groupby(["REF_AREA", "TIME_PERIOD", "Profit grouped by"], sort=False):
        codes = b["COUNTERPART_AREA"]
        if not ((codes == "STLS").any() and (codes == "WXD").any()):
            continue
        s, w = b.loc[codes == "STLS"].iloc[0], b.loc[codes == "WXD"].iloc[0]
        other = pd.to_numeric(b.loc[~codes.isin([p, "W", "WXD", "STLS"]), P], errors="coerce").sum()
        resid = pd.to_numeric(w[P], errors="coerce") - other
        stls = pd.to_numeric(s[P], errors="coerce")
        if pd.isna(resid) or pd.isna(stls) or abs(resid - stls) > 0.02 * abs(w[P]) + 1e6:
            continue
        i = b.index[codes == "WXD"][0]
        for c in meas:
            v = pd.to_numeric(s[c], errors="coerce")
            if pd.notna(v) and pd.notna(cbcr.at[i, c]):
                cbcr.at[i, c] = pd.to_numeric(cbcr.at[i, c], errors="coerce") - v
        log.append({"iso_parent": p, "year": y, "grouping": g, "stls_profit_usd": stls, "wxd_profit_usd": w[P],
                    "residual_before_usd": resid})
    a = pd.DataFrame(log)
    out = output_root / "diagnostics" / "stateless_in_wxd"
    out.mkdir(parents=True, exist_ok=True)
    a.to_csv(out / "stateless_removed_from_wxd.csv", index=False)
    if len(a):
        tot = a[a.grouping == "Total (All sub-groups)"]
        print(f"  [stateless] STLS taken off WXD in {len(a)} blocks ({len(tot)} parent-years); Total profit "
              f"US${tot.stls_profit_usd.sum() / 1e9:,.1f}bn, of which USA US${tot[tot.iso_parent == 'USA'].stls_profit_usd.sum() / 1e9:,.1f}bn")
    return cbcr


cbcr = remove_stateless_from_wxd(cbcr)
_drop_codes = ["ANT_F", "BVT", "W", "STLS"]
cbcr = cbcr[~cbcr["COUNTERPART_AREA"].isin(_drop_codes)].copy()

# Parent-year submissions that I drop entirely (config.DROP_PARENT_YEARS). Indonesia's submissions for 2021–2023
# contain rupiah entered as US$ (stated capital and earnings in almost every cell, profit and loss in the
# holding-company cells), cells of groups with non-Indonesian parents (1.6–2.8m foreign employees, money cells of
# the size of Taiwanese dollar or Thai baht amounts) and broken count fields. I drop them here, before the WXD
# handling and the ETR construction. Indonesia stays a partner. If I treated Indonesia as a bad reporter
# (EXCLUSION_CONDITIONS) instead, script 2 would redistribute its WXD row. Mexico's submission for 2020 gives its
# Venezuelan line in bolivars as if they were US$: a loss of US$314bn on US$879bn of revenue with 868 employees,
# against about US$0.1bn of revenue in the neighbouring years. Its foreign total (WXD) carries the same amounts. As a
# bad reporter, Mexico would have that total redistributed. Without the year, Mexico also leaves the countries whose
# reported profit grows the global total of 2021–2023 in 7a, so the scale factors do not depend on these amounts.
# Peru's submission for 2018 has the fault of Indonesia's: its foreign total is 39 times that of the neighbouring
# years (revenue of 520bn and 730,000 employees, against 23bn and 96,000 in 2017), with lines for Canada and the
# United Kingdom that appear in no other year and 49,500 employees in the United States against 24–606. It looks
# like local filings of foreign-parented groups, and the domestic line is half its usual size.
_dpy = pd.Series([(r, int(y)) in DROP_PARENT_YEARS for r, y in zip(cbcr["REF_AREA"], cbcr["TIME_PERIOD"])],
                 index=cbcr.index)
if _dpy.any():
    print(f"  [drop] parent-year submissions removed: {sorted(DROP_PARENT_YEARS)} ({int(_dpy.sum())} rows)")
cbcr = cbcr[~_dpy].copy()

# I drop an empty line of Chile's 2016 report (partner code F, a continent aggregate).
cbcr = cbcr[
    ~(
        (cbcr["REF_AREA"] == "CHL")
        & (cbcr["TIME_PERIOD"] == 2016)
        & (cbcr["COUNTERPART_AREA"] == "F")
    )
].copy()

# I drop Romania's 2022 record entirely because it is corrupt at source. The raw OECD data report an impossible
# 492m employees for Romanian multinationals in 2022 (including about 105m in the US and about 83m in Israel,
# against about 0.98m in 2021), a payroll inflated about 1,600 times, and collapsed or negative tangible assets and
# revenues. The whole 2022 submission is internally inconsistent, so I treat Romania as a non-reporter for 2022.
# The raw CbCR file shows the same values, so this is not an artefact of the pipeline.
cbcr = cbcr[~((cbcr["REF_AREA"] == "ROU") & (cbcr["TIME_PERIOD"] == 2022))].copy()

# ---- Partner detail of each submission ----
# Script 2 lists the reporters that give little partner detail (tables B1 and B2 of the methodology note). I record
# the detail of every submission in the analysis window here, from the file as published (before any row is dropped):
# the partner rows with a reported profit in the Total panel. A foreign partner is any three-letter jurisdiction code
# other than the reporter and WXD. The detail is "country_by_country" with at least ten foreign partners,
# "few_partners" with one to nine, "continents_only" with continent or residual codes only, and
# "domestic_and_rest_of_world_only" with the domestic row and the WXD total only. A submission counts as dropped when
# none of its rows is left after this section.
_CONTINENT_CODES = {"A", "E", "F", "S", "A_O", "E_O", "F_O", "S_O", "W_O"}
_kept_submissions = set(zip(cbcr["REF_AREA"], cbcr["TIME_PERIOD"].astype(int)))
_total_profit_rows = cbcr_wide[(cbcr_wide["Profit grouped by"] == "Total (All sub-groups)")
                               & cbcr_wide["TIME_PERIOD"].astype(int).isin(analysis_years)
                               & cbcr_wide["Profit (loss) before income tax"].notna()]
_detail = []
for (_rep, _yr), _g in _total_profit_rows.groupby(["REF_AREA", "TIME_PERIOD"]):
    _codes = set(_g["COUNTERPART_AREA"])
    _n_foreign = sum(1 for c in _codes if len(c) == 3 and c.isalpha() and c.isupper() and c not in ("WXD", _rep))
    if _n_foreign >= 10:
        _cls = "country_by_country"
    elif _n_foreign > 0:
        _cls = "few_partners"
    elif _codes & _CONTINENT_CODES:
        _cls = "continents_only"
    elif "WXD" in _codes:
        _cls = "domestic_and_rest_of_world_only"
    else:
        _cls = "domestic_only_or_empty"
    _detail.append(dict(iso_parent=_rep, parent_jurisdiction=_g["Reference area"].iloc[0], year=int(_yr),
                        n_foreign_partners=_n_foreign, partner_detail=_cls,
                        dropped_submission=(_rep, int(_yr)) not in _kept_submissions))
pd.DataFrame(_detail).to_csv(f"{data_intermediate}cbcr_reporter_detail.csv", index=False)
print(f"  [detail] partner detail of {len(_detail)} submissions written to cbcr_reporter_detail.csv")

# %% MARK: 2.3 Column names, analysis window and checks

cbcr.rename(
    columns={
        "REF_AREA": "iso_parent",
        "Reference area": "parent_jurisdiction",
        "COUNTERPART_AREA": "iso_partner",
        "Counterpart area": "partner_jurisdiction",
        "Profit grouped by": "grouping",
        "TIME_PERIOD": "year",
        "Unrelated party revenues": "unrelated_party_revenues",
        "Profit (loss) before income tax": "profit_loss_before_income_tax",
        "Adjusted profit (loss) before income tax": "adjusted_profit_loss_before_income_tax",
        "Income tax paid (on cash basis)": "income_tax_paid_on_cash_basis",
        "Income tax accrued - current year": "income_tax_accrued_current_year",
        "Employees": "n_employees",
        "Tangible assets other than cash and cash equivalents": "tangible_assets_except_cash",
        "Stated capital": "stated_capital",
        "Total revenues": "total_revenues",
        "Related party revenues": "related_party_revenues",
        "Holding or managing intellectual property business activity": "holding_or_managing_ip",
        "Multinational enterprise groups": "n_cbcr",
        "Multinational enterprise sub-groups": "n_cbcr_groups",
        "Entities": "n_entities",
    },
    inplace=True,
)

# I keep only the configured analysis window a second time, on the renamed column, after the filter in 2.1. Years
# outside it would otherwise enter the ±2-year ETR windows and the final files before `n_years` is updated.
_n_outside_window = int((~cbcr["year"].isin(analysis_years)).sum())
if _n_outside_window:
    print(
        f"Dropping {_n_outside_window:,} rows outside the analysis window "
        f"{analysis_years[0]}-{analysis_years[-1]}."
    )
    cbcr = cbcr[cbcr["year"].isin(analysis_years)].copy()

check_duplicates(cbcr, "cbcr")

check_missing_values(
    cbcr,
    [
        "unrelated_party_revenues",
        "profit_loss_before_income_tax",
        "adjusted_profit_loss_before_income_tax",
        "income_tax_paid_on_cash_basis",
        "income_tax_accrued_current_year",
        "n_employees",
        "tangible_assets_except_cash",
        "stated_capital",
        "total_revenues",
        "related_party_revenues",
        "holding_or_managing_ip",
        "n_cbcr",
        "n_cbcr_groups",
        "n_entities",
    ],
)

# %% MARK: 2.4 Rest-of-world (WXD) rows
# Every parent-year-grouping block gets a raw WXD ("world excluding domestic") row. I keep the reported WXD values,
# fill missing ones with the sum of the block's foreign rows and add a WXD row to blocks without one. In the
# gravity sample, script 2 spreads the part of WXD that the listed partner rows do not cover over the markets.

RAW_WXD_FILL_COLS = [
    "unrelated_party_revenues",
    "profit_loss_before_income_tax",
    "adjusted_profit_loss_before_income_tax",
    "income_tax_paid_on_cash_basis",
    "income_tax_accrued_current_year",
    "n_employees",
    "tangible_assets_except_cash",
    "stated_capital",
    "total_revenues",
    "related_party_revenues",
    "holding_or_managing_ip",
    "n_cbcr",
    "n_cbcr_groups",
    "n_entities",
]


def add_or_fill_wxd_rows(cbcr):
    """
    Add or complete a raw WXD row for each parent-year-grouping block.

    I fill missing WXD values with the sum of all non-domestic entries except WXD itself and
    keep the reported values. I do this on the raw variables, before the dividend correction.
    """
    cbcr = cbcr.copy()
    group_cols = ["iso_parent", "year", "grouping"]
    new_rows = []

    wxd_fill_cols = [col for col in RAW_WXD_FILL_COLS if col in cbcr.columns]

    for (iso_parent, year, grouping), g in cbcr.groupby(group_cols, sort=False):
        wxd = g[g["iso_partner"] == "WXD"]
        base = g[(g["iso_partner"] != iso_parent) & (g["iso_partner"] != "WXD")].copy()

        if base.empty:
            continue

        replacement_values = {col: base[col].sum(min_count=1) for col in wxd_fill_cols}

        if not wxd.empty:
            wxd_idx = wxd.index[0]

            for col, val in replacement_values.items():
                if pd.isna(cbcr.at[wxd_idx, col]):
                    cbcr.at[wxd_idx, col] = val

            if "parent_jurisdiction" in cbcr.columns and pd.isna(
                cbcr.at[wxd_idx, "parent_jurisdiction"]
            ):
                parent_vals = g["parent_jurisdiction"].dropna()
                cbcr.at[wxd_idx, "parent_jurisdiction"] = (
                    parent_vals.iloc[0] if not parent_vals.empty else pd.NA
                )

            if "partner_jurisdiction" in cbcr.columns and pd.isna(
                cbcr.at[wxd_idx, "partner_jurisdiction"]
            ):
                cbcr.at[wxd_idx, "partner_jurisdiction"] = "World excluding domestic"

        else:
            new_row = {
                "iso_parent": iso_parent,
                "iso_partner": "WXD",
                "year": year,
                "grouping": grouping,
            }

            if "parent_jurisdiction" in cbcr.columns:
                parent_vals = g["parent_jurisdiction"].dropna()
                new_row["parent_jurisdiction"] = (
                    parent_vals.iloc[0] if not parent_vals.empty else pd.NA
                )

            if "partner_jurisdiction" in cbcr.columns:
                new_row["partner_jurisdiction"] = "World excluding domestic"

            for col, val in replacement_values.items():
                new_row[col] = val

            new_rows.append(new_row)

    if new_rows:
        cbcr = pd.concat([cbcr, pd.DataFrame(new_rows)], ignore_index=True)

    return cbcr


cbcr = add_or_fill_wxd_rows(cbcr)


def move_wxd(cbcr, parent, year, grouping, col, delta):
    """Add `delta` to the WXD row of one parent-year-grouping block. WXD holds the foreign total, so every correction
    of a foreign cell moves it too. Otherwise script 2 would spread the difference over the markets as if it were
    activity in countries the parent does not list."""
    m = (cbcr["iso_parent"].eq(parent) & pd.to_numeric(cbcr["year"], errors="coerce").eq(year)
         & cbcr["grouping"].eq(grouping) & cbcr["iso_partner"].eq("WXD"))
    if m.any() and col in cbcr.columns and pd.notna(delta) and delta != 0:
        cbcr.loc[m, col] = pd.to_numeric(cbcr.loc[m, col], errors="coerce") + delta

# These are the parent and partner jurisdictions of the panel, for the correction tables (4.1) and the country-year
# grid (6.1). The corrections in section 3 change values, not rows.
parent_countries = cbcr["iso_parent"].drop_duplicates()
partner_countries = cbcr["iso_partner"].drop_duplicates()

print(f"Number of unique parent jurisdictions: {len(parent_countries)}")
print(
    f"Number of unique partner jurisdictions, including aggregated regions: {len(partner_countries)}"
)

partner_countries_filtered = partner_countries[~partner_countries.isin(non_countries)]
print(
    f"Number of unique partner jurisdictions, without aggregated regions: {len(partner_countries_filtered)}"
)

# %% MARK: 3. Correct reporting errors
# I correct the cells whose reported figures are implausible (unit and currency errors, a duplicated filing, swapped
# panels, tax signs, one-off valuation losses) before I derive corrected profits (section 4) and tax rates
# (section 5) from them. The loss-swing rule (3.7) runs after the listed cells (3.6) are back at their ordinary level.

# %% MARK: 3.1 Denmark 2023: swapped profit panels
# Denmark FY2023: the profit panels are swapped in the raw OECD file (config.CORRECT_DNK_2023_PANEL_SWAP). The
# "positive profits" panel of every Danish 2023 cell holds losses (35 of 35) and its "negative profits" panel holds
# profits (73 of 73). The sub-group counts are swapped too (DNK to DNK: 14 / 71, against 70 / 12 in 2022). I exchange
# the two labels back. I relabel whole panels, including their rest-of-world rows, so the WXD rows of 2.4 still add
# up.
if CORRECT_DNK_2023_PANEL_SWAP:
    _POSG, _NEGG = "Sub-groups with positive profits", "Sub-groups with negative profits"
    _dk = (cbcr["iso_parent"] == "DNK") & (cbcr["year"].astype(int) == 2023)
    _pos, _neg = _dk & (cbcr["grouping"] == _POSG), _dk & (cbcr["grouping"] == _NEGG)
    cbcr.loc[_pos, "grouping"] = _NEGG
    cbcr.loc[_neg, "grouping"] = _POSG
    print(f"  [artifact] DNK 2023 profit panels swapped back ({int(_pos.sum())} + {int(_neg.sum())} rows)")

# %% MARK: 3.2 Implausible units and inflated cells

def correct_source_data_artifacts(cbcr):
    """Correct clearly corrupt source CbCR cells before the ETR construction.

    I use two time-series fingerprints that need no list and treat every jurisdiction alike.
    I detect them on the comprehensive 'Total (All sub-groups)' grouping and then apply the
    correction to every grouping of the flagged (iso_parent, iso_partner, year) cell.

    (1) Units error. Profit, income tax and tangible assets each jump to more than 3 times the
        cell's own average over its other years, while revenue and employees stay in their
        normal range and the resulting profit margin is above 0.5. The real-activity fields
        (revenue, headcount) are the correctly filed parts, so I reset profit, tax and assets
        to revenue times the cell's average ratio over its other years. An example is
        Indonesia's domestic cell in 2018: a 97% margin, assets of about 4 times GDP and tax of
        about 25 times the normal level, while every other year has a margin of about 10% and
        the foreign Indonesian cells of that year are normal.

    (1b) Employees units error. The headcount jumps to more than 5 times the cell's average
        over its other years while revenue, profit and assets stay flat. I reset it to revenue
        times the cell's average ratio of employees to revenue. This is a historical estimate,
        not a recovered employee count or proof of a units conversion. For corrected foreign
        cells I reduce the WXD total by the same amount, so any residual that existed before
        stays as it was and the disaggregation does not add the employees back.

    Cells in which every field is inflated (hyperinflation or a bad currency conversion) leave no
    trustworthy field to rescale against, so I drop such submissions instead (DROP_PARENT_YEARS).
    """
    PROFIT = "profit_loss_before_income_tax"
    REV = "total_revenues"
    EMP = "n_employees"
    RESCALE_COLS = [
        "profit_loss_before_income_tax", "adjusted_profit_loss_before_income_tax",
        "income_tax_paid_on_cash_basis", "income_tax_accrued_current_year",
        "tangible_assets_except_cash",
    ]
    MONEY_COLS = RESCALE_COLS + [
        "total_revenues", "unrelated_party_revenues", "related_party_revenues",
        "stated_capital",
    ]
    num = {c: pd.to_numeric(cbcr[c], errors="coerce") for c in
           set(MONEY_COLS + [EMP]) if c in cbcr.columns}
    employees_before = num[EMP].copy()
    tot_mask = cbcr["grouping"] == "Total (All sub-groups)"
    tot = cbcr[tot_mask].copy()
    for c in num:
        tot[c] = num[c][tot_mask]

    units_cells = []
    emp_cells = []
    for (p, pt), g in tot.groupby(["iso_parent", "iso_partner"]):
        if g["year"].nunique() < 4:
            continue
        g = g.sort_values("year")
        for _, r in g.iterrows():
            o = g[g["year"] != r["year"]]

            def spike(col, k=3.0):
                m = o[col].mean()
                return bool(m > 0 and r[col] > k * m)

            def flat(col, k=2.0):
                m = o[col].mean()
                return bool(m <= 0 or abs(r[col]) <= k * abs(m))

            rev = r[REV]
            margin = (r[PROFIT] / rev) if (pd.notna(rev) and rev > 0) else np.nan
            # Units error: the income and balance-sheet fields spike while real activity stays flat.
            if (pd.notna(r[PROFIT]) and r[PROFIT] / 1e9 >= 2
                    and spike(PROFIT) and spike("income_tax_paid_on_cash_basis")
                    and spike("tangible_assets_except_cash")
                    and flat(REV) and flat(EMP)
                    and pd.notna(margin) and margin > 0.5):
                units_cells.append((p, pt, int(r["year"])))
            # Employees units error: the headcount spikes while revenue, profit and assets all stay in their normal
            # range. Examples are Czechia's rest-of-world row in 2023 (10.3m against about 0.35m in every other year)
            # and Saudi Arabia's domestic cell in 2022 (5.4m against about 0.45m). Employees drive the payroll factor
            # and the activity conservation in script 2, so I reset the spike to revenue times the cell's own average
            # ratio of employees to revenue over its other years.
            if (pd.notna(r[EMP]) and r[EMP] >= 50_000
                    and spike(EMP, k=5.0)
                    and flat(REV) and flat(PROFIT) and flat("tangible_assets_except_cash")):
                emp_cells.append((p, pt, int(r["year"])))

    # I remove duplicates (a cell can be visited twice when the Total grouping carries a raw and a filled WXD row)
    # and honour the config switch.
    emp_cells = list(dict.fromkeys(emp_cells))
    if not CORRECT_EMPLOYEE_UNITS_ERRORS:
        if emp_cells:
            print(f"  [artifact] EMPLOYEES units errors detected but NOT corrected "
                  f"(config.CORRECT_EMPLOYEE_UNITS_ERRORS = False): {emp_cells}")
        emp_cells = []

    def cell_grouping_rows(p, pt):
        return (cbcr["iso_parent"] == p) & (cbcr["iso_partner"] == pt)

    for (p, pt, y) in units_cells:
        for grp in cbcr.loc[cell_grouping_rows(p, pt), "grouping"].unique():
            m = cell_grouping_rows(p, pt) & (cbcr["grouping"] == grp)
            sub = cbcr[m]
            yr = pd.to_numeric(sub["year"], errors="coerce")
            if y not in yr.values:
                continue
            others = sub[yr != y]
            rev_o = pd.to_numeric(others[REV], errors="coerce")
            rev_y = pd.to_numeric(sub.loc[yr == y, REV], errors="coerce").iloc[0]
            if not (pd.notna(rev_y) and rev_y != 0):
                continue
            # I only correct a grouping whose own value is anomalous (an impossible margin above 0.5). The normal
            # 'negative profits' grouping, for example, stays untouched, while I fix 'Total' and 'positive profits'
            # (both corrupt).
            profit_y = pd.to_numeric(sub.loc[yr == y, PROFIT], errors="coerce").iloc[0]
            if not (pd.notna(profit_y) and profit_y / rev_y > 0.5):
                continue
            for col in RESCALE_COLS:
                if col not in cbcr.columns:
                    continue
                ratio = (pd.to_numeric(others[col], errors="coerce") / rev_o)
                ratio = ratio.replace([np.inf, -np.inf], np.nan).mean()
                if pd.notna(ratio):
                    cbcr.loc[m & (pd.to_numeric(cbcr["year"], errors="coerce") == y), col] = rev_y * ratio
        print(f"  [artifact] UNITS-ERROR rescaled {p}->{pt} {y} "
              f"(profit/tax/assets reset to revenue x avg ratio, all groupings)")

    for (p, pt, y) in emp_cells:
        n_fixed = 0
        for grp in cbcr.loc[cell_grouping_rows(p, pt), "grouping"].unique():
            m = cell_grouping_rows(p, pt) & (cbcr["grouping"] == grp)
            sub = cbcr[m]
            yr = pd.to_numeric(sub["year"], errors="coerce")
            if y not in yr.values:
                continue
            others = sub[yr != y]
            rev_o = pd.to_numeric(others[REV], errors="coerce")
            emp_o = pd.to_numeric(others[EMP], errors="coerce")
            rev_y = pd.to_numeric(sub.loc[yr == y, REV], errors="coerce").iloc[0]
            emp_y = pd.to_numeric(sub.loc[yr == y, EMP], errors="coerce").iloc[0]
            if not (pd.notna(rev_y) and rev_y > 0 and pd.notna(emp_y)):
                continue
            ratio = (emp_o / rev_o).replace([np.inf, -np.inf], np.nan).mean()
            # I only correct a grouping whose own headcount is anomalous (more than 5 times the level implied by its
            # other years), so normal groupings stay untouched.
            if not (pd.notna(ratio) and ratio > 0 and emp_y > 5.0 * rev_y * ratio):
                continue
            cbcr.loc[m & (pd.to_numeric(cbcr["year"], errors="coerce") == y), EMP] = rev_y * ratio
            n_fixed += 1
        if n_fixed:
            print(f"  [artifact] EMPLOYEES units error rescaled {p}->{pt} {y} "
                  f"(headcount reset to revenue x avg employees/revenue ratio, {n_fixed} grouping(s))")
        else:
            print(f"  [artifact] EMPLOYEES spike flagged but NOT rescaled {p}->{pt} {y} "
                  f"(below 5x the revenue-implied headcount in every grouping)")

    # WXD contains the foreign partner counts. Leaving it unchanged after a partner correction would create an
    # artificial residual of missing countries, which script 2 would distribute back into the panel. I therefore
    # carry each grouping's actual deduction into its foreign total. Domestic corrections do not affect WXD. A WXD
    # row that was corrected on its own already has its own estimated level.
    employee_deduction = employees_before - pd.to_numeric(cbcr[EMP], errors="coerce")
    foreign_changed = (
        cbcr["iso_partner"].ne(cbcr["iso_parent"])
        & cbcr["iso_partner"].ne("WXD")
        & employee_deduction.notna()
        & employee_deduction.abs().gt(1e-9)
    )
    deductions = (cbcr.loc[foreign_changed, ["iso_parent", "year", "grouping"]]
                  .assign(employee_deduction=employee_deduction.loc[foreign_changed])
                  .groupby(["iso_parent", "year", "grouping"])["employee_deduction"].sum())
    n_wxd = 0
    for (p, y, grp), amount in deductions.items():
        m = (cbcr["iso_parent"].eq(p) & cbcr["year"].eq(y)
             & cbcr["grouping"].eq(grp) & cbcr["iso_partner"].eq("WXD"))
        old = employees_before.loc[m]
        current = pd.to_numeric(cbcr.loc[m, EMP], errors="coerce")
        eligible = current.notna() & old.notna() & np.isclose(current, old)
        if not eligible.any():
            continue
        adjusted = current.loc[eligible] - amount
        if (adjusted < 0).any():
            print(f"  [artifact] WXD employee deduction exceeds the total for "
                  f"{p} {y} {grp}; aggregate left unchanged")
            continue
        cbcr.loc[adjusted.index, EMP] = adjusted
        n_wxd += len(adjusted)
    if n_wxd:
        print(f"  [artifact] EMPLOYEES partner deductions also applied to "
              f"{n_wxd} WXD grouping row(s), preserving the prior residual")

    if not units_cells and not emp_cells:
        print("  [artifact] no corrupt source cells detected")
    return cbcr


print("Source-data artifact correction:")
cbcr = correct_source_data_artifacts(cbcr)

# %% MARK: 3.3 US groups' employees in 2023

def correct_us_employees_2023(cbcr):
    """Reset the FY2023 employee jumps of US-parent cells to the trend of the BEA survey.

    In the FY2023 file, US groups report 22.2m foreign employees against 16.1m in
    2022 (Mexico 1.9 times the 2022 level, Brazil 3.0, Argentina 4.4, Korea 2.9,
    Belgium 3.2 and so on). Revenue, assets and the counts of reporting groups do
    not show comparable jumps, and the employee jumps already appear in the primary
    tables of the IRS (SOI Table 1A, tax year 2023). Employment in US groups'
    foreign affiliates in the survey of the US Bureau of Economic Analysis (BEA)
    rises by only 0.2%. The BEA survey and the CbCR data cover different
    populations and employee concepts. The CbCR data count full-time equivalents
    and can include operating contractors, while the BEA counts payroll staff in
    majority-owned affiliates. A counting change or a filing error is a hypothesis,
    not an established cause. The rule below transfers the observed BEA growth to
    the CbCR levels as an estimate that keeps the years comparable. It does not
    recover independently verified headcounts.

    The rule, detected on the 'Total (All sub-groups)' grouping: I flag a US-parent
    2023 cell when employees_2023 / employees_2022 > g_BEA + 0.25 and its
    unrelated-party revenue grew by less than 25%. g_BEA is the partner's BEA
    employment growth from 2022 to 2023 (1.0 where the BEA has no figure, for
    example for continent aggregates and small countries). I reset the flagged
    headcount to employees_2022 x g_BEA and scale every grouping of the cell by the
    same factor. Payroll follows, since it is built later as employees x wage.
    """
    if not CORRECT_US_EMPLOYEES_2023 or last_year < 2023:
        return cbcr
    MARGIN, REV_FLAT = 0.25, 1.25
    EMP, REV = "n_employees", "unrelated_party_revenues"

    # ---- BEA growth factors by ISO3 ----
    # I look names up exactly. The file also has region rows such as "Other" that a fuzzy match would assign wrongly.
    bea = pd.read_csv(bea_mofa_employment_data, header=None, skiprows=5,
                      names=["country", "e22", "e23"], dtype=str)
    bea["country"] = bea["country"].fillna("").str.strip()
    bea_names = {
        "South Korea": "KOR", "Russia": "RUS", "Turkey": "TUR", "Vietnam": "VNM",
        "Taiwan": "TWN", "Hong Kong": "HKG", "Kosovo": "XKV", "Curacao": "CUW",
        "Sint Maarten": "SXM", "St. Kitts and Nevis": "KNA", "St. Lucia": "LCA",
        "St. Vincent and the Grenadines": "VCT", "Cape Verde": "CPV",
        "Democratic Republic of the Congo": "COD", "Cote D'Ivoire": "CIV",
        "Brunei": "BRN", "Burma": "MMR", "Macau": "MAC", "Micronesia": "FSM",
    }

    def bea_iso3(name):
        if name in bea_names:
            return bea_names[name]
        try:
            return pycountry.countries.lookup(name).alpha_3
        except LookupError:
            return None

    bea["iso"] = bea["country"].map(bea_iso3)
    for c in ("e22", "e23"):
        bea[c] = pd.to_numeric(bea[c], errors="coerce")
    g_bea = (bea.dropna(subset=["iso", "e22", "e23"]).query("e22 > 0")
             .drop_duplicates("iso").set_index("iso").eval("e23 / e22").to_dict())

    # ---- Flag on the Total grouping ----
    yr = pd.to_numeric(cbcr["year"], errors="coerce")
    us_tot = ((cbcr["iso_parent"] == "USA") & (cbcr["iso_partner"] != "USA")
              & (cbcr["grouping"] == "Total (All sub-groups)"))

    def by_partner(y):
        s = cbcr.loc[us_tot & (yr == y), ["iso_partner", EMP, REV]].copy()
        for c in (EMP, REV):
            s[c] = pd.to_numeric(s[c], errors="coerce")
        return s.drop_duplicates("iso_partner").set_index("iso_partner")

    k22, k23 = by_partner(2022), by_partner(2023)
    log = []
    for pt, r in k23.iterrows():
        # WXD is the total of all foreign rows, not a market. I adjust it below.
        if pt not in k22.index or pt == "WXD":
            continue
        e22, e23 = k22.at[pt, EMP], r[EMP]
        r22, r23 = k22.at[pt, REV], r[REV]
        if not (pd.notna(e22) and pd.notna(e23) and e22 > 0 and e23 > 0):
            continue
        g = g_bea.get(pt, 1.0)
        rev_ratio = r23 / r22 if (pd.notna(r22) and r22 > 0) else np.nan
        if e23 / e22 > g + MARGIN and not (rev_ratio >= REV_FLAT):
            log.append(dict(iso_partner=pt, employees_2022=e22, employees_2023_reported=e23,
                            bea_factor=g, bea_available=pt in g_bea, revenue_ratio=rev_ratio,
                            employees_2023_corrected=e22 * g))

    # ---- Apply ----
    # I scale every grouping of a flagged cell by the factor of its Total and take the same headcount off the WXD
    # total, so that script 2 does not spread the removed employees as a WXD residual.
    us23 = (cbcr["iso_parent"] == "USA") & (yr == 2023)
    removed = pd.Series(0.0, index=cbcr.loc[us23, "grouping"].unique())
    for x in log:
        factor = x["employees_2023_corrected"] / x["employees_2023_reported"]
        m = us23 & (cbcr["iso_partner"] == x["iso_partner"])
        old = pd.to_numeric(cbcr.loc[m, EMP], errors="coerce")
        cbcr.loc[m, EMP] = old * factor
        removed = removed.add((old * (1 - factor)).groupby(cbcr.loc[m, "grouping"]).sum(),
                              fill_value=0)
    for grp, amount in removed.items():
        m = us23 & (cbcr["iso_partner"] == "WXD") & (cbcr["grouping"] == grp)
        cbcr.loc[m, EMP] = pd.to_numeric(cbcr.loc[m, EMP], errors="coerce") - amount

    if log:
        log = pd.DataFrame(log).sort_values("employees_2023_reported", ascending=False)
        rep = k23.loc[k23.index.difference(list(log.iso_partner) + ["WXD"]), EMP].sum()
        print(f"  [artifact] US 2023 EMPLOYEES reset to the BEA trend in {len(log)} cells: "
              f"US groups' foreign headcount {(rep + log.employees_2023_reported.sum()) / 1e6:.1f}m "
              f"-> {(rep + log.employees_2023_corrected.sum()) / 1e6:.1f}m "
              f"(2022: {k22.drop(index='WXD', errors='ignore')[EMP].sum() / 1e6:.1f}m)")
        print(log.head(12).round(2).to_string(index=False))
    return cbcr


cbcr = correct_us_employees_2023(cbcr)

# %% MARK: 3.4 Saudi Arabia 2021 and 2023

def correct_sau_2021_duplicate(cbcr):
    """Remove the second copy of Saudi Aramco from the FY2021 Saudi cells.

    In FY2021 the Saudi domestic cell holds Aramco twice. Its profit of 451.9bn is
    about 2 × Aramco's pre-tax income (205.2) + 41.5. Its cash tax of 159.0 is about
    2 × Aramco's settled Saudi income tax and zakat (77.9) + 3.2. Its accrued tax of
    185.1 is about 2 × 90.8 + 3.5, and its unrelated revenue of 684.7 is about
    2 × Aramco's revenue in the Kingdom (279.3) + 126. The remainders match 2020 and
    2022 (the other Saudi groups). Employees and entity counts are not doubled. The
    foreign cells of Saudi groups jump in the same year (revenue 455bn against 102 and
    310, profit 41 against −3 and 10). The Aramco figures come from
    config.aramco_financials_data.

    Domestic cell (Total and positive-profit panels): I subtract one Aramco copy using
    Aramco's own figures for profit, cash tax, accrued tax and unrelated revenue. I
    halve related-party revenue, tangible assets and stated capital, for which I
    collected no Aramco figure. Total revenue follows.
    Foreign cells of Saudi parents (all panels): I halve them, employees included.
    """
    if not (first_year <= 2021 <= last_year):
        return cbcr
    a = pd.read_csv(aramco_financials_data)
    a = a[a["year"] == 2021].set_index("item")["value_sar_m"] * 1e6 / 3.75   # USD
    kingdom_tax_settled = sum(a[k] for k in ("tax_paid_cash_company", "tax_paid_cash_subsidiaries",
                                             "tax_settled_offset_government", "tax_settled_other"))
    kingdom_tax_accrued = a["current_tax_kingdom"] + a["zakat_expense"]          # Aramco's note 8 (expense)
    in_kingdom_revenue = a["revenue_in_kingdom"] + a["other_income_related_to_sales"]
    aramco = {"profit_loss_before_income_tax": a["pbt"],
              "income_tax_paid_on_cash_basis": kingdom_tax_settled,
              "income_tax_accrued_current_year": kingdom_tax_accrued,
              "unrelated_party_revenues": in_kingdom_revenue}
    halve = ["related_party_revenues", "tangible_assets_except_cash", "stated_capital"]

    yr = pd.to_numeric(cbcr["year"], errors="coerce")
    sau = (cbcr["iso_parent"] == "SAU") & (yr == 2021)
    dom = sau & (cbcr["iso_partner"] == "SAU") & cbcr["grouping"].isin(
        ["Total (All sub-groups)", "Sub-groups with positive profits"])
    before = pd.to_numeric(cbcr.loc[dom & (cbcr["grouping"] == "Total (All sub-groups)"),
                                    "profit_loss_before_income_tax"], errors="coerce").sum()
    for col, v in aramco.items():
        old = pd.to_numeric(cbcr.loc[dom, col], errors="coerce")
        cbcr.loc[dom, col] = old - v
        if col == "unrelated_party_revenues":
            cbcr.loc[dom, "total_revenues"] = pd.to_numeric(cbcr.loc[dom, "total_revenues"], errors="coerce") - v
    for col in halve:
        old = pd.to_numeric(cbcr.loc[dom, col], errors="coerce")
        cbcr.loc[dom, col] = old * 0.5
        if col == "related_party_revenues":
            cbcr.loc[dom, "total_revenues"] = pd.to_numeric(cbcr.loc[dom, "total_revenues"], errors="coerce") - old * 0.5

    foreign = sau & (cbcr["iso_partner"] != "SAU")
    fcols = [c for c in ["profit_loss_before_income_tax", "adjusted_profit_loss_before_income_tax",
                         "income_tax_paid_on_cash_basis", "income_tax_accrued_current_year",
                         "unrelated_party_revenues", "related_party_revenues", "total_revenues",
                         "tangible_assets_except_cash", "stated_capital", "n_employees"]
             if c in cbcr.columns]
    for col in fcols:
        cbcr.loc[foreign, col] = pd.to_numeric(cbcr.loc[foreign, col], errors="coerce") * 0.5

    after = pd.to_numeric(cbcr.loc[dom & (cbcr["grouping"] == "Total (All sub-groups)"),
                                   "profit_loss_before_income_tax"], errors="coerce").sum()
    print(f"  [artifact] SAU 2021 duplicate Aramco filing removed: domestic profit "
          f"{before / 1e9:,.1f}bn -> {after / 1e9:,.1f}bn; {int(foreign.sum())} foreign rows halved")
    return cbcr


cbcr = correct_sau_2021_duplicate(cbcr)


def correct_sau_2023_unexplained_profit(cbcr):
    """Remove the FY2023 Saudi domestic profit that no company explains.

    In FY2023 the Saudi domestic cell reports 359.8bn of profit, but only Aramco's
    pre-tax income (236.8bn) and that of the other Saudi groups likely to file a CbCR
    (32.9bn, the generous count including borderline filers) can be documented. About
    90bn is left with almost no tax (the cell's tax matches Aramco and the other
    groups within 6.5bn), and the profitable sub-groups report 406bn of profit on
    153bn of revenue. I treat the excess as a data artefact, most likely intra-group
    dividends or equity income counted twice. I take the excess over Aramco and the
    other groups off profit in the Total and positive-profit panels. Tax, revenue and
    employees stay.
    Sources: config.aramco_financials_data, config.sau_other_groups_sums_data.
    """
    if not (first_year <= 2023 <= last_year):
        return cbcr
    a = pd.read_csv(aramco_financials_data)
    aramco_pbt = float(a.loc[(a["year"] == 2023) & (a["item"] == "pbt"), "value_sar_m"].iloc[0]) * 1e6 / 3.75
    o = pd.read_csv(sau_other_groups_sums_data)
    others = float(o.loc[(o["year"] == 2023) & o["scenario"].str.startswith("A_core+borderline"),
                         "pretax_usd_bn"].iloc[0]) * 1e9
    yr = pd.to_numeric(cbcr["year"], errors="coerce")
    dom = (cbcr["iso_parent"] == "SAU") & (cbcr["iso_partner"] == "SAU") & (yr == 2023)
    tot = dom & (cbcr["grouping"] == "Total (All sub-groups)")
    p_tot = pd.to_numeric(cbcr.loc[tot, "profit_loss_before_income_tax"], errors="coerce").sum()
    excess = p_tot - aramco_pbt - others
    if not excess > 0:
        return cbcr
    m = dom & cbcr["grouping"].isin(["Total (All sub-groups)", "Sub-groups with positive profits"])
    cbcr.loc[m, "profit_loss_before_income_tax"] = (
        pd.to_numeric(cbcr.loc[m, "profit_loss_before_income_tax"], errors="coerce") - excess)
    print(f"  [artifact] SAU 2023 domestic profit not explained by Aramco ({aramco_pbt/1e9:,.1f}bn) "
          f"+ other groups ({others/1e9:,.1f}bn) removed: {excess/1e9:,.1f}bn "
          f"(cell {p_tot/1e9:,.1f} -> {(p_tot-excess)/1e9:,.1f}bn)")
    return cbcr


cbcr = correct_sau_2023_unexplained_profit(cbcr)

# %% MARK: 3.5 Tax entered with the wrong sign (Cepsa, Maersk)

def correct_esp_are_cepsa_tax_sign(cbcr):
    """Restore the sign of Cepsa's UAE income tax in the cells of Spanish groups in the UAE, FY2019–2023.

    Cepsa prints every tax payment in brackets in its public country-by-country
    table (Spain, Algeria, Brazil and the others are all negative, and the one
    positive entry, Thailand, is a refund). The Spanish CbCR data carry that
    convention. The cash tax of the ESP → ARE cell equals Cepsa's published UAE
    line, negative, to within 0.1% each year after currency conversion (the cell
    in US$ m against Cepsa's line in € m: 2019 −169.3 against −151.0, 2020 −104.7
    against −91.5, 2021 −283.1 against −239.2, 2022 −990.4 against −939.2, 2023
    −272.8 against 252 € m of "taxes paid" in its tax report). Cepsa's tax report
    and its filings of payments to governments show these amounts as payments to
    the UAE, not refunds.

    I flip the cash and accrued tax of the sub-group row that carries Cepsa's line
    (|tax| >= US$50m, in the positive-profit panel, or in the negative one in 2020,
    when Cepsa made a loss), and I move the Total panel and the WXD rows by the same amount. Small
    negatives of other Spanish groups stay as published. Cepsa operates in other
    Spanish partner cells too, mixed with other groups. I correct its Algerian tax
    separately (correct_dza_cepsa_maersk_tax_sign).
    """
    yr = pd.to_numeric(cbcr["year"], errors="coerce")
    cell = (cbcr["iso_parent"] == "ESP") & (cbcr["iso_partner"] == "ARE") & yr.between(2019, 2023)
    sub = cell & cbcr["grouping"].isin(["Sub-groups with positive profits", "Sub-groups with negative profits"])
    tot = cell & (cbcr["grouping"] == "Total (All sub-groups)")
    for col in ("income_tax_paid_on_cash_basis", "income_tax_accrued_current_year"):
        v = pd.to_numeric(cbcr[col], errors="coerce")
        flip = sub & (v <= -50e6)
        if not flip.any():
            continue
        delta = (-2 * v[flip]).groupby(yr[flip]).sum()          # amount added per year
        for i in flip[flip].index:
            move_wxd(cbcr, "ESP", int(yr[i]), cbcr.at[i, "grouping"], col, -2 * v[i])
        for y_, d_ in delta.items():
            move_wxd(cbcr, "ESP", int(y_), "Total (All sub-groups)", col, d_)
        cbcr.loc[flip, col] = -v[flip]
        cbcr.loc[tot, col] = v[tot] + yr[tot].map(delta).fillna(0)
        print(f"  [artifact] ESP→ARE {col}: Cepsa sign restored in {int(flip.sum())} sub-group rows, "
              f"total +{delta.sum() / 1e9:,.2f}bn over {sorted(delta.index.astype(int))}")
    return cbcr


cbcr = correct_esp_are_cepsa_tax_sign(cbcr)


# Cepsa's Algerian income tax as printed in its public CbCR table, in EUR m. A negative sign means a payment ("Negative
# sign indicates tax payment", ESP_Cepsa_CbCR_2023_en.xlsx, sheet 'CbC - Pag 3'), and the FY2019–2022 tables use the
# same convention. I convert the amounts at the World Bank's period-average EUR/USD rate
# (wb_fx_official_rate_2026-02.csv, euro-area row EMU). Cepsa's tax reports show the same Algerian amounts as payments
# (for example 244 €m in 2022, ARE_Cepsa_IGI_2022.pdf, PDF page 121).
_CEPSA_DZA_TAX_USD_M = {   # year: (cash, accrued) — magnitude of the printed negative, USD m
    2019: (146.961, 191.822), 2020: (175.483, 88.037), 2021: (77.485, 165.679),
    2022: (257.138, 176.897), 2023: (151.325, 99.486),
}


def correct_dza_cepsa_maersk_tax_sign(cbcr):
    """Restore the sign of two groups' Algerian income tax in the cells of Spanish and
    Danish groups in Algeria.

    ESP → DZA, FY2019–2023: the cell's tax nets Cepsa's payment, printed as a negative,
    against Repsol's positive tax (Cepsa and Repsol explain 85–95% of the positive-profit
    panel). I therefore do not flip the whole row. Instead, I add 2 × Cepsa's documented
    amount to the sub-group that carries Cepsa (the positive-profit panel, or the negative
    panel in 2020, when Cepsa made a loss) and to the Total panel.
    DNK → DZA, FY2016–2018: the cell is Maersk Oil's Algerian business (sold to Total in
    March 2018). A.P. Møller-Mærsk reports "Tax paid – Algeria" of +309 USD m for 2016
    (DNK_APMM_P2G_2016.pdf) against −308.9 in the cell, so I flip the negative cash and
    accrued tax of those years (sub-group and Total panels).
    """
    yr = pd.to_numeric(cbcr["year"], errors="coerce")
    esp = (cbcr["iso_parent"] == "ESP") & (cbcr["iso_partner"] == "DZA")
    tot = cbcr["grouping"] == "Total (All sub-groups)"
    for i_col, col in enumerate(("income_tax_paid_on_cash_basis", "income_tax_accrued_current_year")):
        added = 0.0
        for y, vals in _CEPSA_DZA_TAX_USD_M.items():
            panel = "Sub-groups with negative profits" if y == 2020 else "Sub-groups with positive profits"
            d = 2 * vals[i_col] * 1e6
            for g, m in ((panel, esp & (yr == y) & (cbcr["grouping"] == panel)),
                         ("Total (All sub-groups)", esp & (yr == y) & tot)):
                if m.sum() == 1:
                    cbcr.loc[m, col] = pd.to_numeric(cbcr.loc[m, col], errors="coerce") + d
                    move_wxd(cbcr, "ESP", y, g, col, d)
            added += d
        print(f"  [artifact] ESP→DZA {col}: Cepsa sign restored, +{added / 1e9:,.2f}bn over 2019–2023")
        dnk = (cbcr["iso_parent"] == "DNK") & (cbcr["iso_partner"] == "DZA") & yr.between(2016, 2018)
        v = pd.to_numeric(cbcr[col], errors="coerce")
        flip = dnk & (v < 0)
        for i in flip[flip].index:
            move_wxd(cbcr, "DNK", int(yr[i]), cbcr.at[i, "grouping"], col, -2 * v[i])
        cbcr.loc[flip, col] = -v[flip]
        print(f"  [artifact] DNK→DZA {col}: Maersk sign restored in {int(flip.sum())} rows (2016–2018)")
    return cbcr


cbcr = correct_dza_cepsa_maersk_tax_sign(cbcr)

# %% MARK: 3.6 Listed cells

def correct_listed_cell_artifacts(cbcr):
    """Correct individual cells that are reporting errors, in the order of the code.
    Switch: config.CORRECT_LISTED_CELL_ARTIFACTS.

    BEL → GBR (AB InBev's UK holding chain: intra-group dividends booked as profit before the
      2019 OECD guidance, impairments in 2023, profit swings larger than the cell's revenue):
      I set total profit to the cell's ordinary level and take the difference off the panel
      that carries the holding block. That is the positive panel in 2017–2019 (level +1.40bn,
      the 2020–22 mean) and the negative panel in 2023 (level +1.47bn, from the published
      positive-profit bands). Tax, revenue, employees and assets stay unchanged.
    BEL → NLD 2016 / 2018 (AB InBev Nederland Holding's reorganisation gain of EUR 43.5bn in
      2018, intra-group income as related-party revenue in 2016): level +2.52bn.
    JPN → JEY 2020–23 (SoftBank Vision Funds: fair-value swings, no staff): set to the cell's
      ordinary level.
    JPN → CYM 2021–23 (SoftBank's Cayman vehicles): loss panel set to its 2017–19 level.
    JPN → USA 2022–2023 (SoftBank's US fund vehicles: loss panel −27.3 / −101.6bn against −5.8 to
      −13.1bn in the years before): loss panel set to its 2017–19 mean (−9.682bn), as for
      JPN → CYM.
    JPN → SGP 2022–2023 and JPN → GBR 2022 (fund losses on negative revenue in OECD Table VI):
      loss panel set to its 2017–19 mean (−0.791 / −4.748bn), as for JPN → USA.
    ZAF → NLD 2023 (−34.7bn absorbed against stated capital): set to the cell's ordinary level.
    Cash-tax entry errors, set to the accrued tax: CHN → CYP 2023 (US$3.06bn on US$103m of
      profit), HKG → SGP, JPN → CAN and JPN → VNM 2022 (positive panels), ZAF → ZAF 2018
      (loss panel), and in the positive panels LUX → COL 2017, JPN → COL 2020, JPN → SVN, KHM
      and HRV 2019, ARE → TKM 2021, LUX → PHL 2017, SAU → ESP 2019 and JEY → CAN 2023. In each
      the cash tax is many times the accrued tax in one year only, and in the cell's other years
      the two are close, so I correct that year alone.
    TUR 2021 (cash tax of the whole submission many times the accrued tax): every 2021 row set
      to its accrued tax. The domestic line uses the accrued tax in every year, because its 2021
      excess partly comes back as cash tax below the accrued tax in 2022 and 2023.
    THA → CHN 2023 (CP Group, yuan entered as US$: US$3.1m revenue per employee, and the figures
      match CP's own CNY numbers): I divide the negative panel's monetary fields by 7.084 (CNY
      per US$, 2023) and move the Total by the same difference. Employees and counts stay
      unchanged.
    CZE → CZE 2023 employees (272k, 2.8 times the cell's level while revenue fell, and the same
      submission's rest-of-world headcount is a confirmed units error): reset to revenue times
      the cell's average ratio of employees to revenue in its other years (the level of
      rule 1b).
    AZE → JPN 2022 tangible assets (40.93bn in a cell with 11 employees): yen read as US$,
      divided by the 2022 rate of JPY per US$ (131.50).
    ARG → ARG 2021–2022 tangible assets (ratios of assets to revenue of 17 and 47 in the
      positive-profit panel): I interpolate that panel between 2020 and 2023 and set the Total
      to the sum of the panels.
    Entry, unit and currency errors, each one year that lies orders of magnitude away from the
      cell's other years:
      BMU → CHN 2016 (yuan entered as US$): the monetary fields divided by 6.644.
      BMU → PER 2016 (every monetary field 10 to 90 times its level, employees flat): the
      monetary fields set to the median of the cell's other years.
      Profit set to the median of the cell's other years: BMU → VGB and BMU → HKG 2016, ZAF → GBR,
      ZAF → ARE and ZAF → HKG 2018, CHL → PAN 2021, BRA → VEN 2016. MEX → VEN 2017 (bolivars):
      every monetary field.
      MYS → THA 2020 (every field of the loss panel 35 to 1,000 times its level): that panel set
      to the median of its other years.
      Employees: the panel set to the median of its other years for BMU → IND 2016, CYM → SGP 2023
      and six cells of Luxembourg's 2021 submission (GBR, USA, BEL, NLD, CHE, ESP); the Total set
      to the sum of the panels for CHN → FIN 2018 and LUX → DEU 2021.
    Corrections of foreign cells also move the parent's WXD foreign total by the same amount, so
    that the gravity sample does not impute again what I removed.
    """
    if not CORRECT_LISTED_CELL_ARTIFACTS:
        print("  [artifact] listed cell corrections OFF (config.CORRECT_LISTED_CELL_ARTIFACTS)")
        return cbcr
    yr = pd.to_numeric(cbcr["year"], errors="coerce")
    TOT, POS, NEG = ("Total (All sub-groups)", "Sub-groups with positive profits",
                     "Sub-groups with negative profits")
    PROFIT_COLS = ["profit_loss_before_income_tax", "adjusted_profit_loss_before_income_tax"]
    cell = lambda p, pt, y: (cbcr["iso_parent"] == p) & (cbcr["iso_partner"] == pt) & (yr == y)
    num = lambda m, c: pd.to_numeric(cbcr.loc[m, c], errors="coerce")

    def wxd_shift(p, y, grouping, col, delta):
        """Move the parent's WXD foreign total by the same amount as a corrected foreign cell, so
        that fix_corrected_wxd and script 2 do not impute the removed amount again in the gravity
        sample."""
        m = cell(p, "WXD", y) & (cbcr["grouping"] == grouping)
        if m.any() and pd.notna(delta) and col in cbcr.columns:
            cbcr.loc[m, col] = num(m, col) - delta

    # BEL → GBR: AB InBev's UK holding chain
    for pt, y, level, panel in [("GBR", 2017, 1.40e9, POS), ("GBR", 2018, 1.40e9, POS), ("GBR", 2019, 1.40e9, POS),
                                ("GBR", 2023, 1.47e9, NEG),
                                # BEL → NLD: AB InBev Nederland Holding's reorganisation gain of EUR 43.5bn in
                                # 2018 and intra-group income booked as related-party revenue in 2016. The level
                                # is the cell's 2020–22 mean (+2.52bn), taken off the positive panel.
                                ("NLD", 2016, 2.52e9, POS), ("NLD", 2018, 2.52e9, POS)]:
        c = cell("BEL", pt, y)
        if not (c & (cbcr["grouping"] == TOT)).any():
            continue
        for col in [k for k in PROFIT_COLS if k in cbcr.columns]:
            t = num(c & (cbcr["grouping"] == TOT), col).iloc[0]
            if pd.isna(t):
                continue
            d = t - level
            for g in (TOT, panel):
                m = c & (cbcr["grouping"] == g)
                cbcr.loc[m, col] = num(m, col) - d
                wxd_shift("BEL", y, g, col, d)
        print(f"  [artifact] BEL→{pt} {y}: holding-chain profit removed, cell total -> {level / 1e9:.2f}bn (WXD moved too)")

    def set_level(p, pt, y, cols_levels, panel=None):
        """Set a foreign cell's Total to `level` per column. The difference also comes off `panel`
        (or, if it is None, off the one sub-group panel present that year, if there is exactly one)
        and off the parent's WXD rows."""
        c = cell(p, pt, y)
        panels = [panel] if panel else [g for g in (POS, NEG) if (c & (cbcr["grouping"] == g)).any()]
        for col, level in cols_levels.items():
            if col not in cbcr.columns:
                continue
            mt = c & (cbcr["grouping"] == TOT)
            if mt.sum() != 1 or pd.isna(num(mt, col).iloc[0]):
                continue
            d = num(mt, col).iloc[0] - level
            for g in [TOT] + (panels if len(panels) == 1 else []):
                m = c & (cbcr["grouping"] == g)
                cbcr.loc[m, col] = num(m, col) - d
                wxd_shift(p, y, g, col, d)

    # JPN → JEY 2020–2023: the fair-value swings of SoftBank Vision Fund 1 and 2 (Jersey partnerships, according to
    # the Global Legal Entity Identifier Foundation, GLEIF) match the cell year by year (+59 / −31 / −36bn), and the
    # cell has almost no staff. I neutralise them to the cell's 2017–18 level (profit −0.13bn, revenue 1.34bn).
    # The swing of 2021 sits in the positive-profit panel, which feeds the ETR base. There I use the level +0.01bn,
    # the panel's 2017 level, so that the panel keeps a positive profit.
    for y, lvl in ((2020, -0.13e9), (2021, 0.01e9), (2022, -0.13e9), (2023, -0.13e9)):
        set_level("JPN", "JEY", y, {"profit_loss_before_income_tax": lvl,
                                    "adjusted_profit_loss_before_income_tax": lvl,
                                    "total_revenues": 1.34e9, "unrelated_party_revenues": 1.34e9})
    print("  [artifact] JPN→JEY 2020–2023: SoftBank Vision Fund swings neutralised (2017–18 level)")
    # JPN → CYM 2021–2023: SoftBank's Cayman vehicles (SB Northstar, the special-purpose vehicles of the Alibaba
    # forward contracts, SVF Cayman entities). The OECD size bands point to SoftBank. The loss sits in the band below
    # US$2.5bn in 2022, and in 2023 about 215 entities move to the band above US$10bn, as for a group whose
    # unrelated-party revenue was wiped out by investment losses. I set the loss panel to its own 2017–19 level
    # (profit −0.11bn, revenue 0.27bn, unrelated revenue 0.23bn, with revenue reset only in 2021–22, where it went
    # negative). The Total is the positive panel plus the reset loss panel, so both panels keep their sign.
    _neg_lvl = {"profit_loss_before_income_tax": -0.107e9, "adjusted_profit_loss_before_income_tax": -0.107e9,
                "total_revenues": 0.273e9, "unrelated_party_revenues": 0.230e9}
    for y in (2021, 2022, 2023):
        mpos = cell("JPN", "CYM", y) & (cbcr["grouping"] == POS)
        cols = list(_neg_lvl) if y in (2021, 2022) else ["profit_loss_before_income_tax",
                                                         "adjusted_profit_loss_before_income_tax"]
        lv = {}
        for col in cols:
            pos = num(mpos, col)
            pos = pos.iloc[0] if len(pos) == 1 and pd.notna(pos.iloc[0]) else 0.0
            lv[col] = pos + _neg_lvl[col]
        set_level("JPN", "CYM", y, lv, panel=NEG)
    print("  [artifact] JPN→CYM 2021–2023: SoftBank Cayman losses neutralised (2017–19 level)")
    # JPN → USA 2022–2023: the loss panel jumps from −5.8 to −13.1bn (2016–21) to −27.3bn (2022) and −101.6bn
    # (2023), while revenue, employees, assets and tax stay normal. The OECD size bands show about 700 holding and
    # "other activity" entities moving into the band above US$10bn in 2023, as SoftBank's Cayman vehicles did. In the
    # BEA data, the Japanese-owned US affiliates have positive income, with the capital losses of 2023 concentrated in
    # non-bank finance. SoftBank's SVF2 and Latin America funds hold their investments through stacked Delaware
    # limited liability companies (fair-value losses in FY2021–22). I apply the same rule as for JPN → CYM: I set the
    # loss panel to its own 2017–19 mean (−9.682bn) and the Total to the positive panel plus the reset loss panel, and
    # the parent's WXD moves too. Switch: config.CORRECT_JPN_USA_SOFTBANK. I correct all three SoftBank cells
    # (Jersey, Cayman, the US) because, in the pooled data, one group's fund losses shrink the profit pool of every
    # Japanese group.
    if CORRECT_JPN_USA_SOFTBANK:
        for y in (2022, 2023):
            mpos = cell("JPN", "USA", y) & (cbcr["grouping"] == POS)
            lv = {}
            for col in [k for k in PROFIT_COLS if k in cbcr.columns]:
                pos = num(mpos, col)
                pos = pos.iloc[0] if len(pos) == 1 and pd.notna(pos.iloc[0]) else 0.0
                lv[col] = pos - 9.682e9
            set_level("JPN", "USA", y, lv, panel=NEG)
        print("  [artifact] JPN→USA 2022–2023: SoftBank US fund losses neutralised (loss panel at its 2017–19 mean)")
    else:
        print("  [artifact] JPN→USA 2022–2023: SoftBank US fund losses kept (config.CORRECT_JPN_USA_SOFTBANK = False)")
    # JPN → SGP 2022–2023 and JPN → GBR 2022 (I correct every SoftBank-type cell). OECD Table VI (by group size)
    # shows the fund signature, a large loss on negative revenue, in the smallest size band in 2022: GBR −38.3bn on
    # −27.7bn of revenue and SGP −11.1bn on −3.1bn (also CYM −21.0bn and Jersey, inside "Other Europe", −29.1bn,
    # both corrected above). In 2023 the SoftBank-type losses sit in the largest band (JEY, CYM, USA), where SGP's
    # loss panel of −12.9bn also sits. I apply the same rule as for JPN → CYM and JPN → USA: I set the loss panel to
    # its own 2017–19 mean (SGP −0.791bn, GBR −4.748bn) and the Total to the positive panel plus the reset loss
    # panel, and the parent's WXD moves too. SGP's positive panel also rose in 2022–23 (from 11.4 to 23.4 and
    # 25.7bn, with revenue), and I keep it.
    if CORRECT_JPN_SGP_GBR_SOFTBANK:
        for pt, years, neg_lvl in (("SGP", (2022, 2023), -0.791e9), ("GBR", (2022,), -4.748e9)):
            for y in years:
                mpos = cell("JPN", pt, y) & (cbcr["grouping"] == POS)
                lv = {}
                for col in [k for k in PROFIT_COLS if k in cbcr.columns]:
                    pos = num(mpos, col)
                    pos = pos.iloc[0] if len(pos) == 1 and pd.notna(pos.iloc[0]) else 0.0
                    lv[col] = pos + neg_lvl
                set_level("JPN", pt, y, lv, panel=NEG)
        print("  [artifact] JPN→SGP 2022–2023, JPN→GBR 2022: SoftBank-type fund losses neutralised "
              "(loss panel at its 2017–19 mean)")
    else:
        print("  [artifact] JPN→SGP / JPN→GBR SoftBank-type losses kept (config.CORRECT_JPN_SGP_GBR_SOFTBANK = False)")
    # ZAF → NLD 2023: a loss of −34.7bn absorbed against stated capital (not Prosus) makes the South African pool of
    # 2023 negative. I set the profit to the cell's 2020–22 mean (−0.58bn).
    set_level("ZAF", "NLD", 2023, {"profit_loss_before_income_tax": -0.58e9,
                                   "adjusted_profit_loss_before_income_tax": -0.58e9})
    print("  [artifact] ZAF→NLD 2023: profit set to the 2020–22 mean (−0.58bn)")
    # Cash-tax entry errors: in these panels the cash tax is many times the accrued tax and the level of the cell's
    # other years, while profit is normal. I set the panel's cash tax to its accrued tax. The Total moves by the same
    # difference, and for foreign cells so do the parent's WXD rows. As a guard, I only correct a panel if its cash
    # tax is more than 4 times the accrued tax.
    CT, AT = "income_tax_paid_on_cash_basis", "income_tax_accrued_current_year"

    def cash_tax_to_accrued(p, pt, y, panel):
        c = cell(p, pt, y)
        mp, mt = c & (cbcr["grouping"] == panel), c & (cbcr["grouping"] == TOT)
        if mp.sum() != 1 or mt.sum() != 1 or AT not in cbcr.columns:
            return
        cash, acc = num(mp, CT).iloc[0], num(mp, AT).iloc[0]
        if pd.isna(cash) or pd.isna(acc) or cash <= 4 * max(acc, 1.0):
            return
        d = cash - acc
        for m in (mp, mt):
            cbcr.loc[m, CT] = num(m, CT) - d
        if p != pt:                       # a domestic cell has no WXD counterpart
            wxd_shift(p, y, panel, CT, d)
            wxd_shift(p, y, TOT, CT, d)
        print(f"  [artifact] {p}→{pt} {y} ({panel}): cash tax {cash / 1e6:,.1f}m -> {acc / 1e6:,.1f}m (accrued tax)")

    for p, pt, y, panel in [("CHN", "CYP", 2023, POS),   # cash US$3,064m on US$103m of profit
                            ("HKG", "SGP", 2022, POS),   # 4,312m against 163m accrued, cash 164m / 454m in 2021 / 2023
                            ("JPN", "CAN", 2022, POS),   # 9,673m against 345m, otherwise 430–640m in 2020–23
                            ("JPN", "VNM", 2022, POS),   # 2,706m against 644m, cash 591m / 755m in 2021 / 2023
                            ("ZAF", "ZAF", 2018, NEG),   # 29,105m in the loss panel against 361m accrued
                            ("LUX", "COL", 2017, POS),   # 2,811m on 50m of profit, accrued −17m, cash 4–139m otherwise
                            ("JPN", "COL", 2020, POS),   # 1,962m against 33m accrued, cash 23–60m otherwise
                            ("JPN", "SVN", 2019, POS),   # 891m against 4m accrued, cash 5–11m otherwise
                            ("JPN", "KHM", 2019, POS),   # 230m against 20m accrued, cash 16–58m otherwise
                            ("JPN", "HRV", 2019, POS),   # 119m against 1m accrued, cash 1–3m otherwise
                            ("ARE", "TKM", 2021, POS),   # cash equal to the profit (136m), accrued tax nil
                            ("LUX", "PHL", 2017, POS),   # 80m on 19m of profit against 1m accrued, cash 2–8m otherwise
                            ("SAU", "ESP", 2019, POS),   # 60m on 13m of profit against 2m accrued, cash 2–10m otherwise
                            ("JEY", "CAN", 2023, POS)]:  # 89m on 34m of profit against 7m accrued
        cash_tax_to_accrued(p, pt, y, panel)

    # TUR: in 2021 the cash tax of the whole submission is many times its accrued tax (foreign lines 7.1bn against
    # 0.7bn, the domestic line 12.0bn against 4.3bn), while profit is normal and in the other years the cash tax is
    # close to the accrued tax. I set the cash tax of every 2021 row to its accrued tax, in every panel and for each
    # partner, aggregate and WXD row, so the WXD rows need no separate shift. On the domestic line the 2021 excess
    # partly comes back as cash tax below the accrued tax in 2022 and 2023, so there I use the accrued tax in every
    # year.
    mtur = (cbcr["iso_parent"] == "TUR") & ((yr == 2021) | (cbcr["iso_partner"] == "TUR"))
    if AT in cbcr.columns:
        mtur &= pd.to_numeric(cbcr[AT], errors="coerce").notna()
        before = num(mtur & (cbcr["grouping"] == TOT), CT).groupby(yr[mtur & (cbcr["grouping"] == TOT)]).sum()
        cbcr.loc[mtur, CT] = num(mtur, AT)
        after = num(mtur & (cbcr["grouping"] == TOT), CT).groupby(yr[mtur & (cbcr["grouping"] == TOT)]).sum()
        print("  [artifact] TUR: cash tax set to the accrued tax (2021 all rows, domestic line every year), "
              "Total rows incl. WXD in US$m: "
              + ", ".join(f"{int(y)} {before[y] / 1e6:,.0f} -> {after[y] / 1e6:,.0f}" for y in before.index))

    # THA → CHN 2023: CNY entered as US$ in the negative panel
    money = [k for k in ["profit_loss_before_income_tax", "adjusted_profit_loss_before_income_tax",
                         "income_tax_paid_on_cash_basis", "income_tax_accrued_current_year",
                         "total_revenues", "unrelated_party_revenues", "related_party_revenues",
                         "tangible_assets_except_cash", "stated_capital"] if k in cbcr.columns]
    c = cell("THA", "CHN", 2023)
    mneg, mtot = c & (cbcr["grouping"] == NEG), c & (cbcr["grouping"] == TOT)
    if mneg.sum() == 1 and mtot.sum() == 1:
        for col in money:
            v = num(mneg, col).iloc[0]
            if pd.notna(v):
                new = v / 7.084
                cbcr.loc[mneg, col] = new
                cbcr.loc[mtot, col] = num(mtot, col) - (v - new)
                wxd_shift("THA", 2023, NEG, col, v - new)
                wxd_shift("THA", 2023, TOT, col, v - new)
        print("  [artifact] THA→CHN 2023: negative panel converted from CNY (/7.084), Total adjusted")

    # CZE → CZE 2023 employees
    base = (cbcr["iso_parent"] == "CZE") & (cbcr["iso_partner"] == "CZE")
    for g in cbcr.loc[base, "grouping"].unique():
        m = base & (cbcr["grouping"] == g)
        o = m & (yr != 2023) & yr.between(first_year, last_year)
        ratio = (num(o, "n_employees") / num(o, "total_revenues")).replace([np.inf, -np.inf], np.nan).mean()
        m23 = m & (yr == 2023)
        if m23.sum() == 1 and pd.notna(ratio):
            old = num(m23, "n_employees").iloc[0]
            cbcr.loc[m23, "n_employees"] = num(m23, "total_revenues").iloc[0] * ratio
            print(f"  [artifact] CZE→CZE 2023 employees ({g}): {old:,.0f} -> {num(m23, 'n_employees').iloc[0]:,.0f}")

    # AZE → JPN 2022 tangible assets in yen
    m = cell("AZE", "JPN", 2022)
    if m.any():
        for i in cbcr.index[m]:
            v = pd.to_numeric(cbcr.at[i, "tangible_assets_except_cash"], errors="coerce")
            if pd.notna(v):
                cbcr.at[i, "tangible_assets_except_cash"] = v / 131.50
                wxd_shift("AZE", 2022, cbcr.at[i, "grouping"], "tangible_assets_except_cash", v - v / 131.50)
        print("  [artifact] AZE→JPN 2022 tangible assets converted from JPY (/131.50)")

    # ARG → ARG 2021–2022 tangible assets: the excess sits in the positive-profit panel (500bn and 854bn against 65bn
    # and 37bn in 2020 and 2023). I interpolate that panel between 2020 and 2023 and set the Total to the sum of the
    # positive and the negative panel (the negative panel stays unchanged).
    base = (cbcr["iso_parent"] == "ARG") & (cbcr["iso_partner"] == "ARG")
    TA = "tangible_assets_except_cash"
    mp = base & (cbcr["grouping"] == POS)
    a20, a23 = num(mp & (yr == 2020), TA), num(mp & (yr == 2023), TA)
    if len(a20) == 1 and len(a23) == 1 and pd.notna(a20.iloc[0]) and pd.notna(a23.iloc[0]):
        for y, w in ((2021, 1 / 3), (2022, 2 / 3)):
            cbcr.loc[mp & (yr == y), TA] = a20.iloc[0] + w * (a23.iloc[0] - a20.iloc[0])
            neg = num(base & (cbcr["grouping"] == NEG) & (yr == y), TA)
            neg = neg.iloc[0] if len(neg) == 1 and pd.notna(neg.iloc[0]) else 0.0
            cbcr.loc[base & (cbcr["grouping"] == TOT) & (yr == y), TA] = num(mp & (yr == y), TA).iloc[0] + neg
        print("  [artifact] ARG→ARG 2021–2022 tangible assets (positive panel) interpolated between 2020 and 2023")

    # ---- Entry, unit and currency errors ----
    # A screen of every variable for single-year spikes found these cells. In each, one year lies orders of magnitude
    # away from the cell's other years, while the fields that should move with it stay at their level. I set the
    # faulty values to the median of the cell's other years in the analysis window and take the difference off the
    # panel that carries the error. The Total moves by the same difference, and for foreign cells so do the parent's
    # WXD rows.
    win = yr.between(first_year, last_year)

    def median_other_years(p, pt, y, grouping, col):
        m = ((cbcr["iso_parent"] == p) & (cbcr["iso_partner"] == pt) & (cbcr["grouping"] == grouping)
             & win & (yr != y))
        return pd.to_numeric(cbcr.loc[m, col], errors="coerce").median()

    def total_to_median(p, pt, y, cols, panel=None):
        """Set the Total of each column to the median of the cell's other years (set_level)."""
        lv = {c: median_other_years(p, pt, y, TOT, c) for c in cols if c in cbcr.columns}
        set_level(p, pt, y, {c: v for c, v in lv.items() if pd.notna(v)}, panel=panel)

    def panel_to_median(p, pt, y, panel, cols):
        """Set a sub-group panel to the median of the same panel in the cell's other years."""
        c = cell(p, pt, y)
        mp, mt = c & (cbcr["grouping"] == panel), c & (cbcr["grouping"] == TOT)
        if mp.sum() != 1 or mt.sum() != 1:
            return
        for col in [k for k in cols if k in cbcr.columns]:
            v, lvl = num(mp, col).iloc[0], median_other_years(p, pt, y, panel, col)
            if pd.isna(v) or pd.isna(lvl):
                continue
            d = v - lvl
            cbcr.loc[mp, col] = lvl
            cbcr.loc[mt, col] = num(mt, col) - d
            if p != pt:
                wxd_shift(p, y, panel, col, d)
                wxd_shift(p, y, TOT, col, d)

    def total_to_panel_sum(p, pt, y, col):
        """Set the Total to the sum of the sub-group panels, where the error sits in the Total alone."""
        c = cell(p, pt, y)
        mt = c & (cbcr["grouping"] == TOT)
        s = pd.to_numeric(cbcr.loc[c & cbcr["grouping"].isin([POS, NEG]), col], errors="coerce").sum(min_count=1)
        if mt.sum() != 1 or pd.isna(s):
            return
        d = num(mt, col).iloc[0] - s
        cbcr.loc[mt, col] = s
        if p != pt:
            wxd_shift(p, y, TOT, col, d)

    # BMU → CHN 2016: revenue of 508bn, profit of 25.8bn and stated capital of 1.18tn, against 23–93bn of revenue and
    # 1.1–5.3bn of profit in 2017–2023. Divided by the 2016 rate of yuan per US$ (6.644), the amounts fit the later
    # years, so I convert every monetary field of the cell. Employees and counts stay unchanged.
    for i in cbcr.index[cell("BMU", "CHN", 2016)]:
        for col in money:
            v = pd.to_numeric(cbcr.at[i, col], errors="coerce")
            if pd.notna(v):
                cbcr.at[i, col] = v / 6.644
                wxd_shift("BMU", 2016, cbcr.at[i, "grouping"], col, v - v / 6.644)
    # BMU → PER 2016: profit of 15.0bn, revenue of 58bn and assets of 287bn, against 0.1–1.8bn, 3–8bn and 0.4–3.1bn in
    # 2017–2023, with the same 31,000 employees. I set every monetary field to the median of the other years, so that
    # the tax of 4.8bn does not stay behind on the reset profit.
    total_to_median("BMU", "PER", 2016, money, panel=POS)
    # Profit spikes on revenue at the cell's usual level: BMU → VGB 2016 (12.7bn on 1.5bn of revenue), BMU → HKG 2016
    # (13.9bn on 15.6bn of revenue), ZAF → GBR, ZAF → ARE and ZAF → HKG 2018 (21.9bn, 10.0bn and 9.2bn, against
    # medians of 0.06, 0.17 and 0.05bn), CHL → PAN 2021 (33.4bn on 2.2bn of revenue, about 270 times its level) and
    # BRA → VEN 2016 (a loss of 19.5bn on 4.9bn of revenue). I set the profit to the median of the other years as
    # reported, before the loss swings of other years are reset below.
    mchl = cell("CHL", "PAN", 2021) & (cbcr["grouping"] == TOT)
    chl_before = {col: num(mchl, col).iloc[0] for col in PROFIT_COLS if col in cbcr.columns and mchl.sum() == 1}
    for p, pt, y, panel in (("BMU", "VGB", 2016, POS), ("BMU", "HKG", 2016, POS), ("ZAF", "GBR", 2018, None),
                            ("ZAF", "ARE", 2018, None), ("ZAF", "HKG", 2018, None), ("CHL", "PAN", 2021, None),
                            ("BRA", "VEN", 2016, NEG)):
        total_to_median(p, pt, y, PROFIT_COLS, panel=panel)
    # The panels of CHL → PAN 2021 are suppressed, so the spike also sits in the positive panel of Chile's WXD row.
    # I move that panel by the same amount.
    for col, v in chl_before.items():
        if pd.notna(v):
            wxd_shift("CHL", 2021, POS, col, v - num(mchl, col).iloc[0])
    # MEX → VEN 2017: a loss of 13.0bn and assets of 71bn on 9.3bn of revenue, against amounts below 0.3bn in
    # 2018–2023. These are bolivars entered as US$, the fault for which I drop Mexico's 2020 submission. The 7,400
    # employees fit 2016, so I keep them and set every monetary field to the median of the other years.
    total_to_median("MEX", "VEN", 2017, money, panel=NEG)
    # MYS → THA 2020: the loss panel shows a loss of 31.8bn, revenue of 46bn and 41,700 employees, against losses below
    # 0.11bn, revenue below 0.5bn and 500–2,500 employees in the other years. I set that panel to the median of its
    # other years in every field. The positive panel stays as reported.
    panel_to_median("MYS", "THA", 2020, NEG, money + ["n_employees"])
    # Employees. BMU → IND 2016: 12,800 in the positive panel on revenue of 6.6bn, against 81,000–143,000 from 2017.
    # CYM → SGP 2023: 1,548,041 in the positive panel (Singapore's labour force is 3.9m), against 4,100–14,000.
    # Luxembourg's 2021 submission: 1.40m in the United Kingdom, 1.04m in the United States and 148,000 in Belgium
    # (loss panels), against 27,000–102,000, 35,000–86,000 and 1,500–28,000 in the other years, and the same pattern
    # in the Netherlands (loss panel), Switzerland and Spain (positive panels).
    for p, pt, y, panel in (("BMU", "IND", 2016, POS), ("CYM", "SGP", 2023, POS),
                            ("LUX", "GBR", 2021, NEG), ("LUX", "USA", 2021, NEG), ("LUX", "BEL", 2021, NEG),
                            ("LUX", "NLD", 2021, NEG), ("LUX", "CHE", 2021, POS), ("LUX", "ESP", 2021, POS)):
        panel_to_median(p, pt, y, panel, ["n_employees"])
    # CHN → FIN 2018 (540,000 employees in the Total, 1,401 in the panel) and LUX → DEU 2021 (670,498 in the Total,
    # 137,701 in the two panels): the error sits in the Total alone.
    for p, pt, y in (("CHN", "FIN", 2018), ("LUX", "DEU", 2021)):
        total_to_panel_sum(p, pt, y, "n_employees")
    print("  [artifact] entry, unit and currency errors: BMU 2016 (CHN in yuan, PER, VGB, HKG, IND), ZAF 2018 "
          "(GBR, ARE, HKG), CHL→PAN 2021, BRA→VEN 2016, MEX→VEN 2017, MYS→THA 2020, employees CYM→SGP 2023, "
          "CHN→FIN 2018, LUX 2021 (7 cells)")
    return cbcr


cbcr = correct_listed_cell_artifacts(cbcr)

# %% MARK: 3.7 Loss swings in tax havens

def correct_haven_loss_swings(cbcr):
    """Reset huge losses booked in tax havens to the cell's ordinary level.

    For every foreign cell (parent ≠ partner) whose partner is a tax haven, a year's loss panel (sub-groups
    with negative profits) counts as a swing when it is a loss of at least HAVEN_LOSS_SWING_MIN_USD and more
    than HAVEN_LOSS_SWING_MULTIPLE times the cell's ordinary loss. Such holding and valuation losses (the SoftBank
    pattern, or US groups' −101bn in Luxembourg in 2021 and −34.6bn and −21.2bn in Malta in 2020 and 2023) would
    otherwise make the haven look like a winner under unitary taxation and shrink the parent country's pool.

    The ordinary loss is the smaller of (a) the cell's median loss in its other years and (b) the loss that is
    ordinary for loss-making business. That is the margin that loss panels book in non-haven foreign cells in the
    same year (Σ loss ÷ Σ total revenues, all parents) times the cell's loss-panel revenues (zero where those
    revenues are zero or negative). The margin pools only true losses (loss < 0) on positive revenues. The cell's
    own median alone would treat losses that a haven books every year as ordinary. I judge cells with fewer than
    three years on (b) alone. I reset a swing to the smaller of the two ordinary losses and never below the reported
    loss. For the reset, (a) is the median of the cell's years without a swing. The Total and the parent's WXD rows
    move by the same amount. The function runs after correct_listed_cell_artifacts, so the SoftBank cells are
    already at their ordinary level. The haven set is the frozen TAX_HAVENS_FUNCTIONAL, because the rule changes
    numbers and the representation list is derived from the estimates, so it would feed back into them.
    Switch: config.CORRECT_HAVEN_LOSS_SWINGS. I write every reset panel to haven_loss_swings.csv (listed under
    Writes in the module header).
    """
    if not CORRECT_HAVEN_LOSS_SWINGS:
        print("  [haven losses] swings kept (config.CORRECT_HAVEN_LOSS_SWINGS = False)")
        return cbcr
    TOT, NEG = "Total (All sub-groups)", "Sub-groups with negative profits"
    yr = pd.to_numeric(cbcr["year"], errors="coerce")
    cols = [c for c in ["profit_loss_before_income_tax", "adjusted_profit_loss_before_income_tax"] if c in cbcr.columns]
    havens = TAX_HAVENS_FUNCTIONAL
    foreign_neg = (cbcr["grouping"] == NEG) & (cbcr["iso_parent"] != cbcr["iso_partner"])
    neg = cbcr[foreign_neg & cbcr["iso_partner"].isin(havens)].copy()
    neg["_L"] = pd.to_numeric(neg["profit_loss_before_income_tax"], errors="coerce")
    neg["_y"] = pd.to_numeric(neg["year"], errors="coerce")
    # ---- (b) ordinary loss: the year's loss margin of loss panels in non-haven countries ----
    nh = cbcr[foreign_neg & ~cbcr["iso_partner"].isin(havens) & ~cbcr["iso_partner"].isin(non_countries)]
    g = pd.DataFrame({"y": yr[nh.index],
                      "L": pd.to_numeric(nh["profit_loss_before_income_tax"], errors="coerce"),
                      "R": pd.to_numeric(nh["total_revenues"], errors="coerce")}).dropna()
    g = g[(g["L"] < 0) & (g["R"] > 0)].groupby("y").sum()
    margin = g["L"] / g["R"]
    print("  [haven losses] ordinary loss margin (non-haven loss panels): "
          + ", ".join(f"{int(y)} {m:.1%}" for y, m in margin.items()))
    neg["_ord"] = neg["_y"].map(margin) * pd.to_numeric(neg["total_revenues"], errors="coerce").clip(lower=0)
    audit = []
    for (p, q), d in neg.dropna(subset=["_L"]).groupby(["iso_parent", "iso_partner"]):
        if len(d) < 3 and d["_ord"].isna().all():
            continue
        own = {i: d.loc[d.index != i, "_L"].abs().median() if len(d) >= 3 else np.nan for i in d.index}
        bench = {i: np.nanmin([own[i], abs(d.at[i, "_ord"])]) if pd.notna(own[i]) or pd.notna(d.at[i, "_ord"])
                 else np.nan for i in d.index}
        swing = [i for i in d.index
                 if d.at[i, "_L"] <= -HAVEN_LOSS_SWING_MIN_USD
                 and pd.notna(bench[i]) and abs(d.at[i, "_L"]) > HAVEN_LOSS_SWING_MULTIPLE * bench[i]]
        if not swing:
            continue
        ordinary = d.loc[~d.index.isin(swing), "_L"]
        own_level = float(ordinary.median()) if len(d) >= 3 and not ordinary.empty else np.nan
        for i in swing:
            level = np.nanmax([own_level, d.at[i, "_ord"]])    # the smaller of the two ordinary losses
            if pd.isna(level):
                continue
            level = min(level, 0.0)
            if level <= d.at[i, "_L"]:                         # never deepen a loss
                continue
            y = int(d.at[i, "_y"])
            delta = d.at[i, "_L"] - level                      # negative: the loss removed
            c = (cbcr["iso_parent"] == p) & (cbcr["iso_partner"] == q) & (yr == y)
            for col in cols:
                for g in (NEG, TOT):
                    m = c & (cbcr["grouping"] == g)
                    v = pd.to_numeric(cbcr.loc[m, col], errors="coerce")
                    cbcr.loc[m, col] = v - delta
                    mw = (cbcr["iso_parent"] == p) & (cbcr["iso_partner"] == "WXD") & (yr == y) & (cbcr["grouping"] == g)
                    if mw.any():
                        cbcr.loc[mw, col] = pd.to_numeric(cbcr.loc[mw, col], errors="coerce") - delta
            audit.append({"iso_parent": p, "iso_partner": q, "year": y, "loss_panel_usd": d.at[i, "_L"],
                          "reset_to_usd": level, "removed_usd": delta,
                          "median_other_years_usd": own[i], "ordinary_margin_loss_usd": d.at[i, "_ord"]})
    a = pd.DataFrame(audit)
    out = output_root / "diagnostics" / "haven_loss_swings"
    out.mkdir(parents=True, exist_ok=True)
    a.to_csv(out / "haven_loss_swings.csv", index=False)
    if len(a):
        top = a.sort_values("removed_usd").head(6)
        print(f"  [haven losses] {len(a)} loss panels reset in {a[['iso_parent', 'iso_partner']].drop_duplicates().shape[0]} "
              f"haven cells; losses removed US${-a.removed_usd.sum() / 1e9:,.1f}bn over all years; largest: "
              + ", ".join(f"{r.iso_parent}→{r.iso_partner} {r.year} {r.loss_panel_usd / 1e9:,.1f}bn" for r in top.itertuples()))
    return cbcr


cbcr = correct_haven_loss_swings(cbcr)

# %% MARK: 4. Corrected profit
# profit_loss_before_income_tax_corrected is the reported profit without the dividends counted twice (4.1), with the
# UK's suppressed domestic profit of 2023 filled in (4.2) and with the rest-of-world rows rebuilt from the corrected
# cells (4.3).

# %% MARK: 4.1 Dividends counted twice (García-Bernardo, Janský and Zucman)

def correct_for_dividend_double_counting(row, year, corrections, tax_havens):
    """
    Correct a row's reported profit for dividends counted twice. The caller stores the result
    in 'profit_loss_before_income_tax_corrected'.
    """
    profit = row.get("profit_loss_before_income_tax")

    if pd.isna(profit):
        return np.nan

    # I use the OECD's adjusted profits where they are available and then apply no further correction.
    if pd.notna(row.get("adjusted_profit_loss_before_income_tax")):
        return row["adjusted_profit_loss_before_income_tax"]

    # I do not correct profits that are zero or negative.
    if profit <= 0:
        return profit

    # I only apply the rules of the row's year.
    if row["year"] != year:
        return profit

    # Domestic profits
    if row["iso_parent"] == row["iso_partner"]:
        domestic_correction = (
            corrections["domestic"].get(year, {}).get(row["iso_parent"], 0)
        )
        profit *= 1 - domestic_correction

    # Foreign profits
    else:
        # The 10% haven correction and the 5% aggregate correction apply to non-US parents only. García-Bernardo and
        # Janský (2024, section 3) write: "we remove 10% of profits in tax havens for non-US MNCs". For US
        # multinationals, the US-specific foreign correction of García-Bernardo, Janský and Zucman (2026, sections
        # 2.5–2.6, which remove foreign double counting from haven profits) below handles the dividends counted twice
        # in full, so stacking the two cuts would correct twice.
        if row["iso_parent"] != "USA":
            taxhaven_correction = (
                corrections["taxhavens"].get(year, {}).get(row["iso_partner"], 0)
            )
            profit *= 1 - taxhaven_correction

            countrygroup_correction = (
                corrections["countrygroups"].get(year, {}).get(row["iso_partner"], 0)
            )
            profit *= 1 - countrygroup_correction

        foreign_correction = (
            corrections["foreign"].get(year, {}).get(row["iso_parent"], 0)
        )
        profit *= 1 - foreign_correction

    return profit
#
# Sources:
#
# General corrections:
# Garcia-Bernardo, J. and Janský, P. (2024).
# "Profit shifting of multinational corporations worldwide."
# World Development, 177, 106527.
#
# USA-specific corrections:
# Garcia-Bernardo, J., Janský, P. and Zucman, G. (2026).
# "Did the Tax Cuts and Jobs Act Reduce Profit Shifting by US Multinational Companies?"
#
# Assumptions:
# - I treat 2016 like 2017.
# - From 2020 onwards, I apply no corrections.
# - Italy receives the standard 35% correction.
# - For NLD and GBR, I use the OECD-adjusted profits where they are available, so I do not correct them separately
#   here.
# - Aggregated country groups receive a 5% correction because they may contain tax havens.

correction_domestic = {
    2016: {"USA": 0.54},
    2017: {"USA": 0.54},
    2018: {"USA": 0.74},
    2019: {"USA": 0.42},
    # There is no correction from 2020 onwards. Keys after 2019 are not needed because I look the years up with
    # .get(year, {}), so extending the window needs no edit here.
}

correction_foreign = {
    2016: {"USA": 0.07},
    2017: {"USA": 0.07},
    2018: {"USA": 0.39},
    2019: {"USA": 0.28},
    # There is no correction from 2020 onwards (see correction_domestic).
}

# Country-specific deviations from the general domestic correction of 35% that every parent receives for 2016–2019.
# I apply the general correction first and then override it with the entries here. The 0.00 entries do have an
# effect: they switch the default 35% off for parents whose domestic ETR shows no sign of inflation by dividends.
correction_domestic_other_countries = {
    year: {
        # The domestic ETR is far below the foreign ETR, so the correction is stronger.
        "BEL": 0.50,
        "SGP": 0.50,
        "BMU": 0.50,
        # The domestic ETR exceeds the foreign ETR, so there is no correction (this overrides the 35%).
        "LVA": 0.00,
        "SVN": 0.00,
        "LUX": 0.00,
        # Saudi Arabia: the domestic cell is essentially Saudi Aramco (its settled income tax and zakat match the
        # cell's tax within 0.6–3.4bn in 2018–2020), whose profit comes from upstream oil, not from intra-group
        # dividends. The 35% cut would take 77bn and 72bn (2018 and 2019) off it and leave the cell below Aramco's
        # own pre-tax income (source table data/raw/extractive/source_tables/SAU_aramco_financials_2016_2024.csv).
        "SAU": 0.00,
    }
    for year in range(2016, 2020)
}

correction_taxhavens = {
    year: {key: 0.10 for key in tax_havens} for year in range(2016, 2020)
}

# Aggregated country groups may contain tax havens, so I apply half of the tax-haven correction to them. This covers
# both the "other" residual codes (WXD, A_O, …) and the single-letter continent aggregates (A, E, F, S), because the
# reasoning is the same for the two families. W is dropped in 2.2.
correction_countrygroups = {
    year: {
        key: 0.05
        for key in (other_country_groups | aggregated_country_groups) - {"W"}
    }
    for year in range(2016, 2020)
}

corrections = {
    "domestic": {},
    "foreign": {},
    "taxhavens": {},
    "countrygroups": {},
}

for year in analysis_years:

    corrections["domestic"][year] = {key: 0 for key in parent_countries.tolist()}

    corrections["foreign"][year] = {key: 0 for key in parent_countries.tolist()}

    corrections["taxhavens"][year] = {key: 0 for key in partner_countries.tolist()}

    corrections["countrygroups"][year] = {key: 0 for key in partner_countries.tolist()}

    # General domestic correction (2016–2019 only)
    if year in range(2016, 2020):
        corrections["domestic"][year].update(
            {key: 0.35 for key in parent_countries.tolist()}
        )

    # Country-specific domestic corrections
    corrections["domestic"][year].update(
        correction_domestic_other_countries.get(year, {})
    )

    # USA-specific domestic corrections
    corrections["domestic"][year].update(correction_domestic.get(year, {}))

    # USA-specific foreign corrections
    corrections["foreign"][year].update(correction_foreign.get(year, {}))

    # Tax haven corrections
    corrections["taxhavens"][year].update(correction_taxhavens.get(year, {}))

    # Country-group corrections
    corrections["countrygroups"][year].update(correction_countrygroups.get(year, {}))

    print(
        f"Applied corrections for year {year} "
        f"(Domestic: {len(corrections['domestic'][year])} countries, "
        f"Foreign: {len(corrections['foreign'][year])}, "
        f"Tax Havens: {len(corrections['taxhavens'][year])}, "
        f"Country Groups: {len(corrections['countrygroups'][year])})"
    )

print(corrections)

# I apply the corrections row by row.

for year in analysis_years:
    mask = cbcr["year"] == year
    original_values = cbcr.loc[mask, "profit_loss_before_income_tax"].copy()

    adjusted_available = cbcr.loc[
        mask, "adjusted_profit_loss_before_income_tax"
    ].notna()

    corrected_values = cbcr.loc[mask].apply(
        lambda row: correct_for_dividend_double_counting(
            row, year, corrections, tax_havens
        ),
        axis=1,
    )

    cbcr.loc[mask, "profit_loss_before_income_tax_corrected"] = corrected_values

    changed = (
        corrected_values.notna()
        & original_values.notna()
        & (corrected_values != original_values)
    ).sum()

    changed_by_adjusted_profit = (
        adjusted_available
        & corrected_values.notna()
        & original_values.notna()
        & (corrected_values != original_values)
    ).sum()

    changed_by_manual_correction = (
        ~adjusted_available
        & corrected_values.notna()
        & original_values.notna()
        & (corrected_values != original_values)
    ).sum()

    domestic_nonzero = {
        k: v for k, v in corrections["domestic"][year].items() if v != 0
    }
    foreign_nonzero = {k: v for k, v in corrections["foreign"][year].items() if v != 0}
    taxhavens_nonzero = {
        k: v for k, v in corrections["taxhavens"][year].items() if v != 0
    }
    countrygroups_nonzero = {
        k: v for k, v in corrections["countrygroups"][year].items() if v != 0
    }

    print(f"\nYear {year}")
    print(f"Processed rows: {mask.sum()}")
    print(f"Non-missing corrected entries: {corrected_values.notna().sum()}")
    print(f"Actually changed entries: {changed}")
    print(f"Changed via OECD adjusted profits: {changed_by_adjusted_profit}")
    print(f"Changed via manual correction rules: {changed_by_manual_correction}")
    print(f"Domestic corrections: {domestic_nonzero}")
    print(f"Foreign corrections: {foreign_nonzero}")
    print(f"Tax haven corrections: {taxhavens_nonzero}")
    print(f"Country group corrections: {countrygroups_nonzero}")

# %% MARK: 4.2 The UK's domestic profit in 2023
# The OECD suppresses the UK groups' domestic Total profit for FY2023. I fill it after the dividend corrections, on the
# corrected-profit column only, with the published 2023 positive-profit panel plus the average loss panel of
# UK_DOMESTIC_PROFIT_RATIO_YEARS (2017–2022). The raw reported profit stays missing, and the row is flagged as
# imputed.

cbcr, _uk_profit_audit = fill_uk_domestic_profit(
    cbcr,
    enabled=IMPUTE_UK_DOMESTIC_PROFIT_2023,
    target_year=UK_DOMESTIC_PROFIT_IMPUTATION_TARGET_YEAR,
    source_years=UK_DOMESTIC_PROFIT_RATIO_YEARS,
    source_file=_Path(cbcr_data).relative_to(_Path(data_raw).parents[1]).as_posix(),   # repository-relative
)
_uk_profit_audit_dir = output_root / "diagnostics" / "cbcr_profit_imputation"
_uk_profit_audit_dir.mkdir(parents=True, exist_ok=True)
_uk_profit_audit.to_csv(_uk_profit_audit_dir / "uk_domestic_profit_carryforward.csv", index=False)
if not _uk_profit_audit.empty:
    _uk_record = _uk_profit_audit.iloc[0]
    print(
        f"UK domestic Total {_uk_record.target_year}: filled at "
        f"{_uk_record.imputed_corrected_profit_usd / 1e9:,.3f}bn USD ({_uk_record.method}); "
        "raw reported profit remains missing."
    )

# %% MARK: 4.3 Rest-of-world rows after the corrections
# The dividend corrections act on each row, so I rebuild the corrected profit of every WXD row from the corrected
# foreign rows of its block.

def fix_corrected_wxd(cbcr, rtol=1e-6, atol=1e-3):
    """
    Rebuild the corrected WXD profits after the row-wise dividend correction.

    A WXD row that equals the sum of its block's foreign rows takes the sum of their
    corrected profits. Otherwise, I scale that sum by the ratio of the raw WXD value to the
    raw sum of the foreign rows. Blocks with only domestic and WXD rows keep the raw WXD
    profit. Blocks without a usable raw sum keep the row-wise corrected value.
    """
    cbcr = cbcr.copy()
    group_cols = ["iso_parent", "year", "grouping"]

    n_wxd_rows = 0
    n_domestic_wxd_only = 0
    n_exact_match = 0
    n_scaled = 0
    n_fallback = 0

    grouped_indices = cbcr.groupby(group_cols, sort=False).groups

    for _, idx in grouped_indices.items():
        idx = list(idx)
        block = cbcr.loc[idx].copy()

        iso_parent = block["iso_parent"].iloc[0]
        wxd_mask = block["iso_partner"] == "WXD"

        if not wxd_mask.any():
            continue

        wxd_idx = block.index[wxd_mask]
        n_wxd_rows += len(wxd_idx)

        reported_codes = set(block["iso_partner"].dropna())

        # If the block only has domestic and WXD rows, I keep the raw WXD value.
        if reported_codes == {iso_parent, "WXD"}:
            replacement_value = block.loc[
                wxd_mask, "profit_loss_before_income_tax"
            ].sum(min_count=1)
            cbcr.loc[wxd_idx, "profit_loss_before_income_tax_corrected"] = (
                replacement_value
            )
            n_domestic_wxd_only += len(wxd_idx)
            continue

        base_mask = (block["iso_partner"] != iso_parent) & (
            block["iso_partner"] != "WXD"
        )

        original_base_sum = block.loc[base_mask, "profit_loss_before_income_tax"].sum(
            min_count=1
        )
        corrected_base_sum = block.loc[
            base_mask, "profit_loss_before_income_tax_corrected"
        ].sum(min_count=1)
        original_wxd = block.loc[wxd_mask, "profit_loss_before_income_tax"].sum(
            min_count=1
        )

        if pd.isna(original_wxd) or pd.isna(corrected_base_sum):
            n_fallback += len(wxd_idx)
            continue

        if pd.notna(original_base_sum) and np.isclose(
            float(original_wxd),
            float(original_base_sum),
            rtol=rtol,
            atol=atol,
        ):
            replacement_value = corrected_base_sum
            n_exact_match += len(wxd_idx)

        elif pd.notna(original_base_sum) and float(original_base_sum) != 0:
            scale_factor = float(original_wxd) / float(original_base_sum)
            replacement_value = float(corrected_base_sum) * scale_factor
            n_scaled += len(wxd_idx)

        else:
            n_fallback += len(wxd_idx)
            continue

        cbcr.loc[wxd_idx, "profit_loss_before_income_tax_corrected"] = replacement_value

    print(f"WXD rows checked: {n_wxd_rows}")
    print(f"  domestic + WXD only: {n_domestic_wxd_only}")
    print(f"  exact-match replacements: {n_exact_match}")
    print(f"  scaled replacements: {n_scaled}")
    print(f"  fallback / unchanged: {n_fallback}")

    return cbcr


cbcr = fix_corrected_wxd(cbcr)

# %% MARK: 4.4 Log variables
# I take log(1 + x) of the non-negative part of selected variables.

variables_to_log = [
    "profit_loss_before_income_tax_corrected",
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
    "stated_capital",
    "total_revenues",
    "related_party_revenues",
    "holding_or_managing_ip",
]

for col_name in variables_to_log:
    if col_name in cbcr.columns:
        new_col_name = f"ln_{col_name}"
        cbcr[new_col_name] = np.log1p(cbcr[col_name].clip(lower=0))
        num_transformed = cbcr[new_col_name].notna().sum()
        print(
            f"Transformed {num_transformed} values for column '{col_name}' into '{new_col_name}'"
        )
    else:
        print(
            f"Column '{col_name}' not found in the DataFrame. Skipping transformation."
        )

# %% MARK: 5. Effective tax rates
# I compute partner-year ETRs over a rolling window of ±2 years with _etr_construction.compute_partner_year_etrs, on
# the positive-profit sub-group panel (config.ETR_PROFIT_SUBGROUP). They are the domestic, foreign and average ETRs on
# reported and on corrected profit, and the median, 25th percentile, 10th percentile and minimum over parents and the
# pair-specific ETR on corrected profit. I fill the gaps in 6.2, once the CIT rates are merged.

def main_etrs(file, grouping_name=ETR_PROFIT_SUBGROUP):
    """Compute partner-year ETRs (domestic, foreign, average) over a rolling
    5-year window, for both reported profit and corrected profit.

    This is a thin wrapper around compute_partner_year_etrs in _etr_construction.py.
    I call it twice (uncorrected and corrected) and merge the results, so that the
    output columns carry the names of the cleaning stage (etr_domestic, etr_foreign,
    etr_average, etr_domestic_corrected, etr_foreign_corrected,
    etr_average_corrected).
    """
    partner_uncorrected, _ = compute_partner_year_etrs(
        file,
        profit_col="profit_loss_before_income_tax",
        tax_col="income_tax_paid_on_cash_basis",
        suffix=None,
        grouping_col="grouping",
        grouping_value=grouping_name,
        window=2,
        pair_stats=False,
    )
    partner_corrected, _ = compute_partner_year_etrs(
        file,
        profit_col="profit_loss_before_income_tax_corrected",
        tax_col="income_tax_paid_on_cash_basis",
        suffix="corrected",
        grouping_col="grouping",
        grouping_value=grouping_name,
        window=2,
        pair_stats=False,
    )

    merged = partner_uncorrected.merge(
        partner_corrected, on=["iso_partner", "year"], how="outer"
    )
    return merged

def alternative_corrected_etrs(file, grouping_name=ETR_PROFIT_SUBGROUP):
    """Compute the pair-specific corrected ETR and the partner-level median, 25th
    percentile, 10th percentile and minimum over the rolling window. This is a thin
    wrapper around compute_partner_year_etrs.

    It returns (pair_year_df, partner_year_df).
    """
    partner_year, pair_year = compute_partner_year_etrs(
        file,
        profit_col="profit_loss_before_income_tax_corrected",
        tax_col="income_tax_paid_on_cash_basis",
        suffix="corrected",
        grouping_col="grouping",
        grouping_value=grouping_name,
        window=2,
        pair_stats=True,
    )

    partner_stats_only = partner_year[
        [
            "iso_partner",
            "year",
            "etr_partner_median_corrected",
            "etr_partner_p25_corrected",
            "etr_partner_p10_corrected",
            "etr_partner_min_corrected",
        ]
    ].copy()

    return pair_year, partner_stats_only

# Main rolling-window ETRs
etrs = main_etrs(cbcr, grouping_name=ETR_PROFIT_SUBGROUP)

for year in etrs["year"].unique():
    num_partners = etrs[etrs["year"] == year].shape[0]
    print(
        f"Calculated main rolling-window ETRs for year {year} "
        f"({ETR_PROFIT_SUBGROUP}). Number of partners: {num_partners}"
    )

# Reporting countries without a positive-profit sub-group entry get a domestic fallback from the Total panel.
reporting_countries_with_no_positive_profits = set(
    cbcr.loc[
        (cbcr["iso_parent"] == cbcr["iso_partner"])
        & (cbcr["grouping"] == "Total (All sub-groups)"),
        "iso_parent",
    ]
) - set(
    cbcr.loc[
        (cbcr["iso_parent"] == cbcr["iso_partner"])
        & (cbcr["grouping"] == ETR_PROFIT_SUBGROUP),
        "iso_parent",
    ]
)

cbcr_countries_no_positive_profits = cbcr[
    (cbcr["iso_parent"].isin(reporting_countries_with_no_positive_profits))
    & (cbcr["iso_parent"] == cbcr["iso_partner"])
].copy()

etrs_no_positive_profits = main_etrs(
    cbcr_countries_no_positive_profits,
    grouping_name="Total (All sub-groups)",
)

for year in etrs_no_positive_profits["year"].unique():
    num_partners = etrs_no_positive_profits[
        etrs_no_positive_profits["year"] == year
    ].shape[0]
    print(
        f"Calculated domestic fallback ETRs for year {year} "
        f"(Total - All sub-groups). Number of partners: {num_partners}"
    )

merged_df = etrs.merge(
    etrs_no_positive_profits[
        ["iso_partner", "year", "etr_domestic", "etr_domestic_corrected"]
    ],
    on=["iso_partner", "year"],
    how="left",
    suffixes=("", "_update"),
)

merged_df["etr_domestic"] = merged_df["etr_domestic"].combine_first(
    merged_df["etr_domestic_update"]
)
merged_df["etr_domestic_corrected"] = merged_df["etr_domestic_corrected"].combine_first(
    merged_df["etr_domestic_corrected_update"]
)

etrs = merged_df.drop(columns=["etr_domestic_update", "etr_domestic_corrected_update"])

updated_entries = (
    merged_df[["etr_domestic", "etr_domestic_corrected"]].notna().sum().sum()
)
print(
    f"Updated {updated_entries} entries for domestic ETRs based on "
    f"'Total (All sub-groups)' data."
)

# Additional rolling-window corrected ETRs
pair_etrs_corrected, partner_etrs_corrected = alternative_corrected_etrs(
    cbcr,
    grouping_name=ETR_PROFIT_SUBGROUP,
)

print(
    "Calculated additional corrected rolling-window ETRs: "
    "pair-specific, median, p25, and minimum."
)

check_duplicates(etrs, "ETRs", subset=["iso_partner", "year"])

check_missing_values(
    etrs,
    [
        "iso_partner",
        "year",
        "etr_domestic",
        "etr_foreign",
        "etr_average",
        "etr_average_corrected",
    ],
)

cbcr_etrs = cbcr.merge(etrs, on=["iso_partner", "year"], how="left")

cbcr_etrs = cbcr_etrs.merge(
    partner_etrs_corrected,
    on=["iso_partner", "year"],
    how="left",
)

cbcr_etrs = cbcr_etrs.merge(
    pair_etrs_corrected,
    on=["iso_parent", "iso_partner", "year"],
    how="left",
)

alternative_etr_cols = [
    "etr_parent_partner_corrected",
    "etr_partner_median_corrected",
    "etr_partner_p25_corrected",
    "etr_partner_p10_corrected",
    "etr_partner_min_corrected",
]

for col in alternative_etr_cols:
    if col in cbcr_etrs.columns:
        cbcr_etrs[col] = cbcr_etrs[col].clip(lower=0, upper=1)

check_missing_values(
    cbcr_etrs,
    [
        "etr_domestic",
        "etr_foreign",
        "etr_average",
        "etr_average_corrected",
        "etr_parent_partner_corrected",
        "etr_partner_median_corrected",
        "etr_partner_p25_corrected",
        "etr_partner_p10_corrected",
        "etr_partner_min_corrected",
    ],
)

num_missing_domestic = cbcr_etrs["etr_domestic"].isna().sum()
num_missing_foreign = cbcr_etrs["etr_foreign"].isna().sum()
num_missing_average = cbcr_etrs["etr_average"].isna().sum()
num_missing_average_corrected = cbcr_etrs["etr_average_corrected"].isna().sum()
total_rows = cbcr_etrs.shape[0]

missing_percentage_domestic = (num_missing_domestic / total_rows) * 100
missing_percentage_foreign = (num_missing_foreign / total_rows) * 100
missing_percentage_average = (num_missing_average / total_rows) * 100
missing_percentage_average_corrected = (
    num_missing_average_corrected / total_rows
) * 100

print(
    f"Percentage of rows with missing domestic ETRs: {missing_percentage_domestic:.2f}%. "
    "There can be several missing values as we can only calculate domestic ETRs for reporting jurisdictions."
)
print(
    f"Percentage of rows with missing foreign ETRs: {missing_percentage_foreign:.2f}%"
)
print(
    f"Percentage of rows with missing average ETRs: {missing_percentage_average:.2f}%"
)
print(
    f"Percentage of rows with missing average corrected ETRs before CIT fallback: "
    f"{missing_percentage_average_corrected:.2f}%"
)

# %% MARK: 6. Other variables
# I merge the jurisdiction-year variables onto the panel (CIT rates, GDP, population, wages, regions, income groups)
# and write the low-tax destination sets based on the IRS data to their own files for the variants of script 5.

# %% MARK: 6.1 Manual values and the country-year grid
# The hand-collected values (GDP, population and wages for small territories such as San Marino, the French overseas
# departments, Taiwan, the Pacific islands and the Channel Islands, and the flat CIT overrides) are not written into
# this script. I store each value, together with its source URL and a note, in one hand-maintained file:
#   data/raw/macro_variables/manual_imputation_values.csv
#     (columns: iso_partner, year, variable, value, mode, source_url, note).
# This script only reads that file (load_manual_imputation_values / apply_manual_values) and applies each value by
# its mode: fill_if_missing writes only where the cell is missing, override writes unconditionally. To add or revise
# a value or its source, edit the CSV, not the code. The source URLs stay in the CSV and are not carried into the
# output dataset.

def load_manual_imputation_values():
    """Load the curated manual values for macro variables, CIT rates and wages.

    The file is the single source of the hand-maintained values that this script applies
    (GDP and population of small territories, the flat CIT overrides and the hand-collected
    wages). It is ``data/raw/macro_variables/manual_imputation_values.csv``, with the columns
    ``iso_partner, year, variable, value, mode, source_url, note``.
    """
    manual = pd.read_csv(f"{data_raw}macro_variables/manual_imputation_values.csv")
    manual["year"] = pd.to_numeric(manual["year"], errors="coerce")
    return manual

def apply_manual_values(df, manual, variables):
    """Apply the curated manual values for ``variables`` to ``df`` (in place).

    Each manual row sets ``df[variable]`` for the matching ``iso_partner`` and, if one is
    given, ``year``. A blank year applies to every row of that jurisdiction.
    ``mode == "fill_if_missing"`` only writes where the cell is currently NaN, and
    ``mode == "override"`` writes unconditionally. I skip rows whose target column is
    absent from ``df``.
    """
    sub = manual[manual["variable"].isin(variables)]
    for _, row in sub.iterrows():
        column = row["variable"]
        if column not in df.columns:
            continue
        mask = df["iso_partner"] == row["iso_partner"]
        if pd.notna(row["year"]):
            mask &= df["year"] == int(row["year"])
        if row["mode"] == "fill_if_missing":
            mask &= df[column].isna()
        df.loc[mask, column] = float(row["value"])


MANUAL_VALUES = load_manual_imputation_values()

# This is the country-year grid (every partner code × analysis year) on which I complete the auxiliary data.
sample_jur_year = [(jur, year) for jur in partner_countries for year in analysis_years]

# %% MARK: 6.2 Corporate income tax rates
# Statutory combined CIT rates: I take the OECD's rates, the Tax Foundation's where the OECD has none, and then
# derived and manual values. fill_missing_cit_and_corrected_etrs fills the remaining gaps and also completes the
# corrected ETRs.

cits_oecd_raw = pd.read_csv(cit_data_oecd)
columns_cit_data = ["REF_AREA", "Measure", "Targeting", "TIME_PERIOD", "OBS_VALUE"]
cits_oecd_raw = cits_oecd_raw[columns_cit_data].copy()

cits_oecd = (
    cits_oecd_raw[
        (cits_oecd_raw["Measure"] == "Combined corporate income tax rate")
        & (cits_oecd_raw["Targeting"] == "Statutory")
        & (cits_oecd_raw["TIME_PERIOD"] >= first_year)
        & (cits_oecd_raw["TIME_PERIOD"] < first_year + n_years)
    ]
    .rename(
        columns={"REF_AREA": "iso_partner", "TIME_PERIOD": "year", "OBS_VALUE": "cit"}
    )
    .drop(columns=["Measure", "Targeting"])
    .copy()
)

cits_oecd["cit"] = cits_oecd["cit"] / 100

cits_wide_tf = pd.read_excel(cit_data_taxfoundation)
columns_cit_data_tf = ["iso_3"] + analysis_years
cits_wide_tf = cits_wide_tf[columns_cit_data_tf].copy()

cits_tf = cits_wide_tf.melt(
    id_vars=["iso_3"],
    value_vars=analysis_years,
    var_name="year",
    value_name="cit",
)
cits_tf.rename(columns={"iso_3": "iso_partner"}, inplace=True)
cits_tf["cit"] = cits_tf["cit"] / 100

cits = pd.merge(
    cits_oecd,
    cits_tf,
    on=["iso_partner", "year"],
    how="outer",
    suffixes=("_cits", "_cits_tf"),
)
cits["cit"] = cits["cit_cits"].combine_first(cits["cit_cits_tf"])
cits = cits[["iso_partner", "year", "cit"]].drop_duplicates().reset_index(drop=True)

for year in cits["year"].unique():
    fra_cit = cits.loc[
        (cits["iso_partner"] == "FRA") & (cits["year"] == year), "cit"
    ].values[0]
    cits.loc[(cits["iso_partner"] == "MTQ") & (cits["year"] == year), "cit"] = fra_cit
    if not ((cits["iso_partner"] == "MTQ") & (cits["year"] == year)).any():
        cits = pd.concat(
            [
                cits,
                pd.DataFrame(
                    {"iso_partner": ["MTQ"], "year": [year], "cit": [fra_cit]}
                ),
            ],
            ignore_index=True,
        )

    nor_cit = cits.loc[
        (cits["iso_partner"] == "NOR") & (cits["year"] == year), "cit"
    ].values[0]
    cits.loc[(cits["iso_partner"] == "BVT") & (cits["year"] == year), "cit"] = nor_cit
    if not ((cits["iso_partner"] == "BVT") & (cits["year"] == year)).any():
        cits = pd.concat(
            [
                cits,
                pd.DataFrame(
                    {"iso_partner": ["BVT"], "year": [year], "cit": [nor_cit]}
                ),
            ],
            ignore_index=True,
        )

missing_cits = [
    {"iso_partner": jur, "year": year}
    for jur, year in sample_jur_year
    if not ((cits["iso_partner"] == jur) & (cits["year"] == year)).any()
]
cits = pd.concat([cits, pd.DataFrame(missing_cits)], ignore_index=True)

# Malta refunds 6/7 of the tax to the shareholders, which leaves an effective rate of 1/7 of the headline rate.
# This is a derived (multiplicative) adjustment, so I apply it in code. The rates of Martinique (MTQ, copied from
# FRA) and of Bouvet Island (BVT, copied from NOR) above are derived in the same way. The flat and fill-if-missing
# CIT overrides (GIB, MCO, AND, CAF, ..., SMR) are in data/raw/macro_variables/manual_imputation_values.csv.
cits.loc[cits["iso_partner"] == "MLT", "cit"] *= 1 / 7
apply_manual_values(cits, MANUAL_VALUES, ["cit"])

cbcr_etrs_cits = cbcr_etrs.merge(cits, on=["iso_partner", "year"], how="left")

missing_cit_rows = cbcr_etrs_cits[
    (cbcr_etrs_cits["cit"].isnull())
    & (~cbcr_etrs_cits["iso_partner"].isin(non_countries))
]

if not missing_cit_rows.empty:
    missing_iso_partners_cit = missing_cit_rows[
        ["iso_partner", "year"]
    ].drop_duplicates()
    print(
        "Warning: CIT values are missing for the following iso_partner countries and years "
        "(excluding specified groups) before fallback:"
    )
    for _, row in missing_iso_partners_cit.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing CIT values found before fallback.")


def fill_missing_cit_and_corrected_etrs(df):
    """
    Fill the remaining gaps once the CIT rates are merged.

    1. I complete the CIT rates first. I fill them with the country's mean CIT across
       years, then with the corrected partner-level ETR columns and finally with the
       global median CIT.
    2. I then complete the corrected ETRs. I fill the partner-year ETRs with the
       country's mean over the years and then with the CIT rate. I fill the
       pair-specific ETR with the pair's mean over the years, then with the partner's
       mean and then with the CIT rate.

    Aggregate partner rows stay untouched.
    """
    df = df.copy()

    corrected_partner_cols = [
        "etr_domestic_corrected",
        "etr_foreign_corrected",
        "etr_average_corrected",
        "etr_partner_median_corrected",
        "etr_partner_p25_corrected",
        "etr_partner_p10_corrected",
        "etr_partner_min_corrected",
    ]
    pair_specific_col = "etr_parent_partner_corrected"

    real_mask = ~df["iso_partner"].isin(non_countries)
    real = df.loc[real_mask].copy()

    # I complete the CIT rates first.
    real["cit"] = pd.to_numeric(real["cit"], errors="coerce").clip(lower=0, upper=1)

    cit_missing_before = real["cit"].isna().sum()

    mean_cit_by_country = real.groupby("iso_partner")["cit"].transform("mean")
    real["cit"] = real["cit"].fillna(mean_cit_by_country)

    # The CIT rate is an attribute of the jurisdiction, so its fallbacks are partner-level rates only, the average
    # first. I deliberately do not use the pair-specific ETR as a fallback. It varies across parents, so it could give
    # the same partner-year different `cit` values on different rows.
    cit_backup_cols = [
        "etr_average_corrected",
        "etr_partner_median_corrected",
        "etr_partner_p25_corrected",
        "etr_partner_p10_corrected",
        "etr_partner_min_corrected",
    ]

    for col in cit_backup_cols:
        if col in real.columns:
            real["cit"] = real["cit"].fillna(real[col])

    global_median_cit = real["cit"].median(skipna=True)
    real["cit"] = real["cit"].fillna(global_median_cit).clip(lower=0, upper=1)

    cit_missing_after = real["cit"].isna().sum()

    print(f"CIT missing before fallback: {cit_missing_before}")
    print(f"CIT missing after fallback: {cit_missing_after}")

    # I fill the pair-specific corrected ETR.
    if pair_specific_col in real.columns:
        real[pair_specific_col] = pd.to_numeric(
            real[pair_specific_col], errors="coerce"
        )

        missing_before = real[pair_specific_col].isna().sum()

        pair_mean = real.groupby(["iso_parent", "iso_partner"])[
            pair_specific_col
        ].transform("mean")
        partner_mean = real.groupby("iso_partner")[pair_specific_col].transform("mean")

        real[pair_specific_col] = real[pair_specific_col].fillna(pair_mean)
        real[pair_specific_col] = real[pair_specific_col].fillna(partner_mean)
        real[pair_specific_col] = real[pair_specific_col].fillna(real["cit"])
        real[pair_specific_col] = real[pair_specific_col].clip(lower=0, upper=1)

        missing_after = real[pair_specific_col].isna().sum()
        print(
            f"{pair_specific_col}: filled {missing_before - missing_after} missing values; remaining missing {missing_after}"
        )

    # I fill the partner-level corrected ETRs.
    for col in corrected_partner_cols:
        if col not in real.columns:
            continue

        real[col] = pd.to_numeric(real[col], errors="coerce")
        missing_before = real[col].isna().sum()

        partner_mean = real.groupby("iso_partner")[col].transform("mean")

        real[col] = real[col].fillna(partner_mean)
        real[col] = real[col].fillna(real["cit"])
        real[col] = real[col].clip(lower=0, upper=1)

        missing_after = real[col].isna().sum()
        print(
            f"{col}: filled {missing_before - missing_after} missing values; remaining missing {missing_after}"
        )

    fill_cols = ["cit"] + [c for c in corrected_partner_cols if c in real.columns]
    if pair_specific_col in real.columns:
        fill_cols.append(pair_specific_col)

    df.loc[real_mask, fill_cols] = real[fill_cols]

    return df


cbcr_etrs_cits = fill_missing_cit_and_corrected_etrs(cbcr_etrs_cits)

missing_cit_rows_after = cbcr_etrs_cits[
    (cbcr_etrs_cits["cit"].isnull())
    & (~cbcr_etrs_cits["iso_partner"].isin(non_countries))
]

if not missing_cit_rows_after.empty:
    missing_iso_partners_cit_after = missing_cit_rows_after[
        ["iso_partner", "year"]
    ].drop_duplicates()
    print(
        "Warning: CIT values are still missing after fallback for the following "
        "iso_partner countries and years:"
    )
    for _, row in missing_iso_partners_cit_after.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing CIT values found after fallback.")

check_missing_values(
    cbcr_etrs_cits,
    [
        "cit",
        "etr_domestic_corrected",
        "etr_foreign_corrected",
        "etr_average_corrected",
        "etr_parent_partner_corrected",
        "etr_partner_median_corrected",
        "etr_partner_p25_corrected",
        "etr_partner_p10_corrected",
        "etr_partner_min_corrected",
    ],
)

# %% MARK: 6.3 GDP and population

gdp_population_long = pd.read_csv(gdp_population_data)

formatted_years = [f"{year} [YR{year}]" for year in analysis_years]
columns_gdp_population_data = ["Series Name", "Country Code"] + formatted_years
gdp_population_long = gdp_population_long[columns_gdp_population_data].copy()

gdp_population_long = gdp_population_long.melt(
    id_vars=["Country Code", "Series Name"],
    value_vars=formatted_years,
    var_name="Year",
    value_name="Value",
)

gdp_population = gdp_population_long.pivot_table(
    index=["Country Code", "Year"],
    columns="Series Name",
    values="Value",
    aggfunc="first",
).reset_index()

pop_col = (
    "Population, total"
    if "Population, total" in gdp_population.columns
    else "Population total"
)

# I use only the population series of this DataBank export. GDP comes exclusively from the World Bank snapshot merged
# below. That snapshot covers every country-year that the export's GDP series covers, so nothing is lost by ignoring
# the export's GDP.
gdp_population = gdp_population.rename(
    columns={
        "Country Code": "iso_partner",
        "Year": "year",
        pop_col: "population",
    }
)

gdp_population["year"] = gdp_population["year"].str.extract(r"(\d{4})").astype(int)

missing_markers = ["..", "...", "......", "—"]
gdp_population["population"] = pd.to_numeric(
    gdp_population["population"].replace(missing_markers, np.nan),
    errors="coerce",
)

gdp_population = gdp_population[["iso_partner", "year", "population"]].copy()

missing_population = gdp_population["population"].isna().sum()
print(f"Missing population values: {missing_population}")
print("iso_partner with missing population values:")
print(gdp_population.loc[gdp_population["population"].isna(), "iso_partner"].unique())

sample_jur_year_df = pd.DataFrame(
    sample_jur_year, columns=["iso_partner", "year"]
).drop_duplicates()
gdp_population = sample_jur_year_df.merge(
    gdp_population, on=["iso_partner", "year"], how="left"
)

# GDP: one World Bank snapshot (config.canonical_gdp_data, series NY.GDP.MKTP.CD) is the single GDP source of the
# repository (the extractive pipeline reads the same file). I merge it after the grid expansion, so that every sample
# jurisdiction-year receives a row even if it is absent from the population export (for example the Bahamas). The
# manual fills below cover the small territories that the World Bank does not publish.
_canon_gdp = pd.read_csv(canonical_gdp_data, comment="#").rename(
    columns={"iso3": "iso_partner"}
)
gdp_population = gdp_population.merge(
    _canon_gdp[["iso_partner", "year", "gdp_current_usd"]],
    on=["iso_partner", "year"],
    how="left",
)

kosovo_code = "XKX" if "XKX" in gdp_population["iso_partner"].unique() else "XKV"

# Manual GDP and population fills: the curated values and their source URLs are in
# data/raw/macro_variables/manual_imputation_values.csv (see 6.1). They only fill missing values, so they only reach
# the small territories that the World Bank data lack.
apply_manual_values(gdp_population, MANUAL_VALUES, ["gdp_current_usd", "population"])

# The final panel year often lacks World Bank values at download time, so I fill it from the preceding year.
for col in ["gdp_current_usd", "population"]:
    values_prev = gdp_population.loc[
        gdp_population["year"] == last_year - 1, ["iso_partner", col]
    ].rename(columns={col: f"{col}_prev"})
    gdp_population = gdp_population.merge(values_prev, on="iso_partner", how="left")

    mask_last_missing = (gdp_population["year"] == last_year) & (
        gdp_population[col].isna()
    )
    gdp_population.loc[mask_last_missing, col] = gdp_population.loc[
        mask_last_missing, f"{col}_prev"
    ]

    gdp_population = gdp_population.drop(columns=[f"{col}_prev"])

avg_gdp = gdp_population.groupby("iso_partner")["gdp_current_usd"].transform("mean")
gdp_population["gdp_current_usd"] = gdp_population["gdp_current_usd"].fillna(avg_gdp)

avg_pop = gdp_population.groupby("iso_partner")["population"].transform("mean")
gdp_population["population"] = gdp_population["population"].fillna(avg_pop)

cbcr_etrs_cits_gdp = cbcr_etrs_cits.merge(
    gdp_population,
    on=["iso_partner", "year"],
    how="left",
)

missing_gdp_rows = cbcr_etrs_cits_gdp[
    (cbcr_etrs_cits_gdp["gdp_current_usd"].isnull())
    & (~cbcr_etrs_cits_gdp["iso_partner"].isin(non_countries))
]
missing_population_rows = cbcr_etrs_cits_gdp[
    (cbcr_etrs_cits_gdp["population"].isnull())
    & (~cbcr_etrs_cits_gdp["iso_partner"].isin(non_countries))
]

if not missing_gdp_rows.empty:
    missing_iso_partners_gdp = missing_gdp_rows[
        ["iso_partner", "year"]
    ].drop_duplicates()
    print("Warning: GDP is missing for the following iso_partner countries and years:")
    for _, row in missing_iso_partners_gdp.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing GDP values found.")

if not missing_population_rows.empty:
    missing_iso_partners_population = missing_population_rows[
        ["iso_partner", "year"]
    ].drop_duplicates()
    print(
        "Warning: Population is missing for the following iso_partner countries and years:"
    )
    for _, row in missing_iso_partners_population.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing population values found.")

# %% MARK: 6.4 Wages from the ILO data
# Average monthly earnings in US$ from the International Labour Organization (ILO). I extrapolate missing
# country-years from the local-currency observations with consumer price indices (CPI) and exchange rates, and then
# fill them with the country mean and the hand-collected values (6.1).

wages_fulltable = pd.read_csv(wage_data)

if "sex" in wages_fulltable.columns:
    both_sexes = wages_fulltable["sex"] == "SEX_T"
    all_occupations = wages_fulltable["classif1"] == "ECO_SECTOR_TOTAL"
    in_usd = wages_fulltable["classif2"] == "CUR_TYPE_USD"
    relevant_years = (wages_fulltable["time"] >= first_year) & (
        wages_fulltable["time"] <= last_year
    )
    relevant_rows = both_sexes & all_occupations & in_usd & relevant_years

    wages = wages_fulltable.loc[
        relevant_rows, ["ref_area", "time", "obs_value"]
    ].reset_index(drop=True)
    wages.rename(
        columns={
            "ref_area": "iso_partner",
            "time": "year",
            "obs_value": "wage_monthly",
        },
        inplace=True,
    )

else:
    import pycountry

    both_sexes = wages_fulltable["sex.label"] == "Total"
    in_usd = wages_fulltable["classif1.label"] == "Currency: U.S. dollars"
    relevant_years = (wages_fulltable["time"] >= first_year) & (
        wages_fulltable["time"] <= last_year
    )
    relevant_rows = both_sexes & in_usd & relevant_years

    wages = wages_fulltable.loc[
        relevant_rows, ["ref_area.label", "time", "obs_value"]
    ].reset_index(drop=True)
    wages.rename(
        columns={
            "ref_area.label": "country_name",
            "time": "year",
            "obs_value": "wage_monthly",
        },
        inplace=True,
    )

    manual_map = {
        "Bolivia (Plurinational State of)": "BOL",
        "Congo, Democratic Republic of the": "COD",
        "Hong Kong, China": "HKG",
        "Republic of Korea": "KOR",
        "Kosovo": kosovo_code,
        "Macao, China": "MAC",
    }

    def name_to_iso3(name):
        if name in manual_map:
            return manual_map[name]
        try:
            return pycountry.countries.lookup(name).alpha_3
        except Exception:
            return None

    wages["iso_partner"] = wages["country_name"].map(name_to_iso3)
    unmapped = wages[wages["iso_partner"].isna()]["country_name"].unique()
    if len(unmapped) > 0:
        print(
            f"Warning: Could not map {len(unmapped)} country names to ISO3: {unmapped}"
        )

    wages = wages.dropna(subset=["iso_partner"])
    wages = wages[["iso_partner", "year", "wage_monthly"]].copy()

missing_wages = []
for jur, year in sample_jur_year:
    if not ((wages["iso_partner"] == jur) & (wages["year"] == year)).any():
        missing_wages.append({"iso_partner": jur, "year": year})

wages = pd.concat([wages, pd.DataFrame(missing_wages)], ignore_index=True)

# Outlier filter on the ILO observations in US$.
#
# Some ILO survey years are wildly inconsistent with the rest of the country's series. Liberia's labour force survey
# (LFS) of 2017 reports $1,309 a month, against $95–122 in the household income and expenditure surveys (HIES), and
# real formal-sector wages in Liberia are about $100–200. The LFS row also lists the "Local currency" value as the
# same 1,308.61. This is an artefact of the two currencies in use: Liberian respondents reported in US$, but the
# values were tagged as "Local currency". Without the filter, the outlier anchors the CPI extrapolation and corrupts
# every later year for that country.
#
# The rule: per country, I drop the observations whose US$ value is more than 3 times or less than 1/3 of the
# country's median US$ value across all available ILO years (not just the panel years), so that countries with only
# one or two observations in the panel years still get a robust median.
if "country_name" in wages.columns or "iso_partner" in wages.columns:
    # I compute the country median from the full ILO history in US$ (all years).
    if "sex" in wages_fulltable.columns:
        all_usd = wages_fulltable.loc[
            both_sexes & all_occupations & in_usd, ["ref_area", "obs_value"]
        ].rename(columns={"ref_area": "iso_partner", "obs_value": "w"})
    else:
        all_usd = wages_fulltable.loc[
            (wages_fulltable["sex.label"] == "Total")
            & (wages_fulltable["classif1.label"] == "Currency: U.S. dollars"),
            ["ref_area.label", "obs_value"],
        ].rename(columns={"ref_area.label": "country_name", "obs_value": "w"})
        all_usd["iso_partner"] = all_usd["country_name"].map(name_to_iso3)
        all_usd = all_usd.dropna(subset=["iso_partner"])[["iso_partner", "w"]]
    country_med_full = all_usd.groupby("iso_partner")["w"].median()
    country_med = wages["iso_partner"].map(country_med_full)
    outliers = (
        country_med.notna()
        & (country_med > 0)
        & wages["wage_monthly"].notna()
        & (
            (wages["wage_monthly"] > 3.0 * country_med)
            | (wages["wage_monthly"] < (1.0 / 3.0) * country_med)
        )
    )
    if outliers.any():
        n_drops = int(outliers.sum())
        countries_affected = wages.loc[outliers, "iso_partner"].unique().tolist()
        print(
            f"Wage outlier filter dropped {n_drops} observations "
            f"in {len(countries_affected)} countries: {sorted(countries_affected)}"
        )
        wages.loc[outliers, "wage_monthly"] = np.nan
        # I leave these rows with wage_monthly = NaN, so that the CPI extrapolation below treats them as missing and
        # imputes them again from clean local-currency anchors.


# Extrapolation of the ILO observations across missing panel years with consumer price indices.
#
# Many countries in the panel (especially lower-middle-income and low-income countries) have only one or two ILO
# survey observations in the analysis window. Filling the missing years with the country mean would keep
# wage_monthly constant across years for those countries and hide wage growth and the effects of high inflation.
# Instead, I anchor on each country's local-currency wage observations from the ILO file, scale them to the other
# panel years with the national CPI and convert them to US$ at each year's exchange rate.
#
#     wage_USD[year] = wage_LCY[obs_year]
#                      × CPI[year] / CPI[obs_year]
#                      / exchange_rate[year]
#
# When there are several local-currency observations, I anchor each target year on the closest one. Countries
# without a local-currency observation skip this step and fall through to the prediction from GDP and population
# in 6.5.

# I take the local-currency wage observations from the same ILO survey rows.
if "sex" in wages_fulltable.columns:
    in_lcy = wages_fulltable["classif2"] == "CUR_TYPE_LCU"
    lcy_relevant = (
        both_sexes
        & all_occupations
        & in_lcy
        & (
            (wages_fulltable["time"] >= first_year)
            & (wages_fulltable["time"] <= last_year)
        )
    )
    wages_lcy = wages_fulltable.loc[
        lcy_relevant, ["ref_area", "time", "obs_value"]
    ].rename(
        columns={
            "ref_area": "iso_partner",
            "time": "year",
            "obs_value": "wage_monthly_lcy",
        }
    )
else:
    in_lcy = wages_fulltable["classif1.label"] == "Currency: Local currency"
    lcy_relevant = (
        both_sexes
        & in_lcy
        & (
            (wages_fulltable["time"] >= first_year)
            & (wages_fulltable["time"] <= last_year)
        )
    )
    wages_lcy = wages_fulltable.loc[
        lcy_relevant, ["ref_area.label", "time", "obs_value"]
    ].rename(
        columns={
            "ref_area.label": "country_name",
            "time": "year",
            "obs_value": "wage_monthly_lcy",
        }
    )
    wages_lcy["iso_partner"] = wages_lcy["country_name"].map(name_to_iso3)
    wages_lcy = wages_lcy.dropna(subset=["iso_partner"])
    wages_lcy = wages_lcy[["iso_partner", "year", "wage_monthly_lcy"]]

# I apply the same per-country outlier filter to the local-currency observations. In dual-currency countries (Liberia,
# Ecuador, Panama), some surveys report wages in US$ but tag them as "Local currency". Those values are far below the
# proper local-currency scale, so the floor at 1/3 of the median catches and drops them.
if not wages_lcy.empty:
    lcy_med = wages_lcy.groupby("iso_partner")["wage_monthly_lcy"].transform("median")
    lcy_outliers = (
        lcy_med.notna()
        & (lcy_med > 0)
        & wages_lcy["wage_monthly_lcy"].notna()
        & (
            (wages_lcy["wage_monthly_lcy"] > 3.0 * lcy_med)
            | (wages_lcy["wage_monthly_lcy"] < (1.0 / 3.0) * lcy_med)
        )
    )
    if lcy_outliers.any():
        print(
            f"Local-currency outlier filter dropped {int(lcy_outliers.sum())} "
            f"ILO LCY observations (countries: "
            f"{sorted(wages_lcy.loc[lcy_outliers, 'iso_partner'].unique().tolist())})"
        )
        wages_lcy = wages_lcy[~lcy_outliers].reset_index(drop=True)


def _load_wb_long(path, value_name):
    """Read a World Development Indicators (WDI) CSV of the World Bank into long format.

    The files have four header rows and are wide, with one column per year from 1960 to 2025.
    """
    df = pd.read_csv(path, skiprows=4)
    year_cols = [c for c in df.columns if str(c).isdigit()]
    long = df.melt(
        id_vars=["Country Code"],
        value_vars=year_cols,
        var_name="year",
        value_name=value_name,
    )
    long["year"] = long["year"].astype(int)
    long = long.rename(columns={"Country Code": "iso_partner"})
    return long[["iso_partner", "year", value_name]].dropna(subset=[value_name])


cpi_long = _load_wb_long(cpi_data, "cpi")
fx_long = _load_wb_long(exchange_rates_wb, "fx_lcu_per_usd")

# For each (iso_partner, target_year) that needs a wage, I find the nearest local-currency observation, scale it by
# the CPI and divide it by the exchange rate to get US$.
sample_target = (
    wages[wages["wage_monthly"].isna()][["iso_partner", "year"]]
    .drop_duplicates()
    .reset_index(drop=True)
)


def _extrapolate_one(iso, target_year):
    obs = wages_lcy[wages_lcy["iso_partner"] == iso]
    if obs.empty:
        return np.nan
    # I pick the closest observation year.
    obs = obs.assign(distance=(obs["year"] - target_year).abs())
    nearest = obs.loc[obs["distance"].idxmin()]
    obs_year = int(nearest["year"])
    lcy_obs = float(nearest["wage_monthly_lcy"])

    cpi_target = cpi_long[
        (cpi_long["iso_partner"] == iso) & (cpi_long["year"] == target_year)
    ]
    cpi_obs = cpi_long[
        (cpi_long["iso_partner"] == iso) & (cpi_long["year"] == obs_year)
    ]
    fx_target = fx_long[
        (fx_long["iso_partner"] == iso) & (fx_long["year"] == target_year)
    ]
    if cpi_target.empty or cpi_obs.empty or fx_target.empty:
        return np.nan
    cpi_t = float(cpi_target.iloc[0]["cpi"])
    cpi_o = float(cpi_obs.iloc[0]["cpi"])
    fx_t = float(fx_target.iloc[0]["fx_lcu_per_usd"])
    if cpi_o <= 0 or fx_t <= 0:
        return np.nan
    return lcy_obs * (cpi_t / cpi_o) / fx_t


sample_target["wage_extrapolated"] = sample_target.apply(
    lambda r: _extrapolate_one(r["iso_partner"], int(r["year"])), axis=1
)

# Plausibility check on the extrapolated values. The extrapolation with CPI and exchange rates silently fails for
# countries whose currency was redenominated between the ILO observation year and the panel years. Sierra Leone, for
# example, redenominated at 1:1000 in 2022, so an ILO observation in old leones combined with a World Bank exchange
# rate in new leones gives a wage 1000 times too high. Without country-by-country overrides I cannot detect the
# redenomination directly, but I can detect implausible US$ results by comparing them with GDP per capita. A monthly
# wage cannot reasonably exceed annual GDP per capita.
#
# The rule: I reject an extrapolated wage above (GDP per capita) / 12 × 5. The cap of 5 times monthly GDP per capita
# is very generous, since in most countries the average monthly wage falls far below monthly GDP per capita.

# GDP per capita for the plausibility check.
gdp_pc = cbcr_etrs_cits_gdp.drop_duplicates(["iso_partner", "year"])[
    ["iso_partner", "year", "gdp_current_usd", "population"]
].copy()
gdp_pc["gdp_per_capita"] = gdp_pc["gdp_current_usd"] / gdp_pc["population"]
sample_target = sample_target.merge(
    gdp_pc[["iso_partner", "year", "gdp_per_capita"]],
    on=["iso_partner", "year"],
    how="left",
)
# The check has two sides:
#  (a) Upper: an extrapolated wage above 5 times monthly GDP per capita points to a redenomination (SLE, BDI and
#      others).
#  (b) Lower: if the country has ILO observations in US$ and the extrapolated wage is below 1/5 of the country's
#      median ILO wage in US$, the local-currency units are probably wrong (Iceland's "Local currency" values are in
#      unusual units).
country_usd_median_map = (
    all_usd.groupby("iso_partner")["w"].median() if "all_usd" in dir() else None
)
sample_target["country_usd_median"] = (
    sample_target["iso_partner"].map(country_usd_median_map)
    if country_usd_median_map is not None
    else np.nan
)
implausible_high = (
    sample_target["wage_extrapolated"].notna()
    & sample_target["gdp_per_capita"].notna()
    & (sample_target["gdp_per_capita"] > 0)
    & (
        sample_target["wage_extrapolated"]
        > 5.0 * sample_target["gdp_per_capita"] / 12.0
    )
)
implausible_low = (
    sample_target["wage_extrapolated"].notna()
    & sample_target["country_usd_median"].notna()
    & (sample_target["country_usd_median"] > 0)
    & (sample_target["wage_extrapolated"] < 0.2 * sample_target["country_usd_median"])
)
implausible = implausible_high | implausible_low
if implausible.any():
    rejected_iso = sample_target.loc[implausible, "iso_partner"].unique().tolist()
    n_high = int(implausible_high.sum())
    n_low = int(implausible_low.sum())
    print(
        f"Rejected {int(implausible.sum())} extrapolated wages "
        f"({n_high} too high vs GDP/cap, {n_low} too low vs ILO USD median). "
        f"Likely currency redenomination or LCY-unit mismatch. "
        f"Countries: {sorted(rejected_iso)}"
    )
    sample_target.loc[implausible, "wage_extrapolated"] = np.nan
sample_target = sample_target.drop(columns=["gdp_per_capita", "country_usd_median"])

# I merge the extrapolated values into the wages.
wages = wages.merge(
    sample_target.rename(columns={"wage_extrapolated": "_w_extrap"}),
    on=["iso_partner", "year"],
    how="left",
)
mask_fill = wages["wage_monthly"].isna() & wages["_w_extrap"].notna()
wages.loc[mask_fill, "wage_monthly"] = wages.loc[mask_fill, "_w_extrap"]
n_extrap = int(mask_fill.sum())
n_extrap_countries = wages.loc[mask_fill, "iso_partner"].nunique()
print(
    f"CPI-extrapolated wages: {n_extrap} (iso, year) cells across "
    f"{n_extrap_countries} countries."
)
wages = wages.drop(columns=["_w_extrap"])

# For any remaining gaps (for example countries without a local-currency observation or without CPI or exchange-rate
# coverage), I fall back to the country mean. The ordinary least squares (OLS) imputation in 6.5 handles the rows that
# are still NaN after this.
avg_wage = wages.groupby("iso_partner")["wage_monthly"].transform("mean")
wages["wage_monthly"] = wages["wage_monthly"].fillna(avg_wage)

# Hand-collected monthly wages for small territories missing from the ILO data. These are unconditional overrides. The
# values and their sources are in data/raw/macro_variables/manual_imputation_values.csv (see
# load_manual_imputation_values).
apply_manual_values(wages, MANUAL_VALUES, ["wage_monthly"])

cbcr_etrs_cits_gdp_wages = cbcr_etrs_cits_gdp.merge(
    wages,
    on=["iso_partner", "year"],
    how="left",
)

missing_wages_after_merge = cbcr_etrs_cits_gdp_wages[
    (cbcr_etrs_cits_gdp_wages["wage_monthly"].isna())
    & (~cbcr_etrs_cits_gdp_wages["iso_partner"].isin(non_countries))
]

if not missing_wages_after_merge.empty:
    missing_iso_partners_wages = missing_wages_after_merge[
        ["iso_partner", "year"]
    ].drop_duplicates()
    print(
        "Warning: The following years and countries have to be imputed in the next step:"
    )
    for _, row in missing_iso_partners_wages.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing wage data after the merge.")

# %% MARK: 6.5 Wages predicted from GDP and population, payroll
# For the remaining gaps, I regress the log wage on log GDP and log population. I leave the jurisdictions whose wage
# looks implausible against GDP per capita out of the estimation sample.

offsample_countries = []

for country, gdp_per_capita, wage in zip(
    cbcr_etrs_cits_gdp_wages["iso_partner"],
    cbcr_etrs_cits_gdp_wages["gdp_current_usd"]
    / cbcr_etrs_cits_gdp_wages["population"],
    cbcr_etrs_cits_gdp_wages["wage_monthly"],
):
    if pd.notna(gdp_per_capita) and pd.notna(wage) and gdp_per_capita > 0 and wage > 0:
        ratio = np.log(gdp_per_capita / 12 / wage)
        if (ratio > np.log2(1.5)) or (ratio < -2):
            offsample_countries.append(country)

offsample_countries = list(dict.fromkeys(offsample_countries))

ols_sample = cbcr_etrs_cits_gdp_wages[
    ~cbcr_etrs_cits_gdp_wages["iso_partner"].isin(offsample_countries)
].copy()

ols_sample = ols_sample.dropna(subset=["wage_monthly", "gdp_current_usd", "population"])
ols_sample = ols_sample[
    (ols_sample["wage_monthly"] > 0)
    & (ols_sample["gdp_current_usd"] > 0)
    & (ols_sample["population"] > 0)
].copy()

cbcr_etrs_cits_gdp_wages["pred_wage_monthly"] = np.nan

if not ols_sample.empty:
    ols_regression = smf.ols(
        formula="np.log(wage_monthly) ~ np.log(gdp_current_usd) + np.log(population)",
        data=ols_sample,
    )
    ols_fitted_values = ols_regression.fit()

    cbcr_etrs_cits_gdp_wages["pred_wage_monthly"] = np.exp(
        ols_fitted_values.predict(cbcr_etrs_cits_gdp_wages)
    )

cbcr_etrs_cits_gdp_wages.loc[
    cbcr_etrs_cits_gdp_wages["wage_monthly"].isna(), "wage_monthly"
] = cbcr_etrs_cits_gdp_wages.loc[
    cbcr_etrs_cits_gdp_wages["wage_monthly"].isna(), "pred_wage_monthly"
]

cbcr_etrs_cits_gdp_wages.drop(columns=["pred_wage_monthly"], inplace=True)

missing_after_imputation = cbcr_etrs_cits_gdp_wages[
    (cbcr_etrs_cits_gdp_wages["wage_monthly"].isna())
    & (~cbcr_etrs_cits_gdp_wages["iso_partner"].isin(non_countries))
].shape[0]
print(f"Missing wages after imputation: {missing_after_imputation}")

missing_wages_countries_years = cbcr_etrs_cits_gdp_wages[
    (cbcr_etrs_cits_gdp_wages["wage_monthly"].isna())
    & (~cbcr_etrs_cits_gdp_wages["iso_partner"].isin(non_countries))
][["iso_partner", "year"]].drop_duplicates()

for _, row in missing_wages_countries_years.iterrows():
    country = row["iso_partner"]
    year = row["year"]
    reasons = []

    if country in offsample_countries:
        reasons.append("wages flagged as implausible")

    country_year_slice = cbcr_etrs_cits_gdp_wages[
        (cbcr_etrs_cits_gdp_wages["iso_partner"] == country)
        & (cbcr_etrs_cits_gdp_wages["year"] == year)
    ]

    if country_year_slice["gdp_current_usd"].isna().any():
        reasons.append("missing GDP data")
    if country_year_slice["population"].isna().any():
        reasons.append("missing population data")

    reason_str = (
        ", ".join(reasons)
        if reasons
        else "no wage data available even after prediction"
    )
    print(f"Wages missing for {country} in year {year}: {reason_str}")

# Payroll is employees × monthly wage × 12.
cbcr_etrs_cits_gdp_wages["payroll"] = (
    cbcr_etrs_cits_gdp_wages["n_employees"]
    * cbcr_etrs_cits_gdp_wages["wage_monthly"]
    * 12
)

# I add log versions of the macro variables.
for col_name in ["wage_monthly", "gdp_current_usd", "population"]:
    cbcr_etrs_cits_gdp_wages[f"ln_{col_name}"] = np.log1p(
        cbcr_etrs_cits_gdp_wages[col_name].clip(lower=0)
    )

# %% MARK: 6.6 Regions and World Bank income groups

regions = pd.read_csv(
    unilateral_cross_data,
    usecols=[
        "iso3",
        "region_tjn",
        "ukt",
        "oecd_oct",
        "oecd",
        "eu28",
    ],
).dropna(subset=["iso3"])

regions.rename(columns={"iso3": "iso_partner"}, inplace=True)
regions.loc[regions["iso_partner"] == "XXK", "iso_partner"] = "XKV"

# World Bank income groups: I read them from a pinned snapshot in the repository, so that the cleaned dataset is
# reproducible offline and across the World Bank's yearly reclassifications in July. If the snapshot is absent, I
# fetch the groups from the API once and write the file. To refresh the groups deliberately, delete the file.
_wb_income_snapshot = _Path(data_raw) / "country_info" / "wb_income_groups_2026-07.csv"

if _wb_income_snapshot.exists():
    wb_income_base = pd.read_csv(_wb_income_snapshot)
    print(f"Read WB income-group snapshot: {_wb_income_snapshot}")
else:
    url = "https://api.worldbank.org/v2/country?format=json&per_page=400"

    try:
        wb_response = requests.get(url, timeout=30)
        wb_response.raise_for_status()
        wb_json = wb_response.json()

        if isinstance(wb_json, list) and len(wb_json) > 1 and wb_json[1] is not None:
            wb_raw = wb_json[1]
        else:
            wb_raw = []

    except Exception as exc:
        print(f"Warning: could not download World Bank income groups. {exc}")
        wb_raw = []

    wb_income_base = pd.DataFrame(
        [
            {
                "iso_partner": c["id"],
                "wb_income_group_official": c["incomeLevel"]["value"],
                "wb_income_group_id_official": c["incomeLevel"]["id"],
            }
            for c in wb_raw
            if c.get("region", {}).get("value") != "Aggregates"
            and c.get("id") is not None
            and len(c.get("id")) == 3
        ]
    )

    if wb_income_base.empty:
        wb_income_base = pd.DataFrame(
            columns=[
                "iso_partner",
                "wb_income_group_official",
                "wb_income_group_id_official",
            ]
        )
    else:
        wb_income_base["wb_income_group_official"] = wb_income_base[
            "wb_income_group_official"
        ].replace(
            {
                "Low income": "low_income",
                "Lower middle income": "lower_middle_income",
                "Upper middle income": "upper_middle_income",
                "High income": "high_income",
                "Not classified": pd.NA,
                "": pd.NA,
            }
        )
        wb_income_base["wb_income_group_id_official"] = wb_income_base[
            "wb_income_group_id_official"
        ].replace({"": pd.NA})
        wb_income_base.to_csv(_wb_income_snapshot, index=False)
        print(
            f"Saved WB income-group snapshot to {_wb_income_snapshot} — "
            "commit this file so the run is reproducible."
        )

# I expand the groups to the country-year grid.
wb_income = pd.DataFrame(
    sample_jur_year, columns=["iso_partner", "year"]
).drop_duplicates()

wb_income = wb_income.merge(
    wb_income_base,
    on="iso_partner",
    how="left",
)

# The analytical income group starts from the official World Bank group.
wb_income["wb_income_group"] = wb_income["wb_income_group_official"]
wb_income["wb_income_group_id"] = wb_income["wb_income_group_id_official"]

# Tax havens overwrite the World Bank group. The "tax_haven" income group is the representation haven list in config
# (TAX_HAVENS_REPRESENTATION), whose definition is documented there. Edit the list in config.py, not here.
tax_haven_codes = sorted(TAX_HAVENS_REPRESENTATION)

wb_income.loc[
    wb_income["iso_partner"].isin(tax_haven_codes),
    ["wb_income_group", "wb_income_group_id"],
] = ["tax_haven", "HVN"]

# Manual fills for countries and territories that the World Bank does not cover well.
manual_income_map = {
    # Not covered by the World Bank classification in every sample year
    "ETH": ("low_income", "LIC"),
    "VEN": ("upper_middle_income", "UMC"),
    "TWN": ("high_income", "HIC"),
    "XKV": ("lower_middle_income", "LMC"),
    # French overseas departments and territories
    "GLP": ("high_income", "HIC"),
    "GUF": ("high_income", "HIC"),
    "MTQ": ("high_income", "HIC"),
    "REU": ("high_income", "HIC"),
    "WLF": ("high_income", "HIC"),
    "BLM": ("high_income", "HIC"),   # Saint Barthélemy (French collectivity, partner from FY2023): no World Bank row
    # Other territories absent from the World Bank list
    "FLK": ("high_income", "HIC"),
    # Cook Islands: not classified by the World Bank, so I treat them as high income
    "COK": ("high_income", "HIC"),
}

for iso, (group, group_id) in manual_income_map.items():
    wb_income.loc[wb_income["iso_partner"] == iso, "wb_income_group"] = group
    wb_income.loc[wb_income["iso_partner"] == iso, "wb_income_group_id"] = group_id

# An optional version with three groups plus tax havens.
wb_income["wb_income_group_3"] = wb_income["wb_income_group"].replace(
    {
        "low_income": "low_income",
        "lower_middle_income": "middle_income",
        "upper_middle_income": "middle_income",
        "high_income": "high_income",
        "tax_haven": "tax_haven",
    }
)

# Final check: the remaining missing values among real countries only.
remaining_missing_wb = wb_income[
    (~wb_income["iso_partner"].isin(non_countries))
    & (wb_income["wb_income_group"].isna())
][["iso_partner", "year"]].drop_duplicates()

if not remaining_missing_wb.empty:
    print("Warning: wb_income_group still missing for:")
    print(
        remaining_missing_wb.sort_values(["iso_partner", "year"]).to_string(index=False)
    )
else:
    print("No missing wb_income_group values remain.")

print(
    wb_income.loc[
        wb_income["iso_partner"].isin(
            [
                "ETH",
                "VEN",
                "AIA",
                "COK",
                "GGY",
                "GLP",
                "GUF",
                "IOT",
                "JEY",
                "REU",
                "TWN",
                "WLF",
                "XKV",
                "MTQ",
                "FLK",
            ]
        ),
        [
            "iso_partner",
            "year",
            "wb_income_group",
            "wb_income_group_id",
            "wb_income_group_3",
        ],
    ]
    .drop_duplicates()
    .sort_values(["iso_partner", "year"])
    .to_string(index=False)
)

# %% MARK: 6.7 US groups' profit taxed below 15% (IRS)
# This section classifies every jurisdiction-year as a profit-shifting destination when more than half of the positive
# profit that US multinationals book there is taxed below 15%, according to IRS SOI CbCR Table 4 (Form 8975, by the
# effective tax rate of the multinational's sub-group, major region and selected jurisdiction). The sets restrict
# script 5 in the irs15_gate variants (config.DEST_GATES). Positive misalignment (profit booked above the allocation
# under unitary taxation) is kept only in qualifying destinations, and each parent's negative side is rescaled to
# match. The headline estimate does not use these files. It places no restriction on where profit can be shifted to.
#
# The share below 15% is (profit of the sub-groups with an ETR below 15% + profit of the sub-groups with positive
# profit and negative income tax accrued, that is an ETR below 0) ÷ profit of all positive-profit sub-groups. The ETR
# is income tax accrued (current year) ÷ profit before income tax, as the IRS defines it. I leave out the sub-groups
# with zero or negative profit, because they book no profit that could have been shifted into the jurisdiction.
#
# Disclosure gaps: Table 4 lists a jurisdiction in an ETR band only when enough groups sit there. Otherwise, its
# profit in that band is folded into "<region>, other countries", so a missing band is not zero. The denominator then
# comes from Table 1B (all positive-profit sub-groups of the jurisdiction), and the share is bounded. The lower bound
# is the listed low-band profit ÷ the total, and the upper bound is 1 − the listed high-band profit ÷ the total. When
# every band is listed, I measure the share exactly from Table 4.
#
# Year coverage of the 15% cut:
#   2019–2023  Table 4 splits at 15%.
#   2017–2018  Table 4 splits at 10% and 25% only, so the 10–25% band counts toward the upper bound only.
#   2016       No Table 4 was published, so I carry the 2017 classification back.
# Classification, shown for the > 50% rule (the ≥ 30% variant applies the same steps at its cut):
# a lower bound above 50% makes a destination, and an upper bound of 50% or less does not. When the bounds straddle
# the cut, I proceed as follows. In 2019–23 (disclosure gaps), I put the hidden profit in the low or the high band by
# its own rate (Table 1B tax − listed tax, over the hidden profit). In 2017–18 (the 10–25% band), the jurisdiction's
# nearest year with a determinate result decides (on a tie, the later year). A year in which a listed jurisdiction is
# not shown (or shows no positive profit) also takes its nearest determinate year. I classify the "United States"
# row (US groups' domestic sub-groups) like any other jurisdiction. Jurisdictions that the IRS never lists separately
# cannot be shown to qualify and are not destinations. The exceptions are the representation havens
# (config.TAX_HAVENS_REPRESENTATION), which qualify in every year and at every cut (method
# "never_listed_representation_haven"). The IRS pools them in the regional "other countries" rows, whose shares
# below 15% pass the cuts in most years.
#
# I also write the parsed Table 4 rows as one tidy file (irs_soi_cbcr_table4_long.csv) for the figure scripts.
#
# Tables (tax years). manifest.csv in the same folder gives the URL, retrieval date and SHA-256 hash of each file.
#   data/raw/tax_rates/irs_soi_cbcr_table4/<yy>it04cbc.xlsx  — Table 4, by sub-group ETR, 2017–2023
#   data/raw/tax_rates/irs_soi_cbcr_table4/<yy>it01bcbc.xlsx — Table 1B, positive-profit sub-groups, 2017–2023

IRS_TABLES_DIR = _Path(data_raw) / "tax_rates" / "irs_soi_cbcr_table4"
IRS_OUT_DIR = _Path(data_intermediate)
# Destination thresholds on the share of positive profit taxed below 15%, as tag: (cut, inclusive, output file).
# "gt50" is the main rule (more than half). ge30 is the sensitivity (at least 30%).
IRS_SHARE_CUTS = {
    "gt50": (0.5, False, "irs_low_tax_destinations.csv"),
    "ge30": (0.3, True, "irs_low_tax_destinations_ge30.csv"),
}
IRS_YEARS_TABLE4 = range(2017, 2024)

# IRS jurisdiction labels that pycountry does not resolve, or resolves wrongly.
IRS_NAME_TO_ISO = {
    "United Kingdom (England, Northern Ireland, Scotland, and Wales)": "GBR",
    "United Kingdom": "GBR",
    "United Kingdom (England, Northern Ireland, Scotland, and Wales": "GBR",
    "Cote d’Ivoire (Ivory Coast)": "CIV",
    "Cote d'Ivoire (Ivory Coast)": "CIV",
    "Korea, South": "KOR",
    "South Korea": "KOR",
    "Korea": "KOR",
    "Russia": "RUS",
    "Turkey": "TUR",
    "Taiwan": "TWN",
    "Vietnam": "VNM",
    "Hong Kong": "HKG",
    "Macau": "MAC",
    "Czech Republic": "CZE",
    "Netherlands Antilles": "ANT",
    "Curacao": "CUW",
    "Bolivia": "BOL",
    "Venezuela": "VEN",
    "Tanzania": "TZA",
    "Bahamas, The": "BHS",
    "The Bahamas": "BHS",
    "Bahamas": "BHS",
    "British Virgin Islands": "VGB",
    "Virgin Islands, British": "VGB",
    # Listed next to "British Virgin Islands" in the same tables, with small values (about US$0.1bn), so this is the
    # U.S. Virgin Islands.
    "Virgin Islands": "VIR",
    "Congo (Kinshasa)": "COD",
    "Congo (Brazzaville)": "COG",
    "Laos": "LAO",
    "Burma": "MMR",
    "Swaziland": "SWZ",
    "Macedonia": "MKD",
    "North Macedonia": "MKD",
    "Saint Kitts and Nevis": "KNA",
    "St. Kitts and Nevis": "KNA",
    "Saint Lucia": "LCA",
    "Iran": "IRN",
    "Syria": "SYR",
    "Moldova": "MDA",
    "Bosnia-Herzegovina": "BIH",
    "Burma; Myanmar": "MMR",
    "Cote D'Ivoire (Ivory Coast)": "CIV",
    "Korea, Republic of (South)": "KOR",
}


def irs_name_to_iso3(name):
    name = name.strip()
    if name in IRS_NAME_TO_ISO:
        return IRS_NAME_TO_ISO[name]
    try:
        return pycountry.countries.lookup(name).alpha_3
    except LookupError:
        pass
    try:
        return pycountry.countries.search_fuzzy(name)[0].alpha_3
    except LookupError:
        return None


# I parse Table 4 (profit and tax by ETR band) and Table 1B (all positive-profit sub-groups).
def _irs_number(v):
    """Convert an IRS cell to a float. Suppressed cells ('d') and blanks become NaN, and '*' flags are stripped."""
    if pd.isna(v):
        return float("nan")
    s = str(v).strip().replace("*", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _irs_etr_band(label):
    s = label.lower()
    if "negative or zero profit" in s:
        return "neg_profit"
    if "negative income tax accrued" in s:
        return "neg_accrued"
    if re.search(r"less than 15", s):
        return "lt15"
    if re.search(r"15% or greater", s):
        return "ge15"
    if re.search(r"less than 10", s):
        return "lt10"
    if re.search(r"10% to less than 25", s):
        return "b10_25"
    if re.search(r"25% or greater", s):
        return "ge25"
    return None


def parse_irs_table4(year):
    path = IRS_TABLES_DIR / f"{year % 100:02d}it04cbc.xlsx"
    d = pd.read_excel(path, header=None)
    hdr = d.iloc[2].fillna("").astype(str)
    pcol = next(i for i, s in enumerate(hdr) if s.startswith("Profit"))
    tcol = next(i for i, s in enumerate(hdr) if s.startswith("Income tax accrued"))
    c0 = d[0].fillna("").astype(str).str.strip()
    rows, band = [], None
    for i in range(5, len(d)):
        label = c0[i]
        if not label:
            continue
        if re.match(r"(d |\* |\[|NOTE|SOURCE)", label):
            break
        b = _irs_etr_band(label)
        if b is not None:
            band = b
            continue
        low = label.lower()
        # I classify the "United States" row (US groups' domestic sub-groups) like any other jurisdiction.
        if (band is None or "stateless" in low
                or low.endswith(", total") or "other countr" in low):
            continue
        rows.append(dict(year=year, band=band, name=label,
                         profit=_irs_number(d.iat[i, pcol]), tax=_irs_number(d.iat[i, tcol]),
                         suppressed=str(d.iat[i, pcol]).strip() == "d"))
    out = pd.DataFrame(rows)
    out["iso_partner"] = out["name"].map(irs_name_to_iso3)
    return out


def parse_irs_table1b(year):
    """Read the total positive profit per jurisdiction from Table 1B, the denominator of the share."""
    d = pd.read_excel(IRS_TABLES_DIR / f"{year % 100:02d}it01bcbc.xlsx", header=None)
    hdr = d.iloc[2].fillna("").astype(str)
    pcol = next(i for i, s in enumerate(hdr) if s.startswith("Profit"))
    tcol = next(i for i, s in enumerate(hdr) if s.startswith("Income tax accrued"))
    c0 = d[0].fillna("").astype(str).str.strip()
    rows = []
    for i in range(5, len(d)):
        label = c0[i]
        if re.match(r"(d |\* |\[|NOTE|SOURCE|Source)", label):
            break
        low = label.lower()
        if (not label or low.startswith("all jurisdictions")
                or "stateless" in low or low.endswith(", total") or "other countr" in low):
            continue
        rows.append(dict(year=year, name=label, total_1b=_irs_number(d.iat[i, pcol]),
                         tax_1b=_irs_number(d.iat[i, tcol])))
    out = pd.DataFrame(rows)
    out["iso_partner"] = out["name"].map(irs_name_to_iso3)
    return out


IRS_LOW_SURE = {"neg_accrued", "lt15", "lt10"}     # certainly below 15%
IRS_HIGH_SURE = {"ge15", "ge25"}                    # certainly 15% or more
# b10_25 (2017–18) is undetermined. It only widens the bounds.


# This function computes the share below 15% per jurisdiction-year and the classification at each cut.
def classify_irs_destinations(long, t1b, cut=0.5, inclusive=False):
    for df in (long, t1b):
        unmatched = sorted(df.loc[df["iso_partner"].isna(), "name"].unique())
        if unmatched:
            print(f"[warn] IRS names without ISO3 (dropped): {unmatched}")
    long = long.dropna(subset=["iso_partner"])
    t1b = t1b.dropna(subset=["iso_partner"])
    print(f"[info] suppressed ('d') profit cells: {int(long['suppressed'].sum())}")
    w = (long[long["band"] != "neg_profit"]
         .pivot_table(index=["iso_partner", "year"], columns="band",
                      values="profit", aggfunc="sum")
         .reset_index())
    for c in ["neg_accrued", "lt15", "ge15", "lt10", "b10_25", "ge25"]:
        if c not in w:
            w[c] = float("nan")
    wt = (long[long["band"] != "neg_profit"].groupby(["iso_partner", "year"])["tax"]
          .sum().rename("tax_listed").reset_index())
    w = w.merge(wt, on=["iso_partner", "year"], how="left")
    w = w.merge(t1b.groupby(["iso_partner", "year"], as_index=False)[["total_1b", "tax_1b"]].sum(),
                on=["iso_partner", "year"], how="outer")
    w = w[w["year"] >= 2017]
    names = pd.concat([long, t1b]).groupby("iso_partner")["name"].first()
    w["irs_name"] = w["iso_partner"].map(names)

    pos = lambda c: w[c].fillna(0).clip(lower=0)
    has15 = w["year"] >= 2019
    # "Fully listed" means that every positive band is present. neg_accrued may legitimately be absent when the
    # jurisdiction's other bands add up to the Table 1B total.
    listed_sum = (pos("neg_accrued") + pos("lt15") + pos("ge15")).where(
        has15, pos("neg_accrued") + pos("lt10") + pos("b10_25") + pos("ge25"))
    core_listed = (w["lt15"].notna() & w["ge15"].notna()).where(
        has15, w["lt10"].notna() & w["b10_25"].notna() & w["ge25"].notna())
    tot = w["total_1b"].where(w["total_1b"] > 0)
    # I use the Table 4 sum as the denominator when all core bands are listed, so that the two tables are not mixed.
    # Otherwise, I use the Table 1B total, but never less than what Table 4 lists.
    denom = listed_sum.where(core_listed, pd.concat([tot, listed_sum], axis=1).max(axis=1))
    denom = denom.where(denom > 0)
    low = (pos("neg_accrued") + pos("lt15")).where(has15, pos("neg_accrued") + pos("lt10"))
    high = pos("ge15").where(has15, pos("ge25"))
    w["positive_profit_usd"] = denom
    w["share_below15_lower"] = (low / denom).clip(0, 1)
    w["share_below15_upper"] = (1 - high / denom).clip(0, 1)
    w["share_below15"] = (low / denom).where(has15 & core_listed)
    w["all_bands_listed"] = core_listed

    w["qualifies"] = pd.NA
    w["method"] = ""
    lo, hi = w["share_below15_lower"], w["share_below15_upper"]
    above = (lambda x: x >= cut) if inclusive else (lambda x: x > cut)
    det_yes = above(lo)
    det_no = ~above(hi)
    w.loc[det_yes, "qualifies"] = True
    w.loc[det_no & ~det_yes, "qualifies"] = False
    w.loc[det_yes | det_no, "method"] = (
        w["all_bands_listed"].map({True: "measured", False: "bounded"}) + "_" +
        has15.map({True: "cut15", False: "cut10_25"}))[det_yes | det_no]

    # Straddling bounds in 2019–23 (disclosure gaps only): I assign the hidden profit (Table 1B total − listed bands)
    # by its own rate, the Table 1B tax minus the listed tax over the hidden profit. Below 15% it goes to the low band,
    # otherwise to the high band.
    hid_p = (denom - listed_sum).clip(lower=0)
    hid_t = w["tax_1b"] - w["tax_listed"].fillna(0)
    hid_etr = hid_t / hid_p.where(hid_p > 0)
    w["hidden_profit_usd"] = hid_p
    w["hidden_profit_etr"] = hid_etr
    amb15 = w["qualifies"].isna() & has15 & denom.notna() & hid_etr.notna()
    est = (low + hid_p.where(hid_etr < 0.15, 0.0)) / denom
    w.loc[amb15, "share_below15"] = est[amb15]
    w.loc[amb15, "qualifies"] = above(est)[amb15]
    w.loc[amb15, "method"] = "straddles_cut_hidden_etr"

    # Remaining straddles (2017–18, the 10–25% band): the jurisdiction's nearest determinate year decides (on a tie,
    # the later year).
    det = w[w["qualifies"].notna()][["iso_partner", "year", "qualifies"]]
    amb = w["qualifies"].isna() & denom.notna()
    for i in w.index[amb]:
        iso, y = w.at[i, "iso_partner"], w.at[i, "year"]
        c = det[det["iso_partner"] == iso]
        if len(c):
            c = c.assign(dist=(c["year"] - y).abs(), later=c["year"] > y)
            r = c.sort_values(["dist", "later"], ascending=[True, False]).iloc[0]
            w.at[i, "qualifies"] = bool(r["qualifies"])
            w.at[i, "method"] = f"straddles_cut_nearest_{int(r['year'])}"
    # Years in which a listed jurisdiction is missing (not listed, or no positive-profit sub-groups shown): its nearest
    # determinate year decides (on a tie, the later year).
    grid = pd.MultiIndex.from_product(
        [sorted(w["iso_partner"].unique()), list(IRS_YEARS_TABLE4)], names=["iso_partner", "year"])
    w = w.set_index(["iso_partner", "year"]).reindex(grid).reset_index()
    w["irs_name"] = w["iso_partner"].map(names)
    det = w[w["qualifies"].notna()][["iso_partner", "year", "qualifies", "method"]]
    for i in w.index[w["qualifies"].isna()]:
        iso, y = w.at[i, "iso_partner"], w.at[i, "year"]
        c = det[(det["iso_partner"] == iso) & ~det["method"].str.startswith("straddles_cut_nearest")]
        if len(c):
            c = c.assign(dist=(c["year"] - y).abs(), later=c["year"] > y)
            r = c.sort_values(["dist", "later"], ascending=[True, False]).iloc[0]
            w.at[i, "qualifies"] = bool(r["qualifies"])
            w.at[i, "method"] = f"not_shown_nearest_{int(r['year'])}"
    rest = w["qualifies"].isna()
    w.loc[rest, "qualifies"] = False
    w.loc[rest, "method"] = "undetermined"

    # 2016 has no Table 4, so I carry 2017 back.
    y16 = w[w["year"] == 2017].copy()
    y16["year"] = 2016
    y16["method"] = "carried_back_from_2017"
    w = pd.concat([w, y16], ignore_index=True)
    w["qualifies"] = w["qualifies"].astype(bool)
    return w.sort_values(["iso_partner", "year"])


def add_unlisted_havens(w):
    """Let the representation havens that the IRS never lists separately qualify in every year.

    The regional "other countries" rows that pool them show shares below 15% that pass the
    cuts, so without this step they could not qualify at all."""
    extra = sorted(set(TAX_HAVENS_REPRESENTATION) - set(w["iso_partner"]))
    rows = pd.DataFrame([dict(iso_partner=iso, irs_name="", year=y, qualifies=True,
                              method="never_listed_representation_haven")
                         for iso in extra for y in [2016] + list(IRS_YEARS_TABLE4)])
    print(f"  never-listed representation havens added as destinations: {' '.join(extra) or 'none'}")
    out = pd.concat([w, rows], ignore_index=True)
    out["qualifies"] = out["qualifies"].astype(bool)
    return out.sort_values(["iso_partner", "year"])


# I write the parsed Table 4 and one destination file per cut, and report the destinations.
def write_irs_low_tax_destinations():
    long = pd.concat([parse_irs_table4(y) for y in IRS_YEARS_TABLE4], ignore_index=True)
    # These are the parsed Table 4 rows (tax year × ETR band × listed jurisdiction), for the figure scripts that use
    # the bands directly.
    long.to_csv(IRS_OUT_DIR / "irs_soi_cbcr_table4_long.csv", index=False)
    print(f"wrote irs_soi_cbcr_table4_long.csv: {len(long):,} rows of IRS SOI CbCR Table 4")
    t1b = pd.concat([parse_irs_table1b(y) for y in IRS_YEARS_TABLE4], ignore_index=True)
    cols = ["iso_partner", "irs_name", "year", "qualifies", "method", "share_below15",
            "share_below15_lower", "share_below15_upper", "all_bands_listed",
            "hidden_profit_usd", "hidden_profit_etr", "positive_profit_usd", "total_1b",
            "tax_1b", "neg_accrued", "lt15", "ge15", "lt10", "b10_25", "ge25"]
    for tag, (cut, inclusive, fname) in IRS_SHARE_CUTS.items():
        w = add_unlisted_havens(classify_irs_destinations(long, t1b, cut=cut, inclusive=inclusive))
        out = IRS_OUT_DIR / fname
        w[cols].to_csv(out, index=False)
        print(f"[{tag}] wrote {out.name}: {int(w['qualifies'].sum())} destination "
              f"jurisdiction-years of {len(w)} ({w['iso_partner'].nunique()} jurisdictions)")
        q = w[w["qualifies"]].groupby("year")["iso_partner"].apply(lambda s: " ".join(sorted(s)))
        for y, s in q.items():
            print(f"  {y} ({len(s.split())}): {s}")


write_irs_low_tax_destinations()

# %% MARK: 7. Merge, save and check
# I merge the auxiliary data onto the panel, write the two datasets and run the final checks.

# %% MARK: 7.1 Merge

cbcr_main = cbcr_etrs_cits_gdp_wages.merge(
    regions,
    on=["iso_partner"],
    how="left",
)

cbcr_main = cbcr_main.merge(
    wb_income,
    on=["iso_partner", "year"],
    how="left",
)

# Current EU membership (EU27): the raw file carries an EU28 flag. I exclude the United Kingdom in all years, because
# the dummy describes membership in today's EU, not historical membership.
cbcr_main["eu27"] = cbcr_main["eu28"]
cbcr_main.loc[cbcr_main["iso_partner"] == "GBR", "eu27"] = 0
cbcr_main.drop(columns=["eu28"], inplace=True)

variables_to_replace = ["ukt", "oecd_oct", "oecd", "eu27"]
cbcr_main[variables_to_replace] = cbcr_main[variables_to_replace].fillna(0)

# %% MARK: 7.2 Save
# I write the full panel (all three profit groupings) and the "Total (All sub-groups)" panel alone, the working sample
# of 1a and 2. The columns follow the canonical order of _column_order.py.

cbcr_main_allsubgroupsonly = cbcr_main[
    cbcr_main["grouping"] == "Total (All sub-groups)"
].copy()
cbcr_main_allsubgroupsonly.drop(columns=["grouping"], inplace=True)

cbcr_main = apply_canonical_order(cbcr_main, COLUMNS_STAGE_1)
cbcr_main_allsubgroupsonly = apply_canonical_order(
    cbcr_main_allsubgroupsonly, COLUMNS_STAGE_1
)

cbcr_main.to_csv(f"{data_final}/cbcr_main.csv", index=False)
cbcr_main_allsubgroupsonly.to_csv(
    f"{data_final}/cbcr_main_allsubgroupsonly.csv",
    index=False,
)

# %% MARK: 7.3 Final checks

check_duplicates(cbcr_main_allsubgroupsonly, "final dataset (reporting sample only)")

# Coverage of the macro variables: every real partner jurisdiction must carry GDP, population and a monthly wage.
# Only the aggregate partner codes (continents and residuals, which script 2 disaggregates across real markets) may
# lack them. A future update of the raw data that breaks this coverage should fail here, loudly, instead of flowing
# silently into the estimation.
_aggregate_partner_codes = aggregated_country_groups | other_country_groups
_real_rows = cbcr_main_allsubgroupsonly[
    ~cbcr_main_allsubgroupsonly["iso_partner"].isin(_aggregate_partner_codes)
]
for _col in ["gdp_current_usd", "population", "wage_monthly"]:
    _missing = _real_rows.loc[_real_rows[_col].isna(), ["iso_partner", "year"]]
    if not _missing.empty:
        raise AssertionError(
            f"{_col} missing for real partner jurisdictions in the final "
            f"dataset: "
            f"{sorted(_missing['iso_partner'].unique())} — fix the raw data "
            "or add manual values in manual_imputation_values.csv before "
            "rerunning."
        )
print(
    "Macro coverage check passed: GDP, population and wages present for all "
    "real partner jurisdictions."
)

inf_check = cbcr_main.isin([np.inf, -np.inf]).any().any()
if inf_check:
    print("There were inf or -inf values in the DataFrame.")
else:
    print("No inf or -inf values found in the DataFrame.")

check_missing_values(
    cbcr_main_allsubgroupsonly,
    [
        "cit",
        "etr_domestic_corrected",
        "etr_foreign_corrected",
        "etr_average_corrected",
        "etr_parent_partner_corrected",
        "etr_partner_median_corrected",
        "etr_partner_p25_corrected",
        "etr_partner_p10_corrected",
        "etr_partner_min_corrected",
    ],
)

print(cbcr_main_allsubgroupsonly.columns.tolist())
