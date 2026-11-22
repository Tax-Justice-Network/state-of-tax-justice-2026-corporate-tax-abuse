# %%
"""
Gravity feature matrix for the García-Bernardo & Janský (2024) activity imputation, 2014 to config.last_year.

This script builds the feature matrix of the gravity model. The targets are the
employees, unrelated-party sales and tangible assets that good reporters report in their
foreign CbCR cells. The features come from the cached gravity sources (CEPII Gravity,
World Bank WDI, WGI, IMF CDIS / CPIS).

CEPII Gravity V202211 ends in 2021, so the later years of the window need filled
features. Update mode (the default) fills every later year explicitly (rule below). A
plain one-year carry-forward of the previous year's features (replicate mode) leaves the
reported cells of the last year without features.

Two modes:
  --mode replicate  The one-year carry-forward rule (CEPII backbone, with the features of
                    the year before carried into the last year for pairs absent from
                    it), on the CbCR snapshot restricted to <= --last-year.
  --mode update     Default. 2014 to config.last_year (2023). CEPII Gravity V202211 ends in
                    2021, so for every later year (2022, 2023):
                      * The CEPII bilateral rows are the 2021 rows. Distance, contiguity,
                        language, colony, legal origin, religion and col45 are time-
                        invariant. heg/gatt/wto/fta_wto are carried as in 2021.
                        entry_cost/entry_proc are already empty since 2020, and the
                        trade flows are already empty in 2021, so they stay empty.
                      * The CEPII unilateral gdp/gdpcap/pop (thousands, CEPII units)
                        come from the World Bank files in data/raw/macro_variables/
                        (canonical GDP 2026-08, population 2026-02). A missing
                        country-year keeps the previous year's value.
                      * WB WDI block (data/raw/gravity/wb_*.csv, ends 2022): real 2022
                        values. For 2023, GDP, population and GDP per capita come from
                        data/raw/macro_variables/, and every other indicator keeps the
                        country's 2022 value.
                      * The WGI governance PCA is fitted as in replicate mode (the data
                        end in 2022). For 2023 each country keeps its 2022 score.
                      * IMF CDIS / CPIS (end 2022): for 2023 each pair keeps its 2022 value.
                    The CbCR targets include every FY2023 cell. Every row of a
                    fill year gets features, including the reported CbCR pairs that
                    the one-year carry-forward leaves without features.
  --fix-cepii-dedup Optional sensitivity (off by default). When an ISO3 code occurs twice in CEPII
                    (DEU, IDN, MYS, PAK, VNM, ETH, SDN, YEM, ANT — a historical '.1'
                    entity and a current '.2' entity), I keep the row whose country
                    exists in that year. The default keeps the first ('.1',
                    country_exists = 0, no data), which leaves those countries
                    without any CEPII features.

Section outline (numbers match the cell headings below):
1. CbCR targets — reported foreign country cells (Total, all sub-groups).
2. CEPII gravity backbone (o=parent, d=partner), year>=2014.
3. World Bank unilateral indicators.
4. WGI: one governance PCA component per (iso3, year).
5. IMF CDIS FDI and CPIS portfolio positions (bilateral).
6. Assemble.
   6.1 Last-year handling.
7. Log-transform the skewed level variables (the dummies stay as they are).

Reads:
  data/raw/gravity/Gravity_V202211.csv                — CEPII Gravity (1948-2021)
  data/raw/gravity/wb_*.csv, wgi_*.csv                — WB WDI / WGI caches (to 2022)
  data/raw/gravity/imf_cdis_inward.csv, imf_cpis_assets.csv — IMF bilateral (to 2022)
  data/raw/macro_variables/wb_gdp_current_usd_2026-08.csv   — canonical WB GDP (to 2023)
  data/raw/macro_variables/wb_gdp_population_2026-02.csv    — WB GDP + population (to 2024)
  data/final/cbcr_main_allsubgroupsonly.csv            — CbCR targets (Total, all sub-groups)
Writes:
  data/intermediate/gravity/gravity_feature_matrix.parquet — feature matrix (or --out)
Usage:
  python src/gravity/build_features.py                        — update mode (default), standard paths
  python src/gravity/build_features.py --mode replicate --last-year 2022 --out <dir>   — the one-year carry-forward rule

Author: Tax Justice Network (based on the method of García-Bernardo and Janský).
Last updated: 2026-11-23.
"""

# %%
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src", "gravity"))
sys.path.insert(0, os.path.join(ROOT, "src"))
from _ifs_iso3 import IFS_TO_ISO3  # noqa: E402
from config import last_year as _CFG_LAST_YEAR  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw", "gravity")
MACRO = os.path.join(ROOT, "data", "raw", "macro_variables")
GRAV = os.path.join(ROOT, "data", "intermediate", "gravity")

ap = argparse.ArgumentParser()
ap.add_argument("--mode", choices=["replicate", "update"], default="update")
ap.add_argument("--last-year", type=int, default=_CFG_LAST_YEAR)
ap.add_argument("--out", default=GRAV)
ap.add_argument("--cbcr", default=os.path.join(ROOT, "data", "final", "cbcr_main_allsubgroupsonly.csv"))
ap.add_argument("--fix-cepii-dedup", action="store_true")
args = ap.parse_args()
OUT = args.out
os.makedirs(OUT, exist_ok=True)
LAST_YEAR = args.last_year
YEARS = list(range(2014, LAST_YEAR + 1))
print(f"mode={args.mode}  years={YEARS[0]}-{YEARS[-1]}  fix_cepii_dedup={args.fix_cepii_dedup}")

# %% MARK: 1. CbCR targets — reported foreign country cells (Total, all sub-groups)
cb = pd.read_csv(
    args.cbcr,
    usecols=["iso_parent", "iso_partner", "year", "n_employees",
             "unrelated_party_revenues", "tangible_assets_except_cash"],
)
cb = cb[cb["year"] <= LAST_YEAR]
AGG = {"W", "A", "E", "F", "S", "WXD", "A_O", "E_O", "F_O", "S_O", "W_O", "X"}
cb = cb[~cb["iso_partner"].isin(AGG) & ~cb["iso_parent"].isin(AGG)]
cb = cb[cb["iso_parent"] != cb["iso_partner"]]
for c in ["n_employees", "unrelated_party_revenues", "tangible_assets_except_cash"]:
    cb[c] = pd.to_numeric(cb[c], errors="coerce")
cb = cb.groupby(["iso_parent", "iso_partner", "year"], as_index=False).sum(min_count=1)
print(f"CbCR target cells: {len(cb)}  by year: {cb.groupby('year').size().to_dict()}")

# %% MARK: 2. CEPII gravity backbone (o=parent, d=partner), year>=2014
GRAV_BI = ["distw_harmonic", "dist", "contig", "comlang_off", "comlang_ethno",
           "comcol", "comrelig", "col45", "comleg_pretrans", "comleg_posttrans",
           "fta_wto", "tradeflow_comtrade_o", "tradeflow_comtrade_d",
           "tradeflow_baci", "tradeflow_imf_o", "tradeflow_imf_d"]
GRAV_UNI = ["gdp_o", "gdp_d", "gdpcap_o", "gdpcap_d", "pop_o", "pop_d",
            "heg_o", "heg_d", "gatt_o", "gatt_d", "wto_o", "wto_d",
            "entry_cost_o", "entry_cost_d", "entry_proc_o", "entry_proc_d"]
usec = ["year", "iso3_o", "iso3_d"] + GRAV_BI + GRAV_UNI
if args.fix_cepii_dedup:
    usec += ["country_exists_o", "country_exists_d"]
g = pd.read_csv(os.path.join(RAW, "Gravity_V202211.csv"), usecols=usec)
g = g[g["year"] >= 2014].rename(columns={"iso3_o": "iso_parent", "iso3_d": "iso_partner"})
if args.fix_cepii_dedup:
    # I keep the entity that exists in that year (the current DEU/IDN/... '.2' rows).
    g["_ex"] = g["country_exists_o"].fillna(0) + g["country_exists_d"].fillna(0)
    g = g.sort_values("_ex", ascending=False, kind="stable")
    g = g.drop(columns=["_ex", "country_exists_o", "country_exists_d"])
g = g.drop_duplicates(["iso_parent", "iso_partner", "year"])
g = g[g["year"] <= LAST_YEAR]
CEPII_LAST = int(g.loc[g["distw_harmonic"].notna(), "year"].max())
print(f"CEPII gravity pairs (>=2014): {len(g)}; last CEPII year with data = {CEPII_LAST}")


def _wb_macro():
    """Returns the World Bank GDP (current US$) and population per (iso3, year) from macro_variables."""
    gdp = pd.read_csv(os.path.join(MACRO, "wb_gdp_current_usd_2026-08.csv"), comment="#")
    gdp = gdp.rename(columns={"gdp_current_usd": "gdp_usd"})[["iso3", "year", "gdp_usd"]]
    wide = pd.read_csv(os.path.join(MACRO, "wb_gdp_population_2026-02.csv"))
    wide = wide[wide["Country Code"].notna() & wide["Series Code"].isin(
        ["SP.POP.TOTL", "NY.GDP.MKTP.CD"])]
    ycols = [c for c in wide.columns if c[:4].isdigit()]
    long = wide.melt(id_vars=["Country Code", "Series Code"], value_vars=ycols,
                     var_name="yc", value_name="v")
    long["year"] = long["yc"].str[:4].astype(int)
    long["v"] = pd.to_numeric(long["v"].replace("..", np.nan), errors="coerce")
    long = long.pivot_table(index=["Country Code", "year"], columns="Series Code",
                            values="v").reset_index()
    long = long.rename(columns={"Country Code": "iso3", "SP.POP.TOTL": "pop_persons",
                                "NY.GDP.MKTP.CD": "gdp_usd_feb"})
    mac = long.merge(gdp, on=["iso3", "year"], how="outer")
    mac["gdp_usd"] = mac["gdp_usd"].fillna(mac["gdp_usd_feb"])   # canonical first
    mac["gdpcap_usd"] = mac["gdp_usd"] / mac["pop_persons"]
    return mac[["iso3", "year", "gdp_usd", "pop_persons", "gdpcap_usd"]]


FILL_YEARS = []
if args.mode == "update":
    FILL_YEARS = [y for y in YEARS if y > CEPII_LAST]
    mac = _wb_macro()
    base = g[g["year"] == CEPII_LAST].copy()
    parts = [g]
    prev = base
    for y in FILL_YEARS:
        b = prev.copy()
        b["year"] = y
        my = mac[mac["year"] == y].set_index("iso3")
        for side, key in [("_o", "iso_parent"), ("_d", "iso_partner")]:
            for cep, wbc in [("gdp", "gdp_usd"), ("pop", "pop_persons"),
                             ("gdpcap", "gdpcap_usd")]:
                new = b[key].map(my[wbc]) / 1e3          # CEPII units: thousands
                b[cep + side] = new.where(new.notna(), b[cep + side])  # otherwise keep the previous year's value
        parts.append(b)
        prev = b
    g = pd.concat(parts, ignore_index=True)
    print(f"CEPII backbone extended {CEPII_LAST} -> {FILL_YEARS} "
          f"({len(base)} pairs per fill year; GDP/pop from WB macro_variables)")

# %% MARK: 3. World Bank unilateral indicators
# Reshaped wide (iso3, year, <ind>) and merged for both sides (o and d).
wb_files = sorted(glob.glob(os.path.join(RAW, "wb_*.csv")))
wb_wide = None
for f in wb_files:
    code = os.path.basename(f)[3:-4]
    d = pd.read_csv(f).rename(columns={"value": f"wb_{code}"})
    d = d[["iso3", "year", f"wb_{code}"]]
    d = d.drop_duplicates(["iso3", "year"])
    wb_wide = d if wb_wide is None else wb_wide.merge(d, on=["iso3", "year"], how="outer")
wb_wide = wb_wide.drop_duplicates(["iso3", "year"])
WB_LAST = int(wb_wide["year"].max())
print(f"WB indicators merged: {wb_wide.shape[1]-2} cols, {len(wb_wide)} rows, last year {WB_LAST}")
if args.mode == "update":
    wb_cols = [c for c in wb_wide.columns if c.startswith("wb_")]
    prev = wb_wide[wb_wide["year"] == WB_LAST].copy()
    add = []
    for y in [y for y in YEARS if y > WB_LAST]:
        b = prev.copy()
        b["year"] = y
        my = mac[mac["year"] == y].set_index("iso3")
        for col, src in [("wb_NY.GDP.MKTP.CD", "gdp_usd"), ("wb_SP.POP.TOTL", "pop_persons"),
                         ("wb_NY.GDP.PCAP.CD", "gdpcap_usd")]:
            new = b["iso3"].map(my[src])
            b[col] = new.where(new.notna(), b[col])
        # countries with a macro value but no WB row in the cache
        extra = my.index.difference(b["iso3"])
        add.append(b)
        prev = b
        print(f"  WB block {y}: {len(b)} countries; GDP/pop/GDPpc from macro_variables, "
              f"other {len(wb_cols) - 3} indicators = {WB_LAST} value "
              f"({len(extra)} macro-only iso3 not in the WB cache, ignored)")
    wb_wide = pd.concat([wb_wide] + add, ignore_index=True)

# %% MARK: 4. WGI: one governance PCA component per (iso3, year)
# I fit the PCA on the raw data (identical in both modes) and carry the scores forward afterwards.
wgi_parts = []
for f in sorted(glob.glob(os.path.join(RAW, "wgi_*.csv"))):
    dim = os.path.basename(f)[4:-4]
    d = pd.read_csv(f)
    cols = {c.lower(): c for c in d.columns}
    iso = cols.get("ref_area") or cols.get("iso3") or list(d.columns)[0]
    d = d.rename(columns={iso: "iso3", "TIME_PERIOD": "year", "OBS_VALUE": dim})
    wgi_parts.append(d[["iso3", "year", dim]])
wgi = wgi_parts[0]
for p in wgi_parts[1:]:
    wgi = wgi.merge(p, on=["iso3", "year"], how="outer")
dims = [c for c in wgi.columns if c not in ("iso3", "year")]
wgi[dims] = wgi[dims].apply(pd.to_numeric, errors="coerce")
complete = wgi.dropna(subset=dims)
pca = PCA(n_components=1).fit(complete[dims])
wgi.loc[complete.index, "governance"] = pca.transform(complete[dims])[:, 0]
wgi = wgi[["iso3", "year", "governance"]].drop_duplicates(["iso3", "year"])
print(f"WGI governance PCA: explained var {pca.explained_variance_ratio_[0]:.2f}")
if args.mode == "update":
    WGI_LAST = int(wgi["year"].max())
    add = []
    for y in [y for y in YEARS if y > WGI_LAST]:
        b = wgi[wgi["year"] == WGI_LAST].copy()
        b["year"] = y
        add.append(b)
    wgi = pd.concat([wgi] + add, ignore_index=True)
    print(f"  WGI carried {WGI_LAST} -> {[y for y in YEARS if y > WGI_LAST]}")


# %% MARK: 5. IMF CDIS FDI and CPIS portfolio positions (bilateral)
# The inward position of REF_AREA from the counterpart.
def _load_bilateral(fname):
    d = pd.read_csv(os.path.join(RAW, fname))
    d["cp_ifs"] = d["COMP_BREAKDOWN_1"].str.extract(r"(\d+)").astype(float)
    d["cp_iso"] = d["cp_ifs"].map(IFS_TO_ISO3)
    n_un = d["cp_iso"].isna().mean()
    d = d.dropna(subset=["cp_iso"])
    d = d.rename(columns={"REF_AREA": "ref_iso", "TIME_PERIOD": "year"})
    d["val"] = pd.to_numeric(d["OBS_VALUE"], errors="coerce")
    d["_abs"] = d["val"].abs()
    d = d.sort_values("_abs").drop_duplicates(["ref_iso", "cp_iso", "year"], keep="last")
    d = d[["ref_iso", "cp_iso", "year", "val"]]
    if args.mode == "update":
        last = int(d["year"].max())
        add = []
        for y in [y for y in YEARS if y > last]:
            b = d[d["year"] == last].copy()
            b["year"] = y
            add.append(b)
        if add:
            print(f"  {fname}: carried {last} -> {[y for y in YEARS if y > last]}")
        d = pd.concat([d] + add, ignore_index=True)
    return d, n_un


cdis, n_un = _load_bilateral("imf_cdis_inward.csv")
print(f"CDIS: {len(cdis)} rows, {n_un:.1%} counterpart codes unmapped")
fdi_od = cdis.rename(columns={"ref_iso": "iso_partner", "cp_iso": "iso_parent",
                              "val": "fdi_origin_to_dest"})
fdi_do = cdis.rename(columns={"ref_iso": "iso_parent", "cp_iso": "iso_partner",
                              "val": "fdi_dest_to_origin"})
cpis, n_unc = _load_bilateral("imf_cpis_assets.csv")
print(f"CPIS: {len(cpis)} rows, {n_unc:.1%} counterpart codes unmapped")
porti_od = cpis.rename(columns={"ref_iso": "iso_partner", "cp_iso": "iso_parent",
                                "val": "porti_origin_to_dest"})
porti_do = cpis.rename(columns={"ref_iso": "iso_parent", "cp_iso": "iso_partner",
                                "val": "porti_dest_to_origin"})
# (BIS banking statistics, downloaded by fetch_bis.py, are not used as features.)

# %% MARK: 6. Assemble
# The backbone is the union of the CEPII pairs and the CbCR cells.
m = g.copy()
for side, key in [("_o", "iso_parent"), ("_d", "iso_partner")]:
    w = wb_wide.rename(columns={"iso3": key, **{c: c + side for c in wb_wide.columns if c.startswith("wb_")}})
    m = m.merge(w, on=[key, "year"], how="left")
    gov = wgi.rename(columns={"iso3": key, "governance": "governance" + side})
    m = m.merge(gov, on=[key, "year"], how="left")
m = m.merge(fdi_od, on=["iso_parent", "iso_partner", "year"], how="left")
m = m.merge(fdi_do, on=["iso_parent", "iso_partner", "year"], how="left")
m = m.merge(porti_od, on=["iso_parent", "iso_partner", "year"], how="left")
m = m.merge(porti_do, on=["iso_parent", "iso_partner", "year"], how="left")
m = m.merge(cb, on=["iso_parent", "iso_partner", "year"], how="outer")

# %% MARK: 6.1 Last-year handling
TARGET_COLS = ["n_employees", "unrelated_party_revenues", "tangible_assets_except_cash"]
if args.mode == "replicate":
    # Replicate mode: I carry the second-to-last year's features into the
    # last year for every pair not already present in it.
    SRC_YEAR, CARRY_TO = YEARS[-2], YEARS[-1]
    _cnt = m.groupby("year").size()
    if _cnt.get(CARRY_TO, 0) < 0.5 * _cnt.get(SRC_YEAR, 1):
        _have = set(map(tuple, m.loc[m["year"] == CARRY_TO,
                                     ["iso_parent", "iso_partner"]].to_numpy()))
        _src = m[m["year"] == SRC_YEAR].copy()
        _src = _src[[t not in _have for t in
                     map(tuple, _src[["iso_parent", "iso_partner"]].to_numpy())]]
        _src["year"] = CARRY_TO
        _src[TARGET_COLS] = np.nan
        m = pd.concat([m, _src], ignore_index=True)
        print(f"Carried {len(_src)} pairs forward {SRC_YEAR}->{CARRY_TO} "
              f"({_cnt.get(CARRY_TO, 0)} -> {int(m.groupby('year').size().get(CARRY_TO))} rows).")
else:
    _cnt = m.groupby("year").size()
    for y in FILL_YEARS:
        assert _cnt.get(y, 0) >= 0.9 * _cnt.get(CEPII_LAST, 1), f"fill year {y} too sparse"
    print(f"Rows per year: {_cnt.to_dict()}")

# %% MARK: 7. Log-transform the skewed level variables (the dummies stay as they are)
LOG_VARS = (["tradeflow_comtrade_o", "tradeflow_comtrade_d", "tradeflow_baci",
             "tradeflow_imf_o", "tradeflow_imf_d", "distw_harmonic", "dist",
             "fdi_origin_to_dest", "fdi_dest_to_origin",
             "porti_origin_to_dest", "porti_dest_to_origin",
             "gdp_o", "gdp_d", "gdpcap_o", "gdpcap_d", "pop_o", "pop_d",
             "entry_cost_o", "entry_cost_d", "n_employees",
             "unrelated_party_revenues", "tangible_assets_except_cash",
             ]
            + [c for c in m.columns if c.startswith("wb_")])
for v in LOG_VARS:
    if v in m.columns:
        m["ln_" + v] = np.log(pd.to_numeric(m[v], errors="coerce").clip(lower=0) + 1)

out = os.path.join(OUT, "gravity_feature_matrix.parquet")
m.to_parquet(out, index=False)
n_train = m["n_employees"].notna().sum()
print(f"\nFeature matrix: {m.shape[0]} rows x {m.shape[1]} cols")
print(f"  rows with CbCR target (training): {n_train}  by year: "
      f"{m[m['n_employees'].notna()].groupby('year').size().to_dict()}")
print(f"  saved -> {out}")
