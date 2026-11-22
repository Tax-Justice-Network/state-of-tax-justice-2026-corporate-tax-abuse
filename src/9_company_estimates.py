# %%
"""
9 — Company estimates from public country-by-country reports.

This script applies unitary taxation to each multinational group's own public country-by-country report and produces
every company result of chapter 3 of The State of Tax Justice 2026.

Unitary taxation per group (sections 2–4). The panel of src/firm_level/f1 holds one row per group, fiscal year and
jurisdiction. For every group-year, I apportion the group's worldwide profit across its reported jurisdictions, half
by employees and half by revenues. The revenues are sales by origin: unrelated-party revenues where every line of the
report gives them, else total revenues. Misaligned profit is the reported minus the apportioned profit. I price the
profit a jurisdiction would lose at the tax rate that the group's own report implies there (current-year tax ÷ profit,
the cash tax where the accrued tax is missing, clipped to [0, 1]), so the tax lost never exceeds the tax the group pays
on that profit. I price the profit a jurisdiction would gain at its statutory corporate income tax (CIT) rate. Besides
the exchange rates (and, in the second specification, consolidated revenue), this rate is the one number taken from
outside the reports. There are two specifications:
  * sales_employees_anyrev_reportonly — the revenues exactly as the reports give them.
  * sales_employees_anyrev_report — total revenues include sales to other group companies, so a report's lines add
    up to more than the group's revenue (Microsoft FY2025: US$521.7bn against US$281.7bn). I take the surplus off
    the lines where intra-group sales are booked (the home line, the residual "Other" line and booking hubs), using
    the consolidated revenue found by src/firm_level/f1b (correct_intragroup_revenue). This is the estimate the
    chapter uses.
Sample: a group-year enters where every line reports profit and both factors and the report names at least two
jurisdictions (single-jurisdiction and aggregate-only filings carry no worldwide table). A report's residual "Other"
line (OTHER) stays in the apportionment pool with its own factors. It has no statutory rate, so I price both of its
legs at its own implied rate (else the group's). There is no resource correction. The chapter's public-report
estimates leave out banks, insurers and oil, gas and mining groups because of the peculiarities of their sectors.
Years outside 2016–2023 take the statutory rates of the nearest year.

Results of the chapter (sections 5–11):
  * Figure 3.1: the share of their EU profit that the chapter's companies book in one hub, and the tax rate there.
  * Figure 3.2: profit per employee by country of the same companies, as single figures and as one image.
  * Figure 3.3: the tax rate groups pay where they book too much and too little profit (latest report of 2023–2025),
    as weighted averages with 95% confidence intervals from resampling the companies, the EU countries without the tax
    havens first. Banks and insurers are included because the rates compare tax with profit. Extractive groups are left
    out because they pay special resource taxes.
  * Table 3.1: EU countries, the country-level estimate of 2023 against the public reports of 2025, scaled up by the
    share of the country's multinational activity they cover.
  * The averages across all groups that put the company examples in context, and the distribution of EU profit by tax
    rate in the five EU hubs and the other EU countries.
  * The sample counts of the chapter and of the methodology note.
  * The company numbers quoted in the chapter text, its notes and the methodology note.

Section outline (numbers match the cell headings below):
1. Setup.
2. Partner-year inputs (statutory rates, income groups, regions).
3. Apportionment, intra-group sales and pricing.
4. Group-by-group estimates (the two specifications).
5. Figure 3.1: the share of their EU profit companies book in one hub, and the tax rate there.
6. Figure 3.2: profit per employee by country of the companies of Figure 3.1.
7. Figure 3.3: tax rates where groups book too much and too little profit.
8. Table 3.1: EU countries, country-level estimate and public reports.
9. Averages across all groups.
10. Sample counts.
11. Company numbers quoted in the chapter text and the methodology note.
12. Run.

Pipeline step 9 — after 8 and firm_level f1/f1b, before 10.

Reads:
  data/intermediate/firm_level/firm_cbcr_panel.csv                — f1: the public reports, one row per line
  data/intermediate/firm_level/firm_year_meta.csv                 — f1: one row per report (share of revenue in the
                                                                    line for the rest of the world)
  data/intermediate/firm_level/firm_consolidated_revenue.csv      — f1b: consolidated revenue per group-year
  data/intermediate/firm_level/firm_line_third_party_revenue.csv  — f1b: documented sales to customers of single lines
  data/raw/macro_variables/wb_gdp_current_usd_2026-08.csv         — world GDP shares (booking-hub screen)
  data/final/cbcr_main_excl_resource.csv                          — statutory CIT, income groups, regions and the OECD
                                                                    universe of multinationals per country (Table 3.1)
  data/final/cbcr_main.csv                                        — GDP of the EU countries (rows of Table 3.1)
  output/estimates/reported_only/2_resources_excluded/tables/excl_resource/
      country_estimates__sales_employees_destmnedds__etrdef_domfor__etrmax_inf__loss_cit_gain_etr.csv — headline estimate
  output/paper/main_text/tables/host_scale_factors.csv            — 7a: the world scale factor (Table 3.1)
  data/raw/firm_level/pcbcr_ireland_fy25_{apple,microsoft}.csv    — Apple's and Microsoft's Irish filings, FY2025
  data/raw/chapter_inputs/company_report_facts.csv                — a fact from a company document quoted in the text
Writes:
  output/analysis/firm_level/tables/
      firm_cell_misalignment__<spec>.csv          — one row per group × year × jurisdiction (both specifications)
      firm_year_summary__<spec>.csv               — one row per group × year
  output/chapter/figures/
      EU_profit_booked_in_the_hub.png|pdf (Figure 3.1)
      <Company>_profit_per_employee.png|pdf (Figure 3.2, one for each of its companies)
      profit_per_employee_companies.png|pdf       — Figure 3.2 as one image
      figC8c_pcbcr_rates_too_much_too_little.png|pdf (Figure 3.3)
  output/chapter/tables/
      EU_profit_booked_in_the_hub.csv, <Company>_profit_per_employee.csv
      pcbcr_rates_too_much_too_little.csv          — Figure 3.3: excess profit and rates by group of jurisdictions
      pcbcr_rates_too_much_too_little_eu.csv       — Figure 3.3: the weighted rates of the four samples and two tax concepts
      pcbcr_rates_too_much_too_little_eu_ci.csv    — Figure 3.3: the averages with their 95% confidence intervals
      europe_ut_pcbcr_scaled.csv                   — European countries: headline estimate and public reports (both
                                                     specifications, unscaled and scaled, coverage)
      table1_eu_estimates_vs_public_reports.csv    — Table 3.1 of the chapter (€ bn)
      table1_comparison_stats.csv                  — coverage range and agreement of Table 3.1's two columns
      company_averages.csv                         — the averages across all groups
      eu_profit_by_tax_rate.csv                    — EU profit by tax-rate band, five hubs and other EU countries
      company_numbers_in_text.csv                  — the company numbers of the chapter text and the methodology note,
                                                     with the sample counts
Usage:
  python src/9_company_estimates.py   — from the repository root

Author: Tax Justice Network.
Created: 2026-11-02.  Last updated: 2026-11-23.
"""
# %% MARK: 1. Setup
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pycountry

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import config  # noqa: E402
from config import TAX_HAVENS_REPRESENTATION, canonical_gdp_data, deflator_to_base  # noqa: E402
from _brand import INK, apply_tjn_style  # noqa: E402
from _sotj_palette import GAIN, PURPLE, tint  # noqa: E402
from _host_coverage import load_factors  # noqa: E402

apply_tjn_style()

# ---- inputs ----
PANEL = ROOT / "data/intermediate/firm_level/firm_cbcr_panel.csv"
META = ROOT / "data/intermediate/firm_level/firm_year_meta.csv"
CONSOLIDATED = ROOT / "data/intermediate/firm_level/firm_consolidated_revenue.csv"
LINE_DOCS = ROOT / "data/intermediate/firm_level/firm_line_third_party_revenue.csv"
EXCL_RESOURCE = ROOT / "data/final/cbcr_main_excl_resource.csv"
OECD_TABLES = config.estimates_dir("reported_only", "excl_resource") / "tables" / "excl_resource"
OECD_HEADLINE = OECD_TABLES / "country_estimates__sales_employees_destmnedds__etrdef_domfor__etrmax_inf__loss_cit_gain_etr.csv"
IRISH_FILINGS = str(ROOT / "data/raw/firm_level/pcbcr_ireland_fy25_{}.csv")    # Apple and Microsoft, FY2025
INPUTS = ROOT / "data/raw/chapter_inputs"

# ---- outputs ----
FIRM_TABLES = ROOT / "output/analysis/firm_level/tables"
CHAPTER_FIGS = ROOT / "output/chapter/figures"
CHAPTER_TABLES = ROOT / "output/chapter/tables"

# ---- specifications and samples ----
SPEC_REPORT = "sales_employees_anyrev_report"          # revenues measured against consolidated revenue (headline)
SPEC_REPORTONLY = "sales_employees_anyrev_reportonly"  # revenues as the reports give them
SPECS = {SPEC_REPORT: "sales_any_revenue", SPEC_REPORTONLY: "sales_revenue_reported"}   # specification: sales column
HEADLINE = SPEC_REPORT
WEIGHTS = [0.5, 0.5, 0.0, 0.0]          # employees, sales, tangible assets, payroll (the order of script 5)
HUB_GDP_MULT = 3.0                      # a line is a booking hub if its revenue exceeds 3 × consolidated revenue ×
                                        # the country's share of world GDP (Ireland for Microsoft, Belgium for Toyota)
HAVENS = set(TAX_HAVENS_REPRESENTATION)
RECENT_YEARS = [2023, 2024, 2025]       # the years in which public country-by-country reports are dense
EXTRACTIVE_SECTORS = {"Oil, Gas and Mining", "Oil, Gas and Mining / Utilities", "Mining", "Oil & Gas"}
FINANCIAL_SECTORS = {"Banking", "Banking, Insurance & Financial Services", "Insurance / Financial Services"}
LOW = 0.15                              # low-tax threshold for the rates of Figure 3.3
EU27 = ["AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA",
        "LTU", "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE"]
EU = set(EU27)
EU_HUBS = {"IRL", "LUX", "NLD", "MLT", "CYP"}       # the five EU hubs of the averages
Y_OECD, Y_FIRM = config.last_year, 2025              # Table 3.1: country-level estimate 2023, public reports 2025
EUR_PER_USD = 0.885                                  # 2025 average (ECB: US$1.12998 per euro), as in Table 3.1's note
LOW_COVERAGE = 0.03                                  # flag coverage below this share of activity


def wavg(x, w):
    """Return the weighted mean over the rows where both value and weight are given."""
    m = x.notna() & w.notna()
    return float((x[m] * w[m]).sum() / w[m].sum()) if w[m].sum() > 0 else np.nan


# %% MARK: 2. Partner-year inputs (statutory rates, income groups, regions)
def nearest_year_map(df, keys, year_col="year"):
    """Extend a partner-year table to every year of the panel by taking the nearest available year per partner. The
    years 2024–2026 take 2023, the years 2012–2015 take 2016."""
    years = sorted(df[year_col].unique())
    out = []
    for y in range(2012, 2027):
        src = min(years, key=lambda v: abs(v - y))
        d = df[df[year_col] == src].copy()
        d[year_col] = y
        out.append(d)
    return pd.concat(out, ignore_index=True).drop_duplicates(keys + [year_col])


def load_partner_year():
    ex = pd.read_csv(EXCL_RESOURCE, low_memory=False, usecols=["iso_partner", "year", "cit", "wb_income_group", "region_tjn"])
    ex = ex.drop_duplicates(["iso_partner", "year"])
    ex["cit"] = pd.to_numeric(ex["cit"], errors="coerce")
    return nearest_year_map(ex, ["iso_partner"])


# %% MARK: 3. Apportionment, intra-group sales and pricing
def apportion(df, weights, sales_col):
    """Apportion the profit within each (company_key, year), as in script 5. The activity share is Σ weight × factor
    share. The theoretical profit is share × Σ profit when the group's pool is positive, else the theoretical profit
    equals the reported profit (misalignment 0)."""
    g = ["company_key", "year"]
    vars_ = ["n_employees", sales_col, "tangible_assets_except_cash", "payroll"]
    act = pd.Series(0.0, index=df.index)
    for var, wgt in zip(vars_, weights):
        if wgt <= 0:
            continue
        v = pd.to_numeric(df[var], errors="coerce").clip(lower=0)
        tot = v.groupby([df[c] for c in g]).transform("sum")
        act = act + wgt * np.where(tot > 0, v / tot, 0.0)
    tot_act = act.groupby([df[c] for c in g]).transform("sum")
    share = np.where(tot_act > 0, act / tot_act, 0.0)
    pool = df["profit_loss_before_income_tax"].groupby([df[c] for c in g]).transform("sum")
    theo = np.where(pool > 0, share * pool, df["profit_loss_before_income_tax"])
    return share, theo, pool


def correct_intragroup_revenue(df):
    """Measure the sales factor of a total-revenue report against the group's consolidated revenue R (f1b).

    Total revenues include sales to other group companies, so a report's lines add up to more than R. I take the surplus
    D = Σ lines − R off the lines where intra-group sales are booked. These are the home line, the report's OTHER
    residual and the booking hubs, that is, lines whose revenue exceeds HUB_GDP_MULT × R × the country's share of world
    GDP (a line without GDP data counts as a hub). I scale these lines down pro rata. Every other line keeps its revenue
    as sales to customers there, so its share of the sales factor is its revenue ÷ R (Microsoft Germany FY2025: 2.2% of
    the summed revenue, 4.1% of R). Where the annual report discloses a home line's sales to customers (LINE_DOCS), the
    line takes that figure when it is by location of the selling companies ("fixed"). When it is by customer location
    ("floor"), I never scale the line below it, because the group's home companies make most of its sales at home.
    Where the hub lines cannot absorb the surplus, I scale all other lines pro rata to R. Reports without an accepted
    R, and reports whose lines do not exceed R, keep their revenues. The function adds sales_revenue_reported,
    consolidated_revenue_usd, revenue_line_role and revenue_correction."""
    g = ["company_key", "year"]
    df["sales_revenue_reported"] = df["sales_any_revenue"]
    df["consolidated_revenue_usd"] = np.nan
    df["revenue_line_role"] = ""
    df["revenue_correction"] = np.where(df["sales_any_revenue_basis"].eq("total"), "none_no_consolidated", "none_basis")
    if not CONSOLIDATED.exists():
        print(f"  [warn] {CONSOLIDATED} not found (run src/firm_level/f1b_consolidated_revenue.py): "
              "revenues are not measured against consolidated revenue")
        return df
    cons = pd.read_csv(CONSOLIDATED)
    cons = cons[cons["chosen"].astype(bool)].drop_duplicates(g).set_index(g)["revenue_usd"]
    idx = pd.MultiIndex.from_frame(df[g])
    R = pd.Series(cons.reindex(idx).to_numpy(), index=df.index)
    gdp = pd.read_csv(canonical_gdp_data, comment="#").rename(columns={"iso3": "iso_partner"})
    gdp["gdp_share"] = gdp["gdp_current_usd"] / gdp.groupby("year")["gdp_current_usd"].transform("sum")
    gdp = nearest_year_map(gdp[["iso_partner", "year", "gdp_share"]], ["iso_partner"]).set_index(["iso_partner", "year"])
    share = pd.Series(gdp["gdp_share"].reindex(pd.MultiIndex.from_frame(df[["iso_partner", "year"]])).to_numpy(),
                      index=df.index).fillna(0.0)
    doc_val = pd.Series(np.nan, index=df.index)
    doc_kind = pd.Series("", index=df.index)
    if LINE_DOCS.exists():
        docs = pd.read_csv(LINE_DOCS).drop_duplicates(g + ["iso_partner"]).set_index(g + ["iso_partner"])
        li = pd.MultiIndex.from_frame(df[g + ["iso_partner"]])
        doc_val = pd.Series(docs["third_party_revenue_usd"].reindex(li).to_numpy(), index=df.index)
        doc_kind = pd.Series(docs["kind"].reindex(li).fillna("").to_numpy(), index=df.index)

    v = df["sales_any_revenue"].clip(lower=0)
    apply = df["sales_any_revenue_basis"].eq("total") & R.gt(0) & v.notna()
    home = df["iso_partner"].eq(df["hq_iso3"])
    other = df["iso_partner"].eq("OTHER")
    hub = apply & ~home & ~other & (v > HUB_GDP_MULT * R * share)
    grp = [df[c] for c in g]
    fixed = apply & doc_kind.eq("fixed") & doc_val.notna()
    fixed_val = doc_val.clip(upper=v).where(fixed)
    floor = doc_val.clip(upper=v).where(apply & doc_kind.eq("floor"))
    for _ in range(4):        # a floored line that scaling would push below its floor is fixed at the floor
        v0 = v.where(~fixed, fixed_val)
        H = apply & ~fixed & (home | other | hub)
        D = v0.where(apply, 0.0).groupby(grp).transform("sum") - R
        SH = v0.where(H, 0.0).groupby(grp).transform("sum")
        SF = v0.where(fixed, 0.0).groupby(grp).transform("sum")
        SN = v0.where(apply & ~fixed, 0.0).groupby(grp).transform("sum")
        surplus = apply & (D > 0)
        by_hubs = surplus & (SH >= D) & (SH > 0)
        pro_rata = surplus & ~by_hubs & (R > SF) & (SN > 0)
        new = v0.copy()
        new = new.where(~(by_hubs & H), v0 * (SH - D) / SH.where(SH > 0))
        new = new.where(~(pro_rata & ~fixed), v0 * (R - SF) / SN.where(SN > 0))
        below = ~fixed & floor.notna() & (new < floor - 1.0)
        if not below.any():
            break
        fixed, fixed_val = fixed | below, fixed_val.where(~below, floor)
    df["sales_any_revenue"] = new.where(apply, df["sales_any_revenue"])
    df["consolidated_revenue_usd"] = R.where(apply)
    df["revenue_line_role"] = np.select([~apply, fixed & home, fixed, home, other, hub],
                                        ["", "home (documented)", "documented", "home", "other", "hub"], "market")
    df["revenue_correction"] = np.select([~apply, ~surplus, by_hubs, pro_rata],
                                         [df["revenue_correction"], "none_no_surplus", "corrected", "pro_rata"], "none")
    gy = df[apply].drop_duplicates(g)
    print(f"  intra-group sales: {len(gy):,} total-revenue group-years with consolidated revenue "
          f"({gy['revenue_correction'].value_counts().to_dict()}); hub lines {int(hub.sum()):,}, "
          f"documented lines {int(fixed.sum()):,}")
    return df


def price_report(df, mis):
    """Return the revenue legs (US$). I price the profit a jurisdiction loses under unitary taxation (mis > 0) at the tax
    rate the group's report implies there (current-year tax ÷ profit, the cash tax where the accrued tax is missing,
    clipped to [0, 1]). I price the profit it gains (mis < 0) at its statutory CIT. The residual OTHER line has no
    statutory rate, so both of its legs take its own implied rate, else the group's. I use the accrued tax before the
    cash tax because, for example, Apple's 2025 Irish cash tax (US$17.1bn against 4.8bn accrued) includes the EU
    state-aid recovery, a prior-year settlement."""
    p = df["profit_loss_before_income_tax"]
    t = df["income_tax_accrued_current_year"].fillna(df["income_tax_paid_on_cash_basis"])
    implied = pd.Series(np.where(p > 0, (t / p).clip(0, 1), np.nan), index=df.index)
    gk = [df[c] for c in ["company_key", "year"]]
    g_rate = (t.where(p > 0).groupby(gk).transform("sum") / p.clip(lower=0).groupby(gk).transform("sum").replace(0, np.nan)).clip(0, 1)
    lose_rate = implied.fillna(g_rate).fillna(0.0)
    other = df["iso_partner"] == "OTHER"
    gain_rate = df["cit"].where(~other, lose_rate).fillna(lose_rate)
    loss = np.where(mis < 0, -mis, 0.0) * gain_rate     # revenue the jurisdiction would gain
    gain = np.where(mis > 0, mis, 0.0) * lose_rate      # revenue the jurisdiction would forgo
    return pd.Series(loss, index=df.index), pd.Series(gain, index=df.index), lose_rate, gain_rate


# %% MARK: 4. Group-by-group estimates (the two specifications)
CELL_COLS = ["formula", "source", "company", "company_key", "hq_iso3", "sector", "is_extractive", "year",
             "iso_partner", "jurisdiction_name", "wb_income_group", "region_tjn", "is_haven",
             "n_employees", "unrelated_party_revenues", "tangible_assets_except_cash",
             "sales_any_revenue", "sales_any_revenue_basis", "total_revenues",
             "sales_revenue_reported", "consolidated_revenue_usd", "revenue_line_role", "revenue_correction",
             "profit_loss_before_income_tax", "income_tax_paid_on_cash_basis",
             "group_profit", "share_economy", "theoretical_profit", "misaligned_profit",
             "cit", "etr_cash_cell", "etr_accrued_cell",
             "gain_rate_applied", "loss_rate_applied", "tax_revenue_loss_usd", "tax_revenue_gain_usd",
             "revenue_gain_from_ut_usd", "deflator"]


def group_year_summary(d, name):
    """Return one row per group-year with the misalignment share and the home and hub shares of profit (reported and
    apportioned)."""
    g = ["company_key", "year"]
    home = d["iso_partner"] == d["hq_iso3"]
    s = (d.assign(_pos_mis=d["misaligned_profit"].clip(lower=0), _pos_profit=d["profit_loss_before_income_tax"].clip(lower=0),
                  _home_rep=np.where(home, d["profit_loss_before_income_tax"], 0.0),
                  _home_theo=np.where(home, d["theoretical_profit"], 0.0),
                  _hav_rep=np.where(d["is_haven"], d["profit_loss_before_income_tax"], 0.0),
                  _hav_theo=np.where(d["is_haven"], d["theoretical_profit"], 0.0),
                  _hav_emp=np.where(d["is_haven"], d["n_employees"], 0.0),
                  _other_rep=np.where(d["iso_partner"] == "OTHER", d["profit_loss_before_income_tax"], 0.0),
                  _home_rev=np.where(home, d["revenue_gain_from_ut_usd"], 0.0),
                  _hav_rev=np.where(d["is_haven"], d["revenue_gain_from_ut_usd"], 0.0))
         .groupby(g, as_index=False)
         .agg(company=("company", "first"), source=("source", "first"), hq_iso3=("hq_iso3", "first"),
              sector=("sector", "first"), is_extractive=("is_extractive", "first"),
              n_jurisdictions=("iso_partner", "nunique"), group_profit=("group_profit", "first"),
              positive_profit=("_pos_profit", "sum"), gross_positive_misalignment=("_pos_mis", "sum"),
              n_employees=("n_employees", "sum"), haven_employees=("_hav_emp", "sum"),
              home_profit_reported=("_home_rep", "sum"), home_profit_apportioned=("_home_theo", "sum"),
              haven_profit_reported=("_hav_rep", "sum"), haven_profit_apportioned=("_hav_theo", "sum"),
              other_profit_reported=("_other_rep", "sum"),
              home_revenue_change_usd=("_home_rev", "sum"), haven_revenue_change_usd=("_hav_rev", "sum"),
              world_gainers_usd=("tax_revenue_loss_usd", "sum"), world_losers_usd=("tax_revenue_gain_usd", "sum"),
              cash_tax_usd=("income_tax_paid_on_cash_basis", "sum")))
    s["misalignment_share_of_profit"] = np.where(s["group_profit"] > 0, s["gross_positive_misalignment"] / s["group_profit"], np.nan)
    s["misalignment_share_of_positive_profit"] = np.where(s["positive_profit"] > 0, s["gross_positive_misalignment"] / s["positive_profit"], np.nan)
    for k in ["home", "haven"]:
        s[f"{k}_share_reported"] = np.where(s["group_profit"] > 0, s[f"{k}_profit_reported"] / s["group_profit"], np.nan)
        s[f"{k}_share_apportioned"] = np.where(s["group_profit"] > 0, s[f"{k}_profit_apportioned"] / s["group_profit"], np.nan)
    s["haven_share_employees"] = np.where(s["n_employees"] > 0, s["haven_employees"] / s["n_employees"], np.nan)
    s["formula"] = name
    return s


def estimate(panel):
    """Run both specifications group by group and return, per specification, the cell frame (with every panel column)
    and the group-year summary. The function writes nothing."""
    df = panel.merge(load_partner_year(), on=["iso_partner", "year"], how="left")
    g = ["company_key", "year"]
    df["is_haven"] = df["iso_partner"].isin(HAVENS)
    df["is_extractive"] = df["sector"].isin(EXTRACTIVE_SECTORS)
    # ---- sample rules: profit on every line, a headquarters country and at least two named jurisdictions ----
    # Single-jurisdiction and aggregate-only filings, for example a Romania-only local filing of a US parent, carry no
    # worldwide table.
    gk = [df[c] for c in g]
    profit_missing = df["profit_loss_before_income_tax"].isna().groupby(gk).transform("any")
    n_real = (df["iso_partner"] != "OTHER").groupby(gk).transform("sum")
    base_ok = (~profit_missing) & df["hq_iso3"].notna() & (n_real >= 2)
    # ---- the rates each line implies (tax ÷ profit where profit > 0, clipped to [0, 1]) ----
    p = df["profit_loss_before_income_tax"]
    df["etr_cash_cell"] = np.where(p > 0, (df["income_tax_paid_on_cash_basis"] / p).clip(0, 1), np.nan)
    df["etr_accrued_cell"] = np.where(p > 0, (df["income_tax_accrued_current_year"] / p).clip(0, 1), np.nan)
    deflate = deflator_to_base()
    # ---- sales by origin: unrelated-party revenues where every line reports them, else total revenues ----
    # I use total revenues where every line reports those. Most reports under the EU directive give turnover only.
    gk = [df[c] for c in g]
    upr_ok = df["unrelated_party_revenues"].notna().groupby(gk).transform("all")
    tot_ok = df["total_revenues"].notna().groupby(gk).transform("all")
    df["sales_any_revenue"] = np.where(upr_ok, df["unrelated_party_revenues"], np.where(tot_ok, df["total_revenues"], np.nan))
    df["sales_any_revenue_basis"] = np.where(upr_ok, "unrelated", np.where(tot_ok, "total", ""))
    df = correct_intragroup_revenue(df)

    cells, summaries = {}, {}
    for name, sales_col in SPECS.items():
        need = ["n_employees", sales_col]
        d = df.copy()
        missing = d[need].isna().any(axis=1)
        d["_factor_missing"] = missing.groupby([d[c] for c in g]).transform("any")
        d = d[base_ok.reindex(d.index) & (~d["_factor_missing"])].copy()
        share, theo, pool = apportion(d, WEIGHTS, sales_col)
        d["share_economy"] = share
        d["theoretical_profit"] = theo
        d["group_profit"] = pool
        d["misaligned_profit"] = d["profit_loss_before_income_tax"] - d["theoretical_profit"]
        loss, gain, lose_rate, gain_rate = price_report(d, d["misaligned_profit"])
        d["gain_rate_applied"] = np.where(d["misaligned_profit"] < 0, gain_rate, np.nan)
        d["loss_rate_applied"] = np.where(d["misaligned_profit"] > 0, lose_rate, np.nan)
        d["tax_revenue_loss_usd"] = loss           # what the country gains under unitary taxation (its current loss)
        d["tax_revenue_gain_usd"] = gain           # what the country forgoes under unitary taxation (its current gain)
        d["revenue_gain_from_ut_usd"] = loss - gain
        d["deflator"] = d["year"].map(deflate)
        d["formula"] = name
        cells[name] = d
        s = group_year_summary(d, name)
        summaries[name] = s
        print(f"  {name:38s} group-years {s.shape[0]:5d}  groups {s['company_key'].nunique():4d}  "
              f"median misaligned share {s['misalignment_share_of_profit'].median():.1%}")
    return cells, summaries


def run_estimates(panel):
    """Write the cell tables and the group-year summaries of both specifications to output/analysis/firm_level/tables/
    and return the cell frames in memory (with every panel column)."""
    FIRM_TABLES.mkdir(parents=True, exist_ok=True)
    cells, summaries = estimate(panel)
    for name in SPECS:
        cells[name][CELL_COLS].to_csv(FIRM_TABLES / f"firm_cell_misalignment__{name}.csv", index=False)
        summaries[name].to_csv(FIRM_TABLES / f"firm_year_summary__{name}.csv", index=False)
    return cells


# %% MARK: 5. Figure 3.1: the share of their EU profit companies book in one hub, and the tax rate there
def rate_label(pct, decimals):
    """A tax rate in per cent with the given number of decimals, or with more where rounding would show a rate below
    the 15% minimum as 15, so that a rate below the minimum never reads as the minimum itself."""
    d = decimals
    while pct < 15 and round(pct, d) >= 15 and d < 3:
        d += 1
    return f"{pct:.{d}f}"


# EU profit is the profit before tax summed over the EU-27 lines of the company's latest report (the EU directive
# lists every member state separately). I take the share of the net EU profit. Where the other EU lines net to a
# loss, the hub books more than the whole EU profit, and the ring is full with ">100%" in the centre (the exact share
# is in the CSV). Under each donut, the figure gives the hub, the EU profit, the hub's share of the group's EU
# employees and the tax rate there. The rate is the income tax accrued for the year ÷ profit before tax. Where a
# report gives no accrued tax, or zero accrued tax against a positive payment, I use the tax paid and mark it "paid".
HUB_NAMES = {"IRL": "Ireland", "LUX": "Luxembourg", "NLD": "the Netherlands", "MLT": "Malta"}
# Name shown: (source, key in the source, hub shown). The companies are the chapter's examples: first those of the
# chapter introduction and IKEA stores (Ingka), then the further examples. Each company is named by its best-known brand, with its group in brackets where the two differ. For Primark this is Associated
# British Foods, which owns it. The report is filed by ABF's parent Wittington Investments and covers the whole group.
# Ingka runs most IKEA stores as the largest franchisee.
DONUT_INTRO = {
    "Apple": ("cro", "apple", "IRL"),
    "Microsoft": ("cro", "microsoft", "IRL"),
    "Kraft Heinz": ("panel", "KRAFT HEINZ", "NLD"),
    "IKEA stores (Ingka)": ("panel", "INGKA", "IRL"),
}
DONUT_FURTHER = {
    "Primark (Associated British Foods)": ("panel", "WITTINGTON INVESTMENTS", "IRL"),
    "Jameson (Pernod Ricard)": ("panel", "PERNOD RICARD", "IRL"),
    "Adobe": ("panel", "ADOBE", "IRL"),
    "TE Connectivity": ("panel", "TE CONNECTIVITY", "LUX"),
    "Western Digital": ("panel", "WESTERN DIGITAL", "IRL"),
    "PTC": ("panel", "PTC", "IRL"),
}
DONUT_CHAPTER = {**DONUT_INTRO, **DONUT_FURTHER}


def eu_lines(panel, src, key):
    """Return the EU-27 lines of the company's latest report (profit before tax, tax accrued, tax paid and employees,
    amounts in US$) and its fiscal year. Apple and Microsoft come from their Irish filings, the other companies from
    the panel."""
    if src == "cro":
        d = pd.read_csv(IRISH_FILINGS.format(key))
        d["iso3"] = [getattr(pycountry.countries.get(alpha_2=c), "alpha_3", None) if isinstance(c, str) else None for c in d["code"]]
        d = d.rename(columns={"pbt": "profit", "tax_accrued": "accrued", "tax_paid": "paid"})
        fy = 2025
    else:
        d = panel[(panel["company"] == key) | (panel["company_key"] == key)]   # display names can change, keys do not
        fy = int(d["year"].max())
        d = d[d["year"] == fy].rename(columns={"iso_partner": "iso3", "profit_loss_before_income_tax": "profit",
                                               "income_tax_accrued_current_year": "accrued",
                                               "income_tax_paid_on_cash_basis": "paid", "n_employees": "employees"})
    cols = ["profit", "accrued", "paid", "employees"]
    for c in cols:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    e = d.loc[d["iso3"].isin(EU), ["iso3", *cols]].groupby("iso3")[cols].sum(min_count=1)
    return e, fy


def hub_table(panel, companies):
    rows = []
    for name, (src, key, hub) in companies.items():
        e, fy = eu_lines(panel, src, key)
        h = e.loc[hub] if hub in e.index else pd.Series(dict(profit=0.0, accrued=np.nan, paid=np.nan, employees=0.0))
        eu_profit = e["profit"].sum()
        # The tax rate in the hub uses the accrued tax, or the payment where no accrued tax is given (or zero accrued
        # tax against a positive payment).
        use_paid = (pd.isna(h["accrued"]) or (h["accrued"] == 0 and (h["paid"] or 0) > 0))
        tax = h["paid"] if use_paid else h["accrued"]
        rows.append(dict(company=name, fiscal_year=fy, hub=HUB_NAMES[hub], hub_iso3=hub, eu_profit_usd=eu_profit,
                         eu_profit_positive_lines_usd=e["profit"].clip(lower=0).sum(), hub_profit_usd=h["profit"],
                         hub_share_uncapped=h["profit"] / eu_profit, hub_share=min(h["profit"] / eu_profit, 1.0),
                         hub_employees=h["employees"], hub_employee_share=h["employees"] / e["employees"].sum(),
                         hub_tax_accrued_usd=h["accrued"], hub_tax_paid_usd=h["paid"],
                         hub_rate_accrued=h["accrued"] / h["profit"], hub_rate_paid=h["paid"] / h["profit"],
                         hub_rate_shown=tax / h["profit"], hub_rate_basis="paid" if use_paid else "accrued",
                         eu_lines=len(e), eu_loss_lines=int((e["profit"] < 0).sum())))
    return pd.DataFrame(rows)


def draw_donuts(T, stem, per_row=6):
    n = len(T)
    nrow, ncol = int(np.ceil(n / per_row)), min(n, per_row)
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.3 * ncol + 0.6, 4.8 * nrow), squeeze=False)
    for ax in axes.flat[n:]:
        ax.axis("off")
    last = n - (nrow - 1) * ncol      # an incomplete last row is centred
    if nrow > 1 and last < ncol:
        step = axes[-1][1].get_position().x0 - axes[-1][0].get_position().x0
        for ax in axes[-1][:last]:
            pos = ax.get_position()
            ax.set_position([pos.x0 + (ncol - last) / 2 * step, pos.y0, pos.width, pos.height])
    for ax, (_, r) in zip(axes.flat, T.iterrows()):
        # One palette for all company figures: the hub in purple, the rest of the EU in light purple.
        ax.pie([r["hub_share"], 1 - r["hub_share"]], colors=[PURPLE, tint(PURPLE, 0.4)], startangle=90, counterclock=False,
               wedgeprops=dict(width=0.32, edgecolor="white", linewidth=2))
        # I show ">100%" only where the other EU lines net to a visible loss (a share of at least 100.5%).
        centre = ">100%" if r["hub_share_uncapped"] >= 1.005 else f"{100 * r['hub_share']:.0f}%"
        ax.text(0, 0.02, centre, ha="center", va="center", fontsize=21, weight="bold", color=INK)
        # A long name puts the group that files the report on a second line.
        title = r["company"].replace(" (", "\n(") if len(r["company"]) > 18 else r["company"]
        ax.set_title(title, fontsize=15, weight="bold", color=INK, pad=6)
        eu = r["eu_profit_usd"] / 1e9
        eu_txt = f"US${eu:,.1f}bn" if eu >= 1 else f"US${eu * 1e3:,.0f}m"
        emp = r["hub_employee_share"]
        emp_txt = f"{100 * emp:.0f}%" if emp >= 0.01 else "less than 1%"
        rate = f"{rate_label(100 * r['hub_rate_shown'], 1)}%" + (" (paid)" if r["hub_rate_basis"] == "paid" else "")
        # The lines below the ring print at about 6.6pt at the report's text width, which leaves a clear gap between the
        # texts of neighbouring rings.
        ax.text(0, -1.15, f"booked in {r['hub']}\nof {eu_txt} EU profit (FY{r['fiscal_year']})\n"
                f"with {emp_txt} of EU employees\ntax rate there: {rate}", ha="center", va="top", fontsize=11, color=INK,
                linespacing=1.35)
        ax.set_aspect("equal")
    # The figure has no source line because the definitions are in this script and the CSV.
    fig.savefig(CHAPTER_FIGS / f"{stem}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    T.round(4).to_csv(CHAPTER_TABLES / f"{stem}.csv", index=False)


def report_panel(panel, cells, src, key):
    """Return the panel up to the year of the company's report in the company estimates, the latest of 2023–2025.
    Figures 3.1 and 3.2 use the same report, because the panel can hold a later report that the estimates leave out
    (for Adobe, the panel holds a 2025 filing that covers Spain alone). The Irish filings of Apple and Microsoft are
    not in the panel."""
    year = cells.loc[cells["year"].between(2023, 2025) & (cells["company_key"] == key), "year"].max()
    return panel if src != "panel" or pd.isna(year) else panel[panel["year"] <= year]


def figure_9(panel, cells):
    """Draw the donuts of the chapter's companies, four to a row."""
    parts = [hub_table(report_panel(panel, cells, src, key), {name: (src, key, hub)})
             for name, (src, key, hub) in DONUT_CHAPTER.items()]
    chapter = pd.concat(parts, ignore_index=True)
    draw_donuts(chapter, "EU_profit_booked_in_the_hub", per_row=4)
    print(chapter[["company", "fiscal_year", "hub", "hub_share_uncapped", "hub_employee_share", "hub_rate_shown",
                   "hub_rate_basis"]].round(3).to_string(index=False))
    return chapter


# %% MARK: 6. Figure 3.2: profit per employee by country of the companies of Figure 3.1
# The figure shows the profit before tax per employee by country, with the tax rate, for the countries with the most
# revenue plus every tax-haven line booking more than US$1m of profit per employee. Bars above US$1m per employee are
# in the State of Tax Justice (SOTJ) purple, the rest in light purple. The label gives the profit per employee and
# tax ÷ profit. The tax is the current tax accrued for the year, as in Figure 3.1 and the text: cash payments mix years
# (prepayments, back payments, refunds and one-offs such as the release of Apple's State Aid escrow funds in its FY2025
# Irish cash tax). Where a report gives no accrued tax, or zero accrued tax against a positive payment, I use the tax
# paid. Microsoft and Apple come from their Irish filings, the others from the panel (the companies' own reports, in
# US$ at the report year's average rate). Each company uses the report of its donut in Figure 3.1. The single figures
# show up to ten countries, the panels of the combined figure up to six. I first take the lines with at least US$10m
# of profit and 10 employees. This threshold only keeps the figure to that number of bars. Where fewer lines pass it,
# I fill the free places with the company's other lines that book a profit and have at least one employee, again those
# with the most revenue first. The residual lines for all other jurisdictions are never shown, because they are no
# country. The 10 panels fill five rows of two.
PPE_COMPANIES = {    # name shown, as in Figure 3.1: file stem of its single figure
    "Microsoft": "Microsoft_FY2025",
    "Apple": "Apple_FY2025",
    "IKEA stores (Ingka)": "IKEA_Ingka",
    "Kraft Heinz": "Kraft_Heinz",
    "Primark (Associated British Foods)": "Primark",
    "Jameson (Pernod Ricard)": "Jameson_Pernod_Ricard",
    "Adobe": "Adobe",
    "TE Connectivity": "TE_Connectivity",
    "Western Digital": "Western_Digital",
    "PTC": "PTC",
}
PPE_N_SHOW, PPE_N_PANEL = 10, 6
_SHORT_NAMES = {"NLD": "Netherlands", "USA": "United States", "GBR": "United Kingdom", "KOR": "South Korea", "TWN": "Taiwan",
                "RUS": "Russia", "CZE": "Czechia", "IRN": "Iran", "VNM": "Viet Nam", "TUR": "Türkiye", "BOL": "Bolivia",
                "VEN": "Venezuela", "TZA": "Tanzania", "MDA": "Moldova", "LAO": "Laos", "SYR": "Syria", "PRK": "North Korea",
                "COD": "DR Congo", "HKG": "Hong Kong", "MAC": "Macao"}


def irish_filing_lines(key):
    d = pd.read_csv(IRISH_FILINGS.format(key))
    d["iso_partner"] = [getattr(pycountry.countries.get(alpha_2=c), "alpha_3", None) if isinstance(c, str) else None for c in d["code"]]
    d = d[d["iso_partner"].notna()].rename(columns={"jurisdiction": "jurisdiction_name", "revenue": "total_revenues",
                                                    "pbt": "profit_loss_before_income_tax", "employees": "n_employees",
                                                    "tax_paid": "income_tax_paid_on_cash_basis",
                                                    "tax_accrued": "income_tax_accrued_current_year"})
    return d.assign(year=2025, source="cro_ireland", unrelated_party_revenues=np.nan)


def ppe_lines(panel, src, key, n_show=PPE_N_SHOW):
    """Return the lines the figure shows from the company's latest report in `panel` (or its Irish filing), and the
    report year."""
    if src == "cro":
        d = irish_filing_lines(key)
    else:
        d = panel[(panel["company"] == key) | (panel["company_key"] == key)]
        d = d[d["year"] == d["year"].max()].copy()
    for c in ["total_revenues", "unrelated_party_revenues", "profit_loss_before_income_tax", "n_employees",
              "income_tax_accrued_current_year", "income_tax_paid_on_cash_basis"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["revenue"] = d["total_revenues"].fillna(d["unrelated_party_revenues"])
    acc, paid = d["income_tax_accrued_current_year"], d["income_tax_paid_on_cash_basis"]
    d["tax"] = acc.where(~(acc.isna() | ((acc == 0) & (paid.fillna(0) > 0))), paid)
    d = d[(d["iso_partner"] != "OTHER") & (d["profit_loss_before_income_tax"] > 0) & (d["n_employees"] >= 1)].copy()
    d["ppe_m"] = d["profit_loss_before_income_tax"] / d["n_employees"] / 1e6
    d["etr"] = 100 * d["tax"] / d["profit_loss_before_income_tax"]
    large = d[(d["profit_loss_before_income_tax"] >= 1e7) & (d["n_employees"] >= 10)]
    high = large[(large["ppe_m"] > 1.0) & large["iso_partner"].isin(HAVENS)]
    rest = large[~large.index.isin(high.index)].sort_values("revenue", ascending=False).head(max(n_show - len(high), 0))
    shown = pd.concat([high, rest])
    # A report with fewer large lines than places gets its smaller profitable lines, by revenue.
    small = d[~d.index.isin(shown.index)].sort_values("revenue", ascending=False).head(max(n_show - len(shown), 0))
    d = pd.concat([shown, small]).sort_values("ppe_m")
    d["jurisdiction_name"] = [english_name(i, n) for i, n in zip(d["iso_partner"], d["jurisdiction_name"])]
    return d, int(d["year"].iloc[0]) if len(d) else None


def english_name(iso, fallback):
    """Return the English country name for the ISO code (some reports give names in their own language, for example
    '22. Niederlande')."""
    if iso in _SHORT_NAMES:
        return _SHORT_NAMES[iso]
    c = pycountry.countries.get(alpha_3=str(iso))
    return getattr(c, "common_name", None) or (c.name if c else fallback)


def ppe_axes(ax, d, label, fs_bar=15, fs_country=16, fs_tick=15, xmax_mult=1.6, slots=None):
    """Draw the profit per employee of one company's lines on ax: the bars, the label of each bar (`label` formats the
    amount and the tax rate) and the country names. With `slots`, every panel has the same bar height, and a company
    with fewer lines keeps empty space below them."""
    y = np.arange(len(d))
    hub_col, rest_col = PURPLE, tint(PURPLE, 0.4)
    ax.barh(y, d["ppe_m"], height=0.72, color=[hub_col if v > 1.0 else rest_col for v in d["ppe_m"]], zorder=3)
    for yy, v, e in zip(y, d["ppe_m"], d["etr"]):
        # Millions with one decimal, smaller amounts to the dollar, so that no small amount looks rounded away.
        amount = f"US${v:,.1f}m" if v >= 0.995 else f"US${v * 1e6:,.0f}"
        # A small line can owe more tax than its profit (prior-year or non-deductible items), so I cap the label.
        tax = (">100% tax" if e > 100 else f"{rate_label(e, 0)}% tax") if pd.notna(e) else "tax n/a"
        ax.annotate(label(amount, tax), (v, yy), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=fs_bar, color=INK, zorder=4)
    ax.set_yticks(y)
    ax.set_yticklabels(d["jurisdiction_name"], fontsize=fs_country)
    if slots:
        ax.set_ylim(len(d) - slots - 0.5, len(d) - 0.5)
    ax.set_xlim(0, d["ppe_m"].max() * xmax_mult)
    ax.tick_params(axis="x", labelsize=fs_tick)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#D8D5CC", linewidth=1.2, zorder=0)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color("#B9B4A8")


def draw_ppe(panel, src, key, stem, name):
    d, fy = ppe_lines(panel, src, key)
    fig, ax = plt.subplots(figsize=(11, 5.6))
    ppe_axes(ax, d, lambda amount, tax: f"{amount}/employee   ·   {tax}")
    ax.set_xlabel(f"Profit before tax per employee (US$ million), FY{fy}", fontsize=17)
    # The figure has no source line because the source is described above and the CSV holds the plotted lines.
    fig.savefig(CHAPTER_FIGS / f"{stem}_profit_per_employee.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    d[["jurisdiction_name", "revenue", "profit_loss_before_income_tax", "n_employees", "tax", "ppe_m", "etr"]].sort_values(
        "ppe_m", ascending=False).round(3).to_csv(CHAPTER_TABLES / f"{stem}_profit_per_employee.csv", index=False)
    top = d.sort_values("ppe_m").iloc[-1]
    print(f"  {name} FY{fy}: {top['jurisdiction_name']} US${top['ppe_m']:.1f}m per employee at {top['etr']:.0f}% tax ({len(d)} bars)")


def figure_10(panel, cells):
    for name, stem in PPE_COMPANIES.items():
        src, key, _ = DONUT_CHAPTER[name]
        draw_ppe(report_panel(panel, cells, src, key), src, key, stem, name)
    figure_10_combined(panel, cells)


def figure_10_combined(panel, cells):
    """Draw all companies as panels of one figure, two to a row, for documents that take one image. A short last row
    is centred. Two panels to a row leave room for text of the size of the other figures. The figure carries no legend,
    definitions or sources, which go into the caption."""
    with matplotlib.rc_context({"text.parse_math": False}):
        _figure_10_combined(panel, cells)


def _figure_10_combined(panel, cells):
    n, ncol = len(PPE_COMPANIES), 2
    nrow = -(-n // ncol)
    fig = plt.figure(figsize=(18, 3.5 * nrow))
    grid = fig.add_gridspec(nrow, 2 * ncol)
    for i, name in enumerate(PPE_COMPANIES):
        row, col = divmod(i, ncol)
        start = ncol - min(ncol, n - row * ncol) + 2 * col
        ax = fig.add_subplot(grid[row, start:start + 2])
        src, key, _ = DONUT_CHAPTER[name]
        d, fy = ppe_lines(report_panel(panel, cells, src, key), src, key, PPE_N_PANEL)
        # The text prints at about 7.5pt at the report's text width (the titles at about 8.5pt), like the other figures.
        ppe_axes(ax, d, lambda amount, tax: f"{amount} · {tax}", fs_bar=21, fs_country=21, fs_tick=19, xmax_mult=2.0,
                 slots=PPE_N_PANEL)
        ax.set_title(f"{name}, FY{fy}", fontsize=23, loc="left", color=INK, pad=10)
        ax.set_xlabel("profit per employee (US$ million)", fontsize=19)
    fig.tight_layout(h_pad=2.0, w_pad=3.0)
    fig.savefig(CHAPTER_FIGS / "profit_per_employee_companies.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote profit_per_employee_companies (Figure 3.2 as one image, {n} companies)")


# %% MARK: 7. Figure 3.3: tax rates where groups book too much and too little profit
# I use each group's latest report of 2023–2025, with its profit apportioned half by employees and half by sales
# against consolidated revenue (the cells of the headline specification).
# - Too much profit: lines booking more profit than the formula gives them. The tax rate is the current tax (accrued,
#   else paid) ÷ profit, weighted by the excess.
# - Too little profit: profitable lines booking less. The rate is the same, weighted by their profit.
# - Statutory rate (table only): the statutory CIT where the excess is booked, weighted by the excess.
# The chart leaves out extractive groups, which pay special resource taxes. With them, the excess outside havens shows
# the petroleum-tax rates of Shell and TotalEnergies in Oman, Norway and Nigeria (65–83%). The chart keeps banks and
# insurers, because the rates compare tax with profit, so the reason to leave finance out of the apportionment
# estimates does not apply. The table keeps all four samples.
# The chart compares the EU countries outside the five EU hubs of the averages (EU_HUBS) with the hubs. Each marker is
# the weighted rate of the chart sample with the current tax (accrued, else paid). Its line is the 95% confidence
# interval of that average: I resample the companies with replacement BOOT_REPS times and take the 2.5th and 97.5th
# percentiles of the recomputed averages. The table gives the weighted rates of all four samples and also with the tax
# paid (else accrued): Apple's FY2025 Irish cash tax includes the release of the State Aid escrow funds, a one-off that
# would raise the hub rate by about five points.
CHART_SAMPLE = "no extractive groups"
BOOT_REPS, BOOT_SEED = 2000, 2026
RATE_GROUPS = ["all jurisdictions", "tax havens (representation list)", "non-havens, statutory CIT >= 15%"]
EU_GROUPS = [("EU countries\nexcluding tax havens", False), ("EU tax havens\n(Ireland, Luxembourg, the Netherlands,\nMalta and Cyprus)", True)]
TAX_CONCEPTS = [("accrued, else paid", "etr_cell"), ("paid, else accrued", "etr_cell_paid")]


def rate_cells(d_report):
    """Return the headline cells of 2023–2025 with the line's current tax rate. I leave out the residual OTHER lines
    (they stay in the apportionment pool)."""
    d = d_report[d_report["year"].isin(RECENT_YEARS)].copy()
    d["is_latest_year"] = d["year"] == d.groupby("company_key")["year"].transform("max")
    p = d["profit_loss_before_income_tax"]
    d["tax_current"] = d["income_tax_accrued_current_year"].fillna(d["income_tax_paid_on_cash_basis"])
    d["etr_cell"] = np.where(p > 0, (d["tax_current"] / p).clip(0, 1), np.nan)
    tax_paid = d["income_tax_paid_on_cash_basis"].fillna(d["income_tax_accrued_current_year"])
    d["etr_cell_paid"] = np.where(p > 0, (tax_paid / p).clip(0, 1), np.nan)
    d["is_other"] = d["iso_partner"] == "OTHER"
    d["is_haven"] = d["iso_partner"].isin(HAVENS)
    return d[~d["is_other"]]


def rate_table(c, variant, n_groups, etr_col="etr_cell"):
    """Return the excess profit by jurisdiction group, with its weighted tax rate against the statutory rate and
    against the rate where profitable lines book too little."""
    pos = c[c["misaligned_profit"] > 0]
    neg = c[(c["misaligned_profit"] < 0) & (c["profit_loss_before_income_tax"] > 0)]
    masks = {"all jurisdictions": pd.Series(True, index=c.index),
             "tax havens (representation list)": c["is_haven"],
             "non-havens, statutory CIT >= 15%": ~c["is_haven"] & (c["cit"] >= LOW)}
    rows = []
    for name in RATE_GROUPS:
        mask = masks[name]
        pm = pos[mask.reindex(pos.index, fill_value=False)]
        nm = neg[mask.reindex(neg.index, fill_value=False)]
        m = pm["misaligned_profit"]
        has_etr = pm[etr_col].notna()
        low = has_etr & (pm[etr_col] < LOW)
        rows.append({"variant": variant, "jurisdiction_group": name, "n_groups_sample": n_groups,
                     "pos_misaligned_usd_bn": m.sum() / 1e9,
                     "etr_on_pos_misaligned_weighted": wavg(pm[etr_col], m),
                     "etr_neg_misaligned_profit_weighted": wavg(nm[etr_col], nm["profit_loss_before_income_tax"]),
                     "cit_on_pos_misaligned_weighted": wavg(pm["cit"], m),
                     "share_pos_misaligned_taxed_below_15": m[low].sum() / m[has_etr].sum() if m[has_etr].sum() > 0 else np.nan})
    return rows


def eu_rates(c, etr_col):
    """Return the tax paid where groups book too much or too little profit in the five EU hubs and in the other EU
    countries."""
    c = c[c["iso_partner"].isin(EU)]
    rows = []
    for hub in (True, False):
        g = c[c["iso_partner"].isin(EU_HUBS) == hub]
        pos = g[(g["misaligned_profit"] > 0) & g[etr_col].notna()]
        neg = g[(g["misaligned_profit"] < 0) & (g["profit_loss_before_income_tax"] > 0) & g[etr_col].notna()]
        rows.append(dict(hub=hub, rate_too_much=wavg(pos[etr_col], pos["misaligned_profit"]),
                         rate_too_little=wavg(neg[etr_col], neg["profit_loss_before_income_tax"]),
                         excess_usd_bn=pos["misaligned_profit"].sum() / 1e9, n_groups=g["company_key"].nunique()))
    return rows


def eu_line_rates(c, etr_col):
    """Return the single country lines behind eu_rates (company, rate and weight), by hub and series."""
    c = c[c["iso_partner"].isin(EU)]
    out = {}
    for hub in (True, False):
        g = c[c["iso_partner"].isin(EU_HUBS) == hub]
        pos = g[(g["misaligned_profit"] > 0) & g[etr_col].notna()]
        neg = g[(g["misaligned_profit"] < 0) & (g["profit_loss_before_income_tax"] > 0) & g[etr_col].notna()]
        out[(hub, "rate_too_much")] = pd.DataFrame({"company_key": pos["company_key"], "rate": pos[etr_col],
                                                    "weight": pos["misaligned_profit"]})
        out[(hub, "rate_too_little")] = pd.DataFrame({"company_key": neg["company_key"], "rate": neg[etr_col],
                                                      "weight": neg["profit_loss_before_income_tax"]})
    return out


def bootstrap_ci(lines, reps=BOOT_REPS, seed=BOOT_SEED):
    """Return the 95% confidence interval of a weighted average rate. I resample the companies with replacement, so
    that all lines of a company stay together, and recompute the weighted average in each draw."""
    by = lines.assign(tw=lines["rate"] * lines["weight"]).groupby("company_key")[["tw", "weight"]].sum()
    tw, w = by["tw"].to_numpy(), by["weight"].to_numpy()
    idx = np.random.default_rng(seed).integers(0, len(tw), size=(reps, len(tw)))
    return np.percentile(tw[idx].sum(axis=1) / w[idx].sum(axis=1), [2.5, 97.5])


def figure_11(d_report):
    m = rate_cells(d_report)
    m = m[m["is_latest_year"]]
    out, E = [], []
    for lab, sub in [("all sectors", m), ("no extractive groups", m[~m["sector"].isin(EXTRACTIVE_SECTORS)]),
                     ("no banks or insurers", m[~m["sector"].isin(FINANCIAL_SECTORS)]),
                     ("no banks, insurers or extractive groups", m[~m["sector"].isin(FINANCIAL_SECTORS | EXTRACTIVE_SECTORS)])]:
        out += rate_table(sub, lab, sub["company_key"].nunique())
        for tax, col in TAX_CONCEPTS:
            E += [dict(sample=lab, tax=tax, **r) for r in eu_rates(sub, col)]
        if lab == CHART_SAMPLE:
            cells = sub
    pd.DataFrame(out).round(4).to_csv(CHAPTER_TABLES / "pcbcr_rates_too_much_too_little.csv", index=False)
    E = pd.DataFrame(E)
    E.round(4).to_csv(CHAPTER_TABLES / "pcbcr_rates_too_much_too_little_eu.csv", index=False)
    head = E[(E["sample"] == CHART_SAMPLE) & (E["tax"] == TAX_CONCEPTS[0][0])].set_index("hub")
    acc = E[E["tax"] == TAX_CONCEPTS[0][0]]
    lo = acc.groupby("hub")[["rate_too_much", "rate_too_little"]].min()
    hi = acc.groupby("hub")[["rate_too_much", "rate_too_little"]].max()
    print(pd.concat({"point": head[["rate_too_much", "rate_too_little"]], "low": lo, "high": hi}, axis=1).round(3).to_string())
    n = cells["company_key"].nunique()
    lines = eu_line_rates(cells, TAX_CONCEPTS[0][1])
    cis = []
    with matplotlib.rc_context({"text.parse_math": False}):
        # The figure is flat, so that it shares a page of the report with its note and the text around it.
        fig, ax = plt.subplots(figsize=(11, 5.2))
        x = np.arange(len(EU_GROUPS))
        # The two series differ in hue and in marker shape, so that colour-blind readers can tell them apart.
        series = [("Where they book too much profit", "rate_too_much", PURPLE, "o"),
                  ("Where they book too little profit", "rate_too_little", GAIN, "s")]
        for k, (lab, col, color, marker) in enumerate(series):
            for xi, (glab, hub) in zip(x, EU_GROUPS):
                xx = xi + (k - 0.5) * 0.4
                v = 100 * head.loc[hub, col]
                a, b = 100 * bootstrap_ci(lines[(hub, col)])
                # As in a coefficient plot, a thin line with caps shows the confidence interval and the marker the average.
                ax.errorbar([xx], [v], yerr=[[v - a], [b - v]], fmt=marker, ms=9, color=color, elinewidth=1.5, capsize=6,
                            capthick=1.5, zorder=4, label=lab if xi == 0 else None)
                # The value stands on the outer side of each pair, so that it never runs into the neighbouring line.
                ax.text(xx + (0.1 if k else -0.1), v, f"{v:.1f}%", va="center", ha="left" if k else "right",
                        fontsize=12, color=INK, zorder=5)
                cis.append(dict(group=glab.replace("\n", " "), series=lab, weighted_average=v, ci_low=a, ci_high=b,
                                n_lines=len(lines[(hub, col)]), n_groups=lines[(hub, col)]["company_key"].nunique()))
        cis = pd.DataFrame(cis)
        cis.round(2).to_csv(CHAPTER_TABLES / "pcbcr_rates_too_much_too_little_eu_ci.csv", index=False)
        print(cis.round(1).to_string(index=False))
        ax.set_ylim(5 * np.floor((cis["ci_low"].min() - 2) / 5), 5 * np.ceil((cis["ci_high"].max() + 2) / 5))
        ax.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(5))
        ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%d"))
        ax.axhline(15, color=INK, lw=0.9, ls=(0, (4, 3)), zorder=1)
        # The label of the minimum tax sits in the gap between the two groups, clear of the intervals.
        ax.text(x.mean(), 15.3, "15% minimum tax", ha="center", va="bottom", fontsize=11, color=INK)
        ax.set_xticks(x)
        ax.set_xticklabels([g for g, _ in EU_GROUPS], fontsize=11)
        ax.set_xlim(-0.6, len(EU_GROUPS) - 0.4)
        ax.set_ylabel("tax paid ÷ profit (%)", fontsize=11)
        ax.tick_params(axis="y", labelsize=11)
        ax.grid(axis="x", visible=False)
        ax.legend(frameon=False, fontsize=11, loc="lower left", bbox_to_anchor=(0, 1.01), ncol=2,
                  title="tax paid by multinationals", title_fontsize=11, alignment="left")
        fig.savefig(CHAPTER_FIGS / "figC8c_pcbcr_rates_too_much_too_little.png", dpi=200, bbox_inches="tight")
        plt.close(fig)
    print(f"  wrote figC8c ({n:,} groups, {CHART_SAMPLE}, the other EU countries against the EU hubs, with 95% confidence intervals)")


# %% MARK: 8. Table 3.1: EU countries, country-level estimate and public reports
# For the European jurisdictions (region_tjn == "Europe"), I put the headline estimate next to the public reports of
# 2025 in both specifications. The headline estimate comes from the aggregate OECD country-by-country reporting (CbCR)
# data (2023, net revenue change under unitary taxation, unscaled, constant 2025 US$). The public reports cover all
# groups reporting the country, without banks, insurers and extractive groups. The scaled value is the result ÷ the
# mean of the shares of the country's multinational employees and revenues that the reports cover in the OECD data
# (a rough estimate for the universe of multinationals). The coverage is the reports' share of the country's
# multinational employees, revenues and profit. Table 3.1 shows, in euros, the largest EU economies by GDP in the OECD
# year and Luxembourg, whose sign differs between the two columns, and sums the other member states in one row. The
# smaller economies are left out because their public-report results rest on few groups and a small share of activity.
TABLE1_TOP_GDP = 15
TABLE1_EXTRA = ["LUX"]
CBCR_MAIN = ROOT / "data/final/cbcr_main.csv"
# Novo Nordisk books about twice the profit in Denmark that its employees and sales there warrant, and its result alone
# exceeds the net result of all groups with a Danish line. Scaling it up with the coverage of all reports would treat the
# multinationals without public reports as if they booked their profits like Novo Nordisk. I therefore add the result of
# these groups unscaled and scale up only the other groups, with their share of the activity the unscaled groups leave.
UNSCALED_GROUPS = {"DNK": ["NOVO NORDISK"]}


def oecd_headline():
    """Return the headline estimate per country for 2023, in constant 2025 US$ bn."""
    ce = pd.read_csv(OECD_HEADLINE, low_memory=False)
    ce = ce[ce["year"] == Y_OECD].set_index("iso_partner")["revenue_gain_from_ut"]
    return ce / 1e3 * deflator_to_base()[Y_OECD]


def firm_by_country(cells, eur):
    """Return the public-report result per country (US$ bn), its number of groups and the groups' employees, revenues
    (total, else unrelated-party) and profit in the country, without banks, insurers and extractive groups."""
    c = cells[(cells["year"] == Y_FIRM) & cells["iso_partner"].isin(eur)].copy()
    c = c[~c["sector"].isin(FINANCIAL_SECTORS | EXTRACTIVE_SECTORS)]
    c["_rev"] = pd.to_numeric(c["total_revenues"], errors="coerce").fillna(pd.to_numeric(c["unrelated_party_revenues"], errors="coerce"))
    g = c.groupby("iso_partner")
    return pd.DataFrame({"pcbcr": g["revenue_gain_from_ut_usd"].sum() / 1e9, "pcbcr_groups": g["company_key"].nunique(),
                         "_emp": g["n_employees"].sum(min_count=1), "_rev": g["_rev"].sum(min_count=1),
                         "_prof": g["profit_loss_before_income_tax"].sum(min_count=1)})


def oecd_universe(oc):
    """Return the OECD universe of multinationals per country in the latest OECD year, with all cells including the
    imputed ones of aggregate reporters, in 2025 prices like the FY2025 report amounts it is compared with."""
    uni = oc[oc["year"] == Y_OECD].groupby("iso_partner")[["n_employees", "total_revenues", "profit_loss_before_income_tax"]].sum(min_count=1)
    uni[["total_revenues", "profit_loss_before_income_tax"]] *= deflator_to_base()[Y_OECD]
    return uni


def unscaled_groups(cells_csv, index):
    """Return, per country, the result (US$ bn, both specifications), employees and revenues of the groups that enter
    the scaled public-report result unscaled (UNSCALED_GROUPS), and zero for the other countries."""
    out = pd.DataFrame(0.0, index=index, columns=["res", "res_reportonly", "emp", "rev"])
    for iso, keys in UNSCALED_GROUPS.items():
        if iso not in out.index:
            continue
        for spec, col in ((SPEC_REPORT, "res"), (SPEC_REPORTONLY, "res_reportonly")):
            c = cells_csv[spec]
            c = c[(c["year"] == Y_FIRM) & (c["iso_partner"] == iso) & c["company_key"].isin(keys)]
            out.loc[iso, col] = c["revenue_gain_from_ut_usd"].sum() / 1e9
            if spec == SPEC_REPORT:
                rev = pd.to_numeric(c["total_revenues"], errors="coerce").fillna(
                    pd.to_numeric(c["unrelated_party_revenues"], errors="coerce"))
                out.loc[iso, ["emp", "rev"]] = [c["n_employees"].sum(), rev.sum()]
    return out


def europe_table(cells_csv):
    """Return the European countries with the headline estimate, the public-report results (unscaled and scaled, both
    specifications) and the coverage, and, per country, the coverage of the activity the groups of UNSCALED_GROUPS
    leave, with which the other groups are scaled."""
    oc = pd.read_csv(EXCL_RESOURCE, usecols=["iso_partner", "partner_jurisdiction", "region_tjn", "year", "n_employees",
                                             "total_revenues", "profit_loss_before_income_tax"], low_memory=False)
    o = oc.drop_duplicates("iso_partner").set_index("iso_partner")
    eur = o[o["region_tjn"] == "Europe"]["partner_jurisdiction"]
    uni = oecd_universe(oc)
    t = pd.DataFrame(index=eur.index)
    t["country"] = eur
    t["tax_haven"] = t.index.isin(HAVENS)
    t["headline_estimate"] = oecd_headline().reindex(t.index)
    f = firm_by_country(cells_csv[SPEC_REPORT], eur.index).reindex(t.index)
    t["pcbcr"] = f["pcbcr"]
    t["pcbcr_groups"] = f["pcbcr_groups"].fillna(0).astype(int)
    t["employees_covered"] = f["_emp"] / uni["n_employees"].reindex(t.index)
    t["revenues_covered"] = f["_rev"] / uni["total_revenues"].reindex(t.index)
    t["profit_covered"] = f["_prof"] / uni["profit_loss_before_income_tax"].reindex(t.index)
    cov = (t["employees_covered"] + t["revenues_covered"]) / 2
    # The groups of UNSCALED_GROUPS enter unscaled, and the others are scaled with their share of the activity the
    # unscaled groups leave. In every other country this is the plain scaling with the coverage of all reports.
    u = unscaled_groups(cells_csv, t.index)
    ue_c, ur_c = uni["n_employees"].reindex(t.index), uni["total_revenues"].reindex(t.index)
    cov_rest = ((f["_emp"] - u["emp"]) / (ue_c - u["emp"]) + (f["_rev"] - u["rev"]) / (ur_c - u["rev"])) / 2
    t["pcbcr_scaled"] = u["res"] + (t["pcbcr"] - u["res"]) / cov_rest.where(cov_rest > 0)
    t["low_coverage"] = cov < LOW_COVERAGE
    # Reports only: the same groups and coverage, with the revenues as the reports give them.
    t["pcbcr_reportonly"] = firm_by_country(cells_csv[SPEC_REPORTONLY], eur.index).reindex(t.index)["pcbcr"]
    t["pcbcr_reportonly_scaled"] = u["res_reportonly"] + (t["pcbcr_reportonly"] - u["res_reportonly"]) / cov_rest.where(cov_rest > 0)
    t = t.sort_values("headline_estimate", ascending=False)
    # Non-haven Europe: I sum the countries, and the scaled value divides the summed result by the summed coverage, with
    # the groups of UNSCALED_GROUPS unscaled as above.
    nh = t[~t["tax_haven"]].index
    fe, ue, un = f.reindex(nh), uni.reindex(nh), u.reindex(nh)
    ce = fe["_emp"].sum() / ue["n_employees"].sum()
    cr = fe["_rev"].sum() / ue["total_revenues"].sum()
    rest = ((fe["_emp"].sum() - un["emp"].sum()) / (ue["n_employees"].sum() - un["emp"].sum())
            + (fe["_rev"].sum() - un["rev"].sum()) / (ue["total_revenues"].sum() - un["rev"].sum())) / 2
    tot = {c: t.loc[nh, c].sum() for c in ["headline_estimate", "pcbcr", "pcbcr_reportonly"]}
    tot.update(country="Non-haven Europe", tax_haven=False, pcbcr_groups=np.nan, employees_covered=ce, revenues_covered=cr,
               profit_covered=fe["_prof"].sum() / ue["profit_loss_before_income_tax"].sum(),
               pcbcr_scaled=un["res"].sum() + (tot["pcbcr"] - un["res"].sum()) / rest,
               pcbcr_reportonly_scaled=un["res_reportonly"].sum() + (tot["pcbcr_reportonly"] - un["res_reportonly"].sum()) / rest,
               low_coverage=False)
    t = pd.concat([t, pd.DataFrame([tot], index=["EUR_NONHAVEN"])])
    return t[["country", "tax_haven", "headline_estimate", "pcbcr", "pcbcr_scaled", "pcbcr_reportonly",
              "pcbcr_reportonly_scaled", "employees_covered", "revenues_covered", "profit_covered", "pcbcr_groups",
              "low_coverage"]], cov_rest


def table_1(cells_csv):
    """Write the European table, Table 3.1 and the statistics of the paragraph on Table 3.1. I return the European table and
    the coverage of the activity the groups of UNSCALED_GROUPS leave (quoted in the note to Table 3.1)."""
    t, cov_rest = europe_table(cells_csv)
    t.round(4).to_csv(CHAPTER_TABLES / "europe_ut_pcbcr_scaled.csv", index_label="iso3")
    # I build Table 3.1 from the table as written (four decimals), in euros at the 2025 average rate.
    e = pd.read_csv(CHAPTER_TABLES / "europe_ut_pcbcr_scaled.csv").set_index("iso3")
    eu27 = e.reindex(EU27).dropna(subset=["country"]).sort_values("headline_estimate", ascending=False)
    gdp = pd.read_csv(CBCR_MAIN, usecols=["iso_partner", "year", "gdp_current_usd"], low_memory=False)
    gdp = gdp[(gdp["year"] == Y_OECD) & gdp["iso_partner"].isin(EU27)].groupby("iso_partner")["gdp_current_usd"].first()
    keep = list(gdp.sort_values(ascending=False).index[:TABLE1_TOP_GDP]) + TABLE1_EXTRA
    show = eu27.loc[keep].sort_values("headline_estimate", ascending=False)
    others = eu27.index.difference(keep)
    rows = [{"Country": r.country,
             "Country-level estimates, 2023 (2025 prices), EUR bn": round(EUR_PER_USD * r.headline_estimate, 1),
             "Public country-by-country reports, 2025, scaled up, EUR bn": round(EUR_PER_USD * r.pcbcr_scaled, 1),
             "Share of activity the reports cover, %": round(100 * (r.employees_covered + r.revenues_covered) / 2)}
            for r in show.itertuples()]
    # The row of the other member states and the EU-27 row sum their countries in both columns, so that each country's
    # public-report result keeps the scaling of its own coverage, which differs widely between countries. Their share
    # of activity covered is that of the countries together.
    oc = pd.read_csv(EXCL_RESOURCE, usecols=["iso_partner", "year", "n_employees", "total_revenues",
                                             "profit_loss_before_income_tax"], low_memory=False)
    uni = oecd_universe(oc).reindex(EU27)
    f = firm_by_country(cells_csv[SPEC_REPORT], EU27).reindex(EU27)
    cov_o = (f.loc[others, "_emp"].sum() / uni.loc[others, "n_employees"].sum()
             + f.loc[others, "_rev"].sum() / uni.loc[others, "total_revenues"].sum()) / 2
    rows.append({"Country": f"Other {len(others)} EU countries",
                 "Country-level estimates, 2023 (2025 prices), EUR bn": round(EUR_PER_USD * eu27.loc[others, "headline_estimate"].sum(), 1),
                 "Public country-by-country reports, 2025, scaled up, EUR bn": round(EUR_PER_USD * eu27.loc[others, "pcbcr_scaled"].sum(), 1),
                 "Share of activity the reports cover, %": round(100 * cov_o)})
    cov = (f["_emp"].sum() / uni["n_employees"].sum() + f["_rev"].sum() / uni["total_revenues"].sum()) / 2
    rows.append({"Country": "EU-27",
                 "Country-level estimates, 2023 (2025 prices), EUR bn": round(EUR_PER_USD * eu27["headline_estimate"].sum(), 1),
                 "Public country-by-country reports, 2025, scaled up, EUR bn": round(EUR_PER_USD * eu27["pcbcr_scaled"].sum(), 1),
                 "Share of activity the reports cover, %": round(100 * cov)})
    # The last row scales the country-level estimate of the EU-27 up to all multinationals with the world factor of the
    # previous chapter, so that it compares with the scaled public reports.
    sf = load_factors("reported_only")[Y_OECD]
    rows.append({"Country": "EU-27, scaled up to all multinationals",
                 "Country-level estimates, 2023 (2025 prices), EUR bn": round(EUR_PER_USD * sf * eu27["headline_estimate"].sum(), 1),
                 "Public country-by-country reports, 2025, scaled up, EUR bn": np.nan,
                 "Share of activity the reports cover, %": pd.NA})
    T1 = pd.DataFrame(rows)
    T1["Share of activity the reports cover, %"] = T1["Share of activity the reports cover, %"].astype("Int64")
    T1.to_csv(CHAPTER_TABLES / "table1_eu_estimates_vs_public_reports.csv", index=False)
    print(T1.to_string(index=False))
    # The numbers of the paragraph on Table 3.1: the share of the multinationals' activity that the reports cover, and
    # how close the two columns are, for the countries of the table and for all 27 member states.
    rows = []
    for lab, d in (("Table 3.1 countries", show), ("EU-27", eu27)):
        d = d.dropna(subset=["headline_estimate", "pcbcr_scaled"])
        a, b = EUR_PER_USD * d["headline_estimate"], EUR_PER_USD * d["pcbcr_scaled"]
        cov = 100 * (d["employees_covered"] + d["revenues_covered"]) / 2
        rows += [dict(sample=lab, statistic="countries", value=len(d)),
                 dict(sample=lab, statistic="coverage, lowest (%)", value=cov.min(), country=d.loc[cov.idxmin(), "country"]),
                 dict(sample=lab, statistic="coverage, highest (%)", value=cov.max(), country=d.loc[cov.idxmax(), "country"]),
                 dict(sample=lab, statistic="correlation of the two columns", value=a.corr(b)),
                 dict(sample=lab, statistic="rank correlation of the two columns", value=a.corr(b, method="spearman")),
                 dict(sample=lab, statistic="countries with the same sign in both columns", value=int((np.sign(a) == np.sign(b)).sum())),
                 dict(sample=lab, statistic="sum of the country-level estimates (EUR bn)", value=a.sum()),
                 dict(sample=lab, statistic="sum of the public reports, scaled up (EUR bn)", value=b.sum())]
    rows.append(dict(sample="EU-27", statistic="country-level estimate scaled up to all multinationals (EUR bn)",
                     value=EUR_PER_USD * sf * eu27["headline_estimate"].sum()))
    S = pd.DataFrame(rows)
    S.round(4).to_csv(CHAPTER_TABLES / "table1_comparison_stats.csv", index=False)
    print(S.round(3).to_string(index=False))
    return t, cov_rest


# %% MARK: 9. Averages across all groups
# This section checks whether the patterns of the company examples hold on average across all public reports. I use
# the headline cells and each group's latest report of 2023–2025, without banks, insurers and oil, gas and mining
# groups as in all public-report estimates (and also with banks and insurers, as in Figure 3.3). The EU hubs are
# Ireland, Luxembourg, the Netherlands, Malta and Cyprus. I leave out J&F. Its Luxembourg line (from Taxplorer, as the
# original report could not be found) shows €62bn of revenue with 3 employees and very likely double-counts the JBS
# USA sub-group.
UNVERIFIED = {"J&F"}
# The bands of the distribution of EU profit by tax rate. Negative rates (refunds) count in the first band.
RATE_BANDS = [(-np.inf, 0.05, "below 5%"), (0.05, 0.10, "5–10%"), (0.10, 0.15, "10–15%"), (0.15, 0.20, "15–20%"),
              (0.20, 0.25, "20–25%"), (0.25, 0.30, "25–30%"), (0.30, np.inf, "30% or more")]


def company_averages(cells_report, panel):
    """Write the statistics across all groups (company_averages.csv) and the distribution of EU profit by tax rate
    (eu_profit_by_tax_rate.csv), and return the statistics. The counts, the hubs' shares
    of profit, employees and sales and the profit per employee are for the groups with an EU report: those whose
    latest report has at least two EU lines. The counts of groups by the share of their net EU profit booked in the hubs
    are for those of them with a positive net EU profit. The tax rates and the distribution of profit by tax rate are
    for all groups with a line in the EU, and their names say so."""
    c = cells_report[cells_report["iso_partner"] != "OTHER"]
    latest = c.groupby("company_key")["year"].transform("max")
    c = c[(c["year"] == latest) & c["year"].between(2023, 2025)].copy()
    c = c[~c["company_key"].isin(UNVERIFIED)]
    p = panel[["company_key", "year", "iso_partner", "income_tax_accrued_current_year"]]
    p = p.groupby(["company_key", "year", "iso_partner"], as_index=False)["income_tax_accrued_current_year"].sum(min_count=1)
    c = c.merge(p, on=["company_key", "year", "iso_partner"], how="left")
    fin = c["sector"].isin(FINANCIAL_SECTORS)
    ext = c["sector"].isin(EXTRACTIVE_SECTORS) | c["is_extractive"].astype(str).str.lower().eq("true")
    for col in ["profit_loss_before_income_tax", "theoretical_profit", "misaligned_profit", "n_employees", "sales_any_revenue",
                "income_tax_paid_on_cash_basis", "income_tax_accrued_current_year"]:
        c[col] = pd.to_numeric(c[col], errors="coerce")
    # The current tax is the accrued tax, else the tax paid (as in Figure 3.3).
    c["tax"] = c["income_tax_accrued_current_year"].where(c["income_tax_accrued_current_year"].notna(), c["income_tax_paid_on_cash_basis"])
    rows, bands = [], []
    # All multinationals' employees and revenues in the EU countries in the OECD data for 2023, at 2025 prices
    oc = pd.read_csv(EXCL_RESOURCE, usecols=["iso_partner", "year", "n_employees", "total_revenues",
                                             "profit_loss_before_income_tax"], low_memory=False)
    uni_eu = oecd_universe(oc).reindex(sorted(EU))

    def add(stat, value, note, sample):
        rows.append(dict(statistic=stat, value=value, sample=sample, definition=note))

    for lab, s in [("no banks, insurers or extractive groups", c[~fin & ~ext]), ("no extractive groups (banks and insurers in)", c[~ext])]:
        e = s[s["iso_partner"].isin(EU)].copy()
        e["hub"] = e["iso_partner"].isin(EU_HUBS)
        groups = e.groupby("company_key")
        tot = groups[["profit_loss_before_income_tax", "n_employees", "sales_any_revenue", "theoretical_profit"]].sum()
        hub = e[e["hub"]].groupby("company_key")[["profit_loss_before_income_tax", "n_employees", "sales_any_revenue",
                                                   "theoretical_profit"]].sum().reindex(tot.index).fillna(0.0)
        # I keep the groups present in the EU with at least two EU lines, also those whose EU lines add up to a loss,
        # because the pooled shares and the profit per employee add up the amounts of all groups.
        ok = groups.size() >= 2
        # A group's share of its net EU profit booked in the hubs is defined only where that profit is positive.
        positive = ok & (tot["profit_loss_before_income_tax"] > 0)
        share = (hub["profit_loss_before_income_tax"] / tot["profit_loss_before_income_tax"])[positive]
        add("groups with an EU report (≥2 EU lines)", int(ok.sum()), "count", lab)
        # The groups' combined EU profit, and how much more tax EU countries would collect if each group's EU profit were
        # spread over its EU countries by their shares of its EU sales and employees, half each, as for the company
        # examples: profit that arrives in a country is taxed at its statutory rate, profit that leaves it at the rate
        # in the report (accrued tax, else tax paid, at most the statutory rate).
        g = e[e["company_key"].isin(ok[ok].index)].copy()
        for col in ["cit", "etr_accrued_cell", "etr_cash_cell"]:
            g[col] = pd.to_numeric(g[col], errors="coerce")
        key = g["company_key"]
        emp, sales = g["n_employees"].fillna(0), g["sales_any_revenue"].fillna(0)
        emp_sum, sales_sum = emp.groupby(key).transform("sum"), sales.groupby(key).transform("sum")
        weight = 0.5 * emp / emp_sum + 0.5 * sales / sales_sum
        profit = g["profit_loss_before_income_tax"]
        move = profit.groupby(key).transform("sum") * weight - profit
        implied = g["etr_accrued_cell"].fillna(g["etr_cash_cell"]).clip(lower=0)
        rate = pd.concat([implied, g["cit"]], axis=1).min(axis=1)
        change = (g["cit"] * move.clip(lower=0) - rate * (-move).clip(lower=0))[(emp_sum > 0) & (sales_sum > 0)]
        add("groups' combined net EU profit (US$ million)", tot.loc[ok, "profit_loss_before_income_tax"].sum() / 1e6,
            "sum over the groups", lab)
        add("additional tax EU countries would collect from these groups (US$ million)", change.sum() / 1e6,
            "EU profit spread by EU sales and employees, half each", lab)
        # The groups' share of all multinationals' employees and revenues in the EU in the OECD data for 2023, as in
        # the scaling of the EU table, and the additional tax if the groups without public reports booked their EU
        # profit in the same way.
        rev = pd.to_numeric(g["total_revenues"], errors="coerce").fillna(pd.to_numeric(g["unrelated_party_revenues"],
                                                                                      errors="coerce"))
        cover = (g["n_employees"].sum() / uni_eu["n_employees"].sum() + rev.sum() / uni_eu["total_revenues"].sum()) / 2
        add("share of multinationals' EU employees and revenues these groups cover", cover, "share", lab)
        add("additional tax EU countries would collect, scaled up to all multinationals (US$ million)",
            change.sum() / 1e6 / cover, "divided by the share covered", lab)
        add("groups booking >50% of net EU profit in the five hubs", int((share > 0.5).sum()), "count", lab)
        add("groups booking >90% of net EU profit in the five hubs", int((share > 0.9).sum()), "count", lab)
        # The same groups measured against their economic activity: the groups that book more profit in the five hubs
        # than their employees and sales there warrant (the profit the formula gives the hubs), and those that book
        # more than twice as much.
        hp, hw = hub["profit_loss_before_income_tax"][ok], hub["theoretical_profit"][ok]
        n_hub_lines = e[e["hub"]].groupby("company_key").size().reindex(tot.index).fillna(0)[ok]
        add("groups with a line in the five hubs", int((n_hub_lines > 0).sum()), "count", lab)
        add("groups booking more profit in the five hubs than their activity there warrants", int((hp > hw).sum()), "count", lab)
        add("groups booking more than twice the profit their activity in the five hubs warrants",
            int(((hp > 2 * hw) & (hp > 0)).sum()), "count", lab)
        # The hubs' shares and the profit per employee are for the groups counted above, pooled over their EU lines,
        # because the chapter states them for these groups.
        own = "pooled over the groups with an EU report"
        P, H = g["profit_loss_before_income_tax"], g["hub"]
        add("hubs' share of the groups' combined EU profit (net)", P[H].sum() / P.sum(), own, lab)
        add("hubs' share of the groups' EU employees", g.loc[H, "n_employees"].sum() / g["n_employees"].sum(), own, lab)
        add("hubs' share of the groups' EU sales (corrected revenue)", g.loc[H, "sales_any_revenue"].sum() / g["sales_any_revenue"].sum(),
            own, lab)
        add("profit booked in the hubs ÷ profit the formula gives them", P[H].sum() / g.loc[H, "theoretical_profit"].sum(), own, lab)
        ppe_h = P[H].sum() / g.loc[H, "n_employees"].sum()
        ppe_o = P[~H].sum() / g.loc[~H, "n_employees"].sum()
        add("profit per employee, hubs (US$ thousand)", ppe_h / 1e3, own, lab)
        add("profit per employee, other EU countries (US$ thousand)", ppe_o / 1e3, own, lab)
        add("profit per employee, hubs ÷ other EU countries", ppe_h / ppe_o, own, lab)
        # Tax rates are the current tax ÷ profit over the profitable lines, pooled.
        pos = g[(g["profit_loss_before_income_tax"] > 0) & g["tax"].notna()]
        add("tax rate in the hubs, groups with an EU report (current tax ÷ profit, profitable lines)",
            pos.loc[pos["hub"], "tax"].sum() / pos.loc[pos["hub"], "profit_loss_before_income_tax"].sum(), own, lab)
        # The statistics below are for all groups of the sample with a line in the EU. They include the groups with a
        # single EU line and those whose EU lines add up to a loss, because the chapter states the tax rates for all
        # groups with public reports.
        every = "pooled over all groups with a line in the EU"
        H = e["hub"]
        add("groups with a line in the EU", int(e["company_key"].nunique()), "count", lab)
        # I count the groups with more profit than warranted in the hubs and those with less than warranted in the
        # other EU countries.
        gh = e[H].groupby("company_key")["misaligned_profit"].sum()
        go = e[~H].groupby("company_key")["misaligned_profit"].sum()
        add("groups with hub lines booking more than warranted there", int((gh > 0).sum()), f"of {len(gh)} groups with hub lines", lab)
        add("groups booking less than warranted in the other EU countries", int((go < 0).sum()), f"of {len(go)} groups with such lines", lab)
        pos = e[(e["profit_loss_before_income_tax"] > 0) & e["tax"].notna()]
        add("tax rate in the hubs, all groups with a line in the EU (current tax ÷ profit, profitable lines)",
            pos.loc[pos["hub"], "tax"].sum() / pos.loc[pos["hub"], "profit_loss_before_income_tax"].sum(), every, lab)
        add("tax rate in the other EU countries, all groups with a line in the EU (same definition)",
            pos.loc[~pos["hub"], "tax"].sum() / pos.loc[~pos["hub"], "profit_loss_before_income_tax"].sum(), every, lab)
        hub_pos = pos[pos["hub"]].copy()
        hub_pos["rate"] = hub_pos["tax"] / hub_pos["profit_loss_before_income_tax"]
        add("share of hub profit taxed below 15%, all groups with a line in the EU",
            hub_pos.loc[hub_pos["rate"] < 0.15, "profit_loss_before_income_tax"].sum()
            / hub_pos["profit_loss_before_income_tax"].sum(), "profitable hub lines of all groups with a line in the EU", lab)
        low = hub_pos[hub_pos["rate"] < 0.15]
        add("tax rate on the hub profit taxed below 15%, all groups with a line in the EU",
            low["tax"].sum() / low["profit_loss_before_income_tax"].sum(),
            "pooled, profitable hub lines below 15% of all groups with a line in the EU", lab)
        # The distribution of the EU profit by the rate at which it is taxed, for the hubs and the other EU countries.
        pos = pos.assign(rate=pos["tax"] / pos["profit_loss_before_income_tax"])
        for where, d in (("five hubs", pos[pos["hub"]]), ("other EU countries", pos[~pos["hub"]])):
            for lo_, hi_, band in RATE_BANDS:
                v = d.loc[(d["rate"] >= lo_) & (d["rate"] < hi_), "profit_loss_before_income_tax"].sum()
                bands.append(dict(sample=lab, where=where, band=band, profit_usd_bn=v / 1e9,
                                  share=v / d["profit_loss_before_income_tax"].sum()))
        v = s[s["iso_partner"] == "VNM"]
        add("groups with a Viet Nam line", v["company_key"].nunique(), "count", lab)
        add("groups booking less than warranted in Viet Nam", int((v["misaligned_profit"] < 0).sum()), "count", lab)
        add("profit booked in Viet Nam ÷ profit the formula gives it", v["profit_loss_before_income_tax"].sum() / v["theoretical_profit"].sum(),
            "pooled", lab)
    T = pd.DataFrame(rows)
    T.to_csv(CHAPTER_TABLES / "company_averages.csv", index=False)
    pd.DataFrame(bands).round(4).to_csv(CHAPTER_TABLES / "eu_profit_by_tax_rate.csv", index=False)
    return T


# %% MARK: 10. Sample counts
# The counts of the chapter's note on the sample and of the methodology note. A group's latest report is its report for
# the latest fiscal year in the panel. A report is usable when it enters the company estimates (the headline
# specification): it names at least two jurisdictions and gives the profit, the employees and the revenues of every
# line, and the group has a headquarters country. The usable report of a group is its latest usable report, counted
# where it is for 2023–2025. For the groups without a usable report, I count the reports with no more than one country
# (the residual line for the rest of the world is no country), the reports that leave out the profit, the employees or
# the revenues of some lines, and those that lack only the headquarters country. The counts for 2025 are the usable
# reports for fiscal year 2025, and the same restricted to the groups whose latest report is for 2025.
def sample_counts(panel, summary, cells):
    """Return the sample counts as rows of the table of company numbers."""
    rows = []

    def add(number, value, as_in_text, source="firm_cbcr_panel.csv; firm_year_summary (headline specification)"):
        rows.append(dict(number=f"sample: {number}", value=value, unit="count", as_in_text=as_in_text, source=source))

    latest = panel[panel["year"] == panel.groupby("company_key")["year"].transform("max")]
    L = latest[latest["year"].between(2023, 2025)]
    g = L.groupby("company_key")
    add("groups with a public report in the panel", panel["company_key"].nunique(), "1,469", "firm_cbcr_panel.csv")
    add("groups whose latest report is for 2023–2025", g.ngroups, "1,370", "firm_cbcr_panel.csv")
    latest_year = g["year"].first()
    add("groups whose latest report is for 2025", int((latest_year == 2025).sum()), "1,045", "firm_cbcr_panel.csv")
    taxplorer = g["source"].agg(lambda x: (x == "taxplorer").all())
    add("groups whose latest report (2023–2025) comes from the Taxplorer database (every line)", int(taxplorer.sum()),
        "1,014", "firm_cbcr_panel.csv")
    add("groups whose latest report (2023–2025) comes from the own collection", int((~taxplorer).sum()), "356",
        "firm_cbcr_panel.csv")
    last = summary.groupby("company_key")["year"].transform("max")
    x = summary[(summary["year"] == last) & summary["year"].between(2023, 2025)]
    ext, fin = x["sector"].isin(EXTRACTIVE_SECTORS), x["sector"].isin(FINANCIAL_SECTORS)
    add("groups with a usable report for 2023–2025", len(x), "684")
    add("groups with a usable report for 2023–2025: banks and insurers", int(fin.sum()), "63")
    add("groups with a usable report for 2023–2025: oil, gas and mining groups", int(ext.sum()), "28")
    add("groups with a usable report for 2023–2025 without oil, gas and mining groups (the companies analysed)",
        int((~ext).sum()), "656")
    # ---- the groups without a usable report, by what their latest report lacks ----
    unusable = sorted(set(g.groups) - set(x["company_key"]))
    U = L[L["company_key"].isin(unusable)]
    countries = U[U["iso_partner"] != "OTHER"].groupby("company_key")["iso_partner"].nunique().reindex(unusable).fillna(0)
    by = U.groupby("company_key")
    revenues_complete = by.apply(lambda d: d["unrelated_party_revenues"].notna().all() or d["total_revenues"].notna().all(),
                                 include_groups=False)
    incomplete = (by["profit_loss_before_income_tax"].apply(lambda v: v.isna().any())
                  | by["n_employees"].apply(lambda v: v.isna().any()) | ~revenues_complete).reindex(unusable)
    no_hq = by["hq_iso3"].apply(lambda v: v.isna().all()).reindex(unusable)
    single = countries <= 1
    add("groups without a usable report for 2023–2025", len(unusable), "686")
    add("groups without a usable report: no more than one country in the latest report", int(single.sum()), "328")
    add("groups without a usable report: leave out the employees, the profit or the revenues of some countries",
        int((~single & incomplete).sum()), "356")
    add("groups without a usable report: lack only the headquarters country", int((~single & ~incomplete & no_hq).sum()),
        "two")
    other = int((~single & ~incomplete & ~no_hq).sum())
    if other:
        print(f"  [check] {other} groups without a usable report fit none of the three reasons")
    # A single-country report comes from a group headquartered in another country where its one country differs from a
    # known headquarters country.
    one = (U[U["iso_partner"] != "OTHER"].groupby("company_key")
           .agg(country=("iso_partner", "first"), hq=("hq_iso3", "first")).reindex(countries[countries == 1].index))
    foreign = one["hq"].notna() & (one["country"] != one["hq"])
    add("groups without a usable report: single-country reports of groups headquartered in another country",
        int(foreign.sum()), "298 of 328")
    add("groups without a usable report: single-country reports of groups headquartered in another country, only Spain",
        int((foreign & (one["country"] == "ESP")).sum()), "253")
    # ---- the reports for 2025 ----
    y = summary[summary["year"] == 2025]
    e2, f2 = y["sector"].isin(EXTRACTIVE_SECTORS), y["sector"].isin(FINANCIAL_SECTORS)
    add("usable reports for 2025", len(y), "")
    add("usable reports for 2025: oil, gas and mining groups", int(e2.sum()), "")
    add("usable reports for 2025: banks and insurers", int(f2.sum()), "40")
    add("usable reports for 2025 without banks, insurers and oil, gas and mining groups (the sample of the estimates)",
        int((~e2 & ~f2).sum()), "455")
    # A group can have a usable report for 2025 and a later report (for fiscal year 2026), so I also count the usable
    # reports for 2025 among the groups whose latest report is for 2025.
    y25 = y[y["company_key"].isin(latest_year[latest_year == 2025].index)]
    add("usable reports for 2025 of the groups whose latest report is for 2025", len(y25), "510")
    add("usable reports for 2025 of the groups whose latest report is for 2025: oil, gas and mining groups",
        int(y25["sector"].isin(EXTRACTIVE_SECTORS).sum()), "15")
    c25 = cells[(cells["year"] == Y_FIRM) & ~cells["sector"].isin(FINANCIAL_SECTORS | EXTRACTIVE_SECTORS)]
    add("usable reports for 2025 in the sample of the estimates with at least one EU line (the sample of Table 3.1)",
        c25.loc[c25["iso_partner"].isin(EU), "company_key"].nunique(), "449 of the remaining 455",
        f"firm_cell_misalignment__{SPEC_REPORT}.csv")
    # ---- the line for the rest of the world in the reports analysed ----
    meta = pd.read_csv(META)
    u = x[~ext][["company_key", "year"]].merge(meta[["company_key", "year", "other_share_of_revenue"]], how="left")
    has = u["other_share_of_revenue"] > 0
    add("reports analysed with a line for the rest of the world holding revenue", int(has.sum()), "",
        "firm_year_meta.csv")
    rows.append(dict(number="sample: share of the reports analysed with such a line", value=has.mean(), unit="share",
                     as_in_text="72%", source="firm_year_meta.csv"))
    rows.append(dict(number="sample: median share of revenue in that line, reports with one",
                     value=u.loc[has, "other_share_of_revenue"].median(), unit="share", as_in_text="70%",
                     source="firm_year_meta.csv"))
    return rows


# %% MARK: 11. Company numbers quoted in the chapter text and the methodology note
# The table gives every company number of the chapter text, its notes and the methodology note that no other table of
# this script holds, with its value, the form in which the text gives it and its source. Euro amounts of the 2025
# reports use the 2025 average rate of Table 3.1 (EUR_PER_USD).
def company_numbers(donuts, averages, cells_csv, panel, europe, cov_rest, counts):
    """Write the company numbers of the text (company_numbers_in_text.csv). The arguments are the table of Figure 3.1,
    the averages across all groups, the headline cells, the panel, the European table with the coverage of the activity
    the groups of UNSCALED_GROUPS leave (section 8) and the sample counts (section 10)."""
    rows = []

    def add(number, value, unit, as_in_text, source):
        rows.append(dict(number=number, value=value, unit=unit, as_in_text=as_in_text, source=source))

    # ---- Figure 3.1: hub shares of EU profit and the tax rate there ----
    d = donuts.set_index("company")
    fig9 = "EU_profit_booked_in_the_hub.csv"
    for comp, label in [("Apple", "97%"), ("Microsoft", "96%"), ("TE Connectivity", "more than 100% (105%)"),
                        ("Kraft Heinz", "more than 100% (107%)"), ("IKEA stores (Ingka)", "62%")]:
        add(f"{comp}: share of EU profit booked in {d.at[comp, 'hub']}", d.at[comp, "hub_share_uncapped"], "share", label, fig9)
    for comp, label in [("Microsoft", "14.1%"), ("IKEA stores (Ingka)", "7.4%"), ("Apple", "13.8% (Figure 3.1)"),
                        ("Kraft Heinz", "2.7% (Figure 3.1)")]:
        add(f"{comp}: tax rate in {d.at[comp, 'hub']} (accrued tax ÷ profit)", d.at[comp, "hub_rate_shown"], "share", label, fig9)
    # ---- Figure 3.2: profit per employee in the hub ÷ in the other EU countries (the EU lines of Figure 3.1) ----
    for name in PPE_COMPANIES:
        src, key, hub = DONUT_CHAPTER[name]
        e, _ = eu_lines(report_panel(panel, cells_csv, src, key), src, key)
        h, o = e.loc[hub], e.drop(index=hub)
        ppe_o = o["profit"].sum() / o["employees"].sum()
        ratio = (h["profit"] / h["employees"]) / ppe_o
        if o["profit"].sum() > 0:
            add(f"{name}: profit per employee in the hub ÷ in the other EU countries", ratio, "ratio",
                f"{ratio:.0f} times", "EU lines of Figure 3.1 (pcbcr_ireland_fy25_*.csv; firm_cbcr_panel.csv)")
        else:
            add(f"{name}: profit of the other EU countries taken together", o["profit"].sum(), "US$",
                "reports losses in its other EU countries taken together",
                "EU lines of Figure 3.1 (pcbcr_ireland_fy25_*.csv; firm_cbcr_panel.csv)")
    # ---- Apple in Ireland and Viet Nam (headline cells, FY2025) ----
    a = cells_csv[(cells_csv.company_key == "APPLE")]
    a = a[a.year == a.year.max()]
    t = a[["n_employees", "profit_loss_before_income_tax"]].sum()
    irl, vnm = a[a.iso_partner == "IRL"].iloc[0], a[a.iso_partner == "VNM"].iloc[0]
    src = f"firm_cell_misalignment__{SPEC_REPORT}.csv (Apple, FY{int(irl.year)})"
    add("Apple: profit booked in Ireland above what employees and sales warrant", irl.misaligned_profit, "US$",
        f"US${irl.misaligned_profit / 1e9:.1f} billion", src)
    add("Apple: employees in Viet Nam", vnm.n_employees, "persons", f"{vnm.n_employees:,.0f}", src)
    add("Apple: employees worldwide (report total)", t["n_employees"], "persons", "166,000", src)
    add("Apple: Viet Nam's share of employees", vnm.n_employees / t["n_employees"], "share",
        f"{100 * vnm.n_employees / t['n_employees']:.2f}%", src)
    add("Apple: Viet Nam's share of revenues (revenue booked there ÷ consolidated revenue)",
        vnm.sales_any_revenue / vnm.consolidated_revenue_usd, "share",
        f"at least {100 * vnm.sales_any_revenue / vnm.consolidated_revenue_usd:.2f}%", src)
    add("Apple: Viet Nam's share of profit", vnm.profit_loss_before_income_tax / t["profit_loss_before_income_tax"], "share",
        f"{100 * vnm.profit_loss_before_income_tax / t['profit_loss_before_income_tax']:.2f}%", src)
    add("Apple: profit booked in Viet Nam ÷ the profit its activity warrants",
        vnm.profit_loss_before_income_tax / vnm.theoretical_profit, "ratio", "about a seventh", src)
    add("Apple: profit missing in Viet Nam", -vnm.misaligned_profit, "US$", f"US${-vnm.misaligned_profit / 1e6:,.0f} million", src)
    # ---- averages across all groups ----
    A = averages[averages["sample"] == "no banks, insurers or extractive groups"].set_index("statistic")["value"]
    for stat, label in [("groups with an EU report (≥2 EU lines)", "554"),
                        ("hubs' share of the groups' combined EU profit (net)", "45%"),
                        ("hubs' share of the groups' EU employees", "a sixth of their share of the EU profit"),
                        ("profit booked in the hubs ÷ profit the formula gives them", "1.9 times"),
                        ("groups with a Viet Nam line", "159"),
                        ("profit booked in Viet Nam ÷ profit the formula gives it", "58%"),
                        ("groups with a line in the five hubs", "426"),
                        ("groups booking more profit in the five hubs than their activity there warrants", "164"),
                        ("groups booking more than twice the profit their activity in the five hubs warrants", "109"),
                        ("groups with a line in the EU", "all groups with public reports"),
                        ("share of hub profit taxed below 15%, all groups with a line in the EU", "78%"),
                        ("tax rate on the hub profit taxed below 15%, all groups with a line in the EU", "11.8%"),
                        ("tax rate in the hubs, all groups with a line in the EU (current tax ÷ profit, profitable lines)",
                         "13.8%"),
                        ("tax rate in the other EU countries, all groups with a line in the EU (same definition)", "19.7%"),
                        ("tax rate in the hubs, groups with an EU report (current tax ÷ profit, profitable lines)", "13.8%"),
                        ("profit per employee, hubs (US$ thousand)", "US$309,000"),
                        ("profit per employee, other EU countries (US$ thousand)", "US$29,000"),
                        ("profit per employee, hubs ÷ other EU countries", "11 times")]:
        add(f"all groups: {stat}", A[stat], "count" if stat.startswith("groups") else "value", label,
            "company_averages.csv (no banks, insurers or extractive groups)")
    # ---- the paragraph on Table 3.1 ----
    S = pd.read_csv(CHAPTER_TABLES / "table1_comparison_stats.csv")
    for sample in ("Table 3.1 countries", "EU-27"):
        t = S[S["sample"] == sample].set_index("statistic")
        lo, hi = t.loc["coverage, lowest (%)"], t.loc["coverage, highest (%)"]
        add(f"{sample}: share of activity the reports cover, lowest and highest", f"{lo['value']:.1f} / {hi['value']:.1f}", "%",
            f"between {lo['value']:.0f}% ({lo['country']}) and {hi['value']:.0f}% ({hi['country']})", "table1_comparison_stats.csv")
        add(f"{sample}: correlation of the country-level estimates and the scaled public reports",
            t.at["correlation of the two columns", "value"], "coefficient", f"{t.at['correlation of the two columns', 'value']:.2f}",
            "table1_comparison_stats.csv")
        add(f"{sample}: rank correlation of the two columns", t.at["rank correlation of the two columns", "value"], "coefficient",
            f"{t.at['rank correlation of the two columns', 'value']:.2f}", "table1_comparison_stats.csv")
        add(f"{sample}: countries with the same sign in both columns", t.at["countries with the same sign in both columns", "value"],
            "countries", f"{t.at['countries with the same sign in both columns', 'value']:.0f} of {t.at['countries', 'value']:.0f}",
            "table1_comparison_stats.csv")
        add(f"{sample}: sums of the two columns (EUR bn)",
            f"{t.at['sum of the country-level estimates (EUR bn)', 'value']:.2f} / {t.at['sum of the public reports, scaled up (EUR bn)', 'value']:.2f}",
            "EUR bn", f"€{t.at['sum of the country-level estimates (EUR bn)', 'value']:.1f} billion against "
            f"€{t.at['sum of the public reports, scaled up (EUR bn)', 'value']:.1f} billion", "table1_comparison_stats.csv")
    # ---- facts from company documents ----
    f = pd.read_csv(INPUTS / "company_report_facts.csv").set_index("company_key")
    # ---- TE Connectivity in Luxembourg, the example of the executive summary and of the text on Figure 3.2 ----
    src, key, hub = DONUT_CHAPTER["TE Connectivity"]
    e, fy = eu_lines(report_panel(panel, cells_csv, src, key), src, key)
    lux, deu = e.loc["LUX"], e.loc["DEU"]
    te = f"EU lines of TE Connectivity's FY{fy} report (firm_cbcr_panel.csv)"
    add("TE Connectivity: profit booked in Luxembourg", lux["profit"], "US$", f"US${lux['profit'] / 1e6:,.0f} million", te)
    add("TE Connectivity: employees in Luxembourg / in all its EU countries", f"{lux['employees']:.0f} / {e['employees'].sum():.0f}",
        "persons", f"{lux['employees']:.0f} of its more than {1000 * (e['employees'].sum() // 1000):,.0f} EU employees", te)
    add("TE Connectivity: profit per employee in Luxembourg", lux["profit"] / lux["employees"], "US$",
        f"US${lux['profit'] / lux['employees'] / 1e6:,.0f} million", te)
    add("TE Connectivity: profit per employee in Germany", deu["profit"] / deu["employees"], "US$",
        f"US${deu['profit'] / deu['employees']:,.0f}", te)
    add("TE Connectivity: Germany's share of its EU employees", deu["employees"] / e["employees"].sum(), "share",
        "almost a third", te)
    top = f.loc["INGKA"]
    add("IKEA stores (Ingka): top-up tax disclosed for Ireland", top.value * 1e6, "EUR", "€19 million",
        f"{top.document}, {top.page} ({top.url})")
    # ---- the note to Table 3.1: Novo Nordisk and Denmark ----
    c = cells_csv[cells_csv["year"] == Y_FIRM]
    n = c[(c["company_key"] == "NOVO NORDISK") & (c["iso_partner"] == "DNK")].iloc[0]
    src = f"firm_cell_misalignment__{SPEC_REPORT}.csv (Novo Nordisk, Denmark, FY{Y_FIRM})"
    v = EUR_PER_USD * n["profit_loss_before_income_tax"]
    add("Novo Nordisk: profit booked in Denmark", v, "EUR", f"€{v / 1e9:.1f} billion", src)
    add("Novo Nordisk: profit booked in Denmark ÷ the profit its employees and sales there warrant",
        n["profit_loss_before_income_tax"] / n["theoretical_profit"], "ratio", "about twice", src)
    v = -EUR_PER_USD * n["revenue_gain_from_ut_usd"]
    add("Novo Nordisk: tax Denmark would collect less from it under unitary taxation", v, "EUR", f"€{v / 1e9:.1f} billion",
        src)
    dk = europe.loc["DNK"]
    add("Denmark: groups with a Danish line in the reports for 2025", dk["pcbcr_groups"], "count",
        f"{dk['pcbcr_groups']:.0f}", "europe_ut_pcbcr_scaled.csv")
    v = EUR_PER_USD * dk["pcbcr"] * 1e9
    add("Denmark: net result of these groups under unitary taxation (unscaled)", v, "EUR",
        f"€{abs(v) / 1e9:.1f} billion", "europe_ut_pcbcr_scaled.csv")
    cov = (dk["employees_covered"] + dk["revenues_covered"]) / 2
    add("Denmark: share of multinational activity the reports cover", cov, "share", f"{100 * cov:.0f}%",
        "europe_ut_pcbcr_scaled.csv")
    v = EUR_PER_USD * dk["pcbcr"] / cov * 1e9
    add("Denmark: net result scaled up with that coverage", v, "EUR", f"−€{abs(v) / 1e9:.1f} billion",
        "europe_ut_pcbcr_scaled.csv")
    add("Denmark: coverage of the activity Novo Nordisk leaves, with which the other groups are scaled",
        cov_rest["DNK"], "share", f"{100 * cov_rest['DNK']:.0f}%", "europe_table (this script)")
    # ---- the note on the bias of the scaling: coverage and the hubs' shares by headquarters ----
    # The sample is that of Table 3.1 (reports for 2025, without banks, insurers and oil, gas and mining groups), their
    # lines in EU countries. The coverage compares the groups' EU employees with those of all multinationals in the
    # OECD data for 2023, by where their headquarters are. The hubs' shares leave out J&F (UNVERIFIED).
    t1 = c[~c["sector"].isin(FINANCIAL_SECTORS | EXTRACTIVE_SECTORS) & c["iso_partner"].isin(EU)]
    oc = pd.read_csv(EXCL_RESOURCE, usecols=["iso_parent", "iso_partner", "year", "n_employees"], low_memory=False)
    oc = oc[(oc["year"] == Y_OECD) & oc["iso_partner"].isin(EU)]
    src = f"firm_cell_misalignment__{SPEC_REPORT}.csv (FY{Y_FIRM}); cbcr_main_excl_resource.csv ({Y_OECD})"
    for lab, inside in (("outside the EU", False), ("in the EU", True)):
        v = (t1.loc[t1["hq_iso3"].isin(EU) == inside, "n_employees"].sum()
             / oc.loc[oc["iso_parent"].isin(EU) == inside, "n_employees"].sum())
        add(f"share of the EU employees of multinationals headquartered {lab} that the reports for 2025 cover", v,
            "share", f"{100 * v:.0f}%", src)
    t1 = t1[~t1["company_key"].isin(UNVERIFIED)]
    src = f"firm_cell_misalignment__{SPEC_REPORT}.csv (FY{Y_FIRM}, without J&F)"
    hq_groups = (("in the United States", t1["hq_iso3"].eq("USA")),
                 ("elsewhere outside the EU", ~t1["hq_iso3"].isin(EU) & t1["hq_iso3"].ne("USA")),
                 ("in the EU", t1["hq_iso3"].isin(EU)))
    for col, what in (("profit_loss_before_income_tax", "EU profit"), ("n_employees", "EU employees")):
        for lab, m in hq_groups:
            d = t1[m]
            v = d.loc[d["iso_partner"].isin(EU_HUBS), col].sum() / d[col].sum()
            add(f"groups headquartered {lab}: share of their {what} in the five EU hubs (reports for 2025)", v, "share",
                f"{100 * v:.0f}%", src)
    # ---- GSK in Belgium and in France, Germany, Italy and Spain ----
    # The rate in the four countries is their accrued tax summed ÷ their profit summed, like the pooled rates of the
    # averages. I take the accrued tax from the panel, because the single rates of the cell table are bounded at zero
    # and Spain's accrued tax is negative.
    g = cells_csv[cells_csv["company_key"] == "GSK"]
    fy = int(g["year"].max())
    g = g[g["year"] == fy].set_index("iso_partner")
    src = f"firm_cell_misalignment__{SPEC_REPORT}.csv (GSK, FY{fy})"
    bel = g.loc["BEL"]
    v = EUR_PER_USD * bel["profit_loss_before_income_tax"]
    add("GSK: profit booked in Belgium", v, "EUR", f"€{v / 1e9:.1f} billion", src)
    add("GSK: profit booked in Belgium ÷ the profit its employees and sales there warrant",
        bel["profit_loss_before_income_tax"] / bel["theoretical_profit"], "ratio", "about five times", src)
    add("GSK: tax rate in Belgium (accrued tax ÷ profit)", bel["etr_accrued_cell"], "share",
        f"{100 * bel['etr_accrued_cell']:.0f}%", src)
    add("GSK: statutory corporate income tax rate of Belgium", bel["cit"], "share", f"{100 * bel['cit']:.0f}%", src)
    four = g.loc[["FRA", "DEU", "ITA", "ESP"]]
    add("GSK: profit booked in France, Germany, Italy and Spain ÷ the profit its activity there warrants",
        four["profit_loss_before_income_tax"].sum() / four["theoretical_profit"].sum(), "ratio", "a third", src)
    pg = panel[(panel["company_key"] == "GSK") & (panel["year"] == fy)].set_index("iso_partner")
    v = pg.loc[four.index, "income_tax_accrued_current_year"].sum() / four["profit_loss_before_income_tax"].sum()
    add("GSK: tax rate in France, Germany, Italy and Spain (accrued tax ÷ profit, pooled)", v, "share",
        f"{100 * v:.0f}%", src + "; firm_cbcr_panel.csv (accrued tax)")
    # ---- the methodology note: Microsoft's revenues and J&F's Luxembourg line ----
    m = c[c["company_key"] == "MICROSOFT"]
    src = f"firm_cell_misalignment__{SPEC_REPORT}.csv (Microsoft, FY{Y_FIRM})"
    v = m["sales_revenue_reported"].sum()
    add("Microsoft: total revenues summed over the lines of its report", v, "US$", f"US${v / 1e9:.1f} billion", src)
    v = m["consolidated_revenue_usd"].iloc[0]
    add("Microsoft: consolidated revenue", v, "US$", f"US${v / 1e9:.1f} billion", src + "; firm_consolidated_revenue.csv")
    j = panel[(panel["company_key"] == "J&F") & (panel["iso_partner"] == "LUX")]
    j = j[j["year"] == j["year"].max()].iloc[0]
    src = f"firm_cbcr_panel.csv (J&F, Luxembourg, FY{int(j['year'])}, report in {j['currency']})"
    v = j["total_revenues"] * j["fx_lcu_per_usd"]
    add("J&F: revenues of its Luxembourg line, in the report's currency", v, j["currency"], f"€{v / 1e9:.0f} billion", src)
    add("J&F: employees of its Luxembourg line", j["n_employees"], "persons", f"{j['n_employees']:.0f}", src)
    rows += counts
    out = pd.DataFrame(rows)
    out.to_csv(CHAPTER_TABLES / "company_numbers_in_text.csv", index=False)
    print(f"  {len(out)} company numbers of the text -> company_numbers_in_text.csv")
    return out


# %% MARK: 12. Run
def main():
    CHAPTER_FIGS.mkdir(parents=True, exist_ok=True)
    CHAPTER_TABLES.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(PANEL, low_memory=False)
    print("[9] unitary taxation per group")
    cells = run_estimates(panel)
    # The later steps read the cell tables and the summary as written, like any other user of these tables.
    cells_csv = {s: pd.read_csv(FIRM_TABLES / f"firm_cell_misalignment__{s}.csv", low_memory=False) for s in SPECS}
    summary = pd.read_csv(FIRM_TABLES / f"firm_year_summary__{SPEC_REPORT}.csv")
    print("[9] Figure 3.1")
    donuts = figure_9(panel, cells_csv[SPEC_REPORT])
    print("[9] Figure 3.2")
    figure_10(panel, cells_csv[SPEC_REPORT])
    print("[9] Figure 3.3")
    figure_11(cells[SPEC_REPORT])
    print("[9] Table 3.1")
    europe, cov_rest = table_1(cells_csv)
    print("[9] averages across all groups")
    averages = company_averages(cells_csv[SPEC_REPORT], panel)
    print("[9] sample counts and company numbers of the text")
    counts = sample_counts(panel, summary, cells_csv[SPEC_REPORT])
    company_numbers(donuts, averages, cells_csv[SPEC_REPORT], panel, europe, cov_rest, counts)
    print(f"\nOutputs in {FIRM_TABLES}, {CHAPTER_FIGS}, {CHAPTER_TABLES}")


if __name__ == "__main__":
    main()
