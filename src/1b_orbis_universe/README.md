# Step 1b: Orbis group counts (code only)

These scripts build `data/intermediate/extractive/cbcr_universe_presence.csv`: for each headquarters country and market, the number of distinct multinational groups above the country-by-country reporting threshold (consolidated revenue of at least EUR 750 million) that have at least one subsidiary in the market. Step 1a uses these counts in the extrapolation test of the market key (methodology note), as a measure of how many groups are present in a market that the OECD's multinational data do not cover. The estimates do not use them.

The inputs are Orbis flat files of Moody's / Bureau van Dijk (key financials, about 49 GB, and current ownership links, about 13 GB), which are licensed and not included. The derived counts are shipped, so the pipeline runs without these scripts.

| Script | Pass | Output (`data/intermediate/extractive/`) |
|---|---|---|
| `1b_1_financials.py` | 1: groups whose global ultimate owner reports consolidated turnover of at least EUR 750 million | `cbcr_inscope_groups.csv` |
| `1b_2_links_filter.py` | 2: ownership links of those groups (global ultimate owner, 50% control) | `cbcr_links_filtered.tsv` |
| `1b_3_assemble.py` | 2: member entities of each group and their country | `cbcr_universe_entities.csv` |
| `1b_4_presence.py` | 2: distinct groups per headquarters country and market | `cbcr_universe_presence.csv` (shipped) |
| `_paths.py` | shared paths | |

To rebuild, set the paths of the Orbis files at the top of `1b_1_financials.py` and `1b_2_links_filter.py` and run the four scripts in order from the repository root, e.g. `python src/1b_orbis_universe/1b_1_financials.py`.
