"""
Make the BaTIS extract shipped with this package.

Reads the OECD-WTO Balanced Trade in Services (BaTIS) BPM6 bulk file, December
2025 edition (OECD-WTO_BATIS_BPM6_December2025_bulk.csv, 2.98 GB), and keeps only
the rows and columns that step 1a (src/1a_destination_based_sales.py) reads:
  - Flow = M (imports);
  - Year 2016-2023;
  - Item_code in SF, SG, SH, SI, SJ, SK1 (the digitally deliverable services of
    the IMF-OECD-UNCTAD-WTO Handbook on Measuring Digital Trade);
  - type_Reporter = c and type_Partner = c (countries only);
  - the nine columns Reporter, type_Reporter, Partner, type_Partner, Flow,
    Item_code, Year, Final_value, Balanced_value.
All values are read and written as text, so they are copied unchanged. The output
is gzip-compressed (level 9, fixed timestamp, so the same input gives the same file).

Usage:
  python data/raw/destination_based_sales/make_batis_extract.py <bulk.csv> <out.csv.gz>

Author: Tax Justice Network.
"""
import sys

import pandas as pd

src, dst = sys.argv[1], sys.argv[2]
use = ["SF", "SG", "SH", "SI", "SJ", "SK1"]
usecols = ["Reporter", "type_Reporter", "Partner", "type_Partner", "Flow", "Item_code", "Year",
           "Final_value", "Balanced_value"]
parts = []
n = 0
for chunk in pd.read_csv(src, usecols=usecols, chunksize=3_000_000, dtype=str):
    n += len(chunk)
    c = chunk[(chunk["Flow"] == "M") & (chunk["Year"].isin([str(y) for y in range(2016, 2024)]))
              & (chunk["Item_code"].isin(use)) & (chunk["type_Reporter"] == "c")
              & (chunk["type_Partner"] == "c")]
    parts.append(c[usecols])
out = pd.concat(parts, ignore_index=True)
out.to_csv(dst, index=False, compression={"method": "gzip", "compresslevel": 9, "mtime": 0})
print(n, "rows read;", len(out), "rows kept")
