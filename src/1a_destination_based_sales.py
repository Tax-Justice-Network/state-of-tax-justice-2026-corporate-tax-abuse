# %%
"""
1a — Destination-based sales: the market key and the keys of Japanese and Canadian groups.

This script builds the destination-based measure of multinationals' sales that
replaces the origin-based sales factor in the apportionment formulas. The
origin-based factor consists of the unrelated-party revenues in the
country-by-country reports (CbCR). The script builds two kinds of keys:
  - The market key `mne_plus_dds_share` (formula tag `destmnedds`, the headline
    sales measure). It has one value per market jurisdiction and year, the same
    for every parent.
  - The keys of the variants `mkt_own_jpn` and `mkt_own_can`. They give the
    Japanese or the Canadian groups the sales pattern that their country's
    official statistics show. Every other parent keeps the market key.
Script 2 merges the market key into the disaggregated CbCR dataset after the
disaggregation, because the disaggregation introduces partner jurisdictions
that do not exist after script 1 (destination-based sales are a property of the
market jurisdiction). Script 5 reads the keys of Japanese and Canadian groups
in the variant runs (config.HQ_DEST_KEY_FILES).

Market key (section 3). The destination-based sales of multinationals in a
market are the sum of two legs:
  (i)  the local sales of multinational enterprise (MNE) entities across all
       sectors, that is the turnover minus exports of foreign-owned (F) and
       domestic-owned MNE (D_MNE) entities, from the OECD Analytical Activity of
       Multinational Enterprises database (AAMNE), and
  (ii) the MNE share of the market's imports of digitally deliverable services
       from the OECD-WTO Balanced Trade in Services data (BaTIS), with the
       category set of the IMF-OECD-UNCTAD-WTO Handbook but without SH, the
       charges for the use of intellectual property. These are services
       consumed in the market but supplied remotely, which never appear as
       local turnover.
The local-sales proxy (turnover minus exports) follows OECD (2020, "Tax
Challenges Arising from Digitalisation — Economic Impact Assessment", chapter
2). I deviate in one respect. The OECD restricts the proxy to consumer-facing
sectors (the scope of its Pillar One), whereas the market key keeps all
sectors, including finance, mining and business-to-business services, because
it replaces the CbCR unrelated-party revenues, which cover all sectors.

Coverage. I extrapolate the markets that a source does not observe by
regression (log GDP, log GDP per capita, log trade openness), with an
adjustment for remittances and aid. The 2026 AAMNE edition covers 2008-2023.
Country-years after 2020 that it misses reuse the country's own 2019 ratio,
because 2020 is distorted by COVID. Markets with a population below 250,000 and
no data are set to 0. A coverage check guarantees that every real CbCR
partner-year carries the market key and that the shares sum to 1 per year.

Extrapolation test (section 4). The methodology note reports how well the
regression of the local-sales ratio fits and whether the number of large
multinational groups present in a market (Orbis) would improve it. I fit both
versions and write their fit, their leave-one-country-out error and the 2023
predictions for the markets outside AAMNE.

Keys of Japanese and Canadian groups (section 5), in four steps:
  5.1 The unaffiliated share of US multinationals' cross-border sales, from the
      survey of US multinationals by the US Bureau of Economic Analysis (BEA).
      It is the only source that splits exports into sales to affiliates and
      to unaffiliated customers, so it nets the intra-group part out of the
      modelled exports of every headquarters country.
  5.2 The modelled key of the headquarters country p in the AAMNE
      owner-by-host layer is the sum of p's groups' local sales in market j
      (the MNE local sales of j times p's share of j's MNE output) and their
      exports to j. The exports are those of p-owned firms by destination, from
      BACI goods trade and BaTIS services trade without IP charges, net of the
      intra-group part.
  5.3 Official statistics replace the modelled home share and the
      distribution of foreign sales: the Basic Survey of Overseas Business
      Activities of Japan's Ministry of Economy, Trade and Industry (METI) and
      the tables of Statistics Canada.
  5.4 The Japan-only and Canada-only keys keep the rows of one country. They give the footnote on Japan and
      Canada in the methodology note (src/8_chapter_figures.py).

Section outline (numbers match the cell headings below):
1. Setup.
2. Shared inputs.
   2.1 GDP and population.
   2.2 Trade openness, remittances and aid.
   2.3 Multinationals' output and exports (AAMNE).
3. Market key.
   3.1 MNE local sales.
   3.2 Digitally deliverable services.
   3.3 The market key: coverage checks and save.
4. Extrapolation test.
5. Keys of Japanese and Canadian groups from their own statistics.
   5.1 Unaffiliated share of cross-border sales (BEA).
   5.2 Modelled headquarters key.
   5.3 Official statistics: METI and Statistics Canada.
   5.4 Save the Japan-only and Canada-only keys.

Pipeline step 1a — after 1 (clean), before 2 (disaggregate).

Reads:
  {data_final}/cbcr_main_allsubgroupsonly.csv                — cleaned CbCR panel: GDP and population (script 1)
  {data_raw}macro_variables/wb_gdp_current_usd_2026-08.csv    — canonical World Bank GDP snapshot (fallback fill)
  {data_raw}macro_variables/wb_gdp_population_2026-02.csv     — World Bank GDP and population (DataBank export,
                                                                last-resort backfill)
  {data_raw}macro_variables/wb_trade_pct_gdp_2026-06.csv      — World Bank trade openness (regression covariate)
  {data_raw}macro_variables/wb_remittances_received_2026-06.csv — World Bank remittances received (coverage
                                                                adjustment)
  {data_raw}context/wb_oda_received_2026-06.csv               — World Bank official development assistance (ODA)
                                                                received (coverage adjustment)
  {data_raw}destination_based_sales/oecd_wto_batis_bpm6_2025-12_extract_dds_imports.csv.gz
                                                              — BaTIS extract: digitally deliverable imports
  {data_raw}destination_based_sales/oecd_aamne_mne_xvem_2026-07.csv — OECD Analytical AMNE output and exports by
                                                                ownership (F / D_MNE / D_OTH)
  {data_intermediate}/extractive/cbcr_universe_presence.csv   — Orbis groups by headquarters country and market
                                                                (extrapolation test)
  {data_raw}destination_based_sales/bea_us_mne/usdia<year>{r,p}_Part{I,II_E}*.xls — BEA Tables I.O 1 (U.S.
                                                                parents' sales by destination) and II.E 2
                                                                (affiliates' sales by destination)
  {data_raw}destination_based_sales/oecd_aamne_bilateral_output_2026-07.csv — AAMNE gross output by host and owner
                                                                country
  {data_intermediate}/bilateral_{goods,services}_trade.csv    — trade matrices (shipped, built when missing from
                                                                the three downloads below, which are not shipped)
  {data_raw}destination_based_sales/baci/BACI_HS17_V202501.zip — CEPII BACI goods trade, 2017–2023
  {data_raw}gravity/Gravity_V202211.csv                       — CEPII Gravity (BACI goods trade, 2016)
  {data_raw}destination_based_sales/oecd_wto_batis_data_bpm6/OECD-WTO_BATIS_BPM6_December2025_bulk.csv
                                                              — BaTIS bulk file (bilateral services trade)
  {data_raw}destination_based_sales/home_share_sources/…      — METI and Statistics Canada tables (manifest.csv)
Writes:
  {data_intermediate}/destination_based_sales.csv             — per (iso_partner, year): the market key
                                                                mne_plus_dds_share and its legs
  {data_intermediate}/destination_key_extrapolation_test.csv  — fit of the local-sales regression with and without
                                                                the Orbis groups (section 4)
  {data_intermediate}/destination_key_extrapolation_predictions.csv — predictions of both regressions for the
                                                                markets outside AAMNE, latest year (section 4)
  {data_intermediate}/destination_based_sales_mkt_own_jpn.csv — key of Japanese groups: (iso_parent, iso_partner,
                                                                year) hq_dest_key, source, home_share_used
  {data_intermediate}/destination_based_sales_mkt_own_can.csv — the same, Canadian groups
  {data_intermediate}/bilateral_{goods,services}_trade.csv    — trade matrices, when built
Usage:
  python src/1a_destination_based_sales.py                       — all keys

Author: Tax Justice Network (based on the method of García-Bernardo and Janský).
Created: 2026-07-17.  Last updated: 2026-11-22.
"""

# %% MARK: 1. Setup
import io
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pycountry

from config import *

analysis_years = list(range(first_year, first_year + n_years))
# Years after 2020. Where the AAMNE source lacks a country-year in these years,
# I reuse the country's own 2019 ratio instead of the regression extrapolation,
# because 2020 is distorted by COVID. The list follows from the analysis window,
# so extending config.n_years needs no edit here.
POST_COVID_YEARS = [y for y in analysis_years if y > 2020]
year_str = [str(y) for y in analysis_years]
formatted_years = [f"{y} [YR{y}]" for y in analysis_years]
OUT_DIR = Path(data_intermediate)


def _via_csv(df):
    """Return `df` as stored in a CSV file and read back with pandas' default parser.

    In section 5, I read each table that I save back from its file, and I pass
    the other tables on in this form, because the parser can change the last
    binary digit of a value. Every step thus works on the numbers as stored.
    """
    return pd.read_csv(io.StringIO(df.to_csv(index=False)))


def _nearest_year(years, y):
    """Return the year in `years` that is closest to y (the later one on a tie)."""
    return min(years, key=lambda h: (abs(h - y), -h))


# %% MARK: 2. Shared inputs
# This section reads the macro frame per market and year (GDP, population,
# trade openness, remittances, aid) and the AAMNE file of multinationals'
# output and exports.

# %% MARK: 2.1 GDP and population
# I take GDP and population from the filled output of script 1, which carries
# the manual fills for havens and territories that the raw World Bank file
# misses.
g1 = pd.read_csv(
    f"{data_final}/cbcr_main_allsubgroupsonly.csv",
    usecols=["iso_partner", "year", "gdp_current_usd", "population"],
)
g1 = g1.drop_duplicates(["iso_partner", "year"])
macro = g1.rename(columns={"iso_partner": "iso", "gdp_current_usd": "gdp"})
macro["gdp"] = pd.to_numeric(macro["gdp"], errors="coerce")
macro["population"] = pd.to_numeric(macro["population"], errors="coerce")

# Full grid of countries and years. The output must cover every partner in
# every analysis year. A table built only from observed partner-years would
# drop markets from the years in which they do not appear in the reporting
# sample. That would leave NaN in those cells, and with them the activity of
# the whole row, in every destination formula downstream.
_grid = pd.MultiIndex.from_product(
    [sorted(macro["iso"].unique()), analysis_years], names=["iso", "year"]
).to_frame(index=False)
macro = _grid.merge(macro, on=["iso", "year"], how="left")

# I apply the GDP snapshot first (config.canonical_gdp_data, the snapshot of
# the World Bank's World Development Indicators that the whole repository
# uses). It fills any grid cell that script 1 left NaN and covers countries that
# the DataBank export misses entirely (BHS). It runs before the DataBank
# backfill so that an older DataBank GDP (from before the rebasing of Nigeria,
# Angola and others) never wins over the newer snapshot.
_canon = pd.read_csv(canonical_gdp_data, comment="#").rename(
    columns={"iso3": "iso", "gdp_current_usd": "_gdp_canon"}
)
macro = macro.merge(_canon, on=["iso", "year"], how="left")
macro["gdp"] = macro["gdp"].where(macro["gdp"].notna(), macro["_gdp_canon"])
macro = macro.drop(columns=["_gdp_canon"])

# Last-resort backfill from the older World Bank DataBank file. It mainly
# supplies population, because the snapshot file holds only GDP, and supplies
# GDP only for cells that neither script 1 nor the snapshot covers. The left
# merge can only fill years for countries already on the grid. Continent and
# rest-of-world aggregate codes have no GDP here and stay missing, because they
# carry no destination sales.
wb_raw = pd.read_csv(gdp_population_data)
wb_raw = wb_raw.dropna(subset=["Country Code"])
wb_raw = wb_raw[["Series Name", "Country Code"] + formatted_years]
wb_long = wb_raw.melt(
    id_vars=["Series Name", "Country Code"], var_name="year_col", value_name="value"
)
wb_long["year"] = wb_long["year_col"].str[:4].astype(int)
wb_long["value"] = pd.to_numeric(
    wb_long["value"].replace("..", np.nan), errors="coerce"
)
wb_wide = wb_long.pivot_table(
    index=["Country Code", "year"], columns="Series Name", values="value"
).reset_index()
wb_wide = wb_wide.rename(
    columns={
        "Country Code": "iso",
        "GDP (current US$)": "gdp_wb",
        "Population total": "pop_wb",
    }
)
macro = macro.merge(
    wb_wide[["iso", "year", "gdp_wb", "pop_wb"]], on=["iso", "year"], how="left"
)
macro["gdp"] = macro["gdp"].where(macro["gdp"].notna(), macro["gdp_wb"])
macro["population"] = macro["population"].where(
    macro["population"].notna(), macro["pop_wb"]
)
macro = macro.drop(columns=["gdp_wb", "pop_wb"])

# For grid years that no source covers, I fill within each country. GDP and
# population move slowly, and a gap of one year must not knock a market out of
# the key in that year.
macro = macro.sort_values(["iso", "year"]).reset_index(drop=True)
for _c in ("gdp", "population"):
    macro[_c] = macro.groupby("iso")[_c].transform(lambda s: s.ffill().bfill())

# %% MARK: 2.2 Trade openness, remittances and aid
# Trade openness (World Bank API file "API_*.csv"). The first 4 rows hold
# metadata, and the year columns are plain strings like "2016".
trade_raw = pd.read_csv(trade_openness_data, skiprows=4)
trade_raw = trade_raw[["Country Code"] + year_str]
trade_long = trade_raw.melt(
    id_vars="Country Code", var_name="year", value_name="trade_openness"
)
trade_long["year"] = trade_long["year"].astype(int)
trade_long = trade_long.rename(columns={"Country Code": "iso"})
macro = macro.merge(trade_long, on=["iso", "year"], how="left")

# Personal remittances received (World Bank API file, current US$).
remit_raw = pd.read_csv(remittances_data, skiprows=4)
remit_raw = remit_raw[["Country Code"] + year_str]
remit_long = remit_raw.melt(
    id_vars="Country Code", var_name="year", value_name="remittances"
)
remit_long["year"] = remit_long["year"].astype(int)
remit_long = remit_long.rename(columns={"Country Code": "iso"})
macro = macro.merge(remit_long, on=["iso", "year"], how="left")

# Net official development assistance (ODA) received (World Bank DataBank
# export, current US$). The file is wide, with year columns like
# "2016 [YR2016]" and ".." as the marker for missing values.
oda_raw = pd.read_csv(oda_data)
oda_raw = oda_raw.dropna(subset=["Country Code"])
oda_raw = oda_raw[["Country Code"] + formatted_years]
oda_long = oda_raw.melt(id_vars="Country Code", var_name="year_col", value_name="oda")
oda_long["year"] = oda_long["year_col"].str[:4].astype(int)
oda_long["oda"] = pd.to_numeric(oda_long["oda"].replace("..", np.nan), errors="coerce")
oda_long = oda_long[["Country Code", "year", "oda"]].rename(
    columns={"Country Code": "iso"}
)
macro = macro.merge(oda_long, on=["iso", "year"], how="left")

# GDP per capita and the log covariates of every extrapolation regression.
macro["gdp_per_capita"] = macro["gdp"] / macro["population"]
macro["ln_gdp"] = np.log(macro["gdp"].where(macro["gdp"] > 0))
macro["ln_gdp_pc"] = np.log(macro["gdp_per_capita"].where(macro["gdp_per_capita"] > 0))
macro["ln_trade"] = np.log(macro["trade_openness"].where(macro["trade_openness"] > 0))

# Adjustment for remittances and aid (OECD paragraph 98). Consumption in a
# market is financed by GDP plus remittances plus aid. I apply the adjustment
# to extrapolated ratios only. Missing remittances and aid count as zero.
macro["remittances"] = macro["remittances"].fillna(0)
macro["oda"] = macro["oda"].fillna(0)
macro["aid_adjustment"] = (macro["gdp"] + macro["remittances"] + macro["oda"]) / macro[
    "gdp"
]

# %% MARK: 2.3 Multinationals' output and exports (AAMNE)
# OECD Analytical AMNE, 2026 edition. It gives gross output (GO) and gross
# exports (EXGR) by host country, industry and ownership: foreign-owned (F),
# domestic-owned multinationals (D_MNE) and other domestic firms (D_OTH). The
# values are in million USD for 2008-2023.
if not Path(aamne_dmne_data).exists():
    raise FileNotFoundError(
        f"AAMNE MNE file not found: {aamne_dmne_data} (OECD Analytical AMNE, "
        "http://oe.cd/gvc-mne)."
    )
aamne_mne = pd.read_csv(aamne_dmne_data)

# %% MARK: 3. Market key
# The market key adds the all-sector MNE local sales (3.1) and the MNE share of
# the imports of digitally deliverable services without IP charges (3.2) and
# turns the sum into shares per year (3.3). It is the sales measure of the
# headline formula (sales_employees_destmnedds).

# %% MARK: 3.1 MNE local sales
# Turnover minus exports of F and D_MNE entities over all sections of the
# International Standard Industrial Classification (ISIC) in AAMNE, including
# finance (K64T66), mining and business-to-business services. This matches the
# scope of the CbCR unrelated-party revenues that the key replaces in the
# apportionment formulas. The OECD restricts the proxy to consumer-facing
# sectors.
a2 = aamne_mne[aamne_mne["year"].isin(analysis_years)]
a2 = a2[a2["cou"] != "ROW"]
a2 = a2[a2["own"].isin(["F", "D_MNE"])]
a2["GO"] = pd.to_numeric(a2["GO"], errors="coerce")
a2["EXGR"] = pd.to_numeric(a2["EXGR"], errors="coerce")
a2["db_sales"] = a2["GO"] - a2["EXGR"]
mne_wide = a2.groupby(["cou", "year"], as_index=False)["db_sales"].sum()
mne_wide = mne_wide.rename(columns={"db_sales": "mne_sales_musd"})

mne_wide["mne_sales_aamne"] = mne_wide["mne_sales_musd"] * 1e6
mne_aamne = mne_wide[["cou", "year", "mne_sales_aamne"]].rename(columns={"cou": "iso"})
print(f"AAMNE MNE local sales for {mne_aamne['iso'].nunique()} jurisdictions, "
      f"years {mne_aamne['year'].min()}-{mne_aamne['year'].max()}.")
macro = macro.merge(mne_aamne, on=["iso", "year"], how="left")
macro["mne_ratio_actual"] = macro["mne_sales_aamne"] / macro["gdp"]

# Extrapolation regressions of the observed ratio of MNE sales to GDP on log
# GDP, log GDP per capita and log trade openness. The reduced regression
# without trade openness serves markets that have no trade data.
mreg = macro[
    (macro["mne_ratio_actual"] > 0)
    & (macro["gdp"] > 0)
    & (macro["gdp_per_capita"] > 0)
    & (macro["trade_openness"] > 0)
].copy()
Xm = np.column_stack(
    [np.ones(len(mreg)), np.log(mreg["gdp"]), np.log(mreg["gdp_per_capita"]),
     np.log(mreg["trade_openness"])]
)
mbeta, _, _, _ = np.linalg.lstsq(Xm, np.log(mreg["mne_ratio_actual"]).values, rcond=None)
print(f"\nAll-sector MNE ratio regression: N = {len(mreg)} jurisdiction-years")
print(f"  constant / log GDP / log GDP p.c. / log trade: "
      f"{mbeta[0]:.4f} / {mbeta[1]:.4f} / {mbeta[2]:.4f} / {mbeta[3]:.4f}")

mreg2 = macro[
    (macro["mne_ratio_actual"] > 0) & (macro["gdp"] > 0) & (macro["gdp_per_capita"] > 0)
].copy()
Xm2 = np.column_stack(
    [np.ones(len(mreg2)), np.log(mreg2["gdp"]), np.log(mreg2["gdp_per_capita"])]
)
mbeta2, _, _, _ = np.linalg.lstsq(
    Xm2, np.log(mreg2["mne_ratio_actual"]).values, rcond=None
)

macro["mne_ratio_pred_full"] = np.exp(
    mbeta[0] + mbeta[1] * macro["ln_gdp"] + mbeta[2] * macro["ln_gdp_pc"]
    + mbeta[3] * macro["ln_trade"]
)
macro["mne_ratio_pred_reduced"] = np.exp(
    mbeta2[0] + mbeta2[1] * macro["ln_gdp"] + mbeta2[2] * macro["ln_gdp_pc"]
)
macro["mne_ratio_pred"] = macro["mne_ratio_pred_full"].where(
    macro["mne_ratio_pred_full"].notna(), macro["mne_ratio_pred_reduced"]
)
# The scaling for remittances and aid (2.2) applies to extrapolated ratios only.
macro["mne_ratio_pred_adj"] = macro["mne_ratio_pred"] * macro["aid_adjustment"]

# Final ratio, USD level, rule for tiny markets and share per year. I use the
# observed AAMNE ratio wherever it exists. For country-years after 2020 that
# the file misses, the country's own 2019 ratio replaces the regression
# extrapolation, because 2020 is distorted by COVID. A market that is still
# missing after the extrapolation and has almost no population gets 0. This
# never overrides a real estimate.
macro["mne_is_imputed"] = macro["mne_ratio_actual"].isna().astype(int)
macro["mne_ratio_final"] = macro["mne_ratio_actual"].where(
    macro["mne_ratio_actual"].notna(), macro["mne_ratio_pred_adj"]
)
mne_ratio_2019 = macro.loc[macro["year"] == 2019, ["iso", "mne_ratio_actual"]].dropna()
mne_ratio_2019 = dict(zip(mne_ratio_2019["iso"], mne_ratio_2019["mne_ratio_actual"]))
for yr in POST_COVID_YEARS:
    mask = (
        (macro["year"] == yr)
        & (macro["iso"].isin(mne_ratio_2019))
        & macro["mne_ratio_actual"].isna()
    )
    macro.loc[mask, "mne_ratio_final"] = macro.loc[mask, "iso"].map(mne_ratio_2019)
    macro.loc[mask, "mne_is_imputed"] = 1
macro["mne_sales"] = macro["mne_ratio_final"] * macro["gdp"]
tiny_m = (macro["mne_sales"].isna()) & (macro["population"] < 250_000)
macro.loc[tiny_m, "mne_sales"] = 0.0
macro.loc[tiny_m, "mne_is_imputed"] = 1

# %% MARK: 3.2 Digitally deliverable services
# Imports of digitally deliverable services (BaTIS) and their MNE share. The
# WTO "digitally delivered" series is not clearly defined. It lies between the
# broad "digitally deliverable" of the IMF-OECD-UNCTAD-WTO Handbook
# (deliverable using information and communication technology) and the narrow
# automated digital services (produced and delivered digitally). Following the
# G24 publication "Options for a Protocol on Services under the UNFCITC", I
# build the deliverable aggregate directly and transparently from the BaTIS
# categories of the Extended Balance of Payments Services classification
# (EBOPS). The Handbook category set (EBOPS 2010) is SF insurance and pension,
# SG financial services, SH charges for IP, SI telecommunications, computer and
# information services (the aggregate, because its sub-items SI1-SI3 would
# count twice), SJ other business services and SK1 audiovisual and related
# services (the digitally deliverable part of SK). I leave out SH, the charges
# for the use of IP. It is about 15% of the aggregate and largely intra-group
# royalty payments from affiliates to parents, which are at odds with the
# concept of unrelated-party sales that the destination factor replaces.


def _load_batis_dds_imports(path):
    """Read the BaTIS BPM6 file into (iso, year, dds_imports_exip_usd).

    Layout (December 2025 edition): Reporter and Partner as ISO2 codes with the
    flags type_Reporter and type_Partner ("c" = country), Flow (M/X), Item_code
    (EBOPS 2010), Year, and the reported, final and balanced values in million
    USD. The balanced value is the reconciled export/import series (see the
    notes of the codes workbook). I use it here, with Final_value as the
    fallback row by row. I keep imports (M) only and country reporters and
    country partners only (no region aggregates), sum over partners and
    restrict the items to the digitally deliverable set of the Handbook without
    SH: SF, SG, SI (the aggregate, so without SI1-3), SJ and SK1. I read the
    file in chunks, because the full bulk file is about 2.8 GB.
    """
    use = ["SF", "SG", "SI", "SJ", "SK1"]
    usecols = ["Reporter", "type_Reporter", "Partner", "type_Partner", "Flow",
               "Item_code", "Year", "Final_value", "Balanced_value"]
    parts = []
    for chunk in pd.read_csv(path, usecols=usecols, chunksize=3_000_000):
        c = chunk[
            (chunk["Flow"] == "M")
            & (chunk["Year"].isin(analysis_years))
            & (chunk["Item_code"].isin(use))
            & (chunk["type_Reporter"] == "c")
            & (chunk["type_Partner"] == "c")
        ]
        if c.empty:
            continue
        v = pd.to_numeric(c["Balanced_value"], errors="coerce").fillna(
            pd.to_numeric(c["Final_value"], errors="coerce")
        )
        parts.append(pd.DataFrame({"iso2": c["Reporter"], "year": c["Year"],
                                   "item": c["Item_code"], "v": v}))
    if not parts:
        raise ValueError(f"BaTIS: no matching rows found in {path} — check layout.")
    b = pd.concat(parts, ignore_index=True)
    b = b.groupby(["iso2", "year", "item"], as_index=False)["v"].sum()
    iso_map = {}
    for code in b["iso2"].dropna().unique():
        cc = pycountry.countries.get(alpha_2=str(code))
        if cc is not None:
            iso_map[code] = cc.alpha_3
    b["iso"] = b["iso2"].map(iso_map)
    _dropped = b.loc[b["iso"].isna(), "iso2"].unique()
    b = b.dropna(subset=["iso"])
    out = (b.groupby(["iso", "year"])["v"].sum() * 1e6).rename("dds_imports_exip_usd").reset_index()
    print(f"  BaTIS: {out['iso'].nunique()} reporter countries, categories {use}, balanced value "
          f"(Final fallback); unmapped ISO2 dropped: {list(_dropped)}.")
    return out


# The market key is defined on the BaTIS deliverable aggregate, so the file is required.
if not Path(batis_data).exists():
    raise FileNotFoundError(
        f"BaTIS file not found: {batis_data}. The market key requires the BaTIS "
        "digitally deliverable imports (download source: the batis_data entry in src/config.py)."
    )
macro = macro.merge(_load_batis_dds_imports(batis_data), on=["iso", "year"], how="left")

# I extrapolate the aggregate on log GDP so that its coverage matches the MNE
# local sales.
d3 = macro[(macro["dds_imports_exip_usd"] > 0) & (macro["gdp"] > 0)].copy()
db3 = np.linalg.lstsq(
    np.column_stack([np.ones(len(d3)), np.log(d3["gdp"])]),
    np.log(d3["dds_imports_exip_usd"]).values, rcond=None,
)[0]
macro["dds_exip_pred"] = np.exp(db3[0] + db3[1] * macro["ln_gdp"])
macro["dds_exip_filled"] = macro["dds_imports_exip_usd"].where(
    macro["dds_imports_exip_usd"].notna(), macro["dds_exip_pred"]
)
macro["dds_exip0"] = macro["dds_exip_filled"].fillna(0)

# MNE share of the exports of the digitally deliverable sectors (AAMNE). The
# BaTIS imports are trade flows of all suppliers, but the key replaces an MNE
# sales variable, so only the part that MNEs supply belongs in it. The share is
# the EXGR of F and D_MNE entities divided by the EXGR of all firms, over the
# ISIC sectors that produce the Handbook categories: K64T66 for SF and SG,
# J58T60, J61 and J62T63 for SI, M69T75 and N77T82 for SJ, and R90T93 for SK1.
# I compute it per year (about 53-58%, stable) and roll the last AAMNE year
# forward to later analysis years.
DDS_MNE_ISIC = ["J58T60", "J61", "J62T63", "K64T66", "M69T75", "N77T82", "R90T93"]
_am = aamne_mne[aamne_mne["isic"].isin(DDS_MNE_ISIC)]
_ms = (_am[_am["own"].isin(["F", "D_MNE"])].groupby("year")["EXGR"].sum()
       / _am.groupby("year")["EXGR"].sum())
mne_dds_share = {int(y): float(v) for y, v in _ms.items()}
_last_cov = max(mne_dds_share)
for _y in analysis_years:
    if _y not in mne_dds_share:
        mne_dds_share[_y] = mne_dds_share[_last_cov]
print("\nMNE (F + D_MNE) share of digitally deliverable-sector exports (AAMNE), %:")
print("  " + ", ".join(f"{y}: {mne_dds_share[y] * 100:.1f}"
                       for y in sorted(analysis_years)))
macro["dds_exip_mne"] = macro["dds_exip0"] * macro["year"].map(mne_dds_share)

# %% MARK: 3.3 The market key: coverage checks and save
# The market key is the all-sector MNE local sales plus the MNE share of the
# digitally deliverable imports without SH, turned into shares per year. The
# two legs do not overlap, because one is local turnover and the other is
# cross-border imports. The key covers paid automated digital services (they
# are inside the BaTIS deliverable imports), not the free, ad-funded ones,
# which have no trade counterpart.
macro["mne_plus_dds_value"] = macro["mne_sales"] + macro["dds_exip_mne"]
macro["mne_plus_dds_share"] = macro["mne_plus_dds_value"] / macro.groupby("year")[
    "mne_plus_dds_value"
].transform("sum")

# Weight of the digital leg in the market key.
_v2 = macro[macro["mne_plus_dds_value"].notna()]
_w2 = (_v2.groupby("year")["dds_exip_mne"].sum()
       / _v2.groupby("year")["mne_plus_dds_value"].sum() * 100).round(1)
print("\nWeight of the digital leg (deliverable imports / [all-MNE + imports]) by year, %:")
print(_w2.to_string())

# The table has one row per market jurisdiction and year, and script 2 merges
# the key into the disaggregated CbCR dataset. It holds the key and its legs:
# the MNE local sales (and whether they are extrapolated), the BaTIS imports as
# observed, their MNE part after the extrapolation, and the sum. Section 5
# reads the local sales back from the file.
cols = [
    "iso",
    "year",
    "mne_sales",
    "mne_is_imputed",
    "dds_imports_exip_usd",
    "dds_exip_mne",
    "mne_plus_dds_value",
    "mne_plus_dds_share",
]
dest_sales = macro[cols].copy()
dest_sales = dest_sales.rename(columns={"iso": "iso_partner"})
dest_sales = dest_sales[dest_sales["mne_sales"].notna()]
dest_sales = dest_sales.sort_values(["iso_partner", "year"]).reset_index(drop=True)

# Every real CbCR partner must carry the market key in every analysis year. A
# NaN here would exclude the whole market from every estimate with a
# destination formula in script 5 (a missing share for BHS, for example, would
# drop about $30bn of booked profit). A jurisdiction enters the exception set
# only with a documented reason.
_real_isos = sorted(set(g1["iso_partner"].unique()) - set(non_countries))
_coverage_exceptions = set()  # none at present
_expected = pd.MultiIndex.from_product(
    [[i for i in _real_isos if i not in _coverage_exceptions], analysis_years],
    names=["iso_partner", "year"],
).to_frame(index=False)
_have = _expected.merge(
    dest_sales[["iso_partner", "year", "mne_plus_dds_share"]],
    on=["iso_partner", "year"],
    how="left",
)
_gaps = _have[_have["mne_plus_dds_share"].isna()]
if not _gaps.empty:
    _gap_isos = _gaps.groupby("iso_partner")["year"].apply(list).to_dict()
    raise AssertionError(
        f"Headline destination share (mne_plus_dds_share) missing for "
        f"{len(_gaps)} real partner-years: {_gap_isos}"
    )

# The key must sum to 1 per year (within tolerance).
_sums = dest_sales.groupby("year")["mne_plus_dds_share"].sum()
_bad = _sums[(_sums - 1.0).abs() > 1e-6]
if not _bad.empty:
    raise AssertionError(f"mne_plus_dds_share does not sum to 1 in years: {_bad.to_dict()}")
print("Coverage checks passed: all real partner-years carry the key; it sums to 1.")

dest_sales.to_csv(OUT_DIR / "destination_based_sales.csv", index=False)
print(f"\nWrote {len(dest_sales):,} rows to {OUT_DIR / 'destination_based_sales.csv'}")

# %% MARK: 4. Extrapolation test
# The regression of 3.1 extrapolates the local-sales ratio of the markets that
# AAMNE does not cover. Sanctions and the presence of foreign groups are not in
# it. I test whether the number of large multinational groups present in a
# market improves it: the foreign groups above the CbCR threshold with a
# subsidiary in the market (cbcr_universe_presence.csv, counts from Orbis), per
# US$ billion of GDP, in logs (plus one group, so that a market without groups
# stays defined). The count is the same in every year.
# I fit the current regression and the regression with the Orbis variable on
# two samples:
#   "regression"            the observations of the regression in 3.1 (observed
#                           AAMNE ratio, GDP, GDP per capita and trade openness
#                           available),
#   "excluding_tax_havens"  the observed AAMNE country-years without the tax
#                           havens of config.TAX_HAVENS_REPRESENTATION, where
#                           the ratio of local sales to GDP reflects booking
#                           structures more than the size of the market, with
#                           the latest trade openness carried forward within a
#                           country.
# For each fit, I report the R-squared, the leave-one-country-out error (the
# root mean squared error of the log ratio when the country's years are
# predicted by the regression fitted without them) and the coefficients. For
# the markets outside AAMNE, I give the ratio of local sales to GDP that the
# key uses in the latest year and the ratios that both regressions predict
# (with trade openness carried forward and without the adjustment for
# remittances and aid). The test changes no number of the key.
PRESENCE_FILE = Path(data_intermediate) / "extractive" / "cbcr_universe_presence.csv"
_pres = pd.read_csv(PRESENCE_FILE)
orbis_groups = (_pres[_pres["hq_iso3"] != _pres["market_iso3"]]
                .groupby("market_iso3")["n_groups"].sum())

# Trade openness carried forward within each country over every year of the file.
_tr = pd.read_csv(trade_openness_data, skiprows=4)
_tr = _tr.melt(id_vars="Country Code", value_vars=[c for c in _tr.columns if c.isdigit()],
               var_name="year", value_name="trade_carried")
_tr["year"] = _tr["year"].astype(int)
_tr = _tr.sort_values(["Country Code", "year"]).rename(columns={"Country Code": "iso"})
_tr["trade_carried"] = _tr.groupby("iso")["trade_carried"].ffill()

ex = macro[["iso", "year", "gdp", "gdp_per_capita", "trade_openness", "mne_ratio_actual", "mne_sales"]].merge(
    _tr, on=["iso", "year"], how="left")
ex["orbis_groups"] = ex["iso"].map(orbis_groups)
ex["ln_gdp"] = np.log(ex["gdp"].where(ex["gdp"] > 0))
ex["ln_gdp_pc"] = np.log(ex["gdp_per_capita"].where(ex["gdp_per_capita"] > 0))
ex["ln_trade_observed"] = np.log(ex["trade_openness"].where(ex["trade_openness"] > 0))
ex["ln_trade_carried"] = np.log(ex["trade_carried"].where(ex["trade_carried"] > 0))
ex["ln_orbis"] = np.log((ex["orbis_groups"].fillna(0) + 1) / (ex["gdp"] / 1e9))
ex["ln_ratio"] = np.log(ex["mne_ratio_actual"].where(ex["mne_ratio_actual"] > 0))
ex["tax_haven"] = ex["iso"].isin(TAX_HAVENS_REPRESENTATION)

EXTRAP_MODELS = {"current": ["ln_gdp", "ln_gdp_pc", "ln_trade"],
                 "with_orbis_groups": ["ln_gdp", "ln_gdp_pc", "ln_trade", "ln_orbis"]}
_in_regression = ((ex["mne_ratio_actual"] > 0) & (ex["gdp"] > 0) & (ex["gdp_per_capita"] > 0)
                  & (ex["trade_openness"] > 0))
EXTRAP_SAMPLES = {
    "regression": ex[_in_regression].assign(ln_trade=lambda d: d["ln_trade_observed"]),
    "excluding_tax_havens": (ex[ex["ln_ratio"].notna() & (ex["gdp"] > 0) & ~ex["tax_haven"]]
                             .assign(ln_trade=lambda d: d["ln_trade_carried"])
                             .dropna(subset=["ln_gdp", "ln_gdp_pc", "ln_trade"])),
}


def _fit(d, xs):
    """Return the least-squares coefficients of ln_ratio on a constant and the columns xs."""
    X = np.column_stack([np.ones(len(d))] + [d[c] for c in xs])
    return np.linalg.lstsq(X, d["ln_ratio"].values, rcond=None)[0]


def _predict(coef, d, xs):
    """Return the predicted log ratio for the rows of d."""
    return coef[0] + sum(coef[i + 1] * d[c] for i, c in enumerate(xs))


fits, coefs = [], {}
for sample, d in EXTRAP_SAMPLES.items():
    for model, xs in EXTRAP_MODELS.items():
        coef = _fit(d, xs)
        coefs[(sample, model)] = coef
        resid = d["ln_ratio"] - _predict(coef, d, xs)
        r2 = 1 - (resid ** 2).sum() / ((d["ln_ratio"] - d["ln_ratio"].mean()) ** 2).sum()
        loco = [((g["ln_ratio"] - _predict(_fit(d[d["iso"] != iso], xs), g, xs)) ** 2).mean()
                for iso, g in d.groupby("iso")]
        row = dict(sample=sample, model=model, n_obs=len(d), n_countries=d["iso"].nunique(), r2=r2,
                   loco_rmse_log=float(np.sqrt(np.mean(loco))))
        row.update({f"coef_{c}": v for c, v in zip(["constant"] + xs, coef)})
        fits.append(row)
fits = pd.DataFrame(fits)
fits.to_csv(OUT_DIR / "destination_key_extrapolation_test.csv", index=False)
print("\nExtrapolation test of the local-sales regression:")
print(fits[["sample", "model", "n_obs", "n_countries", "r2", "loco_rmse_log"]].round(4).to_string(index=False))

# Predictions of the latest year for the markets outside AAMNE.
_aamne_isos = set(ex.loc[ex["mne_ratio_actual"].notna(), "iso"])
ex_last = ex[(ex["year"] == analysis_years[-1]) & ~ex["iso"].isin(_aamne_isos) & (ex["gdp"] > 0)]
ex_last = ex_last.assign(ln_trade=ex_last["ln_trade_carried"]).set_index("iso")
pred = pd.DataFrame({"tax_haven": ex_last["tax_haven"], "orbis_groups": ex_last["orbis_groups"],
                     "ratio_used": ex_last["mne_sales"] / ex_last["gdp"]})
for sample in EXTRAP_SAMPLES:
    for model, xs in EXTRAP_MODELS.items():
        pred[f"ratio_{model}__{sample}"] = np.exp(_predict(coefs[(sample, model)], ex_last, xs))
    pred[f"change_pct__{sample}"] = 100 * (pred[f"ratio_with_orbis_groups__{sample}"]
                                           / pred[f"ratio_current__{sample}"] - 1)
pred = pred.reset_index().rename(columns={"iso": "iso_partner"}).sort_values("iso_partner")
pred.insert(1, "year", analysis_years[-1])
pred.to_csv(OUT_DIR / "destination_key_extrapolation_predictions.csv", index=False)
print(f"Change of the predicted ratio with the Orbis groups, {analysis_years[-1]}, regression sample / "
      "without tax havens (%): "
      + ", ".join(f"{r['iso_partner']} {r['change_pct__regression']:+.0f} / {r['change_pct__excluding_tax_havens']:+.0f}"
                  for _, r in pred[pred["iso_partner"].isin(["KWT", "IRN"])].iterrows()))

# %% MARK: 5. Keys of Japanese and Canadian groups from their own statistics
# The market key gives every parent's sales the same distribution over
# markets. Japan and Canada publish statistics on where their own groups sell:
# the groups' home share and the distribution of their foreign sales. Section
# 5.2 builds the modelled vector of the two headquarters countries from the
# AAMNE owner layer, net of intra-group exports by BEA's ratio (5.1). Section
# 5.3 substitutes the official statistics, and 5.4 saves one key per country.
# The steps start from the market key as stored in destination_based_sales.csv.
OWN_STATISTICS_HQ = ("CAN", "JPN")
dest = pd.read_csv(OUT_DIR / "destination_based_sales.csv")

# %% MARK: 5.1 Unaffiliated share of cross-border sales (BEA)
# AAMNE exports include intra-group trade, which the concept of unrelated-party
# sales excludes. The survey of US direct investment abroad by BEA is the only
# source that splits multinationals' cross-border sales into sales to
# affiliates and to unaffiliated persons. The unaffiliated share is the
# parents' sales to other foreign persons (Table I.O 1, column 4) plus the
# sales of majority-owned foreign affiliates (MOFA) to unaffiliated persons in
# the US and in third countries (Table II.E 2, columns 4 and 11), divided by
# the same sum including the sales to affiliates (Table I.O 1, column 3, and
# Table II.E 2, columns 2 and 9). I apply it to the modelled exports of every
# headquarters country.
BEA_RAW = Path(data_raw) / "destination_based_sales" / "bea_us_mne"


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return np.nan


def bea_file(year, part):
    hits = sorted(BEA_RAW.glob(f"usdia{year}*_{part}*.xls"))
    if not hits:
        raise FileNotFoundError(f"no BEA {part} file for {year} in {BEA_RAW}")
    return hits[-1]


def bea_parent_sales(year):
    """Return the all-industries row of Table I.O 1: US parents' sales (USD million) to US
    persons (column 2), to foreign affiliates (column 3) and to other foreign persons
    (column 4)."""
    x = pd.ExcelFile(bea_file(year, "PartI"))
    sheet = next(s for s in x.sheet_names if re.search(r"I\.O 1\b", s))
    d = pd.read_excel(x, sheet_name=sheet, header=None)
    return d[d[0].astype(str).str.strip().str.startswith("All industries")].iloc[0]


def bea_affiliate_totals(year):
    """Return the all-countries row of Table II.E 2: MOFA sales (USD million) in columns 1–11."""
    x = pd.ExcelFile(bea_file(year, "PartII_E"))
    sheet = next(s for s in x.sheet_names if re.search(r"II\.E 2\b", s))
    d = pd.read_excel(x, sheet_name=sheet, header=None)
    for _, r in d.iterrows():
        label = str(r[0]).strip() if pd.notna(r[0]) else ""
        if re.sub(r"\s*\d+$", "", label).lower() == "all countries":
            return {f"c{c}": _num(r[c]) for c in range(1, 12)}
    raise ValueError(f"no all-countries row in BEA Table II.E 2 for {year}")


unaff = {}
for y in analysis_years:
    a = bea_affiliate_totals(y)
    p_row = bea_parent_sales(y)
    p_aff, p_unaff = _num(p_row[3]), _num(p_row[4])
    num = p_unaff + a["c4"] + a["c11"]
    den = p_aff + p_unaff + a["c2"] + a["c9"]
    unaff[y] = num / den
print("  BEA unaffiliated share of US MNEs' cross-border sales: "
      + ", ".join(f"{y} {v:.0%}" for y, v in unaff.items()))

# %% MARK: 5.2 Modelled headquarters key
# Per (headquarters country p, market j, year):
#   local(p, j)   = mne_sales(j) x frac(p, j), the MNE local sales of j (3.1)
#       times p's share of j's MNE output in the AAMNE owner-by-host layer
#       (gross output by host and owner country). The host's own column is all
#       domestic-owned output, so I scale it by its D_MNE share. Owners in the
#       rest of the world (ROW) stay in the denominator. Exports are netted at
#       host level, because exports by owner are not published. A covered host
#       where p owns nothing gets 0. Only hosts outside AAMNE fall back to p's
#       global ownership share.
#   exports(p, j) = exports of p-owned firms by destination. These are the
#       domestic MNEs' exports at home and the foreign affiliates' exports
#       abroad times p's share of the foreign-owned output, distributed by the
#       exporter's shares by importer in BACI goods trade and BaTIS services
#       trade without IP charges, times the unaffiliated share of 5.1.
#   key(p, j)     = local + exports.
OWNER_LAYER_FILE = (Path(data_raw) / "destination_based_sales"
                    / "oecd_aamne_bilateral_output_2026-07.csv")
GOODS_ISIC = ["A01T03", "B05T09", "C10T12", "C13T15", "C16", "C17T18", "C19", "C20", "C21",
              "C22", "C23", "C24", "C25", "C26", "C27", "C28", "C29", "C30", "C31T33", "D35_E36T39"]
BACI_ZIP = Path(data_raw) / "destination_based_sales" / "baci" / "BACI_HS17_V202501.zip"
GRAVITY_FILE = Path(data_raw) / "gravity" / "Gravity_V202211.csv"
GOODS_CACHE = Path(data_intermediate) / "bilateral_goods_trade.csv"
SERV_CACHE = Path(data_intermediate) / "bilateral_services_trade.csv"
# The shipped BaTIS extract (config.batis_data) holds only the digitally
# deliverable items. The services matrix needs total services (S), so I build
# it from the bulk file.
BATIS_BULK = (Path(data_raw) / "destination_based_sales" / "oecd_wto_batis_data_bpm6"
              / "OECD-WTO_BATIS_BPM6_December2025_bulk.csv")


def ownership_fractions(w, mne):
    """Return p's share of each host's MNE output, p's global share and the covered hosts."""
    ids = ["year", "cou", "isic"]
    bl = w.melt(id_vars=ids, var_name="iso_parent", value_name="go")
    bl["go"] = pd.to_numeric(bl["go"], errors="coerce").fillna(0.0).clip(lower=0)
    bl = bl[(bl["cou"] != "ROW") & bl["year"].isin(analysis_years)].rename(columns={"cou": "iso"})
    bl = bl.groupby(["iso", "iso_parent", "year"], as_index=False)["go"].sum()

    # The host's own column is all domestic-owned output, so I keep only its D_MNE part.
    dm = mne[mne["own"].isin(["D_MNE", "D_OTH"])]
    dm["GO"] = pd.to_numeric(dm["GO"], errors="coerce")
    dm = dm.pivot_table(index=["cou", "year"], columns="own", values="GO", aggfunc="sum")
    dmne = (dm["D_MNE"] / (dm["D_MNE"] + dm["D_OTH"])).rename("dmne_share")
    # I roll the last year with an AAMNE split forward.
    last = dmne.reset_index().groupby("cou").apply(lambda g: g.loc[g["year"].idxmax()])
    for y in analysis_years:
        miss = [c for c in last.index if (c, y) not in dmne.index]
        if miss:
            add = pd.Series(last.loc[miss, "dmne_share"].values,
                            index=pd.MultiIndex.from_tuples([(c, y) for c in miss], names=["cou", "year"]))
            dmne = pd.concat([dmne, add])
    diag = bl["iso"] == bl["iso_parent"]
    sh = pd.Series(pd.MultiIndex.from_frame(bl.loc[diag, ["iso", "year"]]).map(dmne),
                   index=bl.index[diag]).fillna(0.14)            # flat share of OECD (2020), paragraph 95
    bl.loc[diag, "go"] *= sh

    bl["frac"] = bl["go"] / bl.groupby(["iso", "year"])["go"].transform("sum")
    covered_hosts = set(map(tuple, bl[["iso", "year"]].drop_duplicates().values))
    bl = bl[bl["iso_parent"] != "ROW"]
    glob = bl.groupby(["iso_parent", "year"])["go"].sum()
    glob = (glob / glob.groupby(level="year").transform("sum")).rename("global_frac")
    return bl[["iso", "iso_parent", "year", "frac"]], glob, covered_hosts


def bilateral_goods():
    """Return goods trade by exporter, importer and year (US$ thousand): CEPII Gravity BACI
    for 2016 and BACI HS17 (V202501) for 2017–2023. The result is cached."""
    if GOODS_CACHE.exists():
        return pd.read_csv(GOODS_CACHE)
    g = pd.read_csv(GRAVITY_FILE, usecols=["year", "iso3_o", "iso3_d", "tradeflow_baci"],
                    low_memory=False)
    g = g[(g["year"] == 2016) & (g["tradeflow_baci"] > 0)]
    parts = [g.rename(columns={"iso3_o": "exp", "iso3_d": "imp", "tradeflow_baci": "v"})]
    with zipfile.ZipFile(BACI_ZIP) as z:
        names = z.namelist()
        cc = pd.read_csv(z.open(next(n for n in names if "country_codes" in n)))
        code = dict(zip(cc["country_code"], cc["country_iso3"]))
        for y in range(2017, max(analysis_years) + 1):
            f = next((n for n in names if f"_Y{y}_" in n), None)
            if f is None:
                continue
            b = pd.read_csv(z.open(f), usecols=["t", "i", "j", "v"])
            a = b.groupby(["i", "j"], as_index=False)["v"].sum()
            a["exp"], a["imp"], a["year"] = a["i"].map(code), a["j"].map(code), y
            parts.append(a[["year", "exp", "imp", "v"]])
            print(f"  BACI {y}: {len(b):,} flows -> {len(a):,} pairs")
    out = pd.concat(parts, ignore_index=True)[["year", "exp", "imp", "v"]]
    out = out[(out["exp"] != out["imp"]) & out["exp"].notna() & out["imp"].notna()]
    out.to_csv(GOODS_CACHE, index=False)
    return out


def _batis_iso3(a2):
    try:
        return pycountry.countries.get(alpha_2=a2).alpha_3
    except (LookupError, AttributeError):
        return {"XK": "XKV"}.get(a2)


def bilateral_services():
    """Return services trade without IP charges by exporter, importer and year (BaTIS,
    balanced values, US$ million). I use the import flows (M) as the importer reports
    them, with the partner as the exporter. The result is cached."""
    if SERV_CACHE.exists():
        return pd.read_csv(SERV_CACHE)
    parts = []
    for c in pd.read_csv(BATIS_BULK, usecols=["Reporter", "type_Reporter", "Partner", "type_Partner",
                                              "Flow", "Item_code", "Year", "Final_value",
                                              "Balanced_value"],
                         chunksize=3_000_000, low_memory=False):
        c = c[(c["Flow"] == "M") & c["Year"].isin(analysis_years) & (c["type_Reporter"] == "c")
              & (c["type_Partner"] == "c") & c["Item_code"].isin(["S", "SH"])]
        if len(c):
            c = c.assign(v=pd.to_numeric(c["Balanced_value"], errors="coerce")
                         .fillna(pd.to_numeric(c["Final_value"], errors="coerce")))
            parts.append(c[["Reporter", "Partner", "Item_code", "Year", "v"]])
    b = pd.concat(parts)
    w = b.pivot_table(index=["Year", "Partner", "Reporter"], columns="Item_code", values="v",
                      aggfunc="sum").fillna(0.0)
    w["v"] = (w.get("S", 0.0) - w.get("SH", 0.0)).clip(lower=0)
    w = w.reset_index()
    m = {a: _batis_iso3(a) for a in set(w["Partner"]) | set(w["Reporter"])}
    out = pd.DataFrame({"year": w["Year"], "exp": w["Partner"].map(m), "imp": w["Reporter"].map(m),
                        "v": w["v"]})
    out = out[(out["exp"] != out["imp"]) & out["exp"].notna() & out["imp"].notna()]
    out.to_csv(SERV_CACHE, index=False)
    return out


def owned_exports(w, mne):
    """Return the exports (US$ million) of firms owned by headquarters country p and located
    in e, split into goods and services. For e = p, these are the domestic MNEs' exports
    (D_MNE EXGR). For e != p, they are the foreign affiliates' exports in e (F EXGR) times
    p's share of the foreign-owned output in (e, industry) from the owner layer."""
    m = mne[mne["year"].isin(analysis_years)]
    m["EXGR"] = pd.to_numeric(m["EXGR"], errors="coerce").fillna(0.0)
    m["grp"] = np.where(m["isic"].isin(GOODS_ISIC), "goods", "services")
    home = (m[m["own"] == "D_MNE"].groupby(["cou", "year", "grp"])["EXGR"].sum()
            .rename("x").reset_index().assign(iso_parent=lambda d: d["cou"]))
    fexp = m[m["own"] == "F"][["cou", "year", "isic", "grp", "EXGR"]]
    bl = w.melt(id_vars=["year", "cou", "isic"], var_name="iso_parent", value_name="go")
    bl = bl[bl["year"].isin(analysis_years) & (bl["cou"] != "ROW") & (bl["cou"] != bl["iso_parent"])]
    bl["go"] = pd.to_numeric(bl["go"], errors="coerce").fillna(0.0).clip(lower=0)
    bl["sh"] = bl["go"] / bl.groupby(["cou", "year", "isic"])["go"].transform("sum")
    bl = bl[bl["iso_parent"] != "ROW"].merge(fexp, on=["cou", "year", "isic"], how="inner")
    bl["x"] = bl["sh"].fillna(0.0) * bl["EXGR"]
    abroad = bl.groupby(["iso_parent", "cou", "year", "grp"], as_index=False)["x"].sum()
    out = pd.concat([home[["iso_parent", "cou", "year", "grp", "x"]], abroad], ignore_index=True)
    return out.rename(columns={"cou": "exp"})


def destination_shares(flows):
    """Return each exporter's exports by importer as shares. Years without data take the nearest year."""
    f = flows.groupby(["year", "exp", "imp"], as_index=False)["v"].sum()
    f = f[f["v"] > 0]
    f["s"] = f["v"] / f.groupby(["year", "exp"])["v"].transform("sum")
    have = sorted(f["year"].unique())
    parts = [f]
    for y in analysis_years:
        if y not in have:
            near = _nearest_year(have, y)
            parts.append(f[f["year"] == near].assign(year=y))
            print(f"  [trade] {y}: no flows — using {near} destination shares")
    return pd.concat(parts, ignore_index=True)[["year", "exp", "imp", "s"]]


owner_layer = pd.read_csv(OWNER_LAYER_FILE, low_memory=False)

# Local sales. The ownership shares and the global fallback come from every
# owner in the layer. I keep the two headquarters countries afterwards.
frac, glob, covered = ownership_fractions(owner_layer, aamne_mne)
local = dest[["iso_partner", "year", "mne_sales"]].merge(
    glob.reset_index()[["iso_parent", "year", "global_frac"]], on="year")
local = local.merge(frac.rename(columns={"iso": "iso_partner"}),
                    on=["iso_partner", "iso_parent", "year"], how="left")
in_aamne = pd.Series([(i, y) in covered for i, y in zip(local["iso_partner"], local["year"])],
                     index=local.index)
local["frac_used"] = np.where(in_aamne, local["frac"].fillna(0.0), local["global_frac"])
local["source"] = np.where(in_aamne, "aamne_owner_layer", "global_share_fallback")
# mne_sales in destination_based_sales.csv is in US$.
local["local_usd"] = local["mne_sales"] * local["frac_used"]

# Exports by destination, net of intra-group trade.
gs = destination_shares(bilateral_goods()).assign(grp="goods")
ss = destination_shares(bilateral_services()).assign(grp="services")
shares = pd.concat([gs, ss], ignore_index=True)
ox = owned_exports(owner_layer, aamne_mne)
e = ox.merge(shares, on=["year", "exp", "grp"], how="inner")
e["x_to"] = e["x"] * e["s"] * e["year"].map(unaff)
exp_pj = (e.groupby(["iso_parent", "imp", "year"], as_index=False)["x_to"].sum()
          .rename(columns={"imp": "iso_partner", "x_to": "exports_usd"}))
exp_pj["exports_usd"] *= 1e6
covered_x = (e.groupby(["iso_parent", "exp", "year", "grp"])["x"].first().sum()
             / max(ox["x"].sum(), 1))
print(f"  owned exports matched to destination shares: {covered_x:.1%} of the value "
      f"(the rest: exporters without bilateral data)")
model = local[["iso_parent", "iso_partner", "year", "local_usd", "source"]].merge(
    exp_pj, on=["iso_parent", "iso_partner", "year"], how="left")
model["exports_usd"] = model["exports_usd"].fillna(0.0)
model["hq_dest_key"] = model["local_usd"] + model["exports_usd"]
_cols = ["iso_parent", "iso_partner", "year", "local_usd", "exports_usd", "hq_dest_key", "source"]
hq_model = model[model["iso_parent"].isin(OWN_STATISTICS_HQ)][_cols]
hq_model = hq_model.sort_values(["iso_parent", "year", "iso_partner"])

_t = hq_model[hq_model["year"] == 2022].groupby("iso_parent")[["local_usd", "exports_usd"]].sum()
print("  exports' share of the modelled key, 2022: " + ", ".join(
    f"{p} {_t.loc[p, 'exports_usd'] / _t.loc[p].sum():.0%}" for p in OWN_STATISTICS_HQ))

# %% MARK: 5.3 Official statistics: METI and Statistics Canada
# I replace the two weakest numbers of the modelled key of each country with
# observed ones:
#   1. the home share of the country's groups' sales (by customer location where
#      published, otherwise by location of the selling unit minus the groups'
#      exports), and
#   2. the distribution of their foreign sales over host countries or regions.
# The sources are in data/raw/destination_based_sales/home_share_sources/ (see
# manifest.csv):
#   JPN  METI Basic Survey of Overseas Business Activities (FY2016–2024). Home
#        share by customer location (parents' domestic sales plus affiliates'
#        sales to Japan, without intra-group flows). Foreign sales by region
#        (North America, Asia, Europe, other), split to countries by the
#        modelled pattern.
#   CAN  Statistics Canada 36-10-0356 / 36-10-0470 (2011–2024). Home is the
#        operating revenues in Canada minus merchandise and commercial-services
#        exports. Foreign sales by host come from the affiliates' sales by
#        country.
# Years outside the coverage of a source take its nearest available year.
HOME_SHARE_SRC = Path(data_raw) / "destination_based_sales" / "home_share_sources"


def meti_shares():
    """Return {year: (home_share, {region: share_of_foreign}, unallocated share, source)} for Japan."""
    d = pd.read_csv(HOME_SHARE_SRC / "meti_overseas_business_survey/meti_japan_mne_destination_by_region.csv")
    d["dest"] = d["destination"].str.split(" ").str[0]
    out = {}
    for y, g in d.groupby("fiscal_year"):
        s = g.set_index("dest")["share"]
        home = s.get("japan_external", np.nan)
        reg = {k: s.get(k, 0.0) for k in ["north_america", "asia", "europe", "other"]}
        unalloc = s.get("abroad_unallocated", 0.0)
        tot = sum(reg.values()) + unalloc
        out[int(y)] = (float(home), {k: v / tot for k, v in reg.items()}, unalloc / tot, "meti_customer_location")
    return out


# METI region of each ISO3 code, for splitting the regional totals by the
# modelled pattern. Oceania counts as METI "other".
METI_NORTH_AMERICA = {"USA", "CAN", "MEX", "PRI"}
METI_EUROPE = {"ALB", "AND", "AUT", "BEL", "BGR", "BIH", "BLR", "CHE", "CYP", "CZE", "DEU", "DNK", "ESP",
               "EST", "FIN", "FRA", "GBR", "GRC", "HRV", "HUN", "IRL", "ISL", "ITA", "LIE", "LTU", "LUX",
               "LVA", "MCO", "MDA", "MKD", "MLT", "MNE", "NLD", "NOR", "POL", "PRT", "ROU", "RUS", "SRB",
               "SVK", "SVN", "SWE", "UKR", "GGY", "JEY", "IMN", "GIB", "FRO", "SMR", "XKV", "TUR"}
METI_ASIA = {"CHN", "HKG", "TWN", "KOR", "SGP", "THA", "MYS", "IDN", "PHL", "VNM", "IND", "BGD", "LKA",
             "PAK", "KHM", "LAO", "MMR", "MNG", "NPL", "BRN", "MAC", "TLS", "KAZ", "UZB", "KGZ", "TJK",
             "TKM", "AFG", "BTN", "MDV"}


def meti_region(iso):
    if iso in METI_NORTH_AMERICA:
        return "north_america"
    if iso in METI_EUROPE:
        return "europe"
    if iso in METI_ASIA:
        return "asia"
    return "other"


def statcan_shares():
    """Return {year: (home_share, {host: share_of_foreign}, source)} for Canada."""
    h = pd.read_csv(HOME_SHARE_SRC / "statcan_cdia_activities/tidy_home_share_can.csv")
    h = h[h["measure"] == "sales_destination_adj_all_cmoa_abroad"].set_index("year")["home_share"]
    s = pd.read_csv(HOME_SHARE_SRC / "statcan_cdia_activities/tidy_sales_by_country_can.csv")
    s = s[(s["measure"] == "sales") & (~s["is_aggregate"])].copy()

    def iso(n):
        n = re.sub(r"\s*\(.*\)", "", str(n)).strip()
        m = {"United States": "USA", "United Kingdom": "GBR", "Korea, South": "KOR", "Russian Federation": "RUS",
             "Hong Kong": "HKG", "Bahamas": "BHS", "Taiwan": "TWN", "Türkiye": "TUR", "Turkey": "TUR",
             "Czechia": "CZE", "Viet Nam": "VNM"}
        if n in m:
            return m[n]
        try:
            return pycountry.countries.lookup(n).alpha_3
        except LookupError:
            return None
    s["iso"] = s["affiliate_location"].map(iso)
    out = {}
    for y, g in s.dropna(subset=["iso"]).groupby("year"):
        f = g.groupby("iso")["value"].sum()
        f = f[f > 0]
        if y in h.index and not f.empty:
            out[int(y)] = (float(h[y]), (f / f.sum()).to_dict(), "statcan_export_adjusted")
    return out


def rebuild(b, hq, y, home_share, foreign_shares, src, regional=None, unalloc=0.0):
    """Replace the modelled vector of (hq, y). Home gets home_share of the vector total.
    Foreign gets (1 - home_share), spread by foreign_shares (by host) or, with a regional
    dict, by the modelled pattern within each region."""
    v = b[(b["iso_parent"] == hq) & (b["year"] == y)].set_index("iso_partner")["hq_dest_key"].astype(float)
    if v.empty or v.sum() <= 0:
        return None
    total = v.sum()
    foreign = v.drop([hq] if hq in v.index else [])
    new = pd.Series(0.0, index=v.index)
    new[hq] = total * home_share
    rest = total * (1 - home_share)
    if regional is not None:
        regs = pd.Series({i: meti_region(i) for i in foreign.index})
        alloc = pd.Series(0.0, index=foreign.index)
        for reg, sh in regional.items():
            m = regs == reg
            w = foreign[m]
            if w.sum() > 0:
                alloc[m] += sh * w / w.sum()
        # Parents' exports with an unknown destination follow the modelled foreign pattern.
        alloc += unalloc * foreign / foreign.sum()
        new[foreign.index] = rest * alloc / alloc.sum()
    else:
        fs = pd.Series(foreign_shares)
        fs = fs[fs.index.isin(foreign.index)]
        covered = fs.sum()
        alloc = pd.Series(0.0, index=foreign.index)
        alloc[fs.index] = fs
        # Hosts that the statistic does not list keep the modelled relative pattern for
        # the uncovered remainder (the modelled foreign share outside the listed hosts).
        unl = foreign[~foreign.index.isin(fs.index)]
        unl_share_b = unl.sum() / foreign.sum()
        alloc[unl.index] = unl / unl.sum() * unl_share_b * covered / max(1 - unl_share_b, 1e-9) if unl.sum() > 0 else 0.0
        new[foreign.index] = rest * alloc / alloc.sum()
    out = new.reset_index()
    out.columns = ["iso_partner", "hq_dest_key"]
    out["iso_parent"], out["year"], out["source"], out["home_share_used"] = hq, y, src, home_share
    return out


b = _via_csv(hq_model)
jp, ca = meti_shares(), statcan_shares()
parts = []
for hq in sorted(b["iso_parent"].unique()):
    for y in analysis_years:
        if hq == "JPN":
            yy = _nearest_year(jp, y)
            hs, reg, unalloc, src = jp[yy]
            rec = rebuild(b, hq, y, hs, None, f"{src}_{yy}", regional=reg, unalloc=unalloc)
        else:
            yy = _nearest_year(ca, y)
            hs, fs, src = ca[yy]
            rec = rebuild(b, hq, y, hs, fs, f"{src}_{yy}")
        if rec is None:
            raise ValueError(f"no modelled key for {hq} in {y}")
        parts.append(rec)
hq_official = pd.concat(parts, ignore_index=True)[
    ["iso_parent", "iso_partner", "year", "hq_dest_key", "source", "home_share_used"]]

_mkt = dest[dest["year"] == analysis_years[-1]].set_index("iso_partner")["mne_plus_dds_share"]
print(f"\nHome shares {analysis_years[-1]} (%): market key -> modelled key -> official statistics")
for p in OWN_STATISTICS_HQ:
    _v = b[(b["iso_parent"] == p) & (b["year"] == analysis_years[-1])].set_index("iso_partner")["hq_dest_key"]
    _o = hq_official[(hq_official["iso_parent"] == p) & (hq_official["year"] == analysis_years[-1])]
    print(f"  {p}: {100 * _mkt.get(p, 0) / _mkt.sum():.1f} -> {100 * _v.get(p, 0) / _v.sum():.1f} -> "
          f"{100 * _o['home_share_used'].iloc[0]:.1f}")

# %% MARK: 5.4 Save the Japan-only and Canada-only keys
# Each key keeps the rows of one country, so that only that country's groups
# take their own statistics in script 5. Every other parent keeps the market
# key.
h = _via_csv(hq_official)
for iso in OWN_STATISTICS_HQ:
    k = h[h["iso_parent"] == iso]
    if k.empty:
        raise ValueError(f"no official-statistics rows for {iso}")
    k.to_csv(OUT_DIR / f"destination_based_sales_mkt_own_{iso.lower()}.csv", index=False)
    print(f"Wrote destination_based_sales_mkt_own_{iso.lower()}.csv: {len(k):,} rows")
