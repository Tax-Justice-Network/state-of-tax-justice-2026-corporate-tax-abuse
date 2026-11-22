# %%
"""
6 — Consolidate the country-level estimates of a run into one summary.

This script concatenates the per-specification country estimates that script 5
writes into one long summary per run (topic). It reads exactly the files listed in
the topic's run_summary.csv, which script 5 rewrites in every run, so files of
earlier runs in the same folder never enter the summary. It is the final data stage
of the pipeline: every figure, table and ranking is produced downstream by the
exhibit scripts 7a to 10.

Section outline (numbers match the cell headings below):
1. Setup.
2. Run settings.
3. Consolidation.
4. Main.

Pipeline step 6 — after 5 (estimation), before the exhibit scripts 7a to 10.

Reads (per topic, with <topic> remapped by config.output_dirs into
output/estimates/{reported_only,with_imputed_rows}/2_resources_excluded/):
  output/<topic>/tables/<sample>/run_summary.csv              — the specifications of the run (script 5)
  output/<topic>/tables/<sample>/country_estimates__*.csv     — the country estimates of each specification (script 5)

Writes:
  output/<topic>/tables/summary_country_year_long.csv         — all (iso_partner, year, specification) rows, the file
                                                                the exhibit scripts read

Usage:
  python src/6_consolidate_country_estimates.py                                 — both samples
  python src/6_consolidate_country_estimates.py unitary_taxation_excl_resource  — just that one topic

Author: Tax Justice Network.
Last updated: 2026-11-22.
"""
# %% MARK: 1. Setup
import os
import re
import sys
from pathlib import Path

import pandas as pd


def _longpath(p):
    """On Windows, this function prefixes paths longer than 240 characters with
    \\\\?\\ so that open() bypasses the 260-character MAX_PATH limit. Deep project
    roots can push some country_estimates file names over that limit."""
    s = os.fspath(p)
    if sys.platform == "win32" and len(s) > 240 and not s.startswith("\\\\?\\"):
        s = "\\\\?\\" + os.path.abspath(s)
    return s


if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import output_dirs


# %% MARK: 2. Run settings
# The topics to consolidate are the output topics of script 5 on both samples. The
# reported-only ("_reported") topic is the headline sample. A topic given on the
# command line replaces them.
DEFAULT_TOPICS = ["unitary_taxation_excl_resource_reported", "unitary_taxation_excl_resource"]

# The file name of a country estimate encodes its specification.
SPEC_PATTERN = re.compile(
    r"country_estimates__(?P<formula>.+?)__etrdef_(?P<etr>.+?)__etrmax_(?P<thr>.+?)__(?P<rate>.+)$"
)


# %% MARK: 3. Consolidation
def consolidate(topic):
    """Writes the long summary of one topic from the country files that its
    run_summary.csv lists."""
    print(f"\n=== topic: {topic} ===")
    tables_dir, _ = output_dirs(topic)   # script 6 writes tables only
    rs_path = tables_dir / "run_summary.csv"
    if not rs_path.exists():
        print(f"  [skip] no run_summary.csv at {rs_path}")
        return
    rs = pd.read_csv(rs_path)
    print(f"  {len(rs)} specifications in run_summary")

    parts = []
    for _, row in rs.iterrows():
        # Script 5 writes the country files into a subfolder per sample.
        fp = tables_dir / str(row["sample_name"]) / Path(str(row["country_file"])).name
        m = SPEC_PATTERN.match(fp.stem)
        if m is None or not fp.exists():
            raise FileNotFoundError(f"listed in {rs_path} but missing or unnamed: {fp}")
        df = pd.read_csv(_longpath(fp))
        if df.empty:
            continue
        for k, v in m.groupdict().items():
            if k not in df.columns:
                df[k] = v
        parts.append(df)

    if not parts:
        print(f"  [skip] no country estimates in {tables_dir}")
        return
    long_df = pd.concat(parts, ignore_index=True)
    long_df["year"] = pd.to_numeric(long_df["year"], errors="coerce")
    long_df.to_csv(tables_dir / "summary_country_year_long.csv", index=False)
    print(f"  wrote {tables_dir / 'summary_country_year_long.csv'} ({len(long_df):,} rows)")


# %% MARK: 4. Main
def main():
    for topic in sys.argv[1:] or DEFAULT_TOPICS:
        consolidate(topic)


if __name__ == "__main__":
    main()
