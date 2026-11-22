# %%
"""
_host_coverage — World scale factors (scaling aggregates to all multinationals).

This module provides the factors that scale aggregates from the country-by-country sample up to all
multinationals. Every aggregate development (world, income group, region) is shown per year and scaled with
the world factor SF_t of that year (global multinational profit divided by the profit in the sample, from 7a),
while country-level exhibits stay unscaled. Every country takes the same factor, so gains and losses stay in
proportion and the scaled net equals the unscaled net times SF_t.

7a, which runs first, writes the factors to output/paper/main_text/tables/host_scale_factors.csv, one row per
sample (reported_only, gravity) and year, with the columns sample, year and f. The exhibits multiply every money
column of a country-year by f before they aggregate, and then recompute the percentages from the scaled sums.

Section outline (numbers match the cell headings below):
1. Constants.
2. Estimation sample.
3. Factor table.
4. Readers for the exhibit scripts.

Author: Tax Justice Network.
Created: 2026-10-13.  Last updated: 2026-11-23.
"""
import os
import sys
from pathlib import Path

import pandas as pd

_SRC = os.path.dirname(os.path.abspath(__file__))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
import config  # noqa: E402

# %% MARK: 1. Constants
SAMPLES = ("reported_only", "gravity")
FACTOR_TABLE = config.output_dirs("paper/main_text")[0] / "host_scale_factors.csv"


# %% MARK: 2. Estimation sample
def reported_estimate_sample(df, max_agg_share=0.5):
    """Reproduces script 5's REPORTED_ONLY sample on a cbcr_main_* frame.

      (1) Partial-reporter rule: I drop each (parent, year) whose share of foreign
          unrelated-party revenue in aggregate rows (is_distributed == 1) exceeds
          `max_agg_share`.
      (2) I keep the rows with is_distributed == 0.
      (3) I drop bad-reporter parents left with only their domestic row.
    The frame needs the columns iso_parent, iso_partner, year, is_distributed and
    unrelated_party_revenues."""
    f = df[df["iso_partner"] != df["iso_parent"]]
    upr = pd.to_numeric(f["unrelated_party_revenues"], errors="coerce").fillna(0.0)
    agg = upr.where(f["is_distributed"] == 1, 0.0)
    tot = upr.groupby([f["iso_parent"], f["year"]]).sum()
    sh = agg.groupby([f["iso_parent"], f["year"]]).sum() / tot.where(tot > 0)
    flagged = set(sh[sh > max_agg_share].index)
    key = pd.MultiIndex.from_arrays([df["iso_parent"], df["year"]])
    df = df[~key.isin(flagged)].copy()
    df = df[df["is_distributed"] == 0].copy()
    cross = df.loc[df["iso_partner"] != df["iso_parent"], "iso_parent"].unique()
    return df[df["iso_parent"].isin(cross)].copy()


# %% MARK: 3. Factor table
def build_factor_table(sf_by_sample):
    """Builds the factor table for all samples from `sf_by_sample`, which maps {sample: {year: SF_t}} (7a's world
    scale factors). Returns one row per sample and year with the columns sample, year and f."""
    rows = [dict(sample=s, year=int(y), f=float(v)) for s, sf in sf_by_sample.items() for y, v in sf.items()]
    return pd.DataFrame(rows).sort_values(["sample", "year"]).reset_index(drop=True)


def write_factor_table(table, path=None):
    path = FACTOR_TABLE if path is None else path
    _CACHE.clear()
    table.to_csv(path, index=False, float_format="%.6g")
    print(f"wrote {path}  ({len(table):,} rows)")
    return path


# %% MARK: 4. Readers for the exhibit scripts
_CACHE = {}


def load_factors(sample, path=None):
    """Returns the factors f of one sample as a Series indexed by year. Raises a clear error when 7a has not
    written the table yet."""
    path = FACTOR_TABLE if path is None else path
    key = (str(path), sample)
    if key not in _CACHE:
        if not Path(path).exists():
            raise FileNotFoundError(
                f"scale-factor table missing: {path} — run 7a_coverage_scaleup.py first")
        t = pd.read_csv(path)
        t = t[t["sample"] == sample]
        if t.empty:
            raise ValueError(f"no scale factors for sample {sample!r} in {path}")
        _CACHE[key] = t.set_index("year")["f"]
    return _CACHE[key]


def factor_for(df, sample, iso_col="iso_partner", year_col="year"):
    """Returns the scale factor f per row of a frame with a year column. A year without a factor keeps its
    sample value (f = 1). The function does not use `iso_col`, because every country takes the factor of its
    year."""
    f = load_factors(sample)
    return pd.Series(df[year_col].map(f).to_numpy(), index=df.index, dtype=float).fillna(1.0)


def apply_factors(df, cols, sample, iso_col="iso_partner", year_col="year"):
    """Returns a copy of `df` with every column in `cols` multiplied by the scale factor."""
    out = df.copy()
    f = factor_for(out, sample, iso_col, year_col)
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce") * f
    return out
