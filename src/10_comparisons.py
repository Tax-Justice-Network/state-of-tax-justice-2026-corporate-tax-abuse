# %%
"""
10 — Comparisons: the country results of the report's annex and the country comparison figure.

This script writes the tables behind three parts of the State of Tax Justice 2026: the annex table of corporate tax
abuse (Table A1), the annex table of corporate and individual tax abuse together (Table A3) and the figure after the
executive summary that compares each country's losses with a budget item of its own. It also writes the estimate for
Japan and Canada with their own statistics on where their multinationals sell, which the two tables show below these
countries.

The losses are those of 2023 in constant 2025 US$ million. The corporate loss is the headline estimate (reported-only
sample, resources excluded, unscaled). It is net: a country either loses from profit shifting or gains from it, and a
country that gains has no loss and its gain in a column of its own. The jurisdictions without a corporate income tax
neither lose nor gain. The offshore loss is the tax lost on wealth that a country's residents hide offshore, from the
owner-country results of the State of Tax Justice 2026 offshore-wealth study. The total loss is the sum of the two.

The jurisdictions responsible for the losses are all those with a net inflow of shifted profit, tax havens and other
countries alike. I split each losing country's net loss over them in proportion to its own profit flows to them, so
that the losses caused add up to the losses suffered. Where most of a country's inflow is booked by its own
multinationals at home, the losses it causes come from a headquarters bias, and the country table flags it.

Each loss is compared with four items, as the share of the item it would cover (above 1 means more than all of it),
the first three for the total loss, for the corporate loss alone and for the change in tax revenue under unitary
taxation:
  1 government health spending (WHO Global Health Expenditure Database);
  2 a year of public job training for all unemployed young people aged 15–24 (International Labour Organization (ILO)
    modelled estimates, for the EU countries and Switzerland the EU Labour Force Survey), at a cost per participant of
    the median public cost of training programmes relative to GDP per head in OECD countries;
  3 a year's average wage for all unemployed young people (ILO average earnings, for the EU countries Eurostat);
  4 each country's own budget item under debate in 2026 (the figure after the executive summary).

The tables are plain CSV files. The country table has one row per jurisdiction, the totals table four rows for the
world, each continent and each income group (the World Bank groups without the tax havens, which form a group of their
own): the net gain from unitary taxation and the losses of the losing countries alone, each scaled to all
multinationals and unscaled. The parameters table gives the cost of a year of job training and the scale factor.

Section outline (numbers match the cell headings below):
1. Settings.
2. Losses: the corporate estimate and offshore wealth.
3. The jurisdictions responsible for the losses.
4. Japan and Canada with their own statistics.
5. Health spending and the unemployed young people.
6. Each country's budget item.
7. The country rows and the totals.
8. The tables.
9. Run.

Pipeline step 10 — after 9, the last step.

Reads:
  output/estimates/reported_only/2_resources_excluded/tables/excl_resource/country_estimates__<headline>.csv
      — corporate losses and wages
  output/estimates/reported_only/2_resources_excluded/tables/excl_resource/misalignment__<headline>.csv
      — profit flows (the jurisdictions responsible) and the headquarter countries reporting in each country
  output/variants/mkt_own_{jpn,can}/estimates/reported_only/2_resources_excluded/tables/excl_resource/
      {misalignment,country_estimates}__<headline>.csv  — Japan and Canada with their own statistics
  output/chapter/tables/footnote_own_statistics_jpn_can.csv  — step 8: their home shares of sales
  output/paper/main_text/tables/scaleup_yearly.csv  — the 2023 scale factor (all multinationals)
  data/final/cbcr_main_disaggregated.csv  — the jurisdictions of the data (mark for few observations, _data_coverage)
  data/raw/offshore_wealth/offshore_wealth_owned_sotj2026.csv  — offshore wealth by owner country, US$ million
  data/raw/context/who_ghed_gghed_usd_2026-11.csv  — government health spending in US$ (WHO)
  data/raw/context/youth_comparisons_2026-10/ilostat/  — youth unemployment (modelled and national) and average earnings
  data/raw/context/youth_comparisons_2026-10/wb/wb_NY.GDP.PCAP.CD_2015-2025.json  — GDP per head
  data/raw/context/youth_comparisons_2026-10/oecd/oecd_lmp_2015-2023.csv  — OECD labour-market programmes
  data/raw/context/youth_comparisons_2026-10/wdi/wdi_SP.POP.TOTL_2019-2025.json  — population (training cost)
  data/raw/context/youth_comparisons_2026-10/eurostat/{lfsa_ugan,nama_10_fte,earn_nt_net}*.json  — European youth unemployment
      and wages
  data/raw/context/budget_items_africa_2026-10/comparators_<region>.json  — African budget items
  data/raw/context/budget_items_africa_2026-10/fx_open_er_api_usd_2026-10-20.json  — exchange rates of 20 Oct
      2026, for the budget items of the countries outside Africa and Europe
  data/raw/context/budget_items_europe_2026-10/DEU_government_cuts/germany_agreed_cuts_2026-11-17.csv
  data/raw/chapter_inputs/europe_country_budget_items_2026-11-17.csv, country_comparators_2026-10-20.csv,
      world_budget_item_updates_2026-11-18.csv  — the budget items of the European and other countries and the
      corrected items
  data/raw/macro_variables/{ecb_exr_annual_avg_2026-10,manual_imputation_values}.csv and the ILO wage file of step 1
Writes:
  output/comparisons/tables/annex_countries_2023.csv  — one row per jurisdiction: losses suffered and caused, the
      comparisons, the budget item and the marks of the annex tables
  output/comparisons/tables/annex_totals_2023.csv  — the world, the continents and the income groups, four rows each
  output/comparisons/tables/annex_parameters_2023.csv  — the cost of a year of job training and the scale factor
  output/comparisons/tables/losses_caused_own_statistics.csv  — Japan's and Canada's losses caused and change under
      unitary taxation with the market key and with their own statistics
Usage:
  python src/10_comparisons.py   — from the repository root

Author: Tax Justice Network.
Created: 2026-11-02.  Last updated: 2026-11-23.
"""
import functools
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import config  # noqa: E402
import _data_coverage  # noqa: E402

# %% MARK: 1. Settings
YEAR = 2023                       # loss year (and wage year)
YOUTH_YEAR = 2025                 # latest ILO modelled-estimate year that is not a projection
DEFL = config.deflator_to_base()  # maps a year to the factor that converts that year's US$ to constant 2025 US$
RAW = ROOT / "data/raw"
CTX = RAW / "context"
OUT = ROOT / "output/comparisons"
TABLES = OUT / "tables"
CHAPTER_TABLES = ROOT / "output/chapter/tables"

HEADLINE = "sales_employees_destmnedds__etrdef_domfor__etrmax_inf__loss_cit_gain_etr"
EST = ROOT / "output/estimates/reported_only/2_resources_excluded/tables/excl_resource"
CORP_FILE = EST / f"country_estimates__{HEADLINE}.csv"
MIS_FILE = EST / f"misalignment__{HEADLINE}.csv"
SCALE = ROOT / "output/paper/main_text/tables/scaleup_yearly.csv"
OFFSHORE_SRC = RAW / "offshore_wealth/offshore_wealth_owned_sotj2026.csv"
ECB = RAW / "macro_variables/ecb_exr_annual_avg_2026-10.csv"
MANUAL = RAW / "macro_variables/manual_imputation_values.csv"
HEALTH = CTX / "who_ghed_gghed_usd_2026-11.csv"   # WHO: domestic general government health expenditure, million US$

YOUTH_EV = CTX / "youth_comparisons_2026-10"
LMP = CTX / "youth_comparisons_2026-10/oecd/oecd_lmp_2015-2023.csv"
WDI_POP = CTX / "youth_comparisons_2026-10/wdi/wdi_SP.POP.TOTL_2019-2025.json"
ES_DIR = CTX / "youth_comparisons_2026-10/eurostat"
AFRICA_ITEMS = CTX / "budget_items_africa_2026-10"
DEU_CUTS = CTX / "budget_items_europe_2026-10/DEU_government_cuts/germany_agreed_cuts_2026-11-17.csv"
EUROPE_ITEMS = RAW / "chapter_inputs/europe_country_budget_items_2026-11-17.csv"
COUNTRY_RESEARCH = RAW / "chapter_inputs/country_comparators_2026-10-20.csv"
# Corrected descriptions, amounts and sources of budget items
WORLD_ITEM_UPDATES = RAW / "chapter_inputs/world_budget_item_updates_2026-11-18.csv"
FX_SNAPSHOT = AFRICA_ITEMS / "fx_open_er_api_usd_2026-10-20.json"   # ExchangeRate-API, 20 Oct 2026: units per US$

COUNTRIES_CSV = TABLES / f"annex_countries_{YEAR}.csv"
TOTALS_CSV = TABLES / f"annex_totals_{YEAR}.csv"
PARAMETERS_CSV = TABLES / f"annex_parameters_{YEAR}.csv"

ALIAS = {"XKX": "XKV", "KOS": "XKV"}               # Kosovo: the World Bank and ILOSTAT codes, mapped to the repository code


def rel(path):
    """Return a path relative to the repository root."""
    return str(Path(path).relative_to(ROOT))


def load_fx():
    """Return the ECB's annual average reference rates, in units of each currency per euro, by (currency, year)."""
    e = pd.read_csv(ECB, usecols=["CURRENCY", "TIME_PERIOD", "OBS_VALUE"])
    return {(c, int(y)): v for c, y, v in e.itertuples(index=False)}


FX = load_fx()
ECB25 = pd.Series({c: v for (c, y), v in FX.items() if y == 2025})
USD_PER_EUR = float(ECB25["USD"])


def scale_factor_2023():
    s = pd.read_csv(SCALE)
    ycol = next(c for c in s.columns if c.lower() == "year")
    fcol = next(c for c in s.columns if "factor" in c.lower() or c.lower() in ("sf", "scale"))
    return float(s.loc[s[ycol] == 2023, fcol].iloc[0])


# %% MARK: 2. Losses: the corporate estimate and offshore wealth
# The World Bank income groups of the offshore study's owner countries, in the codes of the corporate estimates
WB_GROUPS = {"HIC": "high_income", "UMC": "upper_middle_income", "LMC": "lower_middle_income", "LIC": "low_income"}
EXTRA_NAMES = {"FLK": "Falkland Islands", "SHN": "Saint Helena", "VAT": "Holy See", "MAF": "Saint Martin",
               "SXM": "Sint Maarten", "COG": "Republic of the Congo", "BOL": "Bolivia", "CZE": "Czechia"}
# Continents from the TJN regions of the estimates. The Caribbean and American islands join Latin America, and Bermuda
# goes to North America (UN M49). The jurisdictions without a region in the estimate files (offshore estimate only) get
# theirs here.
CONTINENT = {"Africa": "Africa", "Asia": "Asia", "Europe": "Europe", "Latin America": "Latin America and the Caribbean",
             "Caribbean/American isl.": "Latin America and the Caribbean", "Northern America": "North America",
             "Oceania": "Oceania"}
CONTINENT_ISO = {"BMU": "North America", "BDI": "Africa", "COM": "Africa", "ERI": "Africa", "GMB": "Africa", "GNB": "Africa",
                 "SHN": "Africa", "FLK": "Latin America and the Caribbean", "KIR": "Oceania", "PLW": "Oceania", "TON": "Oceania",
                 "WLF": "Oceania", "VAT": "Europe"}


def display_name(iso, fallback=None):
    """Return a short display name, from the repository overrides, then a few extras, then pycountry."""
    if iso in config.COUNTRY_NAME_OVERRIDES and iso != "COG":
        return config.COUNTRY_NAME_OVERRIDES[iso]
    if iso in EXTRA_NAMES:
        return EXTRA_NAMES[iso]
    try:
        import pycountry
        c = pycountry.countries.get(alpha_3=iso)
        if c is not None:
            return getattr(c, "common_name", None) or c.name
    except ImportError:
        pass
    return fallback or iso


@functools.lru_cache(maxsize=1)
def offshore_owners():
    """Return the offshore-wealth results of the loss year by owner country (US$ million of the year, the study's own
    column names), indexed by ISO3 code."""
    o = pd.read_csv(OFFSHORE_SRC)
    return o[o["year"] == YEAR].set_index("country_iso3")


def offshore_available():
    """Return the jurisdictions with an offshore-wealth estimate in the loss year."""
    o = offshore_owners()
    return set(o.index[o["tax_loss"].notna()])


@functools.lru_cache(maxsize=1)
def corporate_net():
    """Return the change in corporate tax revenue under unitary taxation in the loss year (headline estimate,
    unscaled, constant 2025 US$ million) by jurisdiction: positive for a country that loses from profit shifting,
    negative for one that gains."""
    s = pd.read_csv(CORP_FILE, low_memory=False)
    return s[s["year"] == YEAR].set_index("iso_partner")["revenue_gain_from_ut"] * DEFL[YEAR]


def load_losses():
    """Return, per jurisdiction with a corporate or an offshore estimate, the corporate loss in the headline estimate
    (2023, constant 2025 US$ million, negative values set to zero), the offshore-wealth tax loss, the total and the
    2023 monthly wage carried in the estimate file (the wage that step 1 attaches to every jurisdiction in the
    country-by-country data)."""
    d = pd.read_csv(CORP_FILE, low_memory=False)
    s = d[d["year"] == YEAR].set_index("iso_partner")
    o = offshore_owners()
    idx = sorted(set(s.index) | set(o.index))
    t = pd.DataFrame(index=pd.Index(idx, name="iso3"))
    names = s["partner_jurisdiction"].reindex(idx).fillna(o["country"].reindex(idx))
    t["country"] = [display_name(i, names.get(i)) for i in idx]
    t["wb_income_group"] = s["wb_income_group"].reindex(idx).fillna(o["incomelevel"].map(WB_GROUPS).reindex(idx))
    t["region_tjn"] = s["region_tjn"].reindex(idx)
    t["corp_estimate_available"] = t.index.isin(s.index)
    defl = DEFL[YEAR]
    t["corp_loss_musd"] = (s["revenue_gain_from_ut"] * defl).reindex(idx).clip(lower=0).fillna(0.0)
    t["offshore_wealth_loss_musd"] = (o["tax_loss"] * defl).reindex(idx).clip(lower=0).fillna(0.0)
    t["total_loss_musd"] = t["corp_loss_musd"] + t["offshore_wealth_loss_musd"]
    t["_wage_cbcr"] = s["wage_monthly"].reindex(idx)
    return t


def continents(losses):
    """Return the continent of every jurisdiction of losses."""
    continent = losses["region_tjn"].map(CONTINENT)
    continent.update(pd.Series(CONTINENT_ISO))
    assert continent.notna().all(), sorted(continent.index[continent.isna()])
    return continent


# %% MARK: 3. The jurisdictions responsible for the losses
# A country whose inflow of shifted profit is booked mostly (more than this share) by its own multinationals at home is
# flagged: the losses it causes come from a headquarters bias.
HQ_BIAS = 0.5


@functools.lru_cache(maxsize=None)
def misaligned(year, est=EST):
    """Return the misaligned profit of every headquarters country × partner cell in a year (constant 2025 US$ million),
    from the estimates in the folder est (the headline unless given)."""
    m = pd.read_csv(est / MIS_FILE.name, low_memory=False, usecols=["iso_parent", "iso_partner", "year", "misaligned_profit"])
    m = m[(m["year"] == year) & m["misaligned_profit"].notna()].copy()
    m["v"] = m["misaligned_profit"] * DEFL[year] / 1e6
    return m


def responsibility(year=YEAR, est=EST):
    """Return the tax losses each jurisdiction causes in other countries in a year, 2023 unless given (unscaled,
    constant 2025 US$ million), from the estimates in the folder est (the headline unless given). The responsible
    jurisdictions are all those with a net inflow of shifted profit in that year, tax havens and other countries alike.
    I spread each losing country's net loss (the corporate-loss column) over them in proportion to its own profit flows
    to each of them. Within each headquarters country's panel, the profit shifted out of the country goes to the
    panel's excess-profit jurisdictions in proportion to their excess (the bilateral rule). I leave out flows to
    jurisdictions without a net inflow, so the losses caused add up exactly to the losses suffered. The function returns
    the losses caused (a Series by jurisdiction) and the losses they add up to."""
    m = misaligned(year, est)
    inflow = m.groupby("iso_partner")["v"].sum()
    resp = sorted(inflow.index[inflow > 0])
    pos = m[m["v"] > 0].assign(w=lambda d: d["v"] / d.groupby("iso_parent")["v"].transform("sum"))
    out = m[m["v"] < 0].assign(out=lambda d: -d["v"])
    f = out[["iso_parent", "iso_partner", "out"]].merge(pos[["iso_parent", "iso_partner", "w"]], on="iso_parent",
                                                          suffixes=("_from", "_to"))
    flows = (f["out"] * f["w"]).groupby([f["iso_partner_from"], f["iso_partner_to"]]).sum().unstack(fill_value=0.0)
    s = pd.read_csv(est / CORP_FILE.name, low_memory=False)
    net = s[s["year"] == year].set_index("iso_partner")["revenue_gain_from_ut"] * DEFL[year]
    lost = net[net > 0]
    fl = flows.reindex(index=lost.index, columns=resp, fill_value=0.0)
    to_resp = fl.sum(axis=1)
    pooled = fl.sum(axis=0) / fl.values.sum()                           # a loser with no flow to the set takes the mix of all losers
    shares = fl.div(to_resp.where(to_resp > 0), axis=0)
    shares.loc[to_resp <= 0] = pooled.values
    caused = shares.mul(lost, axis=0).sum(axis=0)
    assert abs(caused.sum() - lost.sum()) < 1e-6 * lost.sum(), (caused.sum(), lost.sum())
    return caused[caused > 0].sort_values(ascending=False), lost.sum()


def headquarters_share(year=YEAR):
    """Return, for each jurisdiction that receives shifted profit, the share of that profit (its excess profit, summed
    over the multinationals of every headquarters country) that its own multinationals book at home. Above HQ_BIAS, the
    losses it causes come from a headquarters bias: its multinationals report more profit at home than their employees
    and sales there would attract under unitary taxation."""
    pos = misaligned(year).query("v > 0")
    gross = pos.groupby("iso_partner")["v"].sum()
    home = pos[pos["iso_parent"] == pos["iso_partner"]].groupby("iso_partner")["v"].sum()
    return home.reindex(gross.index, fill_value=0.0) / gross


def headquarters_bias(iso, share):
    """Whether the losses a country causes come from a headquarters bias: more than HQ_BIAS of the profit shifted into
    it is booked by its own multinationals at home, and it is not on the tax-haven list. The chapter's figure of the
    largest recipients (step 8) leaves out the same countries."""
    return pd.notna(share) and share > HQ_BIAS and iso not in config.TAX_HAVENS_REPRESENTATION


# %% MARK: 4. Japan and Canada with their own statistics
# Japan and Canada publish statistics on where their own multinationals sell. The variants mkt_own_jpn and mkt_own_can
# rerun the headline estimate with only that country's groups apportioned on those statistics, and step 8 writes the
# methodology note's footnote from them (home shares of sales under the market key and the national statistics). I
# add the losses each country would cause on that basis, for the annex of the report.
OWN_STATS = {"JPN": "mkt_own_jpn", "CAN": "mkt_own_can"}
OWN_STATS_FOOTNOTE = CHAPTER_TABLES / "footnote_own_statistics_jpn_can.csv"
OWN_STATS_CSV = TABLES / "losses_caused_own_statistics.csv"


def own_statistics(year=YEAR):
    """Return and write, for Japan and Canada, the losses caused in other countries and the change in tax revenue
    under unitary taxation with the market key (headline) and with the country's own statistics for its groups
    (unscaled, constant 2025 US$ million), with the home shares of the footnote."""
    fn = pd.read_csv(OWN_STATS_FOOTNOTE).set_index("iso3")
    headline, _ = responsibility(year)

    def ut(est, iso):
        s = pd.read_csv(est / CORP_FILE.name, low_memory=False)
        return float(s.loc[(s["year"] == year) & (s["iso_partner"] == iso), "revenue_gain_from_ut"].iloc[0]) * DEFL[year]

    rows = []
    for iso, variant in OWN_STATS.items():
        est = ROOT / f"output/variants/{variant}/estimates/reported_only/2_resources_excluded/tables/excl_resource"
        caused, _ = responsibility(year, est)
        rows.append(dict(iso3=iso, country=fn.at[iso, "country"], caused_market_key=headline.get(iso, 0.0),
                         caused_own_statistics=caused.get(iso, 0.0), ut_market_key=ut(EST, iso),
                         ut_own_statistics=ut(est, iso), home_share_market_key_pct=fn.at[iso, "home_share_market_key_pct"],
                         home_share_national_pct=fn.at[iso, "home_share_national_pct"], source=fn.at[iso, "source"]))
    out = pd.DataFrame(rows)
    assert (abs(out["ut_own_statistics"] / 1e3 - fn["own_statistics_bn"].reindex(out["iso3"]).values) < 0.01).all()
    TABLES.mkdir(parents=True, exist_ok=True)
    out.to_csv(OWN_STATS_CSV, index=False)
    return out.set_index("iso3")


# %% MARK: 5. Health spending and the unemployed young people
ILO = {"une": YOUTH_EV / "ilostat/ilostat_UNE_2UNE_SEX_AGE_NB_A_sexT_2015-2027.csv",
       "une_nat": YOUTH_EV / "ilostat/ilostat_UNE_TUNE_SEX_AGE_NB_A_sexT_age15-24_2015-2026.csv",
       "earn": YOUTH_EV / "ilostat/ilostat_EAR_EMTA_SEX_CUR_NB_A_sexT_2015-2025.csv"}
WB_GDPPC = YOUTH_EV / "wb/wb_NY.GDP.PCAP.CD_2015-2025.json"
YOUTH = "AGE_YTHADULT_Y15-24"
EU27 = ["AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA",
        "LVA", "LTU", "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE"]
COUNTRIES = EU27 + ["GBR", "CHE"]   # the European rows, whose inputs come from Eurostat where it has them
ES_GEO = {"AT": "AUT", "BE": "BEL", "BG": "BGR", "HR": "HRV", "CY": "CYP", "CZ": "CZE", "DK": "DNK", "EE": "EST", "FI": "FIN",
          "FR": "FRA", "DE": "DEU", "EL": "GRC", "HU": "HUN", "IE": "IRL", "IT": "ITA", "LV": "LVA", "LT": "LTU", "LU": "LUX",
          "MT": "MLT", "NL": "NLD", "PL": "POL", "PT": "PRT", "RO": "ROU", "SK": "SVK", "SI": "SVN", "ES": "ESP", "SE": "SWE",
          "CH": "CHE", "UK": "GBR", "NO": "NOR", "IS": "ISL"}


def closest_year(d, isos, year=YEAR):
    """Return the row of the year closest to year for each country of isos (the earlier year on a tie), indexed by
    ISO3 code. d has the columns iso3, year and value."""
    d = d[d["iso3"].isin(isos)].assign(_dist=lambda t: (t["year"] - year).abs())
    return d.sort_values(["iso3", "_dist", "year"]).groupby("iso3").head(1).set_index("iso3")


def health_spending(isos, year=YEAR):
    """Return government health spending in constant 2025 US$ million in the year closest to 2023 (the earlier one on
    a tie), deflated with the US GDP deflator of that year: value_musd and year by country. It is WHO's own amount in
    current US$. I do not multiply WHO's share of GDP by the World Bank's GDP, because the two GDP figures differ for
    some countries and the product then misstates the spending. The World Bank already uses Nigeria's revised GDP of
    2025, for example, which is a third larger than the GDP behind WHO's share."""
    d = closest_year(pd.read_csv(HEALTH, comment="#"), isos, year)
    v = pd.Series({i: d.at[i, "value"] * DEFL[int(d.at[i, "year"])] for i in d.index}, dtype=float)
    return pd.DataFrame({"value_musd": v, "year": d["year"].reindex(v.index)})


def read_ilo(path):
    d = pd.read_csv(path, low_memory=False)
    d["ref_area"] = d["ref_area"].replace(ALIAS)
    return d


def youth_unemployed():
    """Return the unemployed 15–24-year-olds from the ILO modelled estimates (November 2025) for YOUTH_YEAR, with the
    year of each figure and its origin: "modelled" for the modelled estimate of YOUTH_YEAR, "modelled_latest" for the
    latest earlier modelled estimate and "national" for the latest national ILOSTAT figure, with the label of its
    national source. Where the ILO does not model a jurisdiction for YOUTH_YEAR, I take the latest ILO modelled or
    national ILOSTAT figure, whichever is more recent (ties go to the modelled estimate)."""
    m = read_ilo(ILO["une"])
    m = m[(m["sex"] == "SEX_T") & (m["classif1"] == YOUTH)]
    n = read_ilo(ILO["une_nat"])
    n = n[(n["sex"] == "SEX_T") & (n["classif1"] == YOUTH) & (n["time"] <= YOUTH_YEAR)].dropna(subset=["obs_value"])
    rows = {}
    for iso, v in m[m["time"] == YOUTH_YEAR].set_index("ref_area")["obs_value"].items():
        rows[iso] = (v * 1e3, YOUTH_YEAR, "modelled", np.nan)
    m_last = m[m["time"] < YOUTH_YEAR].sort_values("time").groupby("ref_area").last()
    n_last = n.sort_values("time").groupby("ref_area").last()
    for iso in sorted((set(m_last.index) | set(n_last.index)) - set(rows)):
        cands = []
        if iso in m_last.index:
            cands.append((int(m_last.at[iso, "time"]), 1, m_last.at[iso, "obs_value"] * 1e3, "modelled_latest", np.nan))
        if iso in n_last.index:
            cands.append((int(n_last.at[iso, "time"]), 0, n_last.at[iso, "obs_value"] * 1e3, "national",
                          n_last.at[iso, "source.label"]))
        y, _, v, origin, label = max(cands)
        rows[iso] = (v, y, origin, label)
    return pd.DataFrame.from_dict(rows, orient="index", columns=[
        "youth_unemployed_15_24", "youth_unemployed_year", "youth_unemployed_origin", "youth_unemployed_source_label"])


def ilo_usd(path):
    d = read_ilo(path)
    d = d[d["classif1"] == "CUR_TYPE_USD"]
    return d[d["sex"] == "SEX_T"] if "sex" in d.columns else d


def nearest(d, year, lo=2016, hi=2025, key="ref_area", tcol="time"):
    """Return the observation nearest to `year` per jurisdiction (the later year on ties), within [lo, hi]."""
    d = d[(d[tcol] >= lo) & (d[tcol] <= hi)].copy()
    d["_dist"] = (d[tcol] - year).abs()
    return d.sort_values([key, "_dist", tcol], ascending=[True, True, False]).groupby(key).first()


def average_wage(t):
    """Return the monthly average wage (US$), its year and its annual amount in constant 2025 US$ for every
    jurisdiction, and where it comes from (wage_origin): "manual" for a hand-collected wage, "cbcr" for the wage that
    step 1 attaches to the jurisdiction in the country-by-country data (ILO average earnings, carried to 2023 from other
    years or, without ILO data, modelled from GDP and population), "ilo_nearest" for the ILO figure nearest to 2023 of a
    jurisdiction outside those data and "none" without a wage. I take a hand-collected wage from the manual file
    itself, the wage that step 1 applies to the data unconditionally."""
    near = nearest(ilo_usd(ILO["earn"]), YEAR)
    man = pd.read_csv(MANUAL)
    man = man[man["variable"] == "wage_monthly"].drop_duplicates("iso_partner", keep="last").set_index("iso_partner")
    rows = {}
    for iso in t.index:
        w = t.at[iso, "_wage_cbcr"]
        if iso in man.index:
            rows[iso] = (float(man.at[iso, "value"]), YEAR, "manual")
        elif pd.notna(w):
            rows[iso] = (w, YEAR, "cbcr")
        elif iso in near.index:
            rows[iso] = (near.at[iso, "obs_value"], int(near.at[iso, "time"]), "ilo_nearest")
        else:
            rows[iso] = (np.nan, np.nan, "none")
    w = pd.DataFrame.from_dict(rows, orient="index", columns=["avg_wage_monthly_usd", "avg_wage_year", "wage_origin"])
    w["avg_wage_annual_usd_2025"] = 12 * w["avg_wage_monthly_usd"] * w["avg_wage_year"].map(DEFL)
    return w


def gdp_per_head(index):
    """Return GDP per head (World Bank) of the year nearest to 2023, in US$ of that year and in constant 2025 US$."""
    g = json.loads(WB_GDPPC.read_text())[1]
    g = pd.DataFrame([{"iso": ALIAS.get(x["countryiso3code"], x["countryiso3code"]), "year": int(x["date"]),
                       "value": x["value"]} for x in g if x["value"] is not None and x["countryiso3code"]])
    g = nearest(g, YEAR, key="iso", tcol="year")
    out = pd.DataFrame(index=index)
    out["gdp_per_capita_usd"] = g["value"].reindex(index)
    out["gdp_per_capita_year"] = g["year"].reindex(index)
    out["gdp_per_capita_usd_2025"] = out["gdp_per_capita_usd"] * out["gdp_per_capita_year"].map(DEFL)
    return out


def youth_inputs(losses):
    """Return, per jurisdiction of losses, the unemployed young people (15–24), the average annual wage and GDP per
    head, both in constant 2025 US$. I round them to whole people and whole dollars."""
    t = losses[[]].join(youth_unemployed()).join(average_wage(losses)).join(gdp_per_head(losses.index))
    return t[["youth_unemployed_15_24", "avg_wage_annual_usd_2025", "gdp_per_capita_usd_2025"]].round(0)


def wdi(path):
    d = json.load(open(path))[1]
    rows = [(ALIAS.get(r["countryiso3code"], r["countryiso3code"]), int(r["date"]), r["value"]) for r in d
            if r["countryiso3code"]]
    return pd.DataFrame(rows, columns=["iso3", "year", "value"]).dropna().drop_duplicates(["iso3", "year"])


def lmp_cost_ratio(programme):
    """Return the public cost per participant-year of an OECD labour-market programme relative to GDP per head. The
    cost is expenditure ÷ average stock of participants ÷ GDP per head, where GDP is expenditure ÷ its share of GDP
    and population comes from WDI. I take each country's mean over 2019, 2022 and 2023 (leaving out the COVID years)
    and the median across countries. The function returns (median, number of countries, per-country ratios)."""
    lmp = pd.read_csv(LMP)
    k = lmp.pivot_table(index=["REF_AREA", "TIME_PERIOD", "PROGRAMME"], columns=["MEASURE", "UNIT_MEASURE"],
                        values="OBS_VALUE")
    k.columns = [f"{a}_{b}" for a, b in k.columns]
    k = k.reset_index()
    k = k[(k["PROGRAMME"] == programme) & k["TIME_PERIOD"].isin([2019, 2022, 2023]) & (k["STO_PS"] > 0)]
    pop = wdi(WDI_POP).set_index(["iso3", "year"])["value"]
    gdp_pc = (k["EXP_XDC"] / (k["EXP_PT_B1GQ"] / 100)) / [pop.get((a, int(y)), np.nan) for a, y in
                                                           zip(k["REF_AREA"], k["TIME_PERIOD"])]
    r = (k["EXP_XDC"] / k["STO_PS"]) / gdp_pc
    by_c = r[np.isfinite(r)].groupby(k["REF_AREA"]).mean()
    return float(by_c.median()), len(by_c), by_c


def eurostat(name, folder=ES_DIR, **filters):
    """Turn a stored Eurostat JSON-stat 2.0 download into an iso3 × year table (other dimensions filtered by
    `filters`)."""
    j = json.load(open(folder / name))
    ids, size = j["id"], j["size"]
    cats = []
    for dim in ids:
        idx = j["dimension"][dim]["category"]["index"]
        cats.append(sorted(idx, key=idx.get) if isinstance(idx, dict) else idx)
    rows = []
    for k, v in (j["value"].items() if isinstance(j["value"], dict) else enumerate(j["value"])):
        k, pos = int(k), []
        for n in reversed(size):
            pos.append(k % n)
            k //= n
        rows.append([cats[i][q] for i, q in enumerate(reversed(pos))] + [v])
    d = pd.DataFrame(rows, columns=ids + ["value"])
    for col, val in filters.items():
        d = d[d[col] == val]
    d["iso3"], d["time"] = d["geo"].map(ES_GEO), d["time"].astype(int)
    return d.pivot_table(index="iso3", columns="time", values="value")


def europe_youth(isos, youth):
    """Return the unemployed young people and the average annual wage of the European rows, per country, the wage in
    US$ of 2025 prices, each with its origin. youth holds the inputs of youth_inputs, the fallback.
    - Unemployed 15–24 (youth_n_origin): the Eurostat Labour Force Survey (LFS, lfsa_ugan) of 2025, else of 2024
      ("eurostat", with youth_n_year), else the ILO modelled estimate ("ilo", the UK).
    - Average annual wage (wage_origin): the Eurostat average full-time adjusted salary per employee of 2023
      ("nama_10_fte"), else the Eurostat gross earnings of an average full-time worker ("earn_nt_net", Netherlands,
      Switzerland), else the ILOSTAT earnings ("ilo", UK)."""
    usd_per_eur = lambda y: FX[("USD", y)]  # noqa: E731
    une = eurostat("lfsa_ugan_y15-24_2023-2025.json", unit="THS_PER", sex="T", age="Y15-24", citizen="TOTAL")
    fte = eurostat("nama_10_fte_2021-2024.json", unit="EUR")
    aw = eurostat("earn_nt_net_gross_aw100_2021-2025.json")
    rows = {}
    for iso in isos:
        r = {}
        u = une.loc[iso].dropna() if iso in une.index else pd.Series(dtype=float)
        if 2025 in u.index or 2024 in u.index:
            y = 2025 if 2025 in u.index else 2024
            r.update(youth_n=u[y] * 1e3, youth_n_origin="eurostat", youth_n_year=y)
        else:
            r.update(youth_n=youth["youth_unemployed_15_24"].get(iso, np.nan), youth_n_origin="ilo", youth_n_year=YOUTH_YEAR)
        if iso in fte.index and pd.notna(fte.at[iso, 2023]):
            r.update(wage_usd25=fte.at[iso, 2023] * usd_per_eur(2023) * DEFL[2023], wage_origin="nama_10_fte")
        elif iso in aw.index and pd.notna(aw.at[iso, 2023]):
            r.update(wage_usd25=aw.at[iso, 2023] * usd_per_eur(2023) * DEFL[2023], wage_origin="earn_nt_net")
        else:
            r.update(wage_usd25=youth["avg_wage_annual_usd_2025"].get(iso, np.nan), wage_origin="ilo")
        rows[iso] = r
    return pd.DataFrame.from_dict(rows, orient="index")


def comparison_amounts(losses, youth, ein, tr):
    """Return, per jurisdiction of losses, the amounts its losses are compared with, in constant 2025 US$ million:
    government health spending (health), a year of public job training (train) and a year's average wage (wage) for
    all unemployed young people, and their number (youth_n). youth holds the inputs of youth_inputs, ein those of
    europe_youth, which replace them for the European rows, and tr is the cost of a year of job training relative to
    GDP per head."""
    health = health_spending(list(losses.index))["value_musd"]
    rows = {}
    for iso in losses.index:
        u, wage_usd = youth["youth_unemployed_15_24"].get(iso, np.nan), youth["avg_wage_annual_usd_2025"].get(iso, np.nan)
        if iso in ein.index:        # the European rows: Eurostat youth unemployment and wages
            u, wage_usd = ein.at[iso, "youth_n"], ein.at[iso, "wage_usd25"]
        some = pd.notna(u) and u > 0
        rows[iso] = dict(health=health.get(iso, np.nan),
                         train=u * tr * youth["gdp_per_capita_usd_2025"].get(iso, np.nan) / 1e6 if some else np.nan,
                         wage=u * wage_usd / 1e6 if some else np.nan, youth_n=u if some else np.nan)
    return pd.DataFrame.from_dict(rows, orient="index")


# %% MARK: 6. Each country's budget item
# The country comparison. I leave out energy subsidies and election budgets and use the country's next documented
# item instead. For Nigeria this is the 2026 UN humanitarian appeal for the north-east, and for Ethiopia there is none.
OVERRIDE = {"COD": "nutrition component", "CMR": "academic debt", "RWA": "maternal, child", "MLI": "school canteens",
            "SOM": "social spending", "NGA": "humanitarian appeal", "ETH": None}


def fx_number(row):
    """Return the local currency per US$ of the record, as local value ÷ US$ value (exact by construction). Without
    these values, I fall back to the first number in the fx_rate text."""
    lv = local_number(row.get("local_value"))
    if lv and row.get("usd_m"):
        return lv / (float(row["usd_m"]) * 1e6)
    m = re.search(r"[\d][\d,]*\.?\d*", str(row.get("fx_rate", "")))
    return float(m.group(0).replace(",", "")) if m else None


def local_number(v):
    """Parse a local value given as a number or as text like '23.79 billion' or '1.01 trillion'."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).lower().replace(",", "")
    m = re.search(r"([\d.]+)\s*(trillion|billion|million|tn|bn|m)?", s)
    if not m:
        return None
    mult = {"trillion": 1e12, "tn": 1e12, "billion": 1e9, "bn": 1e9, "million": 1e6, "m": 1e6}.get(m.group(2), 1)
    return float(m.group(1)) * mult


@functools.lru_cache(maxsize=1)
def item_updates():
    """Return the corrected budget items of WORLD_ITEM_UPDATES, by ISO3 code."""
    return pd.read_csv(WORLD_ITEM_UPDATES).set_index("iso3")


def country_comparison(iso, comp):
    """Return the African country's item: the OVERRIDE item, else the preferred item."""
    c_all = comp[comp["iso3"] == iso]
    if not len(c_all):
        return None
    if iso in OVERRIDE:
        m = OVERRIDE[iso]
        sel = c_all[c_all["comparator"].str.contains(m, regex=False)] if m else c_all.iloc[0:0]
        if m and len(sel) != 1:
            raise ValueError(f"{iso}: the item text {m!r} matches {len(sel)} of the researched items")
    else:
        sel = c_all[c_all["preferred"].astype(bool)]
    return sel.iloc[0] if len(sel) else None


def africa_items():
    """Return one row per researched African budget item: its local and US$ value, exchange rate and sources (the
    record's list of sources joined with " | "). The
    item that a country's comparison uses takes the corrected description, amount and sources of WORLD_ITEM_UPDATES.
    An amount in US$ is converted at the item's own exchange rate, and so is an amount in local currency."""
    rows = []
    for f in sorted(AFRICA_ITEMS.glob("comparators_*.json")):
        group = f.stem.replace("comparators_", "")
        for r in json.loads(f.read_text()):
            rows.append(dict(r, group=group))
    c = pd.DataFrame(rows)
    c["local_value_num"] = c["local_value"].map(local_number)
    c["fx_local_per_usd"] = c.apply(lambda r: fx_number(r), axis=1)
    c["usd_m"] = pd.to_numeric(c["usd_m"], errors="coerce")
    for iso, u in item_updates().iterrows():
        row = country_comparison(iso, c)
        if row is None:
            continue
        k, fx = row.name, row["fx_local_per_usd"]
        if pd.notna(u["description"]):
            c.at[k, "comparator"] = u["description"]
        if pd.notna(u["cost_usd_m"]):
            c.at[k, "usd_m"] = u["cost_usd_m"]
            c.at[k, "local_value_num"] = u["cost_usd_m"] * 1e6 * fx if pd.notna(fx) else np.nan
        elif pd.notna(u["cost_local_m"]):
            c.at[k, "local_value_num"], c.at[k, "usd_m"] = u["cost_local_m"] * 1e6, u["cost_local_m"] / fx
        if pd.notna(u["source"]):
            c.at[k, "sources"] = u["source"]
    c["sources"] = c["sources"].map(lambda v: " | ".join(v) if isinstance(v, list) else v)
    return c


def africa_item(c):
    """Return a researched African budget item as the fields of the country comparison: the description, the amount in
    local currency and in US$, the currency, the exchange rate, the sources of the item and its origin ("africa")."""
    usd_amount = str(c["currency"]).upper() in ("USD", "US$")
    return dict(c_desc=c["comparator"], c_local=c["local_value_num"] / 1e6 if pd.notna(c["local_value_num"]) else np.nan,
                c_usd=c["usd_m"], c_cur="USD" if usd_amount else str(c["currency"]),
                c_fx=1.0 if usd_amount else c["fx_local_per_usd"], c_src=c["sources"], c_origin="africa")


@functools.lru_cache(maxsize=1)
def europe_budget_items():
    """Return the checked budget items of the European countries, by ISO3 code."""
    return pd.read_csv(EUROPE_ITEMS).set_index("iso3")


def europe_item(iso):
    """Return a European country's own budget item, checked against its original source, as the fields specific_*:
    the description, the amount in local currency and in € (ECB 2025 average rate), the currency, the exchange rate
    and the source. For Germany the item is all federal spending cuts agreed for 2027, summed from the cuts table. A
    country without an item gets none."""
    items = europe_budget_items()
    if iso not in items.index:
        return {}
    I = items.loc[iso]
    if iso == "DEU":        # the federal spending cuts agreed for 2027 (cabinet and Bundestag, the largest year), net
        cuts = pd.read_csv(DEU_CUTS)
        local_m = cuts.loc[cuts["include_in_total"] == "yes", "amount_2027_bn_eur"].sum() * 1e3
    else:
        local_m = I["amount_local_m"]
    cur = I["currency"]
    fx = 1.0 if cur == "EUR" else float(ECB25[cur])
    return dict(specific_what=I["description"], specific_local_m=local_m, specific_currency=cur,
                specific_eur_m=local_m / fx if cur != "EUR" else local_m, specific_source=I["source"], specific_fx=fx)


def europe_items():
    """Return the budget items of the European rows, by ISO3 code. A country that gains from profit shifting and has
    no offshore-wealth estimate has no loss to compare, so it gets no item."""
    net, off = corporate_net(), offshore_available()
    rows = {iso: {} if net.get(iso, np.nan) < 0 and iso not in off else europe_item(iso) for iso in COUNTRIES}
    return pd.DataFrame.from_dict(rows, orient="index").reindex(COUNTRIES)


def parse_research_amount(text):
    """Parse an amount of the country research ('ARS 3.7 trillion', 'R$22.7bn in 2027', '≈$197m', 'Rp106tn') into
    (currency, million)."""
    m = re.match(r"\s*[≈~]?\s*(US\$|R\$|C\$|S/|\$|₱|Rp|ARS|NPR)\s?([\d.,]+)\s?(trillion|tn|bn|billion|m|million)\b", str(text))
    if not m:
        raise ValueError(f"cannot read the amount in {text!r}")
    cur = {"US$": "USD", "$": "USD", "R$": "BRL", "C$": "CAD", "S/": "PEN", "₱": "PHP", "Rp": "IDR"}.get(m.group(1), m.group(1))
    return cur, float(m.group(2).replace(",", "")) * {"trillion": 1e6, "tn": 1e6, "bn": 1e3, "billion": 1e3}.get(m.group(3), 1.0)


def apply_item_updates(items):
    """Apply the corrected budget items to the country comparisons in items, a dict by ISO3 code, and return it. The
    update gives the corrected description, amount and sources. An amount in US$ is converted at the item's own
    exchange rate, and so is an amount in local currency. Countries that are not in items are left alone."""
    for iso, u in item_updates().iterrows():
        if iso not in items:
            continue
        c = items[iso]
        if pd.notna(u["description"]):
            c["c_desc"] = u["description"]
        if pd.notna(u["cost_usd_m"]):
            c["c_usd"], c["c_local"] = u["cost_usd_m"], u["cost_usd_m"] * c["c_fx"]
        elif pd.notna(u["cost_local_m"]):
            c["c_local"], c["c_usd"] = u["cost_local_m"], u["cost_local_m"] / c["c_fx"]
        if pd.notna(u["source"]):
            c["c_src"] = u["source"]
    return items


def world_country_specific(isos, continent, comp, europe):
    """Return the country comparison by iso: for African countries the researched item of comp (the rows of
    africa_items), for the European rows the item of europe (specific_* fields, converted from € to US$ at the ECB
    2025 average), else the country research of October 2026. I convert the research's local amounts at the rates of
    20 October 2026, as for the African items, rather than use its rounded US$ figures. The corrected items of
    WORLD_ITEM_UPDATES replace those of the research. The field c_origin says where an item comes from: "africa",
    "europe" or "research"."""
    research = pd.read_csv(COUNTRY_RESEARCH).set_index("iso3")
    rates = json.loads(FX_SNAPSHOT.read_text())["rates"]
    out = {}
    for iso in isos:
        if continent[iso] == "Africa":
            c = country_comparison(iso, comp)
            if c is None:
                continue
            out[iso] = africa_item(c)
        elif iso in europe.index:
            r = europe.loc[iso]
            if pd.isna(r.get("specific_eur_m")):
                continue
            out[iso] = dict(c_desc=r["specific_what"], c_local=r["specific_local_m"], c_usd=r["specific_eur_m"] * USD_PER_EUR,
                            c_cur=r["specific_currency"], c_fx=r["specific_fx"] / USD_PER_EUR, c_src=r["specific_source"],
                            c_origin="europe")
        elif iso in research.index and pd.notna(research.at[iso, "comparator_usd_bn"]):
            r = research.loc[iso]
            cur, v = parse_research_amount(r["comparator_local"])
            fx = 1.0 if cur == "USD" else float(rates[cur])
            out[iso] = dict(c_desc=r["comparator"], c_local=v, c_usd=v / fx, c_cur=cur, c_fx=fx, c_src=r["comparator_source"],
                            c_origin="research")
    assert set(item_updates().index) <= set(out), sorted(set(item_updates().index) - set(out))
    return apply_item_updates(out)


# %% MARK: 7. The country rows and the totals
WORLD = "World"
COMPARE = ["health", "train", "wage"]     # the comparisons of the annex tables
# The income groups of the totals: the World Bank groups without the tax havens of the representation list, which form
# a group of their own, as in the chapter.
INCOME_GROUPS = ["high_income", "upper_middle_income", "lower_middle_income", "low_income", "tax_haven"]


def country_rows(losses, amounts, items, keys):
    """Return the country rows and the losses suffered worldwide. For every country the rows hold the losses
    (corporate net, offshore and total), the tax losses it causes in other countries and their share, the share of
    the profit shifted into it that its own multinationals book at home, and the comparisons with each amount of keys
    (columns of amounts): the share of the item the total loss would cover, the share the corporate loss alone would
    cover and the amount of the whole item. A country that gains has an empty loss cell and its gain in the next
    column. items holds the country budget items. The flags mark what the annex tables mark: no corporate income tax,
    a headquarters bias, an estimate with the country's own statistics, a country that both loses on net and causes
    losses, and an estimate that rests on few observations. They also say whether the country is a tax haven and
    whether it has a corporate and an offshore estimate. The column _den is for the totals."""
    t = losses
    net = corporate_net().reindex(t.index)
    caused, suffered = responsibility()
    hq = headquarters_share()
    off_has = offshore_available()
    continent = continents(t)
    thin = _data_coverage.thin_iso_set()
    rows = []
    for iso, r in t.iterrows():
        no_cit = iso in config.NO_CIT_JURISDICTIONS
        gain = -net[iso] if pd.notna(net[iso]) and net[iso] < 0 and not no_cit else np.nan
        corp = r["corp_loss_musd"] if r["corp_estimate_available"] and pd.isna(gain) and not no_cit else np.nan
        ind = r["offshore_wealth_loss_musd"] if iso in off_has else np.nan
        tot = np.nansum([corp, ind]) if pd.notna(corp) or pd.notna(ind) else np.nan
        resp = caused.get(iso, np.nan)
        den = {k: amounts.at[iso, k] for k in keys}
        share = lambda v: tot / v if pd.notna(v) and v > 0 and pd.notna(tot) and tot > 0 else np.nan  # noqa: E731
        share_c = lambda v: corp / v if pd.notna(v) and v > 0 and pd.notna(corp) and corp > 0 else np.nan  # noqa: E731
        d = {"country": r["country"], "iso": iso, "cont": continent[iso], "income_group": r["wb_income_group"],
             "corp": corp, "gain": gain, "ind": ind, "tot": tot, "resp": resp, "resp_pct": resp / suffered,
             "resp_hq": hq.get(iso, np.nan) if pd.notna(resp) else np.nan, "youth_n": amounts.at[iso, "youth_n"]}
        for k, v in den.items():                    # the shares covered, then the US$ amount of the whole item
            d[k], d[f"{k}_c"], d[f"{k}_usd"] = share(v), share_c(v), v if pd.notna(v) and v > 0 else np.nan
        if iso in items:
            d.update(items[iso])
            d["c_share"] = share(items[iso]["c_usd"])
        d.update(tax_haven=iso in config.TAX_HAVENS_REPRESENTATION, no_cit=no_cit,
                 corp_estimate=bool(r["corp_estimate_available"]), offshore_estimate=iso in off_has,
                 hq_bias=headquarters_bias(iso, d["resp_hq"]), own_stats=iso in OWN_STATS,
                 suffers_and_causes=bool(pd.notna(resp) and pd.notna(corp) and corp > 0),
                 few_obs=iso in thin and bool(r["corp_estimate_available"]), _den=den)
        rows.append(d)
    T = pd.DataFrame(rows).sort_values("country", key=lambda c: c.str.normalize("NFKD"), ignore_index=True)
    return T, suffered


def measure_rows(group, losers, gains, off, amounts, youth_n, sf, extra=None):
    """Return the four rows of a group: its net gain from unitary taxation (measure "net") and its losing countries'
    losses alone (measure "losers"), each scaled to all multinationals and unscaled. losers, gains and off are the
    unscaled sums over the group. amounts maps each comparison to (amount, losers, gains, offshore), the last three
    summed over the countries with the item. extra adds columns, of which "resp" is scaled like the corporate figures.
    I leave a comparison empty where its numerator is not positive, as for a group that gains from profit shifting on
    balance."""
    extra = extra or {}
    rows = []
    for measure in ("net", "losers"):
        for is_scaled in (True, False):
            f = sf if is_scaled else 1.0
            corp = (losers - gains) * f if measure == "net" else losers * f
            tot = corp + off
            r = {"group": group, "measure": measure, "scaled": is_scaled, "sf": f, "losers": losers * f, "gains": gains * f,
                 "net": (losers - gains) * f, "corp": corp, "ind": off, "tot": tot, "youth_n": youth_n,
                 **{k: (v * f if k == "resp" else v) for k, v in extra.items()}}
            for k, (amt, lo, ga, of) in amounts.items():
                c = (lo - ga) * f if measure == "net" else lo * f
                ok = pd.notna(amt) and amt > 0
                r[k] = (c + of) / amt if ok and c + of > 0 else np.nan
                r[f"{k}_c"] = c / amt if ok and c > 0 else np.nan
                r[f"{k}_amt"] = amt if ok else np.nan
            rows.append(r)
    return rows


def group_mask(T, group, group_type):
    """Return which country rows belong to a group of the totals: the world, a continent or an income group."""
    if group_type == "income_group":
        return T["income_group"] == group
    return (T["cont"] == group) | (group_type == "world")


def total_rows(T, keys, sf, suffered):
    """Return the total rows: the world, each continent and each income group, four rows each (measure_rows). The
    income groups are those of the chapter: the World Bank groups without the tax havens, which form a group of their
    own. The total rows sum the losses only, with the gains and the losses caused summed in their own columns, and
    compare like for like over the countries with data."""
    def group_rows(group, group_type):
        """Return the four rows of the world, a continent or an income group."""
        inc = T[group_mask(T, group, group_type)]
        losers, gains, off = inc["corp"].sum(), inc["gain"].sum(), inc["ind"].sum()   # gainers' empty cells count as zero
        amounts = {}
        for k in keys:
            den = inc["_den"].map(lambda x: x[k])
            m = den.notna() & (den > 0)       # a comparison covers the countries that have the item
            amounts[k] = ((den[m].sum(), inc.loc[m, "corp"].sum(), inc.loc[m, "gain"].sum(), inc.loc[m, "ind"].sum())
                          if m.any() else (np.nan, 0.0, 0.0, 0.0))
        extra = {"group_type": group_type, "n_countries": len(inc), "n_losing": int((inc["corp"] > 0).sum()),
                 "n_gaining": int((inc["gain"] > 0).sum()), "resp": inc["resp"].sum(),
                 "resp_pct": inc["resp"].sum() / suffered}
        return measure_rows(group, losers, gains, off, amounts, inc["youth_n"].sum(), sf, extra)

    groups = ([(WORLD, "world")] + [(c, "continent") for c in sorted(T["cont"].unique())]
              + [(g, "income_group") for g in INCOME_GROUPS])
    return pd.DataFrame([r for g, gt in groups for r in group_rows(g, gt)])


def world_table(losses, amounts, items, keys=COMPARE):
    """Return the country rows (country_rows), the total rows (total_rows) and the scale factor. The losses caused
    add up to the losses suffered in the world row."""
    T, suffered = country_rows(losses, amounts, items, keys)
    sf = scale_factor_2023()
    TOT = total_rows(T, keys, sf, suffered)
    world = TOT[(TOT["group"] == WORLD) & (TOT["measure"] == "losers")].iloc[0]
    assert abs(world["resp"] - world["corp"]) < 1e-6 * world["corp"], (world["resp"], world["corp"])
    return T.drop(columns=["_den"]), TOT, sf


# %% MARK: 8. The tables
# The names of the comparisons in the tables
COMPARE_NAMES = {"health": "health_spending", "train": "job_training", "wage": "average_wage"}
ITEM_COLUMNS = {"c_desc": "budget_item", "c_cur": "budget_item_currency", "c_local": "budget_item_cost_local_m",
                "c_fx": "budget_item_fx_local_per_usd", "c_usd": "budget_item_cost_usd_m", "c_share": "budget_item_share",
                "c_src": "budget_item_source", "c_origin": "budget_item_origin"}
FLAG_COLUMNS = {"corp_estimate": "corporate_estimate", "offshore_estimate": "offshore_estimate", "no_cit": "no_cit",
                "hq_bias": "headquarters_bias", "own_stats": "own_statistics_estimate",
                "suffers_and_causes": "suffers_and_causes", "few_obs": "few_observations"}


def country_table(T):
    """Return the country table. The change in tax revenue under unitary taxation is what a country would collect in
    addition: a losing country its loss, a gaining country minus its gain. Each comparison gives the share of the item
    that the total loss, the corporate loss alone and the change in tax revenue would cover."""
    ut = (T["corp"].fillna(0) - T["gain"].fillna(0)).where(T["corp"].notna() | T["gain"].notna())
    out = pd.DataFrame({"iso3": T["iso"], "country": T["country"], "continent": T["cont"],
                        "income_group": T["income_group"], "tax_haven": T["tax_haven"],
                        "corporate_loss_usd_m": T["corp"], "gain_usd_m": T["gain"], "offshore_loss_usd_m": T["ind"],
                        "total_loss_usd_m": T["tot"], "ut_change_usd_m": ut, "losses_caused_usd_m": T["resp"],
                        "losses_caused_share": T["resp_pct"], "own_groups_share": T["resp_hq"]})
    for k, name in COMPARE_NAMES.items():
        out[f"{name}_usd_m"] = T[f"{k}_usd"]
        out[f"{name}_share_total"] = T[k]
        out[f"{name}_share_corporate"] = T[f"{k}_c"]
        out[f"{name}_share_ut"] = ut / T[f"{k}_usd"]
    for k, name in ITEM_COLUMNS.items():
        out[name] = T[k]
    for k, name in FLAG_COLUMNS.items():
        out[name] = T[k]
    return out


def totals_table(TOT):
    """Return the totals table. The measure "net" is the group's net gain from unitary taxation (its losing countries'
    losses minus its gaining countries' gains), the measure "losers" the losses of its losing countries alone. The
    scaled rows multiply the corporate figures and the losses caused by the scale factor. The offshore loss is not
    scaled."""
    out = pd.DataFrame({"group": TOT["group"], "group_type": TOT["group_type"], "measure": TOT["measure"],
                        "scaled": TOT["scaled"], "scale_factor": TOT["sf"], "n_countries": TOT["n_countries"],
                        "n_losing": TOT["n_losing"], "n_gaining": TOT["n_gaining"], "losers_usd_m": TOT["losers"],
                        "gains_usd_m": TOT["gains"], "net_usd_m": TOT["net"], "corporate_usd_m": TOT["corp"],
                        "offshore_loss_usd_m": TOT["ind"], "total_usd_m": TOT["tot"], "losses_caused_usd_m": TOT["resp"],
                        "losses_caused_share": TOT["resp_pct"]})
    for k, name in COMPARE_NAMES.items():
        out[f"{name}_usd_m"] = TOT[f"{k}_amt"]
        out[f"{name}_share_total"] = TOT[k]
        out[f"{name}_share_corporate"] = TOT[f"{k}_c"]
    return out


# %% MARK: 9. Run
def main():
    TABLES.mkdir(parents=True, exist_ok=True)
    losses = load_losses()
    youth = youth_inputs(losses)
    tr, n_c, _ = lmp_cost_ratio("LMP_20")       # a year of job training: cost relative to GDP per head, OECD median
    ein = europe_youth(COUNTRIES, youth)
    amounts = comparison_amounts(losses, youth, ein, tr)
    items = world_country_specific(list(losses.index), continents(losses), africa_items(), europe_items())
    own_statistics()
    T, TOT, sf = world_table(losses, amounts, items)
    country_table(T).to_csv(COUNTRIES_CSV, index=False)
    totals_table(TOT).to_csv(TOTALS_CSV, index=False)
    pd.DataFrame([("job_training_cost_per_gdp_per_head", tr), ("job_training_cost_countries", n_c),
                  ("scale_factor", sf)], columns=["parameter", "value"]).to_csv(PARAMETERS_CSV, index=False)
    print(f"annex tables: {len(T)} countries, {int(T['c_desc'].notna().sum())} budget items → {rel(COUNTRIES_CSV)}, "
          f"{rel(TOTALS_CSV)}, {rel(PARAMETERS_CSV)}; Japan and Canada with their own statistics → {rel(OWN_STATS_CSV)}")
    print(TOT[["group", "measure", "scaled", "losers", "gains", "net", "corp", "tot", "resp"]].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
