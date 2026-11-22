# %%
"""
3_31 — Pull EITI company payments-to-government.

This script pulls the company-level payments to governments from the EITI Open Data API
(https://eiti.org/api/v2.0/revenue: paged, 25 records per page, about 246,000 records). I keep the records of type
== "company" and classify each payment as pre-profit (royalty-like), post-profit (CIT, equity) or general (dropped,
like VAT). The full /summary_data endpoint (about 663 country-fiscal-year reports, keyed on the alphanumeric report
id, e.g. AF2009) is paged once into a JSONL cache for cross-referencing downstream. Both endpoints are paged into
JSONL caches, so that a dropped run resumes from the highest page already written. On server (5xx) and network
errors I retry with exponential backoff and jitter (2**i + random.uniform(0, 1)), and I report gaps in the pages.
Each output row carries a country_year_source column: `direct` (the record carries its own summary_data.iso2 and
.year) or `summary_data` (recovered through the cache lookup).

Note for replicators: about US$540bn (18%) of EITI payment value cannot be assigned a country and year from the
public API. This is a limitation of the API, not of this script. The unassignable records split into about 93,000
"minimal-stub" records (no reference back to a parent report) and about 6,000 records whose
organisation.summary_data URL uses the organisation's numeric id. For these, /summary_data/<numeric id> returns an
empty list and filter[id] is silently ignored. I drop these records from the company-level leg. The lower-priority
legs of the 3_38 cascade (operator disclosures, then manual data, then GRD) cover the affected country-years
instead, so no payment value is missing from the country-level totals, only company-level detail and HQ
attribution.

Preferred source: the EITI database export (eiti-database.eiti.org, launched 2026-09-03) gives every payment a
country and fiscal year. When it is on disk, I build the output from it. For country-years the export lacks, I read
the FY2023 company tables from EITI reports (PDF extraction), and I use the API records only for country-years
covered by neither. The output schema is the same. `country_year_source` is eiti_database, eiti_report_pdf, direct
or summary_data. The commodity comes from the API organisation record of the same company where it exists,
otherwise from the text of the government entity, project or revenue stream, otherwise "unknown". `--api-only`
keeps the API-based output only (the database export is not used).

Section outline (numbers match the cell headings below):
1. Setup.
2. Classification tables.
   2.1 ISO2 → ISO3.
   2.2 Classification: GFS category → bucket (royalty_like / cit / equity / general / other).
   2.3 Commodity from organisation.commodities (the API's revenue-level `sector` is usually null).
3. Fetch and pagination.
   3.1 HTTP fetch with exponential backoff + jitter.
   3.2 Pagination → JSONL cache (revenue or summary_data).
4. Pull endpoints.
5. Process and write.
6. Main.

Extractive prep, stage 3_31 — after the 3_2x rent panel, before 3_32.

Reads:
  https://eiti.org/api/v2.0/revenue        — EITI company payment records (paged API)
  https://eiti.org/api/v2.0/summary_data   — parent-report metadata (paged API)

  data/raw/extractive/eiti_database_company_payments_2026-10-13.csv — EITI database export (preferred)
  data/raw/extractive/eiti_reports/_fy2023_pdf_extraction/*_company_payments.csv — FY2023 from reports
Writes:
  data/intermediate/extractive/eiti_summary_data_cache.jsonl   — parent-report cache (small)
  data/intermediate/extractive/eiti_revenue_company_raw.jsonl  — raw company records (re-process without re-pulling)
  data/intermediate/extractive/eiti_company_payments_long.csv  — one row per company payment, classified

Usage:
  python src/3_extractive_prep/3_31_pull_eiti_company_payments.py [options]
  --process-only          re-process from JSONL caches without re-hitting the API
  --no-resume             start the revenue pull from page 1 (overwrite)
  --refresh-summary-data  re-pull /summary_data even if the cache exists
  --api-only              build the output from the API records only

Author: Tax Justice Network.
Last updated: 2026-11-23.
"""
# %% MARK: 1. Setup
import csv
import json
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT, RAW

REVENUE_FIRST = "https://eiti.org/api/v2.0/revenue?page=1"
SUMMARY_FIRST = "https://eiti.org/api/v2.0/summary_data?page=1"
RAW_JSONL = EXT_INT / "eiti_revenue_company_raw.jsonl"
SUMMARY_JSONL = EXT_INT / "eiti_summary_data_cache.jsonl"
OUT_CSV = EXT_INT / "eiti_company_payments_long.csv"
DB_PAYMENTS = RAW / "extractive" / "eiti_database_company_payments_2026-10-13.csv"


# FY2023 report extraction: I convert the reports that state no exchange rate (PHL, TGO, TJK, TTO, UKR, KGZ, NER,
# ALB, CIV, DEU) at the World Bank official annual rate (PA.NUS.FCRF) of the fiscal year's end year. I leave KAZ
# FY2023 out, because its report contradicts itself (Tengizchevroil alone is above the all-company total).
PDF_EXCLUDE = {("KAZ", "2023")}


def _wb_fx():
    import csv as _csv
    path = RAW / "macro_variables" / "wb_fx_official_rate_2026-02.csv"
    lines = open(path, encoding="utf-8-sig").readlines()
    fx = {}
    for row in _csv.DictReader(lines[4:]):
        for k, v in row.items():
            if k and k.isdigit() and v:
                fx[(row["Country Code"], int(k))] = float(v)
    return fx
PDF_PAYMENTS_DIR = RAW / "extractive" / "eiti_reports" / "_fy2023_pdf_extraction"

# Regex to pull the numeric id out of `organisation.summary_data` URLs:
#   https://eiti.org/api/v2.0/summary_data/208835  →  "208835"
_SUMMARY_ID_RE = re.compile(r"/summary_data/(\d+)/?$")


# %% MARK: 2. Classification tables
# %% MARK: 2.1 ISO2 → ISO3
try:
    import pycountry
    def to_iso3(iso2):
        if not iso2:
            return ""
        iso2 = str(iso2).strip().upper()
        if len(iso2) == 3:
            return iso2
        c = pycountry.countries.get(alpha_2=iso2)
        return c.alpha_3 if c else ""
except ImportError:
    _I = {"AF": "AFG", "AL": "ALB", "AO": "AGO", "AR": "ARG", "AM": "ARM", "AZ": "AZE",
          "BF": "BFA", "BH": "BHR", "BO": "BOL", "BR": "BRA", "CD": "COD", "CF": "CAF",
          "CG": "COG", "CI": "CIV", "CL": "CHL", "CM": "CMR", "CO": "COL", "DE": "DEU",
          "DO": "DOM", "EC": "ECU", "ET": "ETH", "GA": "GAB", "GB": "GBR", "GH": "GHA",
          "GN": "GIN", "GT": "GTM", "GY": "GUY", "HN": "HND", "ID": "IDN", "IQ": "IRQ",
          "KE": "KEN", "KG": "KGZ", "KZ": "KAZ", "LB": "LBN", "LR": "LBR", "MD": "MDA",
          "MG": "MDG", "ML": "MLI", "MM": "MMR", "MN": "MNG", "MR": "MRT", "MW": "MWI",
          "MX": "MEX", "MZ": "MOZ", "NE": "NER", "NG": "NGA", "NL": "NLD", "NO": "NOR",
          "PE": "PER", "PG": "PNG", "PH": "PHL", "SB": "SLB", "SC": "SYC", "SL": "SLE",
          "SN": "SEN", "SR": "SUR", "ST": "STP", "TD": "TCD", "TG": "TGO", "TJ": "TJK",
          "TL": "TLS", "TT": "TTO", "TZ": "TZA", "UA": "UKR", "UG": "UGA", "US": "USA",
          "YE": "YEM", "ZM": "ZMB"}
    def to_iso3(iso2):
        return _I.get(str(iso2).strip().upper(), str(iso2).strip().upper() if len(str(iso2 or "")) == 3 else "")


# %% MARK: 2.2 Classification: GFS category → bucket (royalty_like / cit / equity / general / other)
# `gfs.label` is one of about 30 standardised strings, so I map them directly. I drop the general bucket
# (economy-wide taxes, not peculiar to extractives and not profit-sharing).
GFS_LABEL_TO_BUCKET = {
    # profit-sharing: kept (needed for the CbCR correction)
    "Ordinary taxes on income, profits and capital gains": "cit",
    "Extraordinary taxes on income, profits and capital gains": "cit",
    # state equity, state participation and production shares: kept (post-profit)
    "From government participation (equity)": "equity",
    "Dividends": "equity",
    "From state-owned enterprises": "equity",
    "Delivered/paid to state-owned enterprise(s)": "equity",
    "Withdrawals from income of quasi-corporations": "equity",
    "Profits of natural resource export monopolies": "equity",
    "Sales of state's share of production or other revenue collected in kind": "equity",
    # resource-specific, not profit-based: kept (pre-profit, the base of the resource correction)
    "Royalties": "royalty_like",
    "Bonuses": "royalty_like",
    "Licence fees": "royalty_like",
    "Other taxes payable by natural resource companies": "royalty_like",
    "Other rent payments": "royalty_like",
    "Compulsory transfers to government (infrastructure and other)": "royalty_like",
    # Production entitlements are the state's share of production (its profit that is still inside the extractive
    # company's reported profit), so I classify them as equity.
    "Production entitlements (in-kind or cash)": "equity",
    "Production entitlement": "equity",
    "Delivered/paid directly to government": "royalty_like",
    "Rent": "royalty_like",
    "Administrative fees for government services": "royalty_like",
    "Mandatory social expenditures": "royalty_like",
    "Infrastructure provisions and barter arrangements": "royalty_like",
    # general, economy-wide: dropped
    "General taxes on goods and services (VAT, sales tax, turnover tax)": "general",
    "Customs and other import duties": "general",
    "Taxes on exports": "general",
    "Excise taxes": "general",
    "Taxes on property": "general",
    "Taxes on payroll and workforce": "general",
    "Social security employer contributions": "general",
    "Social security employee contributions": "general",
    "Social security contributions": "general",
    "Fines, penalties, and forfeits": "general",
    "Emission and pollution taxes": "general",
    "Motor vehicle taxes": "general",
    "Sales of goods and services by government units": "general",
    "Voluntary transfers to government (donations)": "general",
    "Interest": "general",
    "Stamp taxes": "general",
    "Other taxes": "general",
}
# Keyword fallback when gfs.label is missing or unknown. I check the buckets in this order.
_KW = [
    ("general", ("value added tax", "vat", "(tva)", "gst", "customs", "import dut", "douane", "excise",
                 "accise", "payroll", "social security", "social contribution", "personal income tax",
                 "pay as you earn", "(paye)", "property tax", "motor vehicle", "stamp dut", "fines", "penalt",
                 "amende", "co2 tax", "carbon tax", "emission tax", "pollution tax", "salaire", "sales tax",
                 "turnover tax", "registration fee", "trade tax",
                 # French: personal income tax & social contributions (excluded, not CIT)
                 "personnes physiques", "revenu des personnes", "irpp", "(its)", "assurance",
                 "cotisation", "timbre", "enregistrement")),
    ("cit", ("income, profits and capital", "income tax", "corporate tax", "corporation tax", "company tax",
             "profits tax", "profit tax", "petroleum profits tax", "supplemental petroleum tax", "windfall",
             "additional profit", "solidarity contribution", "impuesto a las ganancias",
             # French income- and profit-tax GFS labels and stream names (kept in sync with 3_13)
             "benefice", "impot sur les societe", "impots sur les societe", "sur les societe",
             "bic", "impot sur le revenu des societe")),
    ("equity", ("dividend", "government participation", "state participation", "state-owned enterprise",
                "produced petroleum sold", "crude oil export sales", "profit oil", "share of profit",
                "production entitlement", "carried interest", "winstaandeel", "sdfi",
                "concessionary sale", "concession fee", "state's share",
                # French: participation de l'État / part de production / vente de la part de l'État
                "participation de l", "part de production", "part de l'etat", "part de l’etat",
                "part de l'état", "part de l’état", "vente de la part", "revenus de la propriete",
                "revenus de la propriété",
                # The state's production share sold by the national oil company (empty GFS label, English names
                # spelled out): Nigeria's federation crude, Norway's SDFI, Indonesia's PSC lifting and Iraq's state
                # oil exports. All of them are the state's share of production.
                "direct financial interest", "federation crude", "sales of federation",
                "government lifting", "oil products export")),
    ("royalty_like", ("royalt", "redevance", "regalia", "bonus", "licence", "license", "permis", "permit",
                      "surface", "superficiaire", "rent", "loyers", "infrastructure", "training fund",
                      "redevance miniere", "ad valorem", "extraction tax", "severance", "exploration",
                      "exploitation", "administrative fee", "data fee",
                      # French: droits fixes / taxe d'extraction / patente miniere
                      "droits fixes", "droit fixe", "taxe d'extraction", "patente")),
]


def _strip_accents(s):
    """Folds accents so that unaccented keywords match accented labels ('Impôt sur les sociétés' becomes
    'impot sur les societes'). Kept in sync with 3_13."""
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def classify(gfs_label, fallback_text=""):
    b = GFS_LABEL_TO_BUCKET.get((gfs_label or "").strip())
    if b:
        return b
    t = " " + _strip_accents((str(gfs_label or "") + " " + str(fallback_text or ""))) + " "
    for bucket, kws in _KW:
        if any(_strip_accents(k) in t for k in kws):
            return bucket
    # A generic top-level "Taxes (11E)" label with no finer match: for extractives the dominant tax is the income or
    # profit tax, so I classify it as post-profit rather than dropping it.
    if "taxes (11" in t or " 11e " in t:
        return "cit"
    return "other"


# %% MARK: 2.3 Commodity from organisation.commodities (the API's revenue-level `sector` is usually null)
OIL_GAS_C = {"crude oil", "oil", "petroleum", "natural gas", "gas", "condensate", "lng", "ngl",
             "shale gas", "shale oil", "coal bed methane", "coalbed methane", "hydrocarbons", "petrole", "gaz"}
COAL_C = {"coal", "lignite", "anthracite", "thermal coal", "coking coal", "charbon"}
MIN_NONEXTRACTIVE = {"forestry", "timber", "wood", "agriculture", "fisheries", "fishing", "water"}


def commodity_of(org_commodities, sector):
    cs = [str(c).strip().lower() for c in (org_commodities or []) if c]
    if sector:
        s = str(sector).strip().lower()
        if any(k in s for k in ("oil", "gas", "petrol", "hydrocarb")):
            return "oil_gas"
        if "coal" in s or "charbon" in s:
            return "coal"
        if any(k in s for k in ("mining", "mineral", "minier", "metal")):
            return "minerals"
    if any(c in COAL_C for c in cs) and not any(c in OIL_GAS_C for c in cs):
        return "coal"
    if any(c in OIL_GAS_C or any(k in c for k in OIL_GAS_C) for c in cs):
        return "oil_gas"
    if any(c in MIN_NONEXTRACTIVE for c in cs):
        return "other"
    if cs:
        return "minerals"
    return "unknown"


# %% MARK: 3. Fetch and pagination
# %% MARK: 3.1 HTTP fetch with exponential backoff + jitter
def fetch(url, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"Accept": "application/json", "User-Agent": "tjn-research/1.0"},
            )
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                ConnectionError, json.JSONDecodeError) as e:
            if i == tries - 1:
                raise
            sleep = min(60, (2 ** i) + random.uniform(0, 1))
            print(f"  [warn] fetch {url} retry {i+1}/{tries-1} after {e!s}; sleeping {sleep:.1f}s")
            time.sleep(sleep)
    return None


# %% MARK: 3.2 Pagination → JSONL cache (revenue or summary_data)
def _last_page_in_cache(jsonl_path):
    """Return the highest `_page` value already written to the cache, or 0."""
    if not jsonl_path.exists() or jsonl_path.stat().st_size == 0:
        return 0
    last = 0
    seen = set()
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            try:
                p = json.loads(line).get("_page", 0)
                last = max(last, p)
                seen.add(p)
            except Exception:
                pass
    if last and len(seen) < last:
        missing = sorted(set(range(1, last + 1)) - seen)
        print(f"  [warn] cache has gaps: {len(missing)} missing pages, e.g. {missing[:5]}...")
    return last


def pull_paginated(first_url, jsonl_path, *, keep=None, resume=True, label=""):
    """Walks a paged JSON:API endpoint and appends each retained record to the JSONL cache.

    `keep` is a predicate applied to each record (e.g. type == 'company'). If it is None, I keep every record in
    `data`.

    I resume from `_page = last + 1` if the cache exists and `resume=True`.
    """
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    start_page = 1
    mode = "w"
    if resume:
        last = _last_page_in_cache(jsonl_path)
        if last:
            start_page, mode = last + 1, "a"
            print(f"[{label}] resuming from page {start_page} (cache has up to page {last}).")
    url = re.sub(r"page=\d+", f"page={start_page}", first_url)
    n_pages = n_kept = 0
    with open(jsonl_path, mode, encoding="utf-8") as out:
        page = start_page
        while url:
            d = fetch(url)
            for rec in d.get("data", []):
                if keep is None or keep(rec):
                    rec["_page"] = page
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n_kept += 1
            n_pages += 1
            nxt = d.get("next") or d.get("links", {}).get("next")
            url = (nxt.get("href") if isinstance(nxt, dict) else nxt) if nxt else None
            page += 1
            if n_pages % 100 == 0:
                out.flush()
                print(f"  [{label}] ...{n_pages} pages, {n_kept:,} records kept (next page {page})")
    print(f"[{label}] pull done: {n_pages} pages this run, {n_kept:,} records written → {jsonl_path}")


# %% MARK: 4. Pull endpoints
def pull_summary_data(refresh=False):
    """Pulls /summary_data into eiti_summary_data_cache.jsonl. The endpoint is small (a few hundred records), so
    this is usually a one-time pull."""
    if not refresh and SUMMARY_JSONL.exists() and SUMMARY_JSONL.stat().st_size > 0:
        n = sum(1 for _ in open(SUMMARY_JSONL, encoding="utf-8"))
        print(f"[summary_data] cache exists ({n:,} records); skip (use --refresh-summary-data to re-pull)")
        return
    pull_paginated(SUMMARY_FIRST, SUMMARY_JSONL, keep=None, resume=False, label="summary_data")


def build_summary_id_map():
    """Reads SUMMARY_JSONL into a dict {summary_id_str: (iso3, year)}.

    I derive the year from the report `label` (e.g. "Afghanistan: 2009") or from `year_end` (e.g. "2009-03-20"
    gives 2009). iso3 comes from `country.iso3`."""
    out = {}
    if not SUMMARY_JSONL.exists():
        return out
    with open(SUMMARY_JSONL, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            sid = str(r.get("id") or "")
            if not sid:
                continue
            iso3 = (r.get("country.iso3") or "").strip().upper()
            if not iso3:
                iso2 = (r.get("country.iso2") or "").strip().upper()
                if iso2:
                    iso3 = to_iso3(iso2)
            # I prefer the year embedded in the report's label and fall back to year_end.
            yr = None
            lbl = str(r.get("label") or "")
            m = re.search(r"\b(19|20)\d{2}\b", lbl)
            if m:
                yr = int(m.group(0))
            else:
                ye = str(r.get("year_end") or r.get("year_start") or "")
                if ye[:4].isdigit():
                    yr = int(ye[:4])
            if iso3 and yr:
                out[sid] = (iso3, yr)
    return out


def pull_revenue(resume=True):
    pull_paginated(
        REVENUE_FIRST, RAW_JSONL,
        keep=lambda rec: (rec.get("type") or "").lower() == "company",
        resume=resume, label="revenue",
    )


# %% MARK: 5. Process and write
# ---- processing: classify + backfill country/year from summary_data ----
def process():
    """Reads RAW_JSONL, classifies each record, backfills (iso3, year) through summary_data and writes OUT_CSV.

    I drop the `general` bucket and the rows still missing iso3 or year after the backfill.
    """
    summary_map = build_summary_id_map()
    print(f"[process] summary_data map has {len(summary_map):,} entries")

    src_counts = {"direct": 0, "summary_data": 0, "missing": 0}
    rows = []
    dropped_general = dropped_noyear = 0

    with open(RAW_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)

            iso3 = to_iso3(r.get("summary_data.iso2"))
            yr = r.get("summary_data.year")
            try:
                yr = int(str(yr)[:4]) if yr else None
            except ValueError:
                yr = None
            source = "direct" if iso3 and yr else None

            if not (iso3 and yr):
                ref = r.get("organisation.summary_data") or ""
                m = _SUMMARY_ID_RE.search(str(ref))
                if m:
                    hit = summary_map.get(m.group(1))
                    if hit:
                        iso3, yr = hit
                        source = "summary_data"

            if not (iso3 and yr):
                source = "missing"
                src_counts[source] += 1
                dropped_noyear += 1
                continue
            src_counts[source] += 1

            org_comms = []
            for k in sorted(k for k in r if k.startswith("organisation.commodities.")):
                v = r.get(k)
                if v:
                    org_comms.append(v)
            gfs_label = r.get("gfs.label") or ""
            comm = commodity_of(org_comms, r.get("sector"))
            bucket = classify(
                gfs_label,
                " ".join([str(r.get("label") or ""), str(r.get("project_name") or ""), str(r.get("comments") or "")]),
            )
            if bucket == "general":
                dropped_general += 1
                continue
            val = r.get("revenue")
            try:
                val = float(val) if val not in (None, "") else None
            except (TypeError, ValueError):
                val = None
            ink_vol = r.get("in_kind_volume")
            try:
                ink_vol = float(ink_vol) if ink_vol not in (None, "") else None
            except (TypeError, ValueError):
                ink_vol = None
            if val is None and ink_vol is None:
                continue
            comp = (r.get("organisation.label") or "").strip()
            if not comp or len(comp) < 2:
                continue
            rows.append({
                "iso3": iso3, "year": yr,
                "country_year_source": source,
                "commodity": comm,
                "company_name": comp,
                "org_id": r.get("organisation.id") or "",
                "org_identification": r.get("organisation.identification") or "",
                "org_commodities": "; ".join(str(c) for c in org_comms),
                "org_company_type": r.get("organisation.company_type") or "",
                "org_stock_exchange": r.get("organisation.stock_exchange_listing") or "",
                "government_entity": (r.get("goverment_entity") or "").strip(),
                "sector": (r.get("sector") or "").strip(),
                "gfs_code": r.get("gfs.code") or "",
                "gfs_label": gfs_label.strip(),
                "revenue_type": bucket,                                  # royalty_like / cit / equity / other
                "value_usd": "" if val is None else f"{val:.2f}",
                "payment_in_kind": "Y" if str(r.get("payment_made_in_kind") or "").strip().lower() in ("yes", "y", "true", "1") else "",
                "in_kind_volume": "" if ink_vol is None else f"{ink_vol:.4f}",
                "in_kind_unit": (r.get("unit") or "").strip(),
                "project_name": (r.get("project_name") or "").strip(),
                "revenue_stream_label": (r.get("label") or "").strip(),
                "comments": (r.get("comments") or "").strip()[:200],
            })

    cols = [
        "iso3", "year", "country_year_source",
        "commodity", "company_name", "org_id", "org_identification", "org_commodities",
        "org_company_type", "org_stock_exchange", "government_entity", "sector", "gfs_code", "gfs_label",
        "revenue_type", "value_usd", "payment_in_kind", "in_kind_volume", "in_kind_unit",
        "project_name", "revenue_stream_label", "comments",
    ]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Report
    import collections
    by_iso = collections.Counter(r["iso3"] for r in rows)
    by_yr = collections.Counter(r["year"] for r in rows)
    by_rt = collections.Counter(r["revenue_type"] for r in rows)
    by_cm = collections.Counter(r["commodity"] for r in rows)
    by_src = collections.Counter(r["country_year_source"] for r in rows)
    val = sum(float(r["value_usd"]) for r in rows if r["value_usd"])
    val_by_src = collections.defaultdict(float)
    for r in rows:
        if r["value_usd"]:
            val_by_src[r["country_year_source"]] += float(r["value_usd"])

    print(f"\nWrote {OUT_CSV}: {len(rows):,} company-payment rows; total ${val/1e9:,.1f} B")
    print(f"  dropped: {dropped_general:,} general/economy-wide; {dropped_noyear:,} missing iso/year (still unrecoverable)")
    print(f"  country_year_source: {dict(by_src)}")
    for s, v in sorted(val_by_src.items(), key=lambda x: -x[1]):
        print(f"    {s:<14} ${v/1e9:,.1f} B")
    print(f"  countries: {len(by_iso)}  {dict(sorted(by_iso.items()))}")
    print(f"  years: {dict(sorted(by_yr.items()))}")
    print(f"  revenue_type: {dict(by_rt)}  |  commodity: {dict(by_cm)}")


def process_database():
    """Rebuilds OUT_CSV from the EITI database export and the FY2023 report extraction. I keep the API-based rows
    (written by process()) only for country-years covered by neither."""
    import pandas as pd
    norm = lambda x: re.sub(r"[^a-z0-9]", "", _strip_accents(str(x or "")).lower())
    # Commodity per (iso3, company) from the API organisation records
    api_comm = {}
    if RAW_JSONL.exists():
        with open(RAW_JSONL, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                comp = norm(r.get("organisation.label"))
                iso3 = to_iso3(r.get("summary_data.iso2"))
                oc = [r.get(k) for k in sorted(k for k in r if k.startswith("organisation.commodities.")) if r.get(k)]
                c = commodity_of(oc, r.get("sector"))
                if comp and c != "unknown":
                    api_comm.setdefault((iso3, comp), c)
                    api_comm.setdefault((None, comp), c)

    def frame(path, tag):
        d = pd.read_csv(path, low_memory=False, dtype=str)
        d["_source"] = tag
        return d
    db = frame(DB_PAYMENTS, "eiti_database")
    pdfs = [frame(fp, "eiti_report_pdf") for fp in sorted(PDF_PAYMENTS_DIR.glob("*_company_payments.csv"))] \
        if PDF_PAYMENTS_DIR.exists() else []
    have = set(zip(db["country_iso3"], db["year"].astype(str)))
    pdf = pd.concat(pdfs, ignore_index=True) if pdfs else db.iloc[0:0]
    pdf = pdf[[(i, str(y)) not in have for i, y in zip(pdf["country_iso3"], pdf["year"])]]
    pdf = pdf[[(i, str(y)) not in PDF_EXCLUDE for i, y in zip(pdf["country_iso3"], pdf["year"])]]
    if len(pdf):                              # no rate in the report: World Bank annual rate
        _fx = _wb_fx()
        miss = pdf["payment_value_usd"].fillna("").astype(str).str.strip().eq("") & pdf["payment_value"].notna()
        cur = pdf["reporting_currency"].fillna(pdf.get("currency_code", "")).astype(str).str.upper()
        rate = [1.0 if c == "USD" else _fx.get((i, int(float(y)))) for c, i, y in zip(cur, pdf["country_iso3"], pdf["year"])]
        conv = pd.to_numeric(pdf["payment_value"], errors="coerce") / pd.Series(rate, index=pdf.index, dtype=float)
        pdf.loc[miss, "payment_value_usd"] = conv[miss].map(lambda v: "" if pd.isna(v) else f"{v:.6f}")
        pdf.loc[miss & conv.notna(), "_source"] = "eiti_report_pdf_wbfx"
    new = pd.concat([db, pdf], ignore_index=True)
    have |= set(zip(pdf["country_iso3"], pdf["year"].astype(str)))

    rows, dropped_general = [], 0
    _s = lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()
    for r in new.to_dict("records"):
        comp = _s(r.get("company_name"))
        val = pd.to_numeric(r.get("payment_value_usd"), errors="coerce")
        if not comp or len(comp) < 2 or pd.isna(val):
            continue
        gfs_label = _s(r.get("gfs_name"))
        text = " ".join(_s(r.get(k)) for k in ("revenue_stream_name", "project_name"))
        bucket = classify(gfs_label, text)
        if bucket == "general":
            dropped_general += 1
            continue
        iso3 = r["country_iso3"]
        comm = (api_comm.get((iso3, norm(comp))) or api_comm.get((None, norm(comp)))
                or commodity_of([], " ".join(_s(r.get(k)) for k in ("gov_entity_name", "project_name", "revenue_stream_name"))))
        rows.append({
            "iso3": iso3, "year": int(float(r["year"])), "country_year_source": r["_source"],
            "commodity": comm, "company_name": comp, "org_id": _s(r.get("eiti_id_company")),
            "org_identification": _s(r.get("legal_entity_id")), "org_commodities": "",
            "org_company_type": _s(r.get("company_type")), "org_stock_exchange": "",
            "government_entity": _s(r.get("gov_entity_name")), "sector": "",
            "gfs_code": _s(r.get("gfs_code")), "gfs_label": gfs_label, "revenue_type": bucket,
            "value_usd": f"{val:.2f}",
            "payment_in_kind": "Y" if _s(r.get("payment_in_kind")).lower() in ("1", "yes", "y", "true") else "",
            "in_kind_volume": "", "in_kind_unit": "", "project_name": _s(r.get("project_name")),
            "revenue_stream_label": _s(r.get("revenue_stream_name")),
            "comments": "", "company_hq_country_iso3": r.get("company_hq_country_iso3") or "",
        })
    old = pd.read_csv(OUT_CSV, dtype=str, keep_default_na=False) if OUT_CSV.exists() else pd.DataFrame()
    if len(old):
        old = old[[(i, str(y)) not in have for i, y in zip(old["iso3"], old["year"])]]
    out = pd.concat([pd.DataFrame(rows), old], ignore_index=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"\n[database] wrote {OUT_CSV}: {len(out):,} rows "
          f"(database / report {len(rows):,}, API kept {len(old):,}); dropped {dropped_general:,} general")
    print("  by source:", out.groupby("country_year_source")["value_usd"].apply(
        lambda s: round(pd.to_numeric(s, errors="coerce").sum() / 1e9, 1)).to_dict(), "US$bn")
    print("  commodity:", out["commodity"].value_counts().to_dict())


# %% MARK: 6. Main
def main():
    args = set(sys.argv[1:])
    if "--process-only" not in args:
        pull_summary_data(refresh="--refresh-summary-data" in args)
        pull_revenue(resume="--no-resume" not in args)
    process()
    if DB_PAYMENTS.exists() and "--api-only" not in args:
        process_database()


if __name__ == "__main__":
    main()
