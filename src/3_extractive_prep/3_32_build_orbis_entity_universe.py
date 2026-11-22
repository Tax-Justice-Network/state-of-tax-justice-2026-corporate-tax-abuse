# %%
"""
3_32 — Build the Orbis extractive-entity universe.

This script builds the full Orbis extractive-entity universe that 3_33 uses to attach an HQ country to every EITI
company. Matching only against the about 6,000 deduplicated top-level companies is not enough. The raw Orbis pull
contains the full extractive universe (about 600,000 entities, each carrying its GUO BvD ID, name, type and country
directly), so it already includes the local operating subsidiaries ("Total E&P Angola", "Shell Nigeria", "Kibali
Goldmines SA", …). Matching an EITI company string against that universe (blocked by the country the company pays
in) and reading off the matched entity's GUO country is the proper way to get the HQ. The output flag
in_cbcr_universe = (n_subsidiaries >= 2) or (peak revenue >= €750M) marks a multi-entity extractive group above the
CbCR turnover threshold. A missing revenue figure does not disqualify an entity.

Section outline (numbers match the cell headings below):
1. Setup.
2. Header helpers.
3. Read Orbis extracts.
4. Main.

Extractive prep, stage 3_32 — after 3_31, before 3_33.

Reads (all in data/raw/orbis/):
  extractives_guo_orbis*.csv / .xlsx  — Company name, BvD ID, GUO BvD/Name/Type/Country (entity→GUO)
  extractives_static_orbis*.csv       — BvD ID, Country ISO, NACE core, No of subsidiaries
  extractives_financials_orbis*.csv   — BvD ID, Operating revenue (Turnover) th USD 2016..2025
                                        (batches 33/35/36/38/39/42 are missing, so about 15% of entities have no revenue)

Writes:
  data/intermediate/extractive/orbis_entity_universe.csv  — one row per Orbis bvd_id: name,
    entity_country, nace_core, n_subsidiaries, guo_bvd_id, guo_name, guo_type, guo_country,
    peak_operating_revenue_usd, in_cbcr_universe

Usage:
  python src/3_extractive_prep/3_32_build_orbis_entity_universe.py

Author: Tax Justice Network.
Last updated: 2026-07-25.
"""
# %% MARK: 1. Setup
import csv
import glob
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT

RAW_ORBIS = (EXT_INT / ".." / ".." / "raw" / "orbis").resolve()
OUT = EXT_INT / "orbis_entity_universe.csv"
CBCR_REVENUE_THRESHOLD_TH_USD = 750_000.0   # €750M taken as about US$750M. Orbis revenue is in thousands of US$.
MIN_SUBS_FOR_MNE = 2


# %% MARK: 2. Header helpers
def _norm_hdr(s):
    """Normalises a header cell so that the Orbis web-export and flatfile names match. I lowercase the text, turn
    underscores into spaces, collapse whitespace and strip the GUO ownership-threshold token, so that `GUO 50 - Name`
    and `GUO_50_Name` both match the `guo - name` prefix used below."""
    s = str(s).strip().lower().replace("_", " ")
    s = re.sub(r"\bguo\s*\d+(?:\.\d+)?\b", "guo", s)   # "guo 50 -" / "guo 25.01 -" -> "guo -"
    s = re.sub(r"\s+", " ", s)
    return s


def _hdr_idx(hdr, *prefixes):
    for i, c in enumerate(hdr):
        cc = _norm_hdr(c)
        for p in prefixes:
            if cc.startswith(_norm_hdr(p)):
                return i
    return None


def _num(x):
    if x is None:
        return None
    x = str(x).strip().replace(",", "").replace(" ", "")
    if x in ("", "n.a.", "n.s.", "na", "N/A", "-"):
        return None
    try:
        return float(x)
    except ValueError:
        return None


# %% MARK: 3. Read Orbis extracts
def read_guo():
    """Returns a dict bvd_id → (name, guo_bvd, guo_name, guo_type, guo_country)."""
    out = {}
    for f in sorted(glob.glob(str(RAW_ORBIS / "extractives_guo_orbis*.csv"))):
        with open(f, encoding="utf-8-sig", newline="") as fh:
            r = csv.reader(fh)
            hdr = next(r)
            i_name = _hdr_idx(hdr, "company name")
            i_bvd = _hdr_idx(hdr, "bvd id")
            i_gb = _hdr_idx(hdr, "guo - bvd id", "guo  - bvd id")
            i_gn = _hdr_idx(hdr, "guo - name")
            i_gt = _hdr_idx(hdr, "guo - type")
            i_gc = _hdr_idx(hdr, "guo - country")
            for row in r:
                if i_bvd is None or i_bvd >= len(row):
                    continue
                bvd = row[i_bvd].strip()
                if not bvd:
                    continue
                out[bvd] = (
                    row[i_name].strip() if i_name is not None and i_name < len(row) else "",
                    row[i_gb].strip() if i_gb is not None and i_gb < len(row) else "",
                    row[i_gn].strip() if i_gn is not None and i_gn < len(row) else "",
                    row[i_gt].strip() if i_gt is not None and i_gt < len(row) else "",
                    row[i_gc].strip() if i_gc is not None and i_gc < len(row) else "",
                )
    # The two batches that exist only as .xlsx files
    for f in sorted(glob.glob(str(RAW_ORBIS / "extractives_guo_orbis*.xlsx"))):
        try:
            from openpyxl import load_workbook
            wb = load_workbook(f, read_only=True, data_only=True)
            ws = wb.active
            rows = ws.iter_rows(values_only=True)
            hdr = [str(c) if c is not None else "" for c in next(rows)]
            i_name = _hdr_idx(hdr, "company name"); i_bvd = _hdr_idx(hdr, "bvd id")
            i_gb = _hdr_idx(hdr, "guo - bvd id", "guo  - bvd id"); i_gn = _hdr_idx(hdr, "guo - name")
            i_gt = _hdr_idx(hdr, "guo - type"); i_gc = _hdr_idx(hdr, "guo - country")
            for row in rows:
                if i_bvd is None or i_bvd >= len(row) or not row[i_bvd]:
                    continue
                bvd = str(row[i_bvd]).strip()
                out.setdefault(bvd, (
                    str(row[i_name]).strip() if i_name is not None and i_name < len(row) and row[i_name] else "",
                    str(row[i_gb]).strip() if i_gb is not None and i_gb < len(row) and row[i_gb] else "",
                    str(row[i_gn]).strip() if i_gn is not None and i_gn < len(row) and row[i_gn] else "",
                    str(row[i_gt]).strip() if i_gt is not None and i_gt < len(row) and row[i_gt] else "",
                    str(row[i_gc]).strip() if i_gc is not None and i_gc < len(row) and row[i_gc] else "",
                ))
            wb.close()
        except Exception as e:
            print(f"  [warn] could not read {Path(f).name}: {e}")
    return out


def read_static():
    """Returns a dict bvd_id → (entity_country, nace_core, n_subsidiaries)."""
    out = {}
    for f in sorted(glob.glob(str(RAW_ORBIS / "extractives_static_orbis*.csv"))):
        with open(f, encoding="utf-8-sig", newline="") as fh:
            r = csv.reader(fh)
            hdr = next(r)
            i_bvd = _hdr_idx(hdr, "bvd id")
            i_cc = _hdr_idx(hdr, "country iso code")
            i_nace = _hdr_idx(hdr, "nace rev. 2, core code")
            i_subs = _hdr_idx(hdr, "no of subsidiaries")
            for row in r:
                if i_bvd is None or i_bvd >= len(row):
                    continue
                bvd = row[i_bvd].strip()
                if not bvd:           # continuation row (secondary NACE code), skipped
                    continue
                out[bvd] = (
                    (row[i_cc].strip() if i_cc is not None and i_cc < len(row) else ""),
                    (row[i_nace].strip() if i_nace is not None and i_nace < len(row) else ""),
                    _num(row[i_subs]) if i_subs is not None and i_subs < len(row) else None,
                )
    return out


def read_financials():
    """Returns a dict bvd_id → peak operating revenue (thousands of US$) over 2016–2025."""
    out = {}
    for f in sorted(glob.glob(str(RAW_ORBIS / "extractives_financials_orbis*.csv"))):
        with open(f, encoding="utf-8-sig", newline="") as fh:
            r = csv.reader(fh)
            hdr = next(r)
            i_bvd = _hdr_idx(hdr, "bvd id")
            rev_cols = [i for i, c in enumerate(hdr) if c.strip().lower().startswith("operating revenue")]
            for row in r:
                if i_bvd is None or i_bvd >= len(row):
                    continue
                bvd = row[i_bvd].strip()
                if not bvd:
                    continue
                vals = [_num(row[i]) for i in rev_cols if i < len(row)]
                vals = [v for v in vals if v is not None]
                if vals:
                    out[bvd] = max(out.get(bvd, 0.0), max(vals))
    return out


# %% MARK: 4. Main
def main():
    print("Reading raw Orbis extracts ...")
    guo = read_guo()
    print(f"  guo:        {len(guo):,} entities")
    static = read_static()
    print(f"  static:     {len(static):,} entities")
    fin = read_financials()
    print(f"  financials: {len(fin):,} entities with a revenue figure")

    all_bvd = set(guo) | set(static)
    print(f"  union:      {len(all_bvd):,} bvd_ids")

    cols = ["bvd_id", "name", "entity_country", "nace_core", "n_subsidiaries",
            "guo_bvd_id", "guo_name", "guo_type", "guo_country", "peak_operating_revenue_th_usd", "in_cbcr_universe"]
    n_mne = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for bvd in sorted(all_bvd):
            gname, gb, gn, gt, gc = guo.get(bvd, ("", "", "", "", ""))
            ec, nace, nsub = static.get(bvd, ("", "", None))
            rev = fin.get(bvd)
            name = gname or ""
            # The GUO of a top-level company is the company itself. If the GUO country is missing, I use the entity
            # country as the GUO country.
            guo_country = gc or ec
            in_mne = ((nsub is not None and nsub >= MIN_SUBS_FOR_MNE) or
                      (rev is not None and rev >= CBCR_REVENUE_THRESHOLD_TH_USD))
            if in_mne:
                n_mne += 1
            w.writerow([bvd, name, ec, nace, ("" if nsub is None else int(nsub)),
                        gb, gn, gt, guo_country, ("" if rev is None else f"{rev:.0f}"), int(in_mne)])
    print(f"\nWrote {OUT}  ({len(all_bvd):,} entities; {n_mne:,} flagged in_cbcr_universe = {100*n_mne/max(1,len(all_bvd)):.0f}%)")
    # Quick coverage notes
    no_guo_country = sum(1 for bvd in all_bvd if not (guo.get(bvd, ("", "", "", "", ""))[4] or static.get(bvd, ("", "", None))[0]))
    print(f"  entities with no GUO country and no entity country: {no_guo_country:,}")
    n_no_rev = len(all_bvd) - len(set(fin) & all_bvd)
    print(f"  entities with no revenue figure: {n_no_rev:,} ({100*n_no_rev/len(all_bvd):.0f}%)  ← financials batches 33/35/36/38/39/42 are missing from the pull")


if __name__ == "__main__":
    main()
