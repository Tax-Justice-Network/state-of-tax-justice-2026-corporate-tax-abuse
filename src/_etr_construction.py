"""Partner-year effective tax rate (ETR) construction.

This module is the single source of truth for the rolling-window ETR statistics.
They are used in:
  - 1_clean.py (computes the canonical ETRs from reported profit and tax)
  - 4_correcting_cbcr_for_resource_payments.py (recomputes the same family
    on resource-corrected profit and tax for the excl_resource dataset)

The window runs from two years before to two years after the focal year (a
5-year span centred on it). It is the same window that the main_etrs /
alternative_corrected_etrs wrappers in 1_clean.py request.

Outputs per call:
  partner_year_df: one row per (iso_partner, year) with columns
      etr_domestic_{suffix}
      etr_foreign_{suffix}
      etr_average_{suffix}
      etr_partner_median_{suffix}   (only when pair_stats=True)
      etr_partner_p25_{suffix}      (only when pair_stats=True)
      etr_partner_p10_{suffix}      (only when pair_stats=True)
      etr_partner_min_{suffix}      (only when pair_stats=True)

  pair_year_df: one row per (iso_parent, iso_partner, year) with
      etr_parent_partner_{suffix}
  (None when pair_stats=False.)
"""

# %% MARK: 1. Setup
import os

import numpy as np
import pandas as pd

# A jurisdiction's pooled profit base over the window must exceed this amount
# (USD) for its aggregate ETR to count as reliably measured. Below it, the ratio
# of tax to profit is dominated by noise rather than a meaningful rate, so I
# return the ETR as NaN (an undefined rate, distinct from a measured zero) and the
# downstream scripts fall back to the statutory CIT. The default is US$100
# million. It can be changed with the ETR_MIN_PROFIT_BASE_USD environment variable.
ETR_MIN_PROFIT_BASE_USD = float(os.environ.get("ETR_MIN_PROFIT_BASE_USD", "1e8"))


# %% MARK: 2. Helpers
def safe_nonnegative_etr(tax_paid, profit):
    """Returns the ETR = tax / profit, clipped to [0, 1]. The result is NaN if profit <= 0 or
    an input is missing."""
    if pd.isna(tax_paid) or pd.isna(profit) or profit <= 0:
        return np.nan
    etr = tax_paid / profit
    if pd.isna(etr) or np.isinf(etr):
        return np.nan
    return float(min(max(etr, 0.0), 1.0))


def _with_suffix(base, suffix):
    return f"{base}_{suffix}" if suffix else base


def _aggregate_etr_per_partner(df, profit_col, tax_col, out_col):
    """Sums tax and profit per iso_partner and takes the ratio.

    The ETR is undefined (NaN) when the pooled profit base is negligibly small or
    not positive (<= ETR_MIN_PROFIT_BASE_USD), because the ratio of tax to a
    near-zero or negative profit base is noise, not a meaningful rate. I return NaN
    rather than clipping such a ratio into [0, 1], so that a jurisdiction with thin
    or negative profit does not receive a rate of zero by construction. This mirrors
    the guard in safe_nonnegative_etr (used for the pair ETR), which returns NaN for
    profit <= 0."""
    d = df.groupby("iso_partner", as_index=False)[[tax_col, profit_col]].sum()
    ratio = d[tax_col] / d[profit_col]
    d[out_col] = ratio.where(d[profit_col] > ETR_MIN_PROFIT_BASE_USD, np.nan)
    d[out_col] = d[out_col].replace([np.inf, -np.inf], np.nan).clip(lower=0, upper=1)
    return d[["iso_partner", out_col]]


# %% MARK: 3. Loss-offset rules
def _rule_for(rules_for_iso, year):
    """Returns the row of a jurisdiction's rule table that is in force in `year` (the latest
    since_year <= year)."""
    r = None
    for row in rules_for_iso:
        if row["since_year"] <= year and (r is None or row["since_year"] >= r["since_year"]):
            r = row
    return r


def usable_base_with_loss_rules(df, profit_col, loss_rules):
    """Returns, per (parent, partner, year), the positive profit minus the losses of
    the same pair that the partner jurisdiction's rules let it absorb. This
    simulates a taxpayer-level loss carry-forward and carry-back on the CbCR pair
    panel.

    The rules have one row per iso and since_year:
      cf_years              carry-forward horizon (99 = unlimited)
      cf_cap_share          share of the profit above the threshold that losses may
                            offset (1 = no cap)
      cf_cap_threshold_usd  profit that losses may offset in full before the cap
                            applies
      cb_years              carry-back horizon: a loss first offsets the pair's
                            positive base of the preceding cb_years years
    The loss stock starts empty, because losses before the sample are not
    observed. For partners without a rule row I use the positive profit as the
    base (the positive-pooling fallback). The rule in force in the year in which
    the loss is used decides the caps and the expiry."""
    base = np.maximum(pd.to_numeric(df[profit_col], errors="coerce").fillna(0.0).to_numpy(), 0.0)
    if loss_rules is None or len(loss_rules) == 0:
        return base
    rules = {}
    for r in loss_rules.to_dict("records"):
        rules.setdefault(str(r["iso"]).strip(), []).append({
            "since_year": int(r.get("since_year", 0) or 0),
            "cf_years": float(r.get("cf_years", 99) if pd.notna(r.get("cf_years", 99)) else 99),
            "cf_cap_share": float(r.get("cf_cap_share", 1.0) if pd.notna(r.get("cf_cap_share", 1.0)) else 1.0),
            "cf_cap_threshold_usd": float(r.get("cf_cap_threshold_usd", 0.0) if pd.notna(r.get("cf_cap_threshold_usd", 0.0)) else 0.0),
            "cb_years": float(r.get("cb_years", 0) if pd.notna(r.get("cb_years", 0)) else 0),
        })
    profit = pd.to_numeric(df[profit_col], errors="coerce").fillna(0.0).to_numpy()
    years = df["year"].to_numpy()
    order = np.lexsort((years, df["iso_partner"].to_numpy(), df["iso_parent"].to_numpy()))
    parents = df["iso_parent"].to_numpy()[order]
    partners = df["iso_partner"].to_numpy()[order]
    n = len(order)
    i = 0
    while i < n:
        j = i
        while j < n and parents[j] == parents[i] and partners[j] == partners[i]:
            j += 1
        rl = rules.get(str(partners[i]))
        if rl is not None:
            idx = order[i:j]
            ys, ps = years[idx], profit[idx]
            b = np.maximum(ps, 0.0)
            stock = []                                  # [loss_year, remaining]
            for k in range(len(idx)):
                y, p = ys[k], ps[k]
                r = _rule_for(rl, y)
                if r is None:
                    continue
                if p < 0:
                    loss = -p
                    if r["cb_years"] > 0:               # carry-back against recent positive base
                        for m in range(k - 1, -1, -1):
                            if ys[m] < y - r["cb_years"]:
                                break
                            use = min(loss, b[m]); b[m] -= use; loss -= use
                            if loss <= 0:
                                break
                    if loss > 0:
                        stock.append([y, loss])
                elif p > 0 and stock:
                    stock = [s_ for s_ in stock if r["cf_years"] >= 99 or (y - s_[0]) <= r["cf_years"]]
                    if r["cf_cap_share"] >= 1.0:
                        cap = p
                    else:
                        thr = r["cf_cap_threshold_usd"]
                        cap = min(p, thr) + r["cf_cap_share"] * max(p - thr, 0.0)
                    avail = cap
                    for s_ in stock:
                        use = min(s_[1], avail); s_[1] -= use; avail -= use; b[k] -= use
                        if avail <= 0:
                            break
                    stock = [s_ for s_ in stock if s_[1] > 0]
            base[idx] = b
        i = j
    return base


# %% MARK: 4. Rolling-window partner-year ETRs
def compute_partner_year_etrs(
    df,
    profit_col,
    tax_col,
    *,
    suffix=None,
    grouping_col=None,
    grouping_value=None,
    window=2,
    pair_stats=True,
    positive_only=False,
    pooling=None,
    loss_rules=None,
):
    """Computes the rolling-window partner-year ETRs (and optionally the pair-year ETRs).

    Parameters
    ----------
    df : DataFrame with columns iso_parent, iso_partner, year, profit_col, tax_col,
        and optionally grouping_col.
    profit_col, tax_col : str
        Names of the profit and tax columns to use in the (tax / profit) ratio.
    suffix : str or None
        Suffix appended to every output column (e.g. "corrected" produces
        "etr_average_corrected"). With None or "" no suffix is added.
    grouping_col, grouping_value : str or None
        If both are set, I keep only the rows with df[grouping_col] == grouping_value.
    window : int
        Half-window in years. The rolling window is [year - window, year + window],
        inclusive. The default of 2 gives a 5-year window.
    pair_stats : bool
        Whether to compute the pair-year ETR and the partner-level median, p25
        and minimum of the pair ETRs. Variants that do not need them (e.g. the
        uncorrected ETR family) skip them.
    positive_only : bool
        If True, I compute the pooled partner-level rates (domestic, foreign,
        average) on positive-profit cells only, as tax paid over the profit that
        was actually taxed. This is the same base the OECD "positive profits"
        sub-group ETR uses. Pooling over all cells lets one large loss cell
        (Malta's US-parent cell, −US$29.6bn in 2020) collapse the pooled base of
        every window that contains it. The ratio of tax to a profit near zero is
        then clipped to 100%, and the fill-in spreads that rate to the undefined
        years. The forgone-revenue leg priced at such a rate exceeds the tax the
        country collects. The pair-level statistics are not affected, because
        they already treat a pair base that is not positive as undefined.
    pooling : {"all", "positive", "group_net", "group_net_rules"} or None
        How the partner-level pooled rates are formed (None means "positive" if
        positive_only is set, else "all"):
          all             tax / net profit over every cell in the window
          positive        tax / profit of positive-profit cells only
          group_net       within-group netting: in each (parent, partner) pair,
                          losses offset that pair's own profits over the window
                          (unlimited carry inside the window, no offset across
                          groups). The partner base is the sum over pairs of
                          max(pair net, 0). A loss of one group then cannot cancel
                          the taxed profits of unrelated groups in the same country.
          group_net_rules within-group netting restricted by each partner
                          jurisdiction's loss-offset rules (`loss_rules`):
                          carry-forward horizon, annual offset cap, carry-back
                          years. I use the losses year by year over the full
                          panel. The loss stock starts empty, because losses
                          before the sample are not observed. The usable base of
                          each pair-year is the positive profit minus the losses
                          actually absorbed. Where a partner has no rule row, the
                          base is the positive profit (the positive-pooling
                          fallback).
    loss_rules : DataFrame or None
        Rule table for "group_net_rules": one row per (iso, since_year) with
        cf_years (99 = unlimited), cf_cap_share (1 = no cap), cf_cap_threshold_usd
        (amount usable in full before the cap share applies), cb_years.

    Returns
    -------
    partner_year_df : DataFrame
    pair_year_df : DataFrame or None
    """
    required = ["iso_parent", "iso_partner", "year", profit_col, tax_col]
    cols = list(required)
    if grouping_col is not None:
        cols = cols + [grouping_col]
    df = df[cols].copy()

    if grouping_col is not None and grouping_value is not None:
        df = df.loc[df[grouping_col] == grouping_value]

    # Only rows with both tax and profit observed enter the pooled ratios. If I
    # dropped rows on missing tax alone, rows with tax but missing profit would
    # stay, and their tax would be summed against a profit counted as zero, which
    # inflates the pooled ETR.
    df = df.dropna(subset=[tax_col, profit_col])

    domestic_col = _with_suffix("etr_domestic", suffix)
    foreign_col = _with_suffix("etr_foreign", suffix)
    average_col = _with_suffix("etr_average", suffix)
    median_col = _with_suffix("etr_partner_median", suffix)
    p25_col = _with_suffix("etr_partner_p25", suffix)
    p10_col = _with_suffix("etr_partner_p10", suffix)
    min_col = _with_suffix("etr_partner_min", suffix)
    pair_col = _with_suffix("etr_parent_partner", suffix)

    partner_results = []
    pair_results = []

    _pooling = pooling or ("positive" if positive_only else "all")
    if _pooling == "group_net":
        df["_base_group_net"] = df[profit_col]          # netted per pair inside each window
    elif _pooling == "group_net_rules":
        df["_base_rules"] = usable_base_with_loss_rules(df, profit_col, loss_rules)

    unique_years = sorted(df["year"].dropna().unique())

    for year in unique_years:
        start_year = year - window
        end_year = year + window
        window_df = df[(df["year"] >= start_year) & (df["year"] <= end_year)].copy()

        if _pooling == "positive":
            pool_df = window_df[window_df[profit_col] > 0]
        elif _pooling in ("group_net", "group_net_rules"):
            # I collapse the window to (parent, partner) pairs. The pooled base is
            # the pair's netted profit (group_net) or its usable base under the
            # loss-offset rules (group_net_rules), never below zero.
            _bc = "_base_group_net" if _pooling == "group_net" else "_base_rules"
            pool_df = (window_df.groupby(["iso_parent", "iso_partner"], as_index=False)
                       [[tax_col, _bc]].sum())
            if _pooling == "group_net":
                pool_df[_bc] = pool_df[_bc].clip(lower=0)
            pool_df = pool_df.rename(columns={_bc: profit_col})
        else:
            pool_df = window_df
        foreign_df = pool_df[pool_df["iso_parent"] != pool_df["iso_partner"]]
        domestic_df = pool_df[pool_df["iso_parent"] == pool_df["iso_partner"]]

        etr_domestic = _aggregate_etr_per_partner(
            domestic_df, profit_col, tax_col, domestic_col
        )
        etr_foreign = _aggregate_etr_per_partner(
            foreign_df, profit_col, tax_col, foreign_col
        )
        etr_average = _aggregate_etr_per_partner(
            pool_df, profit_col, tax_col, average_col
        )

        partner_year = etr_domestic.merge(
            etr_foreign, on="iso_partner", how="outer"
        ).merge(etr_average, on="iso_partner", how="outer")

        if pair_stats:
            pair_window = (
                window_df.groupby(["iso_parent", "iso_partner"], as_index=False)[
                    [tax_col, profit_col]
                ]
                .sum(min_count=1)
                .copy()
            )

            pair_window[pair_col] = pair_window.apply(
                lambda r: safe_nonnegative_etr(r[tax_col], r[profit_col]), axis=1
            )
            pair_window[pair_col] = pair_window[pair_col].clip(lower=0, upper=1)
            pair_window["year"] = year

            pair_results.append(
                pair_window[
                    ["iso_parent", "iso_partner", "year", pair_col]
                ].copy()
            )

            valid_pairs = pair_window.dropna(subset=[pair_col]).copy()

            if valid_pairs.empty:
                partner_stats = pd.DataFrame(
                    columns=["iso_partner", median_col, p25_col, p10_col, min_col]
                )
            else:
                partner_stats = (
                    valid_pairs.groupby("iso_partner", as_index=False)[pair_col]
                    .agg(**{median_col: "median", min_col: "min"})
                    .copy()
                )

                p25 = (
                    valid_pairs.groupby("iso_partner")[pair_col]
                    .quantile(0.25, interpolation="linear")
                    .reset_index(name=p25_col)
                )
                p10 = (
                    valid_pairs.groupby("iso_partner")[pair_col]
                    .quantile(0.10, interpolation="linear")
                    .reset_index(name=p10_col)
                )

                partner_stats = partner_stats.merge(
                    p25, on="iso_partner", how="left"
                ).merge(p10, on="iso_partner", how="left")

                for c in [median_col, p25_col, p10_col, min_col]:
                    partner_stats[c] = partner_stats[c].clip(lower=0, upper=1)

            partner_year = partner_year.merge(
                partner_stats, on="iso_partner", how="outer"
            )

        partner_year["year"] = year
        partner_results.append(partner_year)

    partner_year_df = pd.concat(partner_results, ignore_index=True)
    pair_year_df = (
        pd.concat(pair_results, ignore_index=True) if pair_stats else None
    )

    return partner_year_df, pair_year_df
