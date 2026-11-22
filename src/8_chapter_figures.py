# %%
"""
8 — Chapter figures and tables.

This script makes the figures, tables and numbers of chapter 2 ("Corporate tax abuse") of The State of Tax Justice
2026 that come from the aggregate country-by-country reporting (CbCR) data. These are the net Sankeys of the profit
and the tax shifted into tax havens (Figures 2.1 and 2.2), the negotiation blocs (Figure 2.3), the shifted profit and
the tax revenue lost over time and the losses at 2016 tax rates (Figures 2.4 and 2.5), the race to the bottom in
statutory rates (Figures 2.6 and 2.7), the statistics of the US Internal Revenue Service (IRS) on the profit US
multinationals book at rates below 15% (Figure 2.8 and a footnote) and who owns US corporate equity (Figure 2.9). The
script also writes the world totals by year, the robustness check of the chapter's footnote (profit counted as
shifted only where it ends up in a low-taxed destination) and a table of every number the chapter text quotes from
these data. For the methodology note, it writes the result under the rule of earlier editions (profit counted as
shifted only into cells with an effective tax rate of at most 15%), the Japan and Canada footnote, the Appendix E
figure that compares sales by origin and by destination on the sample with imputed rows, and a table of the note's
numbers that the run produces but no results table holds.

Conventions. All results use the headline estimate. In it, economic activity is measured by employees and sales by
destination, the sample holds only the reported cells, resources are excluded, the effective tax rates differ
between a country's own groups and foreign groups (domestic/foreign rates), and the profit a country gets back is
priced at its statutory rate, the profit it loses at its effective rate. The reference year is 2023 and amounts are
in US$ at constant 2025 prices. Country figures are those of the multinationals in the country-by-country data
(unscaled). I scale world, bloc and income-group totals to all multinationals with the uniform world factor of 7a
(the scaled net divided by the sample net). The factor is the same for every country, so gains and losses keep
their proportions. The Appendix E figure is the one exception to the sample rule: it uses the sample with imputed
rows, scaled with that sample's own world factor. The chapter figures carry no titles, notes or sources: those go into
the titles and captions of the chapter document.

Section outline (numbers match the cell headings below):
1. Setup.
2. World totals by year.
3. Figures 2.1 and 2.2: net Sankeys of profit and tax.
4. Figure 2.3: negotiation blocs.
5. Figures 2.4 and 2.5: shifted profit and tax revenue lost over time.
6. Figures 2.6 and 2.7: race to the bottom.
7. Figure 2.8 and footnote: IRS low-tax shares of US multinationals.
8. Figure 2.9: who owns US corporate equity.
9. Robustness: profit shifted only into low-taxed destinations.
10. Methodology-note footnote: Japan and Canada with their own statistics.
11. Methodology note, Appendix E: sales by origin and by destination on the sample with imputed rows.
12. Numbers quoted in the chapter.
13. Numbers quoted in the methodology note.
   13.1 Sensitivities of the methodology note.
14. Main.

Pipeline step 8 — after 7b, before 9.

Reads:
  output/estimates/reported_only/2_resources_excluded/tables/summary_country_year_long.csv   — country-year estimates (script 6)
  output/estimates/reported_only/2_resources_excluded/tables/excl_resource/misalignment__<headline>.csv
                                                         — misaligned profit per headquarters × jurisdiction × year (script 5)
  output/estimates/with_imputed_rows/2_resources_excluded/tables/summary_country_year_long.csv
                                                         — country-year estimates of the sample with imputed rows (script 6)
  output/paper/main_text/tables/scaleup_yearly.csv       — uniform world factor and coverage per year (7a)
  output/paper/main_text/tables/host_scale_factors.csv   — the world factor per country-year, for both samples (7a)
  output/variants/{irs15_gate30,irs15_gate}/estimates/reported_only/2_resources_excluded/tables/summary_country_year_long.csv
                                                         — the runs with low-taxed destinations only (robustness)
  output/{,variants/mkt_own_jpn/,variants/mkt_own_can/}estimates/reported_only/2_resources_excluded/
      tables/excl_resource/country_estimates__<headline>.csv — the headline run and the Japan / Canada variants
  output/variants/{res_no_tax_inference,res_no_inferred_companies,accrued_tax}/estimates/reported_only/
      2_resources_excluded/tables/summary_country_year_long.csv — the sensitivities of the methodology note
      (with data/final/cbcr_main_excl_resource__res_no_inferred_companies.csv)
  data/intermediate/destination_based_sales.csv, destination_based_sales_mkt_own_{jpn,can}.csv
                                                         — the market key and the keys from national statistics (step 1a)
  data/intermediate/irs_soi_cbcr_table4_long.csv   — IRS SOI CbCR Table 4, 2017–2023: profit and tax of US groups by
                                                    jurisdiction and effective-tax-rate band (written by step 1)
  data/intermediate/irs_low_tax_destinations.csv    — IRS low-tax shares (step 1)
  data/raw/tax_rates/taxfoundation_cit_rates_1980-2023.xlsx — statutory CIT rates 1980–2023 (Tax Foundation)
  data/raw/country_info/oecd_members_2026.csv, un_g77_members.csv — OECD and G77 members
  data/raw/context/corporate_tax_incidence/{equity_ownership_shares,incidence_assumptions}.csv — tax incidence
  For the methodology note's numbers: data/raw/cbcr/oecd_cbcr_tableI_2026-08.csv (config.cbcr_data, the OECD file as
  published), data/final/{cbcr_main,cbcr_main_allsubgroupsonly,cbcr_main_disaggregated,cbcr_main_excl_resource}.csv
  (steps 1, 2 and 4), output/diagnostics/haven_loss_swings/haven_loss_swings.csv and
  output/diagnostics/cbcr_profit_imputation/uk_domestic_profit_carryforward.csv (step 1).
Writes (to output/chapter/, every figure as PNG and PDF):
  figures/figB4_sankey_net_havens_2023        — Figure 2.1: net profit shifted from the OECD and the G77 into tax havens
  figures/figB7_sankey_tax_only_2023          — Figure 2.2: tax revenue lost and the tax the havens collect
  figures/figB2u_blocs_ut_gains_2023          — Figure 2.3: tax revenue the countries of the world and of each bloc
                                                (havens in their blocs) would gain (+) and lose (−) under unitary
                                                taxation, and the net gain as % of the tax paid
  figures/figS1_shifted_profit                — Figure 2.4: profit shifted (gross) and tax revenue lost by the losing
                                                countries
  figures/figS4_tax_losses_2016_rates         — Figure 2.5: tax revenue the losing countries lose to profit shifting
                                                and, on top, to the lower tax rates since 2016
  figures/figC9_race_to_the_bottom            — Figure 2.6: statutory CIT rates 1980–2023
  figures/figC9b_rate_bands_2023_vs_1980      — Figure 2.7: how much more likely rates below 15%, 25% and 35% (and of
                                                35% and above) are in 2023 than in 1980
  figures/figC8_irs_low_tax_shares_recipients_2023 — Figure 2.8: profit taxed below 15% in the recipients
  figures/figC10_who_pays_corporate_tax       — Figure 2.9: who owns US corporate equity
  figures/fig09_origin_dest_revenue_no_nexus  — methodology note, Figure E3: change in tax revenue by income group with
                                                sales by origin and by destination, sample with imputed rows
  tables/sankey_net_havens_2023_keys.csv, sankey_net_havens_tax_2023_keys.csv, blocs_2023_keys.csv,
         shifted_profit_fig_data.csv, tax_losses_by_year.csv, tax_losses_2016_rates_by_year.csv,
         cit_long_run_by_year.csv, irs_rate_on_profit_below15_by_year.csv, irs_low_tax_shares_recipients_2023_keys.csv,
         irs_low_tax_share_vs_etr_2023.csv, who_pays_corporate_tax.csv   — the data behind the figures and the footnote
  tables/t4_world_by_year.csv                                        — world totals by year
  tables/gate_robustness_world_by_year.csv                           — robustness of the chapter's footnote
  tables/classic_rule_etr15_world_by_year.csv                        — the rule of earlier editions (methodology note)
  tables/footnote_own_statistics_jpn_can.csv                         — Japan and Canada footnote
  tables/chapter_numbers_2023.csv                                    — every number the chapter text quotes, with its source
  tables/methodology_note_numbers.csv                                — the methodology note's numbers that the run
                                                                       produces but no results table holds
Usage:
  python src/8_chapter_figures.py   — from the repository root

Author: Tax Justice Network.
Created: 2026-11-02.  Last updated: 2026-11-23.
"""

# %% MARK: 1. Setup
import sys
from functools import lru_cache
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path as MPath
from matplotlib.transforms import Bbox, blended_transform_factory
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import config  # noqa: E402
import _host_coverage as hc  # noqa: E402
from _brand import apply_tjn_style, HATCH_CYCLE  # noqa: E402
from _sotj_palette import (BLOC, BLUE, EARTH_GREEN, GAIN, GOLD, INK, LOSS, PURPLE, SCALED,  # noqa: E402
                           WEALTH_GROUP, shade, tint)

apply_tjn_style()   # brand fonts and colours, and every PNG is also saved as a PDF

FIG = ROOT / "output/chapter/figures"
TAB = ROOT / "output/chapter/tables"
KEY_LABEL = "Headline estimate"
HEADLINE = "sales_employees_destmnedds__etrdef_domfor__etrmax_inf__loss_cit_gain_etr"
ESTIMATES = ROOT / "output/estimates"
RUN_TABLES = "reported_only/2_resources_excluded/tables"
MISALIGNMENT = ESTIMATES / RUN_TABLES / "excl_resource" / f"misalignment__{HEADLINE}.csv"
MISALIGNMENT_COLS = ["iso_parent", "iso_partner", "partner_jurisdiction", "year", "misaligned_profit",
                     "profit_loss_excl_resource", "theoretical_profit", "wb_income_group", "cit", "etr_domfor_excl_resource"]
SUMMARY_COLS = ["formula_name", "etr_name", "rate_mode", "year", "iso_partner", "partner_jurisdiction", "wb_income_group",
                "region_tjn", "eu27", "revenue_gain_from_ut", "tax_revenue_gain", "tax_revenue_loss", "positive_misalignment",
                "negative_misalignment", "reported_profit", "current_tax_paid_cash_musd"]

Y = config.last_year
YEARS = list(config.ANALYSIS_YEARS)
DEFL = config.deflator_to_base()                # factor per year to constant BASE_YEAR US$
DEFL_Y = DEFL[Y]
HAV = set(config.TAX_HAVENS_REPRESENTATION)
OECD = set(pd.read_csv(ROOT / "data/raw/country_info/oecd_members_2026.csv")["iso3"])
G77 = set(pd.read_csv(ROOT / "data/raw/country_info/un_g77_members.csv", comment="#")["iso3"])
SCALEUP = pd.read_csv(ROOT / "output/paper/main_text/tables/scaleup_yearly.csv").set_index("year")
SF = SCALEUP["scaled_up_net_uniform_bn"] / SCALEUP["revenue_gain_net_bn"]   # uniform world factor per year
SF_Y = float(SF[Y])
COV = SCALEUP["coverage"]                       # share of multinational profit covered by the country-by-country sample
GRP = {"high_income": "High income", "upper_middle_income": "Upper middle income",
       "lower_middle_income": "Lower middle income", "low_income": "Low income", "tax_haven": "Tax havens"}


def headline_summary(estimates=ESTIMATES):
    """Return the country-year estimates of the headline specification from the script-6 summary of a run."""
    d = pd.read_csv(estimates / RUN_TABLES / "summary_country_year_long.csv", low_memory=False, usecols=SUMMARY_COLS)
    return d[(d["formula_name"] == "sales_employees_destmnedds") & (d["etr_name"] == "domfor")
             & (d["rate_mode"] == "loss_cit_gain_etr")].copy()


IRS_TABLE4 = ROOT / "data/intermediate/irs_soi_cbcr_table4_long.csv"


@lru_cache(maxsize=None)
def irs_table4_long():
    """Return IRS SOI CbCR Table 4 for every tax year. It has one row per year × effective-tax-rate band × jurisdiction,
    with the profit and the income tax accrued of US groups' sub-groups in US$ (NaN where the IRS suppresses a cell or
    leaves it blank)."""
    return pd.read_csv(IRS_TABLE4)


def irs_table4(year):
    """Return IRS SOI CbCR Table 4 of one tax year."""
    d = irs_table4_long()
    return d[d["year"] == year].reset_index(drop=True)


def ribbon(ax, x0, y0a, y0b, x1, y1a, y1b, color, alpha=0.55):
    """Draw a Sankey ribbon from the interval (y0a, y0b) at x0 to (y1a, y1b) at x1."""
    cx0, cx1 = x0 + 0.4 * (x1 - x0), x1 - 0.4 * (x1 - x0)
    verts = [(x0, y0b), (cx0, y0b), (cx1, y1b), (x1, y1b), (x1, y1a), (cx1, y1a), (cx0, y0a), (x0, y0a), (x0, y0b)]
    codes = [MPath.MOVETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4, MPath.LINETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4, MPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MPath(verts, codes), facecolor=color, edgecolor="none", alpha=alpha))


def save_cropped(fig, ax, fpath):
    """Save a figure cropped to what is drawn on its axes (bars, ribbons, lines and labels), so that the picture has no
    empty margins. The empty part of the axes would otherwise count as content."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    boxes = [a.get_window_extent(r) for a in ax.texts + ax.patches + ax.lines]
    box = Bbox.union(boxes).transformed(fig.dpi_scale_trans.inverted())
    fig.savefig(fpath, dpi=170, bbox_inches=box.padded(0.03))


def spread(ys, min_sp):
    """Push label positions (top to bottom) apart to at least min_sp, moving lower labels down."""
    ys = list(ys)
    for j in range(1, len(ys)):
        ys[j] = min(ys[j], ys[j - 1] - min_sp)
    return ys


# %% MARK: 2. World totals by year
def world_totals():
    """Write the world totals by year, gross (the gains of the countries that lose today) and net, unscaled and
    scaled, from the scale-up table of 7a, in US$bn at 2025 prices. The table carries no averages over several years,
    because the chapter shows aggregates year by year."""
    rows = [dict(spec=KEY_LABEL, year=y, gross_unscaled=SCALEUP.loc[y, "revenue_gain_winners_bn"],
                 net_unscaled=SCALEUP.loc[y, "revenue_gain_net_bn"], gross_scaled=SCALEUP.loc[y, "scaled_up_winners_bn"],
                 net_scaled=SCALEUP.loc[y, "scaled_up_net_bn"], scale_factor=SCALEUP.loc[y, "scale_factor"])
            for y in SCALEUP.index]
    pd.DataFrame(rows).round(1).to_csv(TAB / "t4_world_by_year.csv", index=False)


# %% MARK: 3. Figures 2.1 and 2.2: net Sankeys of profit and tax
# The left side shows the two blocs of non-haven countries with their net profit shifted out (shifted out less
# shifted in). The right side shows the tax havens with a net inflow, the eight largest by name and the rest pooled.
# I spread each bloc's net loss over the havens in proportion to the bloc's gross bilateral flows to each haven. The
# gross flows follow the bilateral-links rule: within the panel of each headquarters country, profit shifted out of
# a jurisdiction goes to the group's excess-profit destinations in proportion to their share. The figures show 2023
# at 2025 prices, scaled with the uniform factor.
O_OECD, O_G77 = "OECD countries\n(excluding tax havens)", "Non-OECD countries\n(excluding tax havens)"
COL_O = {O_OECD: BLOC["OECD"], O_G77: BLOC["G77"]}
# The OECD ribbons are dark and the G77 ribbons light, so that the two blocs differ in lightness as well as hue and stay
# apart for colour-blind readers.
RIBBON_ALPHA = {O_OECD: 0.8, O_G77: 0.45}
HAV_COL = BLOC["Tax havens"]
N_TOP = 8
# The two Sankeys are drawn wider than high and saved cropped to their content, so that the ribbons span the text width.
SANKEY_SIZE = (10.0, 5.4)
SANKEY_NAMES = {"IRL": "Ireland", "NLD": "Netherlands", "CHE": "Switzerland", "SGP": "Singapore", "HKG": "Hong Kong", "LUX": "Luxembourg",
                "CYM": "Cayman Islands", "BMU": "Bermuda", "PRI": "Puerto Rico", "GBR": "United Kingdom", "USA": "United States", "BEL": "Belgium",
                "JEY": "Jersey", "GGY": "Guernsey", "IMN": "Isle of Man", "VGB": "British Virgin Is.", "MLT": "Malta", "CYP": "Cyprus", "MUS": "Mauritius",
                "BHS": "Bahamas", "ARE": "UAE", "HUN": "Hungary", "PAN": "Panama", "CUW": "Curaçao", "LIE": "Liechtenstein", "MCO": "Monaco",
                "BRB": "Barbados", "AIA": "Anguilla", "LBR": "Liberia", "SYC": "Seychelles", "ABW": "Aruba", "IOT": "BIOT", "MAC": "Macao", "GIB": "Gibraltar"}


def sankey_flows(M):
    """Return the net profit flows from each bloc to each haven (US$bn), with the eight largest havens by name and the
    rest pooled, the number of havens with a net inflow and the net misaligned profit of every jurisdiction."""
    m = M[(M["year"] == Y) & M["misaligned_profit"].notna()].copy()
    k = DEFL_Y * SF_Y / 1e9
    m["bn"] = m["misaligned_profit"] * k
    iso = m["iso_partner"]
    m["origin"] = np.where(iso.isin(HAV), "haven", np.where(iso.isin(OECD), O_OECD, O_G77))
    net = m.groupby("origin")["bn"].sum()
    net_loss = {o: -net[o] for o in (O_OECD, O_G77)}            # positive = net shifted out
    hav_net = m[m["origin"] == "haven"].groupby("iso_partner")["bn"].sum()
    hav_net = hav_net[hav_net > 0].sort_values(ascending=False)   # havens with a net inflow
    # Gross bilateral flows from each bloc to each haven (the bilateral-links rule within the panel of each
    # headquarters country).
    rows = []
    for p, g in m.groupby("iso_parent"):
        pos = g[g["bn"] > 0]; neg = g[g["bn"] < 0]
        if pos.empty or neg.empty:
            continue
        ph = pos[pos["iso_partner"].isin(HAV)].groupby("iso_partner")["bn"].sum() / pos["bn"].sum()
        for o, v in (-neg.groupby("origin")["bn"].sum()).items():
            if o == "haven":
                continue
            for h, s in ph.items():
                rows.append(dict(origin=o, haven=h, bn=v * s))
    G = pd.DataFrame(rows).groupby(["origin", "haven"])["bn"].sum().unstack(fill_value=0.0)
    # Net flows: I spread each bloc's net loss by its gross pattern across the havens, restricted to the havens with
    # a net inflow.
    G = G.reindex(columns=hav_net.index, fill_value=0.0)
    F = G.div(G.sum(axis=1), axis=0).mul(pd.Series(net_loss), axis=0).reindex([O_OECD, O_G77])
    # Right-hand nodes: the largest havens by inflow, the rest pooled.
    inflow = F.sum(axis=0).sort_values(ascending=False)
    top = list(inflow.index[:N_TOP]); rest = list(inflow.index[N_TOP:])
    Fd = F[top].copy()
    Fd[f"{len(rest)} other havens"] = F[rest].sum(axis=1)
    Fd.columns = [SANKEY_NAMES.get(c, c) if c in top else c for c in Fd.columns]
    return Fd, len(hav_net), m.groupby("iso_partner")["bn"].sum()


def draw_sankey_profit(F, n_hav, fpath):
    """Draw figB4, the net profit shifted from the two blocs into the havens."""
    total = F.values.sum()
    out_tot = F.sum(axis=1); in_tot = F.sum(axis=0)
    gap_l, gap_r = 0.06 * total, 0.018 * total
    fig, ax = plt.subplots(figsize=SANKEY_SIZE)
    x0, x1, bw = 0.0, 1.0, 0.035
    top_y = total + (len(in_tot) - 1) * gap_r
    L, y = {}, top_y
    for o in F.index:
        L[o] = (y - out_tot[o], y); y -= out_tot[o] + gap_l
    R, y = {}, top_y
    for h in F.columns:
        R[h] = (y - in_tot[h], y); y -= in_tot[h] + gap_r
    for o in F.index:
        ax.add_patch(plt.Rectangle((x0 - bw, L[o][0]), bw, out_tot[o], color=COL_O[o]))
        ax.text(x0 - bw - 0.015, np.mean(L[o]), f"{o}\nnet US\\${out_tot[o]:,.0f}bn", ha="right", va="center", fontsize=10)
    ys = spread([np.mean(R[h]) for h in F.columns], 0.042 * top_y)
    for i, h in enumerate(F.columns):
        shade = HAV_COL if i < N_TOP else tint(HAV_COL, 0.55)
        ax.add_patch(plt.Rectangle((x1, R[h][0]), bw, in_tot[h], color=shade))
        dx = 0.012 if abs(ys[i] - np.mean(R[h])) < 1e-9 else 0.05
        if dx > 0.012:
            ax.plot([x1 + bw, x1 + bw + 0.04], [np.mean(R[h]), ys[i]], color="#999999", lw=0.6)
        ax.text(x1 + bw + dx, ys[i], f"{h}  US\\${in_tot[h]:,.0f}bn", ha="left", va="center", fontsize=9.3)
    lo = {o: L[o][1] for o in F.index}; ro = {h: R[h][1] for h in F.columns}
    for o in F.index:
        for h in F.columns:
            v = F.loc[o, h]
            if v <= 0:
                continue
            ribbon(ax, x0, lo[o] - v, lo[o], x1, ro[h] - v, ro[h], COL_O[o], alpha=RIBBON_ALPHA[o])
            lo[o] -= v; ro[h] -= v
    ax.text(x0 - bw / 2, top_y + 0.9 * gap_l, "Profit shifted from", ha="center", va="bottom", fontsize=10.5, weight="bold")
    ax.text(x1 + bw / 2, top_y + 0.9 * gap_l, "Profit shifted to", ha="center", va="bottom", fontsize=10.5, weight="bold")
    ax.set_xlim(-0.66, 1.56); ax.set_ylim(-0.6 * gap_l, top_y + 2.2 * gap_l)
    ax.axis("off")
    save_cropped(fig, ax, fpath)
    plt.close(fig)


def sankey_tax_sides(S, F):
    """Return the net tax revenue lost by each bloc (left) and the tax collected by each haven node (right), in US$bn
    at 2025 prices, scaled. The left side is the country-level net change under unitary taxation (for the losers, what
    they lose today). The right side is the tax the havens collect today on the profit shifted into them. Both are
    aggregated to the Sankey nodes."""
    d = S[S["year"] == Y].set_index("iso_partner")
    net = d["revenue_gain_from_ut"] * DEFL_Y * SF_Y / 1e3          # positive = loses today (net, as in Figure 2.3)
    coll = d["tax_revenue_gain"] * DEFL_Y * SF_Y / 1e3              # tax the haven collects today on the profit shifted into it
    iso = net.index
    left = {O_OECD: net[iso.isin(OECD) & ~iso.isin(HAV)].sum(), O_G77: net[~iso.isin(OECD) & ~iso.isin(HAV)].sum()}
    inv = {v: k for k, v in SANKEY_NAMES.items()}
    right = {}
    named = [c for c in F.columns if c in inv]
    for c in named:
        right[c] = coll.get(inv[c], 0.0)
    rest = [c for c in F.columns if c not in inv]
    if rest:
        shown = {inv[c] for c in named}
        right[rest[0]] = coll[iso.isin(HAV) & ~iso.isin(shown)].sum()
    return pd.Series(left), pd.Series(right)


def draw_sankey_tax_only(F, left_tax, right_tax, fpath):
    """Draw figB7, in which the tax revenue lost by each bloc (left) flows to the tax each haven collects on the profit
    shifted into it (right). On the left, each ribbon is the bloc's tax loss split across the havens by the bloc's
    pattern of net profit flows. On the right, it is the haven's tax collected split across the blocs by the same
    pattern, so the ribbon tapers from what is lost to what is collected. Both sides use the same vertical scale."""
    out_tot = F.sum(axis=1); in_tot = F.sum(axis=0)
    lt = left_tax.reindex(F.index); rt = right_tax.reindex(F.columns).clip(lower=0)
    tot_l, tot_r = lt.sum(), rt.sum()
    gap_l, gap_r = 0.06 * tot_l, 0.025 * tot_l
    fig, ax = plt.subplots(figsize=SANKEY_SIZE)
    x0, x1, bw = 0.0, 1.0, 0.035
    top_y = tot_l + (len(lt) - 1) * gap_l
    L, y = {}, top_y
    for o in F.index: L[o] = (y - lt[o], y); y -= lt[o] + gap_l
    h_r = tot_r + (len(rt) - 1) * gap_r
    R, y = {}, top_y / 2 + h_r / 2            # right stack centred on the left stack
    for h in F.columns: R[h] = (y - rt[h], y); y -= rt[h] + gap_r
    for o in F.index:
        ax.add_patch(plt.Rectangle((x0 - bw, L[o][0]), bw, lt[o], color=COL_O[o]))
        ax.text(x0 - bw - 0.015, np.mean(L[o]), f"{o}\ntax revenue lost\nUS\\${lt[o]:,.0f}bn", ha="right", va="center", fontsize=10)
    # I push the label positions apart so that small nodes stay readable, with a leader line to the node.
    min_sp = 0.044 * top_y
    ys = [np.mean(R[h]) for h in F.columns]
    for j in range(1, len(ys)):
        ys[j] = min(ys[j], ys[j - 1] - min_sp)
    for i, h in enumerate(F.columns):
        shade = HAV_COL if i < N_TOP else tint(HAV_COL, 0.55)
        ax.add_patch(plt.Rectangle((x1, R[h][0]), bw, rt[h], color=shade))
        v = rt[h]
        if abs(ys[i] - np.mean(R[h])) > 1e-9:
            ax.plot([x1 + bw, x1 + bw + 0.03], [np.mean(R[h]), ys[i]], color="#999999", lw=0.6)
        verb = "collect" if h.endswith("havens") else "collects"     # the pooled node is plural
        ax.text(x1 + bw + 0.04, ys[i], f"{h} {verb} " + (f"US\\${v:,.1f}bn" if v < 10 else f"US\\${v:,.0f}bn"), ha="left", va="center", fontsize=9.3)
    lo = {o: L[o][1] for o in F.index}; ro = {h: R[h][1] for h in F.columns}
    for o in F.index:
        for h in F.columns:
            f = F.loc[o, h]
            if f <= 0: continue
            vl = lt[o] * f / out_tot[o]; vr = rt[h] * f / in_tot[h]
            ribbon(ax, x0, lo[o] - vl, lo[o], x1, ro[h] - vr, ro[h], COL_O[o], alpha=RIBBON_ALPHA[o]); lo[o] -= vl; ro[h] -= vr
    ax.text(x0 - bw / 2, top_y + 0.9 * gap_l, "Tax revenue lost", ha="center", va="bottom", fontsize=10.5, weight="bold")
    ax.text(x1 + bw / 2, top_y + 0.9 * gap_l, "Tax collected\non the shifted profit", ha="center", va="bottom", fontsize=10.5, weight="bold")
    ax.set_xlim(-0.66, 1.68); ax.set_ylim(-0.6 * gap_l, top_y + 2.4 * gap_l); ax.axis("off")
    save_cropped(fig, ax, fpath); plt.close(fig)
    return tot_l, tot_r


def sankey_figures(M, S):
    """Make Figures 2.1 and 2.2 with their tables and return the numbers the text quotes."""
    F, n_hav, net_iso = sankey_flows(M)
    draw_sankey_profit(F, n_hav, FIG / f"figB4_sankey_net_havens_{Y}.png")
    t = F.copy(); t.index = [i.replace("\n", " ") for i in t.index]; t.insert(0, "key", KEY_LABEL); t.index.name = "origin"
    t.round(1).to_csv(TAB / f"sankey_net_havens_{Y}_keys.csv")
    lt, rt = sankey_tax_sides(S, F)
    pd.DataFrame({"key": KEY_LABEL, "node": list(lt.index) + list(rt.index), "side": ["loser"] * len(lt) + ["haven"] * len(rt),
                  "net_profit_shifted_bn": list(F.sum(axis=1)) + list(F.sum(axis=0)), "net_tax_bn": list(lt) + list(rt)}
                 ).assign(node=lambda x: x["node"].str.replace("\n", " ")).round(1).to_csv(TAB / f"sankey_net_havens_tax_{Y}_keys.csv", index=False)
    tot_l, tot_r = draw_sankey_tax_only(F, lt, rt, FIG / f"figB7_sankey_tax_only_{Y}.png")
    total = F.values.sum()
    print(f"Sankeys: net profit to havens US${total:,.0f}bn; tax lost US${tot_l:,.0f}bn, collected US${tot_r:,.0f}bn")
    return {"profit_to_havens": total, "profit_oecd": F.sum(axis=1)[O_OECD], "profit_g77": F.sum(axis=1)[O_G77],
            "share_top8": 100 * F.sum(axis=0).iloc[:N_TOP].sum() / total, "top8": ", ".join(F.columns[:N_TOP]),
            "n_losing": int((net_iso < 0).sum()), "n_recipients": int((net_iso > 0).sum()), "n_haven_recipients": n_hav,
            "tax_lost_net": tot_l, "tax_collected_havens": tot_r, "lost_per_collected": tot_l / tot_r}


# %% MARK: 4. Figure 2.3: negotiation blocs
# The blocs are defined as follows. The tax havens are config.TAX_HAVENS_REPRESENTATION. The OECD members come from
# data/raw/country_info/oecd_members_2026.csv and the G77 members from un_g77_members.csv. The EU is the eu27 flag.
# The African Group is region_tjn == "Africa" (the 54 African member states of the UN). Latin America is region_tjn ==
# "Latin America" (the 19 Spanish- and Portuguese-speaking countries of the Americas). Every bloc includes the havens
# among its members, and the figure has no separate haven bar. The table also gives the havens as a group, which the
# text quotes. The percentages are scale-free because the numerator and the denominator are scaled alike.
B_OECD, B_G77, B_EU, B_AFR, B_LAT, B_HAV = "OECD", "G77", "EU", "African Group", "Latin America", "Tax havens"
BLOCS = [B_OECD, B_G77, B_LAT, B_AFR, B_EU, B_HAV]
WORLD = "World"
# The jurisdictions on the haven list that are not independent states, by the state they belong to. The chapter's
# footnote on the haven list counts them.
DEPENDENCIES = {
    "United Kingdom": {"AIA", "BMU", "CYM", "FLK", "GGY", "GIB", "IMN", "IOT", "JEY", "MSR", "PCN", "SHN", "TCA", "VGB"},
    "Kingdom of the Netherlands": {"ABW", "BES", "CUW", "SXM"},
    "United States": {"ASM", "GUM", "MNP", "PRI", "UMI", "VIR"},
    "China": {"HKG", "MAC"},
}


def bloc_table(S):
    """Return one row per bloc (and the world) with the profit shifted out and in, the reported profit, the tax revenue
    lost gross and net (the net equals the net gain under unitary taxation), the revenue the losing countries lose and
    the winning countries gain (each country netted first) and the corporate tax multinationals pay today. Values are
    in US$bn at 2025 prices, scaled."""
    d = S[S["year"] == Y].copy()
    iso = d["iso_partner"]
    eu = pd.to_numeric(d["eu27"], errors="coerce").fillna(0).astype(bool)
    masks = {B_OECD: iso.isin(OECD), B_G77: iso.isin(G77), B_EU: eu, B_AFR: d["region_tjn"] == "Africa",
             B_LAT: d["region_tjn"] == "Latin America", B_HAV: iso.isin(HAV), WORLD: pd.Series(True, index=d.index)}
    rows = []
    for b, m in masks.items():
        x = d[m]
        k = DEFL_Y * SF_Y / 1e3   # converts US$ million of the year to US$bn at 2025 prices, scaled
        rows.append(dict(bloc=b, n_countries=x["iso_partner"].nunique(),
                         shifted_out_bn=x["negative_misalignment"].abs().sum() * k,
                         shifted_in_bn=x["positive_misalignment"].sum() * k,
                         reported_profit_bn=x["reported_profit"].sum() * k,
                         revenue_lost_bn=x["tax_revenue_loss"].sum() * k,
                         net_change_bn=x["revenue_gain_from_ut"].sum() * k,
                         losses_bn=x["revenue_gain_from_ut"].clip(lower=0).sum() * k,
                         gains_bn=(-x["revenue_gain_from_ut"]).clip(lower=0).sum() * k,
                         n_losing=int((x["revenue_gain_from_ut"] > 0).sum()), n_winning=int((x["revenue_gain_from_ut"] < 0).sum()),
                         mne_cash_tax_bn=pd.to_numeric(x["current_tax_paid_cash_musd"], errors="coerce").sum() * k))
    t = pd.DataFrame(rows).set_index("bloc")
    t["shifted_out_pct_profit"] = 100 * t["shifted_out_bn"] / t["reported_profit_bn"]
    t["shifted_in_pct_profit"] = 100 * t["shifted_in_bn"] / t["reported_profit_bn"]
    t["net_shifted_out_bn"] = t["shifted_out_bn"] - t["shifted_in_bn"]
    t["net_shifted_out_pct_profit"] = 100 * t["net_shifted_out_bn"] / t["reported_profit_bn"]
    t["revenue_lost_pct_tax"] = 100 * t["revenue_lost_bn"] / t["mne_cash_tax_bn"]
    t["net_change_pct_tax"] = 100 * t["net_change_bn"] / t["mne_cash_tax_bn"]
    t["losses_pct_tax"] = 100 * t["losses_bn"] / t["mne_cash_tax_bn"]
    return t


def signed(v, pct=False):
    s = f"{abs(v):,.0f}" + ("%" if pct else "")
    return ("−" if v < 0 else "+" if v > 0 else "") + s


def draw_bloc_revenue(t, fpath):
    """Draw figB2u: what the world and every bloc (with the havens among its members) would gain and lose under
    unitary taxation, which taxes profit where the economic activity is. The revenue the losing countries lose to
    profit shifting today is what they would gain, so these bars point upwards in the colour of gains. The revenue the
    winning countries gain today is what they would lose, so these bars point downwards in the colour of losses (each
    country netted first). Each bar has the sample solid and the scale-up to all multinationals as a shaded extension
    (with the uniform factor, every bar grows by the same proportion). The right panel shows how much more corporate
    tax the bloc could have collected from multinationals if profit had been taxed where the economic activity is: its
    net gain as % of the corporate tax multinationals pay in the bloc (scale-free, so without an extension). The havens
    as a group stay in the table only."""
    blocs = [WORLD] + [b for b in BLOCS if b != B_HAV]
    losses = t.loc[blocs, "losses_bn"].to_numpy()
    gains = t.loc[blocs, "gains_bn"].to_numpy()
    pct = t.loc[blocs, "net_change_pct_tax"].to_numpy()
    series = ((losses, GAIN), (-gains, LOSS))
    # I draw the canvas at about 1.25 times the report's text width (16.5 cm), so that the text prints at 6.5 to 8.5pt.
    # The titles take three lines, so that each stays above its own panel. The left panel is wider, because it has two
    # bars per group and the sample values inside them must fit.
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 5.1), gridspec_kw={"width_ratios": (1.25, 1)})
    x = np.arange(len(blocs))
    ticks = [b.replace(" ", "\n") for b in blocs]
    ax = axes[0]
    w = 0.49
    span = max(losses.max(), gains.max())
    for xs, (vals, col) in zip((x - w / 2, x + w / 2), series):
        smp = vals / SF_Y
        ax.bar(xs, smp, w, color=col, edgecolor="white", linewidth=0.4)
        ax.bar(xs, vals - smp, w, bottom=smp, color=tint(col, 0.45), hatch=HATCH_CYCLE[1], edgecolor="white", linewidth=0.4)
        for xi, sv, v in zip(xs, smp, vals):
            ax.annotate(signed(v), (xi, v), xytext=(0, 3 if v >= 0 else -3), textcoords="offset points",
                        ha="center", va="bottom" if v >= 0 else "top", fontsize=8.8, fontweight="bold")
            if abs(sv) > 0.12 * span:   # the sample value inside the solid part where it fits
                ax.text(xi, sv / 2, signed(sv), ha="center", va="center", fontsize=8.6, color="white")
    ax.set_ylabel(f"US$bn, {Y} ({config.BASE_YEAR} prices)", fontsize=9.5)
    ax.set_title("Countries that would gain (+)\nand lose (−) under unitary\ntaxation, US$ billion", loc="left", fontsize=10.5)
    fig.legend(handles=[Patch(facecolor="#8A867C", edgecolor="white", label="Sample for which we have country-by-country reporting data"),
                        Patch(facecolor=tint("#8A867C", 0.45), edgecolor="white", hatch=HATCH_CYCLE[1], label="Scaled up to all multinationals")],
               frameon=False, fontsize=9.3, ncol=2, loc="upper left", bbox_to_anchor=(0.0, 1.0))
    ax = axes[1]
    bars = ax.bar(x, pct, 0.58, color=[INK if b == WORLD else (GAIN if v > 0 else LOSS) for b, v in zip(blocs, pct)],
                  edgecolor="white", linewidth=0.4)
    for b, v in zip(bars, pct):
        ax.annotate(signed(v, pct=True), (b.get_x() + b.get_width() / 2, v), xytext=(0, 3 if v >= 0 else -3),
                    textcoords="offset points", ha="center", va="bottom" if v >= 0 else "top", fontsize=9.3)
    ax.set_ylabel("% more than the corporate tax\ncollected from multinationals", fontsize=9.5)
    ax.set_title("How much more corporate\ntax could have been collected\nfrom multinationals", loc="left", fontsize=10.5)
    for ax, size in zip(axes, (9.5, 8.6)):
        ax.axhline(0, color=INK, lw=0.6)
        ax.set_xticks(x, ticks, fontsize=size)
        ax.tick_params(axis="y", labelsize=9.3)
        lo, hi = ax.get_ylim(); ax.set_ylim(lo * 1.12, max(hi * 1.25, 0.06 * abs(lo)))   # room above zero when all bars are negative
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(fpath, dpi=170)
    plt.close(fig)


def bloc_figure(S):
    """Make Figure 2.3 and its table and return the numbers the text quotes (scaled and sample in US$bn, and as % of
    the tax paid)."""
    t = bloc_table(S)
    t.insert(0, "key", KEY_LABEL)
    draw_bloc_revenue(t, FIG / f"figB2u_blocs_ut_gains_{Y}.png")
    t.round(1).to_csv(TAB / f"blocs_{Y}_keys.csv")
    out = {}
    for b, tag in [(WORLD, "world"), (B_OECD, "oecd"), (B_G77, "g77"), (B_LAT, "latam"), (B_AFR, "african"), (B_EU, "eu"),
                   (B_HAV, "havens")]:
        out[f"bloc_{tag}_scaled"] = t.loc[b, "net_change_bn"]
        out[f"bloc_{tag}_sample"] = t.loc[b, "net_change_bn"] / SF_Y
        out[f"bloc_{tag}_pct"] = t.loc[b, "net_change_pct_tax"]
        for side in ("losses", "gains"):
            out[f"bloc_{tag}_{side}_scaled"] = t.loc[b, f"{side}_bn"]
            out[f"bloc_{tag}_{side}_sample"] = t.loc[b, f"{side}_bn"] / SF_Y
    out["shifted_out_pct_profit_world"] = t.loc[WORLD, "shifted_out_pct_profit"]
    out["n_havens"] = int(t.loc[B_HAV, "n_countries"])
    out["n_dependencies"] = {state: len(HAV & members) for state, members in DEPENDENCIES.items()}
    print(f"blocs: world net US${t.loc[WORLD, 'net_change_bn']:,.1f}bn scaled")
    return out


# %% MARK: 5. Figures 2.4 and 2.5: shifted profit and tax revenue lost over time
# Shifted profit is the profit booked in a jurisdiction above what the formula (employees and sales by destination)
# allocates to it, summed over all cells with positive misalignment (gross), in constant 2025 US$. Each year has one
# bar, with the sample solid and the scale-up to all multinationals (uniform world factor) piled on top as a shaded
# part. Under each year, the figure gives the share of multinational profit that the sample covers. The tax revenue
# lost is that of the losing countries: each country's net change, summed over the countries that lose. The gains of
# the other countries are in Figure 2.3.
def shifted_series(M, havens_only=False):
    m = M[M["wb_income_group"] == "tax_haven"].copy() if havens_only else M.copy()
    m["shift"] = (m["profit_loss_excl_resource"] - m["theoretical_profit"]).clip(lower=0) * m["year"].map(DEFL) / 1e9
    s = m.groupby("year")["shift"].sum().reindex(config.ANALYSIS_YEARS)
    return s, s * SF.reindex(s.index)


def revenue_series(S):
    """Return the tax revenue lost per year, gross (the sum over the countries that lose today) and net, for the sample
    and scaled."""
    s = S.copy()
    s["g"] = s["revenue_gain_from_ut"] * s["year"].map(DEFL) / 1e3
    g = s.groupby("year")["g"].agg(gross=lambda x: x.clip(lower=0).sum(), net="sum").reindex(config.ANALYSIS_YEARS)
    return g, g.mul(SF.reindex(g.index), axis=0)


def stacked(ax, x, sample, scaled, bw=0.62, fontsize=9, inner=None):
    """Draw one bar per year, with the sample solid and the scale-up to all multinationals piled on top as a shaded
    part. The scaled total goes above the bar, the sample value inside the solid part (in size inner, by default 1.5pt
    smaller than the total)."""
    inner = fontsize - 1.5 if inner is None else inner
    smp, scl = np.asarray(sample, dtype=float), np.asarray(scaled, dtype=float)
    ax.bar(x, smp, width=bw, color=SCALED, edgecolor="white", linewidth=0.4,
           label="Sample for which we have country-by-country reporting data")
    ax.bar(x, scl - smp, width=bw, bottom=smp, color=tint(SCALED, 0.45), hatch=HATCH_CYCLE[1], edgecolor="white", linewidth=0.4,
           label="Scaled up to all multinationals")
    for xi, s, v in zip(x, smp, scl):
        ax.annotate(f"{v:,.0f}", (xi, v), textcoords="offset points", xytext=(0, 4), ha="center",
                    fontsize=fontsize, fontweight="bold", color="black")
        ax.text(xi, s / 2, f"{s:,.0f}", ha="center", va="center", fontsize=inner, color="white")


def draw_with_revenue(years, sample, scaled, rev_smp, rev_scl, fpath):
    """Draw figS1, the profit shifted (gross) and the tax revenue the losing countries lose, each on its own scale (two
    panels). The definitions go into the caption, not the figure."""
    x = np.arange(len(years))
    # I draw the canvas at about 1.3 times the report's text width (16.5 cm), so that the text prints at 6.5 to 8.5pt.
    # The bars are wide enough for the sample values inside them.
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 4.9))
    for ax, smp, scl, sub, ylab in [
            (axes[0], sample, scaled, "Profit shifted (gross)", f"Profit (US\\$ billion, {config.BASE_YEAR} prices)"),
            (axes[1], rev_smp, rev_scl, "Tax revenue lost by the losing countries", f"Corporate tax revenue (US\\$ billion, {config.BASE_YEAR} prices)")]:
        stacked(ax, x, smp.values, scl.values, bw=0.8, fontsize=9, inner=8.6)
        ax.set_xticks(x); ax.set_xticklabels([f"{y}\n({COV[y]:.0%})" for y in years], fontsize=9)
        ax.tick_params(axis="y", labelsize=9)
        ax.set_ylim(0, 1.18 * float(scl.max())); ax.set_ylabel(ylab, fontsize=9.3)
        ax.set_title(sub, loc="left", fontsize=11, pad=8)
    hdl, lbl = axes[0].get_legend_handles_labels()
    fig.legend(hdl, lbl, fontsize=9.3, framealpha=0.85, loc="lower left", bbox_to_anchor=(0.045, 0.93), ncol=2)
    plt.tight_layout(rect=(0, 0, 1, 0.92)); plt.savefig(fpath, dpi=200, bbox_inches="tight"); plt.close()


def capped_net(c, loss_col):
    """Return each country-year's net change in tax revenue (the revenue it gets back minus the revenue it forgoes)
    after the multi-year loss cap of script 5 (apply_multiyear_loss_cap). Over the years of config.PAPER_YEARS, in
    constant dollars, a country cannot lose more tax than its multinationals pay in cash. Where the cap binds, I trim
    the revenue it forgoes in every year of the window in proportion to that year's amount. Countries without
    cash-tax data and the year 2020 are not capped. The frame c holds one row per year and partner with the revenue
    the country gets back (loss_col), the revenue it forgoes (gain) and the cash tax (current_tax_paid_cash_musd), in
    US$ million of the year."""
    in_win = c["year"].isin(config.PAPER_YEARS)
    w = c["year"].map(DEFL).fillna(1.0)
    cash = pd.to_numeric(c["current_tax_paid_cash_musd"], errors="coerce").where(in_win)
    key = c["iso_partner"]
    net_tot = ((c[loss_col] - c["gain"]) * w).where(in_win, 0.0).groupby(key).transform("sum")
    gain_tot = (c["gain"] * w).where(in_win, 0.0).groupby(key).transform("sum")
    cash_tot = (cash * w).fillna(0.0).groupby(key).transform("sum")
    has_cash = cash.notna().groupby(key).transform("any")
    excess = (-cash_tot - net_tot).clip(lower=0.0)
    bind = in_win & has_cash & (excess > 0) & (gain_tot > 0)
    share = np.where(gain_tot > 0, excess / gain_tot, 0.0)
    return c[loss_col] - (c["gain"] - np.where(bind, share * c["gain"], 0.0))


def repriced_series(M, S):
    """Return the tax revenue lost at each year's rates and had every country kept its 2016 rates, in US$bn at 2025
    prices (sample). I value the cells as script 5 does. The profit a country gets back is priced at its statutory
    rate. The profit it forgoes is priced at its effective rate, at most its statutory rate, and at zero in the
    jurisdictions without a corporate income tax. The multi-year loss cap then applies to each series. The series at
    each year's rates therefore equals Figure 2.4, which I check against the script-6 summary. The 2016 rates apply
    only to the profit a country gets back. The profit it forgoes keeps each year's effective rate, because repricing it
    at 2016 rates would pick up the change in the home rates of the large headquarters countries (the US rate was 35%
    before the 2017 tax cut), not profit shifting."""
    m = M.copy()
    # I take the 2016 statutory rate of each partner. A partner without a rate in 2016 keeps the rate of each year.
    r16 = m[m["year"] == 2016].drop_duplicates("iso_partner").set_index("iso_partner")["cit"]
    cit = pd.to_numeric(m["cit"], errors="coerce")
    cit16 = pd.to_numeric(m["iso_partner"].map(r16), errors="coerce").fillna(cit)
    gain_rate = pd.to_numeric(m["etr_domfor_excl_resource"], errors="coerce")
    gain_rate = gain_rate.mask(m["iso_partner"].isin(config.NO_CIT_JURISDICTIONS), 0.0)
    gain_rate = gain_rate.where(~(cit > 0), np.minimum(gain_rate, cit))
    out_musd = (-m["misaligned_profit"]).clip(lower=0) / 1e6     # profit shifted out, which the country gets back
    in_musd = m["misaligned_profit"].clip(lower=0) / 1e6         # profit shifted in, which the country forgoes
    m["loss_now"], m["loss_16"], m["gain"] = out_musd * cit, out_musd * cit16, in_musd * gain_rate
    c = m.groupby(["year", "iso_partner"], as_index=False)[["loss_now", "loss_16", "gain"]].sum()
    c = c.merge(S[["year", "iso_partner", "current_tax_paid_cash_musd", "revenue_gain_from_ut"]],
                on=["year", "iso_partner"], how="left", validate="one_to_one")
    c["now"], c["r2016"] = capped_net(c, "loss_now"), capped_net(c, "loss_16")
    assert (c["now"] - c["revenue_gain_from_ut"]).abs().max() < 1e-6, "the series at each year's rates differs from Figure 2.4"
    out = {}
    for lab in ("now", "r2016"):
        bn = c[lab] * c["year"].map(DEFL) / 1e3
        out[lab] = bn.groupby(c["year"]).agg(gross=lambda x: x.clip(lower=0).sum(), net="sum").reindex(config.ANALYSIS_YEARS)
    return out


def draw_rates(years, d, fpath):
    """Draw figS4: one bar per year with the tax revenue the losing countries lose at the rates of each year (lower part)
    and the additional revenue they would lose had every country kept its 2016 rates (upper part), scaled. In 2017 the
    2016 rates give slightly less, as some countries raised their rates, so the upper part is zero there."""
    x = np.arange(len(years)); bw = 0.62
    now = d["now"]["gross"].reindex(years) * SF.reindex(years)
    extra = (d["r2016"]["gross"].reindex(years) * SF.reindex(years) - now).clip(lower=0)
    top = now + extra
    # I draw the canvas at about 1.25 times the report's text width (16.5 cm), so that the text prints at 6.5 to 8pt.
    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    ax.bar(x, now.values, width=bw, color=SCALED, edgecolor="white", linewidth=0.4, label="Loss from profit shifting")
    ax.bar(x, extra.values, width=bw, bottom=now.values, color=tint(SCALED, 0.45), edgecolor="white", linewidth=0.4,
           label="Additional loss from lowering tax rates")
    for xi, a, b in zip(x, now.values, extra.values):
        ax.text(xi, a / 2, f"{a:,.0f}", ha="center", va="center", fontsize=8.8, color="white")
        if b > 0.06 * top.max():
            ax.text(xi, a + b / 2, f"{b:,.0f}", ha="center", va="center", fontsize=8.8, color=INK)
        ax.annotate(f"{a + b:,.0f}", (xi, a + b), textcoords="offset points", xytext=(0, 4), ha="center", fontsize=9.5,
                    fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels([str(y) for y in years], fontsize=8.3)
    ax.tick_params(axis="y", labelsize=9.3)
    ax.set_ylim(0, 1.15 * float(top.max()))
    ax.set_ylabel(f"Tax revenue lost by the losing countries, scaled to\nall multinationals (US\\$ billion, {config.BASE_YEAR} prices)",
                  fontsize=9.3)
    ax.legend(fontsize=9.3, framealpha=0.85, loc="lower left", bbox_to_anchor=(0.0, 1.01), borderaxespad=0, ncol=2)
    plt.tight_layout(); plt.savefig(fpath, dpi=200, bbox_inches="tight"); plt.close()


def shifted_profit_figures(M, S):
    """Make Figures 2.4 and 2.5 with their tables and return the gross numbers the text quotes."""
    years = list(config.ANALYSIS_YEARS)
    smp, scl = revenue_series(S)
    rows = []
    for havens in (False, True):   # all jurisdictions (Figure 2.4) and tax havens only (table only)
        s, ss = shifted_series(M, havens)
        if not havens:
            draw_with_revenue(years, s, ss, smp["gross"], scl["gross"], FIG / "figS1_shifted_profit.png")
            shifted_all = ss
        for y in years:
            rows.append(dict(spec=KEY_LABEL, havens_only=havens, year=y, sample_bn=s[y], scaled_bn=ss[y], coverage=COV[y], factor=SF[y]))
    pd.DataFrame(rows).round(1).to_csv(TAB / "shifted_profit_fig_data.csv", index=False)
    pd.DataFrame({"spec": KEY_LABEL, "year": years, "gross_sample": smp["gross"].values, "net_sample": smp["net"].values,
                  "gross_scaled": scl["gross"].values, "net_scaled": scl["net"].values}).round(1).to_csv(TAB / "tax_losses_by_year.csv", index=False)
    d = repriced_series(M, S)
    draw_rates(years, d, FIG / "figS4_tax_losses_2016_rates.png")
    X = pd.DataFrame([dict(spec=KEY_LABEL, year=y, gross_now_sample=d["now"].loc[y, "gross"], gross_2016rates_sample=d["r2016"].loc[y, "gross"],
                           net_now_sample=d["now"].loc[y, "net"], net_2016rates_sample=d["r2016"].loc[y, "net"], factor=SF[y]) for y in years])
    for c in ["gross_now", "gross_2016rates", "net_now", "net_2016rates"]:
        X[c + "_scaled"] = X[c + "_sample"] * X["factor"]
    X.round(1).to_csv(TAB / "tax_losses_2016_rates_by_year.csv", index=False)
    print(f"shifted profit {Y}: US${shifted_all[Y]:,.0f}bn gross scaled; tax lost by the losing countries US${scl.loc[Y, 'gross']:,.0f}bn scaled")
    x = X.set_index("year").loc[Y]
    extra = max(x["gross_2016rates_scaled"] - x["gross_now_scaled"], 0)
    return {"shifted_gross_scaled": shifted_all[Y], "tax_lost_losers_scaled": scl.loc[Y, "gross"],
            "loss_lower_rates_scaled": extra,
            "loss_lower_rates_pct": 100 * (x["gross_2016rates_sample"] / x["gross_now_sample"] - 1),
            "years_more_shifted": int((shifted_all > shifted_all[Y]).sum()),
            "years_more_shifted_list": ", ".join(str(y) for y in shifted_all.index[shifted_all > shifted_all[Y]])}


# %% MARK: 6. Figures 2.6 and 2.7: race to the bottom
# Statutory corporate income tax rates 1980–2023 (Tax Foundation worldwide rates). Figure 2.6 shows the average rate on
# a balanced set of jurisdictions (a rate in 1980 and 2023 and in at least 90% of the years), the averages of the OECD
# countries and of the other countries, each without the tax havens, and of the tax havens (all jurisdictions with
# data, so the three groups do not overlap) and, for comparison, the effective rate US multinationals pay on their
# profit taxed below 15% (IRS Table 4, all jurisdictions including the US). The 15% band exists in the IRS data from
# 2019 on. Figure 2.7 shows how much more likely a statutory rate below 15%, below 25% and below 35%, or of 35% and
# above, is in 2023 than in 1980 (the share of all jurisdictions with data in 2023 ÷ the share in 1980).
TF_RATES = ROOT / "data/raw/tax_rates/taxfoundation_cit_rates_1980-2023.xlsx"
# The thresholds are cumulative (below 15%, 25% and 35%), so that each bar answers how much more common rates below a
# given level have become.
RATE_BANDS_PCT = [(0, 15, "below 15%"), (0, 25, "below 25%"), (0, 35, "below 35%"), (35, 101, "35% and above")]


def statutory_rates():
    """Return the averages, quartiles and band shares of the statutory rates per year, and the size of the balanced
    set."""
    raw = pd.read_excel(TF_RATES, header=0)
    raw = raw.rename(columns={c: int(float(c)) for c in raw.columns if str(c).replace(".0", "").isdigit()})
    years = [y for y in raw.columns if isinstance(y, int)]
    t = raw.set_index("iso_3")[years].apply(pd.to_numeric, errors="coerce")
    bal = t.dropna(subset=[1980, 2023]).dropna(thresh=int(0.9 * len(years)))   # balanced core: data in 1980, 2023 and at least 90% of the years
    print(f"race to the bottom: balanced core of {len(bal)} jurisdictions; all: {t.notna().sum().min()}–{t.notna().sum().max()} per year")
    S = pd.DataFrame({"balanced_mean": bal.mean(), "balanced_p25": bal.quantile(0.25), "balanced_p75": bal.quantile(0.75), "balanced_median": bal.median(),
                      "all_mean": t.mean(), "n_all": t.notna().sum(),
                      "oecd": t.loc[t.index.isin(OECD) & ~t.index.isin(HAV)].mean(),
                      "non_oecd": t.loc[~t.index.isin(OECD) & ~t.index.isin(HAV)].mean(), "havens": t.loc[t.index.isin(HAV)].mean()})
    for lo, hi, lab in RATE_BANDS_PCT:
        S[lab] = 100 * ((t >= lo) & (t < hi)).sum() / t.notna().sum()
    S.index = S.index.astype(int); S = S.astype(float)
    return S, len(bal)


def irs_rate_below15():
    """Return US multinationals' tax ÷ profit in the constituent entities taxed below 15%, all jurisdictions (including
    the US itself), from IRS SOI CbCR Table 4. The 15% band exists from 2019 on only."""
    e = {}
    for y in sorted(irs_table4_long()["year"].unique()):
        lt = irs_table4(y).query("band == 'lt15'")
        if lt["profit"].sum() > 0:
            e[y] = 100 * lt["tax"].sum() / lt["profit"].sum()
    return pd.Series(e).sort_index()


def words(r):
    """Put a ratio in words, for example 2.01 as 'twice as likely', 5.05 as 'more than five times as likely' and 0.06
    as '1/17 as likely'."""
    if r < 1:
        return f"1/{round(1 / r)} as likely"
    n = int(round(r))
    w = {1: "just", 2: "twice", 3: "three times", 4: "four times", 5: "five times", 6: "six times", 7: "seven times"}.get(n, f"{n} times")
    if abs(r - n) < 0.03:
        return f"{w} as likely"
    return f"{'more than' if r > n else 'nearly'} {w} as likely"


def panel_rates(ax, S, n_bal, E):
    # Each line has its own dash pattern and its name at its end, so that no line is told apart by colour alone.
    ax.plot(S.index, S["balanced_mean"], color=INK, lw=2.6, label=f"average statutory rate, {n_bal} jurisdictions observed since 1980")
    ax.plot(S.index, S["oecd"], color=BLOC["OECD"], lw=1.8, ls=(0, (6, 2.5)), label="OECD countries (excluding tax havens)")
    ax.plot(S.index, S["non_oecd"], color=BLOC["G77"], lw=1.8, ls=(0, (6, 2, 1.5, 2)), label="non-OECD countries (excluding tax havens)")
    ax.plot(S.index, S["havens"], color=BLOC["Tax havens"], lw=2.2, ls=(0, (1.2, 1.8)), label="tax havens")
    ax.plot(E.index, E.values, color=BLUE, lw=2.2, marker="o", ms=4.5,
            label="for comparison: effective rate US multinationals pay\non their profit taxed below 15%")
    ax.annotate(f"US multinationals,\nprofit taxed below 15%: {E.iloc[-1]:.1f}%", (E.index[-1], E.iloc[-1]),
                textcoords="offset points", xytext=(6, -3), va="center", fontsize=9, color=INK)
    # The 2023 averages lie close together, so I push their labels apart (top to bottom).
    ends = sorted(((S[col].iloc[-1], name) for col, name in [("balanced_mean", "average"), ("oecd", "OECD"), ("non_oecd", "non-OECD"),
                                                             ("havens", "tax havens")]), key=lambda e: -e[0])
    for (v, name), y in zip(ends, spread([v for v, _ in ends], 1.7)):
        ax.annotate(f"{name} {v:.0f}", (2023, v), xytext=(2023.6, y), textcoords="data", va="center", fontsize=9, color=INK)
    ax.annotate(f"{S['balanced_mean'].iloc[0]:.0f}", (1980, S["balanced_mean"].iloc[0]), textcoords="offset points", xytext=(0, -12), ha="center", fontsize=9, color=INK)
    ax.set_ylim(0, 55); ax.set_xlim(1979, 2026); ax.set_ylabel("statutory corporate income tax rate (%)", fontsize=9.5)
    ax.tick_params(labelsize=9.5)
    # The legend stands in the lower left, where no line runs before the mid-2000s.
    ax.legend(frameon=False, fontsize=9, loc="lower left")


def panel_ratios(ax, S):
    """Draw the bands as ratios, that is, how much more likely a statutory rate in each band is in 2023 than in 1980."""
    labs = [lab for _, _, lab in RATE_BANDS_PCT]
    r = (S.loc[2023, labs] / S.loc[1980, labs]).values
    x = np.arange(len(labs))
    ax.bar(x, r, width=0.62, color=[PURPLE if v >= 1 else tint(PURPLE, 0.35) for v in r], zorder=3)
    ax.axhline(1, color=INK, lw=0.9, ls="--", zorder=4)
    ax.text(len(labs) - 0.55, 1.08, "as likely as in 1980", ha="right", va="bottom", fontsize=9, color=INK)
    for xx, v in zip(x, r):
        # Below the 1980 line the label takes two lines, so that it stays under the dashed line.
        text = words(v) if v < 1 else words(v).replace(" as likely", "\nas likely")
        ax.text(xx, v + 0.12, text + f"\n(×{v:.2f})", ha="center", va="bottom", fontsize=9.5, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{lab}\nfrom {S.loc[1980, lab]:.0f}% to {S.loc[2023, lab]:.0f}%\nof jurisdictions" for lab in labs], fontsize=9.5)
    ax.tick_params(axis="y", labelsize=9.5)
    ax.set_ylim(0, max(r) * 1.35); ax.set_ylabel("2023 share ÷ 1980 share", fontsize=9.5)
    ax.grid(axis="x", visible=False)
    return r


def race_to_the_bottom():
    """Make Figures 2.6 and 2.7 (the statutory rates over time, and how much more likely each rate band is in 2023 than
    in 1980) with their tables, and return the size of the balanced set and the band ratios, which the text and the
    figure notes quote."""
    S, n_bal = statutory_rates()
    S.round(2).to_csv(TAB / "cit_long_run_by_year.csv")
    E = irs_rate_below15()
    E.rename("irs_rate_on_profit_taxed_below_15_pct").to_csv(TAB / "irs_rate_on_profit_below15_by_year.csv")
    # Both figures are drawn at about 1.25 times the report's text width (16.5 cm), so that the text prints at 7 to 8pt.
    # The rates figure is a little wider, for the two-line label at the end of the US line.
    fig, ax = plt.subplots(figsize=(8.8, 5.4))
    panel_rates(ax, S, n_bal, E)
    plt.tight_layout(); plt.savefig(FIG / "figC9_race_to_the_bottom.png", dpi=200, bbox_inches="tight"); plt.close()
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    r = panel_ratios(ax, S)
    plt.tight_layout(); plt.savefig(FIG / "figC9b_rate_bands_2023_vs_1980.png", dpi=200, bbox_inches="tight"); plt.close()
    print("race to the bottom: ratios 2023/1980:", {lab: round(float(v), 2) for (_, _, lab), v in zip(RATE_BANDS_PCT, r)})
    return {"n_balanced": n_bal, "band_ratios": {lab: float(v) for (_, _, lab), v in zip(RATE_BANDS_PCT, r)}}


# %% MARK: 7. Figure 2.8 and footnote: IRS low-tax shares of US multinationals
# The source is the IRS Statistics of Income country-by-country tables (Table 4, effective-tax-rate bands, with the
# shares from step 1). Figure 2.8 shows the share of US multinationals' profit taxed below 15% in the net recipients
# of shifted profit (net inflow > 0 in the headline estimate), against the rate they pay on that low-taxed profit. I
# leave out China and the non-havens whose inflow is mostly their own groups' home profit (more than 50% of the
# positive misalignment). The figure shows the 20 largest recipients, plus every jurisdiction with at least as much
# low-taxed profit as the smallest of the big havens (the US home cell and the UK). The chapter's footnote quotes,
# for every jurisdiction with at least US$1bn of US groups' profit, how much of the low-taxed profit sits in
# jurisdictions whose average rate on all their profit is 15% or more, which a 15% rule on the average rate would not
# count.
IRS_RECIPIENT_NAMES = {"IRL": "Ireland", "SGP": "Singapore", "CHE": "Switzerland", "JPN": "Japan", "HKG": "Hong Kong", "CYM": "Cayman Islands", "CHN": "China", "ARE": "UAE",
                       "DNK": "Denmark", "CYP": "Cyprus", "BMU": "Bermuda", "CAN": "Canada", "PRI": "Puerto Rico", "HUN": "Hungary", "THA": "Thailand", "BRB": "Barbados",
                       "NLD": "Netherlands", "JEY": "Jersey", "ITA": "Italy", "MAC": "Macao", "VGB": "BVI", "URY": "Uruguay", "MYS": "Malaysia", "PAN": "Panama",
                       "NZL": "New Zealand", "BHR": "Bahrain", "SAU": "Saudi Arabia", "GGY": "Guernsey", "ISR": "Israel", "BEL": "Belgium", "NOR": "Norway", "GUY": "Guyana",
                       "GRC": "Greece", "ZAF": "South Africa", "TUR": "Türkiye", "LUX": "Luxembourg", "GBR": "United Kingdom", "USA": "United States (home)"}
N_RECIPIENTS = 20
# Labels of the scatter (offset in points, alignment) for the largest amounts and the high-tax jurisdictions.
IRS_RECIPIENT_LABELS = {"USA": (0, 46, "center"), "IRL": (-14, 18, "right"), "SGP": (10, 14, "left"), "CHE": (-18, 40, "right"),
                        "GBR": (-6, -30, "left"), "NLD": (10, -28, "left"), "HKG": (14, 10, "left"), "PRI": (-16, 16, "right"),
                        "LUX": (-12, 12, "right"), "ARE": (-14, -3, "right"), "PAN": (-12, -4, "right"),
                        "URY": (-12, -14, "right")}
# The bubbles taxed almost entirely below 15% lie on top of each other near 100%. Their labels stand in a column right
# of the plot, ordered by the rate, each with a line to its bubble.
IRS_RECIPIENT_COLUMN = ["HUN", "MAC", "BMU", "MLT", "JEY", "BRB", "CYM", "VGB", "CYP"]
IRS_EXCLUDE = {"CHN"}                                   # China is left out (its inflow is not a low-tax story)
BIG_HAVENS = ["IRL", "SGP", "CHE", "NLD", "PRI", "CYM", "HKG", "BMU"]
MIN_PROFIT = 1e9                                        # the footnote: jurisdictions with at least US$1bn of profit
IRS_SCATTER_NAMES = {"USA": "United States (home)", "GBR": "United Kingdom", "ARE": "UAE", "KOR": "South Korea", "VGB": "British Virgin Is.",
                     "CZE": "Czechia", "CYM": "Cayman Islands", "HKG": "Hong Kong"}
NEAR_ZERO_RATE = 2.0                                    # the text: almost all profit below 15%, at rates of less than 2%


def irs_recipients_table(M):
    """Return the table of Figure 2.8: the net recipients of shifted profit with the share of US multinationals' profit
    taxed below 15% there (a lower and an upper bound where the IRS suppresses a band), the rate on that low-taxed
    profit and its amount, ordered by the share."""
    L = irs_table4(Y)
    r = L[L["band"] == "lt15"].groupby("iso_partner").agg(p=("profit", "sum"), t=("tax", "sum")); r["etr_lt15"] = 100 * r["t"] / r["p"]
    i = pd.read_csv(ROOT / "data/intermediate/irs_low_tax_destinations.csv")
    y = i[i["year"] == Y].copy()
    y["share"] = y["share_below15"].fillna(y["share_below15_lower"]); y["upper"] = y["share_below15_upper"].fillna(y["share"])
    y["bounded"] = y["share_below15"].isna(); y["etr_lt15"] = y["iso_partner"].map(r["etr_lt15"])
    y = y.set_index("iso_partner")
    m = M[M["year"] == Y]
    net = m.groupby("iso_partner")["misaligned_profit"].sum() * DEFL_Y * SF_Y / 1e9
    rec = net[net > 0].sort_values(ascending=False)
    # I drop the home-bias recipients, the non-havens whose inflow is mostly their own groups' home profit (more than
    # 50% of the positive misalignment on iso_parent == iso_partner), such as Japan, Canada, Denmark, Thailand and
    # Italy.
    pos = m[m["misaligned_profit"] > 0]
    home_share = (pos[pos["iso_parent"] == pos["iso_partner"]].groupby("iso_partner")["misaligned_profit"].sum()
                  / pos.groupby("iso_partner")["misaligned_profit"].sum()).reindex(rec.index).fillna(0)
    rec = rec[rec.index.isin(config.TAX_HAVENS_REPRESENTATION) | (home_share < 0.5)]
    rec = rec.drop(IRS_EXCLUDE, errors="ignore")
    t = rec.to_frame("net_inflow_bn").join(y[["irs_name", "share", "upper", "bounded", "etr_lt15", "positive_profit_usd", "lt15"]], how="inner").head(N_RECIPIENTS)
    # I add every jurisdiction with at least as much low-taxed profit as the big havens (the US home cell and the UK).
    thr = y.loc[BIG_HAVENS, "lt15"].min()
    extra = y[(y["lt15"] >= thr) & ~y.index.isin(t.index) & ~y.index.isin(IRS_EXCLUDE)]
    t = pd.concat([t, extra[["irs_name", "share", "upper", "bounded", "etr_lt15", "positive_profit_usd", "lt15"]].assign(net_inflow_bn=net.reindex(extra.index))])
    t = t[t["share"].notna()]                            # not shown without an IRS share (all bands suppressed)
    t["name"] = [IRS_RECIPIENT_NAMES.get(k, n) for k, n in zip(t.index, t["irs_name"])]
    print(f"IRS recipients: {len(t)} jurisdictions (threshold US${thr / 1e9:,.1f}bn low-taxed profit; added {list(extra.index)})")
    return t.sort_values("share", ascending=False)   # ordered by the share, largest first


def irs_recipients(M):
    """Make Figure 2.8 and its table and return the jurisdictions of the figure whose low-taxed profit is taxed at
    less than NEAR_ZERO_RATE percent."""
    t = irs_recipients_table(M)
    # The chapter figure is a scatter of the share taxed below 15% (x) against the rate US groups report on that
    # low-taxed profit (y). The bubble area is the amount taxed below 15%. There is no title in the figure because the
    # caption is the title.
    sc = t[t["etr_lt15"].notna() & t["lt15"].notna()].copy()
    # I draw the canvas at about 1.5 times the report's text width (16.5 cm), so that the labels print at about 6.5 to
    # 7pt. The bubble areas (bubble) are scaled to the canvas.
    fig, ax = plt.subplots(figsize=(9.5, 6.0))
    bubble = 1000
    size = bubble * np.sqrt(sc["lt15"] / sc["lt15"].max())
    for _, rw in sc[sc["bounded"] & (sc["upper"] > sc["share"] + 0.005)].iterrows():   # band suppressed by the IRS: show the range
        ax.plot([100 * rw["share"], 100 * rw["upper"]], [rw["etr_lt15"]] * 2, color=tint(PURPLE, 0.5), lw=2, zorder=2)
    ax.scatter(100 * sc["share"], sc["etr_lt15"], s=size, c=LOSS, alpha=0.7, edgecolor="white", linewidth=1.2, zorder=3)

    def bubble_label(rw):
        bn = rw["lt15"] / 1e9
        return f"{rw['name']}: US${bn:,.0f}bn at {rw['etr_lt15']:.1f}%" if bn >= 1 else f"{rw['name']}: US${bn:.1f}bn at {rw['etr_lt15']:.1f}%"

    line = dict(arrowstyle="-", color="#9A958C", lw=0.6, shrinkA=0, shrinkB=4)
    for iso, (dx, dy, ha) in IRS_RECIPIENT_LABELS.items():
        if iso in sc.index:
            rw = sc.loc[iso]
            ax.annotate(bubble_label(rw), (100 * rw["share"], rw["etr_lt15"]), xytext=(dx, dy), textcoords="offset points",
                        fontsize=10, color=INK, ha=ha, zorder=4, arrowprops=line)
    col = sc[sc.index.isin(IRS_RECIPIENT_COLUMN)].sort_values("etr_lt15", ascending=False)
    for (iso, rw), ly in zip(col.iterrows(), np.linspace(4.4, 0.2, len(col))):
        ax.annotate(bubble_label(rw), (100 * rw["share"], rw["etr_lt15"]), xytext=(105.5, ly), textcoords="data", fontsize=10,
                    color=INK, ha="left", va="center", zorder=4, annotation_clip=False, arrowprops=line)
    # Every bubble has a label. A new bubble without one stops the script, so that it gets a place.
    unlabelled = set(sc.index) - set(IRS_RECIPIENT_LABELS) - set(IRS_RECIPIENT_COLUMN)
    if unlabelled:
        raise ValueError(f"bubbles without a label in Figure 2.8: {sorted(unlabelled)}")
    ax.set_xlim(25, 104); ax.set_ylim(0, max(12, sc["etr_lt15"].max() * 1.15))
    ax.set_xlabel("share of US multinationals' profit in the jurisdiction taxed below 15% (%)", fontsize=10.5)
    ax.set_ylabel("tax rate they pay on that low-taxed profit (%)", fontsize=10.5)
    ax.tick_params(labelsize=10.5)
    for v in (5e9, 50e9, 500e9):
        ax.scatter([], [], s=bubble * np.sqrt(v / sc["lt15"].max()), c=LOSS, alpha=0.7, edgecolor="white", label=f"US${v / 1e9:,.0f}bn")
    # The legend stands in a box right of the plot, above the column of labels, where it covers neither bubbles nor
    # labels. Its left edge lines up with the column (x = 105.5 in data units).
    leg = ax.legend(frameon=True, fancybox=False, framealpha=1, edgecolor="#9A958C", fontsize=10, loc="upper left",
                    bbox_to_anchor=(105.5, 1), bbox_transform=blended_transform_factory(ax.transData, ax.transAxes),
                    borderaxespad=0,
                    title="profit taxed below 15%", title_fontsize=10, labelspacing=1.5, borderpad=1.2, handletextpad=1.4)
    leg.get_frame().set_linewidth(0.8)
    fig.tight_layout()
    fig.savefig(FIG / f"figC8_irs_low_tax_shares_recipients_{Y}.png", dpi=200, bbox_inches="tight"); plt.close(fig)
    tt = t.sort_values("share").sort_values("net_inflow_bn", ascending=False).copy(); tt.insert(0, "key", KEY_LABEL); tt.index.name = "iso_partner"
    tt.round(3).to_csv(TAB / f"irs_low_tax_shares_recipients_{Y}_keys.csv")
    return sorted(sc.index[sc["etr_lt15"] < NEAR_ZERO_RATE])


def irs_share_vs_rate_table():
    """Return, for every jurisdiction with at least US$1bn of US groups' profit, the share of that profit taxed below
    15% and the average effective rate on all of it, and the share of the low-taxed profit booked where the average
    rate is 15% or more (all jurisdictions and outside the US)."""
    L = irs_table4(Y)
    pos = L[L["band"].isin(["lt15", "ge15"])]
    g = pos.pivot_table(index=["iso_partner", "name"], columns="band", values=["profit", "tax"], aggfunc="sum")
    g.columns = [f"{a}_{b}" for a, b in g.columns]
    g = g.reset_index()
    g["profit"] = g["profit_lt15"].fillna(0) + g["profit_ge15"].fillna(0)
    g["tax"] = g["tax_lt15"].fillna(0) + g["tax_ge15"].fillna(0)
    g["share_lt15"] = 100 * g["profit_lt15"] / g["profit"]
    g["etr"] = 100 * g["tax"] / g["profit"]
    g["etr_lt15"] = 100 * g["tax_lt15"] / g["profit_lt15"]
    g["haven"] = g["iso_partner"].isin(HAV)
    g["label"] = [IRS_SCATTER_NAMES.get(i, n) for i, n in zip(g["iso_partner"], g["name"])]
    tot_lt15 = g["profit_lt15"].sum()
    g = g[(g["profit"] >= MIN_PROFIT) & g["share_lt15"].notna()].copy()
    hi = g[g["etr"] >= 15]
    s_all = 100 * hi["profit_lt15"].sum() / tot_lt15
    s_xus = 100 * hi.loc[hi.iso_partner != "USA", "profit_lt15"].sum() / g.loc[g.iso_partner != "USA", "profit_lt15"].sum()
    return g, s_all, s_xus


def irs_share_below15():
    """Return the share of all the profit US multinationals report that is taxed below 15%, counting the profit on
    which they report negative taxes as well (IRS Table 4, all jurisdictions including the US). The loss-making
    entities are not part of it."""
    b = irs_table4(Y).groupby("band")["profit"].sum()
    return 100 * (b["lt15"] + b["neg_accrued"]) / (b["lt15"] + b["ge15"] + b["neg_accrued"])


def irs_figures(M):
    """Make Figure 2.8 and the table of the footnote and return the numbers the text quotes. The labels of the figure
    contain dollar signs, so I switch math text off while it is drawn."""
    with matplotlib.rc_context({"text.parse_math": False}):
        near_zero = irs_recipients(M)
    g, s_all, s_xus = irs_share_vs_rate_table()
    out = g.sort_values("profit_lt15", ascending=False)[["iso_partner", "label", "haven", "profit", "profit_lt15", "share_lt15", "etr", "etr_lt15"]]
    out.round(3).to_csv(TAB / f"irs_low_tax_share_vs_etr_{Y}.csv", index=False)
    print(f"IRS shares: {len(g)} jurisdictions; low-taxed profit where the average rate is >= 15%: {s_all:.1f}% (outside the US: {s_xus:.1f}%)")
    return {"irs_lowtax_in_high_avg": s_all, "irs_lowtax_in_high_avg_xus": s_xus, "irs_share_below15": irs_share_below15(),
            "irs_near_zero": near_zero}


# %% MARK: 8. Figure 2.9: who owns US corporate equity
# The figure is one bar, the distribution of US corporate equity and mutual fund shares by wealth group (Distributional
# Financial Accounts of the Federal Reserve, 2026Q2). Official incidence rules put 75–82% of the corporate income tax on
# the owners of capital (75% for the Congressional Budget Office (CBO) and the Joint Committee on Taxation (JCT), 82%
# for the US Treasury). That part is borne in proportion to equity ownership. The table gives the ownership shares the
# figure shows and the share of the tax borne by each wealth group under both rules, with the remainder borne by
# workers across all households.
INCIDENCE = ROOT / "data/raw/context/corporate_tax_incidence"
WEALTH_GROUPS = ["Top 1%", "Next 9%", "Next 40%", "Bottom 50%"]
OWNERSHIP = "Ownership of US corporate equity and mutual fund shares (Federal Reserve, 2026Q2)"


def incidence_figure():
    """Make Figure 2.9 and its table and return the ownership shares the text quotes."""
    e = pd.read_csv(INCIDENCE / "equity_ownership_shares.csv")
    inc = pd.read_csv(INCIDENCE / "incidence_assumptions.csv")

    def val(region, source_sub, year, asset_sub, group_sub):
        r = e[(e.region == region) & e.source.str.contains(source_sub) & (e.year.astype(str) == str(year)) & e.asset.str.contains(asset_sub) & e.group.str.contains(group_sub, regex=False)]
        return float(r.share_pct.iloc[0])

    us = {"Top 1%": val("USA", "DFA", "2026Q2", "Corporate equities", "Top 1%"), "Next 9%": val("USA", "DFA", "2026Q2", "Corporate equities", "90-99th"),
          "Next 40%": val("USA", "DFA", "2026Q2", "Corporate equities", "50-90th"), "Bottom 50%": val("USA", "DFA", "2026Q2", "Corporate equities", "Bottom 50%")}
    # Incidence is the capital share × ownership. The labour share is spread over all households.
    cbo = float(inc.loc[inc["body"] == "US Congressional Budget Office (CBO)", "capital_share_pct"].iloc[0])
    ota = float(inc.loc[inc["body"].str.startswith("US Treasury Office of Tax Analysis (OTA) - Technical Paper 5"), "capital_share_pct"].iloc[0])
    rules = {f"CBO / JCT rule\n({cbo:.0f}% on owners)": cbo, f"US Treasury rule\n({ota:.0f}% on owners)": ota}
    rows = []
    for rule, cap in rules.items():
        for g in WEALTH_GROUPS:
            rows.append(dict(rule=rule, group=g, pct=cap / 100 * us[g]))
        rows.append(dict(rule=rule, group="Workers (all households)", pct=100 - cap))
    # The ownership shares themselves, which the figure plots.
    rows += [dict(rule=OWNERSHIP, group=g, pct=us[g]) for g in WEALTH_GROUPS]
    pd.DataFrame(rows).round(1).to_csv(TAB / "who_pays_corporate_tax.csv", index=False)
    # I draw the canvas at about 1.2 times the report's text width (16.5 cm), so that the text prints at 7.5 to 8pt.
    fig, ax = plt.subplots(figsize=(7.8, 2.4))
    left = 0
    for g in WEALTH_GROUPS[::-1]:
        v = us[g]
        ax.barh(0, v, left=left, height=0.55, color=WEALTH_GROUP[g], edgecolor="white")
        if v > 4:
            ax.text(left + v / 2, 0, f"{g}\n{v:.0f}%", ha="center", va="center", fontsize=9.5, color="white" if g in ("Top 1%", "Bottom 50%") else INK,
                    fontweight="bold" if g == "Top 1%" else "normal")
        else:
            ax.annotate(f"{g}: {v:.1f}%", (left + v / 2, -0.28), xytext=(left + v / 2 + 1, -0.47), fontsize=9.3, color=EARTH_GREEN, ha="left",
                        arrowprops=dict(arrowstyle="-", color=EARTH_GREEN, lw=0.8))
        left += v
    ax.set_xlim(0, 100); ax.set_ylim(-0.55, 0.32); ax.set_yticks([])
    ax.set_xticks(range(0, 101, 10)); ax.set_xticklabels([f"{t}%" for t in range(0, 101, 10)], fontsize=9.3)
    ax.spines["left"].set_visible(False)
    plt.tight_layout(); plt.savefig(FIG / "figC10_who_pays_corporate_tax.png", dpi=200, bbox_inches="tight"); plt.close()
    print(f"incidence: the richest 10% own {us['Top 1%'] + us['Next 9%']:.0f}% of US corporate equity")
    return {"equity_top10": us["Top 1%"] + us["Next 9%"], "equity_top1": us["Top 1%"], "equity_bottom50": us["Bottom 50%"]}


# %% MARK: 9. Robustness: profit shifted only into low-taxed destinations
# The chapter's footnote. In the robustness runs, profit can be shifted only into jurisdiction-years where at least 30%
# (variant irs15_gate30) or more than 50% (irs15_gate) of the positive profit US multinationals book there is taxed
# below 15% (IRS Table 4, step 1). Tax havens that the IRS never lists separately qualify. No jurisdiction-year has a
# share of exactly 30% or 50%, so "at least 30%" and "more than 30%" select the same set. Script 5 removes the positive
# misalignment elsewhere and rescales each parent's profit shifted out to what remains (the destination gate,
# config.DEST_GATES). Otherwise the runs use the headline specification and the reported-only sample. "Revenue lost
# (net)" is positive where a country loses today (it equals its net gain under unitary taxation). I scale the world
# totals with the uniform world factor of 7a, which is the same for all three runs because it measures coverage, not
# the destination rule.
GATE_RUNS = {  # column label: estimates folder
    "main estimate": ESTIMATES,
    "only destinations ≥ 30% taxed below 15%": ROOT / "output/variants/irs15_gate30/estimates",
    "only destinations > 50% taxed below 15%": ROOT / "output/variants/irs15_gate/estimates",
}
GATE_SAMPLE = "reported_only"


def gate_load(estimates):
    d = headline_summary(estimates)
    k = d["year"].map(DEFL) / 1e3   # converts US$ million of the year to US$ bn at 2025 prices
    d["lost"] = d["revenue_gain_from_ut"] * k
    d["shifted_in"] = d["positive_misalignment"] * k
    d["mne_tax"] = pd.to_numeric(d["current_tax_paid_cash_musd"], errors="coerce") * k
    d["f"] = hc.factor_for(d, GATE_SAMPLE).to_numpy()
    return d


def gate_world():
    """Write the world totals by year of the three runs and return the 2023 values the footnote quotes."""
    world = []
    for run, estimates in GATE_RUNS.items():
        for y, x in gate_load(estimates).groupby("year"):
            f = x["f"]
            world.append(dict(sample=GATE_SAMPLE, run=run, year=y, factor=float(f.iloc[0]),
                              net_lost_bn=x["lost"].sum(), gross_lost_bn=x["lost"].clip(lower=0).sum(),
                              shifted_profit_bn=x["shifted_in"].sum(),
                              net_lost_scaled_bn=(x["lost"] * f).sum(), gross_lost_scaled_bn=(x["lost"].clip(lower=0) * f).sum(),
                              shifted_profit_scaled_bn=(x["shifted_in"] * f).sum(),
                              n_countries_losing=int((x["lost"] > 1e-9).sum())))
    W = pd.DataFrame(world)
    W.round(3).to_csv(TAB / "gate_robustness_world_by_year.csv", index=False)
    w23 = W[W["year"] == Y].set_index("run")
    runs = list(GATE_RUNS)
    print(f"robustness {Y}, world net scaled: " + ", ".join(f"{r} {w23.loc[r, 'net_lost_scaled_bn']:,.1f}" for r in runs))
    return {"gate_main": w23.loc[runs[0], "net_lost_scaled_bn"], "gate_ge30": w23.loc[runs[1], "net_lost_scaled_bn"],
            "gate_gt50": w23.loc[runs[2], "net_lost_scaled_bn"]}


# For comparison with earlier editions of The State of Tax Justice, the methodology note also gives the result under
# their rule: profit counts as shifted only where it ends up in a cell with an effective tax rate of at most 15%. No
# variant run exists for this rule, so I recompute it from the headline misalignment file, year by year, in the same
# way as the destination gate of script 5. I keep positive misalignment only in cells whose effective tax rate (the
# domestic or foreign rate the headline prices with, the statutory rate where it is undefined) is at most 15%, and I
# scale each headquarters country's negative misalignment down to the positive misalignment that remains. I price
# the result as the headline does: profit gained at the statutory rate, profit lost at the effective rate. The
# one-year recompute does not apply the multi-year loss cap of script 5. Without the rule it reproduces the headline,
# and the table gives the difference.
CLASSIC_ETR_MAX = 0.15


def classic_rule_net(M, rule):
    """Return the net revenue change of every row of the headline misalignment file (US$ bn at 2025 prices, positive
    where the country loses today) and the profit shifted into the row, with or without the classic rule."""
    mis = M["misaligned_profit"].to_numpy(dtype=float).copy()
    cit = pd.to_numeric(M["cit"], errors="coerce")
    etr = pd.to_numeric(M["etr_domfor_excl_resource"], errors="coerce")
    if rule:
        destination = (etr.fillna(cit) <= CLASSIC_ETR_MAX).to_numpy()
        mis = np.where((mis > 0) & ~destination, 0.0, mis)
        s = pd.Series(mis, index=M.index)
        keys = [M["year"], M["iso_parent"]]
        pos = s.clip(lower=0).groupby(keys).transform("sum")
        neg = (-s.clip(upper=0)).groupby(keys).transform("sum")
        mis = np.where(mis < 0, mis * np.where(neg > 0, pos / neg, 0.0), mis)
    k = M["year"].map(DEFL).to_numpy() / 1e9
    net = (np.where(mis < 0, -mis, 0.0) * cit.fillna(0.0).to_numpy()
           - np.where(mis > 0, mis, 0.0) * etr.fillna(0.0).to_numpy()) * k
    return net, np.where(mis > 0, mis, 0.0) * k


def classic_rule(M, S):
    """Write the world totals by year under the classic rule and return the scaled net of the latest year."""
    rows = []
    filed = S.assign(lost=S["revenue_gain_from_ut"] * S["year"].map(DEFL) / 1e3).set_index(["iso_partner", "year"])["lost"]
    for rule in (False, True):
        net, shifted = classic_rule_net(M, rule)
        d = pd.DataFrame({"iso_partner": M["iso_partner"], "year": M["year"], "net": net, "shifted": shifted})
        c = d.groupby(["iso_partner", "year"], as_index=False)[["net", "shifted"]].sum()
        c["f"] = hc.factor_for(c, GATE_SAMPLE).to_numpy()
        for y, x in c.groupby("year"):
            gap = (x.set_index(["iso_partner", "year"])["net"] - filed.reindex(x.set_index(["iso_partner", "year"]).index)
                   .fillna(0.0))
            rows.append(dict(rule=rule, year=y, factor=float(x["f"].iloc[0]), net_lost_bn=x["net"].sum(),
                             gross_lost_bn=x["net"].clip(lower=0).sum(), shifted_profit_bn=x["shifted"].sum(),
                             net_lost_scaled_bn=(x["net"] * x["f"]).sum(),
                             gross_lost_scaled_bn=(x["net"].clip(lower=0) * x["f"]).sum(),
                             shifted_profit_scaled_bn=(x["shifted"] * x["f"]).sum(),
                             n_countries_losing=int((x["net"] > 1e-9).sum()), max_country_gap_bn=gap.abs().max()))
    R = pd.DataFrame(rows)
    out = R[R["rule"]].drop(columns=["rule", "max_country_gap_bn"]).reset_index(drop=True)
    check = R[~R["rule"]].set_index("year")
    out["net_lost_bn_without_rule"] = out["year"].map(check["net_lost_bn"])
    out["net_lost_bn_headline"] = out["year"].map(
        S.assign(lost=lambda t: t["revenue_gain_from_ut"] * t["year"].map(DEFL) / 1e3).groupby("year")["lost"].sum())
    out["max_country_gap_without_rule_bn"] = out["year"].map(check["max_country_gap_bn"])
    out.round(4).to_csv(TAB / "classic_rule_etr15_world_by_year.csv", index=False)
    v = out.set_index("year").loc[Y]
    print(f"classic rule (effective tax rate ≤ 15%), {Y}, world net: {v['net_lost_bn']:,.1f} in the sample, "
          f"{v['net_lost_scaled_bn']:,.1f} scaled; without the rule {v['net_lost_bn_without_rule']:,.1f} against the "
          f"headline {v['net_lost_bn_headline']:,.1f} (largest country gap {v['max_country_gap_without_rule_bn']:.3f})")
    return {"classic_rule": v["net_lost_scaled_bn"]}


# %% MARK: 10. Methodology-note footnote: Japan and Canada with their own statistics
# The headline estimate gives every group the same market key, so the home market of Japanese and Canadian groups
# counts only with Japan's and Canada's share of world demand. Their national statistics show far more of these
# groups' sales at home. These are METI's Basic Survey of Overseas Business Activities (customer location) and the
# tables of Statistics Canada on Canadian multinationals (operating revenues in Canada minus exports, and the sales of
# affiliates abroad by country). The variants mkt_own_jpn / mkt_own_can rerun the headline estimate with only that
# country's own groups on its national statistics (keys of step 1a). Every other group keeps the market key.
FOOTNOTE_COUNTRIES = {
    # The URLs are those of the stored downloads listed in
    # data/raw/destination_based_sales/home_share_sources/manifest.csv.
    "JPN": ("Japan", "METI, Basic Survey of Overseas Business Activities",
            "https://www.e-stat.go.jp/stat-search/file-download?statInfId=000040458703&fileKind=2"),
    "CAN": ("Canada", "Statistics Canada, Tables 36-10-0356-01 and 36-10-0470-01",
            "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610035601 | "
            "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610047001"),
}


def country_result(estimates, iso):
    """Return a country's revenue change under unitary taxation in the latest year, in US$bn at 2025 prices,
    unscaled."""
    ce = pd.read_csv(estimates / RUN_TABLES / "excl_resource" / f"country_estimates__{HEADLINE}.csv")
    r = ce[(ce["year"] == Y) & (ce["iso_partner"] == iso)]
    return float(r["revenue_gain_from_ut"].iloc[0]) * DEFL_Y / 1e3


def footnote_own_statistics():
    """Write the table of the footnote: each country's result with the market key and with its own statistics, and
    the home shares of its groups' sales under both keys."""
    mk = pd.read_csv(ROOT / "data/intermediate/destination_based_sales.csv")
    mk = mk[mk["year"] == Y]
    rows = []
    for iso, (name, src, url) in FOOTNOTE_COUNTRIES.items():
        headline = country_result(ESTIMATES, iso)
        own = country_result(ROOT / f"output/variants/mkt_own_{iso.lower()}/estimates", iso)
        k = pd.read_csv(ROOT / f"data/intermediate/destination_based_sales_mkt_own_{iso.lower()}.csv")
        k = k[k["year"] == Y]
        home_nat = 100 * k.loc[k["iso_partner"] == iso, "hq_dest_key"].sum() / k["hq_dest_key"].sum()
        home_mkt = 100 * mk.loc[mk["iso_partner"] == iso, "mne_plus_dds_share"].sum() / mk["mne_plus_dds_share"].sum()
        rows.append(dict(iso3=iso, country=name, headline_estimate_bn=round(headline, 2), own_statistics_bn=round(own, 2),
                         home_share_market_key_pct=round(home_mkt, 1), home_share_national_pct=round(home_nat, 1),
                         source=src, url=url))
        print(f"  {name}: {headline:.2f} with the market key, {own:.2f} with its own statistics (US$ bn, {Y})")
    pd.DataFrame(rows).to_csv(TAB / "footnote_own_statistics_jpn_can.csv", index=False)


# %% MARK: 11. Methodology note, Appendix E: sales by origin and by destination on the sample with imputed rows
# Figure E3 of the methodology note compares the change in tax revenue under the headline formula (employees and sales
# by destination) with the same formula on sales by origin, on the sample with imputed rows. It has one column of
# panels per income group, with the years on the x-axis, in US$bn (top) and as % of the corporate tax the group's
# multinationals pay today (bottom). I deflate every country-year to 2025 prices and scale it with the world factor of
# that sample (sample "gravity" in host_scale_factors.csv), then sum the countries. The % divides by the cash tax of the
# countries that pay a positive amount. The figure keeps the style of the other two figures of Appendix E, which 7b
# draws in the brand colours, rather than the purple of the chapter figures.
IG_LABEL = {g: GRP[g] for g in ("low_income", "lower_middle_income", "upper_middle_income", "high_income", "tax_haven")}
OD_SERIES = [("sales_employees_destmnedds", "Destination-based", shade(GOLD, 0.3), "o"),   # gold darkened for a line
             ("sales_employees", "Origin-based", BLUE, "D")]
OD_ROWS = [("revenue_change_musd", "USD bn", 1e3, False), ("revenue_change_pct_tax", "% of current tax paid", 1.0, True)]
COVID_BAND = tint(GOLD, 0.2)
USD_FMT = FuncFormatter(lambda v, _: f"{v:,.0f}" if abs(v) >= 10 or v == 0 else f"{v:,.1f}")
PCT_FMT = FuncFormatter(lambda v, _: f"{v:,.0f}%")


def origin_destination_groups():
    """Return the change in tax revenue per formula, income group and year on the sample with imputed rows, in US$
    million at 2025 prices (scaled) and as % of the cash tax the multinationals pay today."""
    p = config.estimates_dir("gravity", "excl_resource") / "tables" / "summary_country_year_long.csv"
    d = pd.read_csv(p, low_memory=False, usecols=["formula_name", "etr_name", "rate_mode", "iso_partner", "wb_income_group",
                                                  "year", "revenue_gain_from_ut", "current_tax_paid_cash_musd"])
    d = d[(d["etr_name"] == "domfor") & (d["rate_mode"] == "loss_cit_gain_etr")
          & d["formula_name"].isin([s[0] for s in OD_SERIES]) & d["year"].isin(YEARS)].copy()
    f = hc.factor_for(d, "gravity")
    for c in ("revenue_gain_from_ut", "current_tax_paid_cash_musd"):
        d[c] = pd.to_numeric(d[c], errors="coerce") * d["year"].map(DEFL) * f
    d["cash_tax_pos"] = d["current_tax_paid_cash_musd"].where(d["current_tax_paid_cash_musd"] > 0)
    g = d.groupby(["formula_name", "wb_income_group", "year"], as_index=False).agg(
        revenue_change_musd=("revenue_gain_from_ut", "sum"), cash_tax_musd=("cash_tax_pos", "sum"))
    g["revenue_change_pct_tax"] = np.where(g["cash_tax_musd"] > 0, g["revenue_change_musd"] / g["cash_tax_musd"] * 100.0,
                                           np.nan)
    return g


def draw_origin_destination(g, fpath):
    """Draw Figure E3, with one line per sales measure and the COVID year shaded in every panel. Each panel has its own
    y-scale, because the income groups differ by orders of magnitude."""
    groups = [k for k in IG_LABEL if k in set(g["wb_income_group"])]
    fig, axes = plt.subplots(len(OD_ROWS), len(groups), figsize=(3.0 * len(groups), 2.8 * len(OD_ROWS) + 0.9),
                             squeeze=False)
    x = np.array(YEARS, dtype=float)
    for r, (col, ylabel, div, is_pct) in enumerate(OD_ROWS):
        for c, grp in enumerate(groups):
            ax = axes[r][c]
            for yy in sorted(config.EXCLUDE_YEARS):
                ax.axvspan(yy - 0.5, yy + 0.5, color=COVID_BAND, lw=0, zorder=0)
            sub = g[g["wb_income_group"] == grp]
            # I draw the headline (destination-based) line on top.
            for i, (formula, _label, colour, marker) in enumerate(OD_SERIES):
                v = sub[sub["formula_name"] == formula].set_index("year")[col].reindex(YEARS) / div
                ax.plot(x, v.to_numpy(), color=colour, marker=marker, lw=1.8, ms=4.5, markeredgecolor="white",
                        markeredgewidth=0.5, zorder=3 + len(OD_SERIES) - i)
            ax.axhline(0, color="grey", lw=0.6, zorder=1)
            ax.set_xticks(YEARS)
            ax.set_xticklabels([f"'{str(yy)[2:]}" for yy in YEARS], fontsize=8)
            ax.set_xlim(YEARS[0] - 0.6, YEARS[-1] + 0.6)
            ax.tick_params(axis="y", labelsize=8)
            ax.yaxis.set_major_formatter(PCT_FMT if is_pct else USD_FMT)
            if r == 0:
                ax.set_title(IG_LABEL[grp], fontsize=11)
            if c == 0:
                ax.set_ylabel(ylabel, fontsize=9)
    handles = [plt.Line2D([], [], color=colour, marker=marker, lw=1.8, ms=5, markeredgecolor="white")
               for _formula, _label, colour, marker in OD_SERIES] + [Patch(facecolor=COVID_BAND, edgecolor="none")]
    labels = [label for _formula, label, _colour, _marker in OD_SERIES] + [
        f"{', '.join(str(yy) for yy in sorted(config.EXCLUDE_YEARS))}: COVID year (low CbCR coverage)"]
    # The three legend entries fit on one row below the panels. I reserve 0.25 inch plus 0.22 inch for that row,
    # expressed as a share of the figure height.
    fig.legend(handles, labels, loc="lower center", ncol=len(labels), fontsize=9, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.tight_layout(rect=[0, (0.25 + 0.22) / fig.get_figheight(), 1, 1], w_pad=1.2)
    fig.savefig(fpath, dpi=130)
    plt.close(fig)


def origin_destination_figure():
    """Make Figure E3 of the methodology note."""
    g = origin_destination_groups()
    draw_origin_destination(g, FIG / "fig09_origin_dest_revenue_no_nexus.png")
    v = g[g["year"] == Y].pivot_table(index="wb_income_group", columns="formula_name", values="revenue_change_musd") / 1e3
    dest, orig = OD_SERIES[0][0], OD_SERIES[1][0]
    print(f"Appendix E figure, {Y}, US$bn scaled (destination / origin): "
          + ", ".join(f"{IG_LABEL[k]} {v.loc[k, dest]:,.1f} / {v.loc[k, orig]:,.1f}" for k in IG_LABEL if k in v.index))


# %% MARK: 12. Numbers quoted in the chapter
# The table has one row per number that the chapter text quotes from the aggregate data, with the value at full
# precision, the form in which the text quotes it, where it appears and the table it comes from. The country-level
# numbers of the EU table (Table 3.1) and the company numbers come from script 9.
T_SANKEY = f"output/chapter/tables/sankey_net_havens_{Y}_keys.csv"
T_SANKEY_TAX = f"output/chapter/tables/sankey_net_havens_tax_{Y}_keys.csv"
T_BLOCS = f"output/chapter/tables/blocs_{Y}_keys.csv"
T_MISALIGNMENT = f"output/estimates/{RUN_TABLES}/excl_resource/misalignment__{HEADLINE}.csv"
T_RATES = "output/chapter/tables/cit_long_run_by_year.csv"
T_INCIDENCE = "output/chapter/tables/who_pays_corporate_tax.csv"


def bn(v):
    return f"US${v:,.0f} billion"


def tn(v):
    return f"US${v / 1e3:,.1f} trillion"


def pct(v):
    return f"{v:.0f}%"


def chapter_numbers(n):
    """Write chapter_numbers_2023.csv from the numbers the sections return."""
    sec1 = "Profit shifting drains revenues from OECD and non-OECD countries alike"
    sec2 = "Despite years of OECD reforms, global profit shifting has not declined"
    sample = f"net_change_bn ÷ the {Y} scale factor ({SF_Y:.4f}, output/paper/main_text/tables/scaleup_yearly.csv)"
    rows = [
        ("years of the aggregate data", f"{YEARS[0]}–{YEARS[-1]}", "years", f"from {YEARS[0]} to {YEARS[-1]}", "Estimating shifted profits and lost revenues",
         "config.ANALYSIS_YEARS", ""),
        ("profit shifted into tax havens on balance (net), scaled", n["profit_to_havens"], "US$ bn", tn(n["profit_to_havens"]),
         f"{sec1} (Figure 2.1)", T_SANKEY, "sum of all flows"),
        ("profit OECD countries (excluding tax havens) lose to tax havens on balance, scaled", n["profit_oecd"], "US$ bn", bn(n["profit_oecd"]),
         f"{sec1} (Figure 2.1)", T_SANKEY, "row OECD countries (excluding tax havens), sum"),
        ("profit non-OECD countries (excluding tax havens) lose to tax havens on balance, scaled", n["profit_g77"], "US$ bn",
         bn(n["profit_g77"]), f"{sec1} (Figure 2.1)", T_SANKEY, "row Non-OECD countries (excluding tax havens), sum"),
        ("share of that profit booked in the eight largest destinations", n["share_top8"], "%", pct(n["share_top8"]),
         f"{sec1} (Figure 2.1)", T_SANKEY, f"the eight named havens ÷ all flows: {n['top8']}"),
        ("countries that lose profit on balance", n["n_losing"], "countries", f"{n['n_losing']} countries", sec1, T_MISALIGNMENT,
         f"jurisdictions with net misaligned profit < 0 in {Y}"),
        ("countries that are net recipients of profit", n["n_recipients"], "countries", f"{n['n_recipients']} are net recipients",
         sec1, T_MISALIGNMENT, f"jurisdictions with net misaligned profit > 0 in {Y}"),
        ("tax havens among the net recipients", n["n_haven_recipients"], "countries", f"{n['n_haven_recipients']} of them tax havens",
         sec1, T_SANKEY, "havens with a net inflow (the right-hand side of Figure 2.1)"),
        ("tax revenue lost by the non-haven countries (net), scaled", n["tax_lost_net"], "US$ bn", bn(n["tax_lost_net"]),
         f"{sec1} (Figure 2.2)", T_SANKEY_TAX, "net_tax_bn, loser rows, sum"),
        ("tax the havens collect on the profit shifted to them, scaled", n["tax_collected_havens"], "US$ bn",
         bn(n["tax_collected_havens"]), f"{sec1} (Figure 2.2)", T_SANKEY_TAX, "net_tax_bn, haven rows, sum"),
        ("tax lost elsewhere per dollar a tax haven collects", n["lost_per_collected"], "US$ per US$",
         f"{n['lost_per_collected']:.2f} dollars", f"{sec1} (Figure 2.2)", T_SANKEY_TAX, "loser rows ÷ haven rows"),
        ("world: tax revenue lost (net), sample", n["bloc_world_sample"], "US$ bn", bn(n["bloc_world_sample"]), f"{sec1} (Figure 2.3)",
         T_BLOCS, f"World, {sample}; also t4_world_by_year.csv net_unscaled"),
        ("world: as % of the corporate tax multinationals pay today", n["bloc_world_pct"], "%", pct(n["bloc_world_pct"]),
         f"{sec1} (Figure 2.3)", T_BLOCS, "World, net_change_pct_tax"),
        ("OECD: tax revenue lost (net), sample", n["bloc_oecd_sample"], "US$ bn", bn(n["bloc_oecd_sample"]),
         f"{sec1} (Figure 2.3)", T_BLOCS, f"OECD, {sample}"),
        ("OECD: as % of the tax paid", n["bloc_oecd_pct"], "%", pct(n["bloc_oecd_pct"]), f"{sec1} (Figure 2.3)",
         T_BLOCS, "OECD, net_change_pct_tax"),
        ("G77: tax revenue lost (net), sample", n["bloc_g77_sample"], "US$ bn", bn(n["bloc_g77_sample"]),
         f"{sec1} (Figure 2.3)", T_BLOCS, f"G77, {sample}"),
        ("G77: as % of the tax paid", n["bloc_g77_pct"], "%", pct(n["bloc_g77_pct"]), f"{sec1} (Figure 2.3)",
         T_BLOCS, "G77, net_change_pct_tax"),
        ("Latin America: tax revenue lost (net), sample", n["bloc_latam_sample"], "US$ bn",
         bn(n["bloc_latam_sample"]), f"{sec1} (Figure 2.3)", T_BLOCS, f"Latin America, {sample}"),
        ("Latin America: as % of the tax paid", n["bloc_latam_pct"], "%", pct(n["bloc_latam_pct"]),
         f"{sec1} (Figure 2.3)", T_BLOCS, "Latin America, net_change_pct_tax"),
        ("African Group: tax revenue lost (net), sample", n["bloc_african_sample"], "US$ bn",
         bn(n["bloc_african_sample"]), f"{sec1} (Figure 2.3)", T_BLOCS, f"African Group, {sample}"),
        ("African Group: as % of the tax paid", n["bloc_african_pct"], "%", pct(n["bloc_african_pct"]),
         f"{sec1} (Figure 2.3)", T_BLOCS, "African Group, net_change_pct_tax"),
        ("EU: tax revenue lost (net), sample", n["bloc_eu_sample"], "US$ bn", bn(n["bloc_eu_sample"]),
         f"{sec1} (Figure 2.3)", T_BLOCS, f"EU, {sample}"),
        ("EU: as % of the tax paid", n["bloc_eu_pct"], "%", pct(n["bloc_eu_pct"]), f"{sec1} (Figure 2.3)",
         T_BLOCS, "EU, net_change_pct_tax"),
        ("world: tax revenue lost (net), scaled", n["bloc_world_scaled"], "US$ bn", bn(n["bloc_world_scaled"]), f"{sec1} (Figure 2.3)",
         T_BLOCS, "World, net_change_bn; also t4_world_by_year.csv and tax_losses_by_year.csv net_scaled"),
        ("OECD: tax revenue lost (net), scaled", n["bloc_oecd_scaled"], "US$ bn", bn(n["bloc_oecd_scaled"]),
         f"{sec1} (Figure 2.3)", T_BLOCS, "OECD, net_change_bn"),
        ("G77: tax revenue lost (net), scaled", n["bloc_g77_scaled"], "US$ bn", bn(n["bloc_g77_scaled"]),
         f"{sec1} (Figure 2.3)", T_BLOCS, "G77, net_change_bn"),
        ("Latin America: tax revenue lost (net), scaled", n["bloc_latam_scaled"], "US$ bn",
         bn(n["bloc_latam_scaled"]), f"{sec1} (Figure 2.3)", T_BLOCS, "Latin America, net_change_bn"),
        ("African Group: tax revenue lost (net), scaled", n["bloc_african_scaled"], "US$ bn",
         bn(n["bloc_african_scaled"]), f"{sec1} (Figure 2.3)", T_BLOCS, "African Group, net_change_bn"),
        ("EU: tax revenue lost (net), scaled", n["bloc_eu_scaled"], "US$ bn", bn(n["bloc_eu_scaled"]),
         f"{sec1} (Figure 2.3)", T_BLOCS, "EU, net_change_bn"),
        ("tax havens: tax revenue gained (net), scaled", -n["bloc_havens_scaled"], "US$ bn", bn(-n["bloc_havens_scaled"]),
         f"{sec1} (Figure 2.3)", T_BLOCS, "Tax havens, −net_change_bn"),
        ("tax revenue lost by the losing countries (each netted first), scaled", n["tax_lost_losers_scaled"], "US$ bn",
         bn(n["tax_lost_losers_scaled"]), f"{sec2} (Figure 2.4)", "output/chapter/tables/tax_losses_by_year.csv",
         f"year {Y}, gross_scaled"),
        ("additional loss of the losing countries had every country kept its 2016 rates, scaled", n["loss_lower_rates_scaled"],
         "US$ bn", bn(n["loss_lower_rates_scaled"]), "The race to the bottom masks the full cost of corporate tax abuse (Figure 2.5)", "output/chapter/tables/tax_losses_2016_rates_by_year.csv",
         f"year {Y}, gross_2016rates_scaled − gross_now_scaled"),
        ("profit booked above what employees and sales warrant (gross), scaled", n["shifted_gross_scaled"], "US$ bn",
         tn(n["shifted_gross_scaled"]), f"{sec2} (Figure 2.4)",
         "output/chapter/tables/shifted_profit_fig_data.csv", f"havens_only False, year {Y}, scaled_bn"),
        (f"years since {YEARS[0]} with more profit shifted than {Y}", n["years_more_shifted"], "years",
         f"apart from the post-COVID year {n['years_more_shifted_list']}", sec2, "output/chapter/tables/shifted_profit_fig_data.csv",
         "havens_only False, scaled_bn by year"),
        ("share of US multinationals' profit taxed below 15% that is booked where their average rate is 15% or more",
         n["irs_lowtax_in_high_avg"], "%", pct(n["irs_lowtax_in_high_avg"]), "Estimating shifted profits and lost revenues (footnote)",
         f"output/chapter/tables/irs_low_tax_share_vs_etr_{Y}.csv",
         f"IRS Table 4, {Y}: profit_lt15 of the jurisdictions with etr >= 15 ÷ all profit taxed below 15% (all jurisdictions); "
         f"{n['irs_lowtax_in_high_avg_xus']:.0f}% outside the United States"),
        ("world: tax revenue lost (net), scaled, profit shifted only into destinations where at least 30% is taxed below 15%",
         n["gate_ge30"], "US$ bn", bn(n["gate_ge30"]), "not in the report: methodology note, robustness check (low-taxed destinations)", "output/chapter/tables/gate_robustness_world_by_year.csv",
         f"run 'only destinations ≥ 30% taxed below 15%', year {Y}, net_lost_scaled_bn"),
        ("world: tax revenue lost (net), scaled, profit shifted only into destinations where more than 50% is taxed below 15%",
         n["gate_gt50"], "US$ bn", bn(n["gate_gt50"]), "not in the report: methodology note, robustness check (low-taxed destinations)", "output/chapter/tables/gate_robustness_world_by_year.csv",
         f"run 'only destinations > 50% taxed below 15%', year {Y}, net_lost_scaled_bn"),
    ]
    # The losing and the winning countries of each bloc (Figure 2.3, left panel), sample and scaled.
    for tag, label in [("world", "world"), ("oecd", "OECD"), ("g77", "G77"), ("latam", "Latin America"),
                       ("african", "African Group"), ("eu", "EU"), ("havens", "tax havens")]:
        for side, verb, col in [("losses", "lost by the losing countries", "losses_bn"), ("gains", "gained by the winning countries", "gains_bn")]:
            for kind in ("sample", "scaled"):
                v = n[f"bloc_{tag}_{side}_{kind}"]
                rows.append((f"{label}: tax revenue {verb}, {kind}", v, "US$ bn", bn(v), f"{sec1} (Figure 2.3)", T_BLOCS,
                             f"{col}" + ("" if kind == "scaled" else f" ÷ the {Y} scale factor")))
    # The titles of the chapter's sections, for the numbers below.
    s_shift = "Profit shifting drains revenues from OECD and non-OECD countries alike"
    s_rates = "Lower tax rates have not brought profits home – but allowed multinationals to contribute ever less"
    s_rich = "Corporate tax abuse and the race to the bottom benefit the super-rich"
    s_race = "The race to the bottom masks the full cost of corporate tax abuse"
    dep = n["n_dependencies"]
    lost_per_gained = n["bloc_world_losses_scaled"] / n["bloc_world_gains_scaled"]
    rows += [
        ("tax lost by the losing countries per dollar gained by all the countries that gain", lost_per_gained, "US$ per US$",
         f"US${lost_per_gained:.2f}", f"{s_shift} (footnote to the paragraph on Figure 2.3)", T_BLOCS,
         "World, losses_bn ÷ gains_bn"),
        ("share by which the lower tax rates since 2016 raise the losses of the losing countries", n["loss_lower_rates_pct"], "%",
         pct(n["loss_lower_rates_pct"]), f"{s_race} (Figure 2.5)", "output/chapter/tables/tax_losses_2016_rates_by_year.csv",
         f"year {Y}, gross_2016rates_sample ÷ gross_now_sample − 1"),
        ("jurisdictions classified as tax havens", n["n_havens"], "jurisdictions", str(n["n_havens"]),
         "Estimating shifted profits and lost revenues (footnote on the list of tax havens)", T_BLOCS, "Tax havens, n_countries; config.TAX_HAVENS_REPRESENTATION"),
        ("tax havens that are not independent states", sum(dep.values()), "jurisdictions",
         f"{sum(dep.values())} of the {n['n_havens']}",
         "Estimating shifted profits and lost revenues (footnote on the list of tax havens)", "config.TAX_HAVENS_REPRESENTATION",
         "; ".join(f"{state} {k}" for state, k in dep.items())),
        ("jurisdictions in the balanced set of the average statutory rate", n["n_balanced"], "jurisdictions",
         f"a fixed sample of {n['n_balanced']} jurisdictions", f"{s_rates} (note of Figure 2.6)", T_RATES,
         "rate in 1980, in 2023 and in at least 90% of the years in between"),
    ]
    for _, _, lab in RATE_BANDS_PCT:
        r = n["band_ratios"][lab]
        rows.append((f"statutory rates {lab}: share of jurisdictions in 2023 ÷ share in 1980", r, "ratio", f"×{r:.2f}",
                     f"{s_rates} (Figure 2.7 and the text before it)", T_RATES, f"'{lab}', 2023 ÷ 1980"))
    rows += [
        (f"share of US multinationals' profit taxed below 15%, {Y}, counting the profit with negative taxes",
         n["irs_share_below15"], "%", pct(n["irs_share_below15"]), f"{s_rates} (text before Figure 2.8)",
         "data/intermediate/irs_soi_cbcr_table4_long.csv",
         f"IRS Table 4, {Y}, all jurisdictions: (lt15 + neg_accrued) ÷ (lt15 + ge15 + neg_accrued)"),
        (f"jurisdictions of Figure 2.8 whose low-taxed profit is taxed at less than {NEAR_ZERO_RATE:.0f}%",
         len(n["irs_near_zero"]), "jurisdictions", "several jurisdictions ... less than 2%", f"{s_rates} (text before Figure 2.8)",
         f"output/chapter/tables/irs_low_tax_shares_recipients_{Y}_keys.csv", "etr_lt15 < 2: " + ", ".join(n["irs_near_zero"])),
        ("share of US corporate equity owned by the wealthiest 10% of households", n["equity_top10"], "%", pct(n["equity_top10"]),
         f"{s_rich} (Figure 2.9)", T_INCIDENCE, "ownership rows, Top 1% + Next 9%"),
        ("share of US corporate equity owned by the top 1%", n["equity_top1"], "%", pct(n["equity_top1"]),
         f"{s_rich} (Figure 2.9)", T_INCIDENCE, "ownership rows, Top 1%"),
        ("share of US corporate equity owned by the bottom 50%", n["equity_bottom50"], "%", "less than 1%",
         f"{s_rich} (Figure 2.9)", T_INCIDENCE, "ownership rows, Bottom 50%"),
    ]
    t = pd.DataFrame(rows, columns=["name", "value", "unit", "as_in_text", "where_in_chapter", "source_table", "note"])
    t["value"] = [round(v, 4) if isinstance(v, (float, np.floating)) else v for v in t["value"]]
    t.to_csv(TAB / f"chapter_numbers_{Y}.csv", index=False)
    # The robustness table and the bloc table must give the same world total.
    assert abs(n["gate_main"] - n["bloc_world_scaled"]) < 0.05, (n["gate_main"], n["bloc_world_scaled"])
    print(f"chapter numbers: {len(t)} rows")


# %% MARK: 13. Numbers quoted in the methodology note
# The methodology note quotes many numbers that the run produces but that no results table holds: counts of the
# sample, the size of the corrections step 1 makes to the published data and a few ratios. I compute each from the
# data and write it with the note's macro and place, so that every number of the note can be traced to the package.
# The corrections of step 1 are recounted from the OECD file as published and the cleaned data. Where step 1 applies
# a rule (the employee unit errors), I apply the rule's test to the published data.
CBCR_RAW_COLS = ["REF_AREA", "COUNTERPART_AREA", "MEASURE", "STATISTICAL_OPERATION", "PROFIT_GROUPING", "TIME_PERIOD",
                 "OBS_VALUE", "OBS_STATUS"]
NOT_JURISDICTIONS = {"W", "STLS"}             # the reporter's grand total and the stateless row, not partners
CONTINUOUS_FROM = 2019                        # the last year of the OECD's own estimate of global profit (7a)
SWINGS = ROOT / "output/diagnostics/haven_loss_swings/haven_loss_swings.csv"
UK_IMPUTATION = ROOT / "output/diagnostics/cbcr_profit_imputation/uk_domestic_profit_carryforward.csv"


@lru_cache(maxsize=None)
def cbcr_raw():
    """Return OECD CbCR Table I as published (config.cbcr_data): one row per headquarters × partner × profit grouping
    (_T all sub-groups, PANELAI profit-making, PANELAII loss-making) × year × measure, without the ETR percentiles."""
    d = pd.read_csv(config.cbcr_data, usecols=CBCR_RAW_COLS)
    return d[(d["STATISTICAL_OPERATION"] == "_Z") & d["TIME_PERIOD"].isin(YEARS)]


def raw_value(parent, partner, year, measure, grouping="_T"):
    """Return one published value (NaN where it is suppressed or missing)."""
    d = cbcr_raw()
    v = d.loc[(d["REF_AREA"] == parent) & (d["COUNTERPART_AREA"] == partner) & (d["TIME_PERIOD"] == year)
              & (d["MEASURE"] == measure) & (d["PROFIT_GROUPING"] == grouping), "OBS_VALUE"]
    return float(v.iloc[0]) if len(v) else np.nan


@lru_cache(maxsize=None)
def cbcr_main():
    """Return the cleaned data of step 1 (all three profit groupings)."""
    return pd.read_csv(config.data_final + "cbcr_main.csv", low_memory=False, usecols=[
        "year", "iso_parent", "iso_partner", "grouping", "profit_loss_before_income_tax",
        "profit_loss_before_income_tax_corrected", "total_revenues", "n_employees"])


def clean_value(parent, partner, year, column, grouping="Total (All sub-groups)"):
    d = cbcr_main()
    v = d.loc[(d["iso_parent"] == parent) & (d["iso_partner"] == partner) & (d["year"] == year)
              & (d["grouping"] == grouping), column]
    return float(v.iloc[0])


def employee_unit_errors():
    """Return the cells whose headcount step 1 resets as an error in the unit. I apply its test to the published data
    of the parent-years and partners that the cleaned data keep: in the all-sub-groups data, at least 50,000 employees
    and more than five times the cell's average in its other years (at least four years), while revenues, profit and
    tangible assets stay within twice their average. A flagged cell is reset where, in some profit grouping, the
    headcount exceeds five times the cell's revenues times its usual ratio of employees to revenues."""
    d = cbcr_raw()
    d = d[d["MEASURE"].isin(["EMPLOYEES", "TOT_REV", "PROFIT", "ASSETS"])]
    w = d.pivot_table(index=["REF_AREA", "COUNTERPART_AREA", "PROFIT_GROUPING", "TIME_PERIOD"], columns="MEASURE",
                      values="OBS_VALUE").reset_index()
    c = cbcr_main()
    kept_years = set(zip(c["iso_parent"], c["year"]))
    w = w[pd.Series(list(zip(w["REF_AREA"], w["TIME_PERIOD"])), index=w.index).isin(kept_years)
          & w["COUNTERPART_AREA"].isin(set(c["iso_partner"]))]
    cells = []
    for (p, q), g in w[w["PROFIT_GROUPING"] == "_T"].groupby(["REF_AREA", "COUNTERPART_AREA"]):
        if g["TIME_PERIOD"].nunique() < 4:
            continue
        for _, r in g.iterrows():
            o = g[g["TIME_PERIOD"] != r["TIME_PERIOD"]]

            def flat(col):
                m = o[col].mean()
                return bool(m <= 0 or abs(r[col]) <= 2.0 * abs(m))

            m_emp = o["EMPLOYEES"].mean()
            if (pd.notna(r["EMPLOYEES"]) and r["EMPLOYEES"] >= 50_000 and m_emp > 0 and r["EMPLOYEES"] > 5.0 * m_emp
                    and flat("TOT_REV") and flat("PROFIT") and flat("ASSETS")):
                cells.append((p, q, int(r["TIME_PERIOD"])))
    reset = []
    for p, q, y in dict.fromkeys(cells):
        for _, sub in w[(w["REF_AREA"] == p) & (w["COUNTERPART_AREA"] == q)].groupby("PROFIT_GROUPING"):
            row, o = sub[sub["TIME_PERIOD"] == y], sub[sub["TIME_PERIOD"] != y]
            if row.empty or not (row["TOT_REV"].iloc[0] > 0) or pd.isna(row["EMPLOYEES"].iloc[0]):
                continue
            ratio = (o["EMPLOYEES"] / o["TOT_REV"]).replace([np.inf, -np.inf], np.nan).mean()
            if pd.notna(ratio) and ratio > 0 and row["EMPLOYEES"].iloc[0] > 5.0 * row["TOT_REV"].iloc[0] * ratio:
                reset.append((p, q, y))
                break
    return reset


def africa_lost_per_dollar(M, S):
    """Return the tax revenue the African countries that lose profit on balance lose (net, the headline estimate) per
    dollar of tax that the places where their profit is booked collect on it, in 2023, unscaled. I spread each
    country's net profit loss over the destinations by its gross bilateral flows (the bilateral-links rule within the
    panel of each headquarters country) and value the profit at each destination at the rate the estimate prices it
    there, the domestic or foreign effective rate of the headquarters-destination cell (zero where it is missing). The
    African tax havens are destinations, not losers."""
    m = M[(M["year"] == Y) & M["misaligned_profit"].notna()].copy()
    m["bn"] = m["misaligned_profit"] * DEFL_Y / 1e9
    s = S[S["year"] == Y].set_index("iso_partner")
    africa = set(s.index[s["region_tjn"] == "Africa"]) - HAV
    net = -m[m["iso_partner"].isin(africa)].groupby("iso_partner")["bn"].sum()
    losers = net[net > 0]
    tax = (s["revenue_gain_from_ut"] * DEFL_Y / 1e3).reindex(losers.index).fillna(0.0)
    cell_rate = m.set_index(["iso_parent", "iso_partner"])["etr_domfor_excl_resource"]
    rows = []
    for p, g in m.groupby("iso_parent"):
        pos = g[g["bn"] > 0]
        neg = g[(g["bn"] < 0) & g["iso_partner"].isin(losers.index)]
        if pos.empty or neg.empty:
            continue
        share = pos.groupby("iso_partner")["bn"].sum() / pos["bn"].sum()
        for c, v in (-neg.groupby("iso_partner")["bn"].sum()).items():
            rows += [dict(origin=c, dest=d, parent=p, bn=v * sh) for d, sh in share.items()]
    r = pd.DataFrame(rows)
    r["rate"] = pd.Series([cell_rate.get((pp, dd), np.nan) for pp, dd in zip(r["parent"], r["dest"])],
                          index=r.index).fillna(0.0)
    r["tax"] = r["bn"] * r["rate"]
    G = r.groupby(["origin", "dest"])["bn"].sum().unstack(fill_value=0.0).reindex(index=losers.index, fill_value=0.0)
    F = G.div(G.sum(axis=1).replace(0, np.nan), axis=0).mul(losers, axis=0).fillna(0.0)
    g2 = r.groupby(["origin", "dest"])[["tax", "bn"]].sum()
    rate = (g2["tax"] / g2["bn"]).unstack().reindex(index=F.index, columns=F.columns).fillna(0.0)
    return tax.sum() / (F * rate).values.sum(), len(losers)


def methodology_note_numbers(n, M, S):
    """Write methodology_note_numbers.csv: every number of the methodology note that the run produces but no results
    table holds, with the value at full precision, the form in which the note shows it and where."""
    rows = []

    def add(name, value, unit, as_in_text, where, source, note=""):
        rows.append((name, value, unit, as_in_text, where, source, note))

    raw_src = f"{Path(config.cbcr_data).relative_to(ROOT)} (the OECD file as published)"
    clean_src = "data/final/cbcr_main.csv"
    raw = cbcr_raw()
    # ---- the headquarter jurisdictions in the OECD file ----
    reporters = raw.groupby("TIME_PERIOD")["REF_AREA"].unique().apply(set)
    for y in YEARS:
        where = {YEARS[0]: r"\nreporterstwosix (1_data.tex; Appendix B); ", Y: r"\nreporterstwothree (1_data.tex; Appendix B); "}
        add(f"headquarter jurisdictions in the OECD file, {y}", len(reporters[y]), "jurisdictions", str(len(reporters[y])),
            where.get(y, "") + "Table B1, column 2", raw_src, "distinct REF_AREA")
    new, gone = sorted(reporters[Y] - reporters[Y - 1]), sorted(reporters[Y - 1] - reporters[Y])
    add(f"headquarter jurisdictions in the OECD file in {Y} but not in {Y - 1}", len(new), "jurisdictions",
        "six new or returning reporters", "1_data.tex (the 2023 vintage)", raw_src, ", ".join(new))
    add(f"headquarter jurisdictions in the OECD file in {Y - 1} but not in {Y}", len(gone), "jurisdictions",
        "two absent", "1_data.tex (the 2023 vintage)", raw_src, ", ".join(gone))
    # ---- the reported-only sample ----
    x = pd.read_csv(config.data_final + "cbcr_main_excl_resource.csv", low_memory=False)
    f = x[x["iso_partner"] != x["iso_parent"]]
    upr = pd.to_numeric(f["unrelated_party_revenues"], errors="coerce").fillna(0.0)
    tot = upr.groupby([f["iso_parent"], f["year"]]).sum()
    share = upr.where(f["is_distributed"] == 1, 0.0).groupby([f["iso_parent"], f["year"]]).sum() / tot.where(tot > 0)
    flagged = share[share > 0.5].index
    src5 = "data/final/cbcr_main_excl_resource.csv (the partial-reporter rule of script 5)"
    add("parent-years dropped by the partial-reporter rule", len(flagged), "parent-years", str(len(flagged)),
        r"\nparentyearsdropped (1_data.tex)", src5, "share of foreign unrelated-party revenues in aggregate rows > 50%")
    add("headquarter jurisdictions affected by the partial-reporter rule", flagged.get_level_values(0).nunique(),
        "jurisdictions", str(flagged.get_level_values(0).nunique()), r"\nparentsdropped (1_data.tex)", src5)
    mis = pd.read_csv(MISALIGNMENT, usecols=["iso_parent", "iso_partner", "year"])
    add("headquarter jurisdictions in the reported-only sample", mis["iso_parent"].nunique(), "jurisdictions",
        str(mis["iso_parent"].nunique()), r"\nparentssample (1_data.tex; Appendix B; Table B1 note)", T_MISALIGNMENT,
        "distinct iso_parent, all years")
    add("partner jurisdictions in the reported-only sample", mis["iso_partner"].nunique(), "jurisdictions",
        str(mis["iso_partner"].nunique()), r"\npartnerssample (1_data.tex)", T_MISALIGNMENT, "distinct iso_partner")
    py = mis[["iso_parent", "year"]].drop_duplicates()
    add("parent-years in the reported-only sample", len(py), "parent-years", str(len(py)), "Appendix B; Table B1 note",
        T_MISALIGNMENT)
    for y, k in py.groupby("year").size().items():
        add(f"headquarter jurisdictions in the reported-only sample, {y}", int(k), "jurisdictions", str(k),
            "Table B1, column 7", T_MISALIGNMENT)
    z = pd.read_csv(config.data_final + "cbcr_main_allsubgroupsonly.csv",
                    usecols=["year", "iso_parent", "iso_partner", "income_tax_paid_on_cash_basis"])
    z = z[(z["iso_parent"] != z["iso_partner"]) & z["iso_partner"].isin(["CYM", "BMU", "VGB"])]
    v = (z["income_tax_paid_on_cash_basis"] * z["year"].map(DEFL)).sum() / 1e9
    add("tax foreign groups report paid in the Cayman Islands, Bermuda and the British Virgin Islands, 2016–2023", v,
        "US$ bn (2025 prices)", f"{v:.1f}", r"\zerocittaxpaid (1_data.tex)", "data/final/cbcr_main_allsubgroupsonly.csv",
        "income_tax_paid_on_cash_basis, foreign cells, all sub-groups")
    d = pd.read_csv(config.data_final + "cbcr_main_disaggregated.csv", usecols=["iso_parent", "year"])
    rows_by_year = d[d["year"] >= CONTINUOUS_FROM].groupby(["iso_parent", "year"]).size().unstack("year")
    cont = rows_by_year.reindex(columns=[y for y in YEARS if y >= CONTINUOUS_FROM]).dropna()
    add(f"headquarter jurisdictions that report in every year from {CONTINUOUS_FROM} to {Y}", len(cont), "jurisdictions",
        str(len(cont)), r"\ncontinuousreporters (1_data.tex)", "data/final/cbcr_main_disaggregated.csv",
        "the countries whose profit growth extends the OECD's global profit after 2019 (7a)")
    # ---- the estimates ----
    t = n["shifted_out_pct_profit_world"]
    add(f"profit shifted (gross) as % of the profit reported net of losses, {Y}", t, "%", f"{t:.0f}",
        r"\shiftedsharetwothree (2_methodology.tex)", T_BLOCS, "World, shifted_out_pct_profit")
    t = 100 / n["lost_per_collected"]
    add("tax the havens collect per dollar of tax lost by the non-haven countries", t, "US cents", f"{t:.0f}",
        r"\centsperdollartwothree (2_methodology.tex)", T_SANKEY_TAX, "haven rows ÷ loser rows of net_tax_bn")
    t, k = africa_lost_per_dollar(M, S)
    add(f"tax lost by the African countries that lose profit on balance per dollar collected where the profit is booked, {Y}",
        t, "US$ per US$", f"{t:.1f}", r"\africalostperdollartwothree (2_methodology.tex)", T_MISALIGNMENT,
        f"{k} African countries, unscaled; destinations valued at the domestic/foreign effective rate of each cell")
    s = S[S["year"] == Y].set_index("iso_partner")["revenue_gain_from_ut"] * DEFL_Y / 1e3
    for iso, macro in (("ARE", r"\uaewith"), ("IDN", r"\idnwith"), ("MYS", r"\myswith")):
        add(f"{iso}: tax revenue lost (net), {Y}, headline estimate", s[iso], "US$ bn (2025 prices)", f"{s[iso]:.1f}",
            f"{macro} (2_methodology.tex, the resource-correction paragraph)",
            f"output/estimates/{RUN_TABLES}/summary_country_year_long.csv", "unscaled")
    mm = M[(M["year"] == Y) & (M["iso_partner"] == "SWZ")]
    t = 100 * mm.loc[mm["iso_parent"] == "USA", "profit_loss_excl_resource"].sum() / mm["profit_loss_excl_resource"].sum()
    add(f"share of the multinational profit reported in Eswatini that US groups report, {Y}", t, "%", f"{t:.0f}",
        r"\eswatiniusshare (1_data.tex)", T_MISALIGNMENT)
    # ---- the resource correction ----
    r = hc.reported_estimate_sample(x)
    r = r[r["year"] == Y]
    strip = pd.to_numeric(r["resource_profit_base_usd"], errors="coerce").fillna(0.0)
    profit_pos = pd.to_numeric(r["profit_loss_before_income_tax_corrected"], errors="coerce").clip(lower=0).sum()
    anchored = strip[r["resource_correction_method"].isin(["company_anchor", "company_anchor_tax_inferred"])].sum()
    add(f"profit removed by the resource correction, {Y}, reported-only sample", strip.sum() * DEFL_Y / 1e9,
        "US$ bn (2025 prices)", f"{strip.sum() * DEFL_Y / 1e9:.0f}", r"\resstriptwothree (2_methodology.tex)",
        "data/final/cbcr_main_excl_resource.csv", "resource_profit_base_usd, the reported cells of the sample's parent-years")
    add("as % of the positive reported profit", 100 * strip.sum() / profit_pos, "%",
        f"{100 * strip.sum() / profit_pos:.0f}", r"\resstrippcttwothree (2_methodology.tex)",
        "data/final/cbcr_main_excl_resource.csv", "profit_loss_before_income_tax_corrected clipped at zero")
    add("share of it removed on the basis of company-level data", 100 * anchored / strip.sum(), "%",
        f"{100 * anchored / strip.sum():.0f}", r"\resstripanchorpct (2_methodology.tex)",
        "data/final/cbcr_main_excl_resource.csv", "resource_correction_method company_anchor and company_anchor_tax_inferred")
    # ---- the market key ----
    k = pd.read_csv(ROOT / "data/intermediate/destination_based_sales.csv")
    o = k[k["dds_imports_exip_usd"] > 0]
    dds = (100 * o["dds_exip_mne"] / o["dds_imports_exip_usd"]).groupby(o["year"]).mean()
    src1a = "data/intermediate/destination_based_sales.csv"
    add("multinationals' share of digitally deliverable sector exports, lowest year", dds.min(), "%", f"{dds.min():.0f}",
        r"\ddsmnesharelow (2_methodology.tex)", src1a, f"dds_exip_mne ÷ dds_imports_exip_usd, {int(dds.idxmin())}")
    add("multinationals' share of digitally deliverable sector exports, highest year", dds.max(), "%", f"{dds.max():.0f}",
        r"\ddsmnesharehigh (2_methodology.tex)", src1a, f"dds_exip_mne ÷ dds_imports_exip_usd, {int(dds.idxmax())}")
    t = k.loc[k["mne_is_imputed"] == 0, "iso_partner"].nunique()
    add("economies with multinationals' local sales in the OECD's analytical database (AAMNE)", t, "economies", str(t),
        "1_data.tex (the market key)", src1a, "mne_is_imputed == 0")
    t = k.loc[k["dds_imports_exip_usd"].notna(), "iso_partner"].nunique()
    add("economies with imports of digitally deliverable services (BaTIS)", t, "economies", "roughly 200",
        "1_data.tex (the market key)", src1a, "dds_imports_exip_usd observed")
    # ---- corrections of step 1: loss swings in tax havens and the UK's home profit ----
    sw = pd.read_csv(SWINGS)
    add("losses removed by the rule on loss swings in tax havens, 2016–2023", -sw["removed_usd"].sum() / 1e9,
        "US$ bn (nominal)", f"{-sw['removed_usd'].sum() / 1e9:,.0f}", r"\swingresetsbn (C_dividend.tex)",
        str(SWINGS.relative_to(ROOT)), f"{len(sw)} loss panels")
    big = sw.loc[sw["removed_usd"].idxmin()]
    add(f"largest loss swing: {big['iso_parent']} groups in {big['iso_partner']} {int(big['year'])}, loss as reported",
        -big["loss_panel_usd"] / 1e9, "US$ bn (nominal)", f"{-big['loss_panel_usd'] / 1e9:.0f}", "C_dividend.tex",
        str(SWINGS.relative_to(ROOT)))
    add(f"largest loss swing: {big['iso_parent']} groups in {big['iso_partner']} {int(big['year'])}, loss after the reset",
        -big["reset_to_usd"] / 1e9, "US$ bn (nominal)", f"{-big['reset_to_usd'] / 1e9:.0f}", "C_dividend.tex",
        str(SWINGS.relative_to(ROOT)))
    c = cbcr_main()
    neg = c[(c["grouping"] == "Sub-groups with negative profits") & (c["iso_parent"] != c["iso_partner"])
            & ~c["iso_partner"].isin(config.TAX_HAVENS_FUNCTIONAL) & ~c["iso_partner"].isin(config.non_countries)]
    neg = neg[(neg["profit_loss_before_income_tax"] < 0) & (neg["total_revenues"] > 0)]
    neg = neg[neg["year"] == Y]
    t = 100 * neg["profit_loss_before_income_tax"].sum() / neg["total_revenues"].sum()
    add(f"ordinary loss margin of the loss-making groups in non-haven foreign cells, {Y}", t, "%", f"{t:.1f}",
        r"\swingmargintwothree (C_dividend.tex)", clean_src,
        "loss ÷ total revenues, loss-making groups, foreign cells outside the frozen haven list (the benchmark of the rule)")
    uk = pd.read_csv(UK_IMPUTATION).iloc[0]
    add(f"UK groups at home, {Y}: published profit of the profit-making groups", uk["source_reported_profit_usd"] / 1e9,
        "US$ bn (nominal)", f"{uk['source_reported_profit_usd'] / 1e9:.2f}", r"\ukpositivepanel (Table C1)",
        str(UK_IMPUTATION.relative_to(ROOT)))
    add("UK groups at home: average loss of the loss-making groups, 2017–2022", -uk["source_corrected_profit_usd"] / 1e9,
        "US$ bn (nominal)", f"{-uk['source_corrected_profit_usd'] / 1e9:.1f}", r"\uklossmean (Table C1)",
        str(UK_IMPUTATION.relative_to(ROOT)))
    add(f"UK groups at home, {Y}: profit as imputed", uk["imputed_corrected_profit_usd"] / 1e9, "US$ bn (nominal)",
        f"{uk['imputed_corrected_profit_usd'] / 1e9:.1f}", r"\ukhomeprofit (Table C1)", str(UK_IMPUTATION.relative_to(ROOT)))
    gb = raw[(raw["REF_AREA"] == "GBR") & (raw["TIME_PERIOD"] == Y) & (raw["MEASURE"] == "PROFIT")
             & (raw["PROFIT_GROUPING"] == "_T") & ~raw["COUNTERPART_AREA"].isin(NOT_JURISDICTIONS | {"GBR", "WXD"})]
    pub = gb[gb["OBS_VALUE"].notna()]
    wxd = raw_value("GBR", "WXD", Y, "PROFIT")
    add(f"UK groups, {Y}: partner jurisdictions", len(gb), "jurisdictions", str(len(gb)),
        r"\ukpartnersall (1_data.tex; Table C1)", raw_src)
    add(f"UK groups, {Y}: partner jurisdictions with a published profit", len(pub), "jurisdictions", str(len(pub)),
        r"\ukpartnerspublished (Table C1)", raw_src)
    add(f"UK groups, {Y}: partner jurisdictions with a suppressed profit", len(gb) - len(pub), "jurisdictions",
        str(len(gb) - len(pub)), r"\ukpartnerssuppressed (1_data.tex; Table C1)", raw_src)
    add(f"UK groups, {Y}: sum of the published partner profits", pub["OBS_VALUE"].sum() / 1e9, "US$ bn (nominal)",
        f"{pub['OBS_VALUE'].sum() / 1e9:.0f}", r"\ukpartnersprofit (Table C1)", raw_src)
    add(f"UK groups, {Y}: published foreign total", wxd / 1e9, "US$ bn (nominal)", f"{wxd / 1e9:.0f}",
        r"\ukforeigntotal (Table C1)", raw_src, "partner WXD")
    add(f"UK groups, {Y}: net loss implied in the suppressed partners", (pub["OBS_VALUE"].sum() - wxd) / 1e9,
        "US$ bn (nominal)", f"{(pub['OBS_VALUE'].sum() - wxd) / 1e9:.0f}", r"\uksuppressedloss (Table C1)", raw_src,
        "published partners − foreign total")
    # ---- corrections of step 1: employees ----
    us = {}
    for y in (Y - 1, Y):
        e = raw[(raw["REF_AREA"] == "USA") & (raw["TIME_PERIOD"] == y) & (raw["MEASURE"] == "EMPLOYEES")
                & (raw["PROFIT_GROUPING"] == "_T") & ~raw["COUNTERPART_AREA"].isin(NOT_JURISDICTIONS | {"USA", "WXD"})]
        us[y] = e.set_index("COUNTERPART_AREA")["OBS_VALUE"]
    final = c[(c["iso_parent"] == "USA") & (c["year"] == Y) & (c["grouping"] == "Total (All sub-groups)")
              & ~c["iso_partner"].isin(["USA", "WXD"])].set_index("iso_partner")["n_employees"]
    units = employee_unit_errors()
    changed = final.index[~np.isclose(final, us[Y].reindex(final.index), rtol=1e-9)]
    bea = [q for q in changed if ("USA", q, Y) not in units]
    add(f"US groups' foreign employees, {Y - 1}, as published", us[Y - 1].sum() / 1e6, "million", f"{us[Y - 1].sum() / 1e6:.1f}",
        "Table C1 (US employees)", raw_src)
    add(f"US groups' foreign employees, {Y}, as published", us[Y].sum() / 1e6, "million", f"{us[Y].sum() / 1e6:.1f}",
        r"\usempbefore (Table C1)", raw_src)
    add(f"US groups' foreign employees, {Y}, after the corrections", final.sum() / 1e6, "million", f"{final.sum() / 1e6:.1f}",
        r"\usempafter (Table C1)", clean_src)
    add(f"US-parent cells of {Y} whose employees step 1 sets to the trend of the BEA survey", len(bea), "cells", str(len(bea)),
        r"\usempcells (Table C1)", f"{raw_src}; {clean_src}",
        "cells whose headcount differs from the published one, without the cells with an error in the unit")
    add("cells whose employees step 1 resets as an error in the unit", len(units), "cells", str(len(units)),
        "Table C1 (22 cells with a jump in employees)", raw_src,
        "the test of step 1 applied to the published data: " + ", ".join(f"{p}→{q} {y}" for p, q, y in units))
    v23, v22 = raw_value("CZE", "CZE", Y, "EMPLOYEES"), raw_value("CZE", "CZE", Y - 1, "EMPLOYEES")
    add(f"Czech groups at home, {Y}: employees as published ÷ {Y - 1}", v23 / v22, "ratio", f"{v23 / v22:.1f} times",
        "Table C1 (Czechia)", raw_src)
    t = clean_value("CZE", "CZE", Y, "n_employees")
    add(f"Czech groups at home, {Y}: employees after the correction", t, "employees", f"about {round(t, -3):,.0f}",
        "Table C1 (Czechia)", clean_src)
    rou = {y: (raw_value("ROU", "ROU", y, "EMPLOYEES") + raw_value("ROU", "WXD", y, "EMPLOYEES")) / 1e6 for y in (2021, 2022)}
    add("Romanian groups, 2022: employees (home and foreign total) as published", rou[2022], "million", f"{rou[2022]:.0f}",
        "Table C1 (Romania)", raw_src, "submission dropped")
    add("Romanian groups, 2021: employees (home and foreign total) as published", rou[2021], "million", f"{rou[2021]:.1f}",
        "Table C1 (Romania)", raw_src)
    e = {y: raw_value("CYM", "SGP", y, "EMPLOYEES", "PANELAI") for y in YEARS}
    other = pd.Series({y: v for y, v in e.items() if y != Y}).dropna()
    add(f"Cayman groups in Singapore, {Y}: employees of the profit-making groups as published", e[Y] / 1e6, "million",
        f"{e[Y] / 1e6:.1f}", "Table C1 (employees far from the cell's other years)", raw_src)
    add("Cayman groups in Singapore: lowest and highest count of the other years", other.min(), "employees",
        f"{other.min():,.0f} to {other.max():,.0f}", "Table C1", raw_src, f"highest {other.max():,.0f}")
    # ---- corrections of step 1: profit and revenues ----
    mex = {m: raw_value("MEX", "VEN", 2020, m, "PANELAII") for m in ("PROFIT", "TOT_REV", "EMPLOYEES")}
    add("Mexican groups in Venezuela, 2020: loss of the loss-making groups as published", -mex["PROFIT"] / 1e9, "US$ bn",
        f"{-mex['PROFIT'] / 1e9:.0f}", "Table C1 (Mexico)", raw_src, "submission dropped")
    add("Mexican groups in Venezuela, 2020: revenues of the loss-making groups as published", mex["TOT_REV"] / 1e9,
        "US$ bn", f"{mex['TOT_REV'] / 1e9:.0f}", "Table C1 (Mexico)", raw_src)
    add("Mexican groups in Venezuela, 2020: employees of the loss-making groups as published", mex["EMPLOYEES"],
        "employees", f"{mex['EMPLOYEES']:.0f}", "Table C1 (Mexico)", raw_src)
    per_rev = {y: raw_value("PER", "WXD", y, "TOT_REV") / 1e9 for y in (2017, 2018)}
    add("Peruvian groups, 2018: foreign revenues as published", per_rev[2018], "US$ bn", f"{per_rev[2018]:.0f}",
        "Table C1 (Peru)", raw_src, "partner WXD; submission dropped")
    add("Peruvian groups, 2017: foreign revenues as published", per_rev[2017], "US$ bn", f"{per_rev[2017]:.0f}",
        "Table C1 (Peru)", raw_src, "partner WXD")
    per = raw[(raw["REF_AREA"] == "PER") & ~raw["COUNTERPART_AREA"].isin(NOT_JURISDICTIONS | {"PER", "WXD"})]
    only = set(per.loc[per["TIME_PERIOD"] == 2018, "COUNTERPART_AREA"]) - set(per.loc[per["TIME_PERIOD"] != 2018, "COUNTERPART_AREA"])
    add("Peruvian groups, 2018: partner jurisdictions that appear in no other year", len(only), "jurisdictions",
        "about 100", "Table C1 (Peru)", raw_src)
    t = -raw_value("ZAF", "NLD", Y, "PROFIT") / 1e9
    add(f"South African groups in the Netherlands, {Y}: loss as published", t, "US$ bn", f"{t:.0f}",
        "Table C1 (South Africa → Netherlands)", raw_src)
    loss = {y: -raw_value("MYS", "THA", y, "PROFIT", "PANELAII") / 1e9 for y in YEARS}
    add("Malaysian groups in Thailand, 2020: loss of the loss-making groups as published", loss[2020], "US$ bn",
        f"{loss[2020]:.0f}", "Table C1 (Malaysia → Thailand)", raw_src)
    t = raw_value("MYS", "THA", 2020, "TOT_REV", "PANELAII") / 1e9
    add("Malaysian groups in Thailand, 2020: revenues of the loss-making groups as published", t, "US$ bn", f"{t:.0f}",
        "Table C1 (Malaysia → Thailand)", raw_src)
    worst = pd.Series({y: v for y, v in loss.items() if y != 2020}).dropna()
    add("Malaysian groups in Thailand: largest loss of the loss-making groups in the other years", worst.max(), "US$ bn",
        "below 0.1", "Table C1 (Malaysia → Thailand)", raw_src, f"in {int(worst.idxmax())}")
    t = (raw_value("SAU", "SAU", Y, "PROFIT") - clean_value("SAU", "SAU", Y, "profit_loss_before_income_tax")) / 1e9
    add(f"Saudi groups at home, {Y}: profit no Saudi group's accounts explain, removed", t, "US$ bn", f"about {t:.0f}",
        "Table C1 (Saudi Arabia 2023)", f"{raw_src}; {clean_src}", "published − cleaned profit, all sub-groups")
    dom = c[(c["iso_parent"] == "DEU") & (c["iso_partner"] == "DEU") & (c["grouping"] == "Total (All sub-groups)")]
    dom = dom.set_index("year")["profit_loss_before_income_tax_corrected"] / 1e9
    early = dom.loc[2017:2021]
    for label, y, macro in (("2022", 2022, r"\deuhometwotwo"), ("lowest of 2017–2021", int(early.idxmin()), r"\deuhomelow"),
                            ("highest of 2017–2021", int(early.idxmax()), r"\deuhomehigh"), (str(Y), Y, r"\deuhometwothree")):
        add(f"German groups' profit at home, {label} ({y})", dom[y], "US$ bn (nominal)", f"{dom[y]:.0f}",
            f"{macro} (1_data.tex, footnote)", clean_src, "profit_loss_before_income_tax_corrected, all sub-groups")
    sensitivity_numbers(add, S)
    t = pd.DataFrame(rows, columns=["name", "value", "unit", "as_in_text", "where_in_note", "source", "note"])
    t["value"] = [round(float(v), 4) if isinstance(v, (float, np.floating)) else
                  int(v) if isinstance(v, (int, np.integer)) else v for v in t["value"]]
    t.to_csv(TAB / "methodology_note_numbers.csv", index=False)
    print(f"methodology note numbers: {len(t)} rows")


# %% MARK: 13.1 Sensitivities of the methodology note
# The note tests two choices of the main estimate with variant runs on their own datasets (config.DATASET_VARIANTS):
# the resource profit that the correction infers rather than documents, and the tax accrued in place of the tax paid.
# I compare each with the headline estimate of the same year. The scale factors depend on profit only, so they are the
# same in all runs and the percentage changes hold scaled and unscaled.
SENSITIVITY_RUNS = {v: ROOT / f"output/variants/{v}/estimates" for v in config.DATASET_VARIANTS}
# Countries whose result the note quotes with and without the inferred resource profit, by variant.
SENSITIVITY_COUNTRIES = {
    "res_no_tax_inference": (("ARE", r"\uaewithout"), ("IDN", r"\idnwithout"), ("TCD", "Chad (text)"),
                             ("NGA", "Nigeria (text)")),
    "res_no_inferred_companies": (("MYS", r"\myswithout"), ("BRA", "Brazil (numbers.tex comment)")),
}


def sensitivity_numbers(add, S):
    """Add the numbers of the note's two sensitivities to the methodology-note table."""
    s_main = S[S["year"] == Y].set_index("iso_partner")["revenue_gain_from_ut"] * DEFL_Y / 1e3
    labels = {"res_no_tax_inference": ("without the resource profit inferred from tax rates and taxes paid",
                                       r"\resnoetrpct"),
              "res_no_inferred_companies": ("without the inferred company-level resource profit",
                                            r"\resnocompanyinferredpct")}
    for v, (label, macro) in labels.items():
        sv = headline_summary(SENSITIVITY_RUNS[v])
        s = sv[sv["year"] == Y].set_index("iso_partner")["revenue_gain_from_ut"] * DEFL_Y / 1e3
        src = f"output/variants/{v}/estimates/{RUN_TABLES}/summary_country_year_long.csv"
        t = 100 * (1 - s.sum() / s_main.sum())
        add(f"world tax revenue lost (net), {Y}, {label}: per cent below the headline estimate", t, "%",
            f"{t:.1f}", f"{macro} (2_methodology.tex)", src,
            f"unscaled: {s.sum():.2f} against {s_main.sum():.2f} US$ bn at 2025 prices")
        for iso, where in SENSITIVITY_COUNTRIES[v]:
            add(f"{iso}: tax revenue lost (net), {Y}, {label}", s.get(iso, np.nan), "US$ bn (2025 prices)",
                f"{s.get(iso, np.nan):.1f}", f"{where} (2_methodology.tex)", src,
                f"unscaled; headline estimate {s_main.get(iso, np.nan):.2f}")
    # The company-level resource profit inferred from published information: the profit the correction removes in the
    # headline dataset and not in the dataset without the inferred company tables.
    strip = {}
    for v, path in (("headline", config.data_final + "cbcr_main_excl_resource.csv"),
                    ("res_no_inferred_companies",
                     str(config.data_final) + "cbcr_main_excl_resource__res_no_inferred_companies.csv")):
        r = hc.reported_estimate_sample(pd.read_csv(path, low_memory=False))
        strip[v] = pd.to_numeric(r.loc[r["year"] == Y, "resource_profit_base_usd"], errors="coerce").sum()
    t = (strip["headline"] - strip["res_no_inferred_companies"]) * DEFL_Y / 1e9
    add(f"profit removed through inferred company-level resource profit, {Y}, reported-only sample", t,
        "US$ bn (2025 prices)", f"{t:.0f}", r"\resinferredcompany (2_methodology.tex)",
        "data/final/cbcr_main_excl_resource.csv and …__res_no_inferred_companies.csv",
        "resource_profit_base_usd, headline − variant, the reported cells of the sample's parent-years")
    # The tax accrued in place of the tax paid.
    sa = headline_summary(SENSITIVITY_RUNS["accrued_tax"])
    src = f"output/variants/accrued_tax/estimates/{RUN_TABLES}/summary_country_year_long.csv"
    net = lambda d: (d["revenue_gain_from_ut"] * d["year"].map(DEFL)).groupby(d["year"]).sum()
    change = 100 * (net(sa) / net(S) - 1)
    add(f"world tax revenue lost (net), {Y}, with the tax accrued: per cent above the headline estimate",
        change[Y], "%", f"{change[Y]:.1f}", r"\accruedworldtwothree (1_data.tex)", src)
    other = change.drop(Y)
    add("the same in the other years: largest decrease", -other.min(), "%", f"{-other.min():.1f}",
        r"\accruedworldlow (1_data.tex)", src, f"in {int(other.idxmin())}")
    add("the same in the other years: largest increase", other.max(), "%", f"{other.max():.1f}",
        r"\accruedworldhigh (1_data.tex)", src, f"in {int(other.idxmax())}")
    t = bloc_table(sa).loc[WORLD, "net_change_pct_tax"]
    add(f"world tax revenue lost (net) as % of the tax multinationals pay, {Y}, with the tax accrued", t, "%",
        f"{t:.1f}", r"\accruedworldsharepct (1_data.tex)", src, "the tax multinationals pay is the accrued tax")
    # The two tax measures in the OECD data, all cells of the all-sub-groups panel.
    c = pd.read_csv(config.data_final + "cbcr_main.csv", low_memory=False,
                    usecols=["year", "grouping", "income_tax_paid_on_cash_basis", "income_tax_accrued_current_year"])
    c = c[c["grouping"] == "Total (All sub-groups)"].groupby("year")[
        ["income_tax_paid_on_cash_basis", "income_tax_accrued_current_year"]].sum()
    ratio = c["income_tax_accrued_current_year"] / c["income_tax_paid_on_cash_basis"]
    pooled = c["income_tax_accrued_current_year"].sum() / c["income_tax_paid_on_cash_basis"].sum()
    src = "data/final/cbcr_main.csv (all cells, all sub-groups)"
    add(f"tax accrued below the tax paid, pooled {YEARS[0]}–{Y}", 100 * (1 - pooled), "%", f"{100 * (1 - pooled):.1f}",
        r"\accruedpooledpct (1_data.tex)", src)
    add("tax accrued below the tax paid, single years: largest", 100 * (1 - ratio.min()), "%",
        f"{100 * (1 - ratio.min()):.0f}", r"\accruedlowpct (1_data.tex)", src, f"in {int(ratio.idxmin())}")
    add("tax accrued above the tax paid, single years: largest", 100 * (ratio.max() - 1), "%",
        f"{100 * (ratio.max() - 1):.0f}", r"\accruedhighpct (1_data.tex)", src, f"in {int(ratio.idxmax())}")


# %% MARK: 14. Main
def main():
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    S = headline_summary()
    M = pd.read_csv(MISALIGNMENT, low_memory=False, usecols=MISALIGNMENT_COLS)
    n = {}
    world_totals()
    n.update(sankey_figures(M, S))
    n.update(bloc_figure(S))
    n.update(shifted_profit_figures(M, S))
    n.update(race_to_the_bottom())
    n.update(irs_figures(M))
    n.update(incidence_figure())
    n.update(gate_world())
    n.update(classic_rule(M, S))
    footnote_own_statistics()
    origin_destination_figure()
    chapter_numbers(n)
    methodology_note_numbers(n, M, S)
    print(f"chapter figures in {FIG.relative_to(ROOT)}, tables in {TAB.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
