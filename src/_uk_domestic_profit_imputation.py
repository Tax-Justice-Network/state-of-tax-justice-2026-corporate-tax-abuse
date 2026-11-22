"""Fill the suppressed UK domestic total profit for one explicitly configured missing year.

The OECD suppresses the UK-parent domestic Total profit for FY2023. This module fills it (it is called from
1_clean.py) with the published positive-profit panel of the missing year plus the average loss-panel profit over
earlier years (config.UK_DOMESTIC_PROFIT_RATIO_YEARS). I preserve the raw reported-profit column, the source
observation status and every non-profit input. The filled value is a flagged estimate, not an OECD observation.

Author: Tax Justice Network. Last updated: 2026-11-23.
"""
from pathlib import Path
from math import isfinite

import pandas as pd


IMPUTATION_COLUMNS = [
    "profit_loss_is_imputed", "profit_loss_imputation_source_year",
    "profit_loss_imputation_method", "profit_loss_imputation_source_file",
]
AUDIT_COLUMNS = [
    "iso_parent", "iso_partner", "grouping", "target_year", "source_year",
    "original_reported_profit_usd", "original_corrected_profit_usd",
    "original_profit_observation_status", "source_reported_profit_usd",
    "source_corrected_profit_usd", "imputed_corrected_profit_usd",
    "method", "source_file", "source_vintage", "source_column",
]
PROFIT_METADATA_COLUMNS = ["profit_observation_status"] + IMPUTATION_COLUMNS


def fill_uk_domestic_profit(frame, *, enabled, target_year, source_years, source_file):
    """Return a copied frame and an audit, filling only the missing UK domestic Total.

    The Total is the published positive panel of the target year plus the average loss-panel profit over
    `source_years` (the years whose loss panel has positive total revenues). I leave the negative panel itself
    missing. Only the Total enters the unitary-taxation pool, and the ETR base uses the positive panel.
    """
    result = frame.copy()
    for column, default in [("profit_loss_is_imputed", False)]:
        if column not in result:
            result[column] = default
    if "profit_loss_imputation_source_year" not in result:
        result["profit_loss_imputation_source_year"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    for column in ["profit_loss_imputation_method", "profit_loss_imputation_source_file"]:
        if column not in result:
            result[column] = ""
    audit = pd.DataFrame(columns=AUDIT_COLUMNS)
    if not enabled:
        return result, audit
    TOT, POS, NEG = ("Total (All sub-groups)", "Sub-groups with positive profits", "Sub-groups with negative profits")
    home = (result.iso_parent == "GBR") & (result.iso_partner == "GBR")
    target = home & (result.grouping == TOT) & (result.year == target_year)
    if target.sum() != 1:
        return result, audit
    idx = result.index[target][0]
    if (pd.notna(result.at[idx, "profit_loss_before_income_tax"])
            or pd.notna(result.at[idx, "profit_loss_before_income_tax_corrected"])):
        return result, audit                      # a released (or already filled) value is kept
    pos = pd.to_numeric(result.loc[home & (result.grouping == POS) & (result.year == target_year),
                                   "profit_loss_before_income_tax_corrected"], errors="coerce")
    if len(pos) != 1 or pd.isna(pos.iloc[0]):
        raise ValueError("The UK imputation needs the target year's positive panel.")
    hist = result.loc[home & (result.grouping == NEG) & result.year.isin(source_years),
                      ["year", "profit_loss_before_income_tax_corrected", "total_revenues"]].apply(pd.to_numeric, errors="coerce")
    hist = hist[(hist.total_revenues > 0) & hist.profit_loss_before_income_tax_corrected.notna()]
    if len(hist) < 3:
        raise ValueError("The UK imputation needs at least three earlier loss-panel years.")
    loss = float(hist.profit_loss_before_income_tax_corrected.mean())
    method = f"positive_panel_plus_mean_loss_panel_v3 ({int(hist.year.min())}-{int(hist.year.max())})"
    value = float(pos.iloc[0]) + loss
    if not isfinite(value):
        raise ValueError("The UK imputation produced a non-finite value.")
    record = {
        "iso_parent": "GBR", "iso_partner": "GBR", "grouping": TOT, "target_year": target_year,
        "source_year": int(hist.year.max()),
        "original_reported_profit_usd": result.at[idx, "profit_loss_before_income_tax"],
        "original_corrected_profit_usd": result.at[idx, "profit_loss_before_income_tax_corrected"],
        "original_profit_observation_status": result.loc[idx].get("profit_observation_status", pd.NA),
        "source_reported_profit_usd": float(pos.iloc[0]), "source_corrected_profit_usd": loss,
        "imputed_corrected_profit_usd": value, "method": method, "source_file": str(source_file),
        "source_vintage": Path(source_file).name,
        "source_column": "positive panel + loss panel (profit_loss_before_income_tax_corrected, total_revenues)",
    }
    for column in ["profit_loss_imputation_method", "profit_loss_imputation_source_file"]:
        result[column] = result[column].astype("object")
    result.at[idx, "profit_loss_before_income_tax_corrected"] = value
    result.at[idx, "profit_loss_is_imputed"] = True
    result.at[idx, "profit_loss_imputation_source_year"] = int(hist.year.max())
    result.at[idx, "profit_loss_imputation_method"] = method
    result.at[idx, "profit_loss_imputation_source_file"] = str(source_file)
    return result, pd.DataFrame([record], columns=AUDIT_COLUMNS)


def attach_reported_profit_metadata(disaggregated, reported_input):
    """Carry the optional profit provenance onto the reported activity rows, matched by exact pair-year.

    I carry only the provenance columns that the input has. Distributed activity rows receive no raw status,
    method or source attribution, so they cannot inherit the imputation flag of the UK home cell.
    """
    available = [c for c in PROFIT_METADATA_COLUMNS if c in reported_input.columns]
    if not available:
        return disaggregated.copy()
    keys = ["iso_parent", "iso_partner", "year"]
    metadata = reported_input[keys + available].copy()
    result = disaggregated.drop(columns=available, errors="ignore").merge(
        metadata, on=keys, how="left", validate="many_to_one",
    )
    reported = result["is_distributed"].eq(0)
    for column in available:
        if column == "profit_loss_is_imputed":
            result[column] = result[column].astype("boolean").fillna(False) & reported
        elif column == "profit_loss_imputation_source_year":
            result[column] = result[column].astype("Int64").where(reported)
        else:
            result[column] = result[column].astype("string").where(reported)
    return result
