# %%
# This script downloads the BIS Locational Banking Statistics (LBS), the cross-border
# bank claims and liabilities by counterparty country (García-Bernardo & Janský 2024,
# Table A.2: ln_dClaims and ln_dLiabilities; the consolidated statistics B4 give ln_BIS).
#
# I download the public LBS CSV zip once to data/raw/gravity/, keep it there as a cache
# and extract it. build_features.py does not use these statistics as features.

# %%
import os
import ssl
import urllib.request
import zipfile

RAW_GRAVITY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "raw", "gravity",
)
os.makedirs(RAW_GRAVITY, exist_ok=True)
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

URL = "https://www.bis.org/statistics/full_lbs_d_pub_csv.zip"
ZIP_PATH = os.path.join(RAW_GRAVITY, "bis_lbs_d_pub.zip")

# %%
if not os.path.exists(ZIP_PATH):
    print("Downloading BIS LBS public CSV ...", flush=True)
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=600, context=_CTX) as r, open(ZIP_PATH, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    print(f"  saved {os.path.getsize(ZIP_PATH)/1e6:.0f} MB", flush=True)
else:
    print(f"  cached zip ({os.path.getsize(ZIP_PATH)/1e6:.0f} MB)")

with zipfile.ZipFile(ZIP_PATH) as z:
    names = [n for n in z.namelist() if n.lower().endswith(".csv")]
    print("  zip contents:", names)
    for n in names:
        dest = os.path.join(RAW_GRAVITY, os.path.basename(n))
        if not os.path.exists(dest):
            with z.open(n) as src, open(dest, "wb") as out:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
            print(f"  extracted {os.path.basename(n)} ({os.path.getsize(dest)/1e6:.0f} MB)")

print("\nBIS LBS cached in data/raw/gravity/")
