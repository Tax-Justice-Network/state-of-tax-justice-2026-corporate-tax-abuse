# %%
"""
Formula comparison machinery for the unitary-taxation estimates.

This module builds the per-country and per-group results behind the formula tables and figures of 7b. It reads the
script-6 summary of a sample (resources excluded) on the headline effective tax rates (domestic/foreign) and rate
mode (profit a country gets back at its statutory rate, profit it forgoes at its effective rate). Every country-year
money value is deflated to constant BASE_YEAR US$ and multiplied by the world scale factor of its year
(_host_coverage, table written by 7a) before any aggregation, following the presentation rule for aggregates. One
year at a time, I sum per (country, formula) and aggregate to income groups and the world, with the percentages
recomputed from the scaled sums.

Per (country, formula) row, the summary carries
    formula_name, iso_partner, partner_jurisdiction, wb_income_group
    previous_profits_musd                          reported profit (the sample's baseline)
    posbase_musd                                   positive reported profit (clipped at zero)
    current_tax_paid_cash_musd                     corporate tax the sample's multinationals pay today (cash basis)
    delta_taxable_profits_musd                     theoretical minus reported profit
    delta_tax_revenue_recCIT_forgETR_musd          change in tax revenue under unitary taxation

The group aggregates add
    cash_tax_pos_musd                              tax paid today, summed over the countries that pay a positive amount
    delta_tax_revenue_recCIT_forgETR_pct_revenue   change in tax revenue as % of cash_tax_pos_musd
    delta_taxable_profits_pct_posbase              change in taxable profit as % of the positive profit base

Section outline (numbers match the cell headings below):
1. Settings.
2. Loading a sample's summary.
3. Summary per country and formula.
4. Aggregation to income groups and the world.
5. Group aggregates of the latest year and of every year.

Shared module — imported by _exhibit_helpers. It is not run on its own.

Author: Tax Justice Network.
Last updated: 2026-11-22.
"""

import numpy as np
import pandas as pd

import config
import _host_coverage as _hc

# %% MARK: 1. Settings
ETR = "domfor"                 # the headline effective tax rates: domestic rate on the domestic cell, foreign elsewhere
RATE = "loss_cit_gain_etr"     # profit a country gets back at its statutory rate, profit it forgoes at its rate
REV = "delta_tax_revenue_recCIT_forgETR_musd"
REV_PCT = "delta_tax_revenue_recCIT_forgETR_pct_revenue"
LATEST_YEAR = config.last_year
YEARS_ALL = list(config.ANALYSIS_YEARS)
INCOME_GROUP_ORDER = ["low_income", "lower_middle_income", "upper_middle_income", "high_income", "tax_haven"]
# Group key of the all-country aggregate rows.
WORLD_KEY = "world"
_MONEY = ["theoretical_profit", "reported_profit", "revenue_gain_from_ut", "current_tax_paid_cash_musd"]


# %% MARK: 2. Loading a sample's summary
_LONG_CACHE = {}


def summary_path(sample):
    """Return the script-6 summary of a sample ("reported_only" or "gravity"), resources excluded."""
    return config.estimates_dir(sample, "excl_resource") / "tables" / "summary_country_year_long.csv"


def _read_long(sample):
    """Read the summary of a sample on the headline effective tax rates and rate mode, once per sample."""
    if sample not in _LONG_CACHE:
        cols = ["sample_name", "formula_name", "etr_name", "rate_mode", "iso_partner", "partner_jurisdiction",
                "wb_income_group", "year"] + _MONEY
        df = pd.read_csv(summary_path(sample), low_memory=False, usecols=lambda c: c in cols)
        _LONG_CACHE[sample] = df[(df["sample_name"] == "excl_resource") & (df["etr_name"] == ETR)
                                 & (df["rate_mode"] == RATE)].copy()
    return _LONG_CACHE[sample]


# %% MARK: 3. Summary per country and formula
def build_summary(year, sample, formulas):
    """Return the summary per (formula, country) of one year, deflated and scaled, and the tax paid today summed per
    (formula, income group) over the countries that pay a positive amount (with the world as group WORLD_KEY)."""
    df = _read_long(sample)
    df = df[df["formula_name"].isin(formulas) & (df["year"] == year)].copy()
    defl = df["year"].map(config.deflator_to_base())
    f = _hc.factor_for(df, sample)
    for c in _MONEY:
        df[c] = pd.to_numeric(df[c], errors="coerce") * defl * f
    df["delta_taxable_profits_musd"] = df["theoretical_profit"] - df["reported_profit"]
    # The denominator of the revenue percentages of a group: the tax paid today, summed over the countries that pay a
    # positive amount. The numerator is the full group sum, so the USD and the % panels always rank the groups alike.
    pos = df[df["current_tax_paid_cash_musd"] > 0]
    pos = pd.concat([pos, pos.assign(wb_income_group=WORLD_KEY)], ignore_index=True)
    cash_pos = (pos.groupby(["formula_name", "wb_income_group"])["current_tax_paid_cash_musd"].sum()
                .reset_index().rename(columns={"current_tax_paid_cash_musd": "cash_tax_pos_musd"}))
    # The positive profit base: a loss-making country contributes its change but no base.
    df["_reported_pos"] = df["reported_profit"].clip(lower=0)
    summary = df.groupby(["formula_name", "iso_partner", "partner_jurisdiction", "wb_income_group"],
                         as_index=False, dropna=False).agg(
        previous_profits_musd=("reported_profit", "sum"),
        posbase_musd=("_reported_pos", "sum"),
        delta_taxable_profits_musd=("delta_taxable_profits_musd", "sum"),
        **{REV: ("revenue_gain_from_ut", "sum")},
        current_tax_paid_cash_musd=("current_tax_paid_cash_musd", "sum"),
    )
    return summary, cash_pos


# %% MARK: 4. Aggregation to income groups and the world
_SUM_COLS = ["previous_profits_musd", "posbase_musd", "delta_taxable_profits_musd", REV, "current_tax_paid_cash_musd"]


def _safe_pct_positive_base(numer, denom):
    """Return 100 × numer ÷ denom where denom is strictly positive, NaN elsewhere. A percentage of a negative base
    would flip the sign of the change."""
    out = 100 * pd.to_numeric(numer, errors="coerce") / pd.to_numeric(denom, errors="coerce")
    return out.where(pd.to_numeric(denom, errors="coerce") > 0, np.nan).replace([np.inf, -np.inf], np.nan)


def build_by_income(summary, cash_pos, world=False):
    """Aggregate a summary to income groups, with world=True also to the world (group WORLD_KEY). I sum every money
    column and recompute the percentages from the sums: the change in tax revenue as % of the tax paid today by the
    countries that pay a positive amount, and the change in taxable profit as % of the group's positive profit base."""
    if world:
        return pd.concat([build_by_income(summary, cash_pos),
                          build_by_income(summary.assign(wb_income_group=WORLD_KEY), cash_pos)], ignore_index=True)
    g = summary.groupby(["formula_name", "wb_income_group"], as_index=False, dropna=False)[_SUM_COLS].sum()
    g = g.merge(cash_pos, on=["formula_name", "wb_income_group"], how="left")
    cash = pd.to_numeric(g["cash_tax_pos_musd"], errors="coerce")
    g[REV_PCT] = np.where(cash > 0, pd.to_numeric(g[REV], errors="coerce") / cash * 100.0, np.nan)
    g["delta_taxable_profits_pct_posbase"] = _safe_pct_positive_base(g["delta_taxable_profits_musd"], g["posbase_musd"])
    return g


# %% MARK: 5. Group aggregates of the latest year and of every year
def latest_by_group(sample, formulas):
    """Return the group aggregates (with the world) of the latest year, with a year column."""
    b = build_by_income(*build_summary(LATEST_YEAR, sample, formulas), world=True)
    b.insert(0, "year", LATEST_YEAR)
    return b


def yearly_by_group(sample, formulas):
    """Return the group aggregates (with the world) of every year of the analysis window, with a year column."""
    parts = []
    for y in YEARS_ALL:
        b = build_by_income(*build_summary(y, sample, formulas), world=True)
        b.insert(0, "year", y)
        parts.append(b)
    return pd.concat(parts, ignore_index=True)
