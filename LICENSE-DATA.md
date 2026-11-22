# Data licence

## Our compiled data and the outputs of the pipeline — CC BY 4.0

The datasets compiled by the Tax Justice Network for this study are licensed under the [Creative Commons Attribution 4.0 International licence (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/). They are:
- the hand-collected values for GDP, population, tax rates and wages (`data/raw/macro_variables/manual_imputation_values.csv`);
- the extractive-industry tables: resource revenue, foreign headquarters shares, resource tax rates, country parameters, classification fixes, company overrides and exclusions, and the company tables in `data/raw/extractive/source_tables/`;
- the firm-level compilations: the extractions of public country-by-country reports, the public CbCR database and tracker exports, the lines extracted from the Irish registry filings, the headquarters overrides, the hand-collected consolidated revenues and the shares of report lines sold to customers;
- the home-market tables derived from METI and Statistics Canada statistics;
- the context tables of the report: the budget items compared with each country's losses, the German budget cuts, the corporate tax incidence tables and the manifests;
- the files the pipeline writes to `output/` and `data/final/`, as far as they are not subject to third-party terms.

The Corporate Tax Haven Index file (`tjn_cthi_2025_scores.csv`) and the data-portal file (`tjn_portal_unilateral_cross_2024-06.csv`) in `data/raw/country_info/` are Tax Justice Network data that keep their existing terms and are not relicensed here: free to use for non-commercial purposes with attribution; commercial users need a licence from the Tax Justice Network. The data-portal file also contains fields from third parties, which stay under their providers' terms.

The figures these compilations quote from company reports, government documents and statistics remain those of their sources. Files that the pipeline builds from third-party data, such as those in `data/intermediate/`, are also subject to the terms of the data they are built from.

You may share and adapt our compiled data and the outputs of the pipeline for any purpose, provided you give appropriate credit:

> Tax Justice Network (2026), The State of Tax Justice 2026, chapters 2 and 3 (corporate and company-level tax abuse): replication package.

## Third-party data — their own terms

Files from third-party sources remain subject to the terms of their original providers, listed file by file in `data/raw/README.md`. These sources are:
- international organisations: the OECD, the OECD and the WTO jointly (BaTIS), the World Bank, the ILO, the IMF, the Bank for International Settlements, the World Health Organization, the European Central Bank and Eurostat;
- national authorities: the US Bureau of Economic Analysis, Internal Revenue Service and Energy Information Administration, Japan's Ministry of Economy, Trade and Industry, Statistics Canada, the Australian Taxation Office, the Irish Companies Registration Office, the US Securities and Exchange Commission (EDGAR filings), the National Bank of Belgium (filed accounts) and the French Ministry of the Economy (open data on company accounts);
- research institutes and data providers: CEPII, the EITI, ExchangeRate-API (exchange rates), and Moody's / Bureau van Dijk (Orbis), of which only aggregated counts, shares and country pairs are included;
- the companies whose published reports and filings supply the firm-level figures.

They are redistributed here only for replication, and this package is non-commercial. Nothing in this repository relicenses them. Some carry conditions beyond attribution:
- the BaTIS data are under the Open Database License, which applies to the extract and the derived services-trade table as well;
- the European Central Bank's exchange rates may be reused only if they are left unaltered.

Files whose terms do not allow redistribution, or name no licence, are not included: the Tax Foundation tax rates, the EU Tax Observatory's Taxplorer database (CC BY-NC-ND 4.0, whose terms require permission to republish the database) and bank reports, Compustat Global (S&P Global Market Intelligence, via WRDS), the UNU-WIDER Government Revenue Dataset, BGS World Mineral Statistics (the rent table holds only aggregated rent estimates derived from it) and Orbis records. `data/raw/README.md` says where to get them, and `data/raw/fetch_third_party.sh` downloads the Tax Foundation rates and Taxplorer.

## Fonts — SIL OFL 1.1

The bundled Work Sans fonts (`assets/fonts/`) are licensed under the [SIL Open Font License 1.1](https://openfontlicense.org/); see `assets/fonts/OFL.txt`.
