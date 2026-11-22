# %%
"""
3_21 — Clean the raw EITI production extract into a tidy panel.

This script cleans and aggregates the raw EITI XLSX extract into a tidy
country-commodity-year panel for the downstream rent estimate.

Steps:
  1. I keep the production-volume and production-value rows. The export rows serve only as
     a fallback where the production side is blank.
  2. I normalise the physical units to one canonical unit per HS code (gold and metals in
     tonnes, oil and gas in Sm3, diamonds in carats).
  3. I drop exact-duplicate rows, which come from templates that list the same value in
     several sheets or sub-tables.
  4. I sum the remaining rows within (iso3, fy_end_year, hs_code), which rolls the project-
     and mine-level reporting up into country-commodity-year totals.
  5. I attach the canonical English commodity name and the pipeline category.
  6. I build the gross-revenue columns that the downstream rent estimate uses:
       - value_money_usd:               the reported value converted to USD (WB FX
                                        for local-currency reports, as is for USD).
       - gross_revenue_reconstructed_usd: volume x reference price (always
                                        available, kept for
                                        transparency and sensitivity).
       - gross_revenue_usd (preferred):  three-way blend — the reported USD value, else the
                                        reported local value x FX, else the
                                        reconstructed volume x price figure.
       - gross_revenue_source:           "reported_usd" | "reported_local_fx" |
                                        "reconstructed" | "missing".
  7. In a magnitude-reconciliation pass, I cross-check the volume-implied revenue against the
     reported value where one exists. I correct clean power-of-10 mismatches (x1000 gas,
     x1000/x1e6 gold etc., known quirks of the EITI templates) in `volume_total` and log them.
     Volume-only cells get per-commodity sanity caps as a backstop. The applied factor is in
     `volume_scale_adjustment` (1.0 = untouched).

Section outline (numbers match the cell headings below):
1. Setup.
2. Config and lookups.
3. Normalization and pricing helpers.
4. Build clean panel.

Pipeline: Extractive prep, stage 3_21 — after the 3_1x source ingests, before 3_22.

Reads:
  data/intermediate/extractive/eiti_xlsx_production.csv   — parsed EITI XLSXs (3_12)
  data/raw/macro_variables/wb_fx_official_rate_2026-02.csv — WB official FX rate

Writes:
  data/intermediate/extractive/eiti_production_clean_long.csv        — cleaned long panel
  data/intermediate/extractive/eiti_production_by_category_yearly.csv — country x category x year rollup

Usage:
  python src/3_extractive_prep/3_21_eiti_to_clean_panel.py

Author: Tax Justice Network.
Created: 2026-07-17.  Last updated: 2026-07-25.
"""

# %% MARK: 1. Setup
import sys
import math
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import RAW, EXT_INT
from _reference_prices import (
    MINERAL_PRICES, HS_PRICE_UNIT, MINERAL_VOL_TO_PRICE_MULT,
    BRENT_USD_BBL, HENRY_HUB_USD_MMBTU, COAL_AUS_USD_T,
)

# %% MARK: 2. Config and lookups
IN = EXT_INT / "eiti_xlsx_production.csv"           # parsed from the EITI XLSXs by 3_12
FX_CSV = RAW / "macro_variables/wb_fx_official_rate_2026-02.csv"
OUT_LONG = EXT_INT / "eiti_production_clean_long.csv"
OUT_CAT = EXT_INT / "eiti_production_by_category_yearly.csv"

# Canonical English name per HS-4 code.
HS_TO_NAME = {
    "2501": "Salt", "2505": "Natural sands", "2510": "Natural calcium phosphates",
    "2515": "Marble", "2516": "Granite",
    "2601": "Iron ore", "2602": "Manganese ore", "2603": "Copper ore",
    "2604": "Nickel ore", "2605": "Cobalt ore", "2606": "Aluminium ore (bauxite)",
    "2607": "Lead ore", "2608": "Zinc ore", "2609": "Tin ore", "2610": "Chromium ore",
    "2611": "Tungsten ore", "2613": "Molybdenum ore", "2614": "Titanium ore",
    "2615": "Niobium/Vanadium/Zirconium", "2616": "Precious metal ores", "2617": "Other ores",
    "2701": "Coal", "2702": "Lignite",
    "2709": "Crude oil", "2710": "Petroleum products (refined)", "2711": "Natural gas",
    "7102": "Diamonds", "7106": "Silver", "7108": "Gold", "7110": "Platinum-group metals",
}
HS_TO_CATEGORY = {
    "2501": "other", "2505": "other", "2515": "other", "2516": "other",
    "2510": "minerals",
    "2601": "minerals", "2602": "minerals", "2603": "minerals", "2604": "minerals",
    "2605": "minerals", "2606": "minerals", "2607": "minerals", "2608": "minerals",
    "2609": "minerals", "2610": "minerals", "2611": "minerals", "2613": "minerals",
    "2614": "minerals", "2615": "minerals", "2616": "minerals",
    "2617": "other",   # "Other ores": unidentifiable catch-all without a meaningful price, not in the resource base

    "2701": "coal", "2702": "coal",
    "2709": "oil_gas", "2710": "oil_gas", "2711": "oil_gas",
    "7102": "minerals", "7106": "minerals", "7108": "minerals", "7110": "minerals",
}

# (pattern, canonical_unit, multiplier_to_canonical). I match the patterns after lowercasing the
# raw unit string, fixing common mojibake (Ã© becomes e, etc.), stripping diacritics and
# collapsing whitespace. "Toneladas métricas", "tonnes métriques" and the mojibake "Toneladas
# mÃ©tricas" thus all reduce to "toneladas metricas" / "tonnes metriques" before matching.
# Longer and more specific patterns must come before their prefixes.
UNIT_RULES = [
    # mass — tonnes (en / es / pt / fr)
    ("metric tonnes", "tonnes", 1.0), ("metric ton", "tonnes", 1.0),
    ("toneladas metricas", "tonnes", 1.0), ("tonelada metrica", "tonnes", 1.0),
    ("tonnes metriques", "tonnes", 1.0), ("tonne metrique", "tonnes", 1.0),
    ("toneladas largas", "tonnes", 1.016047),     # long tons
    ("kt", "tonnes", 1000.0), ("thousand tonnes", "tonnes", 1000.0),
    ("miles de toneladas", "tonnes", 1000.0), ("milhares de toneladas", "tonnes", 1000.0),
    ("milliers de tonnes", "tonnes", 1000.0),
    ("tonnes", "tonnes", 1.0), ("tonne", "tonnes", 1.0),
    ("toneladas", "tonnes", 1.0), ("tonelada", "tonnes", 1.0),
    ("tons", "tonnes", 1.0), ("ton", "tonnes", 1.0), ("mt", "tonnes", 1.0),
    # kg / g
    ("kilogrammes", "tonnes", 0.001), ("kilogramos", "tonnes", 0.001),
    ("quilogramas", "tonnes", 0.001), ("kilograms", "tonnes", 0.001),
    ("kilogram", "tonnes", 0.001), ("kilos", "tonnes", 0.001), ("kg", "tonnes", 0.001),
    ("grammes", "tonnes", 1e-6), ("gramos", "tonnes", 1e-6), ("gramas", "tonnes", 1e-6),
    ("grams", "tonnes", 1e-6), ("gram", "tonnes", 1e-6), ("g", "tonnes", 1e-6),
    # troy ounces / pounds
    ("onzas troy", "tonnes", 3.11034768e-5), ("troy oz", "tonnes", 3.11034768e-5),
    ("oncas", "tonnes", 3.11034768e-5), ("onces", "tonnes", 3.11034768e-5),
    ("onzas", "tonnes", 3.11034768e-5), ("ounces", "tonnes", 3.11034768e-5),
    ("oz", "tonnes", 3.11034768e-5),
    ("lbs", "tonnes", 4.5359237e-4), ("lb", "tonnes", 4.5359237e-4),
    ("pounds", "tonnes", 4.5359237e-4), ("libras", "tonnes", 4.5359237e-4),
    # gas / liquid volume
    ("thousand sm3", "Sm3", 1000.0), ("thousand m3", "Sm3", 1000.0),
    ("million sm3", "Sm3", 1e6), ("million m3", "Sm3", 1e6),
    ("millones de m3", "Sm3", 1e6), ("milhoes de m3", "Sm3", 1e6), ("millions de m3", "Sm3", 1e6),
    ("billion sm3", "Sm3", 1e9), ("billion m3", "Sm3", 1e9),
    ("sm3 o.e.", "Sm3 o.e.", 1.0), ("sm3oe", "Sm3 o.e.", 1.0),
    ("sm3", "Sm3", 1.0), ("scm", "Sm3", 1.0), ("m3", "Sm3", 1.0),
    # cubic feet (1 ft³ = 0.0283168 m³)
    ("tcf", "Sm3", 2.83168e10), ("bcf", "Sm3", 2.83168e7),
    ("mmscf", "Sm3", 28316.8), ("mmcf", "Sm3", 28316.8),
    ("mscf", "Sm3", 28.3168), ("mcf", "Sm3", 28.3168), ("scf", "Sm3", 0.0283168),
    ("metros cubicos", "Sm3", 1.0), ("metros cubos", "Sm3", 1.0), ("metres cubes", "Sm3", 1.0),
    ("barriles", "Sm3", 0.158987), ("barris", "Sm3", 0.158987), ("barils", "Sm3", 0.158987),
    ("barrels", "Sm3", 0.158987), ("barrel", "Sm3", 0.158987), ("bbl", "Sm3", 0.158987),
    # gems
    ("carats", "carats", 1.0), ("carat", "carats", 1.0), ("quilates", "carats", 1.0),
    # energy
    ("mmbtu", "MMBtu", 1.0),
]

# Common mojibake digraphs (UTF-8 decoded as Latin-1, lowercased) and the letter each stands for.
_MOJIBAKE = {
    "ã©": "e", "ã¨": "e", "ãª": "e",
    "ã³": "o", "ã²": "o", "ã´": "o",
    "ã¡": "a", "ã ": "a", "ã¢": "a", "ã£": "a",
    "ã­": "i", "ã¬": "i", "ã®": "i",
    "ãº": "u", "ã¹": "u", "ã»": "u", "ã¼": "u",
    "ã±": "n", "ã§": "c",
}


# %% MARK: 3. Normalization and pricing helpers
def _normalize_unit_string(raw_unit: str) -> str:
    """Lowercases a unit string, fixes mojibake, strips diacritics and collapses whitespace."""
    s = str(raw_unit).strip().lower().replace("(", " ").replace(")", " ")
    for bad, good in _MOJIBAKE.items():
        s = s.replace(bad, good)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.split())

# Per-commodity plausibility ceiling on the physical volume of one (iso3, year): the world's
# largest producer plus headroom. I use it only as a backstop for cells without a reported value
# to cross-check against. The units are the canonical units.
VOLUME_CAP = {
    "7108": 500.0,        # gold, tonnes  (China, about 370 t a year, is the global maximum)
    "7106": 9000.0,       # silver, tonnes (Mexico about 6,000 t)
    "7110": 350.0,        # PGMs, tonnes  (South Africa about 250 t Pt+Pd+Rh)
    "7102": 2.5e8,        # diamonds, carats (global about 150M carats a year)
    "2603": 1.0e8,        # copper ore-equivalent tonnes, generous (Chile about 28 Mt of Cu metal, much more ore)
    "2601": 1.5e9,        # iron ore, tonnes (Australia and Brazil about 900 Mt each)
}

# Reference price per (HS code or category, year) for the reconstruction path.
def _ref_price(category, hs_code, year):
    year = int(year)
    if category == "minerals":
        return MINERAL_PRICES.get(hs_code, {}).get(year)
    if category == "oil_gas" and hs_code in ("2709", "2710"):
        # I convert Sm3 of crude to barrels at 6.2898 bbl/m3 and price them at Brent ($/bbl).
        return _yearly(BRENT_USD_BBL, year) * 6.2898
    if category == "oil_gas" and hs_code == "2711":
        # I convert Sm3 of gas to MMBtu at about 0.0383 and price them at Henry Hub ($/MMBtu).
        return _yearly(HENRY_HUB_USD_MMBTU, year) * 0.0383
    if category == "coal":
        return _yearly(COAL_AUS_USD_T, year)
    return None


def _yearly(table, year):
    year = int(year)
    if year in table:
        return table[year]
    avail = sorted(table.keys())
    return table[avail[0]] if year < avail[0] else table[avail[-1]]


# Conversions between mass and volume for the rare reports of hydrocarbons by mass:
#   1 tonne LNG  ≈ 1,360 Sm³ of natural gas (vapour, standard conditions)
#   1 tonne crude ≈ 7.33 bbl ≈ 7.33 / 6.2898 ≈ 1.165 Sm³
TONNES_LNG_TO_SM3 = 1360.0
TONNES_CRUDE_TO_SM3 = 7.33 / 6.2898


def _price_unit_mult(category, hs_code, volume_unit):
    """Returns the multiplier for which revenue = volume × mult × ref_price.

    For minerals, the table that converts volume units to price units handles ounces and
    carats. For oil_gas, ref_price is in $/Sm3, so mult is 1.0 for Sm³, or a mass-to-Sm³
    factor when the hydrocarbon was reported in tonnes. For coal, ref_price is in $/tonne."""
    if category == "minerals":
        return MINERAL_VOL_TO_PRICE_MULT.get((volume_unit, HS_PRICE_UNIT.get(hs_code)))
    if category == "oil_gas":
        if volume_unit in ("Sm3", "Sm3 o.e."):
            return 1.0
        if volume_unit == "tonnes":
            return TONNES_LNG_TO_SM3 if hs_code == "2711" else TONNES_CRUDE_TO_SM3
        return None
    if category == "coal":
        return 1.0 if volume_unit == "tonnes" else None
    return None


def normalize_unit(raw_unit: str, hs_code: str):
    if not raw_unit:
        return "", 1.0
    s = _normalize_unit_string(raw_unit)
    if not s:
        return str(raw_unit).strip(), 1.0
    for raw_pat, canon, mult in UNIT_RULES:
        if s == raw_pat or s.startswith(raw_pat + " ") or s.startswith(raw_pat + "."):
            return canon, mult
    return str(raw_unit).strip(), 1.0


def load_fx() -> dict:
    """Returns {(country_iso3, year): LCU per USD} from the World Bank series PA.NUS.FCRF."""
    if not FX_CSV.exists():
        print(f"  [warn] {FX_CSV} not present — local-currency reports can't be "
              f"converted to USD; those fall back to volume × price.")
        return {}
    raw = pd.read_csv(FX_CSV, skiprows=4)
    year_cols = [c for c in raw.columns if c.strip().isdigit()]
    long = raw.melt(id_vars=["Country Code"], value_vars=year_cols,
                    var_name="year", value_name="fx")
    long["year"] = long["year"].astype(int)
    long["fx"] = pd.to_numeric(long["fx"], errors="coerce")
    long = long[long["fx"].notna() & (long["fx"] > 0)]
    return {(r["Country Code"], int(r["year"])): float(r["fx"])
            for _, r in long.iterrows()}


# %% MARK: 4. Build clean panel
def main():
    print(f"Loading {IN}...")
    df = pd.read_csv(IN)
    print(f"  {len(df):,} rows in")
    fx = load_fx()
    print(f"  {len(fx):,} (country, year) FX rates loaded")

    # I keep both the production (Requirement 3.2) and the export (Requirement 3.3) rows. I use
    # the export figures only as a fallback where the production value or volume is missing (a
    # `< number >` placeholder etc.). This is common for oil- and gas-heavy exporters like
    # Ecuador, whose report fills in only the exports section. The export value understates the
    # production value by the domestically consumed share, but for big exporters that share is
    # small, and the export value is a much better estimate than volume × benchmark price.
    prod = df[df["section"].isin(["production", "exports"])].copy()
    prod["hs_code"] = prod["hs_code"].astype(str).str.strip()
    prod["fy_end_year"] = pd.to_numeric(prod["fy_end_year"], errors="coerce")
    prod = prod.dropna(subset=["fy_end_year", "hs_code"])
    prod["year"] = prod["fy_end_year"].astype(int)
    prod = prod[prod["year"].between(2010, 2030)]
    prod["value"] = pd.to_numeric(prod["value"], errors="coerce")
    prod = prod.dropna(subset=["value"])

    prod["category"] = prod["hs_code"].map(HS_TO_CATEGORY).fillna("unmapped")
    prod["commodity_name_canonical"] = prod["hs_code"].map(HS_TO_NAME).fillna(
        prod["commodity_name"]
    )

    # I reclassify the "volume" rows whose unit is actually a currency code (a known quirk of
    # the EITI templates: the monetary value leaked into the production-volume column). If the
    # raw unit is three uppercase letters and normalize_unit does not recognise it as a physical
    # unit, I treat the row as a value row in that currency. This recovers a reported value that
    # would otherwise be lost. ("TON" is excluded because normalize_unit does recognise it.)
    KNOWN_NON_CURRENCY_3CHAR = {"NAN", "TON", "OZS", "LBS", "MMT", "BBL", "SM3"}

    def _looks_like_currency(raw_unit):
        if raw_unit is None or (isinstance(raw_unit, float) and pd.isna(raw_unit)):
            return False
        u = str(raw_unit).strip().upper()
        if not (len(u) == 3 and u.isalpha()) or u in KNOWN_NON_CURRENCY_3CHAR:
            return False
        canon, _ = normalize_unit(raw_unit, "")
        return canon == str(raw_unit).strip()   # unrecognised by UNIT_RULES
    misclassified = (prod["measure"] == "volume") & prod["unit"].apply(_looks_like_currency)
    n_misclass = int(misclassified.sum())
    if n_misclass:
        prod.loc[misclassified, "measure"] = "value"
        seen = sorted({str(x).strip().upper() for x in prod.loc[misclassified, "unit"]
                       if pd.notna(x)})
        print(f"  reclassified {n_misclass} volume rows with a currency-code "
              f"unit as value rows: {seen}")

    def norm_unit_row(r):
        if r["measure"] != "volume":
            return pd.Series({"unit_canon": r["unit"], "value_norm": r["value"]})
        canon, mult = normalize_unit(r["unit"], r["hs_code"])
        return pd.Series({"unit_canon": canon, "value_norm": r["value"] * mult})

    norm = prod.apply(norm_unit_row, axis=1)
    prod["unit_canon"] = norm["unit_canon"]
    prod["value_norm"] = norm["value_norm"]

    n_before = len(prod)
    prod = prod.drop_duplicates(
        subset=["iso3", "year", "hs_code", "measure", "unit_canon", "value_norm"]
    )
    print(f"  dropped {n_before - len(prod)} exact duplicates")

    # I de-duplicate and aggregate within (iso3, year, hs_code, section, measure, unit).
    n_before = len(prod)
    prod = prod.drop_duplicates(
        subset=["iso3", "year", "hs_code", "section", "measure", "unit_canon", "value_norm"]
    )
    if n_before - len(prod):
        print(f"  dropped {n_before - len(prod)} more exact dups (incl. exports)")

    grouped = (
        prod.groupby(
            ["iso3", "year", "hs_code", "section", "measure", "unit_canon", "category"],
            dropna=False, as_index=False,
        )
        .agg(
            value_total=("value_norm", "sum"),
            n_rows=("value_norm", "size"),
            commodity_name_canonical=("commodity_name_canonical", "first"),
            source_files=("source_file", lambda s: "; ".join(sorted(set(s)))),
        )
    )

    KEYS = ["iso3", "year", "hs_code"]
    vol_p = grouped[(grouped["measure"] == "volume") & (grouped["section"] == "production")]
    vol_e = grouped[(grouped["measure"] == "volume") & (grouped["section"] == "exports")]
    val_p = grouped[(grouped["measure"] == "value") & (grouped["section"] == "production")]
    val_e = grouped[(grouped["measure"] == "value") & (grouped["section"] == "exports")]

    # I prefer the production volume and use the export volume as the fallback for cells that
    # the production side left blank.
    vol = vol_p[KEYS + ["value_total", "unit_canon", "n_rows", "category",
                        "commodity_name_canonical", "source_files"]].rename(
        columns={"value_total": "volume_total", "unit_canon": "volume_unit",
                 "n_rows": "n_volume_rows"})
    vol_e2 = vol_e[KEYS + ["value_total", "unit_canon", "category",
                           "commodity_name_canonical", "source_files"]].rename(
        columns={"value_total": "_vol_exp", "unit_canon": "_vol_exp_unit",
                 "category": "_cat_e", "commodity_name_canonical": "_name_e",
                 "source_files": "_src_e"})
    long_out = vol.merge(vol_e2, on=KEYS, how="outer")
    # I fill the volume from the exports where the production volume is missing.
    long_out["volume_source"] = np.where(long_out["volume_total"].notna(), "production",
                                         np.where(long_out["_vol_exp"].notna(), "exports", ""))
    long_out["volume_total"] = long_out["volume_total"].fillna(long_out["_vol_exp"])
    long_out["volume_unit"] = long_out["volume_unit"].fillna(long_out["_vol_exp_unit"])
    long_out["category"] = long_out["category"].fillna(long_out["_cat_e"])
    long_out["commodity_name_canonical"] = long_out["commodity_name_canonical"].fillna(long_out["_name_e"])
    long_out["source_files"] = long_out["source_files"].fillna(long_out["_src_e"])
    long_out = long_out.drop(columns=["_vol_exp", "_vol_exp_unit", "_cat_e", "_name_e", "_src_e"])

    # I take the production value, with the export value as the fallback.
    long_out = long_out.merge(
        val_p[KEYS + ["value_total", "unit_canon"]].rename(
            columns={"value_total": "value_money_total", "unit_canon": "value_currency"}),
        on=KEYS, how="left")
    long_out = long_out.merge(
        val_e[KEYS + ["value_total", "unit_canon"]].rename(
            columns={"value_total": "value_export_total", "unit_canon": "value_export_currency"}),
        on=KEYS, how="left")
    long_out["category"] = long_out["category"].fillna(long_out["hs_code"].map(HS_TO_CATEGORY))
    long_out["commodity_name_canonical"] = long_out["commodity_name_canonical"].fillna(
        long_out["hs_code"].map(HS_TO_NAME)
    )
    if "n_volume_rows" not in long_out.columns:
        long_out["n_volume_rows"] = np.nan

    # ---- Step 6a: reported value converted to USD ----
    # I treat a reported value below this absolute floor as "not disclosed" (a zero or blank
    # cell that parsed as a tiny number).
    MIN_REPORTED_USD = 5.0e4

    def _one_value_usd(v, c, iso, year):
        if pd.isna(v) or v <= 0:
            return np.nan
        c = str(c).strip() if pd.notna(c) else ""
        if c.upper() == "USD":
            usd = float(v)
        elif not (len(c) == 3 and c.isalpha()):
            return np.nan          # e.g. a unit string that leaked into the currency column
        else:
            rate = fx.get((iso, int(year)))
            if rate is None or rate <= 0:
                return np.nan
            usd = float(v) / rate
        return usd if usd >= MIN_REPORTED_USD else np.nan

    def _value_usd(r):
        """Returns (usd, source) for one row. I prefer the value of the production section
        and fall back to the value of the exports section (Requirement 3.3) when the production
        section left it blank."""
        prod_usd = _one_value_usd(r["value_money_total"], r["value_currency"],
                                  r["iso3"], r["year"])
        if pd.notna(prod_usd):
            return pd.Series({"value_money_usd": prod_usd, "value_section": "production"})
        exp_usd = _one_value_usd(r.get("value_export_total"), r.get("value_export_currency"),
                                 r["iso3"], r["year"])
        if pd.notna(exp_usd):
            return pd.Series({"value_money_usd": exp_usd, "value_section": "exports"})
        return pd.Series({"value_money_usd": np.nan, "value_section": ""})
    long_out[["value_money_usd", "value_section"]] = long_out.apply(_value_usd, axis=1)

    # ---- Step 7: magnitude-reconciliation of volumes ----
    # (a) Where a reported USD value exists and volume × price disagrees with it by a clean power
    #     of 10 (×10^3 or ×10^6 in either direction, the known scale quirks of the EITI templates
    #     for gas and gold), I rescale the volume.
    # (b) Volume-only cells get a per-commodity sanity cap. If a volume exceeds it, I divide it
    #     by 10^3 (kilograms mislabelled as tonnes) or 10^6 (grams as tonnes) to bring it under
    #     the cap.
    long_out["volume_scale_adjustment"] = 1.0
    POW10_CHOICES = [1e9, 1e6, 1e3, 1e-3, 1e-6, 1e-9]
    n_adj_xcheck = n_adj_cap = 0
    for idx, r in long_out.iterrows():
        cat, hs, year = r["category"], str(r["hs_code"]).strip(), int(r["year"])
        vol, unit = r["volume_total"], r["volume_unit"]
        if pd.isna(vol) or vol <= 0:
            continue
        price = _ref_price(cat, hs, year)
        mult = _price_unit_mult(cat, hs, unit)
        if price is None or mult is None:
            continue
        recon = vol * mult * price
        vusd = r["value_money_usd"]
        # I rescale on the cross-check only when the reported value is itself substantial (at
        # least $1M) and the rescaled reconstruction also reaches $1M, i.e. when the rescale
        # gives a sane magnitude on both sides. This prevents a spuriously tiny reported value
        # from shrinking a genuine volume to match it (e.g. a country that disclosed about $0 for
        # a commodity worth billions). The blend guard in step 6c handles that case instead.
        if pd.notna(vusd) and vusd >= 1.0e6 and recon > 0:
            ratio = vusd / recon            # above 1: the volume is too small and is scaled up
            best_k, best_err = 1.0, abs(math.log10(ratio))
            for k in POW10_CHOICES:
                err = abs(math.log10(ratio / k))
                if err < best_err - 1e-9:
                    best_err, best_k = err, k
            if (best_k != 1.0 and best_err < math.log10(3.0)
                    and recon * best_k >= 1.0e6):
                long_out.at[idx, "volume_total"] = vol * best_k
                long_out.at[idx, "volume_scale_adjustment"] = best_k
                n_adj_xcheck += 1
                print(f"    [vol-rescale x{best_k:g}] {r['iso3']} {year} HS{hs} "
                      f"{r['commodity_name_canonical']}: {vol:g}→{vol*best_k:g} {unit} "
                      f"(reported ${vusd/1e6:,.1f}M vs recon ${recon/1e6:,.1f}M)")
        else:
            cap = VOLUME_CAP.get(hs)
            if cap is not None and vol > cap:
                # I bring the volume under the cap by dividing it by 10^3 or 10^6.
                k = 1e-3 if vol / 1e3 <= cap else (1e-6 if vol / 1e6 <= cap else None)
                if k is not None:
                    long_out.at[idx, "volume_total"] = vol * k
                    long_out.at[idx, "volume_scale_adjustment"] = k
                    n_adj_cap += 1
                    print(f"    [vol-cap x{k:g}] {r['iso3']} {year} HS{hs} "
                          f"{r['commodity_name_canonical']}: {vol:g}→{vol*k:g} {unit} "
                          f"(exceeded plausibility cap {cap:g})")
    print(f"  volume adjustments: {n_adj_xcheck} from value cross-check, "
          f"{n_adj_cap} from per-commodity cap")

    # ---- Step 6b: reconstructed revenue from (possibly adjusted) volume ----
    def _recon_usd(r):
        cat, hs, year = r["category"], str(r["hs_code"]).strip(), int(r["year"])
        vol, unit = r["volume_total"], r["volume_unit"]
        if pd.isna(vol) or vol <= 0:
            return np.nan
        price = _ref_price(cat, hs, year)
        mult = _price_unit_mult(cat, hs, unit)
        if price is None or mult is None:
            return np.nan
        return vol * mult * price
    long_out["gross_revenue_reconstructed_usd"] = long_out.apply(_recon_usd, axis=1)

    # ---- Step 6c: three-way blend (preferred) ----
    # I prefer the reported value (of the production section, or of the exports section as a
    # fallback), except when it is implausibly small relative to the volume-implied revenue
    # (below 2% of it, with the reconstruction itself at least $1M). That almost always means
    # that the report left the value cell blank or zero for a commodity it nonetheless produced,
    # so I fall back to the reconstruction.
    # Note: a value that is *consistently* small because both volume and value were reported
    # "in thousands" (e.g. Ecuador crude) cannot be caught here. The cross-source sanity filter
    # in 3_24, which drops an EITI rent far below the WB rent, handles that downstream.
    def _blend(r):
        vusd = r["value_money_usd"]
        vsec = str(r.get("value_section") or "")
        rec = r["gross_revenue_reconstructed_usd"]
        rec_ok = pd.notna(rec) and rec > 0
        if pd.notna(vusd) and vusd > 0:
            if rec_ok and rec >= 1.0e6 and vusd < 0.02 * rec:
                return pd.Series({"gross_revenue_usd": float(rec),
                                  "gross_revenue_source": "reconstructed_reported_too_low"})
            # The currency tag follows the section the value came from.
            ccy = (r["value_currency"] if vsec == "production" else r.get("value_export_currency"))
            is_usd = str(ccy).strip().upper() == "USD"
            base = "reported_usd" if is_usd else "reported_local_fx"
            src = base if vsec == "production" else f"{base}_export"
            return pd.Series({"gross_revenue_usd": float(vusd), "gross_revenue_source": src})
        if rec_ok:
            return pd.Series({"gross_revenue_usd": float(rec), "gross_revenue_source": "reconstructed"})
        return pd.Series({"gross_revenue_usd": np.nan, "gross_revenue_source": "missing"})
    long_out[["gross_revenue_usd", "gross_revenue_source"]] = long_out.apply(_blend, axis=1)

    long_out = long_out.sort_values(["iso3", "year", "category", "hs_code"]).reset_index(drop=True)

    cols = [
        "iso3", "year", "category", "hs_code", "commodity_name_canonical",
        "volume_total", "volume_unit", "volume_source", "volume_scale_adjustment",
        "value_money_total", "value_currency",
        "value_export_total", "value_export_currency",
        "value_money_usd", "value_section",
        "gross_revenue_reconstructed_usd", "gross_revenue_usd", "gross_revenue_source",
        "n_volume_rows", "source_files",
    ]
    for c in cols:
        if c not in long_out.columns:
            long_out[c] = np.nan
    long_out[cols].to_csv(OUT_LONG, index=False)
    print(f"\nWrote {len(long_out):,} rows -> {OUT_LONG}")

    # Category roll-up
    cat = (
        long_out.groupby(["iso3", "year", "category"], as_index=False)
        .agg(
            n_commodities=("hs_code", "nunique"),
            commodity_list=("commodity_name_canonical",
                            lambda s: ", ".join(sorted(set(str(x) for x in s if pd.notna(x))))),
            gross_revenue_usd=("gross_revenue_usd", "sum"),
        )
    )
    cat.to_csv(OUT_CAT, index=False)
    print(f"Wrote {len(cat):,} rows -> {OUT_CAT}")

    # ---- Console summary ----
    print("\n=== gross_revenue_source mix (minerals / oil_gas / coal) ===")
    for catname in ("minerals", "oil_gas", "coal"):
        sub = long_out[long_out["category"] == catname]
        vc = sub["gross_revenue_source"].value_counts().to_dict()
        print(f"  {catname:<9s} ({len(sub)} cells): {vc}")

    print("\n=== Coverage 2021-2022, by category, country count ===")
    target = long_out[long_out["year"].isin([2021, 2022])]
    for yr in (2021, 2022):
        for catname in ("oil_gas", "coal", "minerals"):
            sub = target[(target["year"] == yr) & (target["category"] == catname)]
            print(f"  {yr} {catname:<10s}: {sub['iso3'].nunique()} countries")


if __name__ == "__main__":
    main()
