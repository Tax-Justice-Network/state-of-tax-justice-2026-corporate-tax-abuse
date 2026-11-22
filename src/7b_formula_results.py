# %%
"""
7b — Results by apportionment formula family.

This script compares the four apportionment formula families: sales + employees (the headline), CCCTB, three-factor
and double-weighted sales, all on the complete destination measure. It writes, for the reported sample and for the
sample with imputed rows (gravity):
  * the cross-section across all formulas for the latest year (2023), by income group and for the world, scaled to
    all multinationals, for taxable profit and tax revenue, and their twins with every year (formula × income group
    × year), scaled as well.
  * the country detail for 2023, unscaled, in the `…_countries` companions, whose group heading rows are labels only.
    A country whose estimate rests on few observations carries the mark [2] (_data_coverage).
It also writes the values of the tables of the methodology note's appendices E and F (the sample with imputed rows
and the other formulas): the net profit shifted out of each country and the net tax revenue it loses under each
formula, by continent with the world rows (Tables E1, E2, F2 and F3), and by income group, scaled (Table F1). Below
Japan and Canada, the main sample's tables give the estimates with these countries' own statistics on where their
multinationals sell. Finally, it draws the headline formula per year 2016–2023 (2020 marked) on the sample with
imputed rows, one line per income group, scaled with the world factor of each year: the net profit shifted out (fig02)
and the net tax revenue lost (fig03), the note's Figures E1 and E2.

The presentation rule is that of the whole package: no multi-year averages, countries for the latest year unscaled,
aggregates scaled. The headline specification is the reported-only sample, resources excluded, employees +
destination-based sales (sales_employees_destmnedds), domestic/foreign ETR, gains at the statutory CIT and losses at
the ETR, in constant 2025 US$.

Section outline (numbers match the cell headings below):
1. Settings.
2. Figures of the sample with imputed rows.
3. Formula tables.
4. The tables of the methodology note's appendices E and F.
5. Main.

Exhibit script — consumes the script-6 estimation summaries and the scale factors of 7a. It runs after 7a.

Reads:
  output/estimates/{reported_only,with_imputed_rows}/2_resources_excluded/tables/summary_country_year_long.csv
                                                                        — per-country estimates by formula (script 6)
  output/variants/mkt_own_{jpn,can}/estimates/reported_only/2_resources_excluded/tables/summary_country_year_long.csv
                                                                        — Japan and Canada with their own statistics
  output/paper/main_text/tables/host_scale_factors.csv                  — the scale factor per sample and year (7a)

Writes:
  output/paper/{main_text,appendix}/tables/table2_taxable_profits_by_formula__<sample>.csv — taxable profit by
                                                                          formula and income group (2023, scaled)
  output/paper/{main_text,appendix}/tables/table3_tax_revenue_by_formula__<sample>.csv     — tax revenue by formula
                                                                          and income group (2023, scaled)
  …/table2_taxable_profits_by_formula_yearly__<sample>.csv, table3_tax_revenue_by_formula_yearly__<sample>.csv
                                                                        — every year, scaled
  …/table2_taxable_profits_by_formula_countries__<sample>.csv, table3_tax_revenue_by_formula_countries__<sample>.csv
                                                                        — 2023 country detail, unscaled
  output/paper/main_text/tables/note_table_f1_by_income_group__reported_only.csv
  output/paper/main_text/tables/note_table_f2_profit_shifted_by_formula__reported_only.csv,
    note_table_f3_tax_lost_by_formula__reported_only.csv
  output/paper/appendix/tables/note_table_e1_profit_shifted_by_formula__gravity.csv,
    note_table_e2_tax_lost_by_formula__gravity.csv                      — the methodology note's Tables E1–F3
  output/paper/appendix/figures/fig02_taxable_profit_by_income.png/.pdf — net profit shifted out (note Figure E1)
  output/paper/appendix/figures/fig03_tax_revenue.png/.pdf              — net tax revenue lost (note Figure E2)

Usage:
  python src/7b_formula_results.py   — after 7a_coverage_scaleup.py

Author: Tax Justice Network.
Created: 2026-07-27.  Last updated: 2026-11-22.
"""

# %% MARK: 1. Settings
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np
import pandas as pd

import config
from _brand import apply_tjn_style
import _exhibit_helpers as _eh
import _host_coverage as _hc

apply_tjn_style()

ROOT = Path(__file__).resolve().parents[1]
Y = _eh.LATEST_YEAR
DEFL_Y = config.deflator_to_base()[Y]


def _flab(flab):
    return flab.lower() if flab != "CCCTB" else flab


# %% MARK: 2. Figures of the sample with imputed rows
def formula_figures(by_y):
    """Draw the headline formula per year, one line per income group (scaled), on the sample with imputed rows: the
    net profit shifted out (fig02, the note's Figure E1) and the net tax revenue lost (fig03, Figure E2). A positive
    amount is a loss, the change under unitary taxation with the same sign."""
    figures_dir = _eh.figdir("gravity")
    _eh.group_lines_twopanel(by_y, _eh.HEADLINE_FORMULA, "delta_taxable_profits_musd",
                             "delta_taxable_profits_pct_posbase", _eh.TP_ABS, _eh.TP_PCT,
                             "fig02_taxable_profit_by_income.png", figures_dir)
    _eh.group_lines_twopanel(by_y, _eh.HEADLINE_FORMULA, _eh.REV_CIT, _eh.REV_CIT_PCT, _eh.RV_ABS, _eh.RV_PCT,
                             "fig03_tax_revenue.png", figures_dir)


# %% MARK: 3. Formula tables
_TB_PCT = " (% of positive reported profits)"


def _cross_section_columns(kind):
    if kind == "taxbase":
        cols = [("net reported profits", _eh.HEADLINE_FORMULA, "previous_profits_musd")]
        for fk, flab in _eh.PAPER_4FORMULAS:
            cols += [(_flab(flab), fk, "delta_taxable_profits_musd"),
                     (_flab(flab) + _TB_PCT, fk, "delta_taxable_profits_pct_posbase")]
    else:
        cols = [("current tax revenue from MNEs", _eh.HEADLINE_FORMULA, "cash_tax_pos_musd")]
        for fk, flab in _eh.PAPER_4FORMULAS:
            cols += [(_flab(flab), fk, _eh.REV_CIT),
                     (_flab(flab) + " (%)", fk, _eh.REV_CIT_PCT)]
    return cols


def formula_group_tables(sample, tables_dir, by_latest, by_y):
    """Write the formula tables for taxable profit and tax revenue: the latest-year cross-section across all formulas,
    scaled, by income group with the world, and the twins with every year. The yearly taxable-profit table leaves out
    the world, whose change in taxable profit sums to zero."""
    for kind, name in [("taxbase", "table2_taxable_profits_by_formula"),
                       ("revenue", "table3_tax_revenue_by_formula")]:
        _eh.write_table(_eh.group_cross_section(by_latest, _cross_section_columns(kind)), sample, name, tables_dir)
        if kind == "taxbase":
            vcols = [("change in taxable profit (US$ m)", "delta_taxable_profits_musd"),
                     ("change as % of positive reported profits", "delta_taxable_profits_pct_posbase"),
                     ("net reported profits (US$ m)", "previous_profits_musd")]
        else:
            vcols = [("change in tax revenue (US$ m)", _eh.REV_CIT),
                     ("change as % of current tax revenue from MNEs", _eh.REV_CIT_PCT),
                     ("current tax revenue from MNEs (US$ m)", "cash_tax_pos_musd")]
        t = _eh.group_yearly_long(by_y, _eh.PAPER_4FORMULAS, vcols)
        if kind == "taxbase":
            t = t[t["income group"] != "WORLD"]
        _eh.write_table(t, sample, name + "_yearly", tables_dir)


def formula_country_tables(sample, tables_dir):
    """Write the country detail for the latest year, unscaled: the companions of the formula tables."""
    years = _eh.LATEST
    excl_rev = _eh.rev_musd(sample, "excl_resource", _eh.HEADLINE_FORMULA, years)
    order_iso = pd.Index(sorted(excl_rev.index, key=lambda i: _eh.cname(i).lower()))
    grp = _eh.income_group(sample).to_dict()
    tb = pd.DataFrame(index=order_iso)
    rev = pd.DataFrame(index=order_iso)
    # I show the net reported profits (losses included, so they can be negative) for transparency. The positive-only
    # base stays the denominator of the percentages, because loss cells owe no tax.
    tb["net reported profits"] = _eh.reported_musd(sample, "excl_resource", years)
    tb["taxable profits (positive profits only)"] = _eh.posbase_musd(sample, years)
    rev["current tax revenue from MNEs"] = _eh.current_rev_musd(sample, years)
    for fk, flab in _eh.PAPER_4FORMULAS:
        tb[_flab(flab)] = _eh.taxbase_musd(sample, "excl_resource", fk, years)
        rev[_flab(flab)] = _eh.rev_musd(sample, "excl_resource", fk, years)
    flabs = [_flab(flab) for _, flab in _eh.PAPER_4FORMULAS]
    _eh.emit_table(tb, order_iso, grp, sample, "table2_taxable_profits_by_formula_countries", tables_dir,
                   pct_base="taxable profits (positive profits only)", pct_cols=flabs, drop_base_col=True)
    _eh.emit_table(rev, order_iso, grp, sample, "table3_tax_revenue_by_formula_countries", tables_dir,
                   pct_base="current tax revenue from MNEs", pct_cols=flabs)


# %% MARK: 4. The tables of the methodology note's appendices E and F
# The note speaks of losses, as the report does: the net profit shifted out of a country and the net tax revenue it
# loses through profit shifting. A positive amount is a loss, a negative amount means that the country gains from
# profit shifting. The amounts are the change under unitary taxation with the same sign. Tables E1, E2, F2 and F3 list
# the countries by continent, like the annex tables of the report, each continent with the sum of its countries, and
# end with the world as the sum of countries and scaled up to all multinationals, each with the countries of positive
# and of negative amount shown separately. Table F1 gives the main sample by income group, scaled, with the chapter's
# formula also with sales measured where they are booked (sales by origin). All amounts are in US$ million at 2025
# prices and refer to the latest year. I scale with the world factor of the sample and year from 7a's factor table,
# the one the group tables above use.
NOTE_ORIGIN = "sales_employees"                         # the chapter's formula with sales by origin
NOTE_KINDS = {"profits": "today_profits_reported", "revenue": "today_tax_paid"}
NOTE_COUNTRY_FILES = {
    ("reported_only", "profits"): "note_table_f2_profit_shifted_by_formula",
    ("reported_only", "revenue"): "note_table_f3_tax_lost_by_formula",
    ("gravity", "profits"): "note_table_e1_profit_shifted_by_formula",
    ("gravity", "revenue"): "note_table_e2_tax_lost_by_formula",
}
NOTE_GROUP_FILE = "note_table_f1_by_income_group"
# The countries with an estimate from their own statistics on where their multinationals sell, with the variant run of
# each (main sample only).
NOTE_OWN_STATISTICS = {"JPN": "mkt_own_jpn", "CAN": "mkt_own_can"}
# The labels of the world rows: the countries with a positive and those with a negative amount.
NOTE_PARTS = {"profits": ("Countries with a net outflow", "Countries with a net inflow"),
              "revenue": ("Countries that lose", "Countries that gain")}


def note_rows(path, formulas):
    """Return the latest-year rows of the given formulas with the chapter's tax rates, with the net profit shifted out
    (profits) and the net tax revenue lost (revenue) in US$ million at the prices of the base year, unscaled."""
    s = pd.read_csv(path, low_memory=False, usecols=[
        "iso_partner", "partner_jurisdiction", "year", "formula_name", "etr_name", "rate_mode", "wb_income_group",
        "region_tjn", "revenue_gain_from_ut", "theoretical_profit", "reported_profit", "current_tax_paid_cash_musd"])
    s = s[(s["year"] == Y) & (s["etr_name"] == _eh.ETR) & (s["rate_mode"] == _eh.RATE)
          & s["formula_name"].isin(formulas)].copy()
    for column in ("revenue_gain_from_ut", "theoretical_profit", "reported_profit", "current_tax_paid_cash_musd"):
        s[column] = pd.to_numeric(s[column], errors="coerce") * DEFL_Y
    s["revenue"] = s["revenue_gain_from_ut"]
    s["profits"] = s["theoretical_profit"] - s["reported_profit"]
    return s


def note_estimates(sample):
    """Return the countries of a sample (name, continent, income group, the two marks, the profits reported and the tax
    paid today), one table of countries by formula for each measure (the four formulas and sales by origin) and the
    scale factor of the latest year."""
    names = _eh.FORMULAS + [NOTE_ORIGIN]
    s = note_rows(_eh._summary_path(sample, "excl_resource"), names)
    values = {kind: s.pivot(index="iso_partner", columns="formula_name", values=kind)[names] for kind in NOTE_KINDS}
    assert all(v.notna().all().all() for v in values.values()), "a country lacks a formula"
    h = s[s["formula_name"] == _eh.HEADLINE_FORMULA].set_index("iso_partner")
    info = pd.DataFrame({
        "country": [_eh.display_name(i, n) for i, n in zip(h.index, h["partner_jurisdiction"])],
        "continent": _eh.continent(h["region_tjn"]), "group": h["wb_income_group"],
        "few_observations": h.index.isin(_eh.thin_isos()),
        "no_corporate_income_tax": h.index.isin(config.NO_CIT_JURISDICTIONS),
        "profits": h["reported_profit"], "revenue": h["current_tax_paid_cash_musd"].fillna(0)})
    return info, values, float(_hc.load_factors(sample)[Y])


def own_statistics_values(kind):
    """Return, for Japan and Canada, the amount under each of the four formulas when the country's multinationals use
    the country's own statistics on where they sell (variant runs), in US$ million at the prices of the base year."""
    out = {}
    for iso, variant in NOTE_OWN_STATISTICS.items():
        path = (ROOT / "output/variants" / variant / "estimates/reported_only/2_resources_excluded/tables"
                / "summary_country_year_long.csv")
        s = note_rows(path, _eh.FORMULAS)
        out[iso] = s[s["iso_partner"] == iso].set_index("formula_name")[kind].reindex(_eh.FORMULAS)
    return out


def note_country_table(sample, kind):
    """Return the rows of a country table of the note in the order of the table: per continent its sum and its
    countries in alphabetical order (in the main sample, Japan and Canada are each followed by their estimate with
    their own statistics, which is not part of the sums), then the world as the sum of countries and scaled up, each
    followed by the countries with a positive and those with a negative amount."""
    info, values, factor = note_estimates(sample)
    v, today = values[kind][_eh.FORMULAS], info[kind]
    own = own_statistics_values(kind) if sample == "reported_only" else {}
    today_col = NOTE_KINDS[kind]

    def row(kind_of_row, label, numbers, last, iso="", cont="", few=False, no_cit=False):
        return {"row": kind_of_row, "label": label, "iso3": iso, "continent": cont, "few_observations": few,
                "no_corporate_income_tax": no_cit, **dict(zip(_eh.FORMULAS, np.asarray(numbers, dtype=float))),
                today_col: last}

    rows = []
    for cont in _eh.CONTINENTS:
        members = info[info["continent"] == cont]
        if members.empty:
            continue
        rows.append(row("continent", cont, v.loc[members.index].sum(), today.loc[members.index].sum(), cont=cont))
        for iso in sorted(members.index, key=lambda i: _eh.sort_key(members.at[i, "country"])):
            rows.append(row("country", members.at[iso, "country"], v.loc[iso], today.loc[iso], iso=iso, cont=cont,
                            few=bool(members.at[iso, "few_observations"]),
                            no_cit=bool(members.at[iso, "no_corporate_income_tax"])))
            if iso in own:
                rows.append(row("own_statistics", "based on more accurate data", own.pop(iso), np.nan, iso=iso,
                                cont=cont))
    assert not own, list(own)
    positive, negative = NOTE_PARTS[kind]
    for prefix, label, scale in (("world", "World (sum of countries)", 1.0),
                                 ("world_scaled", "World, scaled up to all multinationals", factor)):
        rows += [row(prefix, label, v.sum() * scale, today.sum() * scale),
                 row(f"{prefix}_positive", positive, v.clip(lower=0).sum() * scale, np.nan),
                 row(f"{prefix}_negative", negative, v.clip(upper=0).sum() * scale, np.nan)]
    return pd.DataFrame(rows), info, factor


def note_group_table(by_latest):
    """Return the net profit shifted out and the net tax revenue lost by income group in the latest year for the main
    sample, scaled to all multinationals: one column per formula, one for the chapter's formula with sales by origin
    and one for the level today. The row LOSERS adds up the countries with a positive amount. The four formulas equal
    the group tables of this script."""
    info, values, factor = note_estimates("reported_only")
    names = _eh.FORMULAS + [NOTE_ORIGIN]
    parts = []
    for kind in NOTE_KINDS:
        v = values[kind] * factor
        g = v.groupby(info["group"]).sum().reindex(_eh.IG_ORDER)
        g["today"] = (info[kind] * factor).groupby(info["group"]).sum()
        g.loc["WORLD"] = g.sum()
        if kind == "revenue":
            g.loc["LOSERS"] = v.clip(lower=0).sum()
        parts.append(g.rename_axis("income_group").reset_index().assign(measure=kind))
    t = pd.concat(parts, ignore_index=True)[["measure", "income_group", *names, "today"]]
    # The four formulas agree with the group tables, which scale every country-year before they sum.
    check = {"profits": "delta_taxable_profits_musd", "revenue": _eh.REV_CIT}
    for kind, col in check.items():
        for g in list(_eh.IG_ORDER) + ["WORLD"]:
            key = "world" if g == "WORLD" else g
            for f in _eh.FORMULAS:
                mine = t.loc[(t["measure"] == kind) & (t["income_group"] == g), f].iloc[0]
                theirs = by_latest.loc[(by_latest["wb_income_group"] == key) & (by_latest["formula_name"] == f),
                                       col].iloc[0]
                assert abs(mine - theirs) < 0.01, (kind, g, f, mine, theirs)
    return t, factor


def note_tables(by_latest):
    """Write the values of the methodology note's Tables E1, E2, F1, F2 and F3."""
    for (sample, kind), name in NOTE_COUNTRY_FILES.items():
        t, info, factor = note_country_table(sample, kind)
        path = Path(_eh.tabledir(sample)) / f"{name}__{sample}.csv"
        t.to_csv(path, index=False)
        w = t.set_index("row")
        print(f"  wrote {path}: {len(info)} countries, {int(info['few_observations'].sum())} marked for few "
              f"observations, world under the chapter's formula {w.at['world', _eh.HEADLINE_FORMULA]:,.1f} (scaled "
              f"{w.at['world_scaled', _eh.HEADLINE_FORMULA]:,.1f} with the factor {factor:.6g})")
    g, factor = note_group_table(by_latest)
    path = Path(_eh.tabledir("reported_only")) / f"{NOTE_GROUP_FILE}__reported_only.csv"
    g.to_csv(path, index=False)
    world = g[(g["measure"] == "revenue") & (g["income_group"] == "WORLD")].iloc[0]
    print(f"  wrote {path}: world net tax revenue lost {Y}, US$ bn scaled: "
          + ", ".join(f"{f} {world[f] / 1e3:.1f}" for f in _eh.FORMULAS + [NOTE_ORIGIN]))


# %% MARK: 5. Main
def main():
    latest = {}
    for sample in _eh.SAMPLES:
        print(f"== {sample} ==")
        by_y = _eh.yearly_groups(sample)
        latest[sample] = _eh.latest_groups(sample)
        if sample == "gravity":
            formula_figures(by_y)
        formula_group_tables(sample, _eh.tabledir(sample), latest[sample], by_y)
        formula_country_tables(sample, _eh.tabledir(sample))
        hl = latest[sample][latest[sample]["formula_name"] == _eh.HEADLINE_FORMULA]
        print(f"  [{sample}] {Y} headline revenue change by group, scaled ($bn): " + ", ".join(
            f"{str(g)[:5]}={v / 1e3:,.1f}" for g, v in zip(hl["wb_income_group"], hl[_eh.REV_CIT])))
    note_tables(latest["reported_only"])
    print("\nDone.")


if __name__ == "__main__":
    main()
