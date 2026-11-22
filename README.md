<!-- TITLE AND SUBTITLE -->
<br />
<p align="center">
  <h1 align="center">State of Tax Justice 2026: Corporate and company-level tax abuse</h1>
</p>
<p align="center">Replication package for the estimates of corporate and company-level tax abuse in<br /><b>The State of Tax Justice 2026</b>: chapter 2 ("What the world loses to corporate tax abuse"), chapter 3 ("The companies behind the numbers"), the annex tables and the methodology note on corporate and company-level tax abuse</p>
<p align="center">How much profit multinationals shift away from where their employees and customers are, how much tax revenue each country would gain or lose if multinationals were taxed as single firms (2016–2023), and what the public country-by-country reports of individual companies show</p>

<p align="center">
  <a href="https://taxjustice.net/reports/the-state-of-tax-justice-2026/"><b>📄 Report and methodology notes</b></a> &nbsp;·&nbsp; <a href="https://taxjustice.net/the-state-of-tax-justice-2026-interactive"><b>📊 Results</b></a> &nbsp;·&nbsp; <a href="data/raw/README.md"><b>🗂 Data sources</b></a>
</p>

<br />

<!-- TABLE OF CONTENTS -->
<details open="open">
  <summary><h2 style="display: inline-block">Contents</h2></summary>
  <ol>
    <li><a href="#about-the-project">About the project</a></li>
    <li><a href="#installation">Installation</a></li>
    <li><a href="#data-sources">Data sources</a></li>
    <li><a href="#running-it">Running it</a></li>
    <li><a href="#where-each-figure-and-table-is-written">Where each figure and table is written</a></li>
    <li><a href="#what-a-rerun-reproduces">What a rerun reproduces</a></li>
    <li><a href="#repository-layout">Repository layout</a></li>
    <li><a href="#built-with">Built with</a></li>
    <li><a href="#licence">Licence</a></li>
    <li><a href="#citation">Citation</a></li>
  </ol>
</details>

<br />

<!-- ABOUT -->
## About the project

This repository reproduces the Tax Justice Network's estimates of corporate and company-level tax abuse published in *The State of Tax Justice 2026*: every number, table and figure of chapter 2 ("What the world loses to corporate tax abuse") and chapter 3 (the public country-by-country reports of individual multinationals), the corporate numbers of the executive summary, annex Tables A1 and A3, the figure after the executive summary that compares each country's losses with a budget item of its own, and the methodology note on corporate and company-level tax abuse. The aggregate estimate covers the multinationals in the OECD's aggregated country-by-country reports, about 200 jurisdictions and the fiscal years 2016 to 2023. The company results use the public country-by-country reports of individual groups, mostly for 2023 to 2025.

The method, the data and the results are described in the report and in its methodology notes, both published at [taxjustice.net/reports/the-state-of-tax-justice-2026](https://taxjustice.net/reports/the-state-of-tax-justice-2026/). The results by country and year can be explored in the [interactive report](https://taxjustice.net/the-state-of-tax-justice-2026-interactive). This package holds the code and the data to reproduce them.

The inputs are in `data/raw/`, or, where their own sources are licensed or very large, in `data/intermediate/`. Two third-party files whose terms do not allow redistribution are downloaded by `data/raw/fetch_third_party.sh`. A run of the pipeline reproduces the published results, apart from a few company results that need licensed data (see [What a rerun reproduces](#what-a-rerun-reproduces)).

<br />

<!-- INSTALLATION -->
## Installation

The pipeline needs **Python 3.14** with the packages in `requirements.txt` (the versions used for the published results). With conda:

```sh
conda env create -f environment.yml
conda activate sotj2026_corporate_tax_abuse
```

or, in an existing Python 3.14 environment, `pip install -r requirements.txt`. scikit-learn is pinned exactly, because the gravity imputation is not reproducible across its versions.

Two third-party files may not be redistributed. Download them once, from the repository root:

```sh
sh data/raw/fetch_third_party.sh
```

This fetches the Tax Foundation tax rates (the pipeline needs them) and the EU Tax Observatory's Taxplorer database (needed for the company results), and checks each file against the SHA-256 of the version used.

**Taxplorer is updated regularly, and each update changes the company results.** We downloaded the database (`taxplorer.eu/data.json`) on 21 October 2026. That download is the version of 17 October 2026, which the published company results use. Taxplorer offers only its current version, and no copy of that version is archived, so the script downloads a newer one and prints a checksum warning. The company results of chapter 3 and the methodology note then differ from the published ones. All other results are unaffected.

A full run takes a few minutes on a recent laptop. It writes about 1 GB to `output/` and `data/final/`, so allow about 2 GB of free disk space. No other downloads are needed to reproduce the published results. A few company results also use the licensed Compustat Global data and the EU Tax Observatory's bank reports, which the package does not ship; without them they differ slightly from the published ones (see [What a rerun reproduces](#what-a-rerun-reproduces)).

<br />

<!-- DATA SOURCES -->
## Data sources

All inputs are in [`data/raw/`](data/raw/README.md), which lists each file with its source, vintage and terms.

| Data | Source |
|---|---|
| Profit, tax, revenues, employees and assets of multinationals by headquarters country and partner jurisdiction, fiscal years 2016–2023 | OECD, Corporate Tax Statistics 2026, aggregated country-by-country reports (Table I) |
| Statutory corporate income tax rates | OECD Corporate Tax Statistics; Tax Foundation where the OECD has no rate and for the long series since 1980 (downloaded by `fetch_third_party.sh`); hand-collected values |
| Wages, GDP, population, exchange rates, prices | ILO; World Bank; ECB; US GDP deflator (BEA) |
| Where multinationals' sales go (destination-based sales) | OECD Analytical AMNE database, 2026 edition; OECD-WTO Balanced Trade in Services (BaTIS); World Bank GDP, trade, remittances and aid for the markets AAMNE does not cover |
| Payments of oil, gas and mining companies to governments | EITI company payments and government revenues; operators' payments-to-governments reports; company reports and official statistics compiled by the Tax Justice Network; UNU-WIDER Government Revenue Dataset; World Bank resource rents; EIA; BGS |
| Multinational groups present in each market (extrapolation test of the market key); headquarters of extractive companies | Orbis (Moody's / Bureau van Dijk): derived counts and shares only |
| Profit of US multinationals taxed below 15% | IRS Statistics of Income, country-by-country report statistics (Tables 1B and 4) |
| Sales of Japanese and Canadian multinationals by destination from their national statistics (methodology note, annex Tables A1 and A3) | METI Basic Survey of Overseas Business Activities; Statistics Canada; BEA, activities of US multinational enterprises (the share of cross-border sales to unaffiliated customers); CEPII BACI and BaTIS trade |
| Public country-by-country reports of individual groups | Tax Justice Network extractions, database and tracker; Irish Companies Registration Office filings; EU Tax Observatory's Taxplorer (downloaded by `fetch_third_party.sh`) |
| Consolidated revenue of the groups with public reports | Annual reports, 10-K and 20-F filings collected by hand; SEC EDGAR XBRL company facts; Compustat Global (licensed, not shipped); statutory accounts of two groups' local companies |
| Tax havens | García-Bernardo, Janský and Zucman (2026); Corporate Tax Haven Index 2025 |
| Who owns corporate equity, and who bears the corporate tax (Figure 2.9) | Federal Reserve Distributional Financial Accounts, ONS, ECB, OECD, WID.world, UBS, CBO, JCT, US Treasury and ZEW, compiled by the Tax Justice Network |
| Comparisons of the annex tables and the figure after the executive summary (government health spending, a year of training and a year's wages for all unemployed young people, a budget item under debate in each country) | WHO Global Health Expenditure Database; ILO; Eurostat; OECD Labour Market Programmes; World Bank; ECB and ExchangeRate-API exchange rates; budget items researched by the Tax Justice Network from budgets, parliaments and news media |
| Offshore wealth (for the total losses in annex Table A3 and the figure after the executive summary) | *The State of Tax Justice 2026: Offshore wealth*, replication package (Tax Justice Network) |

<br />

<!-- RUNNING -->
## Running it

1. Download the third-party files (`sh data/raw/fetch_third_party.sh`, see Installation), then run everything from the repository root:

   ```sh
   PY=python sh run_all.sh
   ```

   (set `PY` to the Python of the environment). The script runs the steps in this order and writes a log per step to `output/logs/`:
   1. data preparation: `src/1_clean.py` (country-by-country, tax-rate, macro and IRS data), `src/1a_destination_based_sales.py` (the headline market key, its extrapolation test, and the keys of Japanese and Canadian groups from their own statistics), `src/2_disaggregate_aggregated_values.py` (the sample with imputed rows and the tables of reporting detail), and the public reports (`src/firm_level/f1_build_firm_panel.py`, `src/firm_level/f1b_consolidated_revenue.py --offline`);
   2. resource correction and estimation: `src/_run_pipeline.py` runs `3_38` (only where the Orbis match is present) → `4` → `5` → `6` on the resources-excluded dataset for both samples; then `src/_build_representation_haven_list.py` derives the list of tax havens;
   3. four variant runs of scripts 5 and 6 on the reported-only sample: `UT_VARIANT=irs15_gate30`, `irs15_gate`, `mkt_own_jpn` and `mkt_own_can`;
   4. three sensitivities with their own dataset: `UT_VARIANT=<variant> python src/_run_pipeline.py` for `res_no_tax_inference`, `res_no_inferred_companies` and `accrued_tax` (scripts 4, 5 and 6, reported-only sample);
   5. the scale factors and the formula tables (`src/7a_coverage_scaleup.py`, `src/7b_formula_results.py`);
   6. the figures, tables and numbers of chapter 2 and the methodology note (`src/8_chapter_figures.py`), the company estimates and chapter 3 (`src/9_company_estimates.py`), and the annex tables (`src/10_comparisons.py`).

2. Compare with the published results: [Where each figure and table is written](#where-each-figure-and-table-is-written) lists the file of every figure, table and number of the report and the methodology note.

**Where the replication starts.** Steps 3_11 to 3_36 of the extractive correction are not rerun. Step 3_38 needs the match of EITI companies to Orbis company records, which may not be redistributed; without it `src/_run_pipeline.py` skips the step, and script 4 reads its outputs, which are shipped aggregated to headquarters country × source country × year (`data/intermediate/extractive/`), for the headline dataset and for the sensitivity `res_no_inferred_companies`. Likewise the gravity predictions, the Orbis group counts and the trade matrices are read as shipped (`data/raw/README.md`, "Intermediate files"). Everything else runs from the inputs.

The steps can also be run one by one with the same commands, from the repository root.

To use newer data, replace the files in `data/raw/` and update their names in `src/config.py`. To extend the period, change `n_years` in `src/config.py`.

<br />

<!-- WHERE -->
## Where each figure and table is written

After a run, every number, table and figure of the report's corporate and company parts and of the methodology note on corporate and company-level tax abuse is in one of the files below. The figures carry no titles, notes or sources: the report adds them in its captions. PNG and PDF versions of each figure are written.

### Chapter 2: What the world loses to corporate tax abuse (`src/8_chapter_figures.py`)

| Item | Figure (`output/chapter/figures/`) | Data (`output/chapter/tables/`) |
|---|---|---|
| Figure 2.1 | `figB4_sankey_net_havens_2023` | `sankey_net_havens_2023_keys.csv` |
| Figure 2.2 | `figB7_sankey_tax_only_2023` | `sankey_net_havens_tax_2023_keys.csv` |
| Figure 2.3 | `figB2u_blocs_ut_gains_2023` | `blocs_2023_keys.csv` |
| Figure 2.4 | `figS1_shifted_profit` | `shifted_profit_fig_data.csv`, `tax_losses_by_year.csv` |
| Figure 2.5 | `figS4_tax_losses_2016_rates` | `tax_losses_2016_rates_by_year.csv` |
| Figures 2.6 and 2.7 | `figC9_race_to_the_bottom`, `figC9b_rate_bands_2023_vs_1980` | `cit_long_run_by_year.csv` |
| Figure 2.8 and its footnote | `figC8_irs_low_tax_shares_recipients_2023` | `irs_low_tax_shares_recipients_2023_keys.csv`, `irs_low_tax_share_vs_etr_2023.csv`, `irs_rate_on_profit_below15_by_year.csv` |
| Figure 2.9 | `figC10_who_pays_corporate_tax` | `who_pays_corporate_tax.csv` |
| Every number the chapter text and the executive summary quote from the aggregate data | | `chapter_numbers_2023.csv` (value, unit, the number as printed, where it appears, the table it comes from) |

### Chapter 3: The companies behind the numbers (`src/9_company_estimates.py`)

| Item | Figure (`output/chapter/figures/`) | Data (`output/chapter/tables/`) |
|---|---|---|
| Figure 3.1 | `EU_profit_booked_in_the_hub` | `EU_profit_booked_in_the_hub.csv` |
| Figure 3.2 | `profit_per_employee_companies`, and one panel per company (`<Company>_profit_per_employee`) | `<Company>_profit_per_employee.csv` |
| Table 3.1 | | `table1_eu_estimates_vs_public_reports.csv`, `table1_comparison_stats.csv`, `europe_ut_pcbcr_scaled.csv` |
| Figure 3.3 | `figC8c_pcbcr_rates_too_much_too_little` | `pcbcr_rates_too_much_too_little_eu_ci.csv`, `pcbcr_rates_too_much_too_little_eu.csv`, `pcbcr_rates_too_much_too_little.csv` |
| The averages across all groups, and EU profit by tax-rate band | | `company_averages.csv`, `eu_profit_by_tax_rate.csv` |
| Every company number of the chapter, its notes and the methodology note, with the sample counts | | `company_numbers_in_text.csv` |

The group-by-group estimates behind these results are in `output/analysis/firm_level/tables/` (`firm_cell_misalignment__*.csv`, `firm_year_summary__*.csv`).

### Annex Tables A1 and A3 and the figure after the executive summary (`src/10_comparisons.py`)

The data of these tables are in `output/comparisons/tables/` (US$ million at 2025 prices, 2023): `annex_countries_2023.csv` has one row per jurisdiction with the corporate loss (Table A1), the offshore loss and the total (Table A3), the losses each jurisdiction causes and their share, the comparisons with government health spending and with a year of training and a year's wages for all unemployed young people, the budget item of the figure after the executive summary, and the marks of the tables as flag columns. `annex_totals_2023.csv` has the world, continent and income-group rows, each as the net gain from unitary taxation and as the losses of the losing countries alone, scaled and unscaled. `annex_parameters_2023.csv` holds the parameters the notes of Table A1 quote (the cost of a year of training relative to GDP per head, the scale factor). `losses_caused_own_statistics.csv` gives the rows below Japan and Canada. Table A2 (offshore tax evasion) comes from the companion package on offshore wealth.

### Methodology note

| Item | File |
|---|---|
| Table B1 and Table B2 | `output/diagnostics/disaggregation/tables/reporting_detail_by_year.csv`, `limited_detail_reporters_by_year.csv` (`src/2_disaggregate_aggregated_values.py`) |
| Table B4 | `output/paper/main_text/tables/scaleup_yearly.csv`, `scaleup_yearly__gravity.csv` (`src/7a_coverage_scaleup.py`) |
| Appendix C and Table C1 | `output/diagnostics/haven_loss_swings/haven_loss_swings.csv`, `output/diagnostics/cbcr_profit_imputation/uk_domestic_profit_carryforward.csv` (`src/1_clean.py`) and `methodology_note_numbers.csv` |
| Appendix D: the fit of the gravity model | `data/intermediate/gravity/gravity_model_fit.csv` (shipped input) |
| Figures E1 and E2 | `output/paper/appendix/figures/fig02_taxable_profit_by_income`, `fig03_tax_revenue` (`src/7b_formula_results.py`) |
| Figure E3 | `output/chapter/figures/fig09_origin_dest_revenue_no_nexus` (`src/8_chapter_figures.py`) |
| Tables E1 and E2 | `output/paper/appendix/tables/note_table_e1_profit_shifted_by_formula__gravity.csv`, `note_table_e2_tax_lost_by_formula__gravity.csv` (`src/7b_formula_results.py`) |
| Tables F1 to F3 | `output/paper/main_text/tables/note_table_f1_by_income_group__reported_only.csv`, `note_table_f2_…`, `note_table_f3_…__reported_only.csv` (`src/7b_formula_results.py`) |
| The formula comparison by income group, year and country | `output/paper/{main_text,appendix}/tables/table2_*.csv`, `table3_*.csv` |
| Japan and Canada with their own statistics | `output/chapter/tables/footnote_own_statistics_jpn_can.csv` |
| Profit shifted only into low-taxed destinations; the rule of earlier editions | `output/chapter/tables/gate_robustness_world_by_year.csv`, `classic_rule_etr15_world_by_year.csv` |
| The conservative and optimistic bounds of the world estimate | `output/paper/main_text/tables/fig01_global_revenue_gains_data.csv` |
| The extrapolation test of the market key | `data/intermediate/destination_key_extrapolation_test.csv` (`src/1a_destination_based_sales.py`) |
| The list of tax havens shown in the figures and tables | `output/diagnostics/haven_list_reevaluation/tables/inward_shift_years_by_jurisdiction.csv` (`src/_build_representation_haven_list.py`) |
| The sensitivities without the inferred resource profit and with the tax accrued | `methodology_note_numbers.csv`; the variants' estimates in `output/variants/<name>/` |
| Every other number the note quotes from the run | `output/chapter/tables/methodology_note_numbers.csv` (value, unit, the number as printed, where it appears and its source) |

### Estimates

Amounts in `output/estimates/` and `output/variants/` are in US$ million at current prices of each year, not scaled. The figures and tables above are in constant 2025 US dollars, Table 3.1 in euros.

| Folder or file | Content |
|---|---|
| `output/estimates/reported_only/2_resources_excluded/tables/excl_resource/country_estimates__sales_employees_destmnedds__etrdef_domfor__etrmax_inf__loss_cit_gain_etr.csv` | The headline estimate by country and year: reported and apportioned profit, misalignment, tax lost and tax collected today, net revenue change under unitary taxation (`revenue_gain_from_ut`) |
| `output/estimates/<sample>/2_resources_excluded/tables/` | Every specification, per country and year (`excl_resource/country_estimates__*.csv`), per headquarters × partner cell (`excl_resource/misalignment__*.csv`), consolidated (`summary_country_year_long.csv`), with the list of specifications (`run_summary.csv`); samples `reported_only` (headline) and `with_imputed_rows` |
| `output/variants/<name>/` | The seven variant runs, in the same layout |
| `data/final/` | The analysis datasets: the cleaned reports, the sample with imputed rows and the resources-excluded dataset (one per dataset variant) |

<br />

<!-- REPRODUCES -->
## What a rerun reproduces

A run from a fresh copy reproduces every number of the report's corporate parts and of the methodology note, apart from some company results, which need two inputs that the package does not ship:

- **Compustat Global** (licensed). Without it, `src/firm_level/f1b_consolidated_revenue.py` finds the consolidated revenue of 294 group-years instead of 952. Table 3.1, Figure 3.3, `company_averages.csv` and some rows of `company_numbers_in_text.csv` then differ slightly from the published ones: the public-report total of Table 3.1 for the EU-27 is €81.5 billion instead of €83.5 billion (Germany €32.0 billion instead of €32.4 billion, France €24.3 billion instead of €25.3 billion); the correlations of its two columns are unchanged (0.99, rank correlation 0.82); 168 groups instead of 164 book more profit in the five EU hubs than their activity warrants, and 111 instead of 109 more than twice as much; Denmark's scaled result is −€8.11 billion instead of −€8.13 billion.
- **The EU Tax Observatory's bank country-by-country reports, 2014–2020** (not shipped). 28 groups appear only there, so the panel counts 1,441 groups instead of the 1,469 the chapter reports. Nothing else changes.

The company results also depend on **Taxplorer**, which users download themselves (`data/raw/fetch_third_party.sh`). We downloaded it on 21 October 2026 (version of 17 October 2026). Taxplorer is updated regularly and offers only its current version, so a download today is a later version, and it changes the company results.

PDF and Excel files carry the time they were written, and Excel files can differ in the last decimal places, so compare their values rather than the files.

<br />

<!-- REPO LAYOUT -->
## Repository layout

```
run_all.sh                     <- runs the whole chain (see Running it)
src/
  config.py                    <- analysis period, file names, corrections, tax-haven lists, variants: all settings
  1_clean.py                   <- corrects and merges the country-by-country, tax-rate, macro and IRS data
  1a_destination_based_sales.py <- destination keys: the market key, its extrapolation test, the keys of Japan and Canada
  1b_orbis_universe/           <- Orbis group counts (code only; output shipped)
  2_disaggregate_aggregated_values.py <- spreads continental aggregates (robustness sample); tables of reporting detail
  gravity/                     <- the gravity model of the activity imputation (output shipped)
  3_extractive_prep/           <- extractive payments by headquarters and source country
  4_correcting_cbcr_for_resource_payments.py <- takes out resource profit and tax
  5_estimate_profit_shifting.py <- apportionment and tax revenue
  6_consolidate_country_estimates.py <- consolidates the specifications
  7a_coverage_scaleup.py, 7b_formula_results.py <- scale-up and bounds; formula tables and the note's appendix tables
  8_chapter_figures.py         <- chapter 2 and the methodology note: figures, tables and numbers from the aggregate data
  9_company_estimates.py       <- unitary taxation of each group's public report; chapter 3
  10_comparisons.py            <- annex Tables A1 and A3 and the figure after the executive summary
  firm_level/                  <- the public reports: panel (f1) and consolidated revenue (f1b)
  _run_pipeline.py             <- runs 3_38 -> 4 -> 5 -> 6 for the headline dataset or a dataset variant
  _build_representation_haven_list.py <- derives the list of tax havens shown in figures and tables
  _*.py                        <- shared helpers (effective tax rates, figure style and colours, scale factors, data coverage)
data/raw/                      <- the inputs, with sources and terms (README.md); fetch_third_party.sh downloads the rest
data/intermediate/             <- shipped intermediate inputs (Orbis-derived counts, extractive panels, gravity predictions, trade matrices)
assets/fonts/                  <- Work Sans (SIL Open Font License), used in the figures
```

<br />

<!-- BUILT WITH -->
## Built with

* [Python 3](https://www.python.org/) · [pandas](https://pandas.pydata.org/) · [NumPy](https://numpy.org/) · [Matplotlib](https://matplotlib.org/) · [scikit-learn](https://scikit-learn.org/) · [statsmodels](https://www.statsmodels.org/) · [pycountry](https://github.com/pycountry/pycountry) · [openpyxl](https://openpyxl.readthedocs.io/) · [PyMuPDF](https://pymupdf.readthedocs.io/)

<br />

<!-- LICENCE -->
## Licence

The code is released under the [MIT licence](LICENSE). The data compiled by the Tax Justice Network and the outputs of the pipeline are released under [CC BY 4.0](LICENSE-DATA.md). Third-party data remain under their providers' terms, listed file by file in [`data/raw/README.md`](data/raw/README.md); some of them carry conditions beyond attribution (see `LICENSE-DATA.md`).

<br />

<!-- CITATION -->
## Citation

Tax Justice Network (2026), *The State of Tax Justice 2026*, chapters 2 and 3 (corporate and company-level tax abuse): replication package.

Main sources:
- García-Bernardo, J. and Janský, P. (2024). Profit shifting of multinational corporations worldwide. *World Development* 177, 106527.
- García-Bernardo, J., Janský, P. and Zucman, G. (2026). Did the Tax Cuts and Jobs Act Reduce Profit Shifting by US Multinational Companies? *IMF Economic Review*.
- OECD (2020). *Tax Challenges Arising from Digitalisation – Economic Impact Assessment*. OECD Publishing, Paris.
- OECD (2026). *Corporate Tax Statistics 2026*. OECD Publishing, Paris.
- Tax Justice Network (2026). *A 500-billion-dollar decision for the world*. August 2026.
