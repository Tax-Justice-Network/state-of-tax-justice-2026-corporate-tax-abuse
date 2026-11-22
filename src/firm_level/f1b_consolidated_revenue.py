# %%
"""
f1b — Consolidated group revenue for the firm-level public CbCR panel.

This script collects the consolidated revenue of the groups in the firm-level panel of public country-by-country
reports (CbCRs). The public CbCRs under the EU directive, and some voluntary ones, report each jurisdiction's total
revenue including intra-group sales, so the revenues of a report's jurisdictions add up to more than the group's
revenue. Microsoft's FY2025 report, for example, sums to US$521.7bn against US$281.7bn of consolidated revenue. A
country's share of the group's sales is then understated wherever the intra-group sales are booked elsewhere
(Germany: 2.2% of the summed revenue, 4.1% of the consolidated revenue). Script 9 therefore measures the sales factor
against the group's consolidated revenue (`correct_intragroup_revenue`). This script finds that revenue for every
group-year it can, from three raw sources, in this order:
  1. Annual reports and 10-Ks collected by hand for the groups of the company examples
     (data/raw/firm_level/consolidated_revenue_2026-10/manifest_*.csv, one row per group-year with the document,
     its page and URL). The documents themselves are not included.
  2. The company facts in the machine-readable (XBRL) filings to the US Securities and Exchange Commission (SEC) of
     10-K, 20-F and 40-F filers, that is us-gaap or ifrs-full revenue of a fiscal year of 330–400 days. I match them
     by name, with the filer names of the SEC revenue frames or else the entity search of EDGAR (the SEC's filing
     database), and cache them.
  3. Compustat Global (listed non-US groups, for the fiscal years the stored extract covers, mostly up to 2024).
     The extract is licensed through Wharton Research Data Services (WRDS) and not included. I read it where it is
     present at the path below, and the script runs without it otherwise. The published results used it. Without
     it, the groups that only Compustat covers keep the revenues as reported.
I accept a candidate only where the report's summed revenue is 0.97–4 times the consolidated revenue and the report's
headcount (Compustat) or profit before tax (SEC) is close to the group's. A lower revenue ratio means that the report
covers only part of the group, and a higher one means a wrong match. The size check rules out a wrong company or a
wrong fiscal year. Hand-collected rows only need the revenue check. I convert consolidated revenue with the exchange
rates of f1, as the reports are converted.

Section outline (numbers match the cell headings below):
1. Setup.
2. The report side: summed revenue, headcount and profit per group-year.
3. Source 1: annual reports collected by hand.
4. Source 2: SEC XBRL company facts.
5. Source 3: Compustat Global (listed non-US groups).
6. Checks and choice.

Firm-level data preparation, step f1b — after f1, before script 9.

Reads:
  data/intermediate/firm_level/firm_cbcr_panel.csv                      — f1 (summed revenue, headcount, profit)
  data/raw/firm_level/consolidated_revenue_2026-10/manifest_*.csv        — hand-collected annual reports
  data/raw/firm_level/local_accounts_2026-10/line_third_party_shares.csv — lines whose sales to customers are
                                                                            documented in local statutory accounts
  data/raw/firm_level/sec_xbrl_2026-10/frames/*.json                     — SEC XBRL revenue frames (filer names)
  data/raw/firm_level/sec_xbrl_2026-10/{search,facts}/*.json             — cached EDGAR searches and extracted facts
  data/raw/firm_level/compustat_global_funda_usd.parquet                — Compustat Global (licensed, optional,
                                                                            not shipped)
Writes:
  data/intermediate/firm_level/firm_consolidated_revenue.csv — one row per company × year × source candidate:
      consolidated revenue (as published and in US$), the checks, accepted (bool), chosen (the row script 9 uses)
  data/intermediate/firm_level/firm_line_third_party_revenue.csv — documented sales to customers of single lines,
      from local statutory accounts ("fixed"), or for the home line where the hand-collected annual report discloses
      home-country revenue. That figure is "fixed" when it is by location of the selling companies and a "floor"
      otherwise (by customer location, since the group's home companies make most of its sales at home).
Usage:
  python src/firm_level/f1b_consolidated_revenue.py --offline  — use the shipped SEC cache only (no network access)
  python src/firm_level/f1b_consolidated_revenue.py            — also fetch SEC data not yet cached (about one
                                                                  request per second)

Author: Tax Justice Network.
Created: 2026-10-29.  Last updated: 2026-11-02.
"""
# %% MARK: 1. Setup
import argparse
import glob
import gzip
import importlib.util
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
from config import data_raw, data_intermediate  # noqa: E402

PANEL = os.path.join(data_intermediate, "firm_level", "firm_cbcr_panel.csv")
OUT = os.path.join(data_intermediate, "firm_level", "firm_consolidated_revenue.csv")
LINES = os.path.join(data_intermediate, "firm_level", "firm_line_third_party_revenue.csv")
LOCAL = os.path.join(data_raw, "firm_level", "local_accounts_2026-10", "line_third_party_shares.csv")
HAND = os.path.join(data_raw, "firm_level", "consolidated_revenue_2026-10")
SEC = os.path.join(data_raw, "firm_level", "sec_xbrl_2026-10")
COMPUSTAT = os.path.join(data_raw, "firm_level", "compustat_global_funda_usd.parquet")
UA = "SOTJ-research-script/1.0 (non-commercial research)"   # the request headers carry no personal name or address
T_OVER_R = (0.97, 4.0)          # report revenue ÷ consolidated revenue
T_OVER_R_HAND = (0.90, 4.0)     # hand-collected: fiscal year checked by hand
EMP_RATIO = (0.75, 1.33)        # report headcount ÷ group headcount
PBT_RATIO = (0.5, 2.0)          # loose, because entity profits can include intra-group dividends
SEARCH_MIN_REVENUE = 10e9       # EDGAR entity search for non-US groups only above this summed revenue (US$)
SOURCE_RANK = {"annual_report": 0, "sec_xbrl": 1, "compustat_global": 2}
_LABEL_ISO = [(r"United States|U\.S\.", "USA"), (r"Germany|Deutschland", "DEU"), (r"France", "FRA"), (r"Japan", "JPN"),
              (r"Spain|España", "ESP"), (r"Netherlands", "NLD"), (r"Finland", "FIN"), (r"Portugal", "PRT"),
              (r"Denmark", "DNK")]

# I use the exchange rates of f1 (local currency units per US$, period average), so that consolidated revenue is
# converted like the reports.
_spec = importlib.util.spec_from_file_location("f1_panel", os.path.join(_HERE, "f1_build_firm_panel.py"))
_f1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_f1)
fx_to_usd = _f1.fx_to_usd

_SUFFIX = re.compile(r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|PLC|LLC|LP|SA|SAS|SPA|NV|AG|SE|"
                     r"ASA|AB|OYJ|AS|KGAA|GMBH|BV|HOLDINGS?|HLDGS|GROUP|GRP|GRUPO|GROUPE|THE|DE|CLASS [A-C]|"
                     r"INTERNATIONAL|INTL|INDUSTRIES|KK)\b")


def norm(s):
    """Return the upper-case name without legal forms, punctuation, bracketed parts (tickers), 'and'/'&' or
    'Group'/'Holdings'."""
    s = str(s).upper().replace("&", " ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[.,\-/'’]", " ", s)
    s = _SUFFIX.sub(" ", s)
    s = re.sub(r"\bAND\b", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def year_label(start, end):
    """Return the panel's fiscal-year label, the calendar year in which most of the fiscal year falls. A fiscal year
    that ends in June (or a 52/53-week year that ends in the first days of July) takes the year it ends in."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if end.month == 6 or (end.month == 7 and end.day <= 7):
        return end.year
    return (start + (end - start) / 2).year


# %% MARK: 2. The report side: summed revenue, headcount and profit per group-year
def report_totals():
    p = pd.read_csv(PANEL, low_memory=False)
    g = p.groupby(["company_key", "year"])
    t = g.agg(company=("company", "first"), hq=("hq_iso3", "first"),
              T=("total_revenues", "sum"), E=("n_employees", "sum"),
              P=("profit_loss_before_income_tax", "sum")).reset_index()
    t["all_total"] = g["total_revenues"].apply(lambda s: s.notna().all()).to_numpy()
    t["all_unrelated"] = g["unrelated_party_revenues"].apply(lambda s: s.notna().all()).to_numpy()
    t["basis"] = np.where(t.all_unrelated, "unrelated", np.where(t.all_total, "total", ""))
    return t


# %% MARK: 3. Source 1: annual reports collected by hand
_UNIT = {"units": 1.0, "unit": 1.0, "thousand": 1e3, "thousands": 1e3, "million": 1e6, "millions": 1e6,
         "billion": 1e9, "billions": 1e9}


def hand_collected():
    files = sorted(glob.glob(os.path.join(HAND, "manifest_*.csv")))
    if not files:
        return pd.DataFrame()
    h = pd.concat([pd.read_csv(f, dtype=str).assign(_file=os.path.basename(f)) for f in files], ignore_index=True)
    h = h[h["consolidated_revenue"].notna() & h["company_key"].notna() & h["cbcr_year_label"].notna()].copy()
    # I drop gross sales including VAT (the retailer dm publishes no net revenue), because the reports cannot be set
    # against such a figure.
    vat = h["revenue_line_label"].fillna("").str.contains(r"incl(?:uding|\.)? VAT|inkl\. MwSt|Bruttoumsatz",
                                                          case=False, regex=True)
    h = h[~vat]
    mult = h["unit"].str.lower().str.strip().map(_UNIT)
    num = lambda s: pd.to_numeric(s.str.replace(",", "", regex=False), errors="coerce")  # noqa: E731
    h["revenue_lcu"] = num(h["consolidated_revenue"]) * mult
    h["pbt_lcu"] = num(h["consolidated_pbt"]) * mult
    h["employees"] = num(h["employees"])
    h["year"] = pd.to_numeric(h["cbcr_year_label"], errors="coerce").astype("Int64")
    h["home_lcu"] = num(h["home_external_revenue"]) * mult
    h["home_entity_basis"] = h["home_external_revenue_basis"].fillna("").str.contains(
        r"selling entity|location of compan|entity location|company recording", case=False, regex=True)
    return pd.DataFrame(dict(
        company_key=h["company_key"].str.strip(), year=h["year"], source="annual_report",
        source_detail=(h["document_title"].fillna("") + ", " + h["page_or_location"].fillna("")).str.strip(", "),
        url=h["url"], currency=h["currency"].str.upper().str.strip(), revenue_lcu=h["revenue_lcu"],
        pbt_lcu=h["pbt_lcu"], employees=h["employees"], fy_start=h["fy_start"], fy_end=h["fy_end"],
        name_in_source=h["company_name_in_source"], home_lcu=h["home_lcu"], home_entity_basis=h["home_entity_basis"],
        home_label=h["home_external_revenue_label"], home_basis=h["home_external_revenue_basis"]))


# %% MARK: 4. Source 2: SEC XBRL company facts
REV_TAGS = [("us-gaap", "Revenues"), ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
            ("us-gaap", "SalesRevenueNet"), ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
            ("ifrs-full", "Revenue"), ("ifrs-full", "RevenueFromContractsWithCustomers")]
PBT_TAGS = [("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"),
            ("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
            ("ifrs-full", "ProfitLossBeforeTax")]
ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "20-F", "20-F/A", "40-F", "40-F/A"}


def _fetch(url):
    time.sleep(1.0)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return json.loads(raw)


def sec_filer_names():
    """Return a map from the SEC's Central Index Key (CIK) to the filer name, from the stored SEC revenue frames
    (every filer with an annual revenue fact)."""
    names = {}
    for f in glob.glob(os.path.join(SEC, "frames", "*.json")):
        for r in json.load(open(f))["data"]:
            names[int(r["cik"])] = r["entityName"]
    return names


def edgar_search(name, offline):
    os.makedirs(os.path.join(SEC, "search"), exist_ok=True)
    path = os.path.join(SEC, "search", re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")[:80] + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    if offline:
        return []
    d = _fetch("https://efts.sec.gov/LATEST/search-index?keysTyped=" + urllib.parse.quote(name)) or {}
    hits = [dict(cik=int(h["_id"]), entity=h["_source"].get("entity", ""), tickers=h["_source"].get("tickers", ""),
                 rank=h["_source"].get("rank", 0)) for h in d.get("hits", {}).get("hits", [])]
    json.dump(hits, open(path, "w"))
    return hits


def sec_facts(cik, offline):
    """Return the annual revenue and profit-before-tax facts of one filer, extracted from its company facts and
    cached."""
    os.makedirs(os.path.join(SEC, "facts"), exist_ok=True)
    path = os.path.join(SEC, "facts", f"CIK{cik:010d}.json")
    if os.path.exists(path):
        return json.load(open(path))
    if offline:
        return None
    d = _fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json") or {}
    out = {"cik": cik, "entityName": d.get("entityName", ""), "revenue": [], "pbt": []}
    for key, tags in [("revenue", REV_TAGS), ("pbt", PBT_TAGS)]:
        for tax, tag in tags:
            for unit, facts in d.get("facts", {}).get(tax, {}).get(tag, {}).get("units", {}).items():
                for f in facts:
                    if f.get("form") not in ANNUAL_FORMS or not f.get("start") or not f.get("end"):
                        continue
                    days = (pd.Timestamp(f["end"]) - pd.Timestamp(f["start"])).days
                    if 330 <= days <= 400:
                        out[key].append(dict(tag=f"{tax}:{tag}", unit=unit, start=f["start"], end=f["end"],
                                             val=f["val"], accn=f.get("accn"), form=f.get("form"),
                                             filed=f.get("filed")))
    json.dump(out, open(path, "w"))
    return out


def sec_candidates(t, offline):
    """Return the candidate CIKs for each company_key. I take an exact name match to an SEC filer, or else use
    EDGAR's entity search (for US groups and for groups above SEARCH_MIN_REVENUE). There I take a listed hit whose
    name matches, whose ticker is the panel name (HPE, IBM) or whose name starts with the same word (Emerson
    Electric, Cisco Systems). The checks in main() reject a candidate whose size does not fit the report."""
    filers = sec_filer_names()
    by_name = {}
    for cik, n in filers.items():
        by_name.setdefault(norm(n), []).append(cik)
    grp = t.sort_values("year").groupby("company_key").agg(company=("company", "last"), hq=("hq", "last"),
                                                           T=("T", "max")).reset_index()
    cand = {}
    for r in grp.itertuples():
        keys = {norm(r.company_key), norm(r.company)} - {""}
        ciks = [c for k in keys for c in by_name.get(k, [])]
        if not ciks and (r.hq == "USA" or r.T >= SEARCH_MIN_REVENUE):
            first = {k.split()[0] for k in keys}
            for q in [r.company_key] + ([r.company] if norm(r.company) != norm(r.company_key) else []):
                hits = sorted(edgar_search(q, offline)[:8], key=lambda h: -(h["rank"] or 0))
                exact = [h["cik"] for h in hits if h["tickers"] and (norm(h["entity"]) in keys
                         or r.company_key.upper() in {x.strip().upper() for x in h["tickers"].split(",")})]
                loose = [h["cik"] for h in hits if h["tickers"] and norm(h["entity"]).split()[:1] and
                         norm(h["entity"]).split()[0] in first]
                ciks = exact or loose[:2]
                if ciks:
                    break
        if ciks:
            cand[r.company_key] = list(dict.fromkeys(ciks))[:3]
    return cand


def sec_rows(t, offline):
    rows = []
    for key, ciks in sec_candidates(t, offline).items():
        for cik in ciks:
            f = sec_facts(cik, offline)
            if not f:
                continue
            rev = pd.DataFrame(f["revenue"])
            if rev.empty:
                continue
            rev = rev.sort_values("filed").drop_duplicates(["end", "unit", "tag"], keep="last")
            rev = rev.loc[rev.groupby(["end", "unit"])["val"].idxmax()]          # the top line among the tags
            pbt = pd.DataFrame(f["pbt"])
            if len(pbt):
                pbt = pbt.sort_values("filed").drop_duplicates(["end", "unit"], keep="last").set_index(["end", "unit"])["val"]
            for x in rev.itertuples():
                rows.append(dict(company_key=key, year=year_label(x.start, x.end), source="sec_xbrl",
                                 source_detail=f"CIK {cik}, {x.form} accession {x.accn}, {x.tag}",
                                 url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={x.form}",
                                 currency=x.unit, revenue_lcu=float(x.val),
                                 pbt_lcu=float(pbt.get((x.end, x.unit), np.nan)) if len(pbt) else np.nan,
                                 employees=np.nan, fy_start=x.start, fy_end=x.end, name_in_source=f["entityName"]))
    return pd.DataFrame(rows)


# %% MARK: 5. Source 3: Compustat Global (listed non-US groups)
def compustat_rows(t):
    if not os.path.exists(COMPUSTAT):
        # The licensed WRDS extract is not part of the replication package.
        print(f"  [compustat] {os.path.relpath(COMPUSTAT, os.path.dirname(os.path.dirname(_HERE)))} not found: "
              "Compustat Global is licensed and not included, so this source is skipped. The published results used "
              "it; groups that only Compustat covers keep the revenues as reported.")
        return pd.DataFrame()
    cs = pd.read_parquet(COMPUSTAT, columns=["gvkey", "conm", "fyear", "datadate", "loc", "fic", "curcd", "revt",
                                             "pi", "emp"])
    cs = cs[(cs.fyear >= 2015) & cs.revt.notna()]
    names = cs.drop_duplicates("gvkey")[["gvkey", "conm", "loc", "fic"]].copy()
    names["n"] = names.conm.map(norm)
    grp = t.sort_values("year").groupby("company_key").agg(company=("company", "last"), hq=("hq", "last")).reset_index()
    pairs = []
    for r in grp[grp.hq != "USA"].itertuples():
        cand = names[(names["loc"] == r.hq) | (names["fic"] == r.hq)]
        keys = {norm(r.company_key), norm(r.company)} - {""}
        hit = cand[cand.n.isin(keys)]
        if hit.empty:                                    # else every word of the name must appear in the Compustat name
            toks = set(norm(r.company_key).split())
            hit = cand[cand.n.map(lambda x: bool(toks) and toks <= set(x.split())).astype(bool)]
        pairs += [(r.company_key, g) for g in hit.gvkey]
    if not pairs:
        return pd.DataFrame()
    m = pd.DataFrame(pairs, columns=["company_key", "gvkey"]).merge(cs, on="gvkey")
    return pd.DataFrame(dict(
        company_key=m.company_key, year=m.fyear.astype(int), source="compustat_global",
        source_detail="Compustat Global gvkey " + m.gvkey.astype(str) + " (" + m.conm + ")", url="",
        currency=m.curcd, revenue_lcu=m.revt * 1e6, pbt_lcu=m.pi * 1e6, employees=m.emp * 1e3,
        fy_start="", fy_end=m.datadate.astype(str), name_in_source=m.conm))


# %% MARK: 6. Checks and choice
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    t = report_totals()
    parts = [hand_collected(), sec_rows(t, a.offline), compustat_rows(t)]
    c = pd.concat([x for x in parts if len(x)], ignore_index=True)
    c["year"] = c["year"].astype(int)
    for col in ["revenue_lcu", "pbt_lcu", "employees"]:
        c[col] = pd.to_numeric(c[col], errors="coerce").astype(float)
    fx = np.array([fx_to_usd(cur, y) for cur, y in zip(c["currency"], c["year"])], dtype=float)
    c["revenue_usd"] = c["revenue_lcu"] / fx
    c["pbt_usd"] = c["pbt_lcu"] / fx
    c = c.merge(t[["company_key", "year", "company", "hq", "basis", "T", "E", "P"]], on=["company_key", "year"],
                how="inner")
    c["t_over_r"] = c["T"] / c["revenue_usd"].where(c["revenue_usd"] > 0)
    c["emp_ratio"] = c["E"] / c["employees"].where(c["employees"] > 0)
    c["pbt_ratio"] = c["P"] / c["pbt_usd"].where(c["pbt_usd"].abs() > 0)
    hand = (c.source == "annual_report").to_numpy()
    lo = np.where(hand, T_OVER_R_HAND[0], T_OVER_R[0])
    hi = np.where(hand, T_OVER_R_HAND[1], T_OVER_R[1])
    tr = c.t_over_r.to_numpy(dtype=float)
    rev_ok = np.isfinite(tr) & (tr >= lo) & (tr <= hi)
    emp_ok = c.emp_ratio.between(*EMP_RATIO).to_numpy()
    pbt_ok = c.pbt_ratio.between(*PBT_RATIO).to_numpy()
    size_ok = np.where(hand, True, np.where(c.employees.notna(), emp_ok, np.where(c.pbt_usd.notna(), pbt_ok, False)))
    fin = np.isfinite(c.revenue_usd.to_numpy(dtype=float))
    c["accepted"] = rev_ok & size_ok & fin
    c["reason"] = np.select([~fin, ~rev_ok & (tr < lo), ~rev_ok, ~size_ok],
                            ["no exchange rate", "report revenue below consolidated revenue (part of the group)",
                             "report revenue more than 4 times consolidated revenue (wrong match)",
                             "headcount / profit does not match the group"], "")
    c["_rank"] = c.source.map(SOURCE_RANK)
    c = c.sort_values(["company_key", "year", "accepted", "_rank"], ascending=[True, True, False, True])
    c["chosen"] = c.accepted & ~c.duplicated(["company_key", "year"])
    c = c.drop(columns="_rank")
    home_cols = ["home_lcu", "home_entity_basis", "home_label", "home_basis"]
    c.drop(columns=[x for x in home_cols if x in c.columns]).to_csv(OUT, index=False)

    # The home line's sales to customers, where the annual report discloses home-country revenue (chosen rows only).
    # A figure by location of the selling companies is the line's figure ("fixed"). A figure by customer location
    # or on an unstated basis is a lower bound ("floor"), since the group's companies at home make most of its sales
    # to customers at home.
    lines = [local_account_lines()]
    if "home_lcu" in c.columns:
        h = c[c.chosen & c.home_lcu.notna()].copy()
        h["third_party_revenue_usd"] = h["home_lcu"] / h["revenue_lcu"] * h["revenue_usd"]
        h["kind"] = np.where(h["home_entity_basis"].astype(bool), "fixed", "floor")
        # I take the country the figure is for from its label, because the SEC rows give the United States also for
        # groups with an Irish parent. Where the label names no country, I take the group's headquarters.
        h["iso_partner"] = [next((iso for pat, iso in _LABEL_ISO if re.search(pat, str(lab))), hq)
                            for lab, hq in zip(h["home_label"], h["hq"])]
        lines.append(h.rename(columns={"home_label": "doc_label", "home_basis": "doc_basis"}))
    cols = ["company_key", "year", "iso_partner", "third_party_revenue_usd", "kind", "doc_label", "doc_basis", "source_detail", "url"]
    L = pd.concat([x[cols] for x in lines if len(x)], ignore_index=True).drop_duplicates(
        ["company_key", "year", "iso_partner"], keep="first")              # local accounts take precedence over the annual report
    L.to_csv(LINES, index=False)
    print(f"  documented sales to customers of single lines: {len(L)} ({L.kind.value_counts().to_dict()}) -> {LINES}")
    coverage_log(c, t)


def local_account_lines():
    """Return the lines whose share of sales to customers is documented in local statutory accounts for the same
    fiscal year (data/raw/firm_level/local_accounts_2026-10/line_third_party_shares.csv), as a fixed figure for
    script 9."""
    if not os.path.exists(LOCAL):
        return pd.DataFrame()
    s = pd.read_csv(LOCAL)
    p = pd.read_csv(PANEL, low_memory=False, usecols=["company_key", "year", "iso_partner", "total_revenues"])
    s = s.merge(p.drop_duplicates(["company_key", "year", "iso_partner"]), on=["company_key", "year", "iso_partner"],
                how="inner")
    return pd.DataFrame(dict(company_key=s["company_key"], year=s["year"], iso_partner=s["iso_partner"],
                             third_party_revenue_usd=s["third_party_share"] * s["total_revenues"], kind="fixed",
                             doc_label="local accounts: " + s["counted"], doc_basis="excluded: " + s["excluded"],
                             source_detail=s["note"], url=s["url"]))


def coverage_log(c, t):
    """Print how many group-years with total revenues found a consolidated revenue (log only)."""
    ch = c[c.chosen]
    tot = t[t.basis == "total"]
    cov = tot.merge(ch[["company_key", "year"]], on=["company_key", "year"], how="left", indicator=True)
    cov["_c"] = cov["_merge"] == "both"
    print(f"[f1b] {len(c):,} candidate rows, {len(ch):,} group-years chosen "
          f"({ch.source.value_counts().to_dict()}) -> {OUT}")
    last = cov[cov.year == cov.groupby("company_key").year.transform("max")]
    print(f"  total-revenue group-years covered: {cov._c.sum():,} of {len(cov):,}; latest report per group: "
          f"{last._c.sum():,} of {len(last):,} ({last.loc[last._c, 'T'].sum() / last['T'].sum():.0%} of their summed revenue)")
    print("  summed ÷ consolidated revenue (chosen, latest): median "
          f"{ch[ch.year >= 2023].t_over_r.median():.2f}, p90 {ch[ch.year >= 2023].t_over_r.quantile(0.9):.2f}")


if __name__ == "__main__":
    main()
