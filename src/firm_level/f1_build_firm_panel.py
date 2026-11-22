# %%
"""
f1 — Build the firm-level public CbCR panel.

This script builds one panel from every public country-by-country report (CbCR) of individual groups that I hold.
It uses the variable names of the OECD CbCR data that the aggregate pipeline uses, so that the same
formulary-apportionment machinery can run group by group (script 9). The panel has one row per (company, fiscal
year, jurisdiction). I convert monetary values to nominal US dollars at the World Bank period-average exchange rate
of the report currency.

The sources (data/raw/firm_level/, with the Irish registry filings downloaded on 2026-10-01) are listed below in
the priority order of the deduplication. For a (company, year) present in several sources, the report of the
highest-priority source wins as a whole. There is one exception: an Irish registry filing wins only when it names
at least as many jurisdictions as the best other source for that group-year (the same applies to the tracker
database, 2b).
  1. tjn_pcbcr      The Tax Justice Network's (TJN) own extractions of EU public CbCRs and of reports under the
                    tax standard of the Global Reporting Initiative (GRI 207). There is one JSON file per company
                    and fiscal year (<slug>/fy<year>.json), for 18 groups and FY2013–2025, in the reporting
                    currency of each report.
  2. cro_ireland    Public CbCRs filed with the Irish Companies Registration Office (document library, reporting
                    year 2025). I parse the inline-XBRL filings from their tags and transcribe the four PDFs and
                    the one untagged XHTML file from their tables. The values are in the report currency, and
                    revenue is total revenue only. The source includes the Apple and Microsoft FY2025 filings.
  2b. tjn_tracker_db TJN's tracker database of public CbCRs (pCbCR tracker), with the confirmed current version
                    of every report (the newest tjn_tracker_db_<date>.csv export). Many of the reports are
                    FY2024–25 filings under the EU directive, in the report currency and scale. Like the Irish
                    filings, it wins only where it names at least as many jurisdictions as the best other source.
  3. taxplorer      The full Taxplorer database of the EU Tax Observatory (taxplorer.eu/data.json v2026-10-17,
                    retrieved 2026-10-21), with 1,387 groups for 2014–2026, 1,011 of them for FY2025, in EUR.
  4. tjn_pdf        TJN's extractions from the PDF tax reports of 13 energy and extractive groups (with a unit
                    column per row).
  5. pcbcr_database Company-website PDFs digitised for the pCbCR tracker (107 groups, mostly FY2024–25, in EUR),
                    the rows with source 'company_website' of pcbcr_database_unified_2026-08.csv.
  6. euto_banks     The EU Tax Observatory's CbCRs of banks under Article 89 of the Capital Requirements Directive
                    (CRD IV), 2014–2020, as unified by the pCbCR tracker (36 banks, in EUR), the rows with source
                    'tax_observatory_banks' of the same file. They are not included in the package, as the
                    source's terms do not allow redistribution. Without them, the panel lacks these bank reports
                    of 2014–2020.

Jurisdictions are ISO3 codes. I keep a report's residual "Other" line as the pseudo-jurisdiction OTHER. It holds
real activity that must stay in the group's apportionment pool, but it cannot be attributed to a country.

Headquarters country. Seven groups carry two different headquarters (HQ) countries across years in the sources.
For Shell, Ferrovial and Nordea this is a real move, and for Aegon, Rio Tinto, CK Hutchison and Insud Pharma a
label change in Taxplorer. The curated file firm_hq_overrides.csv sets their HQ by year range, following the rule
that the HQ is the ultimate parent's headquarters at the end of the fiscal year. A group with several HQs that is
not in the file takes the HQ of its latest year, and I print it.

Two rules work on whole reports. I drop a report whose figures cannot be right and whose original could not be
checked (DROP_REPORTS). I give a sector to the groups that no source assigns to one (SECTOR_FILL), so that the
estimates without financial and extractive groups leave them out. I take one-off capital gains that a
report books as profit and revenue off their lines (ONE_OFF_GAINS).

Section outline (numbers match the cell headings below):
1. Setup.
2. Helpers — names, countries, FX.
3. Source loaders (each returns the unified schema, values in the original currency).
4. Build.

Firm-level data preparation, step f1 — before f1b and script 9.

Reads:
  data/raw/firm_level/…                              — the sources above
  data/raw/firm_level/firm_hq_overrides.csv          — curated HQ per group and year range
                                                       (company_key, hq_iso3, year_start, year_end, note, where
                                                       blank year bounds mean all years)
  data/raw/macro_variables/wb_fx_official_rate_*.csv — World Bank exchange rates, local currency units per US$
                                                       (the EMU row for the euro)
  data/raw/macro_variables/ecb_exr_annual_avg_*.csv  — annual averages of the European Central Bank (ECB, per
                                                       euro) for the years the World Bank file lacks
Writes:
  data/intermediate/firm_level/firm_cbcr_panel.csv   — the unified panel (all sources, deduplicated)
  data/intermediate/firm_level/firm_year_meta.csv    — one row per (company, year): source, HQ, sector,
                                                       currency, number of jurisdictions, OTHER share of revenue
Usage:
  python src/firm_level/f1_build_firm_panel.py

Author: Tax Justice Network.
Created: 2026-09-22.  Last updated: 2026-11-23.
"""
# %% MARK: 1. Setup
import glob
import json
import os
import re
import sys
import unicodedata

import numpy as np
import pandas as pd
import pycountry

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
from config import data_raw, data_intermediate, exchange_rates_wb, exchange_rates_ecb  # noqa: E402

RAW = os.path.join(data_raw, "firm_level")
OUT_DIR = os.path.join(data_intermediate, "firm_level")
os.makedirs(OUT_DIR, exist_ok=True)

SOURCE_PRIORITY = ["tjn_pcbcr", "cro_ireland", "tjn_tracker_db", "taxplorer", "tjn_pdf", "pcbcr_database", "euto_banks"]
# Sources whose filings often show only part of the group (the lines the EU directive requires and one aggregate).
# They outrank lower-priority sources only where they name at least as many jurisdictions as the best of them.
THIN_RISK_SOURCES = ["cro_ireland", "tjn_tracker_db"]
# I read the newest dated export of TJN's pCbCR tracker (confirmed reports).
TRACKER_FILE = os.path.basename(sorted(glob.glob(os.path.join(RAW, "tjn_tracker_db_*.csv")))[-1])
# The tracker has no sector field. These are groups that no other source classifies and that are clearly financial
# (Taxplorer's label). I need them so that the estimates without financial groups leave them out.
TRACKER_SECTOR = {k: "Banking, Insurance & Financial Services" for k in
                  ["CIGNA", "EVEREST", "DEUTSCHE SPARKASSEN LEASING", "LONDON STOCK EXCHANGE",
                   "RAYMOND JAMES FINANCIAL SUBSIDIARIES", "S KREDITPARTNER",
                   # banks without a sector in any source
                   "OCBC OVERSEA CHINESE BANKING OCBC", "DEMIR HALK BANK NEDERLAND"]}
# I replace sector labels that a source got wrong outright. Colt Technology Services is a telecoms group, but
# Taxplorer files it under finance.
SECTOR_OVERRIDES = {"COLT": "Communications"}
# Groups that no source assigns to a sector (banks and an oil and gas producer). Without a sector, the estimates
# that leave out financial and extractive groups would keep them. Crédit Agricole and UniCredit take their sector
# from the EU Tax Observatory's bank reports where that source is present. That source is not included in the
# package, so I list them here as well, with the same label, so that the panel is the same either way.
SECTOR_FILL = {"BNP PARIBAS": "Banking", "OVERSEA CHINESE BANKING OCBC": "Banking", "VERMILION ENERGY": "Oil & Gas",
               "CREDIT AGRICOLE": "Banking", "UNICREDIT": "Banking"}
# I drop reports whose figures cannot be right and whose original could not be checked. In the FY2025 report of
# Grupo ADO (Taxplorer), the 'Other jurisdictions' line shows a profit of €8.05bn on revenue of €2.29bn (accrued
# tax €1.76bn), and the original report could not be obtained.
DROP_REPORTS = {("taxplorer", "ADO", 2025)}
# One-off capital gains that a line books as profit and, as the report's notes say, as revenue ("revenues include
# extraordinary income and financial income"). I take them off the line's profit before tax and its unrelated-party
# and total revenues, in the report currency. Prysmian's Dutch line of 2025 carries the gain of its holding company
# Draka Comteq B.V. on selling its 23.73% stake in YOFC (consolidated gain €354m, Integrated Annual Report 2025,
# printed p. 326 and the tax reconciliation on p. 465). The group states that the stand-alone gain was €538m, because
# the Dutch accounts carried the stake at its 2011 cost. The Dutch line's profit rose by €520m and its unrelated-party
# revenue by €532m from 2024 to 2025, which matches. Without the gain, the line books €75m (€93m in 2024).
ONE_OFF_GAINS = {("PRYSMIAN", 2025, "NLD"): ("EUR", 538e6)}

VALUE_COLS = [
    "total_revenues", "unrelated_party_revenues", "related_party_revenues",
    "profit_loss_before_income_tax", "income_tax_paid_on_cash_basis",
    "income_tax_accrued_current_year", "tangible_assets_except_cash",
    "stated_capital", "accumulated_earnings",
]
OUT_COLS = (["source", "source_detail", "company", "company_key", "hq_iso3", "sector",
             "year", "iso_partner", "jurisdiction_name", "n_employees"]
            + VALUE_COLS + ["currency", "fx_lcu_per_usd", "disclosure_quality", "tax_sign_flipped"])

# %% MARK: 2. Helpers — names, countries, FX
_LEGAL = {"PLC", "P.L.C.", "PLC.", "SA", "S.A.", "SE", "AG", "NV", "N.V.", "SPA", "S.P.A.", "S.P.A",
          "LTD", "LTD.", "LIMITED", "INC", "INC.", "CORP", "CORP.", "CORPORATION", "GROUP", "GRUPO",
          "HOLDINGS", "HOLDING", "CO", "CO.", "COMPANY", "GMBH", "AB", "ASA", "AS", "A/S", "OYJ", "OY",
          "SAU", "S.A.U.", "SRL", "S.R.L.", "LLC", "THE", "AND", "&", "KGAA", "SCA", "BV", "B.V.",
          "PUBLIC", "N.V", "S.A", "P.L.C", "LIMITED.", "UK", "PTY",
          # legal forms that appear in the tracker source (German, Spanish, UK)
          "KG", "LLP", "S.L.", "S.L.U.", "SL", "SLU", "EG", "SAS", "S.A.S."}
_ALIASES = {
    "ROYAL DUTCH SHELL": "SHELL", "TOTAL": "TOTALENERGIES", "ORSTED": "ORSTED", "OERSTED": "ORSTED",
    "KONINKLIJKE PHILIPS": "PHILIPS", "PHILIPS": "PHILIPS", "ENI S P A": "ENI",
    "SOCIETE GENERALE": "SOCIETE GENERALE", "CREDIT AGRICOLE": "CREDIT AGRICOLE",
    "BNP PARIBAS": "BNP PARIBAS", "ERSTE": "ERSTE", "ERSTE BANK": "ERSTE",
    "UNICREDIT": "UNICREDIT", "INTER IKEA": "INTER IKEA", "INTER IKEA SYSTEMS": "INTER IKEA",
    "HSBC": "HSBC", "NATWEST": "NATWEST", "LLOYDS BANKING": "LLOYDS", "LLOYDS": "LLOYDS",
    "STANDARD CHARTERED": "STANDARD CHARTERED", "ANGLO AMERICAN": "ANGLO AMERICAN",
    "BHP": "BHP", "BHP BILLITON": "BHP", "SMITHS": "SMITHS", "ALLIANZ": "ALLIANZ", "REPSOL": "REPSOL",
    "DEUTSCHE BANK": "DEUTSCHE BANK", "BARCLAYS": "BARCLAYS", "BP": "BP", "BP P L C": "BP",
    "EQUINOR": "EQUINOR", "STATOIL": "EQUINOR", "MICROSOFT": "MICROSOFT", "APPLE": "APPLE",
    "IBERDROLA": "IBERDROLA", "ENEL": "ENEL", "ENDESA": "ENDESA", "UNIPER": "UNIPER",
    "FORTUM": "FORTUM", "VATTENFALL": "VATTENFALL", "EDF": "EDF", "ELECTRICITE DE FRANCE": "EDF",
    "ENGIE": "ENGIE", "HOLCIM": "HOLCIM", "SHELL": "SHELL",
    "W&R BARNETT": "WR BARNETT",      # the Irish registry spelling, mapped to the key that Taxplorer's spelling gives
    # Irish registry names, mapped to the key that Taxplorer's short name gives (the same FY2025 filing in both)
    "GUIDEWIRE SOFTWARE": "GUIDEWIRE", "INTELLIGENT PACKAGING PARTNERSHIP": "INTELLIGENT PACKAGING",
    "SEAGATE TECHNOLOGY": "SEAGATE", "TRAVELPORT TECHNOLOGY": "TRAVELPORT",
    # the same groups under the names of the 2026-10 Taxplorer version (found by comparing names across sources)
    "JOHNSON CONTROLS INTERNATIONAL": "JOHNSON CONTROLS", "ATLANTICA SUSTAINABLE INFRASTRUCTURE": "ATLANTICA",
    # company records of TJN's pCbCR tracker, mapped to the key of the same group in Taxplorer (matched by name and
    # by identical lines). Siemens and Siemens Energy, Adobe and ADO and similar pairs are different groups and
    # stay apart.
    "AIR PRODUCTS CHEMICALS": "AIR PRODUCTS", "ALNATURA BETEILIGUNGS": "ALNATURA", "BAINCOMPANY PARTNERS L P": "BAIN",
    "BAXTER INTERNATIONAL": "BAXTER", "BENTLEY SYSTEMS INCORPORATED": "BENTLEY SYSTEMS", "CASIO COMPUTER": "CASIO",
    "CISCO SYSTEMS": "CISCO", "COLT TECHNOLOGY SERVICES": "COLT", "CONSTRUCCIONES Y AUXILIAR DE FERROCARRILES": "CAF",
    "DM DROGERIE MARKT VERWALTUNGS": "DM DROGERIE MARKT", "DSM FIRMENICH": "DSM", "EBSCO": "EBSCO INDUSTRIES",
    "EMERSON ELECTRIC": "EMERSON", "ENCE ENERGIA Y CELULOSA": "ENCE", "EUTELSAT COMMUNICATIONS": "EUTELSAT",
    "FONTERRA OPERATIVE": "FONTERRA", "FUNDACION ONCE": "ONCE", "HANKOOK TIRE TECHNOLOGY": "HANKOOK TIRE",
    "IKEA INGKA": "INGKA", "IKEA INTER IKEA": "INTER IKEA", "IMPORTACO SA": "IMPORTACO",
    "INTERNATIONAL CONSOLIDATED AIRLINES": "IAG", "KWS SAAT": "KWS",
    "MEDPACE SUBSIDIARIES FY2025 PUBLISHED BY MEDPACE SPAIN": "MEDPACE", "META": "META PLATFORMS", "NORSK HYDRO": "HYDRO",
    "O DE LA EMPRESA BRITISH UNITED PROVIDENT ASSOCIATION": "BUPA", "OC OERLIKON PFAFFIKON": "OERLIKON",
    "RAKUTEN TV EUROPE": "RAKUTEN", "SEDGWICK L P": "SEDGWICK", "SOVEREIGN WEALTH FUND SAMRUK KAZYNA JSC": "SAMRUK KAZYNA",
    "STRIPE GLOBAL": "STRIPE", "WASSERMAN MEDIA": "WASSERMAN", "SCHWANHAUER INDUSTRIE": "SCHWAN STABILO",
    "GUBEL": "PROSEGUR", "WAGNER GENERATIONS": "REHAU", "BETEILIGUNGSGESELLSCHAFT EMSLAND STARKE": "EMSLAND STAERKE",
    "EMPRESA REDEIA CORPORACION": "RED ELECTRICA", "RESIDENCIAL MARINA": "PALLADIUM HOTEL",
    # the same report under two names (identical staff and number of jurisdictions, profit equal up to exchange-rate
    # rounding), from parent legal names against brands and from spelling variants
    "P&G": "PROCTER GAMBLE", "CELSA STEEL": "CELSA", "PARTS TOWN UNLIMITED": "PARTS TOWN", "QUAKER CHEMICAL": "QUAKER HOUGHTON",
    "PRICEWATERHOUSECOOPERS WIRTSCHAFTSPRUFUNGSGESELLSCHAFT": "PWC GERMANY", "LONDON STOCK EXCHANGE": "LSEG",
    "UL SOLUTIONS": "UNDERWRITERS LABORATORIES", "L1R HB": "HOLLAND BARRETT", "ASYST TOPCO": "ACCESS",
    "CRAWFORD": "ENTERPRISE",                      # The Crawford Group, Inc., parent of Enterprise Holdings
    "WMB": "CSC", "SCI PH PARENT LOS ANGELES USA": "MAUSER PACKAGING SOLUTIONS", "ZCZL INDUSTRIAL TECHNOLOGY": "SEG AUTOMOTIVE",
    "MOODY S": "MOODYS", "SAZAREC": "SAZERAC", "ULYDIEN DAC": "FLOW TECHNOLOGY DESIGNATED ACTIVITY",
}


# Taxplorer display names whose short form differs from the name that the other sources use for the same group. I
# map them so that the group keeps one key.
TAXPLORER_RENAMES = {"ASPEN": "ASPEN PHARMACARE"}   # there is also an Irish registry filing under that name
# I take Taxplorer rows as EUR. The rows of these groups carry the report's own currency unconverted. The reports
# show this: TotalEnergies' CbCR is in US$, and Taxplorer's values equal it.
TAXPLORER_CURRENCY = {"TOTALENERGIES": "USD"}
# tjn_pcbcr extractions with the wrong unit. I multiply their monetary fields by the factor. Eni FY2018 shows a
# revenue of 139m instead of about 139bn, while the other Eni years are in EUR as published.
TJN_PCBCR_SCALE = {os.path.join("eni-s-p-a", "fy2018.json"): 1000.0}
_MONEY = ["total_revenues", "unrelated_party_revenues", "related_party_revenues", "profit_loss_before_income_tax",
          "income_tax_paid_on_cash_basis", "income_tax_accrued_current_year", "tangible_assets_except_cash",
          "stated_capital", "accumulated_earnings"]


def norm_company(name):
    """Return a stable company key: the name in uppercase ASCII, without legal-form tokens and a trailing report
    year, with the aliases applied."""
    if pd.isna(name):
        return None
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = s.upper().strip()
    s = re.sub(r"\b(19|20)\d{2}\b", " ", s)               # "SHELL PLC 2024"
    s = re.sub(r"[^A-Z0-9&\.\/ ]+", " ", s)
    toks = [t for t in s.split() if t not in _LEGAL]
    s = " ".join(toks)
    s = re.sub(r"[\.\/]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return _ALIASES.get(s, s)


_ISO_FIX = {
    "TÜRKIYE": "TUR", "TURKIYE": "TUR", "TURKEY": "TUR", "RUSSIA": "RUS", "SOUTH KOREA": "KOR", "KOREA": "KOR",
    "REPUBLIC OF KOREA": "KOR", "TAIWAN": "TWN", "CURAÇAO": "CUW", "CURACAO": "CUW", "HONG KONG": "HKG",
    "VENEZUELA": "VEN", "IRAN": "IRN", "BOLIVIA": "BOL", "VIETNAM": "VNM", "VIET NAM": "VNM", "LAOS": "LAO",
    "SYRIA": "SYR", "MOLDOVA": "MDA", "TANZANIA": "TZA", "CZECHIA": "CZE", "CZECH REPUBLIC": "CZE",
    "IVORY COAST": "CIV", "COTE D'IVOIRE": "CIV", "CÔTE D'IVOIRE": "CIV", "COTE D IVOIRE": "CIV",
    "DEMOCRATIC REPUBLIC OF THE CONGO": "COD", "DR CONGO": "COD", "CONGO, DEM. REP.": "COD", "CONGO (DRC)": "COD",
    "CONGO": "COG", "REPUBLIC OF THE CONGO": "COG", "CAPE VERDE": "CPV", "BRUNEI": "BRN", "MACAU": "MAC",
    "MACAO": "MAC", "NETHERLANDS ANTILLES": "ANT", "KOSOVO": "XKX", "UNITED STATES": "USA", "USA": "USA",
    "UNITED STATES OF AMERICA": "USA", "UNITED KINGDOM": "GBR", "UK": "GBR", "GREAT BRITAIN": "GBR",
    "PALESTINE": "PSE", "STATE OF PALESTINE": "PSE", "MYANMAR": "MMR", "BURMA": "MMR", "NORTH MACEDONIA": "MKD",
    "MACEDONIA": "MKD", "SWAZILAND": "SWZ", "ESWATINI": "SWZ", "TIMOR-LESTE": "TLS", "EAST TIMOR": "TLS",
    "SAINT LUCIA": "LCA", "ST LUCIA": "LCA", "TRINIDAD AND TOBAGO": "TTO", "TRINIDAD & TOBAGO": "TTO",
    "BOSNIA AND HERZEGOVINA": "BIH", "BOSNIA": "BIH", "SLOVAK REPUBLIC": "SVK", "SLOVAKIA": "SVK",
    "THE NETHERLANDS": "NLD", "NETHERLANDS": "NLD", "HOLLAND": "NLD", "CHINA": "CHN", "PEOPLE'S REPUBLIC OF CHINA": "CHN",
    "MAINLAND CHINA": "CHN", "BRITISH VIRGIN ISLANDS": "VGB", "VIRGIN ISLANDS (BRITISH)": "VGB",
    "US VIRGIN ISLANDS": "VIR", "CAYMAN": "CYM", "CAYMAN ISLANDS": "CYM", "ISLE OF MAN": "IMN", "JERSEY": "JEY",
    "GUERNSEY": "GGY", "BAHAMAS": "BHS", "THE BAHAMAS": "BHS", "GAMBIA": "GMB", "THE GAMBIA": "GMB",
    "EGYPT": "EGY", "UAE": "ARE", "UNITED ARAB EMIRATES": "ARE", "SAUDI ARABIA": "SAU", "SAINT KITTS AND NEVIS": "KNA",
    "MICRONESIA": "FSM", "RÉUNION": "REU", "REUNION": "REU", "FALKLAND ISLANDS": "FLK", "FAROE ISLANDS": "FRO",
    "SAO TOME AND PRINCIPE": "STP", "SÃO TOMÉ AND PRÍNCIPE": "STP", "ST. VINCENT AND THE GRENADINES": "VCT",
    "SAINT VINCENT AND THE GRENADINES": "VCT", "ANTIGUA AND BARBUDA": "ATG", "TURKS AND CAICOS ISLANDS": "TCA",
    "BONAIRE": "BES", "SINT MAARTEN": "SXM", "ST MAARTEN": "SXM", "SAINT MARTIN": "MAF", "ARUBA": "ABW",
    "NORTH KOREA": "PRK", "SOUTH SUDAN": "SSD", "LIBYA": "LBY", "GUINEA-BISSAU": "GNB", "EQUATORIAL GUINEA": "GNQ",
    "CENTRAL AFRICAN REPUBLIC": "CAF", "PAPUA NEW GUINEA": "PNG", "NEW CALEDONIA": "NCL", "FRENCH POLYNESIA": "PYF",
    "FRENCH GUIANA": "GUF", "GUADELOUPE": "GLP", "MARTINIQUE": "MTQ", "MAYOTTE": "MYT", "GREENLAND": "GRL",
    "GIBRALTAR": "GIB", "MONACO": "MCO", "LIECHTENSTEIN": "LIE", "SAN MARINO": "SMR", "VATICAN": "VAT",
    "ANDORRA": "AND", "BERMUDA": "BMU", "MAURITIUS": "MUS", "SEYCHELLES": "SYC", "MALDIVES": "MDV",
    "NAMIBIA": "NAM", "REPUBLIC OF IRELAND": "IRL", "RUSIA": "RUS", "LUXEMBURG": "LUX",
    "FRANCE OVERSEAS DEPARTMENTS AND TERRITORIES": "OTHER", "ALL OTHER TAX JURISDICTIONS (AGGREGATED)": "OTHER",
}
_OTHER_PAT = re.compile(r"^(other|others|rest of|all other|remaining|other jurisdictions|other countries|non[- ]eu|rest of world|row|total|aggregated)", re.I)
_iso_cache = {}


def to_iso3(code_or_name):
    """Return the ISO3 code for an ISO2 code, ISO3 code or country name. Residual buckets become 'OTHER', and an
    unresolved name gives None."""
    if pd.isna(code_or_name):
        return None
    s = str(code_or_name).strip()
    if not s:
        return None
    if s in _iso_cache:
        return _iso_cache[s]
    r = None
    up = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper().strip()
    if up in ("OTHER", "OT", "OTH", "XX", "ROW", "WLD", "W"):
        r = "OTHER"
    elif _OTHER_PAT.match(up):
        r = "OTHER"
    elif up in _ISO_FIX:
        r = _ISO_FIX[up]
    elif len(up) == 2 and up.isalpha():
        if up == "XK":
            r = "XKX"
        else:
            c = pycountry.countries.get(alpha_2=up)
            r = c.alpha_3 if c else None
    elif len(up) == 3 and up.isalpha():
        r = up if (pycountry.countries.get(alpha_3=up) or up in ("XKX", "ANT")) else None
    else:
        c = pycountry.countries.get(name=s) or pycountry.countries.get(common_name=s) \
            or pycountry.countries.get(official_name=s)
        if c is None:
            try:
                m = pycountry.countries.search_fuzzy(s)
                c = m[0] if m else None
            except LookupError:
                c = None
        r = c.alpha_3 if c else None
    _iso_cache[s] = r
    return r


def load_fx():
    """Return the exchange rates in local currency units (LCU) per US$ (period average) by (iso_country, year).
    The EMU row carries the euro. I fill the years that the World Bank file does not reach from the ECB annual
    averages, with cross rates via the euro. The World Bank EMU row is the ECB rate, so the two agree where both
    exist. Only after that do I carry the last observation forward, so that FY2025 reports are not converted at
    2024 rates."""
    df = pd.read_csv(exchange_rates_wb, skiprows=4)
    year_cols = [c for c in df.columns if str(c).isdigit()]
    long = df.melt(id_vars=["Country Code"], value_vars=year_cols, var_name="year", value_name="fx")
    long["year"] = long["year"].astype(int)
    long = long.dropna(subset=["fx"]).rename(columns={"Country Code": "iso"})
    # ---- ECB fill: LCU per USD = (LCU per EUR) / (USD per EUR) ----
    ecb = pd.read_csv(exchange_rates_ecb)
    ecb = ecb.pivot_table(index="TIME_PERIOD", columns="CURRENCY", values="OBS_VALUE")
    wb_last = long.groupby("iso")["year"].max()   # I extend each World Bank series only past its last year
    fill = [dict(iso="EMU", year=int(y), fx=1.0 / ecb.at[y, "USD"]) for y in ecb.index]
    fill += [dict(iso=iso, year=int(y), fx=ecb.at[y, cur] / ecb.at[y, "USD"])
             for cur, iso in _CUR_ISO.items() if iso and cur in ecb.columns for y in ecb.index
             if pd.notna(ecb.at[y, cur])]
    fill = pd.DataFrame([f for f in fill if f["iso"] in wb_last.index and f["year"] > wb_last[f["iso"]]])
    if len(fill):
        long = pd.concat([long, fill], ignore_index=True)
    last = long.year.max()
    fx = {(r.iso, r.year): r.fx for r in long.itertuples()}
    for iso, g in long.groupby("iso"):
        g = g.sort_values("year")
        for y in range(int(g.year.max()) + 1, last + 4):
            fx[(iso, y)] = g.fx.iloc[-1]
    return fx


_CUR_ISO = {"EUR": "EMU", "GBP": "GBR", "CHF": "CHE", "SEK": "SWE", "NOK": "NOR", "DKK": "DNK", "JPY": "JPN",
            "AUD": "AUS", "CAD": "CAN", "ZAR": "ZAF", "INR": "IND", "BRL": "BRA", "MXN": "MEX", "PLN": "POL",
            "CZK": "CZE", "HUF": "HUN", "HKD": "HKG", "SGD": "SGP", "KRW": "KOR", "CNY": "CHN", "RMB": "CHN",
            "RUB": "RUS", "TRY": "TUR", "ILS": "ISR", "NZD": "NZL", "RON": "ROU", "ISK": "ISL", "AED": "ARE",
            "SAR": "SAU", "THB": "THA", "MYR": "MYS", "PHP": "PHL", "IDR": "IDN", "CLP": "CHL", "COP": "COL",
            "ARS": "ARG", "PEN": "PER", "MAD": "MAR", "EGP": "EGY", "KZT": "KAZ", "AZN": "AZE", "QAR": "QAT",
            "KWD": "KWT", "OMR": "OMN", "BHD": "BHR", "NGN": "NGA", "KES": "KEN", "GHS": "GHA", "PKR": "PAK",
            "BDT": "BGD", "LKR": "LKA", "VND": "VNM", "TWD": "TWN", "HRK": "HRV", "BGN": "BGR", "UAH": "UKR",
            "USD": None}
FX = load_fx()


def fx_to_usd(currency, year):
    """Return local currency units per US$ for the report currency in `year` (1 for USD, NaN if unknown)."""
    if pd.isna(currency):
        return np.nan
    cur = str(currency).upper().strip()
    if cur == "USD":
        return 1.0
    iso = _CUR_ISO.get(cur)
    if iso is None:
        return np.nan
    return FX.get((iso, int(year)), np.nan)


def fy_label(end_date, start_date=None):
    """Return the fiscal-year label of the Taxplorer convention, the calendar year that holds most of the fiscal
    year. A fiscal year ending in June takes the year it ends in, and one ending in March the year before."""
    e = pd.to_datetime(end_date, errors="coerce")
    if pd.isna(e):
        return None
    return int(e.year if e.month >= 6 else e.year - 1)


# %% MARK: 3. Source loaders (each returns the unified schema, values in the original currency)
def load_tjn_pcbcr():
    rows = []
    for f in sorted(glob.glob(os.path.join(RAW, "tjn_pcbcr_extractions_2026-09", "*", "fy*.json"))):
        j = json.load(open(f, encoding="utf-8"))
        s1 = j.get("section1", {})
        meta_path = os.path.join(os.path.dirname(f), "meta.json")
        meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
        year = fy_label(s1.get("financialYearEnd"))
        for r in j.get("section2", []):
            rows.append({
                "source": "tjn_pcbcr", "source_detail": os.path.relpath(f, RAW),
                "company": j.get("companyName"), "hq_iso3": to_iso3(s1.get("registeredOfficeCountry")),
                "sector": meta.get("sector") or None, "year": year,     # an empty string counts as missing
                "iso_partner": to_iso3(r.get("countryCode")) or to_iso3(r.get("taxJurisdiction")),
                "jurisdiction_name": r.get("taxJurisdiction"),
                "n_employees": r.get("numberOfEmployees"),
                "total_revenues": r.get("revenueTotal"),
                "unrelated_party_revenues": r.get("revenueFromUnrelatedParties"),
                "related_party_revenues": r.get("revenueFromRelatedParties"),
                "profit_loss_before_income_tax": r.get("profitOrLossBeforeIncomeTax"),
                "income_tax_paid_on_cash_basis": r.get("incomeTaxPaidCashBasis"),
                "income_tax_accrued_current_year": r.get("incomeTaxAccruedCurrentYear"),
                "tangible_assets_except_cash": r.get("tangibleAssets"),
                "stated_capital": r.get("statedCapital"),
                "accumulated_earnings": r.get("accumulatedEarnings"),
                "currency": s1.get("reportingCurrency"), "disclosure_quality": None,
            })
    out = pd.DataFrame(rows)
    for rel, k in TJN_PCBCR_SCALE.items():
        m = out["source_detail"].str.endswith(rel)
        out.loc[m, _MONEY] = out.loc[m, _MONEY].apply(pd.to_numeric, errors="coerce") * k
    return out


TAXPLORER_FILE = "taxplorer_data_2026-10-17.json"     # taxplorer.eu/data.json, version 2026-10-17 (retrieved 2026-10-21)


def load_taxplorer():
    """Return the Taxplorer rows as delivered (data.json holds a schema and the rows). The company field carries a
    public-facing display name with the full name in brackets ("BP (BRITISH PETROLEUM)"). I drop the bracketed part
    so that the key is built from the short name the other sources use. I do not use the 0–100 transparencyScore,
    because the two-jurisdiction rule of script 9 drops single-country and aggregate-only reports."""
    if not os.path.exists(os.path.join(RAW, TAXPLORER_FILE)):
        # Taxplorer (EU Tax Observatory) is not shipped, because its terms require permission to republish the
        # database.
        # Download data.json from taxplorer.eu into data/raw/firm_level/ (see data/raw/README.md).
        print(f"  [taxplorer] {TAXPLORER_FILE} not found: the panel is built without Taxplorer")
        return pd.DataFrame(columns=["source", "source_detail", "company", "hq_iso3", "sector", "year", "iso_partner",
                                     "jurisdiction_name", "n_employees", "total_revenues", "unrelated_party_revenues",
                                     "related_party_revenues", "profit_loss_before_income_tax",
                                     "income_tax_paid_on_cash_basis", "income_tax_accrued_current_year",
                                     "tangible_assets_except_cash", "stated_capital", "accumulated_earnings",
                                     "currency", "disclosure_quality"])
    with open(os.path.join(RAW, TAXPLORER_FILE)) as f:
        d = json.load(f)
    t = pd.DataFrame(d["rows"], columns=d["schema"])
    name = t["mnc"].astype(str).str.replace(r"\s*\([^)]*\)\s*$", "", regex=True).str.strip()
    name = name.map(lambda n: TAXPLORER_RENAMES.get(n, n))
    return pd.DataFrame({
        "source": "taxplorer", "source_detail": f"taxplorer.eu data.json v{d.get('version', '')}",
        "company": name, "hq_iso3": t["hq"].map(to_iso3), "sector": t["sector"], "year": t["year"],
        "iso_partner": t["jurCode"].map(to_iso3), "jurisdiction_name": t["jurName"],
        "n_employees": t["employees"], "total_revenues": t["revenue"],
        "unrelated_party_revenues": t["unrelatedRevenue"], "related_party_revenues": t["relatedRevenue"],
        "profit_loss_before_income_tax": t["profit"], "income_tax_paid_on_cash_basis": t["taxPaid"],
        "income_tax_accrued_current_year": t["taxAccrued"], "tangible_assets_except_cash": t["tangibleAssets"],
        "stated_capital": t["statedCapital"], "accumulated_earnings": t["accumulatedEarnings"],
        "currency": name.map(lambda n: TAXPLORER_CURRENCY.get(n, "EUR")), "disclosure_quality": None,
    })


_UNIT_MULT = {"": 1.0, "K": 1e3, "M": 1e6, "BN": 1e9, "B": 1e9}
_PDF_HQ = {"BP": "GBR", "EDF": "FRA", "ENGIE": "FRA", "ENI": "ITA", "Enel": "ITA", "Equinor": "NOR",
           "Fortum": "FIN", "Holcim": "CHE", "REPSOL": "ESP", "SHELL": "GBR", "TotalEnergies": "FRA",
           "Uniper": "DEU", "Vattenfall": "SWE"}


def load_tracker_db():
    """Return TJN's pCbCR tracker database, the confirmed current version of every report as exported from the
    tracker. I multiply monetary values by the report's scale (units, thousands or millions) and keep employees as
    printed. 'aggregate' lines (rest of the world, regional remainders) become OTHER, and I drop 'total' lines.
    Revenue is total revenues as printed ('turnover' where a report labels it so). The tracker has no sector field.
    Reports under CRD IV are banks, and other groups take their sector from another source for the same company
    where there is one."""
    t = pd.read_csv(os.path.join(RAW, TRACKER_FILE), low_memory=False, keep_default_na=False, na_values=[""])
    t = t[t["row_type"].isin(["jurisdiction", "aggregate"])].copy()
    sc = pd.to_numeric(t["scale"], errors="coerce").fillna(1.0)
    money = lambda c: pd.to_numeric(t[c], errors="coerce") * sc
    iso = t["jurisdiction_iso"].map(to_iso3).where(t["row_type"] == "jurisdiction", "OTHER")
    return pd.DataFrame({
        "source": "tjn_tracker_db", "source_detail": "pcbcr-database ingestion.db, version " + t["version_id"].astype(str),
        "company": t["company_name"], "hq_iso3": t["parent_country"].map(to_iso3),
        "sector": np.where(t["regime"] == "CRD IV", "Banking", None),
        "year": [fy_label(e, st) for e, st in zip(t["period_end"], t["period_start"])],
        "iso_partner": iso, "jurisdiction_name": t["original_label"],
        "n_employees": pd.to_numeric(t["employees"], errors="coerce"),
        "total_revenues": money("revenues").fillna(money("turnover")),
        "unrelated_party_revenues": money("revenues_unrelated_party"),
        "related_party_revenues": money("revenues_related_party"),
        "profit_loss_before_income_tax": money("profit_before_tax"),
        "income_tax_paid_on_cash_basis": money("tax_paid"),
        "income_tax_accrued_current_year": money("tax_accrued").fillna(money("tax_on_profit")),
        "tangible_assets_except_cash": money("tangible_assets"),
        "stated_capital": money("stated_capital"), "accumulated_earnings": money("accumulated_earnings"),
        "currency": t["currency"], "disclosure_quality": None,
    })


def load_tjn_pdf():
    r = pd.read_csv(os.path.join(RAW, "tjn_pdf_extractions_2026-09", "pcbcr_pdf_rows.csv"), low_memory=False,
                    keep_default_na=False, na_values=[""])
    unit = r["unit"].astype(str).str.upper().str.strip()
    cur = unit.str.extract(r"^([A-Z]{3})")[0]
    mult = unit.str.replace(r"^[A-Z]{3}", "", regex=True).str.strip().map(_UNIT_MULT).fillna(1.0)
    out = pd.DataFrame({
        "source": "tjn_pdf", "source_detail": r["source"], "company": r["company"],
        "hq_iso3": r["company"].map(_PDF_HQ), "sector": "Oil, Gas and Mining / Utilities", "year": r["year"],
        "iso_partner": [to_iso3(c) if pd.notna(c) else to_iso3(n) for c, n in zip(r["country"], r["country_name"])],
        "jurisdiction_name": r["country_name"],
        "n_employees": r["employees"], "currency": cur, "disclosure_quality": None,
    })
    for src, dst in [("rev_total", "total_revenues"), ("rev_unrelated", "unrelated_party_revenues"),
                     ("rev_related", "related_party_revenues"), ("pbt", "profit_loss_before_income_tax"),
                     ("tax_paid", "income_tax_paid_on_cash_basis"), ("tax_accrued", "income_tax_accrued_current_year"),
                     ("tangible_assets", "tangible_assets_except_cash"), ("stated_capital", "stated_capital"),
                     ("accum_earnings", "accumulated_earnings")]:
        out[dst] = pd.to_numeric(r[src], errors="coerce") * mult
    return out


def load_pcbcr_database(which):
    u = pd.read_csv(os.path.join(RAW, "pcbcr_database_unified_2026-08.csv"), low_memory=False,
                    keep_default_na=False, na_values=[""])
    u = u[u["source"] == which].copy()
    iso = u["jurisdiction_iso"].map(to_iso3)
    iso = iso.where(iso.notna(), u["jurisdiction_name"].map(to_iso3))
    return pd.DataFrame({
        "source": "pcbcr_database" if which == "company_website" else "euto_banks",
        "source_detail": u["source_detail"], "company": u["company_name"],
        "hq_iso3": u["upe_country_iso"].map(to_iso3), "sector": u["sector"], "year": u["report_year"],
        "iso_partner": iso, "jurisdiction_name": u["jurisdiction_name"], "n_employees": u["employees"],
        "total_revenues": u["total_revenues"], "unrelated_party_revenues": u["unrelated_revenues"],
        "related_party_revenues": u["related_revenues"], "profit_loss_before_income_tax": u["profit_before_tax"],
        "income_tax_paid_on_cash_basis": u["tax_paid"], "income_tax_accrued_current_year": u["tax_accrued"],
        "tangible_assets_except_cash": u["tangible_assets"], "stated_capital": u["stated_capital"],
        "accumulated_earnings": u["accumulated_earnings"], "currency": u["currency"], "disclosure_quality": None,
    })


def load_cro_ireland():
    """Return the Irish registry filings as extracted from the registry documents (manifest rows with
    verified == 1). I keep the aggregated "all other tax jurisdictions" line as OTHER."""
    cro = os.path.join(RAW, "cro_ireland")
    man = pd.read_csv(os.path.join(cro, "cro_ireland_manifest.csv"), dtype={"report_id": str})
    man = man[man["verified"] == 1]
    rows = []
    for r in man.itertuples():
        q = pd.read_csv(os.path.join(cro, "extracted", r.extracted_file), dtype={"code": str}, keep_default_na=False,
                        na_values=[""])
        company = re.sub(r"\s+\d{1,2}\s+[A-Za-z]+\s+20\d{2}\s*$", "", str(r.company)).strip()   # "… 25 September 2026"
        country = re.sub(r"^the\s+|\s*\(the\)\s*$", "", str(r.parent_country), flags=re.I).strip()
        country = re.sub(r"^Republic of\s+", "", country, flags=re.I)
        iso = [("OTHER" if t == "other_aggregated" else (to_iso3(c) or to_iso3(j)))
               for t, c, j in zip(q["line_type"], q["code"], q["jurisdiction"])]
        rows.append(pd.DataFrame({
            "source": "cro_ireland", "source_detail": os.path.join("cro_ireland", "reports", r.raw_file),
            "company": company, "hq_iso3": to_iso3(country), "sector": None, "year": fy_label(r.fy_end),
            "iso_partner": iso, "jurisdiction_name": q["jurisdiction"], "n_employees": q["employees"],
            "total_revenues": q["revenue"], "unrelated_party_revenues": np.nan, "related_party_revenues": np.nan,
            "profit_loss_before_income_tax": q["pbt"], "income_tax_paid_on_cash_basis": q["tax_paid"],
            "income_tax_accrued_current_year": q["tax_accrued"], "tangible_assets_except_cash": np.nan,
            "stated_capital": np.nan, "accumulated_earnings": q["acc_earnings"], "currency": r.currency,
            "disclosure_quality": None,
        }))
    return pd.concat(rows, ignore_index=True)


def apply_hq_overrides(df):
    """Harmonise the headquarters country of groups that carry more than one hq_iso3 across years. I first apply
    the curated rows of firm_hq_overrides.csv (blank year bounds mean all years). Any group that still carries
    several HQs and is not in the file then takes the HQ of its latest year, and I print it."""
    ov = pd.read_csv(os.path.join(RAW, "firm_hq_overrides.csv"), keep_default_na=False, na_values=[""])
    for r in ov.itertuples():
        m = df["company_key"] == r.company_key
        if not m.any():
            print(f"  [hq] override for {r.company_key!r}: no such group in the panel")
            continue
        if pd.notna(r.year_start):
            m &= df["year"] >= int(r.year_start)
        if pd.notna(r.year_end):
            m &= df["year"] <= int(r.year_end)
        changed = m & (df["hq_iso3"] != r.hq_iso3)
        if changed.any():
            print(f"  [hq] {r.company_key}: {sorted(df.loc[changed, 'year'].unique().tolist())} "
                  f"{sorted(df.loc[changed, 'hq_iso3'].dropna().unique().tolist())} → {r.hq_iso3} (curated)")
        df.loc[m, "hq_iso3"] = r.hq_iso3
    n_hq = df.groupby("company_key")["hq_iso3"].nunique()
    for k in sorted(set(n_hq[n_hq > 1].index) - set(ov["company_key"])):
        g = df[(df["company_key"] == k) & df["hq_iso3"].notna()]
        latest = g.loc[g["year"] == g["year"].max(), "hq_iso3"].iloc[0]
        print(f"  [hq] {k}: several HQs {g.groupby('hq_iso3')['year'].agg(['min', 'max']).to_dict('index')}, "
              f"not in firm_hq_overrides.csv → latest year's HQ {latest} for all years")
        df.loc[df["company_key"] == k, "hq_iso3"] = latest
    return df


# %% MARK: 4. Build
def main():
    parts = [load_tjn_pcbcr(), load_cro_ireland(), load_tracker_db(), load_taxplorer(), load_tjn_pdf(),
             load_pcbcr_database("company_website"), load_pcbcr_database("tax_observatory_banks")]
    df = pd.concat(parts, ignore_index=True)
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df.dropna(subset=["year", "company"]).copy()
    df["year"] = df["year"].astype(int)
    df["company_key"] = df["company"].map(norm_company)
    for c in VALUE_COLS + ["n_employees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # I correct whole reports in the extracted tables before the deduplication, so that a lower-priority source can
    # replace a broken report.
    #  (a) Empty extractions. I drop a report in which every profit and revenue value is zero or missing.
    #  (b) Sign convention. Some reports print tax as a negative expense (the JSON files of BNP Paribas, Deutsche
    #      Bank and Crédit Agricole). I flip a tax column whose sum over the report's positive-profit rows is
    #      negative.
    rk = ["source", "company_key", "year"]
    # The HQ and sector of each company known from any source. I keep them across the deduplication, so that a
    # group-year whose winning report lacks them is still classified.
    _hq_any = df.dropna(subset=["hq_iso3"]).groupby("company_key")["hq_iso3"].agg(lambda x: x.mode().iloc[0])
    _sec_any = df.dropna(subset=["sector"]).groupby("company_key")["sector"].agg(lambda x: x.mode().iloc[0])
    _rev = df["total_revenues"].fillna(df["unrelated_party_revenues"])
    _absum = (df["profit_loss_before_income_tax"].abs().fillna(0) + _rev.abs().fillna(0)).groupby([df[c] for c in rk]).transform("sum")
    empty = _absum <= 0
    if empty.any():
        print(f"  [fix] {df.loc[empty, rk].drop_duplicates().shape[0]} empty reports dropped "
              f"({df.loc[empty].groupby('source').size().to_dict()})")
        df = df[~empty].copy()
    bad = pd.MultiIndex.from_frame(df[rk]).isin(list(DROP_REPORTS))
    if bad.any():
        print(f"  [fix] {df.loc[bad, rk].drop_duplicates().shape[0]} implausible reports dropped "
              f"({sorted(df.loc[bad, rk].drop_duplicates().itertuples(index=False, name=None))})")
        df = df[~bad].copy()
    df["tax_sign_flipped"] = False
    _posrow = df["profit_loss_before_income_tax"] > 0
    for tc in ["income_tax_paid_on_cash_basis", "income_tax_accrued_current_year"]:
        s_ = df[tc].where(_posrow, 0.0).groupby([df[c] for c in rk]).transform("sum")
        # Inline-XBRL registry filings carry tagged signs, so a negative value there is a real refund.
        flip = (s_ < 0) & (df["source"] != "cro_ireland")
        if flip.any():
            df.loc[flip, tc] = -df.loc[flip, tc]
            df.loc[flip, "tax_sign_flipped"] = True
            print(f"  [fix] {tc}: sign flipped on {df.loc[flip, rk].drop_duplicates().shape[0]} reports "
                  f"({df.loc[flip].groupby('source').size().to_dict()})")

    # Residual lines already map to OTHER (to_iso3). I report and drop the jurisdictions that remain unresolved.
    unresolved = df[df["iso_partner"].isna()]
    if len(unresolved):
        top = unresolved["jurisdiction_name"].astype(str).value_counts().head(25)
        print(f"  [warn] {len(unresolved):,} rows with unresolved jurisdiction dropped; most frequent:\n{top.to_string()}")
    df = df[df["iso_partner"].notna()].copy()

    # I collapse duplicate jurisdiction lines inside one report (for example two 'Other' lines).
    agg = {c: (lambda s: s.sum(min_count=1)) for c in VALUE_COLS + ["n_employees"]}   # a group with only NaN values stays NaN
    agg.update({c: "first" for c in ["source_detail", "company", "hq_iso3", "sector", "jurisdiction_name",
                                     "currency", "disclosure_quality"]})
    agg["tax_sign_flipped"] = "max"
    key = ["source", "company_key", "year", "iso_partner"]
    _cnt = df.groupby(key).size()
    df = df.groupby(key, as_index=False).agg(agg)
    df = df.merge(_cnt.rename("_n").reset_index(), on=key)

    # I take the one-off gains off their lines (ONE_OFF_GAINS), in every source that holds the report.
    for (k, y, iso), (cur, amount) in ONE_OFF_GAINS.items():
        m_ = (df["company_key"] == k) & (df["year"] == y) & (df["iso_partner"] == iso)
        for i in df.index[m_]:
            if df.at[i, "currency"] != cur:
                print(f"  [warn] one-off gain {k} {y} {iso}: {df.at[i, 'source']} is in {df.at[i, 'currency']}, not {cur}; "
                      "not corrected")
                continue
            for c in ["profit_loss_before_income_tax", "unrelated_party_revenues", "total_revenues"]:
                if pd.notna(df.at[i, c]):
                    df.at[i, c] = df.at[i, c] - amount
            print(f"  [fix] one-off gain taken off {k} {y} {iso} ({df.at[i, 'source']}): {cur} {amount / 1e6:,.0f}m")

    # I convert the monetary values to US dollars.
    df["fx_lcu_per_usd"] = [fx_to_usd(c, y) for c, y in zip(df["currency"], df["year"])]
    miss_fx = df["fx_lcu_per_usd"].isna()
    if miss_fx.any():
        print(f"  [warn] no FX rate for {miss_fx.sum():,} rows: "
              f"{df.loc[miss_fx, ['currency', 'year']].drop_duplicates().to_dict('records')[:10]} → dropped")
        df = df[~miss_fx].copy()
    for c in VALUE_COLS:
        df[c] = df[c] / df["fx_lcu_per_usd"]

    # Source overlap and deduplication by priority, by whole (company, year) reports.
    df["_prio"] = df["source"].map({s: i for i, s in enumerate(SOURCE_PRIORITY)}).astype(float)
    # An Irish registry filing follows the EU directive (the EU lines and one aggregated line), and so do many
    # tracker reports. Such a report outranks the lower-priority sources only where it names at least as many
    # jurisdictions as the best of them for that group-year.
    _real = df[df["iso_partner"] != "OTHER"].groupby(["company_key", "year", "source"])["iso_partner"].nunique()
    _real = _real.rename("_n_real").reset_index()
    for _src in THIN_RISK_SOURCES:
        _cro = _real[_real["source"] == _src].set_index(["company_key", "year"])["_n_real"]
        _oth = _real[_real["source"] != _src].groupby(["company_key", "year"])["_n_real"].max()
        _thin = _cro.index[_cro.reindex(_cro.index) < _oth.reindex(_cro.index).fillna(0)]
        if len(_thin):
            m_ = (df["source"] == _src) & pd.MultiIndex.from_frame(df[["company_key", "year"]]).isin(_thin)
            df.loc[m_, "_prio"] = len(SOURCE_PRIORITY)
            print(f"  [dedup] {len(_thin)} {_src} reports name fewer jurisdictions than another source → not used: "
                  f"{sorted(set(k for k, _ in _thin))[:30]}")
    overlap = (df.groupby(["company_key", "year", "source"]).size().unstack("source").notna())
    best = df.groupby(["company_key", "year"])["_prio"].transform("min")
    n_before = len(df)
    df = df[df["_prio"] == best].copy()
    print(f"  dedup: {n_before:,} → {len(df):,} rows; (company, year) reports covered by >1 source: "
          f"{int((overlap.sum(axis=1) > 1).sum()):,}")

    # I fill the HQ and the sector within each company, because some sources lack them.
    df["hq_iso3"] = df.groupby("company_key")["hq_iso3"].transform(lambda s: s.ffill().bfill())
    df["sector"] = df.groupby("company_key")["sector"].transform(lambda s: s.ffill().bfill())
    df["sector"] = df["sector"].fillna(df["company_key"].map(TRACKER_SECTOR))
    df["hq_iso3"] = df["hq_iso3"].fillna(df["company_key"].map(_hq_any))
    df["sector"] = df["sector"].fillna(df["company_key"].map(_sec_any))
    df["sector"] = df["sector"].fillna(df["company_key"].map(SECTOR_FILL))
    _ov = df["company_key"].isin(SECTOR_OVERRIDES)
    df.loc[_ov, "sector"] = df.loc[_ov, "company_key"].map(SECTOR_OVERRIDES)
    df = apply_hq_overrides(df)
    df = df.sort_values(["company_key", "year", "iso_partner"]).reset_index(drop=True)
    df[OUT_COLS].to_csv(os.path.join(OUT_DIR, "firm_cbcr_panel.csv"), index=False)

    # Metadata per (company, year).
    rev = df["total_revenues"].fillna(df["unrelated_party_revenues"])
    df["_rev"] = rev
    df["_rev_other"] = np.where(df["iso_partner"] == "OTHER", rev, 0.0)
    meta = (df.groupby(["company_key", "year"], as_index=False)
              .agg(company=("company", "first"), source=("source", "first"), hq_iso3=("hq_iso3", "first"),
                   sector=("sector", "first"), currency=("currency", "first"),
                   disclosure_quality=("disclosure_quality", "first"),
                   n_jurisdictions=("iso_partner", "nunique"),
                   profit_usd=("profit_loss_before_income_tax", lambda s: s.sum(min_count=1)),
                   revenue_usd=("_rev", lambda s: s.sum(min_count=1)), revenue_other_usd=("_rev_other", "sum"),
                   n_employees=("n_employees", lambda s: s.sum(min_count=1)),
                   has_unrelated=("unrelated_party_revenues", lambda s: s.notna().mean()),
                   has_employees=("n_employees", lambda s: s.notna().mean()),
                   has_tangible=("tangible_assets_except_cash", lambda s: s.notna().mean()),
                   has_profit=("profit_loss_before_income_tax", lambda s: s.notna().mean())))
    meta["other_share_of_revenue"] = np.where(meta["revenue_usd"] > 0, meta["revenue_other_usd"] / meta["revenue_usd"], np.nan)
    meta["home_reported"] = [((df["company_key"] == k) & (df["year"] == y) & (df["iso_partner"] == h)).any()
                             for k, y, h in zip(meta["company_key"], meta["year"], meta["hq_iso3"])]
    meta.to_csv(os.path.join(OUT_DIR, "firm_year_meta.csv"), index=False)

    print(f"\nPanel: {len(df):,} rows | {df['company_key'].nunique():,} groups | "
          f"{meta.shape[0]:,} group-years | years {df['year'].min()}–{df['year'].max()}")
    print("rows by source:", df["source"].value_counts().to_dict())
    print("group-years by year:", meta.groupby("year").size().to_dict())
    print("group-years by source:", meta["source"].value_counts().to_dict())
    print(f"HQ unresolved: {int(meta['hq_iso3'].isna().sum())} group-years")


if __name__ == "__main__":
    main()
