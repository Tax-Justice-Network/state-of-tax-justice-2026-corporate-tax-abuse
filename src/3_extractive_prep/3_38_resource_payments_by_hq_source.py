# %%
"""
3_38 — Final cascade: resource payments by HQ × source × commodity × year.

This script brings the resource-related government payments to the level of source country × HQ country ×
commodity × year. Script 4 (4_correcting_cbcr_for_resource_payments.py) uses this panel to remove the resource
component from the CbCR profits.

Per (source_iso3, hq_iso3, commodity ∈ {oil_gas, coal, minerals, unknown, other}, year):
    pre_profit_payments_usd   — royalties, licence/area/surface fees, signature & production
                                bonuses, production entitlements (expensed, so not in CbCR profit)
    post_profit_payments_usd  — corporate income tax + special petroleum/mining taxes + windfall
                                (the profit-based take)
    equity_income_usd         — state dividends / state-participation income (out of post-tax profit)
    other_payments_usd        — anything classified "other" by 3_31 (kept for completeness)
    data_source               — provenance: eiti_bilateral | manual_distributed | grd_distributed |
                                {eiti,manual,grd}_extrapolated (a real tier's value imputed into a gap year)

Source-priority cascade per (source, year) cell:
  1. EITI bilateral  — matched company payments, attributed to their HQ country (3_31 → 3_33). I use this tier
     for every country that files EITI. I drop unmatched companies (I treat them as local operators and do not
     redistribute them).
  2. Manual          — data/raw/extractive/manual_resource_revenue.csv: a curated table of country totals with
     explicit pre/post/equity fractions, a domestic_share and a commodity. I distribute the country totals to HQ
     countries by hq_share_<commodity>.
  3. GRD             — extractive_royalty_dataset_yearly.csv (UNU-WIDER GRD, USD): country totals of resource
     revenue. I split them into pre/post/equity from the GRD tax breakdown, take the commodity split from World Bank
     rents and distribute them to HQs by hq_share. I read the split between domestic and foreign from the
     consolidated control table (resource_country_parameters.csv) where available, otherwise I use the
     per-commodity default.
  4. Gap-year extrapolation (all tiers) — for any covered country (EITI, manual or GRD) with a year in the window
     that has reported CbCR profit but no panel row, I scale the country's average take in its covered years
     (keeping the same HQ / commodity / bucket structure) by that year's reported CbCR profit relative to the
     covered-year average. I treat a missing year as a data gap (e.g. GRD ending in 2021 leaves Brunei 2022
     without data), not as stopped production.
There is no World Bank rent-proxy tier: every included resource country has a real source (EITI, manual or GRD).
The `include` flag of the consolidated control table filters the output to the genuine resource economies.
Non-resource countries are dropped here and get no resource correction in script 4.

Foreign HQ-share cascade for distributed (manual or GRD) totals (no single tier ever fills the whole foreign slice
on its own):
  1. The documented payments of EITI bilateral data and operator P2G reports as absolute anchors. Each covered HQ
     keeps its own documented amount, never scaled up (a scale-up would hand the whole split to whichever operators
     publish P2G reports: OMV 27% of Norway, Glencore 43.6% of South Africa).
  2. manual_foreign_hq_shares.csv on the residual (renormalised over the HQs without an anchor).
  3. CbCR excess-tax weights (_cbcr_excess_tax_weights): the residual follows the (parent → source) cells that show
     tax above the source country's statutory rate, that is, where resource-regime tax is visibly booked and the
     correction can land.
  4. generic global Orbis hq_shares table — true last resort.
  Tiers 3 and 4 apply only with config.RESOURCE_FOREIGN_RESIDUAL = "excess_tax". With the default "unassigned",
  the residual foreign slice that no documented operator or curated share covers is assigned to no parent (no strip
  without documentation).
Every output row carries `hq_share_basis` (one of domestic, eiti_bilateral, eiti_operator, manual_foreign,
cbcr_excess_tax, generic_global), so that the provenance of the shares can be checked.

Section outline (numbers match the cell headings below):
1. Setup.
2. HQ-share tables.
3. Distribute.
4. EITI bilateral tier.
5. Manual and GRD tiers for non-EITI countries.
6. Gap-year extrapolation.
7. Main cascade.
8. Company-anchored strips.

Extractive prep, stage 3_38 — after 3_36. It is the final cascade, and script 4 (resource correction) reads its
output.

Reads:
  data/intermediate/extractive/eiti_company_payments_long.csv          — classified company payments (3_31)
  data/intermediate/extractive/eiti_company_hq_map.csv                 — company→HQ Orbis map (3_33)
  data/intermediate/extractive/operator_payments_by_hq_source_yearly.csv — operator P2G anchors (3_34)
  data/intermediate/extractive/extractive_royalty_dataset_yearly.csv   — GRD + WB rents, USD
  data/intermediate/extractive/hq_shares_by_commodity_yearly.csv       — global HQ shares (3_36)
  data/raw/extractive/manual_resource_revenue.csv                      — curated country-total revenues
  data/raw/extractive/manual_foreign_hq_shares.csv                     — hand-curated foreign HQ shares

Writes:
  data/intermediate/extractive/resource_payments_by_hq_source_yearly.csv    — the cascade panel (input to script 4)
  data/intermediate/extractive/resource_payments_by_hq_source_coverage.csv  — coverage/provenance diagnostics
  data/intermediate/extractive/company_anchored_strips.csv                  — company-anchored strips, read by script 4
  A dataset variant (config.DATASET_VARIANTS, e.g. res_no_inferred_companies) writes its own version of each, with
  `__<variant>` before the extension.

Usage:
  python src/3_extractive_prep/3_38_resource_payments_by_hq_source.py

Author: Tax Justice Network.
Last updated: 2026-11-23.
"""
# %% MARK: 1. Setup
import sys
import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT
from _resource_scope import load_scope_exclusions, payer_in_scope

DATA_RAW = (EXT_INT / ".." / ".." / "raw").resolve()
PAY_LONG = EXT_INT / "eiti_company_payments_long.csv"
HQ_MAP = EXT_INT / "eiti_company_hq_map.csv"
ROYALTY_DS = EXT_INT / "extractive_royalty_dataset_yearly.csv"
HQ_SHARES = EXT_INT / "hq_shares_by_commodity_yearly.csv"
MANUAL = DATA_RAW / "extractive" / "manual_resource_revenue.csv"
MANUAL_FHQ = DATA_RAW / "extractive" / "manual_foreign_hq_shares.csv"   # hand-curated foreign HQ splits
PARAMS = DATA_RAW / "extractive" / "resource_country_parameters.csv"   # consolidated control table: include flag + domestic split
CBCR_DISAGG = (EXT_INT / ".." / ".." / "final" / "cbcr_main_disaggregated.csv").resolve()
OUT = EXT_INT / "resource_payments_by_hq_source_yearly.csv"
OUT_COV = EXT_INT / "resource_payments_by_hq_source_coverage.csv"
SOURCE_TABLES = DATA_RAW / "extractive" / "source_tables"                  # figure-by-figure source tables
OUT_ANCHOR = EXT_INT / "company_anchored_strips.csv"                       # company-anchored strips (script 4)

import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from config import ANALYSIS_YEARS as _ANALYSIS_YEARS  # the CbCR window (config.py)
from config import RESOURCE_FOREIGN_RESIDUAL, RESOURCE_INFERRED_OFF, variant_path  # resource-correction settings
# A dataset variant (config.DATASET_VARIANTS) writes its own version of the three outputs.
OUT, OUT_COV, OUT_ANCHOR = variant_path(OUT), variant_path(OUT_COV), variant_path(OUT_ANCHOR)
YEARS = list(_ANALYSIS_YEARS)                         # the CbCR analysis window
DIST_COMMODITIES = ["oil_gas", "coal", "minerals"]    # commodities the HQ-share table covers
BUCKETS = ["pre_profit_payments_usd", "post_profit_payments_usd", "equity_income_usd", "other_payments_usd"]
RTYPE_TO_BUCKET = {"royalty_like": "pre_profit_payments_usd", "cit": "post_profit_payments_usd",
                   "equity": "equity_income_usd", "other": "other_payments_usd"}
# Default split and domestic share by commodity, used when nothing more specific is known
DEFAULT_SPLIT = {"oil_gas": (0.45, 0.30, 0.25), "coal": (0.55, 0.40, 0.05), "minerals": (0.50, 0.40, 0.10)}
DEFAULT_DOMESTIC = {"oil_gas": 0.55, "coal": 0.40, "minerals": 0.40}
EITI_EXTRAP_SCALE_MIN = 0.2       # bounds of the scaler (gap-year over covered-year reported profit)
EITI_EXTRAP_SCALE_MAX = 5.0
CASCADE_ORDER = ["eiti_bilateral", "manual", "grd", "eiti_extrapolated"]   # no WB rent-proxy tier
# Priority among the bases of the HQ split, for a foreign (hq, commodity) pair that was split by different bases in
# different covered years. The gap-year extrapolation uses it to collapse those competing measurements to one, best
# evidence first. Lower values are preferred. `domestic` never competes with a foreign HQ, so its rank has no effect.
_BASIS_PRIORITY = {"domestic": 0, "eiti_bilateral": 1, "eiti_operator": 2,
                   "manual_foreign": 3, "cbcr_excess_tax": 4, "generic_global": 5}
# Sources whose distributed take describes only their own state companies. For them, I limit the foreign slice to
# the documented operator payments (anchors) and keep the rest domestic (see distribute()). China: the manual rows
# are the income tax and remittances of state-owned enterprises plus the national resource tax.
FOREIGN_ANCHORS_ONLY = {"CHN"}

# Countries where the manual table overrides EITI bilateral (tax-authority data
# judged more comprehensive than incomplete EITI disclosures) are flagged with
# preferred_source = "manual" in resource_country_parameters.csv, which also
# carries the per-country rationale (preferred_source_note). The script reads it below.


# A few non-ISO3 codes that appear in hq_shares_by_commodity_yearly.csv
ISO2_FIX = {"MH": "MHL", "LI": "LIE", "WS": "WSM", "KV": "XKX", "KN": "KNA", "AC": "ATG"}


# %% MARK: 2. HQ-share tables
def _hq_share_table():
    h = pd.read_csv(HQ_SHARES)
    h["hq_iso3"] = h["hq_iso3"].replace(ISO2_FIX)
    bad = h[h.hq_iso3.astype(str).str.len() != 3]
    if len(bad):
        print(f"  [warn] dropping {len(bad)} hq-share rows with non-ISO3 codes: {sorted(bad.hq_iso3.unique())}")
        h = h[h.hq_iso3.astype(str).str.len() == 3]
    h = h[h.year.isin(YEARS) & h.commodity.isin(DIST_COMMODITIES)].copy()
    # I renormalise within (year, commodity) to be safe.
    h["share"] = h["share"] / h.groupby(["year", "commodity"])["share"].transform("sum")
    return h


def _eiti_hq_share_overrides():
    """Builds source-specific HQ-share overrides from the EITI bilateral panel plus the operator-side P2G data, keyed
    by (source_iso3, commodity, year).

    For manual_distributed countries (especially COD, PER and MEX, where the EITI bilateral data is dropped through
    preferred_source = "manual"), I keep the curated total magnitudes but anchor the attribution of who paid within
    each total to operator-level data wherever it exists for the (source, commodity, year) cell. The generic
    Orbis-derived hq_tbl is the fallback when neither EITI nor operator data is available.

    Sources merged in priority order:
      1. EITI bilateral panel (eiti_payments_by_hq_source_yearly.csv)
      2. Operator P2G panel (operator_payments_by_hq_source_yearly.csv: TotalEnergies, Eni, BP, Glencore, Vale,
         Sasol, Galp etc.)
    The operator data extends the EITI panel. For (source, year, hq) cells where EITI has data, EITI wins. For cells
    where only operator data exists, the operator number contributes to the share denominator.

    Returns a DataFrame with the columns source_iso3, year, commodity, hq_iso3, share and value_usd.
    """
    eiti_path = EXT_INT / "eiti_payments_by_hq_source_yearly.csv"
    op_path = EXT_INT / "operator_payments_by_hq_source_yearly.csv"
    parts = []
    if eiti_path.exists():
        e = pd.read_csv(eiti_path, low_memory=False)
        e = e.dropna(subset=["fy_end_year", "hq_iso3"])
        e = e[e["hq_iso3"].astype(str).str.len() == 3]
        e = e[~e["hq_iso3"].isin(["UNMATCHED", "UNKNOWN_HQ"])]
        e["year"] = pd.to_numeric(e["fy_end_year"], errors="coerce").astype("Int64")
        e = e.dropna(subset=["year"])
        e["commodity"] = e["commodity"].where(e["commodity"].isin(DIST_COMMODITIES), "minerals")
        e["value_usd"] = pd.to_numeric(e["value_usd"], errors="coerce").fillna(0.0).clip(lower=0)
        e_g = e.groupby(["source_iso3", "year", "commodity", "hq_iso3"], as_index=False)["value_usd"].sum()
        e_g["source"] = "eiti"
        parts.append(e_g)
    if op_path.exists():
        o = pd.read_csv(op_path, low_memory=False)
        o = o.dropna(subset=["year", "hq_iso3", "source_iso3"])
        o = o[o["hq_iso3"].astype(str).str.len() == 3]
        # I assign operator payments to oil_gas by default, because the major operators in the panel are upstream oil
        # and gas companies. The mining operators (Glencore, CMOC, Vale, Sasol mining) get minerals.
        mineral_ops = {"Glencore", "CMOC", "Vale", "Sasol mining"}
        o["commodity"] = o["operator_name"].apply(lambda op: "minerals" if op in mineral_ops else "oil_gas")
        o["value_usd"] = pd.to_numeric(o["value_usd"], errors="coerce").fillna(0.0).clip(lower=0)
        o["year"] = pd.to_numeric(o["year"], errors="coerce").astype("Int64")
        o = o.dropna(subset=["year"])
        o_g = o.groupby(["source_iso3", "year", "commodity", "hq_iso3"], as_index=False)["value_usd"].sum()
        o_g["source"] = "operator"
        parts.append(o_g)
    if not parts:
        return pd.DataFrame(columns=["source_iso3", "year", "commodity", "hq_iso3", "share"])

    # Merge: I take the EITI value where available, otherwise the operator value.
    combined = pd.concat(parts, ignore_index=True)
    # Within each (source, year, commodity, hq) cell, I prefer EITI over operator data.
    combined["priority"] = combined["source"].map({"eiti": 0, "operator": 1}).fillna(2)
    combined = (combined.sort_values(["source_iso3", "year", "commodity", "hq_iso3", "priority"])
                        .drop_duplicates(["source_iso3", "year", "commodity", "hq_iso3"], keep="first"))
    tot = combined.groupby(["source_iso3", "year", "commodity"])["value_usd"].transform("sum")
    combined = combined[tot > 0].copy()
    combined["share"] = combined["value_usd"] / tot[tot > 0]
    # I keep value_usd: documented payments act as absolute anchors in distribute() (never scaled up to fill the
    # foreign slice), so the dollar level matters, not just the relative share.
    return combined[["source_iso3", "year", "commodity", "hq_iso3", "share", "value_usd"]]


def _cbcr_excess_tax_weights():
    """Returns pooled 'excess tax' weights per (source, parent) from the cleaned CbCR itself:
    excess = Σ_years max(0, tax − statutory CIT × max(profit, 0)) over the reported (parent → source) cells. Tax paid
    above the source country's ordinary statutory rate is the bilateral fingerprint of resource-regime taxation
    (petroleum tax, mining surtax). It therefore locates the parents whose MNEs actually bear a country's resource
    take. Unlike global ownership weights, it also guarantees that the attributed correction lands on CbCR cells that
    exist and can absorb it (e.g. Angola: the USA cell's ETR of 0.80 is Chevron's and Exxon's petroleum tax, while the
    FRA and GBR cells the P2G anchors point at are nearly empty). I pool over all years for stability. The weights
    cover all sectors by construction, because the screen for tax above the statutory rate keeps ordinary business
    out. I drop parents with an excess below US$5m as noise. Returns source_iso3, hq_iso3, share."""
    cb_path = (EXT_INT / ".." / ".." / "final" / "cbcr_main.csv").resolve()
    if not cb_path.exists():
        return pd.DataFrame(columns=["source_iso3", "hq_iso3", "share"])
    cb = pd.read_csv(cb_path, usecols=["iso_parent", "iso_partner", "year", "cit",
                                       "profit_loss_before_income_tax_corrected",
                                       "income_tax_paid_on_cash_basis"], low_memory=False)
    cb = cb[(cb.iso_parent.astype(str).str.len() == 3) & (cb.iso_partner.astype(str).str.len() == 3)
            & (cb.iso_parent != cb.iso_partner)]
    cit = pd.to_numeric(cb["cit"], errors="coerce")
    cit = cit.where(cit <= 1.0, cit / 100.0)
    prof = pd.to_numeric(cb["profit_loss_before_income_tax_corrected"], errors="coerce").clip(lower=0)
    tax = pd.to_numeric(cb["income_tax_paid_on_cash_basis"], errors="coerce")
    cb["excess"] = (tax - cit.fillna(0.25) * prof).clip(lower=0)
    g = (cb.dropna(subset=["excess"]).groupby(["iso_partner", "iso_parent"], as_index=False)["excess"].sum()
           .rename(columns={"iso_partner": "source_iso3", "iso_parent": "hq_iso3"}))
    g = g[g["excess"] >= 5e6]
    tot = g.groupby("source_iso3")["excess"].transform("sum")
    g["share"] = g["excess"] / tot
    return g[["source_iso3", "hq_iso3", "share"]]


def _manual_foreign_hq_shares():
    """Returns the hand-curated foreign-HQ splits (data/raw/extractive/manual_foreign_hq_shares.csv: source_iso3,
    commodity, year (blank = every year), hq_iso3, share, confidence, source_note). The shares are weights within the
    foreign slice only, and I renormalise them per (source, commodity, year). The result has the same shape as the
    EITI override table."""
    if not MANUAL_FHQ.exists():
        return pd.DataFrame(columns=["source_iso3", "year", "commodity", "hq_iso3", "share"])
    f = pd.read_csv(MANUAL_FHQ, comment="#")
    rows = []
    for _, r in f.iterrows():
        yr = r.get("year")
        years = YEARS if (pd.isna(yr) or str(yr).strip() == "") else [int(yr)]
        for y in years:
            rows.append({"source_iso3": r["source_iso3"], "year": y, "commodity": r["commodity"],
                         "hq_iso3": r["hq_iso3"], "share": float(r["share"])})
    df = pd.DataFrame(rows)
    df["share"] = df["share"] / df.groupby(["source_iso3", "year", "commodity"])["share"].transform("sum")
    return df


# %% MARK: 3. Distribute
def distribute(source_iso3, commodity, year, amount_pre, amount_post, amount_eq, domestic_share, hq_tbl,
               eiti_share_override=None, manual_fhq=None, excess_tbl=None):
    """Splits a source-country (commodity, year) total into rows by hq_iso3.

    The domestic_share lands on the source country itself (its national oil company). I spread the rest over the
    *foreign* HQ shares for that commodity-year (with the source country removed and the shares renormalised).

    Foreign-share cascade:
      1. `eiti_share_override` — documented payments from EITI bilateral data and operator P2G reports, used as
         absolute anchors. Each covered HQ keeps its own documented amount (converted to a weight through the cell
         take) and is never scaled up to fill the whole foreign slice. A scale-up would hand the entire foreign split
         to whichever operators happen to publish a P2G report (OMV 27% of Norway, Glencore 43.6% of South Africa),
         the operator-coverage skew. Together, the anchors are capped at the foreign slice.
      2. `manual_fhq` — hand-curated foreign HQ shares (manual_foreign_hq_shares.csv), applied to the residual after
         the anchors and renormalised over the HQs that do not already have an anchor. Evidence outranks inference,
         so the curated splits sit above the CbCR-derived weights.
      3. `excess_tbl` — CbCR excess-tax weights (_cbcr_excess_tax_weights). The residual follows the
         (parent → source) cells that actually show tax paid above the source country's statutory rate, that is,
         where resource-regime tax is visibly booked and the correction can land.
      4. generic global Orbis `hq_tbl` — true last resort.
    Tiers 3 and 4 apply only with config.RESOURCE_FOREIGN_RESIDUAL = "excess_tax". With the default "unassigned",
    the uncovered residual is assigned to no parent.

    Each returned dict carries `hq_share_basis` (one of domestic, eiti_operator, manual_foreign, cbcr_excess_tax,
    generic_global), so that the basis can be checked."""
    rows = []
    dom = float(np.clip(domestic_share, 0.0, 1.0))
    if dom > 0:
        rows.append({"hq_iso3": source_iso3, "pre_profit_payments_usd": amount_pre * dom,
                     "post_profit_payments_usd": amount_post * dom, "equity_income_usd": amount_eq * dom,
                     "other_payments_usd": 0.0, "hq_share_basis": "domestic"})
    fw = 1.0 - dom
    if fw <= 0:
        return rows
    cell_take = amount_pre + amount_post + amount_eq

    def _emit(hq, w, basis):
        rows.append({"hq_iso3": hq, "pre_profit_payments_usd": amount_pre * w,
                     "post_profit_payments_usd": amount_post * w, "equity_income_usd": amount_eq * w,
                     "other_payments_usd": 0.0, "hq_share_basis": basis})

    # 1. Absolute anchors from documented payments
    # ANCHOR_EXCLUDE (United Arab Emirates): the P2G figures of the Gulf concessions are dominated by in-kind
    # production entitlements remitted on the state's behalf (TotalEnergies reports US$6–25bn a year "paid" to Abu
    # Dhabi). They therefore wildly overstate the operator's own fiscal share. Anchoring on them would hand FRA and GBR
    # the whole ARE foreign slice, while the actual taxpayers (INPEX, CNPC, Exxon, cells with ETRs of 0.76–0.87) would
    # get nothing. I skip the anchors for these sources, and the manual concession-equity shares take over (plus the
    # excess-tax residual when RESOURCE_FOREIGN_RESIDUAL = "excess_tax").
    ANCHOR_EXCLUDE = {"ARE"}
    anchored = {}
    if (source_iso3 not in ANCHOR_EXCLUDE
            and eiti_share_override is not None and len(eiti_share_override) and cell_take > 0):
        ev = eiti_share_override[
            (eiti_share_override["source_iso3"] == source_iso3)
            & (eiti_share_override["year"] == year)
            & (eiti_share_override["commodity"] == commodity)
            & (eiti_share_override["hq_iso3"] != source_iso3)
        ]
        if len(ev):
            w_anchor = (ev.set_index("hq_iso3")["value_usd"] / cell_take).clip(lower=0.0)
            scale = min(1.0, fw / w_anchor.sum()) if w_anchor.sum() > 0 else 0.0
            for hq, wi in (w_anchor * scale).items():
                if wi > 0:
                    _emit(hq, wi, "eiti_operator")
                    anchored[hq] = wi
    resid = fw - sum(anchored.values())
    if resid <= 1e-12:
        return rows

    # Sources whose take data describe only their own state companies (the CHN manual rows: income tax and
    # remittances of state-owned enterprises). Only the documented foreign operators (the anchors above) are foreign.
    # The residual foreign slice stays domestic instead of being spread by inferred weights. The CbCR excess-tax
    # weights would put it on US, Hong Kong, German and Cayman groups whose China tax is withholding tax, not
    # resource tax.
    if source_iso3 in FOREIGN_ANCHORS_ONLY:
        dom_row = next((r for r in rows if r["hq_share_basis"] == "domestic"), None)
        if dom_row is None:
            _emit(source_iso3, resid, "domestic")
        else:
            for k, a in [("pre_profit_payments_usd", amount_pre),
                         ("post_profit_payments_usd", amount_post),
                         ("equity_income_usd", amount_eq)]:
                dom_row[k] += a * resid
        return rows

    # 2. Manual shares on the residual (HQs without an anchor only)
    if manual_fhq is not None and len(manual_fhq):
        mv = manual_fhq[
            (manual_fhq["source_iso3"] == source_iso3)
            & (manual_fhq["year"] == year)
            & (manual_fhq["commodity"] == commodity)
            & (manual_fhq["hq_iso3"] != source_iso3)
            & (~manual_fhq["hq_iso3"].isin(anchored))
        ]
        if len(mv) and mv["share"].sum() > 0:
            s = mv.set_index("hq_iso3")["share"]
            for hq, wi in (s / s.sum() * resid).items():
                _emit(hq, wi, "manual_foreign")
            return rows

    # With config.RESOURCE_FOREIGN_RESIDUAL = "unassigned" (the default), I assign the residual foreign slice that
    # no documented operator or curated share covers to no parent, instead of inferring it from CbCR excess tax
    # (tier 3) or generic Orbis shares (tier 4).
    if RESOURCE_FOREIGN_RESIDUAL == "unassigned":
        return rows

    # 3. CbCR excess-tax weights on the residual
    if excess_tbl is not None and len(excess_tbl):
        xv = excess_tbl[(excess_tbl["source_iso3"] == source_iso3)
                        & (excess_tbl["hq_iso3"] != source_iso3)
                        & (~excess_tbl["hq_iso3"].isin(anchored))]
        if len(xv) and xv["share"].sum() > 0:
            s = xv.set_index("hq_iso3")["share"]
            for hq, wi in (s / s.sum() * resid).items():
                _emit(hq, wi, "cbcr_excess_tax")
            return rows

    # 4. generic global Orbis weights
    foreign = hq_tbl[(hq_tbl.year == year) & (hq_tbl.commodity == commodity)
                     & (hq_tbl.hq_iso3 != source_iso3) & (~hq_tbl.hq_iso3.isin(anchored))]
    fsum = foreign["share"].sum()
    if fsum > 0:
        for _, r in foreign.iterrows():
            _emit(r["hq_iso3"], (r["share"] / fsum) * resid, "generic_global")
    else:
        # Without foreign-share information, I put the remainder on the source country too.
        rows.append({"hq_iso3": source_iso3, "pre_profit_payments_usd": amount_pre * resid,
                     "post_profit_payments_usd": amount_post * resid, "equity_income_usd": amount_eq * resid,
                     "other_payments_usd": 0.0, "hq_share_basis": "domestic"})
    return rows


# %% MARK: 4. EITI bilateral tier
def eiti_bilateral():
    pay = pd.read_csv(PAY_LONG, low_memory=False)
    scope_exclusions = load_scope_exclusions()
    scope_ok = [payer_in_scope(src, name, year, scope_exclusions)
                for src, name, year in zip(pay.iso3, pay.company_name, pay.year)]
    n_scope_excluded = len(pay) - sum(scope_ok)
    pay = pay.loc[scope_ok].copy()
    print(f"  Documented out-of-scope EITI payer rows excluded: {n_scope_excluded:,}")
    hq = pd.read_csv(HQ_MAP, usecols=["source_iso3", "company_name", "hq_iso3", "match_method", "in_cbcr_universe"])
    pay = pay.merge(hq.rename(columns={"source_iso3": "iso3"}), on=["iso3", "company_name"], how="left")
    n_all = len(pay)
    # GFS code 1153* means "revenues from sale of the state's share of production". There, the payer is a customer of
    # the state marketer (buyers of SOMO crude such as the trading arms of UNIPEC, Indian Oil, Valero and TOTSA), not a
    # producer paying fiscal obligations. I therefore attribute these rows to the source country itself, never to the
    # buyer's HQ (in material terms Iraq, US$390bn in the window). These rows keep an HQ for the panel even when the
    # buyer was unmatched, and they are exempt from the drop of domestic non-MNE payers below (they are state revenue,
    # not an operator's payment).
    def _state_sales_mask(d):
        # 1153* anywhere, and for IRQ also the whole equity bucket. Iraq has no foreign-equity dividends, so every
        # equity-classified row is a sale of SOMO crude whose GFS code is missing in some report vintages (buyers:
        # Chennai Petroleum, UNIPEC, Reliance, Sinochem ...).
        m = d["gfs_code"].astype(str).str.startswith("1153")
        return m | ((d["iso3"] == "IRQ") & (d["revenue_type"] == "equity"))
    sales_mask = _state_sales_mask(pay)
    pay.loc[sales_mask, "hq_iso3"] = pay.loc[sales_mask, "iso3"]
    pay = pay[pay["hq_iso3"].notna() & (pay["hq_iso3"].astype(str).str.len() == 3)]   # unmatched rows and rows without HQ dropped
    sales_mask = _state_sales_mask(pay)
    # I gate the *domestic* portion. A payment by a company headquartered in the producing country only lands on that
    # country's CbCR diagonal cell if the company itself is in the CbCR universe (a multi-entity extractive group
    # above the €750M threshold). Otherwise it is a purely domestic operator and out of scope.
    in_u = pd.to_numeric(pay["in_cbcr_universe"], errors="coerce").fillna(0).astype(int)
    drop_domestic_nonmne = (pay["hq_iso3"] == pay["iso3"]) & (in_u != 1) & ~sales_mask
    n_dropped_dom = int(drop_domestic_nonmne.sum())
    v_dropped_dom = pd.to_numeric(pay.loc[drop_domestic_nonmne, "value_usd"], errors="coerce").fillna(0).sum()
    pay = pay[~drop_domestic_nonmne]
    n_kept = len(pay)
    pay = pay[pay["year"].between(2010, 2025)].copy()
    pay["bucket"] = pay["revenue_type"].map(RTYPE_TO_BUCKET)
    pay = pay[pay["bucket"].notna()]
    pay["value_usd"] = pd.to_numeric(pay["value_usd"], errors="coerce").fillna(0.0)
    g = (pay.groupby(["iso3", "hq_iso3", "commodity", "year", "bucket"], as_index=False)["value_usd"].sum()
         .pivot_table(index=["iso3", "hq_iso3", "commodity", "year"], columns="bucket", values="value_usd", fill_value=0.0)
         .reset_index().rename(columns={"iso3": "source_iso3"}))
    for b in BUCKETS:
        if b not in g.columns:
            g[b] = 0.0
    g["data_source"] = "eiti_bilateral"
    eiti_countries = sorted(pay["iso3"].unique())
    print(f"  EITI bilateral: {n_all:,} payment rows → {n_kept:,} kept ({100*n_kept/n_all:.0f}%); "
          f"dropped {n_dropped_dom:,} domestic-non-MNE rows (${v_dropped_dom/1e9:,.1f} B out of scope); "
          f"{len(g):,} (source,hq,commodity,year) cells; {len(eiti_countries)} source countries")
    return g[["source_iso3", "hq_iso3", "commodity", "year"] + BUCKETS + ["data_source"]], set(eiti_countries)


# %% MARK: 5. Manual and GRD tiers for non-EITI countries
def manual_rows(year_set, hq_tbl, manual_fhq=None, eiti_overrides=None, excess_tbl=None):
    m = pd.read_csv(MANUAL, comment="#")
    m = m[m["year"].isin(year_set)]
    # I build the HQ-share override from the EITI bilateral and the operator-side P2G data. It applies to all manual
    # entries, not just COD, PER and MEX, whose manual totals override EITI. Operator P2G data (TotalEnergies, Eni,
    # BP, Glencore, Vale, Sasol, Galp etc.) anchors the HQ share for any (source, year, commodity) cell where it
    # exists, even for countries with no EITI presence (e.g. SAU, SDN, SSD, YEM).
    eiti_overrides = _eiti_hq_share_overrides() if eiti_overrides is None else eiti_overrides
    n_overridden = 0
    out = []
    for _, r in m.iterrows():
        tot = float(r["total_resource_revenue_usd_bn"]) * 1e9
        pre, post, eq = tot * r["frac_pre_profit"], tot * r["frac_post_profit"], tot * r["frac_equity"]
        comm = r["commodity"] if r["commodity"] in DIST_COMMODITIES else "minerals"
        # I pass the EITI and operator override to every manual entry. distribute() only uses it when it actually has
        # data for the (source, year, commodity) cell, so cells without coverage fall back to the generic Orbis
        # hq_tbl.
        override_df = eiti_overrides if len(eiti_overrides) else None
        if override_df is not None:
            has_override = ((eiti_overrides["source_iso3"] == r["source_iso3"])
                            & (eiti_overrides["year"] == int(r["year"]))
                            & (eiti_overrides["commodity"] == comm)).any()
            if has_override:
                n_overridden += 1
        for d in distribute(r["source_iso3"], comm, int(r["year"]), pre, post, eq, r["domestic_share"], hq_tbl,
                            eiti_share_override=override_df, manual_fhq=manual_fhq, excess_tbl=excess_tbl):
            d.update({"source_iso3": r["source_iso3"], "commodity": comm, "year": int(r["year"]), "data_source": "manual_distributed"})
            out.append(d)
    if n_overridden:
        print(f"  manual: {n_overridden} (source, year, commodity) cells used EITI+operator-derived hq-shares "
              f"instead of generic Orbis weights")
    return pd.DataFrame(out) if out else pd.DataFrame(columns=["source_iso3", "hq_iso3", "commodity", "year"] + BUCKETS + ["data_source"]), set(m["source_iso3"].unique())


def _commodity_split_from_wb(row):
    """Returns the fractions of a country-year resource total to assign to oil_gas, coal and minerals, from World Bank
    rents.

    Returns None when no usable World Bank rent split exists (all values missing or zero). This includes the NaN case:
    a year with a GRD total but missing World Bank rents (e.g. Brunei 2022, where the World Bank rent series ends in
    2021). I coerce NaN to 0 first, because `nan or 0` returns nan (nan is truthy) and `nan <= 0` is False. Otherwise
    NaN commodity fractions would leak into a phantom GRD row that blocks the gap-year extrapolation."""
    def v(k):
        x = pd.to_numeric(row.get(k, 0.0), errors="coerce")
        return 0.0 if pd.isna(x) else float(x)
    og = v("wb_oil_rents_usd") + v("wb_gas_rents_usd")
    co = v("wb_coal_rents_usd")
    mi = v("wb_mineral_rents_usd")
    s = og + co + mi
    if s <= 0:
        return None
    return {"oil_gas": og / s, "coal": co / s, "minerals": mi / s}


def build_eiti_splits(eiti_df):
    """Returns the pre/post/equity fractions per (source, year) from the bilateral EITI API data plus the
    Summary-Data splits of the EITI report folder (3_13), as (by_year, by_country): by_year[(iso, yr)] and
    by_country[iso] = (pre_f, post_f, eq_f). grd_rows uses them to give a year with a GRD magnitude the country's own
    EITI split instead of the fallback from the GRD tax fields or resource_taxes (the year-specific split if
    available, otherwise the country's average across its EITI years)."""
    recs = []
    if len(eiti_df):
        a = eiti_df.groupby(["source_iso3", "year"])[
            ["pre_profit_payments_usd", "post_profit_payments_usd", "equity_income_usd"]].sum()
        for (iso, y), r in a.iterrows():
            recs.append((iso, int(y), float(r.iloc[0]), float(r.iloc[1]), float(r.iloc[2])))
    fp = EXT_INT / "eiti_folder_summary_splits.csv"
    if fp.exists():
        f = pd.read_csv(fp)
        for _, r in f.iterrows():
            recs.append((r["iso3"], int(r["year"]), float(r["frac_pre_profit"]),
                         float(r["frac_post_profit"]), float(r["frac_equity"])))
    if not recs:
        return {}, {}
    df = pd.DataFrame(recs, columns=["iso", "year", "pre", "post", "eq"]).drop_duplicates(
        ["iso", "year"], keep="first")   # the API data (added first) win over the folder data in the same cell
    df = df.assign(t=df["pre"] + df["post"] + df["eq"])
    df = df[df["t"] > 0]
    df = df.assign(pf=df["pre"] / df["t"], qf=df["post"] / df["t"], ef=df["eq"] / df["t"])
    by_year = {(r.iso, int(r.year)): (r.pf, r.qf, r.ef) for r in df.itertuples()}
    avg = df.groupby("iso")[["pf", "qf", "ef"]].mean()
    by_country = {i: (r.pf, r.qf, r.ef) for i, r in avg.iterrows()}
    return by_year, by_country


def grd_rows(non_eiti_with_manual, eiti_countries, year_set, hq_tbl, ds_tbl=None,
             eiti_by_year=None, eiti_by_country=None, eiti_share_override=None, manual_fhq=None, excess_tbl=None):
    ds_tbl = ds_tbl or {}
    rd = pd.read_csv(ROYALTY_DS)
    rd = rd[rd["year"].isin(year_set)].copy()
    # Commodity mix per country from World Bank rents across all available years. It is the fallback split when a
    # year has a GRD total but no year-specific World Bank split. The World Bank resource-rent series ends in 2021, so
    # every 2022 GRD total (47 countries) would otherwise lack a split. Using the GRD total with the country's own
    # historical mix keeps the real magnitude instead of forcing a needless gap-year extrapolation of a number I have.
    _wbcols = ["wb_oil_rents_usd", "wb_gas_rents_usd", "wb_coal_rents_usd", "wb_mineral_rents_usd"]
    _wb = rd.copy()
    for _c in _wbcols:
        _wb[_c] = pd.to_numeric(_wb[_c], errors="coerce").fillna(0.0)
    _mix = _wb.groupby("iso3")[_wbcols].sum()
    country_split = {}
    for _iso, _r in _mix.iterrows():
        _og = _r["wb_oil_rents_usd"] + _r["wb_gas_rents_usd"]
        _co = _r["wb_coal_rents_usd"]; _mi = _r["wb_mineral_rents_usd"]
        _s = _og + _co + _mi
        if _s > 0:
            country_split[_iso] = {"oil_gas": _og / _s, "coal": _co / _s, "minerals": _mi / _s}
    out = []
    covered = set()
    skip = eiti_countries | non_eiti_with_manual
    for _, row in rd.iterrows():
        iso = row["iso3"]
        if iso in skip:
            continue
        tot = row.get("grd_total_resource_rev_usd")
        if not (isinstance(tot, (int, float)) and np.isfinite(tot) and tot > 0):
            continue
        csplit = _commodity_split_from_wb(row)
        if csplit is None:
            csplit = country_split.get(iso)   # the country's historical World Bank commodity mix
        if csplit is None:
            continue   # no World Bank rents in any year: left to the gap-year extrapolation
        # EITI split carried over: if this country has an EITI-derived split (bilateral API data or folder Summary
        # Data, through build_eiti_splits), I use it for this year with a GRD magnitude instead of the fallback from
        # the GRD tax fields or resource_taxes. I use the year-specific split if available, otherwise the country's
        # average EITI split. This carries each country's own fiscal-regime split onto the years its EITI report is
        # missing (e.g. Kazakhstan 2018 and 2022, Gabon 2016–2020).
        _sp = None
        if eiti_by_year is not None:
            _sp = eiti_by_year.get((iso, int(row["year"]))) or (eiti_by_country or {}).get(iso)
        if _sp:
            pre_f, post_f, eq_f = _sp
            pre, post, eq = tot * pre_f, tot * post_f, tot * eq_f
        else:
            # Pre/post/equity split from the GRD tax breakdown, with sensible fallbacks
            post = row.get("grd_tax_income_profits_capgains_resource_usd")
            if not (isinstance(post, (int, float)) and np.isfinite(post)):
                post = row.get("grd_cit_resource_usd")
            if not (isinstance(post, (int, float)) and np.isfinite(post)):
                # Without a resource income- or profit-tax line and without an EITI split, I substitute the aggregate
                # `resource_taxes` (GRD technical note tn2021-11: "mostly corporate taxation of resource extraction"),
                # a reasonable post-profit proxy.
                post = row.get("grd_resource_taxes_usd")
            post = float(post) if (isinstance(post, (int, float)) and np.isfinite(post)) else np.nan
            nontax = row.get("grd_nontax_rev_resource_usd")
            nontax = float(nontax) if (isinstance(nontax, (int, float)) and np.isfinite(nontax)) else np.nan
            if np.isnan(post) and np.isnan(nontax):
                pre_f, post_f, eq_f = 0.5, 0.3, 0.2
                pre, post, eq = tot * pre_f, tot * post_f, tot * eq_f
            else:
                post = 0.0 if np.isnan(post) else post
                eq = 0.4 * (0.0 if np.isnan(nontax) else nontax)
                post = min(post, tot); eq = min(eq, max(tot - post, 0.0))
                pre = max(tot - post - eq, 0.0)
        for comm, cf in csplit.items():
            if cf <= 0:
                continue
            # Domestic / foreign split: I prefer the researched value in the control table and fall back to the
            # per-commodity default.
            dom = ds_tbl.get(iso, DEFAULT_DOMESTIC[comm])
            for d in distribute(iso, comm, int(row["year"]), pre * cf, post * cf, eq * cf, dom, hq_tbl,
                                eiti_share_override=eiti_share_override, manual_fhq=manual_fhq, excess_tbl=excess_tbl):
                d.update({"source_iso3": iso, "commodity": comm, "year": int(row["year"]), "data_source": "grd_distributed"})
                out.append(d)
        covered.add(iso)
    return (pd.DataFrame(out) if out else pd.DataFrame(columns=["source_iso3", "hq_iso3", "commodity", "year"] + BUCKETS + ["data_source"])), covered


# %% MARK: 6. Gap-year extrapolation
def extrapolate_gap_years(real_df, covered_pairs, needed_partners, prof, oow_base=None):
    """Fills the missing years of any covered country, whether the country is on the EITI, manual or GRD tier, when a
    year in the CbCR window has reported CbCR profit but no panel row.

    Principle: a missing year almost never means that production stopped. It is a data gap (e.g. the GRD series ends
    in 2021, so Brunei has no 2022 row, or an EITI report has not been filed yet). Dropping the resource correction to
    zero for that year would be wrong, so I impute it from the country's other years.

    For each covered source country, I take its average take in its covered years per (hq_iso3, commodity, bucket):
    Σ over the covered years ÷ the number of covered years. This keeps the structure of who paid and of the
    commodities that the real data show. I scale it for each gap year by that year's reported CbCR profit relative to
    the average reported profit of the covered years (clipped to a sensible band). I tag the imputed rows
    `<tier>_extrapolated` after the country's dominant real tier, so that the coverage can still be checked.

    `oow_base`: EITI rows outside the window (within three years before or after it). They never enter the output
    panel (script 4 has no CbCR cells for them), but they do inform the gap-year imputation. EITI 2015 is a good guess
    for a missing 2016, and a report for the year after the window is a good guess for a missing last year. They join
    the base of the average take and its structure. I anchor the profit scaler on the covered years inside the window
    only, because averaging CbCR profit over all covered years would let the years outside the window enter that mean
    as zeros, deflating it and inflating the scaler. A country whose coverage lies entirely outside the window has no
    profit anchor. I carry its take unscaled, and only into gap years within OOW_CARRY_MAX_DIST of a covered year
    (e.g. AZE's EITI data of 2013–2015 into 2016, but never into 2022).

    `real_df` is the concatenated, shadow-filtered EITI, manual and GRD panel. `prof` is a dict
    {(source_iso3, year): reported CbCR profit}. Returns (DataFrame, set of filled pairs).

    Note on the output schema: I pool the covered-year take per (hq_iso3, commodity), not per hq_share_basis, so the
    (source, hq, commodity, year) key is unique. A foreign pair can use different competing bases in different
    covered years (e.g. AZE→GBR oil_gas: eiti_operator in 2017, 2018 and 2022 but eiti_bilateral in 2019–2021). Those
    bases are competing measurements of the same payments, not additive slices, so pooling per basis would
    double-count. I collapse them to one pooled take (Σ buckets ÷ n_cov), tagged with the basis of the highest priority
    (_BASIS_PRIORITY). Domestic and foreign stay separate (different hq_iso3) and additive. No (source, year) cell
    carries more than one real tier."""
    empty = pd.DataFrame(columns=["source_iso3", "hq_iso3", "commodity", "year"] + BUCKETS + ["data_source"])
    if not len(real_df):
        return empty, set()
    OOW_CARRY_MAX_DIST = 3   # max |gap year − nearest covered year| for the unscaled carry
    tier_tag = {"eiti_bilateral": "eiti_extrapolated",
                "manual_distributed": "manual_extrapolated",
                "grd_distributed": "grd_extrapolated"}
    if oow_base is not None and len(oow_base):
        base_df = pd.concat([real_df, oow_base], ignore_index=True)
    else:
        base_df = real_df
    out = []
    covered = set()
    for src in sorted(base_df["source_iso3"].dropna().unique()):
        if src not in needed_partners:
            continue
        sub = base_df[base_df["source_iso3"] == src]
        covered_years = sorted(sub["year"].unique())
        n_cov = len(covered_years)
        gap_years = [y for y in YEARS
                     if (src, y) not in covered_pairs and prof.get((src, y), 0.0) > 0]
        if not gap_years or n_cov == 0:
            continue
        # I pool the covered-year take per (hq_iso3, commodity), deliberately not per hq_share_basis. A given foreign
        # (hq, commodity) pair can be split by different bases in different covered years (e.g. AZE→GBR oil_gas: an
        # eiti_operator basis in 2017, 2018 and 2022 but an eiti_bilateral basis in 2019–2021). Those bases are
        # competing measurements of the same payments, not additive slices. Grouping by basis and emitting one row
        # each would cross-sum them into the gap year, a double count (e.g. AZE, DNK). Grouping by (hq, commodity)
        # only pools them into one take (Σ buckets over the covered years ÷ n_cov), exactly as the main cascade
        # collapses competing bases by priority (§drop_duplicates above) and as script 4 group-sums the additive
        # domestic and foreign slices within a year.
        bcol = sub.get("hq_share_basis", pd.Series("unknown", index=sub.index)).rename("hq_share_basis")
        sub = sub.assign(hq_share_basis=bcol)
        agg = sub.groupby(["hq_iso3", "commodity"])[BUCKETS].sum() / n_cov
        # The representative basis per (hq, commodity) is the basis of the highest priority seen across the covered
        # years, so that the emitted row can be checked.
        rep_basis = (sub.assign(_p=sub["hq_share_basis"].map(_BASIS_PRIORITY).fillna(9))
                        .sort_values("_p")
                        .drop_duplicates(["hq_iso3", "commodity"], keep="first")
                        .set_index(["hq_iso3", "commodity"])["hq_share_basis"].to_dict())
        # Profit anchor: only the covered years inside the window. Years outside the window have no CbCR profit, so
        # including them would pull the mean towards zero and inflate the scaler.
        inw_years = [y for y in covered_years if y in YEARS]
        mean_prof_cov = float(np.mean([prof.get((src, y), 0.0) for y in inw_years])) if inw_years else 0.0
        if inw_years and mean_prof_cov <= 0:
            continue
        tag = tier_tag.get(sub["data_source"].mode().iloc[0], "extrapolated")
        for gy in gap_years:
            if inw_years:
                scaler = float(np.clip(prof.get((src, gy), 0.0) / mean_prof_cov,
                                       EITI_EXTRAP_SCALE_MIN, EITI_EXTRAP_SCALE_MAX))
            else:
                # The coverage lies entirely outside the window (e.g. AZE: EITI 2013–2015 only), so there is no profit
                # anchor. I carry the take unscaled, and only into gap years close to a covered year (from 2015 into
                # 2016, but not into 2022).
                if min(abs(gy - y) for y in covered_years) > OOW_CARRY_MAX_DIST:
                    continue
                scaler = 1.0
            for (hq, comm), vals in agg.iterrows():
                rec = {b: float(vals[b]) * scaler for b in BUCKETS}
                if sum(abs(v) for v in rec.values()) <= 0:
                    continue
                rec.update({"source_iso3": src, "hq_iso3": hq, "commodity": comm,
                            "year": gy, "data_source": tag,
                            "hq_share_basis": rep_basis.get((hq, comm), "extrapolated")})
                out.append(rec)
            covered.add((src, gy))
    return (pd.DataFrame(out) if out else empty), covered


# %% MARK: 7. Main cascade
def main():
    year_set = set(YEARS)
    hq_tbl = _hq_share_table()
    cb = pd.read_csv(CBCR_DISAGG, usecols=["iso_parent", "iso_partner", "year", "is_distributed",
                                           "profit_loss_before_income_tax_corrected"], low_memory=False)
    needed_partners = set(cb["iso_partner"].unique())
    # Reported (not imputed) CbCR profit booked in each source country-year. It is the scaler of the gap-year
    # extrapolation.
    cb_rep = cb[cb["is_distributed"] == 0]
    prof = (cb_rep.groupby(["iso_partner", "year"])["profit_loss_before_income_tax_corrected"]
            .sum().to_dict())

    # Consolidated control table: which countries are genuine resource economies (this drives the final filter) and
    # their researched split between domestic and foreign.
    params = pd.read_csv(PARAMS)
    included_iso = set(params.loc[params["include"].astype(str).str.lower() == "yes", "iso3"])
    ds_tbl = pd.to_numeric(params.set_index("iso3")["domestic_share"], errors="coerce").dropna().to_dict()
    # Countries whose manual entry replaces (rather than augments) their EITI bilateral data
    manual_overrides_eiti = set(
        params.loc[params["preferred_source"].fillna("").astype(str).str.lower() == "manual", "iso3"])


    print("Building resource_payments_by_hq_source_yearly.csv ...")
    manual_fhq = _manual_foreign_hq_shares()
    if len(manual_fhq):
        print(f"  manual foreign-HQ shares loaded for {sorted(manual_fhq.source_iso3.unique())}")
    ovr = _eiti_hq_share_overrides()
    excess_tbl = _cbcr_excess_tax_weights()
    print(f"  CbCR excess-tax weight table: {excess_tbl.source_iso3.nunique() if len(excess_tbl) else 0} source countries")
    eiti_df, eiti_countries = eiti_bilateral()
    # I split off the years outside the window (EITI reaches back to 2010 and forward past the window). They never
    # enter the output panel (script 4 has no CbCR cells for them), but they do feed the gap-year extrapolation below.
    # EITI 2015 is a good guess for a missing first window year, and the year after the window for a missing last
    # one.
    _oow_mask = ~eiti_df["year"].isin(year_set)
    # Only years near the window (within 3 years of config.ANALYSIS_YEARS): adjacent years outside the window may
    # inform gap years, but a 2008 report says little about the levels inside the window.
    eiti_oow = eiti_df[_oow_mask
                       & eiti_df["year"].between(min(YEARS) - 3, max(YEARS) + 3)].copy()
    if _oow_mask.any():
        eiti_df = eiti_df[~_oow_mask].copy()
        print(f"  EITI bilateral: {_oow_mask.sum():,} out-of-window rows excluded from the panel; "
              f"{len(eiti_oow):,} near-window rows ({min(YEARS)-3}-{min(YEARS)-1} / "
              f"{max(YEARS)+1}-{max(YEARS)+3}) kept as extrapolation base")
    eiti_df["hq_share_basis"] = "eiti_bilateral"
    eiti_oow["hq_share_basis"] = "eiti_bilateral"
    # preferred_source == "manual" (resource_country_parameters.csv): I drop the EITI rows of those countries, so that
    # the manual entry below replaces (rather than augments) them.
    if manual_overrides_eiti:
        n_before = len(eiti_df)
        eiti_df = eiti_df[~eiti_df["source_iso3"].isin(manual_overrides_eiti)].copy()
        eiti_oow = eiti_oow[~eiti_oow["source_iso3"].isin(manual_overrides_eiti)].copy()
        eiti_countries = eiti_countries - manual_overrides_eiti
        print(f"  manual override for {sorted(manual_overrides_eiti)}: dropped {n_before - len(eiti_df)} EITI rows")

    # Cascade per (source, year): I cascade at the level of the (source, year) cell rather than per country. A
    # per-country cascade would let an EITI-listed country with thin coverage of years block better fallback layers
    # from filling the gaps. EITI bilateral data win in the cells where they have any rows. Manual data fill the cells
    # where EITI is empty for that year. GRD fills the cells where neither EITI nor manual data exist. The gap-year
    # extrapolation fills the remaining gaps of covered countries.
    #
    # EITI → GRD scale-up: rather than drop EITI cells that under-capture the GRD total, I scale the EITI
    # (source, year) rows up so that their total matches the GRD total. This keeps EITI's HQ allocation and
    # pre/post/equity split while adopting GRD's (more complete) magnitude. I only scale up (factor ≥ 1). Cells where
    # EITI already meets or exceeds GRD keep their EITI total. I tag the scaled rows data_source="eiti_grdscaled", so
    # that they can be checked.
    grd_raw = pd.read_csv(ROYALTY_DS)
    grd_raw = grd_raw[grd_raw["year"].isin(year_set)].copy()
    grd_totals = (
        grd_raw.set_index(["iso3", "year"])["grd_total_resource_rev_usd"]
        .dropna()
    )
    grd_totals = grd_totals[grd_totals > 0]

    if len(eiti_df):
        eiti_totals_by_pair = (
            eiti_df.groupby(["source_iso3", "year"])[BUCKETS].sum().sum(axis=1)
        )  # Series indexed by (source, year)
        # I only scale up where EITI is representative enough (it captures at least 1/MAX_SCALE of the GRD total).
        # Where EITI is too thin (factor > MAX_SCALE: it barely captured any operators, so its HQ structure is noise),
        # I drop the cell and let GRD fill it. The distribution of the factor has an empty gap between about 10× and
        # about 50×, so 10× cleanly separates representative cells (median about 1.3×) from noise (Nigeria 2019 about
        # 100×, Colombia 2019 about 850×).
        MAX_SCALE = 10.0
        scale, drop_pairs = {}, set()
        for key, et in eiti_totals_by_pair.items():
            gt = grd_totals.get(key)
            if gt and et and et > 0 and gt > et:
                f = gt / et
                if f <= MAX_SCALE:
                    scale[key] = f
                else:
                    drop_pairs.add(key)
        if scale:
            fac = np.array([scale.get((s, y), 1.0)
                            for s, y in zip(eiti_df["source_iso3"], eiti_df["year"])])
            for b in BUCKETS:
                eiti_df[b] = eiti_df[b].to_numpy() * fac
            eiti_df["data_source"] = np.where(
                fac > 1.0, "eiti_grdscaled", eiti_df["data_source"].to_numpy())
            print(f"  EITI→GRD scale-up: scaled {len(scale)} (source, year) cells up to the "
                  f"GRD total (median {np.median(list(scale.values())):.1f}×, "
                  f"max {max(scale.values()):.1f}×).")
        if drop_pairs:
            _before = len(eiti_df)
            _keep = ~np.array([(s, y) in drop_pairs
                               for s, y in zip(eiti_df["source_iso3"], eiti_df["year"])])
            eiti_df = eiti_df[_keep].copy()
            print(f"  EITI too thin to scale (< {1 / MAX_SCALE:.0%} of GRD): dropped "
                  f"{_before - len(eiti_df):,} rows in {len(drop_pairs)} cells → GRD fills them "
                  f"({sorted(drop_pairs)[:8]}).")

    eiti_pairs = set(map(tuple, eiti_df[["source_iso3", "year"]].drop_duplicates().itertuples(index=False, name=None)))

    parts = [eiti_df]

    man_df, _ = manual_rows(year_set, hq_tbl, manual_fhq=manual_fhq, eiti_overrides=ovr, excess_tbl=excess_tbl)
    if len(man_df):
        man_pairs_before = set(map(tuple, man_df[["source_iso3", "year"]].drop_duplicates().itertuples(index=False, name=None)))
        man_df = man_df[~man_df[["source_iso3", "year"]].apply(tuple, axis=1).isin(eiti_pairs)].copy()
        manual_pairs = set(map(tuple, man_df[["source_iso3", "year"]].drop_duplicates().itertuples(index=False, name=None)))
        n_shadowed = len(man_pairs_before) - len(manual_pairs)
        parts.append(man_df)
        print(f"  manual_distributed: {len(man_df):,} cells across {len(manual_pairs)} (source, year) pairs "
              f"({n_shadowed} pairs shadowed by EITI)")
    else:
        manual_pairs = set()
        print(f"  manual_distributed: 0 cells")

    eiti_by_year, eiti_by_country = build_eiti_splits(eiti_df)
    print(f"  EITI splits available for split-carry: {len(eiti_by_country)} countries "
          f"({len(eiti_by_year)} country-years)")
    grd_df, _ = grd_rows(set(), set(), year_set, hq_tbl, ds_tbl=ds_tbl,
                         eiti_by_year=eiti_by_year, eiti_by_country=eiti_by_country,
                         eiti_share_override=ovr, manual_fhq=manual_fhq, excess_tbl=excess_tbl)
    if len(grd_df):
        grd_pairs_before = set(map(tuple, grd_df[["source_iso3", "year"]].drop_duplicates().itertuples(index=False, name=None)))
        grd_df = grd_df[
            ~grd_df[["source_iso3", "year"]].apply(tuple, axis=1).isin(eiti_pairs | manual_pairs)
        ].copy()
        grd_pairs = set(map(tuple, grd_df[["source_iso3", "year"]].drop_duplicates().itertuples(index=False, name=None)))
        n_shadowed = len(grd_pairs_before) - len(grd_pairs)
        parts.append(grd_df)
        print(f"  grd_distributed: {len(grd_df):,} cells across {len(grd_pairs)} (source, year) pairs "
              f"({n_shadowed} pairs shadowed by EITI/manual)")
    else:
        grd_pairs = set()
        print(f"  grd_distributed: 0 cells")

    covered_pairs = eiti_pairs | manual_pairs | grd_pairs
    # Gap-year imputation across all tiers (EITI, manual, GRD): a missing year with reported CbCR profit is a data gap,
    # not stopped production, so I impute it from the country's other years (e.g. GRD ending in 2021 leaves Brunei 2022
    # without data).
    real_df = pd.concat([p for p in parts if len(p)], ignore_index=True)
    ext_df, ext_pairs = extrapolate_gap_years(real_df, covered_pairs, needed_partners, prof,
                                              oow_base=eiti_oow)
    if len(ext_df):
        parts.append(ext_df)
        by_tier = ext_df.groupby("data_source")["source_iso3"].nunique().to_dict()
        print(f"  extrapolated gap years: {len(ext_df):,} cells across {len(ext_pairs)} (source, year) pairs "
              f"(scaled by reported CbCR profit); by tier {by_tier}")
    else:
        print(f"  extrapolated gap years: 0 cells")

    df = pd.concat([p for p in parts if len(p)], ignore_index=True)
    # I keep only the genuine resource economies (the include flag of the control table). Non-resource countries are
    # dropped here and get no correction in script 4.
    n_src_before = df["source_iso3"].nunique()
    df = df[df["source_iso3"].isin(included_iso)].copy()
    print(f"  include filter: kept {df['source_iso3'].nunique()}/{n_src_before} source countries "
          f"(dropped non-resource economies per resource_country_parameters.csv)")
    for b in BUCKETS:
        df[b] = pd.to_numeric(df[b], errors="coerce").fillna(0.0)
    # Pre-profit, equity and other payments can never be a negative base, so I floor net EITI refunds recorded as
    # negative payments at 0 per cell. I leave post_profit signed. Script 4 strips nothing for a negative post-profit
    # payment (a net refund).
    for b in ("pre_profit_payments_usd", "equity_income_usd", "other_payments_usd"):
        df[b] = df[b].clip(lower=0.0)
    # I collapse duplicate (source, hq, commodity, year, data_source) rows produced by distribute().
    df["hq_share_basis"] = df.get("hq_share_basis", pd.Series(index=df.index, dtype=object)).fillna("unknown")
    df = (df.groupby(["source_iso3", "hq_iso3", "commodity", "year", "data_source", "hq_share_basis"],
                     as_index=False)[BUCKETS].sum())
    # I drop rows that are zero throughout.
    df = df[df[BUCKETS].abs().sum(axis=1) > 0].copy()
    df = df.sort_values(["source_iso3", "year", "commodity", "hq_iso3"]).reset_index(drop=True)
    df.to_csv(OUT, index=False)

    # Coverage report
    cov = (df.groupby(["source_iso3", "data_source"], as_index=False)[BUCKETS].sum())
    cov["total_usd"] = cov[BUCKETS].sum(axis=1)
    cov = cov.sort_values(["data_source", "total_usd"], ascending=[True, False])
    cov.to_csv(OUT_COV, index=False)

    tot = df[BUCKETS].sum()
    print(f"\nWrote {OUT}  ({len(df):,} rows; {df.source_iso3.nunique()} source countries, {df.hq_iso3.nunique()} HQ countries, years {df.year.min()}-{df.year.max()})")
    print(f"  Σ pre_profit  ${tot['pre_profit_payments_usd']/1e9:,.0f} B")
    print(f"  Σ post_profit ${tot['post_profit_payments_usd']/1e9:,.0f} B")
    print(f"  Σ equity      ${tot['equity_income_usd']/1e9:,.0f} B")
    print(f"  Σ other       ${tot['other_payments_usd']/1e9:,.0f} B")
    print(f"  by data_source ($B):")
    for ds, v in df.groupby("data_source")[BUCKETS].sum().sum(axis=1).sort_values(ascending=False).items():
        print(f"    {ds:20s} {v/1e9:,.0f}")
    print(f"  by hq_share_basis ($B; foreign rows only):")
    fr = df[df.hq_iso3 != df.source_iso3]
    for bs, v in fr.groupby("hq_share_basis")[BUCKETS].sum().sum(axis=1).sort_values(ascending=False).items():
        print(f"    {bs:20s} {v/1e9:,.0f}")
    print(f"  Wrote {OUT_COV}")


# %% MARK: 8. Company-anchored strips
def _wb_fx(iso3):
    """Returns local currency units per USD: the World Bank official rate, period average (PA.NUS.FCRF)."""
    import csv
    with open(DATA_RAW / "macro_variables" / "wb_fx_official_rate_2026-02.csv", encoding="utf-8-sig") as f:
        lines = f.readlines()
    for row in csv.DictReader(lines[4:]):
        if row.get("Country Code") == iso3:
            return {y: float(row[str(y)]) for y in YEARS if row.get(str(y))}
    return {}


def build_company_anchors():
    """Returns the resource profit and tax to remove per (parent, source, year), taken directly from companies'
    audited accounts, for source countries where a few documented companies are the resource sector. Script 4 applies
    these anchors to every cell of an anchored source country (cells without an anchor get no strip) instead of the
    payment and ETR-gap routes.

    Saudi Arabia: the domestic cell is Saudi Aramco. The profit removed is Aramco's Upstream segment result (EBIT,
    after royalties and before tax), and all upstream activity is in the Kingdom. The tax removed is Aramco's Saudi income
    tax and zakat settled in the year (cash plus offsets against amounts due from the Government, the figure that
    matches the CbCR cash-tax line) times the Upstream share of positive segment EBIT, so that the downstream tax
    (refining, SABIC) stays with the downstream profit left in the pool.
    Source: source_tables/SAU_aramco_financials_2016_2024.csv."""
    rows = []
    p = SOURCE_TABLES / "SAU_aramco_financials_2016_2024.csv"
    if p.exists():
        a = pd.read_csv(p).pivot_table(index="year", columns="item", values="value_sar_m", aggfunc="first")
        usd = 1e6 / 3.75
        for y, r in a.iterrows():
            if int(y) not in YEARS:
                continue
            settled = sum(float(r[k]) for k in (
                "tax_paid_cash_company", "tax_paid_cash_subsidiaries",
                "tax_settled_offset_government", "tax_settled_other") if k in r and pd.notna(r[k]))
            up = float(r.get("upstream_segment_result", np.nan))
            down = r.get("downstream_segment_result", np.nan)
            down = max(float(down), 0.0) if pd.notna(down) else 0.0
            share_up = up / (up + down) if up > 0 else 0.0
            rows.append({"iso_parent": "SAU", "iso_partner": "SAU", "year": int(y),
                         "profit_removed_usd": max(up, 0.0) * usd,
                         "tax_removed_usd": settled * share_up * usd,
                         "company": "Saudi Aramco", "source_table": p.name})
    # Chevron (US parent) operates the Saudi half of the onshore Partitioned Zone and is the only foreign upstream
    # operator in Saudi Arabia. I take its documented Saudi income tax paid from its SEC Form SD reports (Rule 13q-1),
    # FY2023 onwards, and set profit = tax / 0.85 (the Saudi income-tax rate for oil producers with an investment
    # below SAR 225bn). There was no production from 2016 to mid-2020 (shut-in). For 2020–2022 (production restarted
    # in July 2020, no Form SD yet) I use the flagged estimate rows (item estimate_pz_taxes_paid): the step of the
    # US→SAU CbCR cash tax over its shut-in mean of 2016–19, times the FY2023 ratio of Chevron's documented tax to that
    # step, the lowest of three estimates (method and range in the row's note). Documented Form SD rows win where both
    # exist.
    p = SOURCE_TABLES / "USA_chevron_saudi_2016_2024.csv"
    if p.exists():
        c = pd.read_csv(p)
        c = c[c["item"].isin(["sd_pz_taxes_paid", "estimate_pz_taxes_paid"])].copy()
        c["year"] = pd.to_numeric(c["year"], errors="coerce")
        c["value"] = pd.to_numeric(c["value"], errors="coerce")
        c = (c.dropna(subset=["year", "value"])
             .assign(_est=lambda x: x["item"].eq("estimate_pz_taxes_paid"))
             .sort_values(["year", "_est"]).drop_duplicates("year"))
        for _, r in c.iterrows():
            if int(r["year"]) not in YEARS:
                continue
            tax = r["value"] * 1e3                          # USD thousand -> USD
            rows.append({"iso_parent": "USA", "iso_partner": "SAU", "year": int(r["year"]),
                         "profit_removed_usd": tax / 0.85, "tax_removed_usd": tax,
                         "company": "Chevron (Partitioned Zone)" + (" [ESTIMATE]" if r["_est"] else ""),
                         "source_table": p.name})
    # Australia: every resource entity in the ATO Corporate Tax Transparency data (income of A$100m or more), mapped
    # to its group's CbCR filing country by source_tables/AUS_resource_entity_map.csv (a mapping reviewed by hand).
    # The tax removed is the income tax payable plus the PRRT payable. The profit removed is the taxable income plus
    # PRRT (PRRT is
    # deductible, so taxable income is after it). I map ATO income years to CbCR years by the group's balance month
    # (for December, calendar year Y is income year Y–(Y+1), for June or March it is (Y−1)–Y) and convert at the World
    # Bank period-average rate. The compiled group table AUS_group_anchors_2016_2023.csv (public CbCR line, then
    # company tax report, then the ATO fallback, per group-year) is the Australian anchor. I keep the ATO-only rows
    # below only for the map's groups that the table does not cover (matched by name, aliases listed here).
    pm = SOURCE_TABLES / "AUS_resource_entity_map.csv"
    pa = SOURCE_TABLES / "AUS_ato_tax_transparency_2016_2024.csv"
    pg = SOURCE_TABLES / "AUS_group_anchors_2016_2023.csv"
    _aus_alias = {"EXXON MOBIL CORPORATION": "ExxonMobil", "MITSUBISHI CORPORATION": "Mitsubishi Corporation",
                  "MITSUI & CO LTD": "Mitsui & Co", "NEWMONT CORPORATION": "Newmont",
                  "PEABODY GLOBAL INVESTMENTS, LLC": "Peabody Energy", "RIO TINTO LIMITED": "Rio Tinto"}
    if pm.exists() and pa.exists():
        emap = pd.read_csv(pm, dtype={"abn": str})
        emap = emap[emap["include"].astype(str).str.lower() == "true"]
        if pg.exists():
            compiled = set(pd.read_csv(pg)["group"].astype(str))
            canon = emap["group"].map(lambda g: _aus_alias.get(g, g))
            covered = canon.map(lambda g: any(c == g or c.startswith(g + " (") for c in compiled))
            print(f"  AUS: ATO-only fallback kept for {emap.loc[~covered, 'group'].nunique()} map groups "
                  f"not in {pg.name}: {sorted(emap.loc[~covered, 'group'].unique())}")
            emap = emap[~covered]
        ato = pd.read_csv(pa, low_memory=False)
        ato["abn"] = pd.to_numeric(ato["abn"], errors="coerce").dropna().astype("int64").astype(str).str.zfill(11)
        ato = ato.merge(emap[["abn", "group", "hq_iso3", "balance_month"]], on="abn", how="inner")
        y0 = ato["income_year"].str[:4].astype(int)
        ato["year"] = np.where(ato["balance_month"] == 12, y0, y0 + 1)
        ato["hq"] = np.where(ato["hq_iso3"] == "SHELL", np.where(ato["year"] <= 2021, "NLD", "GBR"), ato["hq_iso3"])
        f = lambda c: pd.to_numeric(ato[c], errors="coerce").fillna(0.0)   # noqa: E731
        ato["tax_aud"] = f("tax_payable_aud") + f("prrt_payable_aud")
        ato["profit_aud"] = f("taxable_income_aud") + f("prrt_payable_aud")
        fx = _wb_fx("AUS")
        g = (ato[ato["year"].isin(YEARS)].groupby(["hq", "year"], as_index=False)[["profit_aud", "tax_aud"]].sum())
        for r in g.itertuples():
            rate = fx.get(int(r.year))
            if not rate:
                continue
            rows.append({"iso_parent": r.hq, "iso_partner": "AUS", "year": int(r.year),
                         "profit_removed_usd": r.profit_aud / rate, "tax_removed_usd": r.tax_aud / rate,
                         "company": "ATO resource entities (groups not compiled)", "source_table": f"{pa.name} + {pm.name}"})
    # Generic group-anchor tables, one per source country, compiled from company and official data:
    # source_tables/<ISO3>_group_anchors_2016_2023.csv with the columns filing_iso3, source_iso3, group, year,
    # profit_usd_m and tax_usd_m (nominal USD million, a null profit meaning no strip for that group-year, a null tax
    # meaning that script 4 removes the cell's tax in proportion to the group's profit),
    # plus provenance columns. I sum them per (filing, source, year). A country with such a table is anchored in full:
    # its cells without a documented group get no strip. With the optional column
    # anchor_mode = "cell", only the listed (filing, source, year) cells are anchored. The source's other cells keep
    # the inferred correction (a separately labelled layer, used where company data are shown to be missing). A
    # cell-mode row with a documented profit but no documented tax gets its tax side inferred in script 4 (the
    # residual profit taxed at the statutory CIT).
    for p in sorted(SOURCE_TABLES.glob("*_group_anchors_2016_2023.csv")):
        if "inferred_layers" in RESOURCE_INFERRED_OFF and "inferred" in p.name:
            print(f"  [RESOURCE_INFERRED_OFF] inferred layer skipped: {p.name}")
            continue
        g = pd.read_csv(p)
        if "inferred_layers" in RESOURCE_INFERRED_OFF and p.name.startswith("MYS_"):
            _pet = g["group"].astype(str).str.contains("PETRONAS", case=False)
            print(f"  [RESOURCE_INFERRED_OFF] PETRONAS rows skipped in {p.name}: {int(_pet.sum())}")
            g = g[~_pet]
        mode = str(g["anchor_mode"].dropna().iloc[0]) if "anchor_mode" in g.columns and g["anchor_mode"].notna().any() else "country"
        g = g[g["year"].isin(YEARS)]
        for c in ("profit_usd_m", "tax_usd_m"):
            g[c] = pd.to_numeric(g[c], errors="coerce")
        # The profit of group-years with a documented profit but no documented tax. Script 4 removes the cell's tax
        # in proportion to it, because a missing tax figure does not mean that no tax was paid. A tax of zero in the
        # table means that a source states that none was paid, and it stays zero.
        g["_profit_tax_undoc"] = g["profit_usd_m"].where(g["profit_usd_m"].notna() & g["tax_usd_m"].isna(), 0.0)
        agg = g.groupby(["filing_iso3", "source_iso3", "year"], as_index=False).agg(
            profit=("profit_usd_m", lambda s: s.sum(min_count=1)),
            tax=("tax_usd_m", lambda s: s.sum(min_count=1)),
            profit_tax_undoc=("_profit_tax_undoc", "sum"),
            groups=("group", lambda s: "; ".join(sorted(set(map(str, s))))))
        for r in agg.itertuples():
            rows.append({"iso_parent": r.filing_iso3, "iso_partner": r.source_iso3, "year": int(r.year),
                         "profit_removed_usd": r.profit * 1e6,
                         "tax_removed_usd": r.tax * 1e6,
                         "profit_tax_undocumented_usd": r.profit_tax_undoc * 1e6,
                         "company": r.groups, "source_table": p.name, "anchor_mode": mode})
    out = pd.DataFrame(rows, columns=["iso_parent", "iso_partner", "year", "profit_removed_usd",
                                      "tax_removed_usd", "profit_tax_undocumented_usd", "company", "source_table",
                                      "anchor_mode"])
    out["profit_tax_undocumented_usd"] = out["profit_tax_undocumented_usd"].fillna(0.0)
    out["anchor_mode"] = out["anchor_mode"].fillna("country")
    # Distinct groups can land in the same CbCR cell (e.g. the Australian ATO-only fallback plus compiled groups). I
    # emit exactly one row per cell, keep the provenance and leave an entirely undocumented amount missing.
    keys = ["iso_parent", "iso_partner", "year"]
    if out[keys].isna().any().any():
        raise ValueError("Company anchors contain missing parent/source/year keys")
    out = out.groupby(keys, as_index=False).agg(
        profit_removed_usd=("profit_removed_usd", lambda s: s.sum(min_count=1)),
        tax_removed_usd=("tax_removed_usd", lambda s: s.sum(min_count=1)),
        profit_tax_undocumented_usd=("profit_tax_undocumented_usd", "sum"),
        company=("company", lambda s: "; ".join(sorted(set(s.dropna().astype(str))))),
        source_table=("source_table", lambda s: "; ".join(sorted(set(s.dropna().astype(str))))),
        anchor_mode=("anchor_mode", lambda s: "cell" if (s == "cell").all() else "country"),
    )
    mixed = out.groupby("iso_partner")["anchor_mode"].nunique()
    if (mixed > 1).any():
        raise ValueError(f"Source countries with both country- and cell-mode anchors: {list(mixed[mixed > 1].index)}")
    out.to_csv(OUT_ANCHOR, index=False)
    print(f"  Wrote {OUT_ANCHOR} ({len(out)} anchored cells: "
          f"{', '.join(sorted(set(out.iso_parent + '->' + out.iso_partner)))})")


if __name__ == "__main__":
    main()
    build_company_anchors()
