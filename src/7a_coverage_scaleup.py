# %%
"""
7a — Coverage and scale-up to all multinationals.

This script computes the yearly net tax-revenue gain summed over all
jurisdictions and scales it from the sample of multinationals in the
country-by-country reports (CbCR) up to all multinationals worldwide. The
world scale factor SF_t is the ratio of global multinational profit to the
profit that the sample covers. I take global multinational profit from the
OECD's estimates wherever they are published: the global-profit matrix of the
OECD's 2020 economic impact assessment (EIA) for 2016 and OECD Working Paper 68
(Hugger et al., 2024, Figure B.1) for 2017–2019. I extend it to 2020–2023 with
the profit growth of the headquarters countries that report in every year
since 2019 (all the profit they report, including the rest-of-world
remainder), so that countries joining or leaving the data do not move the
global total. SF_t is a ratio within one year, so inflation does not affect
it. Only the dollar series are deflated.

Every country takes the factor SF_t of its year, so the scaled totals equal
SF_t times the sample totals and gains and losses stay in proportion. This
script writes the factors of both samples (`_host_coverage`), and every later
exhibit scales its aggregates with them. It also writes the world estimate per
year with its bounds, from the conservative to the optimistic estimate, which
the methodology note quotes.

The headline specification uses the reported-only sample, excludes resources,
measures economic activity by employees and destination-based sales
(sales_employees_destmnedds) and uses the domestic/foreign effective tax rates
(ETRs). It prices the profit a country gains at its statutory corporate income
tax (CIT) rate and the profit it loses at its ETR. All series are per year for
2016–2023 (2020 included) in constant 2025 US$.

Section outline (numbers match the cell headings below):
1. Setup.
2. Config and constants.
3. Sample loaders.
4. Coverage scale-up tables and scale factors.
5. Bounds of the world estimate.
6. Run.

Exhibit script — consumes the script-6 estimation summaries. It produces the
coverage and scale-up tables, the scale factors that every other exhibit uses
and the bounds of the world estimate. It runs first among the exhibits.

Reads:
  {data_final}/cbcr_main_disaggregated.csv                              — profit and revenue of the sample
  output/estimates/{reported_only,with_imputed_rows}/2_resources_excluded/tables/summary_country_year_long.csv
                                                                        — the headline estimate per country and year
  output/estimates/reported_only/2_resources_excluded/tables/excl_resource/country_estimates__*.csv,
    misalignment__*.csv                                                 — the rate variants of the bounds

Writes:
  output/paper/main_text/tables/scaleup_yearly.csv                      — coverage and world scale factors per year, reported sample
                                                                          (scaled_up_* = totals scaled with SF_t)
  output/paper/main_text/tables/scaleup_yearly__gravity.csv             — the same for the gravity (imputed) sample
  output/paper/main_text/tables/host_scale_factors.csv                  — the scale factor per sample and year (sample, year, f)
  output/paper/main_text/tables/fig01_global_revenue_gains_data.csv     — the world estimate per year with its bounds
                                                                          (conservative, headline, optimistic), unscaled and scaled

Usage:
  python src/7a_coverage_scaleup.py

Author: Tax Justice Network.
Created: 2026-07-27.  Last updated: 2026-11-23.
"""

# %% MARK: 1. Setup
import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

_SRC = os.path.dirname(os.path.abspath(__file__))
_ROOT = Path(os.path.dirname(_SRC))
sys.path.insert(0, _SRC)
import config  # noqa: E402
from config import ANALYSIS_YEARS as _ANALYSIS_YEARS  # noqa: E402
import _host_coverage as _hc  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# %% MARK: 2. Config and constants
# Every series is per year over the full analysis window, with 2020 included. I
# show no averages.
YEARS_WITH_2020 = list(_ANALYSIS_YEARS)
DEFL = config.deflator_to_base()
HEADLINE, ETR, RATE, THRESH = (
    "sales_employees_destmnedds",
    "domfor",
    "loss_cit_gain_etr",
    "inf",
)

# ---- Global benchmark: profits of large multinational groups (consolidated revenue of EUR 750m or more) ----
# I take the levels the OECD observes wherever it publishes them and extend the
# series only after the last observed year.
#   2016       Global profit matrix of the OECD's 2020 economic impact
#              assessment: US$6,180bn.
#   2017-2019  OECD Working Paper 68 (Hugger et al. 2024), Figure B.1: total
#              profit of large multinational enterprises (MNEs), adjusted for
#              losses and read off the chart. The values are consistent with
#              the growth rates and the 2017-2020 average of 5,929 printed in
#              the working paper: 5,900 / 6,230 / 6,134 bn (2020: 5,451 bn).
#   2020-2023  The 2019 level grown with the profit of the 44 headquarters
#              countries that report in every year from 2019 to 2023. This is
#              all the profit they report: domestic, listed foreign and the
#              rest-of-world remainder (5.2tn in 2019, 4.7tn in 2020, 8.5tn in
#              2021). I start from 2019 rather than from the OECD's 2020 level,
#              so that the factors of 2020 to 2023 all grow from the same base
#              year before the pandemic year. Mexico is not among the 44, because
#              I drop its 2020 submission (1_clean, config.DROP_PARENT_YEARS).
#              The profit of the 44 makes up 98–99% of all reported profit, so
#              the growth reflects profit, not coverage. The countries that join
#              after 2020 (1–2% of reported profit) or leave do not move the
#              global total, and neither does the share of a country's data
#              that the reported sample can use.
# Both anchor sources cover the groups above the CbCR threshold, which hold more
# than 90% of all MNE profit according to an OECD analysis of Orbis data. As a
# benchmark for all MNEs, the series is therefore conservative by at most about
# 10%. Global MNE profit is the only comparator I use for coverage and the
# scale-up. I use no reference for total corporate profit.
OECD_MNE_TN = {2016: 6.18, 2017: 5.90, 2018: 6.23, 2019: 6.134}


# %% MARK: 3. Sample loaders
def _load_frame():
    p = os.path.join(_ROOT, "data", "final", "cbcr_main_disaggregated.csv")
    return pd.read_csv(
        p,
        low_memory=False,
        usecols=[
            "year",
            "is_distributed",
            "iso_parent",
            "iso_partner",
            "profit_loss_before_income_tax_corrected",
            "unrelated_party_revenues",
        ],
    )


def _reported_estimate_sample(df):
    """Return the REPORTED_ONLY sample of script 5 (_host_coverage.reported_estimate_sample)."""
    return _hc.reported_estimate_sample(df)


def reported_sample_profit_tn():
    """Return (sample_tn, foreign_share) per year for the analysis sample. The
    sample is exactly the reported-only estimation sample, with partial and bad
    reporters filtered out, and the profit is corrected profit. I return the
    foreign share (iso_parent != iso_partner) for reference only. Nothing
    downstream uses it."""
    r = _reported_estimate_sample(_load_frame())
    r["v"] = pd.to_numeric(
        r["profit_loss_before_income_tax_corrected"], errors="coerce"
    )
    tot = r.groupby("year")["v"].sum()
    frn = r[r["iso_parent"] != r["iso_partner"]].groupby("year")["v"].sum()
    return (
        {int(y): float(x) / 1e12 for y, x in tot.items()},
        {int(y): float(frn[y] / tot[y]) for y in tot.index},
    )


def disaggregated_sample_profit_tn():
    """Return the profit per year ($tn) of the disaggregated (gravity) sample:
    all rows of real countries, reported and imputed (is_distributed 0 and 1).
    Parents that report badly are covered here, because their aggregate rows are
    imputed into individual countries. Unlike in the reported-only sample, I
    therefore drop no partial or bad reporters."""
    d = _load_frame()
    v = pd.to_numeric(d["profit_loss_before_income_tax_corrected"], errors="coerce")
    g = v.groupby(d["year"]).sum()
    return {int(y): float(x) / 1e12 for y, x in g.items()}


# %% MARK: 4. Coverage scale-up tables and scale factors
def continuous_reporter_profit_tn(anchor, years=YEARS_WITH_2020):
    """Return the profit per year ($tn) of the headquarters countries that report in every year from `anchor` to
    the last year. I sum all their rows of the disaggregated sample: the domestic cell, the listed foreign cells
    and the rest-of-world remainder. This is the whole profit they report, however much of it can be used country
    by country. Returns ({year: profit}, sorted list of the continuous reporters)."""
    d = _load_frame()
    d = d[d["year"] >= anchor]
    v = pd.to_numeric(d["profit_loss_before_income_tax_corrected"], errors="coerce")
    tot = v.groupby([d["iso_parent"], d["year"]]).sum().unstack("year")
    tot = tot.reindex(columns=[y for y in years if y >= anchor])
    cont = tot.dropna()                      # a parent without rows in a year has no value there
    return {int(y): float(cont[y].sum()) / 1e12 for y in cont.columns}, sorted(cont.index)


def global_mne_profit_tn(years=YEARS_WITH_2020):
    """Return global MNE profit per year ($tn, nominal). For 2016-2019 I use the
    levels the OECD observes (the economic impact assessment for 2016, Figure B.1
    of Working Paper 68 for 2017-2019). Later years grow the 2019 level
    with the profit of the headquarters countries that report in every year since
    then (continuous_reporter_profit_tn). Countries that join or leave the data
    therefore do not move the global total. Neither does the share of a country's
    data that the reported sample can use, which was unusually high in 2020
    (95.5% of all reported profit, against 84–89% in the other years except
    2023). The function also returns the profit of the reported sample ($tn)."""
    sample_tn, _ = reported_sample_profit_tn()
    anchor = max(OECD_MNE_TN)
    cont_tn, _ = continuous_reporter_profit_tn(anchor, years)
    glob = {y: (OECD_MNE_TN[y] if y in OECD_MNE_TN else OECD_MNE_TN[anchor] * cont_tn[y] / cont_tn[anchor])
            for y in years}
    return glob, sample_tn


def _headline_country_year(sample, rate=RATE):
    """Return the revenue gain of the headline specification per (country, year), in nominal US$ million."""
    p = os.path.join(str(config.estimates_dir(sample, "excl_resource")), "tables",
                     "summary_country_year_long.csv")
    d = pd.read_csv(p, low_memory=False,
                    usecols=["formula_name", "etr_name", "rate_mode", "etr_threshold",
                             "iso_partner", "year", "revenue_gain_from_ut"])
    d = d[(d.formula_name == HEADLINE) & (d.etr_name == ETR) & (d.rate_mode == rate)]
    if d["etr_threshold"].astype(str).nunique() > 1:
        d = d[d["etr_threshold"].astype(str) == THRESH]
    return d


def scale_table(sample, glob_tn, sample_tn, years=YEARS_WITH_2020, rate=RATE):
    """Return the coverage table per year for one sample. The scaled_up_* columns
    are the totals scaled with the factor table, so it must exist. They equal the
    sample totals times SF_t, as does scaled_up_net_uniform_bn (net × SF_t), the
    column the later scripts read."""
    d = _headline_country_year(sample, rate)
    d = d[d["year"].isin(years)].copy()
    d["f"] = _hc.factor_for(d, sample)
    rows = []
    for y in years:
        s = d[d["year"] == y]
        f = DEFL[y]
        g = s["revenue_gain_from_ut"]
        winners = g.clip(lower=0).sum() * f / 1e3          # $bn, constant BASE_YEAR
        net = g.sum() * f / 1e3
        # Scale and coverage are nominal ratios within the same year, so the
        # deflator cancels. The profit columns are in constant BASE_YEAR USD like
        # every other monetary value in the outputs, hence the multiplication by
        # f below.
        scale = glob_tn[y] / sample_tn[y]
        rows.append(dict(
            year=y,
            revenue_gain_winners_bn=winners,
            revenue_gain_net_bn=net,
            global_mne_profit_tn=round(glob_tn[y] * f, 2),
            reported_sample_tn=round(sample_tn[y] * f, 2),
            coverage=sample_tn[y] / glob_tn[y],
            scale_factor=scale,
            scaled_up_winners_bn=(g.clip(lower=0) * s["f"]).sum() * f / 1e3,
            scaled_up_net_bn=(g * s["f"]).sum() * f / 1e3,
            scaled_up_net_uniform_bn=net * scale,
        ))
    return pd.DataFrame(rows)


def main(years=YEARS_WITH_2020, rate=RATE):
    """Compute the world scale factors for both samples, write the factor table and
    the coverage tables with the scaled totals."""
    tables_dir, _ = config.output_dirs("paper/main_text")
    glob_tn, rep_tn = global_mne_profit_tn(years)
    grav_tn = disaggregated_sample_profit_tn()
    sf = {"reported_only": {y: glob_tn[y] / rep_tn[y] for y in years},
          "gravity": {y: glob_tn[y] / grav_tn[y] for y in years}}

    # I write the scale factors (both samples) first, because the coverage tables
    # below and every later exhibit read them.
    table = _hc.build_factor_table(sf)
    _hc.write_factor_table(table)
    print(table.round(4).to_string(index=False))

    for sample, sample_tn, suffix in [("reported_only", rep_tn, ""),
                                      ("gravity", grav_tn, "__gravity")]:
        out = scale_table(sample, glob_tn, sample_tn, years, rate)
        # I check that the scaled gross gains equal SF_t times the sample's gross gains,
        # before rounding.
        gap = (out["scaled_up_winners_bn"] - out["revenue_gain_winners_bn"]
               * out["scale_factor"]).abs().max()
        # I round the $bn and $tn columns to two decimal places and the ratios
        # (coverage, scale factor) to four.
        out = out.round(2).assign(coverage=out["coverage"].round(4),
                                  scale_factor=out["scale_factor"].round(4))
        csv = tables_dir / f"scaleup_yearly{suffix}.csv"
        out.to_csv(csv, index=False)
        print(f"\n[{sample}]")
        print(out.to_string(index=False))
        print(f"wrote {csv}")
        print(f"  scaled gross gains vs SF_t x gross gains: max |diff| = {gap:.4f} bn")


# %% MARK: 5. Bounds of the world estimate
def global_range_series():
    """Return the yearly world net revenue gain (constant BASE_YEAR US$ bn, full window including 2020) of the
    conservative, the headline and the optimistic estimate, unscaled and scaled with the factor table (each
    country-year scaled by its f before summing, which gives SF_t times the sum), and the coverage.

      conservative   both legs at effective tax rates (rate mode loss_etr_gain_etr).
      headline       gains at the statutory CIT, losses at the effective rate (loss_cit_gain_etr).
      optimistic     gains at the statutory CIT, losses at the bottom-10% effective rate of the partner, the rate of
                     the most lightly taxed multinationals.
    Returns (years, cons, head, opt, scaled, cov), with scaled a dict {"cons", "head", "opt"}."""
    import glob as _glob
    tables_dir, _ = config.output_dirs("paper/main_text")
    sc = pd.read_csv(tables_dir / "scaleup_yearly.csv").set_index("year")
    COV = sc["coverage"].to_dict()
    years = YEARS_WITH_2020
    base = (
        str(
            config.estimates_dir("reported_only", "excl_resource")
            / "tables"
            / "excl_resource"
        )
        + "/"
    )
    defl = pd.Series(DEFL)

    def _yearly(values, frame, scaled):
        v = pd.Series(np.asarray(values, dtype=float), index=frame.index)
        if scaled:
            v = v * _hc.factor_for(frame, "reported_only")
        w = v.groupby(frame["year"].values).sum()
        return (w * defl).reindex(years) / 1e3  # $bn constant BASE_YEAR

    def _net(stub, scaled=False):
        f = _glob.glob(base + f"country_estimates__{stub}.csv")
        h = pd.read_csv(f[0], usecols=["iso_partner", "year", "revenue_gain_from_ut"])
        h = h[h.year.isin(years)]
        return _yearly(h["revenue_gain_from_ut"], h, scaled)

    cons_stub = f"{HEADLINE}__etrdef_{ETR}__etrmax_{THRESH}__loss_etr_gain_etr"
    head_stub = f"{HEADLINE}__etrdef_{ETR}__etrmax_{THRESH}__loss_cit_gain_etr"
    cons, head = _net(cons_stub), _net(head_stub)
    mf = _glob.glob(
        base + f"misalignment__{HEADLINE}__etrdef_average"
        f"__etrmax_{THRESH}__losers_p10_gainers_avgetr.csv"
    )[0]
    d = pd.read_csv(
        mf,
        usecols=lambda c: c
        in [
            "iso_partner",
            "year",
            "misaligned_profit",
            "cit",
            "etr_partner_p10_excl_resource",
        ],
        low_memory=False,
    )
    d = d[d.year.isin(years)].reset_index(drop=True)
    m = d.misaligned_profit / 1e6
    cit = pd.to_numeric(d["cit"], errors="coerce")
    p10 = pd.to_numeric(d["etr_partner_p10_excl_resource"], errors="coerce")
    # I price the gain leg at the statutory CIT and the loss leg at the bottom-10% effective rate.
    v = np.where(m < 0, -m, 0) * cit - np.where(m > 0, m, 0) * p10
    opt = _yearly(v, d, scaled=False)
    scaled = {"cons": _net(cons_stub, scaled=True),
              "head": _net(head_stub, scaled=True),
              "opt": _yearly(v, d, scaled=True)}
    return years, cons, head, opt, scaled, COV


def write_global_range():
    """Write the series of the world estimate and its bounds, from the conservative to the optimistic estimate,
    which the methodology note quotes."""
    years, cons, head, opt, scaled, cov = global_range_series()
    tables_dir, _ = config.output_dirs("paper/main_text")
    path = tables_dir / "fig01_global_revenue_gains_data.csv"
    pd.DataFrame({"year": years, "conservative_bn": cons.to_numpy(), "headline_bn": head.to_numpy(),
                  "optimistic_bn": opt.to_numpy(), "conservative_scaled_bn": scaled["cons"].to_numpy(),
                  "headline_scaled_bn": scaled["head"].to_numpy(), "optimistic_scaled_bn": scaled["opt"].to_numpy(),
                  "coverage": [cov.get(y) for y in years]}).round(4).to_csv(path, index=False)
    print(f"wrote {path}")


# %% MARK: 6. Run
if __name__ == "__main__":
    # The coverage tables (both samples, every year including 2020) and the
    # scale factors that every later exhibit reads.
    main(years=YEARS_WITH_2020)
    # The world estimate and its bounds, per year.
    write_global_range()
