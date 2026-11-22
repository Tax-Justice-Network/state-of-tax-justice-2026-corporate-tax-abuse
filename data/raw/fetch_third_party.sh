#!/bin/sh
# Download the third-party inputs that this package does not redistribute (their terms do not allow it,
# or name no licence), and check them against the SHA-256 of the files used for the published results.
#
# Usage (from the repository root):  sh data/raw/fetch_third_party.sh
#
# Needed to run the pipeline:
#   data/raw/tax_rates/taxfoundation_cit_rates_1980-2023.xlsx   Tax Foundation, statutory CIT rates 1980-2023
#       (step 1 fills the CIT rates the OECD does not publish; Figures 2.6 and 2.7 of the report)
# Needed for the firm-level results (src/firm_level/) and the chapter tables built on them:
#   data/raw/firm_level/taxplorer_data_2026-10-17.json          EU Tax Observatory, Taxplorer database
#       Taxplorer updates data.json and serves only its current version. The published results use the
#       version of 17 October 2026, downloaded on 21 October 2026 (checksum below). A download today is a
#       newer version: the script then warns, and the firm-level results differ from the published ones.
#
# Not fetched here (download by hand, see data/raw/README.md): the EU Tax Observatory's bank country-by-country
# reports, the UNU-WIDER Government Revenue Dataset, BGS World Mineral Statistics, Orbis.
#
# Author: Tax Justice Network.
set -e
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
fetch() {   # fetch <url> <destination> <sha256>
  url=$1; dst=$2; sha=$3
  if [ -f "$dst" ] && [ "$(shasum -a 256 "$dst" | cut -d' ' -f1)" = "$sha" ]; then echo "ok (present) $dst"; return; fi
  mkdir -p "$(dirname "$dst")"
  if ! curl -sSfL -A "$UA" -o "$dst.part" "$url"; then echo "FAILED $url"; rm -f "$dst.part"; return; fi
  mv "$dst.part" "$dst"
  got=$(shasum -a 256 "$dst" | cut -d' ' -f1)
  if [ "$got" = "$sha" ]; then echo "ok      $dst"; else echo "WARNING $dst: SHA-256 $got differs from the version used ($sha)"; fi
}

fetch "https://taxfoundation.org/wp-content/uploads/2023/12/1980_2023_Corporate_Tax_Rates_Around_the_World_Tax_Foundation.xlsx" \
      data/raw/tax_rates/taxfoundation_cit_rates_1980-2023.xlsx \
      7a295243a3df746b64602e3d3f9e656ec559a56ea9f4d1cce99d9e49e61c2f90

fetch "https://www.taxplorer.eu/data.json" \
      data/raw/firm_level/taxplorer_data_2026-10-17.json \
      815a8574f2b5c66466d59dd72fd720e2e4b3af6f237b5db121e4cd5ac96899ac
