# %%
"""
3_25 — Build the consolidated country x year royalty panel.

This script builds the consolidated panel of government resource revenue (one row per
country x year over config.ANALYSIS_YEARS). I fill each cell from the matching year only,
with no cross-year imputation within a row. The 3_3x headquarter x source chain (3_38) reads
the panel within the CbCR window.

Section outline (numbers match the cell headings below):
1. Setup.
2. Config and helpers.
3. Build yearly panel.

Pipeline: Extractive prep, stage 3_25 — after 3_24, before 3_26.

Reads:
  data/raw/extractive/wb_resource_rents.csv             — WB resource rents, year-stamped (3_15)
  config.canonical_gdp_data (data/raw/macro_variables/wb_gdp_current_usd_<vintage>.csv)
                                                        — canonical WB WDI GDP (NY.GDP.MKTP.CD)
  data/intermediate/extractive/grd_resource_revenue.csv — GRD government resource revenue (3_14)
  data/raw/macro_variables/wb_fx_official_rate_2026-02.csv — WB official FX rate
  data/intermediate/extractive/eiti_revenues.csv        — EITI country revenues (3_11)
  data/raw/extractive/manual_resource_revenue_fills.csv — hand-curated revenue fills

Writes:
  data/intermediate/extractive/extractive_royalty_dataset_yearly.csv — long iso3 x year panel
    (3_26_apply_classification_fixes.py then rebuckets carried-state rows in place)

Usage:
  python src/3_extractive_prep/3_25_build_consolidated_yearly.py

Author: Tax Justice Network.
Created: 2026-07-17.  Last updated: 2026-11-23.
"""

# %% MARK: 1. Setup
import os
import csv
import sys
from collections import defaultdict
from _paths import RAW, EXT_INT

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# %% MARK: 2. Config and helpers
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from config import ANALYSIS_YEARS as _ANALYSIS_YEARS  # the CbCR window (config.py)
from config import canonical_gdp_data as _CANONICAL_GDP  # same GDP vintage as 1_clean
YEARS = list(_ANALYSIS_YEARS)   # the CbCR analysis window


def _f(s):
    if s is None:
        return None
    s = str(s).strip()
    if not s or s.lower() in ("n.a.", "nan", "none", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# %% MARK: 3. Build yearly panel
def main():
    # ---- 1. WB resource rents — keyed by (iso, year) ----
    print("Reading WB resource rents...")
    wb = defaultdict(dict)
    with open(RAW / "extractive" / "wb_resource_rents.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            iso = row["country_iso3"]
            try: yr = int(row["year"])
            except: continue
            if yr not in YEARS:
                continue
            wb[iso][yr] = row

    # The canonical GDP (the single WB WDI series of the repository, NY.GDP.MKTP.CD) overrides
    # the GDP column of wb_resource_rents, so that the whole repository shares one GDP per
    # country-year (the same file that 1_clean uses). I use it as the reference of the GRD guard
    # and for the % × GDP fallback. I leave the WB rents in USD (used only for commodity ratios)
    # as they are, because they are scale-invariant.
    canon_gdp = {}
    with open(_CANONICAL_GDP, encoding="utf-8") as f:
        for _ln in f:
            if _ln.startswith("#") or _ln.startswith("iso3"):
                continue
            _p = _ln.rstrip("\n").split(",")
            if len(_p) >= 3:
                try:
                    canon_gdp[(_p[0], int(_p[1]))] = float(_p[2])
                except ValueError:
                    pass

    # ---- 2. GRD — per (iso, year) ----
    print("Reading GRD...")
    GRD_FIELDS = [
        "total_resource_rev", "resource_taxes", "cit_resource",
        "tax_income_profits_capgains_resource", "indirect_taxes_resource",
        "nontax_rev_resource", "total_rev_exgrants_exsc",
    ]
    grd = defaultdict(dict)  # (iso, year) -> field -> value (fraction of GDP)
    grd_gdp_lcu = {}         # (iso, year) -> the GRD's own GDP in LCU (absolute)
    with open(EXT_INT / "grd_resource_revenue.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            iso = row["iso"]
            try: yr = int(float(row["year"]))
            except: continue
            if yr not in YEARS:
                continue
            for fld in GRD_FIELDS:
                v = _f(row.get(fld))
                if v is not None and v != 0:
                    grd[(iso, yr)][fld] = v
            _glcu = _f(row.get("gdp_lcu_mn"))
            if _glcu is not None:
                grd_gdp_lcu[(iso, yr)] = _glcu * 1e6   # millions -> absolute LCU

    # ---- 2b. FX — WB period-average official rate (PA.NUS.FCRF), LCU per USD ----
    # I use it to convert the GRD resource revenue from % of GDP to USD with the GRD's own
    # gdp_lcu (usd = % x gdp_lcu / FX). This keeps the GRD figure internally consistent, instead
    # of multiplying the GRD % by an external (possibly rebased) WB GDP in USD. Resource revenue
    # is a full-year flow, so I use the period-average rate.
    print("Reading FX (period-average official rate)...")
    fx = {}   # (iso, year) -> LCU per USD (period average)
    with open(RAW / "macro_variables/wb_fx_official_rate_2026-02.csv", encoding="utf-8-sig") as f:
        _fx_lines = f.readlines()
    for row in csv.DictReader(_fx_lines[4:]):   # 4 metadata rows precede the header
        iso = row.get("Country Code")
        if not iso:
            continue
        for yr in YEARS:
            v = _f(row.get(str(yr)))
            if v is not None and v > 0:
                fx[(iso, yr)] = v

    # ---- 3. EITI — per (iso, year), all payment types ----
    print("Reading EITI...")
    EITI_FIELD_MAP = {
        "total_rev":            "revenue_government_total_usd",
        "royalties":            "Royalties",
        "bonuses":              "Bonuses",
        "production_ent":       "Production entitlements (in-kind or cash)",
        "licence_fees":         "Licence fees",
        "other_rent":           "Other rent payments",
        "delivered_directly":   "Delivered/paid directly to government",
        "rent":                 "Rent",
        "customs":              "Customs and other import duties",
        "excise":               "Excise taxes",
        "export_tax":           "Taxes on exports",
        "property_tax":         "Taxes on property",
        "payroll_tax":          "Taxes on payroll and workforce",
        "other_taxes_natres":   "Other taxes payable by natural resource companies",
        "admin_fees":           "Administrative fees for government services",
        "compulsory_transfers": "Compulsory transfers to government (infrastructure and other)",
        "fines":                "Fines, penalties, and forfeits",
        "emission_tax":         "Emission and pollution taxes",
        "motor_vehicle":        "Motor vehicle taxes",
        "cit":                  "Ordinary taxes on income, profits and capital gains",
        "extraordinary_cit":    "Extraordinary taxes on income, profits and capital gains",
        "soe_profits":          "Profits of natural resource export monopolies",
        "from_soe":             "From state-owned enterprises",
        "dividends":            "Dividends",
        "govt_participation":   "From government participation (equity)",
        "delivered_to_soe":     "Delivered/paid to state-owned enterprise(s)",
        "quasi_corp":           "Withdrawals from income of quasi-corporations",
        "vat":                  "General taxes on goods and services (VAT, sales tax, turnover tax)",
    }
    DEDUCTIBLE_KEYS = (
        "royalties", "bonuses", "production_ent", "licence_fees", "other_rent",
        "delivered_directly", "rent", "customs", "excise", "export_tax",
        "property_tax", "payroll_tax", "other_taxes_natres", "admin_fees",
        "compulsory_transfers", "fines", "emission_tax", "motor_vehicle",
    )
    CIT_KEYS = ("cit", "extraordinary_cit")
    EQUITY_KEYS = (
        "soe_profits", "from_soe", "dividends",
        "govt_participation", "delivered_to_soe", "quasi_corp",
    )

    eiti = defaultdict(dict)  # (iso, year) -> key -> value
    with open(EXT_INT / "eiti_revenues.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            iso = row.get("country_iso3", "")
            try: yr = int(row["year"])
            except: continue
            if yr not in YEARS:
                continue
            for key, col in EITI_FIELD_MAP.items():
                v = _f(row.get(col))
                if v is not None and v > 0:
                    eiti[(iso, yr)][key] = v

    # ---- 4. Manual fills — keyed by iso (single year per row) ----
    print("Reading manual fills...")
    manual = {}
    manual_path = RAW / "extractive" / "manual_resource_revenue_fills.csv"
    if manual_path.exists():
        with open(manual_path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                parts = next(csv.reader([line]))
                if parts and parts[0] == "iso3":
                    continue
                if len(parts) < 5:
                    continue
                iso = parts[0].strip()
                val = _f(parts[2])
                try: yr = int(parts[3])
                except: yr = None
                src = parts[4].strip() if len(parts) > 4 else ""
                prefer = parts[6].strip().upper() in ("TRUE", "1", "YES") if len(parts) > 6 else False
                if iso and val and val > 0:
                    # I snap the manual year onto the panel. A fill without a year or dated
                    # after the last panel year goes to the last panel year, and a fill dated
                    # before the first panel year goes to the first.
                    yr_orig = yr
                    if yr is None:
                        yr_panel = max(YEARS)
                    elif yr < min(YEARS):
                        yr_panel = min(YEARS)
                    elif yr > max(YEARS):
                        yr_panel = max(YEARS)
                    else:
                        yr_panel = yr
                    manual[iso] = {
                        "value": val,
                        "year": yr_panel,
                        "year_orig": yr_orig,
                        "source": src,
                        "prefer_over_eiti": prefer,
                    }

    # ---- 5. Build long-format output ----
    print(f"\nBuilding panel for years {YEARS}...")
    iso_universe = set(wb.keys()) | {k[0] for k in grd} | {k[0] for k in eiti} | set(manual.keys())
    rows_out = []

    for iso in sorted(iso_universe):
        for yr in YEARS:
            row = {"iso3": iso, "year": yr}

            # WB rents
            wb_row = wb[iso].get(yr, {}) if iso in wb else {}
            for k in ("total_rents_pct_gdp", "oil_rents_pct_gdp", "gas_rents_pct_gdp",
                      "coal_rents_pct_gdp", "mineral_rents_pct_gdp", "forest_rents_pct_gdp",
                      "total_rents_usd", "oil_rents_usd", "gas_rents_usd",
                      "coal_rents_usd", "mineral_rents_usd", "forest_rents_usd",
                      "gdp_current_usd"):
                v = _f(wb_row.get(k)) if wb_row else None
                row[f"wb_{k}"] = v if v is not None else ""

            # I override the GDP with the canonical series of the repository where available.
            _canon = canon_gdp.get((iso, yr))
            if _canon is not None:
                row["wb_gdp_current_usd"] = _canon
            gdp = _f(row["wb_gdp_current_usd"])   # WB GDP in USD, for the WB-rents conversion and the GRD fallback

            # GRD in USD: I reconstruct it from the GRD's own GDP (LCU) and the period-average FX
            # rate (usd = % × gdp_lcu ÷ FX), which keeps the GRD figure internally consistent (its
            # % was measured against gdp_lcu).
            # Guard: the implied GDP in USD (gdp_lcu ÷ FX) must be within a factor of 3 of the WB
            # GDP in USD. This admits genuine GDP revisions (Angola +17%, Nigeria −29%) but
            # rejects the unit mismatches of currency redenominations, where the GRD's gdp_lcu
            # (old units) and the WB FX rate (new units) disagree by about 10 to 1000 times
            # (Zambia, Sierra Leone and São Tomé ÷1000, Mauritania ÷10). These cases fall back to
            # % × WB GDP in USD.
            gdp_lcu = grd_gdp_lcu.get((iso, yr))
            fx_yr = fx.get((iso, yr))
            implied = (gdp_lcu / fx_yr) if (gdp_lcu is not None and fx_yr) else None
            lcu_ok = (implied is not None and gdp and (1 / 3) <= implied / gdp <= 3)
            row["grd_gdp_lcu_mn"] = f"{gdp_lcu / 1e6:.0f}" if gdp_lcu is not None else ""
            row["fx_period_avg_lcu_per_usd"] = f"{fx_yr:.4f}" if fx_yr else ""
            row["grd_usd_method"] = "lcu_fx" if lcu_ok else ("wb_gdp" if gdp else "")
            grd_yr = grd.get((iso, yr), {})
            for fld in GRD_FIELDS:
                v = grd_yr.get(fld)
                row[f"grd_{fld}_frac_gdp"] = f"{v:.6f}" if v is not None else ""
                if v is None:
                    row[f"grd_{fld}_usd"] = ""
                elif lcu_ok:
                    row[f"grd_{fld}_usd"] = f"{v * gdp_lcu / fx_yr:.0f}"
                elif gdp:
                    row[f"grd_{fld}_usd"] = f"{v * gdp:.0f}"
                else:
                    row[f"grd_{fld}_usd"] = ""

            # EITI
            eiti_yr = eiti.get((iso, yr), {})
            for key in EITI_FIELD_MAP:
                v = eiti_yr.get(key)
                row[f"eiti_{key}_usd"] = f"{v:.0f}" if v is not None else ""

            # EITI rollups
            ded = sum(eiti_yr.get(k, 0) for k in DEDUCTIBLE_KEYS)
            cit = sum(eiti_yr.get(k, 0) for k in CIT_KEYS)
            eq = sum(eiti_yr.get(k, 0) for k in EQUITY_KEYS)
            vat = eiti_yr.get("vat", 0) or 0
            tot = eiti_yr.get("total_rev", 0) or 0
            row["eiti_deductible_usd"] = f"{ded:.0f}" if ded > 0 else ""
            row["eiti_cit_usd_rollup"] = f"{cit:.0f}" if cit > 0 else ""
            row["eiti_equity_usd"] = f"{eq:.0f}" if eq > 0 else ""

            # Captured columns: a fixed source priority, applied per year
            grd_total = _f(row.get("grd_total_resource_rev_usd"))
            eiti_total = tot if tot > 0 else None
            man = manual.get(iso)
            man_prefers = bool(man and man.get("prefer_over_eiti"))
            man_year_match = man and man.get("year") == yr

            man_src_label = (
                f"MANUAL(y{man['year_orig']}):{man['source'][:50]}" if man else ""
            )
            if grd_total:
                row["captured_total_usd"] = f"{grd_total:.0f}"
                row["captured_total_source"] = "GRD"
            elif man_prefers and man_year_match:
                row["captured_total_usd"] = f"{man['value']:.0f}"
                row["captured_total_source"] = man_src_label
            elif eiti_total:
                row["captured_total_usd"] = f"{eiti_total:.0f}"
                row["captured_total_source"] = "EITI"
            elif man and man_year_match:
                row["captured_total_usd"] = f"{man['value']:.0f}"
                row["captured_total_source"] = man_src_label
            else:
                row["captured_total_usd"] = ""
                row["captured_total_source"] = ""

            # Captured deductible: I prefer the EITI rollup, with GRD indirect + non-tax revenue as the
            # fallback.
            grd_indirect = _f(row.get("grd_indirect_taxes_resource_usd")) or 0
            grd_nontax = _f(row.get("grd_nontax_rev_resource_usd")) or 0
            if ded > 0:
                row["captured_deductible_usd"] = f"{ded:.0f}"
                row["captured_deductible_source"] = "EITI_rollup"
            elif grd_indirect + grd_nontax > 0:
                row["captured_deductible_usd"] = f"{grd_indirect + grd_nontax:.0f}"
                row["captured_deductible_source"] = "GRD_indirect+nontax_proxy"
            else:
                row["captured_deductible_usd"] = ""
                row["captured_deductible_source"] = ""

            # Captured CIT
            grd_cit = _f(row.get("grd_cit_resource_usd"))
            if grd_cit:
                row["captured_cit_usd"] = f"{grd_cit:.0f}"
                row["captured_cit_source"] = "GRD"
            elif cit > 0:
                row["captured_cit_usd"] = f"{cit:.0f}"
                row["captured_cit_source"] = "EITI_rollup"
            else:
                row["captured_cit_usd"] = ""
                row["captured_cit_source"] = ""

            # Captured equity
            if eq > 0:
                row["captured_equity_usd"] = f"{eq:.0f}"
                row["captured_equity_source"] = "EITI_rollup"
            else:
                row["captured_equity_usd"] = ""
                row["captured_equity_source"] = ""

            # I emit a row only if WB rents or captured data exist.
            if any(row.get(c) for c in ["wb_total_rents_usd", "captured_total_usd", "captured_deductible_usd"]):
                rows_out.append(row)

    # Write
    cols = list(rows_out[0].keys())
    outpath = EXT_INT / "extractive_royalty_dataset_yearly.csv"
    with open(outpath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for r in rows_out:
            writer.writerow(r)

    print(f"\nSaved: {outpath}  ({len(rows_out):,} rows)")

    # Statistics
    n_with_total = sum(1 for r in rows_out if r["captured_total_usd"])
    n_with_ded = sum(1 for r in rows_out if r["captured_deductible_usd"])
    n_with_cit = sum(1 for r in rows_out if r["captured_cit_usd"])
    n_with_eq = sum(1 for r in rows_out if r["captured_equity_usd"])
    print(f"\nCoverage (across {len(rows_out)} country-year rows):")
    print(f"  captured_total:      {n_with_total}")
    print(f"  captured_deductible: {n_with_ded}")
    print(f"  captured_cit:        {n_with_cit}")
    print(f"  captured_equity:     {n_with_eq}")


if __name__ == "__main__":
    main()
