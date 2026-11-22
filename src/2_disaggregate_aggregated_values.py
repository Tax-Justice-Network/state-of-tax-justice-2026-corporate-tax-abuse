# %%
"""
2 — Disaggregate aggregated CbCR rows.

This script turns the aggregated CbCR rows into per-(parent, partner, year) country rows.
Several reporting countries ("bad reporters", see EXCLUSION_CONDITIONS) publish some or
all of their foreign activity only as aggregates instead of per-country rows: continent
totals (E/A/F/S), continent residuals (E_O/A_O/F_O/S_O), a global foreign residual (W_O),
or a single total-non-domestic row (WXD). I disaggregate them in two phases.

Phase 1 places the aggregates (conservation). I keep the reported country rows as they
are. I spread each aggregate with an equal split over every structurally eligible foreign
market it can refer to (the broad recipient universe: all real countries observed in the
CbCR panel, and for continent residuals only the countries of their continent). The split
itself is transient. Its only purpose is to select the recipient rows and to conserve each
aggregate total within its (year, parent, aggregate-code) group, and Phase 2 sets the real
values. Beforehand, I drop redundant continent totals (a single-letter row equal to the
sum of the reported country rows plus the _O residual), and I reduce WXD to its residual
after subtracting the foreign rows it already covers.

Phase 2a imputes the real economic activity on the distributed rows. I re-split the three
activity factors (employees, unrelated-party revenues, tangible assets) within each
conserved aggregate group in proportion to the Garcia-Bernardo & Jansky (2024)
gravity-model predictions. A per-country plausibility cap (2× GDP for sales and assets,
0.5× population for employees, recognised tax havens exempt) iteratively down-weights
markets whose total imputed activity across parents would exceed their economic size.
Payroll follows as imputed employees × wage × 12.

Phase 2b imputes profit from partner profitability ratios. For each partner country I
compute per-factor profit yields from its directly reported foreign rows (sum of reported
profit ÷ sum of reported factor, pooled over parents and years). I winsorize the yields
across partners at the 1st and 99th percentiles to clip outliers with thin denominators.
The yields keep their sign, so loss-making partners keep negative yields. Each imputed
row's profit is the mean of (imputed factor × partner yield) over the three activity
factors. I then rescale it within the aggregate group to conserve the reported aggregate
profit (with a sign-robust denominator).

I do not impute income tax (both variants), related-party revenues, stated capital, entity
counts, IP holding or the pair-specific metadata (pair ETR, n_cbcr), and I leave them blank
on the distributed rows. I floor total_revenues to the imputed unrelated-party revenues. I
clip negative distributed values to zero for the activity-type variables only, so imputed
profit keeps its sign. The reported-only estimation sample (is_distributed == 0) is
unaffected.

Section outline (numbers match the cell headings below):
1. Constants.
2. Partner metadata lookup tables.
3. Technical helpers.
4. Phase 1 functions.
5. Per-year pass.
   5.1 Pre-pass.
   5.2 Recipient universe for the broad gravity redistribution.
   5.3 Disaggregate each year.
6. Stack the per-year results into one dataset.
7. Phase 2a.
8. Phase 2b.
9. Clear the not-imputed variables on distributed rows.
10. Merge the market key.
11. Save the dataset and the diagnostics.
12. Reporting detail by year.
13. Check (no data changed).

Pipeline step 2 — after 1a (destination-based sales), before 4 (resource correction).

Reads:
  {data_final}/cbcr_main_allsubgroupsonly.csv            — cleaned CbCR sub-group panels (script 1)
  {data_intermediate}/cbcr_reporter_detail.csv           — partner detail of every submission (script 1)
  {data_intermediate}/gravity/gravity_imputed_activity.csv — GB&J gravity activity predictions
  {data_intermediate}/destination_based_sales.csv        — market key (script 1a)

Writes:
  {data_final}/cbcr_main_disaggregated.csv               — one row per (parent, partner, year), is_distributed in {0,1},
                                                           market key mne_plus_dds_share merged on (iso_partner, year)
  output/diagnostics/disaggregation/tables/reporting_detail_by_year.csv — headquarters jurisdictions by reporting
                                                           detail per year (section 12)
  output/diagnostics/disaggregation/tables/limited_detail_reporters_by_year.csv — the limited-detail reporters of each
                                                           year by type (section 12)
  output/diagnostics/disaggregation/…                    — conservation, WXD and continent-total diagnostics

Usage:
  python src/2_disaggregate_aggregated_values.py             — full run

Author: Tax Justice Network (based on the method of García-Bernardo and Janský).
Created: 2026-04-16.  Last updated: 2026-11-23.
"""

# %%
import sys
import pandas as pd
import numpy as np

# On Windows, stdout defaults to cp1252 and crashes when a printed line contains
# non-ASCII characters (e.g. in a file path). I reconfigure stdout to UTF-8 with error
# replacement, so status prints never abort the script.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import *

pd.set_option("display.max_columns", None)
pd.options.display.float_format = "{:,.2f}".format

# I load the full CbCR data early, so I can use it to build the reference tables.
cbcr_full = pd.read_csv(f"{data_final}/cbcr_main_allsubgroupsonly.csv")
years = sorted(cbcr_full["year"].dropna().unique())

print(f"Loaded {len(cbcr_full)} rows")
print(f"Years: {years}")


# %% MARK: 1. Constants
# 1. Constants: CbCR variables, metadata columns, aggregate codes, and
# the documented bad-reporter list

# %%
CBCR_VARS = [
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

METADATA_COLS = [
    "partner_jurisdiction",
    "etr_domestic_corrected",
    "etr_foreign_corrected",
    "etr_average_corrected",
    "etr_partner_median_corrected",
    "etr_partner_p25_corrected",
    "etr_partner_p10_corrected",
    "etr_partner_min_corrected",
    "etr_parent_partner_corrected",
    "cit",
    "region_tjn",
    "wb_income_group",
    "ukt",
    "oecd",
    "oecd_oct",
    "eu27",
    "wage_monthly",
]

STATIC_METADATA_COLS = [
    "partner_jurisdiction",
    "region_tjn",
    "wb_income_group",
    "ukt",
    "oecd",
    "oecd_oct",
    "eu27",
]

YEARLY_METADATA_COLS = [
    "etr_domestic_corrected",
    "etr_foreign_corrected",
    "etr_average_corrected",
    "etr_partner_median_corrected",
    "etr_partner_p25_corrected",
    "etr_partner_p10_corrected",
    "etr_partner_min_corrected",
    "cit",
    "wage_monthly",
]

PAIR_YEARLY_METADATA_COLS = [
    "etr_parent_partner_corrected",
    # Number of CbCR-reporting MNE groups in this (parent, partner, year) cell. I carry
    # it through as metadata (NaN on the imputed is_distributed==1 rows, like the pair
    # ETR).
    "n_cbcr",
]

CONTINENT_CODES = {
    "E_O": "Europe",
    "E": "Europe",
    "A_O": "Americas",
    "A": "Americas",
    "F_O": "Africa",
    "F": "Africa",
    "S_O": "Asia_Oceania",
    "S": "Asia_Oceania",
}

CONTINENT_TO_SINGLE = {
    "Europe": "E",
    "Americas": "A",
    "Africa": "F",
    "Asia_Oceania": "S",
}

CONTINENT_TO_RESIDUAL = {
    "Europe": "E_O",
    "Americas": "A_O",
    "Africa": "F_O",
    "Asia_Oceania": "S_O",
}

# Consistency check against config.py. Every non-country code must be either a
# continent code mapped above or one of the world-level codes handled in the
# distribution steps (W is dropped upstream, W_O is the global residual and WXD the
# total non-domestic row). Otherwise the disaggregation would silently ignore a new
# aggregate code added to config without a continent mapping here.
_unmapped = non_countries - set(CONTINENT_CODES) - {"W", "W_O", "WXD"}
assert not _unmapped, (
    f"Aggregate codes in config.non_countries without a continent mapping "
    f"in script 2: {sorted(_unmapped)}"
)

# List of "bad reporters": reporter-years whose foreign activity is published mostly or
# entirely as aggregates (continents or rest of world) rather than per-country rows. It
# has no effect on the disaggregated data, because the gravity method builds no weights
# from reporters at all and distributes every reporter's aggregates the same way. I keep
# the list for two reasons:
#   (a) It is the curated record of who reports badly in which years. These are the
#       parents whose rows are mostly is_distributed == 1 and who therefore shrink or
#       vanish from the reported-only sample in script 5.
#   (b) It defines the limited-detail reporters of the tables of reporting detail
#       (section 12) and feeds the per-year diagnostics (disaggregation_diagnostics.csv)
#       and the run prints.
# The comments give the partner detail of the submissions (script 1,
# cbcr_reporter_detail.csv).
# The source for who reports CbCR in which year is the OECD reporters list,
# data/raw/cbcr/oecd_cbcr_reporters_over_time_2026-06.xlsx.
EXCLUSION_CONDITIONS = [
    ("AUT", 2016, 2023),  # Austria: only continents
    ("BHR", 2022, 2023),  # Bahrain: continents only (new in 2022)
    ("CAN", 2022, 2023),  # Canada: few granular partners, heavily aggregated
    ("COL", 2022, 2022),  # Colombia: too few granular partners (no 2023 report)
    ("CZE", 2019, 2023),  # Czechia: only domestic vs ROW
    ("FIN", 2016, 2023),  # Finland: only domestic vs ROW 2016-2018, only continents from 2019
    ("GRC", 2017, 2019),  # Greece: only continents 2017-2018, a few country rows in 2019
    ("GBR", 2017, 2022),  # UK: only continents 2017-2022, granular from 2023
    ("HUN", 2018, 2023),  # Hungary: only domestic vs ROW
    ("IMN", 2017, 2020),  # Isle of Man: only continents
    ("IRL", 2016, 2023),  # Ireland: only domestic vs ROW 2016-2021, only continents from 2022
    ("KOR", 2016, 2023),  # Korea: only domestic vs ROW 2016-2018, only continents from 2019
    ("MAC", 2019, 2021),  # Macau (improved in 2022, no 2022 report)
    ("MAC", 2023, 2023),  # Macau: domestic vs ROW again in 2023
    ("MAR", 2021, 2023),  # Morocco: only domestic vs ROW
    ("MUS", 2019, 2023),  # Mauritius: continents only
    ("NLD", 2016, 2017),  # Netherlands: only domestic vs ROW
    ("NLD", 2022, 2023),  # Netherlands: few granular partners 2022-2023
    ("NOR", 2016, 2017),  # Norway: only continents
    ("NZL", 2018, 2023),  # New Zealand: only domestic vs ROW
    ("POL", 2019, 2021),  # Poland (improved in 2022)
    ("SRB", 2023, 2023),  # Serbia: continents only (new reporter in 2023)
    ("SWE", 2016, 2023),  # Sweden: only continents
    ("UKR", 2022, 2023),  # Ukraine: only domestic vs ROW (new in 2022)
]

METADATA_DTYPES = {
    "partner_jurisdiction": "string",
    "etr_domestic_corrected": "Float64",
    "etr_foreign_corrected": "Float64",
    "etr_average_corrected": "Float64",
    "etr_partner_median_corrected": "Float64",
    "etr_partner_p25_corrected": "Float64",
    "etr_partner_p10_corrected": "Float64",
    "etr_partner_min_corrected": "Float64",
    "etr_parent_partner_corrected": "Float64",
    "n_cbcr": "Float64",
    "cit": "Float64",
    "wage_monthly": "Float64",
    "region_tjn": "string",
    "wb_income_group": "string",
    "ukt": "Float64",
    "oecd": "Float64",
    "oecd_oct": "Float64",
    "eu27": "Float64",
}

# Variables for which a materially negative WXD residual triggers a warning
WXD_WARNING_VARS = [
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
    "stated_capital",
    "total_revenues",
    "related_party_revenues",
    "holding_or_managing_ip",
    "n_entities",
]

# I ignore small negative residuals for the warning.
WXD_WARNING_ATOL = 1e-3

# Variables that must never remain negative on distributed rows. When distributing a
# negative aggregate gives a negative row value for one of these activity-type
# variables, I clip it to zero on the distributed rows. The profit and tax variables are
# deliberately not in this list, so negative imputed profit and tax values survive (see
# SIGNED_DISTRIBUTION_VARS below). Where the clip fires, conservation is relaxed on
# purpose, and the conservation check at the end of the script logs the gap.
NONNEGATIVE_DISTRIBUTED_VARS = [
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
    "stated_capital",
    "total_revenues",
    "related_party_revenues",
    "holding_or_managing_ip",
    "n_entities",
]


# %% MARK: 2. Partner metadata lookup tables
# 2. Partner metadata lookup tables (static, per-year, and per-pair)


# %%
def first_non_null(series):
    non_null = series.dropna()
    return non_null.iloc[0] if not non_null.empty else pd.NA


partner_rows = cbcr_full.loc[
    ~cbcr_full["iso_partner"].isin(non_countries),
    ["iso_partner", "year"] + STATIC_METADATA_COLS + YEARLY_METADATA_COLS,
].copy()

partner_static = (
    partner_rows.groupby("iso_partner", as_index=False)[STATIC_METADATA_COLS]
    .agg(first_non_null)
    .copy()
)

partner_yearly = (
    partner_rows.groupby(["iso_partner", "year"], as_index=False)[YEARLY_METADATA_COLS]
    .agg(first_non_null)
    .copy()
)

pair_rows = cbcr_full.loc[
    ~cbcr_full["iso_partner"].isin(non_countries),
    ["iso_parent", "iso_partner", "year"] + PAIR_YEARLY_METADATA_COLS,
].copy()

pair_yearly = (
    pair_rows.groupby(["iso_parent", "iso_partner", "year"], as_index=False)[
        PAIR_YEARLY_METADATA_COLS
    ]
    .agg(first_non_null)
    .copy()
)

for col in STATIC_METADATA_COLS:
    try:
        partner_static[col] = partner_static[col].astype(METADATA_DTYPES[col])
    except Exception:
        pass

for col in YEARLY_METADATA_COLS:
    try:
        partner_yearly[col] = partner_yearly[col].astype(METADATA_DTYPES[col])
    except Exception:
        pass

for col in PAIR_YEARLY_METADATA_COLS:
    try:
        pair_yearly[col] = pair_yearly[col].astype(METADATA_DTYPES[col])
    except Exception:
        pass

continent_mapping = {
    "Europe": set(
        partner_static.loc[partner_static["region_tjn"] == "Europe", "iso_partner"]
    ),
    "Americas": set(
        partner_static.loc[
            partner_static["region_tjn"].isin(
                ["Latin America", "Northern America", "Caribbean/American isl."]
            ),
            "iso_partner",
        ]
    ),
    "Africa": set(
        partner_static.loc[partner_static["region_tjn"] == "Africa", "iso_partner"]
    ),
    "Asia_Oceania": set(
        partner_static.loc[
            partner_static["region_tjn"].isin(["Asia", "Oceania"]),
            "iso_partner",
        ]
    ),
}

for name, countries in continent_mapping.items():
    print(f"{name}: {len(countries)} countries")


# %% MARK: 3. Technical helpers
# 3. Technical helpers: metadata lookups


# %%
def get_excluded_parents_for_year(year):
    return {iso for iso, start, end in EXCLUSION_CONDITIONS if start <= year <= end}


def build_partner_metadata_lookup(cbcr_year, year, partner_static, partner_yearly):
    """
    Build a partner-level metadata lookup.

    Priority:
    1. Metadata observed in the current cbcr_year country rows
    2. Fallback metadata from the partner_yearly dataframe, where available
    3. Fallback metadata from the partner_static dataframe, where available
    """
    reported_lookup = (
        cbcr_year[~cbcr_year["iso_partner"].isin(non_countries)]
        .drop_duplicates(subset=["iso_partner"])
        .set_index("iso_partner")
    )

    static_lookup = partner_static.set_index("iso_partner")
    yearly_lookup = (
        partner_yearly.loc[partner_yearly["year"] == year]
        .drop(columns="year")
        .set_index("iso_partner")
    )

    all_partners = sorted(
        set(reported_lookup.index)
        .union(set(static_lookup.index))
        .union(set(yearly_lookup.index))
    )
    metadata_lookup = pd.DataFrame(index=all_partners)

    for col in METADATA_COLS:
        if col not in METADATA_DTYPES:
            continue
        dtype = METADATA_DTYPES[col]
        metadata_lookup[col] = pd.Series(
            pd.NA, index=metadata_lookup.index, dtype=dtype
        )

        if col in static_lookup.columns:
            static_series = static_lookup[col].copy()
            try:
                static_series = static_series.astype(dtype)
            except Exception:
                pass
            metadata_lookup.loc[static_series.index, col] = static_series

        if col in yearly_lookup.columns:
            yearly_series = yearly_lookup[col].copy()
            try:
                yearly_series = yearly_series.astype(dtype)
            except Exception:
                pass
            metadata_lookup.loc[yearly_series.index, col] = yearly_series

        if col in reported_lookup.columns:
            reported_series = reported_lookup[col].copy()
            try:
                reported_series = reported_series.astype(dtype)
            except Exception:
                pass
            metadata_lookup.loc[reported_series.index, col] = reported_series

    return metadata_lookup


def build_pair_metadata_lookup(cbcr_year, year, pair_yearly):
    """
    Build a reporter-partner-year lookup for pair-specific metadata.

    Priority:
    1. Metadata observed in the current cbcr_year country rows
    2. Fallback metadata from pair_yearly for the same year
    """
    reported_lookup = (
        cbcr_year[~cbcr_year["iso_partner"].isin(non_countries)]
        .drop_duplicates(subset=["iso_parent", "iso_partner"])
        .set_index(["iso_parent", "iso_partner"])
    )

    yearly_lookup = (
        pair_yearly.loc[pair_yearly["year"] == year]
        .drop(columns="year")
        .drop_duplicates(subset=["iso_parent", "iso_partner"])
        .set_index(["iso_parent", "iso_partner"])
    )

    all_pairs = reported_lookup.index.union(yearly_lookup.index)
    pair_lookup = pd.DataFrame(index=all_pairs)

    for col in PAIR_YEARLY_METADATA_COLS:
        dtype = METADATA_DTYPES[col]
        pair_lookup[col] = pd.Series(pd.NA, index=pair_lookup.index, dtype=dtype)

        if col in yearly_lookup.columns:
            yearly_series = yearly_lookup[col].copy()
            try:
                yearly_series = yearly_series.astype(dtype)
            except Exception:
                pass
            pair_lookup.loc[yearly_series.index, col] = yearly_series

        if col in reported_lookup.columns:
            reported_series = reported_lookup[col].copy()
            try:
                reported_series = reported_series.astype(dtype)
            except Exception:
                pass
            pair_lookup.loc[reported_series.index, col] = reported_series

    return pair_lookup


def get_aggregate_row(parent_data, code):
    rows = parent_data[parent_data["iso_partner"] == code]
    if rows.empty:
        return None
    return rows.iloc[0]


def series_allclose(left, right, vars_to_check, rtol=1e-6, atol=1e-3):
    """
    Compare two Series across vars_to_check. I ignore variables that are missing on both
    sides. The function returns True only if all comparable variables are close and at
    least one variable was actually compared.
    """
    compared_any = False

    for var in vars_to_check:
        lval = left.get(var, pd.NA)
        rval = right.get(var, pd.NA)

        if pd.isna(lval) and pd.isna(rval):
            continue

        if pd.isna(lval) != pd.isna(rval):
            return False

        compared_any = True
        if not np.isclose(float(lval), float(rval), rtol=rtol, atol=atol):
            return False

    return compared_any


def has_nonzero_values(values_dict, atol=1e-12):
    for val in values_dict.values():
        if pd.notna(val) and abs(float(val)) > atol:
            return True
    return False


# %% MARK: 4. Phase 1 functions
# 4. Phase 1 functions: place each aggregate on its eligible markets
# (a transient equal split that only selects the recipient rows and conserves the
# aggregate total, while Phase 2 sets the real values)

# %%
# Aggregate-structure rule (method): a reporter that lists both a continent total
# and its `_O` residual double-counts the continent, so I drop the redundant total
# before the distribution.
def drop_redundant_continent_totals(cbcr_year, continent_mapping):
    """
    For each reporter-year, I check whether a single-letter continent total
    (A/E/F/S) is only a redundant summary line.

    The check is:
    continent total == all reported country rows in that continent + corresponding _O

    This includes the domestic row automatically when the continent is the
    reporter's own continent.

    If it is redundant, I drop the single-letter continent total before the
    disaggregation.

    If both the single-letter row and the _O row exist but do not add up
    consistently, I flag the reporter-year.
    """
    df = cbcr_year.copy()

    group_cols = ["iso_parent"]
    if "year" in df.columns:
        group_cols.append("year")

    grouped_indices = df.groupby(group_cols, sort=False).groups

    rows_to_drop = []
    audit_rows = []
    flagged_rows = []

    for group_key, idx in grouped_indices.items():
        idx = list(idx)
        parent_data = df.loc[idx]

        if isinstance(group_key, tuple):
            group_info = {col: group_key[i] for i, col in enumerate(group_cols)}
        else:
            group_info = {group_cols[0]: group_key}

        for continent_name in continent_mapping.keys():
            single_code = CONTINENT_TO_SINGLE[continent_name]
            residual_code = CONTINENT_TO_RESIDUAL[continent_name]

            single_rows = parent_data[parent_data["iso_partner"] == single_code]
            residual_rows = parent_data[parent_data["iso_partner"] == residual_code]
            residual_row = get_aggregate_row(parent_data, residual_code)

            if single_rows.empty:
                continue

            single_values_dict = single_rows.iloc[0][CBCR_VARS].to_dict()
            single_row_is_empty = not has_nonzero_values(single_values_dict)

            if single_row_is_empty:
                rows_to_drop.extend(single_rows.index.tolist())

                audit_rows.append(
                    {
                        **group_info,
                        "continent": continent_name,
                        "single_code": single_code,
                        "residual_code": residual_code,
                        "has_single_row": True,
                        "n_single_rows": int(len(single_rows)),
                        "single_row_is_empty": True,
                        "has_reported_country_rows": False,
                        "n_reported_country_rows_in_continent": 0,
                        "has_residual_row": not residual_rows.empty,
                        "matches_reported_plus_residual": False,
                        "dropped_redundant_total": False,
                        "flagged_inconsistent_total_with_residual": False,
                        "dropped_empty_single_total": True,
                    }
                )
                continue

            continent_countries = continent_mapping[continent_name]
            reported_country_rows = parent_data[
                parent_data["iso_partner"].isin(continent_countries)
            ]
            reported_sum = reported_country_rows[CBCR_VARS].sum()

            has_reported_country_rows = not reported_country_rows.empty
            has_residual_row = residual_row is not None

            single_values = single_rows.iloc[0][CBCR_VARS]
            comparison_sum = reported_sum.copy()

            if has_residual_row:
                comparison_sum = comparison_sum.add(
                    residual_row[CBCR_VARS], fill_value=0
                )

            matches_components = False
            dropped_redundant_total = False
            flagged_inconsistent_total = False

            if has_reported_country_rows or has_residual_row:
                matches_components = series_allclose(
                    single_values, comparison_sum, CBCR_VARS
                )

                if matches_components:
                    rows_to_drop.extend(single_rows.index.tolist())
                    dropped_redundant_total = True
                elif has_residual_row:
                    flagged_inconsistent_total = True
                    flagged_rows.append(
                        {
                            **group_info,
                            "continent": continent_name,
                            "single_code": single_code,
                            "residual_code": residual_code,
                            "issue": "single_total_not_equal_to_reported_countries_plus_residual",
                        }
                    )

            audit_rows.append(
                {
                    **group_info,
                    "continent": continent_name,
                    "single_code": single_code,
                    "residual_code": residual_code,
                    "has_single_row": True,
                    "n_single_rows": int(len(single_rows)),
                    "single_row_is_empty": False,
                    "has_reported_country_rows": has_reported_country_rows,
                    "n_reported_country_rows_in_continent": int(
                        len(reported_country_rows)
                    ),
                    "has_residual_row": has_residual_row,
                    "matches_reported_plus_residual": matches_components,
                    "dropped_redundant_total": dropped_redundant_total,
                    "flagged_inconsistent_total_with_residual": flagged_inconsistent_total,
                    "dropped_empty_single_total": False,
                }
            )

    if rows_to_drop:
        df = df.drop(index=rows_to_drop).copy()

    audit_df = pd.DataFrame(audit_rows)
    flagged_df = pd.DataFrame(flagged_rows)

    return df, audit_df, flagged_df



# Variables whose global aggregate weight may be negative when I distribute aggregate
# rows. For these, partners that are systematically loss-making (negative profit, a
# negative tax accrual driven by refunds) get correctly signed shares of the aggregate,
# so the imputed rows keep the misalignment between where the activity happens and
# where the profit shows up. For the non-signed variables (employees, revenues, assets
# and so on) I clip negative totals to zero.
SIGNED_DISTRIBUTION_VARS = {
    "profit_loss_before_income_tax_corrected",
    "profit_loss_before_income_tax",
    "income_tax_paid_on_cash_basis",
    "income_tax_accrued_current_year",
}

# Signed imputed values (profit and tax) may stay negative from end to end. A market
# that is loss-making on average keeps a correctly signed negative imputed profit
# instead of being clamped to zero, so the misalignment between activity and profit
# that the downstream estimation detects is preserved. The post-distribution clip
# below exempts SIGNED_DISTRIBUTION_VARS unconditionally.





# %%
def build_uniform_recipient_weights(partner_universe, continent_mapping):
    """Build flat (=1) per-variable weight tables over the full foreign-country
    universe, the broad recipient set.

    I spread bad-reporter aggregates across every structurally eligible market, not
    just the partners that good reporters happened to report. The flat weight of 1 for
    every (variable, partner) makes the Phase-1 split an equal split, which (a) selects
    the recipient set and (b) conserves each raw aggregate (an equal split sums back to
    the aggregate). In Phase 2 below, the gravity-model predictions then set the real
    within-group split of the three activity factors, and partner profitability sets
    the profit. The Phase-1 values are therefore transient, and I clear every variable
    that is not imputed on the distributed rows afterwards.
    """
    partner_index = pd.Index(sorted(partner_universe), name="iso_partner")
    global_foreign_total = pd.DataFrame(1.0, index=partner_index, columns=CBCR_VARS)

    continent_foreign_total = {}
    for continent_name, countries in continent_mapping.items():
        sub = global_foreign_total[global_foreign_total.index.isin(countries)]
        continent_foreign_total[continent_name] = (
            sub.copy() if not sub.empty else pd.DataFrame(columns=CBCR_VARS)
        )

    return continent_foreign_total, global_foreign_total


def distribute_aggregates_per_reporter(
    parent_data,
    iso_parent,
    continent_mapping,
    continent_foreign_total,
    global_foreign_total,
):
    """
    For a single reporter, I keep the country-level rows and distribute the aggregated rows.

    Logic:
    1. I keep all individually reported country rows as they are.
    2. _O codes: I distribute the residual continent values to the unreported foreign
       countries.
    3. Single-letter codes: I also treat them as residual continent values and
       distribute them to the unreported foreign countries of that continent.
    4. W_O: I first distribute it to the foreign countries that are still uncovered. If
       none are left, I distribute it only across the foreign rows already imputed.
    5. WXD: I compute the residual part of WXD after deducting all non-domestic rows
       already covered, variable by variable.
         - I first distribute it to the foreign countries that are still uncovered.
         - Only if there are none, I distribute it across all foreign countries for
           which the parent does not report a true country row, including countries
           that may already have received continent residual imputations.

    I split the aggregate values, including negative values, equally across the
    eligible recipients (Phase-1 placement, and Phase 2 sets the real values).

    I evaluate the WXD diagnostics before clipping the negative distributed values of
    the non-profit and non-tax variables to zero.

    The final output contains country rows only. The metadata is merged later, so this
    function keeps only the identifier columns and the CbCR value columns.
    """
    year = parent_data["year"].iloc[0] if "year" in parent_data.columns else pd.NA

    base_cols = [
        c
        for c in ["year", "iso_parent", "iso_partner"] + CBCR_VARS
        if c in parent_data.columns
    ]

    country_rows = parent_data.loc[
        ~parent_data["iso_partner"].isin(non_countries),
        base_cols,
    ].copy()

    country_rows["is_distributed"] = 0
    country_rows["distribution_source"] = "reported_country"
    country_rows["source_aggregate_code"] = pd.NA

    true_reported_foreign_partners = set(
        country_rows.loc[country_rows["iso_partner"] != iso_parent, "iso_partner"]
    )
    covered_foreign_partners = set(true_reported_foreign_partners)

    distributed_rows = []
    continents_processed = set()
    negative_wxd_warning_rows = []
    clipping_rows = []

    def allocate_across_partners(
        agg_values,
        eligible_partners,
        foreign_total,
        iso_parent,
        year,
        distribution_source,
        source_code,
    ):
        # The Phase-1 split is equal by construction. `foreign_total` carries a flat
        # weight of 1 for every eligible market, so this only selects the recipient rows
        # and conserves the aggregate total within the group (the last row absorbs the
        # floating-point remainder). Phase 2 sets the real values on these rows.
        relevant = foreign_total[foreign_total.index.isin(eligible_partners)]
        if relevant.empty:
            return []

        partner_list = list(relevant.index)
        n_partners = len(partner_list)

        new_rows = [
            {
                "iso_parent": iso_parent,
                "iso_partner": iso_partner_target,
                "year": year,
                "is_distributed": 1,
                "distribution_source": distribution_source,
                "source_aggregate_code": source_code,
            }
            for iso_partner_target in partner_list
        ]

        for var in CBCR_VARS:
            agg_val = agg_values.get(var, 0)

            if pd.isna(agg_val):
                for row in new_rows:
                    row[var] = 0
                continue

            agg_val = float(agg_val)

            if n_partners == 1:
                new_rows[0][var] = agg_val
                continue

            base_value = agg_val / n_partners
            running_sum = 0.0
            for i in range(n_partners - 1):
                new_rows[i][var] = base_value
                running_sum += base_value
            new_rows[-1][var] = agg_val - running_sum

        return new_rows

    # Step 1: residual continent codes (_O)
    for code in ["E_O", "A_O", "F_O", "S_O"]:
        agg_row = parent_data[parent_data["iso_partner"] == code]
        if agg_row.empty:
            continue

        continent_name = CONTINENT_CODES[code]
        continents_processed.add(continent_name)

        eligible_partners = (
            continent_mapping[continent_name] - covered_foreign_partners - {iso_parent}
        )
        if not eligible_partners:
            continue

        foreign_total = continent_foreign_total.get(
            continent_name, pd.DataFrame(columns=CBCR_VARS)
        )
        if foreign_total.empty:
            continue

        agg_values = agg_row.iloc[0][CBCR_VARS].to_dict()
        if not has_nonzero_values(agg_values):
            continue

        new_rows = allocate_across_partners(
            agg_values=agg_values,
            eligible_partners=eligible_partners,
            foreign_total=foreign_total,
            iso_parent=iso_parent,
            year=year,
            distribution_source="continent_residual",
            source_code=code,
        )
        distributed_rows.extend(new_rows)
        covered_foreign_partners.update([row["iso_partner"] for row in new_rows])

    # Step 2: single-letter continent codes, also treated as residual values
    for code in ["E", "A", "F", "S"]:
        continent_name = CONTINENT_CODES[code]
        if continent_name in continents_processed:
            continue

        agg_row = parent_data[parent_data["iso_partner"] == code]
        if agg_row.empty:
            continue

        continents_processed.add(continent_name)

        eligible_partners = (
            continent_mapping[continent_name] - covered_foreign_partners - {iso_parent}
        )
        if not eligible_partners:
            continue

        foreign_total = continent_foreign_total.get(
            continent_name, pd.DataFrame(columns=CBCR_VARS)
        )
        if foreign_total.empty:
            continue

        agg_values = agg_row.iloc[0][CBCR_VARS].to_dict()
        if not has_nonzero_values(agg_values):
            continue

        new_rows = allocate_across_partners(
            agg_values=agg_values,
            eligible_partners=eligible_partners,
            foreign_total=foreign_total,
            iso_parent=iso_parent,
            year=year,
            distribution_source="continent_single_code_residual",
            source_code=code,
        )
        distributed_rows.extend(new_rows)
        covered_foreign_partners.update([row["iso_partner"] for row in new_rows])

    # Step 3: W_O, the global foreign residual
    w_o_row = parent_data[parent_data["iso_partner"] == "W_O"]
    if not w_o_row.empty:
        agg_values = w_o_row.iloc[0][CBCR_VARS].to_dict()

        if has_nonzero_values(agg_values):
            eligible_uncovered = (
                set(global_foreign_total.index)
                - covered_foreign_partners
                - {iso_parent}
            )

            if eligible_uncovered:
                new_rows = allocate_across_partners(
                    agg_values=agg_values,
                    eligible_partners=eligible_uncovered,
                    foreign_total=global_foreign_total,
                    iso_parent=iso_parent,
                    year=year,
                    distribution_source="world_other_residual",
                    source_code="W_O",
                )
                distributed_rows.extend(new_rows)
                covered_foreign_partners.update(
                    [row["iso_partner"] for row in new_rows]
                )
            else:
                print(
                    f"Skipping W_O for {iso_parent}, {year}: "
                    f"no uncovered foreign partners remain."
                )

    # Step 4: WXD residual
    wxd_row = parent_data[parent_data["iso_partner"] == "WXD"]
    reported_codes = set(parent_data["iso_partner"].dropna())
    wxd_only_reporter = reported_codes.issubset({iso_parent, "WXD"})

    if not wxd_row.empty:
        current_result = (
            pd.concat(
                [country_rows, pd.DataFrame(distributed_rows)],
                ignore_index=True,
            )
            if distributed_rows
            else country_rows.copy()
        )

        already_covered_sum = current_result.loc[
            current_result["iso_partner"] != iso_parent, CBCR_VARS
        ].sum()

        wxd_values = wxd_row.iloc[0][CBCR_VARS]

        residual_values = {}
        for var in CBCR_VARS:
            wxd_val = wxd_values.get(var, pd.NA)
            covered_val = already_covered_sum.get(var, pd.NA)

            if pd.isna(wxd_val):
                residual_values[var] = pd.NA
                continue

            covered_num = 0 if pd.isna(covered_val) else float(covered_val)
            residual = float(wxd_val) - covered_num
            residual_values[var] = residual

            if (var in WXD_WARNING_VARS) and (residual < -WXD_WARNING_ATOL):
                warning_row = {
                    "year": year,
                    "iso_parent": iso_parent,
                    "variable": var,
                    "wxd_value": float(wxd_val),
                    "already_covered_value": covered_num,
                    "wxd_residual": residual,
                }
                negative_wxd_warning_rows.append(warning_row)
                print(
                    f"WARNING: negative WXD residual for {iso_parent}, {year}, {var}: "
                    f"WXD={float(wxd_val):,.6f}, covered={covered_num:,.6f}, residual={residual:,.6f}"
                )

        if has_nonzero_values(residual_values):
            current_foreign_partners = set(
                current_result.loc[
                    current_result["iso_partner"] != iso_parent, "iso_partner"
                ]
            )

            wxd_eligible_uncovered = (
                set(global_foreign_total.index)
                - true_reported_foreign_partners
                - current_foreign_partners
                - {iso_parent}
            )

            if wxd_eligible_uncovered:
                new_rows = allocate_across_partners(
                    agg_values=residual_values,
                    eligible_partners=wxd_eligible_uncovered,
                    foreign_total=global_foreign_total,
                    iso_parent=iso_parent,
                    year=year,
                    distribution_source="wxd_residual_to_uncovered",
                    source_code="WXD",
                )
                distributed_rows.extend(new_rows)
                covered_foreign_partners.update(
                    [row["iso_partner"] for row in new_rows]
                )

            else:
                # Spillover case: the WXD residual is positive, but every global
                # foreign partner is already covered by a continent residual (F_O,
                # E_O, A_O, S_O or world_other). I add the WXD residual proportionally
                # to the existing distributed rows, which already cover the same set
                # of partners, so the partner-level totals reflect both the continent
                # share and the WXD spillover on a single row per partner. A second
                # row per partner would produce duplicate parent × partner × year rows
                # downstream.
                wxd_eligible_nonreported = (
                    set(global_foreign_total.index)
                    - true_reported_foreign_partners
                    - {iso_parent}
                )

                if wxd_eligible_nonreported and distributed_rows:
                    # Equal-share spillover (flat Phase-1 weights, as in
                    # allocate_across_partners). Every row already distributed to an
                    # eligible partner receives 1/n of the residual, so the
                    # partner-level totals stay on a single row per partner. A second
                    # row per partner would produce duplicate parent × partner × year
                    # rows downstream. The Phase-2 imputation re-splits the imputed
                    # variables afterwards anyway.
                    eligible_in_universe = wxd_eligible_nonreported & set(
                        global_foreign_total.index
                    )
                    n_eligible = len(eligible_in_universe)
                    if n_eligible > 0:
                        for row in distributed_rows:
                            partner = row.get("iso_partner")
                            if partner not in eligible_in_universe:
                                continue
                            for var in CBCR_VARS:
                                rv = residual_values.get(var)
                                if rv is None or pd.isna(rv):
                                    continue
                                add_val = float(rv) * (1.0 / n_eligible)
                                cur = row.get(var, 0.0)
                                if pd.isna(cur):
                                    cur = 0.0
                                row[var] = float(cur) + add_val
                            existing_src = str(row.get("distribution_source",
                                                       "")).strip()
                            if "wxd_spillover" not in existing_src:
                                row["distribution_source"] = (
                                    existing_src + "+wxd_spillover"
                                    if existing_src
                                    else "wxd_spillover"
                                )
    # Final result for all reporters, including those without a WXD row
    if distributed_rows:
        result = pd.concat(
            [country_rows, pd.DataFrame(distributed_rows)],
            ignore_index=True,
        )
    else:
        result = country_rows

    # Internal WXD check. I compute it before clipping the negative distributed values.
    if not wxd_row.empty:
        wxd_values = wxd_row.iloc[0][CBCR_VARS]
        non_domestic_sum = result.loc[
            result["iso_partner"] != iso_parent, CBCR_VARS
        ].sum()

        wxd_check = {
            "year": year,
            "iso_parent": iso_parent,
            "has_wxd_row": 1,
            "wxd_only_reporter": int(wxd_only_reporter),
            "wxd_matches_non_domestic_rows": series_allclose(
                wxd_values,
                non_domestic_sum,
                CBCR_VARS,
                rtol=1e-4,
                atol=1e-1,
            ),
            "wxd_max_abs_diff": max(
                [
                    abs(round(float(non_domestic_sum[var]) - float(wxd_values[var])))
                    for var in CBCR_VARS
                    if pd.notna(wxd_values.get(var, pd.NA))
                    and pd.notna(non_domestic_sum.get(var, pd.NA))
                ],
                default=pd.NA,
            ),
        }
    else:
        wxd_check = {
            "year": year,
            "iso_parent": iso_parent,
            "has_wxd_row": 0,
            "wxd_only_reporter": int(wxd_only_reporter),
            "wxd_matches_non_domestic_rows": pd.NA,
            "wxd_max_abs_diff": pd.NA,
        }

    # After the WXD checks, I clip the negative distributed values of the activity-type
    # variables to zero. The signed profit and tax variables are not in the list, so
    # their negative imputed values survive into the conserved per-group aggregate,
    # which the profitability recompute (Phase 2b) then redistributes with their sign.
    distributed_mask = result["is_distributed"] == 1

    for var in NONNEGATIVE_DISTRIBUTED_VARS:
        negative_mask = distributed_mask & result[var].notna() & (result[var] < 0)
        if negative_mask.any():
            negative_rows = result.loc[
                negative_mask,
                [
                    "year",
                    "iso_parent",
                    "iso_partner",
                    "distribution_source",
                    "source_aggregate_code",
                    var,
                ],
            ].copy()
            negative_rows = negative_rows.rename(columns={var: "value_before_clipping"})
            negative_rows["variable"] = var
            clipping_rows.extend(negative_rows.to_dict("records"))

            n_neg = int(negative_mask.sum())
            print(
                f"Clipping {n_neg} negative distributed values to zero for "
                f"{iso_parent}, {year}, variable {var}"
            )
            result.loc[negative_mask, var] = 0

    return (
        result,
        len(distributed_rows),
        len(continents_processed),
        wxd_check,
        negative_wxd_warning_rows,
        clipping_rows,
    )


# %% MARK: 5. Per-year pass
# 5. Per-year pass: run Phase 1 for every reporter and attach the partner
# metadata

# %%
print("\nDocumented bad reporters (aggregate-only foreign data) per year:")
for year in years:
    excluded = get_excluded_parents_for_year(year)
    print(f"  {year}: {len(excluded)} countries - {sorted(excluded)}")

# %% MARK: 5.1 Pre-pass
# Pre-pass: for each year I drop the redundant continent totals, flag the inconsistent
# ones and collect the documented bad reporters (for the diagnostics only, see the
# EXCLUSION_CONDITIONS comment). I keep the cleaned per-year frames for the per-year
# distribution pass below.

# %%
cbcr_year_clean = {}
continent_total_audit_dict = {}
continent_total_audit_years = []
flagged_inconsistent_totals_dict = {}
excluded_parents_dict = {}

print("\nChecking continent totals and determining excluded reporters per year:")

for year in years:
    cbcr_year = cbcr_full[cbcr_full["year"] == year].copy()

    # I drop the redundant continent totals and flag the inconsistent cases of a total
    # plus its _O residual.
    cbcr_year, continent_total_audit, flagged_inconsistent_totals = (
        drop_redundant_continent_totals(cbcr_year, continent_mapping)
    )

    # I collect the documented bad reporters plus the parents flagged above, for the
    # diagnostics.
    manual_excluded = get_excluded_parents_for_year(year).copy()
    if not flagged_inconsistent_totals.empty:
        flagged_parents = set(flagged_inconsistent_totals["iso_parent"].unique())
    else:
        flagged_parents = set()
    excluded_parents = manual_excluded | flagged_parents

    cbcr_year_clean[year] = cbcr_year
    continent_total_audit_dict[year] = continent_total_audit
    continent_total_audit_years.append(continent_total_audit)
    flagged_inconsistent_totals_dict[year] = flagged_inconsistent_totals
    excluded_parents_dict[year] = excluded_parents

    n_dropped_redundant_totals = (
        int(continent_total_audit["dropped_redundant_total"].sum())
        if not continent_total_audit.empty
        else 0
    )
    print(
        f"  {year}: dropped {n_dropped_redundant_totals} redundant continent "
        f"total rows; flagged inconsistent totals {sorted(flagged_parents)}; "
        f"documented bad reporters {sorted(excluded_parents)}"
    )

# %% MARK: 5.2 Recipient universe for the broad gravity redistribution
# I spread a bad reporter's aggregate across every structurally eligible foreign market
# (all real countries observed anywhere in the CbCR panel), with a flat phase-1 weight
# that conserves each aggregate. In the post-distribution step further below, the
# gravity model sets the actual within-group split of the three activity factors, and
# partner profitability sets the profit.

# %%
partner_universe = set(partner_static["iso_partner"].dropna()) - set(non_countries)

continent_foreign_total, global_foreign_total = build_uniform_recipient_weights(
    partner_universe, continent_mapping
)

print(
    f"\nBroad recipient universe: {len(global_foreign_total)} foreign markets "
    f"eligible to receive gravity-imputed activity (flat phase-1 weights)."
)

# %% MARK: 5.3 Disaggregate each year
all_years = []
diagnostics = []
wxd_checks = []
negative_wxd_warning_rows_all = []
negative_distributed_clipping_rows_all = []

print("\nDisaggregating rows per year:")

for year in years:
    print(f'\n{"=" * 60}\nYear {year}\n{"=" * 60}')

    cbcr_year = cbcr_year_clean[year]
    manual_excluded = get_excluded_parents_for_year(year)
    excluded_parents = excluded_parents_dict[year]
    flagged_parents = (
        set(flagged_inconsistent_totals_dict[year]["iso_parent"].unique())
        if not flagged_inconsistent_totals_dict[year].empty
        else set()
    )
    continent_total_audit = continent_total_audit_dict[year]
    n_dropped_redundant_totals = (
        int(continent_total_audit["dropped_redundant_total"].sum())
        if not continent_total_audit.empty
        else 0
    )

    n_good = cbcr_year[~cbcr_year["iso_parent"].isin(excluded_parents)][
        "iso_parent"
    ].nunique()
    n_excluded = cbcr_year[cbcr_year["iso_parent"].isin(excluded_parents)][
        "iso_parent"
    ].nunique()
    print(f"Reporters: {n_good} good + {n_excluded} documented bad reporters "
          f"(diagnostic label only — all reporters are distributed identically)")

    # I build the metadata lookups.
    partner_lookup = build_partner_metadata_lookup(
        cbcr_year=cbcr_year,
        year=year,
        partner_static=partner_static,
        partner_yearly=partner_yearly,
    )

    pair_lookup = build_pair_metadata_lookup(
        cbcr_year=cbcr_year,
        year=year,
        pair_yearly=pair_yearly,
    )

    # I disaggregate all reporters.
    processed_reporters = []
    total_distributed = 0
    reporters_with_distribution = 0

    for iso_parent, parent_data in cbcr_year.groupby("iso_parent", sort=False):
        (
            processed,
            n_distributed,
            _,
            wxd_check,
            negative_wxd_warning_rows,
            clipping_rows,
        ) = distribute_aggregates_per_reporter(
            parent_data=parent_data,
            iso_parent=iso_parent,
            continent_mapping=continent_mapping,
            continent_foreign_total=continent_foreign_total,
            global_foreign_total=global_foreign_total,
        )

        processed_reporters.append(processed)
        wxd_checks.append(wxd_check)

        if negative_wxd_warning_rows:
            negative_wxd_warning_rows_all.extend(negative_wxd_warning_rows)

        if clipping_rows:
            negative_distributed_clipping_rows_all.extend(clipping_rows)

        total_distributed += n_distributed

        if n_distributed > 0:
            reporters_with_distribution += 1

    combined = pd.concat(processed_reporters, ignore_index=True)

    # Step 6: I fill the partner metadata of the distributed rows.
    for col in METADATA_COLS:
        target_dtype = METADATA_DTYPES[col]

        if col not in combined.columns:
            combined[col] = pd.Series(pd.NA, index=combined.index, dtype=target_dtype)
        else:
            try:
                combined[col] = combined[col].astype(target_dtype)
            except Exception:
                pass

    # I fill all non-pair metadata from the partner lookup.
    non_pair_cols = [
        col for col in METADATA_COLS if col != "etr_parent_partner_corrected"
    ]

    for col in non_pair_cols:
        missing = combined[col].isna()
        if missing.any():
            mapped = combined.loc[missing, "iso_partner"].map(partner_lookup[col])

            try:
                mapped = mapped.astype(METADATA_DTYPES[col])
            except Exception:
                pass

            combined.loc[missing, col] = mapped

    # I fill the pair-specific corrected ETR from the pair lookup for the cells that were
    # actually reported in the source data. Distributed (is_distributed=1) cells stay
    # NaN, because no real (parent, partner, year) report exists to derive an ETR from,
    # and I deliberately do not impute the pair ETR here. Downstream consumers should
    # treat etr_parent_partner_corrected as a diagnostic only and rely on the partner-year
    # ETRs (median, p25, average, min) for any calculation that needs to cover the
    # distributed rows.
    # Every pair-year metadata column (the pair ETR and the CbCR group count n_cbcr) gets
    # the same treatment. I map the reported value onto the reported cells and leave the
    # distributed (imputed) cells NaN, because they have no real (parent, partner, year)
    # report. n_cbcr in particular is not carried on the good-reporter rows, so I create
    # the column here as NaN first and then fill it from pair_lookup.
    for pair_col in PAIR_YEARLY_METADATA_COLS:
        if pair_col not in pair_lookup.columns:
            continue
        if pair_col not in combined.columns:
            combined[pair_col] = np.nan
        missing_pair = combined[pair_col].isna()
        if missing_pair.any():
            pair_index = pd.MultiIndex.from_frame(
                combined.loc[missing_pair, ["iso_parent", "iso_partner"]]
            )
            mapped_pair = pair_lookup.reindex(pair_index)[pair_col].to_numpy()
            combined.loc[missing_pair, pair_col] = mapped_pair

    combined["year"] = year

    preferred_cols = (
        [
            "year",
            "iso_parent",
            "iso_partner",
            "is_distributed",
            "distribution_source",
            "source_aggregate_code",
        ]
        + CBCR_VARS
        + METADATA_COLS
    )
    existing_preferred = [c for c in preferred_cols if c in combined.columns]
    other_cols = [c for c in combined.columns if c not in existing_preferred]
    combined = combined[existing_preferred + other_cols]

    all_years.append(combined)

    diagnostics.append(
        {
            "year": year,
            "n_rows_input": int(len(cbcr_full[cbcr_full["year"] == year])),
            "n_rows_after_dropping_redundant_totals": int(len(cbcr_year)),
            "n_rows_output": int(len(combined)),
            "n_reporters_total": int(cbcr_year["iso_parent"].nunique()),
            "n_reporters_on_bad_reporter_list": int(len(manual_excluded)),
            "n_reporters_flagged_inconsistent_totals": int(len(flagged_parents)),
            "n_reporters_bad_or_flagged": int(len(excluded_parents)),
            "n_redundant_continent_totals_dropped": int(n_dropped_redundant_totals),
            "n_distributed_rows": int(total_distributed),
            "n_reporters_with_distribution": int(reporters_with_distribution),
        }
    )

    print(
        f"Distributed {total_distributed} rows across {reporters_with_distribution} reporters"
    )
    print(f"Output rows: {len(combined)}")


# %% MARK: 6. Stack the per-year results into one dataset
# 6. Stack the per-year results into one dataset

# %%
cbcr_main_disaggregated = pd.concat(all_years, ignore_index=True)

disaggregation_diagnostics = pd.DataFrame(diagnostics)
continent_total_audit_all = pd.concat(continent_total_audit_years, ignore_index=True)
wxd_checks_all = pd.DataFrame(wxd_checks)
negative_wxd_warnings_all = pd.DataFrame(negative_wxd_warning_rows_all)
negative_distributed_clipping_all = pd.DataFrame(negative_distributed_clipping_rows_all)

non_empty_flagged = [
    df for df in flagged_inconsistent_totals_dict.values() if not df.empty
]
if non_empty_flagged:
    flagged_inconsistent_totals_all = pd.concat(non_empty_flagged, ignore_index=True)
else:
    flagged_inconsistent_totals_all = pd.DataFrame()

cbcr_main_disaggregated = cbcr_main_disaggregated.sort_values(
    ["year", "iso_parent", "iso_partner"]
).reset_index(drop=True)



# %% MARK: 7. Phase 2a
# 7. Phase 2a: impute real activity on distributed rows (gravity model and
# plausibility caps). I re-split each aggregate group's conserved total across its
# recipient rows in proportion to the activity the gravity model predicts. A
# per-country cap bounds the total imputed activity a market can receive. I recompute
# payroll from the imputed employees.

# %%
_g = pd.read_csv(f"{data_intermediate}/gravity/gravity_imputed_activity.csv")
_g = _g.rename(columns={
    "pred_n_employees": "_g_n_employees",
    "pred_unrelated_party_revenues": "_g_unrelated_party_revenues",
    "pred_tangible_assets_except_cash": "_g_tangible_assets_except_cash",
})
# Guard: src/gravity/ rebuilds the gravity panel (fetch_*, then build_features, then
# impute_model), and the panel can lag a new CbCR vintage. A CbCR year without gravity
# predictions would silently fall back to the flat phase-1 weights (a uniform split).
# Instead, I carry the latest gravity year's predictions forward into each missing year
# and print a loud warning that asks for a rerun of the gravity chain.
_g_years = set(pd.to_numeric(_g["year"], errors="coerce").dropna().astype(int))
_cb_years = set(pd.to_numeric(cbcr_main_disaggregated["year"], errors="coerce").dropna().astype(int))
_missing_g_years = sorted(_cb_years - _g_years)
if _missing_g_years:
    _src_y = max(_g_years)
    print("\n" + "!" * 78)
    print(f"WARNING: gravity_imputed_activity.csv has no predictions for "
          f"{_missing_g_years} (it covers {min(_g_years)}-{_src_y}).")
    print(f"         Carrying the {_src_y} predictions forward as a STOP-GAP so the "
          f"imputation runs; the {_missing_g_years} imputed rows are PRELIMINARY.")
    print("         Rerun src/gravity/ (fetch_* -> build_features -> impute_model) "
          "for the extended window.")
    print("!" * 78 + "\n")
    for _y in _missing_g_years:
        _cp = _g[_g["year"] == _src_y].copy()
        _cp["year"] = _y
        _g = pd.concat([_g, _cp], ignore_index=True)
GRAVITY_YEARS_CARRIED_FORWARD = list(_missing_g_years)
df = cbcr_main_disaggregated.merge(
    _g[["iso_parent", "iso_partner", "year", "_g_n_employees",
        "_g_unrelated_party_revenues", "_g_tangible_assets_except_cash"]],
    on=["iso_parent", "iso_partner", "year"], how="left",
)
dist = df["is_distributed"] == 1
grp = [df["year"], df["iso_parent"], df["source_aggregate_code"]]
factor_map = {
    "n_employees": "_g_n_employees",
    "unrelated_party_revenues": "_g_unrelated_party_revenues",
    "tangible_assets_except_cash": "_g_tangible_assets_except_cash",
}
# ---- Per-country total imputed-activity cap ----
# The redistribution conserves each (year, parent, source_aggregate) total, because
# val = weight/Σweight × aggregate always sums back to the aggregate. I can therefore
# iteratively down-weight any market whose *total* imputed activity exceeds an
# economic-size ceiling, and the freed share flows to the other partners while the
# aggregate is preserved. Without this cap, small or fragile non-haven states receive
# implausibly large imputed activity (e.g. Somalia about 6 times its GDP in MNE sales,
# Marshall Islands about 197 times). The anchors are GDP for sales and assets and
# population for employees. Recognised havens are exempt, because high sales relative
# to GDP are legitimate for them.
_CAP_SALES_X_GDP, _CAP_ASSETS_X_GDP, _CAP_EMP_X_POP = 2.0, 2.0, 0.5
_araw = pd.read_csv(
    f"{data_final}/cbcr_main_allsubgroupsonly.csv",
    usecols=["iso_partner", "year", "gdp_current_usd", "population"],
).drop_duplicates(["iso_partner", "year"])
# I fill missing GDP and population per country across the year panel (forward and
# backward fill), so country-years without GDP (e.g. Marshall Islands 2016, North
# Korea) still get a ceiling. Otherwise the cap would silently not fire there.
_isos = df["iso_partner"].dropna().unique()
_yrs = sorted(int(y) for y in pd.to_numeric(df["year"], errors="coerce").dropna().unique())
_grid = pd.MultiIndex.from_product([_isos, _yrs],
                                   names=["iso_partner", "year"]).to_frame(index=False)
_araw = _grid.merge(_araw, on=["iso_partner", "year"], how="left").sort_values(
    ["iso_partner", "year"])
for _c in ["gdp_current_usd", "population"]:
    _araw[_c] = _araw.groupby("iso_partner")[_c].transform(lambda s: s.ffill().bfill())
_araw = _araw.rename(columns={"gdp_current_usd": "_gdp_anchor", "population": "_pop_anchor"})
df = df.merge(_araw, on=["iso_partner", "year"], how="left")
_gdp = pd.to_numeric(df["_gdp_anchor"], errors="coerce")
_pop = pd.to_numeric(df["_pop_anchor"], errors="coerce")
# The cap exemption uses the frozen functional haven set, not the presentational
# representation list. Micro-state havens like Guernsey and the Cook Islands must keep
# the exemption even where the outcome-based representation list omits them.
_exempt = df["iso_partner"].isin(TAX_HAVENS_FUNCTIONAL)
_ceil_map = {
    "n_employees": (_CAP_EMP_X_POP * _pop).where(~_exempt, np.inf),
    "unrelated_party_revenues": (_CAP_SALES_X_GDP * _gdp).where(~_exempt, np.inf),
    "tangible_assets_except_cash": (_CAP_ASSETS_X_GDP * _gdp).where(~_exempt, np.inf),
}
_py = [df["iso_partner"], df["year"]]
_ncap = {}
for _col, _gcol in factor_map.items():
    cur = pd.to_numeric(df[_col], errors="coerce").fillna(0.0)
    gw = pd.to_numeric(df[_gcol], errors="coerce")
    gw = gw.where(gw.notna() & (gw > 0), cur).clip(lower=0).where(dist, 0.0)
    agg = cur.where(dist, 0.0).groupby(grp).transform("sum")
    ceil_row = _ceil_map[_col]
    val = pd.Series(0.0, index=df.index)
    for _ in range(10):
        gwsum = gw.groupby(grp).transform("sum")
        val = pd.Series(np.where(dist & (gwsum > 0), gw / gwsum * agg, 0.0),
                        index=df.index)
        tot = val.where(dist, 0.0).groupby(_py).transform("sum")
        over = dist & ceil_row.notna() & (tot > ceil_row) & (tot > 0)
        if not over.any():
            break
        gw = gw.mask(over, gw * (ceil_row / tot)).clip(lower=0)
    _ncap[_col] = int((dist & ceil_row.notna() & (val.groupby(_py).transform("sum") > ceil_row * 1.001)).sum())
    df[_col] = np.where(dist, val, df[_col])
print(f"  gravity activity cap: rows still > ceiling after capping "
      f"(all-partners-capped groups): {_ncap}")
df["payroll"] = (pd.to_numeric(df["n_employees"], errors="coerce").fillna(0)
                 * pd.to_numeric(df["wage_monthly"], errors="coerce").fillna(0) * 12)

# %% MARK: 8. Phase 2b
# 8. Phase 2b: impute profit on distributed rows from partner profitability.
# I compute per-partner, per-factor profit yields from the directly reported foreign
# rows. Each imputed row's profit is the mean of (imputed factor × partner yield) over
# the three activity factors. I rescale it within the aggregate group to conserve the
# reported aggregate profit, keeping its sign.

# %%
# Factors whose profitability I use to impute the profit of the distributed rows. For
# each factor f, the partner's profit yield is Σ reported profit ÷ Σ reported f (pooled
# over its directly reported foreign rows), and the row's implied profit from f is
# row_f × that yield. The imputed profit is the mean of the implied profits over the
# factors for which the row has a positive value and the partner a defined yield. I fix
# the factors at all three activity factors (sales, employees, tangible assets), so the
# profit reflects the partner's overall return on activity rather than its sales margin
# alone, which would over-reward consumer markets.
PROFIT_IMPUTATION_FACTORS = [
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
]
# Robustness of the partner-specific profit yields. I use each partner's per-factor
# yield (Σ reported profit ÷ Σ reported factor) directly and winsorize it across
# partners at the 1st and 99th percentiles, which clips only the explosive outliers that
# near-zero activity denominators produce. The winsorizing keeps the sign: a partner that
# reported losses keeps a negative yield (and so a negative imputed profit), and a
# structurally highly profitable jurisdiction keeps its high yield.
PROFIT_YIELD_WINSOR = 0.01

# Sign-robustness threshold of the within-group profit rescale. When the signed sum of
# the per-row profit estimates nearly cancels, the raw shares explode, because a tiny
# denominator inflates each share. Below this fraction of the absolute sum I fall back
# to shares clipped at zero.
SIGNED_DENOMINATOR_MIN_RELATIVE = 0.05


def _impute_profit_multifactor(frame, pcol, reported_mask, factors):
    """Return the per-row imputed profit from the partner's profitability on several factors.

    For each factor f in `factors`, the partner-level yield is Σ reported profit ÷
    Σ reported f, pooled over the partner's directly reported foreign rows
    (`reported_mask`). The row's implied profit from f is row_f × yield. The returned
    value is the arithmetic mean of the implied profits across the factors for which the
    row has a positive value and the partner has a defined yield. A row with 0 employees
    therefore contributes no employee-based estimate, and a partner with no reported
    assets contributes no asset yield. The result is aligned to `frame.index` and NaN
    where no factor is usable (the caller leaves such rows as they are).

    With factors == ["unrelated_party_revenues"] this reduces to a pure sales-margin
    imputation (imputed sales × reported profit/sales).
    """
    p = pd.to_numeric(frame[pcol], errors="coerce")
    est_sum = pd.Series(0.0, index=frame.index)
    est_cnt = pd.Series(0.0, index=frame.index)
    for f in factors:
        if f not in frame.columns:
            continue
        fv = pd.to_numeric(frame[f], errors="coerce")
        tab = pd.DataFrame(
            {"iso_partner": frame["iso_partner"], "p": p.where(reported_mask),
             "f": fv.where(reported_mask)}
        ).groupby("iso_partner").sum(min_count=1)
        own_yield = (tab["p"] / tab["f"]).where(tab["f"] > 0)
        # I winsorize the partner yields across partners at the 1st and 99th percentiles.
        # This clips only the explosive outliers with thin denominators and otherwise
        # keeps each partner's own profitability, with its sign.
        _lo, _hi = own_yield.quantile(PROFIT_YIELD_WINSOR), own_yield.quantile(1 - PROFIT_YIELD_WINSOR)
        yield_f = own_yield
        if pd.notna(_lo) and pd.notna(_hi):
            yield_f = own_yield.clip(_lo, _hi)
        implied = fv * frame["iso_partner"].map(yield_f)
        ok = implied.notna() & fv.notna() & (fv > 0)
        est_sum = est_sum + implied.where(ok, 0.0)
        est_cnt = est_cnt + ok.astype(float)
    return est_sum / est_cnt.where(est_cnt > 0)


# %%
_reported = (df["is_distributed"] == 0) & (df["iso_parent"] != df["iso_partner"])
for _pcol in ["profit_loss_before_income_tax_corrected", "profit_loss_before_income_tax"]:
    _p = pd.to_numeric(df[_pcol], errors="coerce")
    # I apply the multi-factor profitability (sales, employees and tangible assets) to
    # each imputed row and then rescale it within the (year, parent, source_aggregate)
    # group to conserve the reported aggregate profit.
    prof = _impute_profit_multifactor(df, _pcol, _reported, PROFIT_IMPUTATION_FACTORS).where(dist).fillna(0.0)
    agg_prof = _p.where(dist, 0.0).groupby(grp).transform("sum")
    # Sign-robust share denominator. When the signed sum of the multi-factor estimates
    # nearly cancels, the raw ratio prof/profsum explodes, because a tiny denominator
    # inflates each share. In that case I fall back to shares clipped at zero, so
    # micro-markets cannot be assigned absurd profit (e.g. Cook Islands −$294bn on $6bn
    # sales).
    _signed = prof.groupby(grp).transform("sum")
    _abssum = prof.abs().groupby(grp).transform("sum")
    _share = prof.where(
        _signed.abs() >= SIGNED_DENOMINATOR_MIN_RELATIVE * _abssum,
        prof.clip(lower=0),
    )
    _den = _share.groupby(grp).transform("sum")
    df[_pcol] = np.where(dist & (_den.abs() > 0), _share / _den * agg_prof, df[_pcol])

# %% MARK: 9. Clear the not-imputed variables on distributed rows
# 9. Clear the not-imputed variables on distributed rows.

# %%
# Imputed rows carry only the gravity-imputed activity, the derived payroll, the
# profitability-imputed profit and total_revenues, which I floor to the imputed
# unrelated-party sales because related-party revenue is not imputed. I deliberately
# leave every other CbCR variable blank on the distributed rows (tax, related-party
# revenue, stated capital, entity counts and IP holding are not imputed).
_imp_all = df["is_distributed"] == 1
df.loc[_imp_all, "total_revenues"] = pd.to_numeric(
    df.loc[_imp_all, "unrelated_party_revenues"], errors="coerce")
_NOT_IMPUTED_ON_DISTRIBUTED = [
    "related_party_revenues", "stated_capital", "n_entities",
    "holding_or_managing_ip",
    "income_tax_paid_on_cash_basis", "income_tax_accrued_current_year",
]
for _c in _NOT_IMPUTED_ON_DISTRIBUTED:
    if _c in df.columns:
        df.loc[_imp_all, _c] = np.nan
cbcr_main_disaggregated = df.drop(
    columns=[c for c in df.columns if c.startswith("_g_")] + ["_gdp_anchor", "_pop_anchor"]
)
print(f"  gravity imputation: activity + profit recomputed on {int(dist.sum())} "
      f"distributed rows; total_revenues floored to imputed sales and "
      f"tax/related/capital/entities/IP cleared on {int(_imp_all.sum())} distributed rows.")

# %% MARK: 10. Merge the market key
# 10. Merge the market key mne_plus_dds_share (1a_destination_based_sales.py), the sales
# factor of the destination formulas in script 5. I do this here, after the
# disaggregation, because the disaggregation introduces partner jurisdictions that do
# not exist after script 1, and destination-based sales are a property of the market
# jurisdiction (iso_partner, year).

# %%
# Profit-source status and the optional UK domestic-profit imputation flags describe one
# exact reported activity cell. I reattach them after the numeric disaggregation
# rebuild. They must not be treated as partner-wide ETR or activity metadata.
# is_distributed==0 means reported activity, and the source-cleaning step may
# separately flag the profit as imputed.
from _uk_domestic_profit_imputation import attach_reported_profit_metadata

cbcr_main_disaggregated = attach_reported_profit_metadata(
    cbcr_main_disaggregated, cbcr_full,
)

dest_sales = pd.read_csv(f"{data_intermediate}/destination_based_sales.csv",
                         usecols=["iso_partner", "year", "mne_plus_dds_share"])
cbcr_main_disaggregated = cbcr_main_disaggregated.merge(
    dest_sales,
    on=["iso_partner", "year"],
    how="left",
)
n_rows = len(cbcr_main_disaggregated)
n_with_key = cbcr_main_disaggregated["mne_plus_dds_share"].notna().sum()
print(f"\nMarket key merged on {n_with_key} / {n_rows} rows.")

print(f"\nFinal disaggregated dataset: {len(cbcr_main_disaggregated)} rows")
print(cbcr_main_disaggregated.head())

if not negative_wxd_warnings_all.empty:
    print(
        f"\nNegative WXD residual warnings: {len(negative_wxd_warnings_all)} "
        f"variable-level cases"
    )

if not negative_distributed_clipping_all.empty:
    print(
        f"Negative distributed values clipped to zero: "
        f"{len(negative_distributed_clipping_all)} row-variable cases"
    )


# %% MARK: 11. Save the dataset and the diagnostics
# 11. Save the dataset and the diagnostics.

# %%
# I apply the shared column order before writing.
from _column_order import COLUMNS_STAGE_2, apply_canonical_order

cbcr_main_disaggregated = apply_canonical_order(
    cbcr_main_disaggregated, COLUMNS_STAGE_2
)
# The disaggregated dataset (gravity activity and profitability profit).
cbcr_main_disaggregated.to_csv(f"{data_final}/cbcr_main_disaggregated.csv", index=False)

DISAGG_TABLES, _ = output_dirs("disaggregation")

disaggregation_diagnostics.to_csv(
    DISAGG_TABLES / "disaggregation_diagnostics.csv",
    index=False,
)

continent_total_audit_all.to_csv(
    DISAGG_TABLES / "continent_total_audit.csv",
    index=False,
)

wxd_checks_all.to_csv(
    DISAGG_TABLES / "wxd_checks.csv",
    index=False,
)

if not negative_wxd_warnings_all.empty:
    negative_wxd_warnings_all.to_csv(
        DISAGG_TABLES / "negative_wxd_residual_warnings.csv",
        index=False,
    )

if not negative_distributed_clipping_all.empty:
    negative_distributed_clipping_all.to_csv(
        DISAGG_TABLES / "negative_distributed_values_clipped.csv",
        index=False,
    )

if not flagged_inconsistent_totals_all.empty:
    flagged_inconsistent_totals_all.to_csv(
        DISAGG_TABLES / "flagged_inconsistent_continent_totals.csv",
        index=False,
    )

print("\nSaved:")
print(f"  {data_final}/cbcr_main_disaggregated.csv")
print(f"  {DISAGG_TABLES}/disaggregation_diagnostics.csv")
print(f"  {DISAGG_TABLES}/continent_total_audit.csv")
print(f"  {DISAGG_TABLES}/wxd_checks.csv")
if not negative_wxd_warnings_all.empty:
    print(f"  {DISAGG_TABLES}/negative_wxd_residual_warnings.csv")
if not negative_distributed_clipping_all.empty:
    print(f"  {DISAGG_TABLES}/negative_distributed_values_clipped.csv")
if not flagged_inconsistent_totals_all.empty:
    print(f"  {DISAGG_TABLES}/flagged_inconsistent_continent_totals.csv")


# %% MARK: 12. Reporting detail by year
# 12. Reporting detail by year: the headquarters jurisdictions in the OECD file by the
# detail of their reports (tables B1 and B2 of the methodology note). The limited-detail
# reporters are the reporter-years on EXCLUSION_CONDITIONS. I classify each by the
# partner detail of its submission (script 1, cbcr_reporter_detail.csv) as "domestic and
# rest of world only", "domestic and continents only", or "few partners or other". The
# last type holds the reporters with one to nine foreign partners and the submissions
# with more country rows that the list still treats as aggregated (Greece in 2019). The
# jurisdictions with usable country-level data are the reporting jurisdictions without
# the limited-detail reporters and without the submissions that script 1 drops.

# %%
LIMITED_DETAIL_TYPES = {
    "domestic_and_rest_of_world_only": "domestic_and_rest_of_world_only",
    "continents_only": "domestic_and_continents_only",
}
detail = pd.read_csv(f"{data_intermediate}/cbcr_reporter_detail.csv")
detail["limited_detail"] = [iso in get_excluded_parents_for_year(y)
                            for iso, y in zip(detail["iso_parent"], detail["year"])]
detail["limited_type"] = np.where(
    detail["limited_detail"],
    detail["partner_detail"].map(LIMITED_DETAIL_TYPES).fillna("few_partners_or_other"),
    "",
)
_types = ["domestic_and_rest_of_world_only", "domestic_and_continents_only", "few_partners_or_other"]
b1, b2 = [], []
for yr, d in detail.groupby("year"):
    row = {"year": yr, "reporting_jurisdictions": len(d)}
    row.update({t: int((d["limited_type"] == t).sum()) for t in _types})
    row["dropped_submissions"] = int(d["dropped_submission"].sum())
    row["usable_country_level_data"] = int((~d["limited_detail"] & ~d["dropped_submission"]).sum())
    b1.append(row)
    b2.append({"year": yr, **{t: ", ".join(sorted(d.loc[d["limited_type"] == t, "parent_jurisdiction"]))
                              for t in _types}})
b1, b2 = pd.DataFrame(b1), pd.DataFrame(b2)
b1.to_csv(DISAGG_TABLES / "reporting_detail_by_year.csv", index=False)
b2.to_csv(DISAGG_TABLES / "limited_detail_reporters_by_year.csv", index=False)
print("\nHeadquarters jurisdictions by reporting detail:")
print(b1.to_string(index=False))
print(f"  {DISAGG_TABLES}/reporting_detail_by_year.csv")
print(f"  {DISAGG_TABLES}/limited_detail_reporters_by_year.csv")


# %% MARK: 13. Check (no data changed)
# 13. Check (no data changed): conservation invariant. For every (reporter, year), the
# disaggregated output must sum back to the raw reported total for the five imputed
# variables. I print the failures beyond the tolerance (US$1 absolute, 0.01% relative)
# and write them to conservation_invariant_fails.csv. The only expected gaps come from
# the documented clip of negative distributed activity values.

# %%
#
# For every (year, iso_parent) reporter, I verify that the sum of all output rows equals
# the raw reported "total" that the disaggregation should preserve. The reference total is
#   - the domestic row (iso_partner == iso_parent in the raw input),
#   - plus the WXD value if the parent reported one,
#   - or else plus the sum of all reported continent codes and specific countries.
# I check conservation only for the imputed variables: the three gravity activity factors
# and the two profit columns (the gravity step conserves each (year, parent,
# source_aggregate) total, and the profit is rescaled to conserve it). The other CbCR
# variables are deliberately not imputed on distributed rows (total_revenues is floored
# to the imputed sales, and tax, related-party revenue, stated capital, entity counts and
# IP holding are blank), so they are not expected to conserve and are excluded from the
# check.

print("\nConservation invariant check (imputed variables only):")
CONSERVED_VARS = [
    "n_employees",
    "unrelated_party_revenues",
    "tangible_assets_except_cash",
    "profit_loss_before_income_tax_corrected",
    "profit_loss_before_income_tax",
]
INVARIANT_ATOL = 1.0   # USD or counts, tolerance for floating-point summation
INVARIANT_RTOL = 1e-4

raw_input = cbcr_full
# I sum the reported values (per parent-year and variable) without sub-totals, so
# nothing is double-counted. The domestic row plus the WXD row (if present) is the
# reference aggregate. Otherwise I sum the country and continent rows.
invariant_fails = []
for (yr, par), grp in cbcr_main_disaggregated.groupby(["year", "iso_parent"]):
    # Output sum (all output rows of this reporter)
    out_sum = grp[CBCR_VARS].sum()
    raw = raw_input[(raw_input["year"] == yr) & (raw_input["iso_parent"] == par)]
    if raw.empty:
        continue
    wxd_raw = raw[raw["iso_partner"] == "WXD"]
    dom_raw = raw[raw["iso_partner"] == par]
    if not wxd_raw.empty:
        ref_sum = (
            dom_raw[CBCR_VARS].sum().fillna(0)
            + wxd_raw[CBCR_VARS].sum().fillna(0)
        )
    else:
        # Without a WXD row, the raw input rows themselves are the reference (continent
        # codes and specific countries). The disaggregation redistributes the continent
        # codes to specific partners, but the parent-level sum is preserved.
        ref_sum = raw[CBCR_VARS].sum().fillna(0)
    for var in CONSERVED_VARS:
        ov = float(out_sum.get(var, 0) or 0)
        rv = float(ref_sum.get(var, 0) or 0)
        if abs(ov - rv) > max(INVARIANT_ATOL, INVARIANT_RTOL * max(abs(rv), 1.0)):
            invariant_fails.append({
                "year": yr, "iso_parent": par, "variable": var,
                "raw_total": rv, "output_total": ov, "diff": ov - rv,
            })
if invariant_fails:
    ifd = pd.DataFrame(invariant_fails)
    ifd.to_csv(DISAGG_TABLES / "conservation_invariant_fails.csv", index=False)
    print(f"  FAIL: {len(invariant_fails)} (parent, year, variable) cells "
          f"failed conservation invariant")
    print(f"     details -> {DISAGG_TABLES}/conservation_invariant_fails.csv")
    # Top offenders
    worst = ifd.reindex(ifd['diff'].abs().sort_values(ascending=False).index).head(10)
    print("  Top 10 by absolute diff:")
    for _, r in worst.iterrows():
        print(f"    {int(r['year'])} {r['iso_parent']:<3s} {r['variable']:<40s} "
              f"raw={r['raw_total']:>15,.1f} out={r['output_total']:>15,.1f} "
              f"diff={r['diff']:>+12,.1f}")
else:
    print("  PASS: every parent-year disaggregated total matches the raw "
          "reported total within tolerance")


# %%
print(cbcr_main_disaggregated.columns.tolist())

# %%
