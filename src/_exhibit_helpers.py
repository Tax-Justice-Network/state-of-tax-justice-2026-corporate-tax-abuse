"""
Shared machinery for the exhibit script 7b.

This module provides the technical helpers of script 7b and produces no exhibit itself. Script 7b imports it to load
the estimation summaries, to render its tables and figures in the common exhibit style and to name and group the
countries of the methodology note's tables. Country-level exhibits show the latest year, unscaled. Aggregates show
every year, scaled to all multinationals with the scale factor of each year (_host_coverage). Formula cross-sections
show the latest year, scaled. The loaders select the year(s) with `years=` and return the average over them.

Section outline (numbers match the cell headings below):
1. Presentation conventions.
2. Estimation-summary loaders.
3. Country names and continents.
4. Table formatting.
5. Per-year figures.

Author: Tax Justice Network.
Last updated: 2026-11-22.
"""
import os
import sys
import unicodedata

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

import config
import _scenario_machinery as _sc
from _brand import GOLD, EARTH_GREEN, BLUE, RED, TEAL, INK, tint, shade  # noqa: E402
from _data_coverage import thin_iso_set, coverage_table  # noqa: E402


# %% MARK: 1. Presentation conventions
# Presentation rule: no multi-year averages.
#   * Country-level exhibits show the latest year only (LATEST = [last_year]), unscaled (the CbCR sample's own
#     values).
#   * Aggregate developments (world, income groups) are shown for every year in YEARS_ALL (2020 included and marked),
#     scaled to all multinationals with the scale factor of each year (_host_coverage, table written by 7a).
#   * Formula comparisons of aggregates show the latest-year cross-section, scaled.
# All money is in constant BASE_YEAR US$ (I deflate each year).
LATEST_YEAR = config.last_year
LATEST = [LATEST_YEAR]
YEARS_ALL = list(config.ANALYSIS_YEARS)

# The headline destination concept combines the destination sales of all MNEs with the MNE share of the BaTIS imports
# of digitally deliverable services.
HEADLINE_FORMULA = "sales_employees_destmnedds"
ETR = _sc.ETR
RATE = _sc.RATE
REV_CIT = _sc.REV                                       # gains at the statutory rate, losses at the effective rate
REV_CIT_PCT = _sc.REV_PCT

# I put all formulas on the complete destination measure (the headline), so that the family comparison is
# like-for-like.
PAPER_4FORMULAS = [
    ("sales_employees_destmnedds", "Sales & employees"),
    ("ccctb_destmnedds", "CCCTB"),
    ("three_factors_destmnedds", "Three-factor"),
    ("double_weighted_sales_destmnedds", "Double-weighted sales"),
]
FORMULAS = [k for k, _ in PAPER_4FORMULAS]

# Written-out, capitalised income-group labels of the figure legends.
IG_LABELS_PAPER = {
    "low_income": "Low\nincome", "lower_middle_income": "Lower middle\nincome",
    "upper_middle_income": "Upper middle\nincome", "high_income": "High\nincome",
    "tax_haven": "Tax\nhavens",
    "world": "World",
}

# Panel titles. They are the only text baked into the figure image, and they are those of the methodology note's
# Figures E1 and E2, which speak of losses: a positive amount is profit shifted out of the group or tax revenue it
# loses. The overall title and the explanatory note live in the caption of the document.
TP_ABS = "Net profit shifted out (USD bn)"
TP_PCT = "% of current profit base"
RV_ABS = "Net tax revenue lost (USD bn)"
RV_PCT = "% of current corporate tax paid"

SAMPLES = ["reported_only", "gravity"]


def figdir(sample):
    """Return the figure folder of a sample: topic paper/main_text for the reported sample and paper/appendix for the
    sample with imputed rows (gravity)."""
    topic = "paper/main_text" if sample == "reported_only" else "paper/appendix"
    return config.output_dirs(topic)[1]


def tabledir(sample):
    topic = "paper/main_text" if sample == "reported_only" else "paper/appendix"
    return str(config.output_dirs(topic)[0])


def yearly_groups(sample):
    """Return the per-year group aggregates (YEARS_ALL), scaled, in constant BASE_YEAR USD."""
    return _sc.yearly_by_group(sample, FORMULAS)


def latest_groups(sample):
    """Return the latest-year group cross-section, scaled, in constant BASE_YEAR USD."""
    return _sc.latest_by_group(sample, FORMULAS)


# %% MARK: 2. Estimation-summary loaders
_NAME_OVR = config.COUNTRY_NAME_OVERRIDES
try:
    import pycountry

    def cname(iso):
        if str(iso) in _NAME_OVR:
            return _NAME_OVR[str(iso)]
        c = pycountry.countries.get(alpha_3=str(iso))
        return c.name if c else str(iso)
except Exception:
    def cname(iso):
        return _NAME_OVR.get(str(iso), str(iso))

# Mark for estimates that rest on few observations (footnote [2]): fewer than three headquarter countries report
# activity in the country in the latest year. The threshold lives in _data_coverage.
_THIN_ISO = None


def thin_isos():
    global _THIN_ISO
    if _THIN_ISO is None:
        _THIN_ISO = thin_iso_set(coverage_table(write=False))
        print(f"[coverage] thin-data flag [2] on {len(_THIN_ISO)} countries")
    return _THIN_ISO


def cname_flagged(iso):
    """Return the display name with the mark for few observations appended."""
    return cname(iso) + (" [2]" if str(iso) in thin_isos() else "")


def _summary_path(sample, scenario):
    return os.path.join(str(config.estimates_dir(sample, scenario)), "tables", "summary_country_year_long.csv")


_SUMMARY_CACHE = {}


def _read_summary(sample, scenario):
    """Read the long summary of one sample and scenario, restricted to the headline ETR family and rate mode, once,
    and cache it (the loaders below are called many times)."""
    p = _summary_path(sample, scenario)
    if p not in _SUMMARY_CACHE:
        d = pd.read_csv(p, low_memory=False, usecols=lambda c: c in {
            "formula_name", "etr_name", "rate_mode", "iso_partner", "year", "revenue_gain_from_ut",
            "theoretical_profit", "reported_profit", "current_tax_paid_cash_musd"})
        _SUMMARY_CACHE[p] = d[(d["etr_name"] == ETR) & (d["rate_mode"] == RATE)]
    return _SUMMARY_CACHE[p]


def _filtered(sample, scenario, formula, years):
    """Return the rows of one (sample, scenario, formula) on the headline ETR and rate mode for `years`."""
    d = _read_summary(sample, scenario)
    return d[(d["formula_name"] == formula) & d["year"].isin(list(years))]


_DEFL = config.deflator_to_base()   # year → factor to constant BASE_YEAR USD


def _per_year(d, values, years):
    """Return the deflated values summed per country and divided by the number of years. With years=LATEST (one
    year), this is the value of that year."""
    d = d.assign(_v=values * d["year"].map(_DEFL))
    return d.groupby("iso_partner")["_v"].sum() / len(list(years))


def rev_musd(sample, scenario, formula, years):
    """Return the change in tax revenue in constant BASE_YEAR US$ million per country."""
    d = _filtered(sample, scenario, formula, years)
    return _per_year(d, d["revenue_gain_from_ut"], years)


def taxbase_musd(sample, scenario, formula, years):
    """Return the change in taxable profit (theoretical minus reported), in the same units and convention."""
    d = _filtered(sample, scenario, formula, years)
    return _per_year(d, d["theoretical_profit"] - d["reported_profit"], years)


def reported_musd(sample, scenario, years, formula=HEADLINE_FORMULA):
    """Return the currently reported profit (net of losses)."""
    d = _filtered(sample, scenario, formula, years)
    return _per_year(d, d["reported_profit"], years)


def current_rev_musd(sample, years, formula=HEADLINE_FORMULA):
    """Return the corporate tax the sample's multinationals pay today, the denominator of the revenue percentages.
    Every revenue comparison is against the taxes on multinationals' profit, never against total tax revenue."""
    d = _filtered(sample, "excl_resource", formula, years)
    return _per_year(d, pd.to_numeric(d["current_tax_paid_cash_musd"], errors="coerce"), years)


def posbase_musd(sample, years, formula=HEADLINE_FORMULA):
    """Return the positive reported profit base (clipped at zero in each year), the denominator of the
    taxable-profit percentages."""
    d = _filtered(sample, "excl_resource", formula, years)
    return _per_year(d, pd.to_numeric(d["reported_profit"], errors="coerce").clip(lower=0), years)


def income_group(sample):
    """Return the income group (with the tax havens as a group of their own) of every country of a sample's
    summary."""
    d = pd.read_csv(_summary_path(sample, "excl_resource"), usecols=["iso_partner", "wb_income_group"],
                    low_memory=False)
    return d.drop_duplicates("iso_partner").set_index("iso_partner")["wb_income_group"]


# %% MARK: 3. Country names and continents
# The methodology note's country tables name and group the countries like the annex tables of the report (script 10):
# short display names, and the continents below, in this order.
EXTRA_NAMES = {"FLK": "Falkland Islands", "SHN": "Saint Helena", "VAT": "Holy See", "MAF": "Saint Martin",
               "SXM": "Sint Maarten", "COG": "Republic of the Congo", "BOL": "Bolivia", "CZE": "Czechia"}
CONTINENTS = ["Africa", "Asia", "Europe", "Latin America and the Caribbean", "North America", "Oceania"]
CONTINENT = {"Africa": "Africa", "Asia": "Asia", "Europe": "Europe", "Latin America": "Latin America and the Caribbean",
             "Caribbean/American isl.": "Latin America and the Caribbean", "Northern America": "North America",
             "Oceania": "Oceania"}
CONTINENT_ISO = {"BMU": "North America", "BDI": "Africa", "COM": "Africa", "ERI": "Africa", "GMB": "Africa",
                 "GNB": "Africa", "SHN": "Africa", "FLK": "Latin America and the Caribbean", "KIR": "Oceania",
                 "PLW": "Oceania", "TON": "Oceania", "WLF": "Oceania", "VAT": "Europe"}


def display_name(iso, fallback=None):
    """Return a short display name: the repository overrides, then a few extras, then pycountry."""
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


def continent(region_tjn):
    """Return the continent of each country of a Series of region_tjn indexed by ISO3 code."""
    out = region_tjn.map(CONTINENT)
    out.update(pd.Series(CONTINENT_ISO).reindex(out.index).dropna())
    assert out.notna().all(), sorted(out.index[out.isna()])
    return out


def sort_key(text):
    """Return a name without accents and in lower case, which gives the alphabetical order of the annex tables."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


# %% MARK: 4. Table formatting
IG_ORDER = _sc.INCOME_GROUP_ORDER
IG_HEADING = {
    "low_income": "LOW-INCOME",
    "lower_middle_income": "LOWER-MIDDLE-INCOME",
    "upper_middle_income": "UPPER-MIDDLE-INCOME",
    "high_income": "HIGH-INCOME",
    "tax_haven": "TAX HAVENS",
}
IG_NAME = {"low_income": "Low income", "lower_middle_income": "Lower middle income",
           "upper_middle_income": "Upper middle income", "high_income": "High income",
           "tax_haven": "Tax havens"}


def with_pct(df_final, base_col, value_cols):
    """Append '<col> (%)' columns equal to 100 × col ÷ base_col. Where the base is ≤ 0, I mark the cell with
    footnote [1]. Extreme percentages (above 1,000%) get footnote [3]. The function runs after finalise, so that the
    group heading rows get the ratio of the group sums."""
    base = pd.to_numeric(df_final[base_col], errors="coerce")
    df_final["_has_negative_basis"] = (base <= 0)
    # The heading names the denominator where it is the positive-only profit base, because "%" alone would suggest
    # net reported profits.
    pct_suffix = (" (% of positive reported profits)" if "positive" in str(base_col) else " (%)")
    for c in value_cols:
        pct = 100 * pd.to_numeric(df_final[c], errors="coerce") / base
        pct_r = np.round(pct, 1)
        pct_col = np.where(
            base > 0,
            np.where(np.abs(pct_r) > 1000,
                     pd.Series(pct_r).map(lambda v: f"{v:,.0f} [3]").to_numpy(),
                     pct_r.astype(object)),
            # A NaN base means that the denominator is not available, so I leave the cell blank instead of marking
            # "losses reported".
            np.where(base.isna(), "", "[1]"))
        df_final[c + pct_suffix] = pct_col
    return df_final.round(1)


def finalise(df, order_iso, grp):
    """Group the countries by income group (with the tax havens as a group of their own). Each group is led by an
    uppercase heading row, which is a label only, because the group aggregates are reported, scaled to all
    multinationals, in the separate group tables (presentation rule: no unscaled aggregates). Its countries follow in
    alphabetical order."""
    df = df.reindex(order_iso)
    rows = []
    for g in list(IG_ORDER) + ["__other__"]:
        if g == "__other__":
            isos = sorted([i for i in df.index if grp.get(i) not in IG_ORDER], key=lambda i: cname(i).lower())
            heading = "OTHER / UNCLASSIFIED"
        else:
            isos = sorted([i for i in df.index if grp.get(i) == g], key=lambda i: cname(i).lower())
            heading = IG_HEADING.get(g, g.upper())
        if not isos:
            continue
        rows.append({"country": heading, **{col: np.nan for col in df.columns}})
        for i in isos:
            rec = {"country": cname_flagged(i)}
            rec.update(df.loc[i].to_dict())
            rows.append(rec)
    out = pd.DataFrame(rows, columns=["country"] + list(df.columns))
    return out.round(1)


def _cap_first(s):
    """Capitalise the first alphabetic character of a header and leave the rest unchanged."""
    s = str(s)
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[:i] + ch.upper() + s[i + 1:]
    return s


def write_table(df, sample, name, tables_dir):
    """Write the table as CSV, with capitalised headers."""
    df = df.drop(columns=["_has_negative_basis"], errors="ignore")
    df = df.rename(columns={c: _cap_first(c) for c in df.columns})
    csv = os.path.join(tables_dir, f"{name}__{sample}.csv")
    df.to_csv(csv, index=False)
    print(f"  wrote {csv}  ({len(df)} countries)")


def _pair_pct_columns(out, value_cols):
    """Reorder the columns so that each value column sits immediately next to its own '… (%)' column (USD, %, USD,
    %, …) instead of all USD columns followed by all % columns. The leading columns (country and reference bases)
    keep their position."""
    cols = list(out.columns)
    pct_map = {}
    for c in value_cols:
        for suf in (" (% of positive reported profits)", " (%)"):
            if c + suf in cols:
                pct_map[c] = c + suf
                break
    pct_display = set(pct_map.values())
    lead = [c for c in cols if c not in set(value_cols) and c not in pct_display]
    ordered = list(lead)
    for c in value_cols:
        if c in cols:
            ordered.append(c)
        if c in pct_map:
            ordered.append(pct_map[c])
    ordered += [c for c in cols if c not in ordered]
    return out[ordered]


def emit_table(df, order_iso, grp, sample, name, tables_dir, pct_base, pct_cols, drop_base_col=False):
    """Write a country table grouped by income group. Each value column is followed by its percentage of pct_base.
    drop_base_col=True removes the pct_base column after the percentages are computed (the positive-only profit base
    is their denominator but is not shown)."""
    out = with_pct(finalise(df, order_iso, grp), pct_base, pct_cols)
    if drop_base_col:
        out = out.drop(columns=[pct_base])
    write_table(_pair_pct_columns(out, pct_cols), sample, name, tables_dir)


def group_label(g):
    """Return the display label of a group key. The world row is 'WORLD'."""
    return "WORLD" if g == _sc.WORLD_KEY else IG_NAME.get(g, str(g))


def group_cross_section(by_g, columns):
    """Build one row per income group and the world. `columns` = [(header, formula_key, value_col)]. The headers
    become the table columns."""
    rows = []
    for g in list(IG_ORDER) + [_sc.WORLD_KEY]:
        gs = by_g[by_g["wb_income_group"] == g]
        if gs.empty:
            continue
        rec = {"income group": group_label(g)}
        for hdr, fk, col in columns:
            r = gs[gs["formula_name"] == fk]
            rec[hdr] = float(r[col].iloc[0]) if (not r.empty and col in r.columns) else np.nan
        rows.append(rec)
    return pd.DataFrame(rows).round(1)


def group_yearly_long(by_y, measures, value_cols):
    """Build a long table with one row per (formula, group, year). measures = [(formula_key, label)], value_cols =
    [(header, column)]."""
    rows = []
    for fk, flab in measures:
        for g in list(IG_ORDER) + [_sc.WORLD_KEY]:
            gs = by_y[(by_y["formula_name"] == fk) & (by_y["wb_income_group"] == g)].sort_values("year")
            for _, r in gs.iterrows():
                rec = {"formula": flab, "income group": group_label(g), "year": int(r["year"])}
                for hdr, col in value_cols:
                    rec[hdr] = r.get(col, np.nan)
                rows.append(rec)
    return pd.DataFrame(rows).round(1)


# %% MARK: 5. Per-year figures
# Each group has a fixed colour and marker, never cycled (the marker carries the identity without colour). GOLD is
# too light for a 2px line on white, so I use its darker shade for line strokes.
GROUP_STYLE = {
    "low_income": (EARTH_GREEN, "o"), "lower_middle_income": (BLUE, "s"),
    "upper_middle_income": (shade(GOLD, 0.3), "^"), "high_income": (RED, "D"),
    "tax_haven": (TEAL, "v"), "world": (INK, "*"),
}
EXCL_BAND = tint(GOLD, 0.2)
EXCL_LABEL = (f"{', '.join(str(y) for y in sorted(config.EXCLUDE_YEARS))}: COVID year "
              "(low CbCR coverage)")
_PCT_FMT = FuncFormatter(lambda v, _: f"{v:,.0f}%")
_USD_FMT = FuncFormatter(lambda v, _: f"{v:,.0f}" if abs(v) >= 10 or v == 0 else f"{v:,.1f}")


def _legend_layout(fig, labels, fontsize=9):
    """Return (ncol, n_rows) so that a bottom legend fits the figure width: as many columns as the longest label
    allows (about 13 characters per inch at 9 pt)."""
    width_chars = fig.get_figwidth() * 13.0 * 9.0 / fontsize
    longest = max(len(str(lab)) for lab in labels) + 6
    ncol = max(1, min(len(labels), int(width_chars // longest)))
    return ncol, int(np.ceil(len(labels) / ncol))


def mark_excluded_years(ax):
    """Draw a light gold band behind each EXCLUDE_YEARS year (2020 stays in every series but is marked)."""
    for y in sorted(config.EXCLUDE_YEARS):
        if YEARS_ALL[0] <= y <= YEARS_ALL[-1]:
            ax.axvspan(y - 0.5, y + 0.5, color=EXCL_BAND, lw=0, zorder=0)


def year_axis(ax, fontsize=9):
    ax.set_xticks(YEARS_ALL)
    ax.set_xticklabels([str(y) for y in YEARS_ALL], fontsize=fontsize)
    ax.set_xlim(YEARS_ALL[0] - 0.6, YEARS_ALL[-1] + 0.6)


def group_lines_twopanel(by_y, formula, abs_col, pct_col, abs_title, pct_title, fname, figures_dir):
    """Draw two panels (absolute USD bn and %), years on the x-axis, one line per income group, for the headline
    formula over time."""
    sub = by_y[by_y["formula_name"] == formula]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.6))
    handles, hlabels = [], []
    for k, (ax, col, title, div, is_pct) in enumerate([
            (axes[0], abs_col, abs_title, 1e3, False),
            (axes[1], pct_col, pct_title, 1.0, True)]):
        mark_excluded_years(ax)
        for g in IG_ORDER:
            s = sub[sub["wb_income_group"] == g].set_index("year")[col].reindex(YEARS_ALL) / div
            if s.notna().sum() == 0:
                continue
            c, m = GROUP_STYLE.get(g, (INK, "o"))
            ln, = ax.plot(YEARS_ALL, s.values, color=c, marker=m, lw=2, ms=6,
                          markeredgecolor="white", markeredgewidth=0.6, zorder=3)
            if k == 0:
                handles.append(ln)
                hlabels.append(str(IG_LABELS_PAPER.get(g, g)).replace("\n", " "))
        ax.axhline(0, color="grey", lw=0.6, zorder=1)
        year_axis(ax)
        ax.yaxis.set_major_formatter(_PCT_FMT if is_pct else _USD_FMT)
        ax.set_title(title, fontsize=13)
    handles.append(Patch(facecolor=EXCL_BAND, edgecolor="none"))
    hlabels.append(EXCL_LABEL)
    ncol, nrow = _legend_layout(fig, hlabels)
    fig.legend(handles, hlabels, loc="lower center", ncol=ncol, fontsize=9, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.tight_layout(rect=[0, 0.04 + 0.04 * nrow, 1, 1])
    fig.savefig(figures_dir / fname, dpi=130)
    plt.close(fig)
    print(f"  wrote {figures_dir / fname}")
