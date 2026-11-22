# %%
# This script fetches the unilateral World Bank indicators of the García-Bernardo &
# Janský (2024) feature set for the gravity / machine-learning imputation.
#
# I fetch each indicator once from the World Bank API and write it to
# data/raw/gravity/wb_<CODE>.csv (long format: iso3, year, value). On later runs I read
# the cached CSV and do not call the API again, so the inputs stay frozen for
# reproducibility. Deleting a file forces a refresh.

# %%
import json
import os
import time
import urllib.request

import pandas as pd

RAW_GRAVITY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "raw", "gravity",
)
os.makedirs(RAW_GRAVITY, exist_ok=True)

import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from config import last_year as _LAST_YEAR  # sample end year (2023) — single source of truth
YEAR_FROM, YEAR_TO = 2014, _LAST_YEAR  # García-Bernardo & Janský use 2014-2018 means. I pull through the last analysis year.

# The World Bank indicators of Table A.2 (code -> short name).
# The WGI governance indicators (GE/RL/RQ/CC/PV/VA) are archived in the classic v2 API,
# so fetch_data360.py fetches them from WB Data360 (GOV_WGI_*) instead.
# IC.TAX.DURS (tax_complex, time to pay taxes) is a retired Doing Business indicator that
# the API no longer serves, so I omit it.
WB_INDICATORS = {
    # Socio-economic / macro
    "SP.POP.TOTL": "population",
    "NY.GDP.MKTP.CD": "gdp_current_usd",
    "NY.GDP.PCAP.CD": "gdp_per_capita_usd",
    "NE.CON.PRVT.KD": "hh_consumption_kd",
    "NE.GDI.FTOT.KD": "gross_fixed_cap_formation_kd",
    "BX.KLT.DINV.CD.WD": "fdi_inflows_usd",
    "NE.IMP.GNFS.CD": "imports_gs_usd",
    "NE.EXP.GNFS.CD": "exports_gs_usd",
    "BM.GSR.ROYL.CD": "ip_payments_usd",
    "BX.GSR.ROYL.CD": "ip_receipts_usd",
    "DT.DOD.DECT.CD": "external_debt_stocks_usd",
    "SE.XPD.TOTL.GD.ZS": "govt_educ_exp_pct_gdp",
    "SH.MED.NUMW.P3": "nurses_per_1000",
    "SH.MED.PHYS.ZS": "physicians_per_1000",
    "SH.XPD.GHED.GD.ZS": "govt_health_exp_pct_gdp",
}


def _fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    payload = json.loads(urllib.request.urlopen(req, timeout=60).read())
    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        return []
    return [
        {"iso3": r["countryiso3code"], "year": int(r["date"]), "value": r["value"]}
        for r in payload[1]
    ]


def fetch_indicator(code):
    """Fetches one World Bank indicator for all countries, YEAR_FROM to YEAR_TO, as a long data frame.

    I try the full date range first. Some indicators return HTTP 400 on a multi-year range, so I
    then fall back to fetching year by year.
    """
    base = f"https://api.worldbank.org/v2/country/all/indicator/{code}?format=json&per_page=20000"
    try:
        rows = _fetch_url(f"{base}&date={YEAR_FROM}:{YEAR_TO}")
    except Exception:
        rows = []
        for y in range(YEAR_FROM, YEAR_TO + 1):
            try:
                rows.extend(_fetch_url(f"{base}&date={y}"))
            except Exception:
                pass
    df = pd.DataFrame(rows, columns=["iso3", "year", "value"])
    return df[df["iso3"].astype(bool)]


# %%
for code, name in WB_INDICATORS.items():
    out = os.path.join(RAW_GRAVITY, f"wb_{code}.csv")
    if os.path.exists(out):
        n = len(pd.read_csv(out))
        print(f"  cached  {code:<22} {name:<28} ({n} rows)")
        continue
    try:
        df = fetch_indicator(code)
        df.to_csv(out, index=False)
        print(f"  fetched {code:<22} {name:<28} ({len(df)} rows)")
        time.sleep(0.5)
    except Exception as e:
        print(f"  FAIL    {code:<22} {name:<28} {type(e).__name__}: {str(e)[:60]}")

print(f"\nWorld Bank indicators cached in data/raw/gravity/")
