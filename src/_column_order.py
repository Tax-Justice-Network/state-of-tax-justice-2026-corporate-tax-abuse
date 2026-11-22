"""
Canonical column ordering for the cbcr_main_* datasets.

This module defines the column order of the cbcr_main_* datasets. The order is
meant for human inspection:
  1. Identifiers (parent / partner ISO codes, country names, year)
  2. Time-invariant country characteristics (region, income group, OECD, ...)
  3. Country macro variables (CIT rate, GDP, population, wages)
  4. Primary CbCR variables (profit, taxes, revenues, employees, assets)
  5. Derived ETRs
  6. Logged variables (analytical helpers, only in the wider output of script 1)
  7. Disaggregation metadata (is_distributed, distribution_source, ...)

Each list below holds the columns of one stage's output. `apply_canonical_order(df, cols)`
puts the listed columns first (in the order given) and appends any other columns
at the end in alphabetical order, so unexpected fields are kept, not lost.
"""

# %%

# Stage 1: cbcr_main.csv / cbcr_main_allsubgroupsonly.csv
# Output of src/1_clean.py
COLUMNS_STAGE_1 = [
    # Identifiers
    "year",
    "iso_parent",
    "parent_jurisdiction",
    "iso_partner",
    "partner_jurisdiction",
    "grouping",
    # Country characteristics (time-invariant)
    "region_tjn",
    "wb_income_group",
    "wb_income_group_3",
    "wb_income_group_official",
    "wb_income_group_id",
    "wb_income_group_id_official",
    "ukt",
    "oecd",
    "oecd_oct",
    "eu27",
    # Country macro (varying)
    "cit",
    "gdp_current_usd",
    "population",
    "wage_monthly",
    "payroll",
    # CbCR primary (analytics-relevant ones first)
    "profit_loss_before_income_tax_corrected",
    "profit_loss_before_income_tax",
    "adjusted_profit_loss_before_income_tax",
    "income_tax_paid_on_cash_basis",
    "income_tax_accrued_current_year",
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
    "total_revenues",
    "related_party_revenues",
    "stated_capital",
    "n_entities",
    "holding_or_managing_ip",
    # CbCR-derived ETRs
    "etr_domestic",
    "etr_domestic_corrected",
    "etr_foreign",
    "etr_foreign_corrected",
    "etr_average",
    "etr_average_corrected",
    "etr_partner_median_corrected",
    "etr_partner_p25_corrected",
    "etr_partner_p10_corrected",
    "etr_partner_min_corrected",
    "etr_parent_partner_corrected",
    # Logged variables (analytical helpers)
    "ln_profit_loss_before_income_tax_corrected",
    "ln_unrelated_party_revenues",
    "ln_n_employees",
    "ln_tangible_assets_except_cash",
    "ln_total_revenues",
    "ln_related_party_revenues",
    "ln_stated_capital",
    "ln_holding_or_managing_ip",
    "ln_wage_monthly",
    "ln_gdp_current_usd",
    "ln_population",
    "ln_gvt_health_expenditure",
    # Counts (metadata)
    "n_cbcr",
    "n_cbcr_groups",
]


# Stage 2: cbcr_main_disaggregated.csv
# Output of src/2_disaggregate_aggregated_values.py
COLUMNS_STAGE_2 = [
    # Identifiers
    "year",
    "iso_parent",
    "iso_partner",
    "partner_jurisdiction",
    # Country characteristics (time-invariant)
    "region_tjn",
    "wb_income_group",
    "ukt",
    "oecd",
    "oecd_oct",
    "eu27",
    # Country macro
    "cit",
    "wage_monthly",
    "payroll",
    # CbCR primary
    "profit_loss_before_income_tax_corrected",
    "profit_loss_before_income_tax",
    "income_tax_paid_on_cash_basis",
    "income_tax_accrued_current_year",
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
    "total_revenues",
    "related_party_revenues",
    "stated_capital",
    "n_entities",
    "holding_or_managing_ip",
    # CbCR ETRs
    "etr_domestic_corrected",
    "etr_foreign_corrected",
    "etr_average_corrected",
    "etr_partner_median_corrected",
    "etr_partner_p25_corrected",
    "etr_partner_p10_corrected",
    "etr_partner_min_corrected",
    "etr_parent_partner_corrected",
    # CbCR group count: metadata of the parent-partner pair and year, missing (NaN)
    # on distributed rows like the pair ETR.
    "n_cbcr",
    # Disaggregation metadata (last in CbCR-only datasets)
    "is_distributed",
    "distribution_source",
    "source_aggregate_code",
]


def apply_canonical_order(df, canonical):
    """Returns df with its columns reordered to follow `canonical`. I append the
    columns that are not in `canonical` at the end in alphabetical order, so that
    any unexpected field is kept rather than silently dropped.
    """
    known = [c for c in canonical if c in df.columns]
    extra = sorted(set(df.columns) - set(known))
    return df[known + extra]
