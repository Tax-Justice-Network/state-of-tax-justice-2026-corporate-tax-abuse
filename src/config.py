# Pipeline configuration.
#
# This file sets the configuration that every script of the pipeline imports.
# Update it before running the analysis for another year and after storing the
# most up-to-date raw data. It has seven sections:
#
#   1. Analysis period
#   2. Project folders
#   3. Output layout
#   4. Constant-dollar conversion
#   5. Raw data files
#   6. Tax-haven lists
#      6.1 Cleaning list
#      6.2 Representation list
#      6.3 Functional list (frozen)
#      6.4 Jurisdictions without a corporate income tax
#   7. Country groups and display names


# %% MARK: 1. Analysis period

# First year of the analysis window.
first_year = 2016

# Number of years to analyse. The window runs from first_year to first_year + n_years − 1.
# Eight years cover FY2016–FY2023, the fiscal years of the OECD Corporate Tax Statistics
# 2026 edition (released 2026-07-21), which added FY2023.
n_years = 8

# Derived year constants. They are the single source of truth for every year list. The
# scripts import them and never re-declare a year literal.
last_year = first_year + n_years - 1                              # 2023
ANALYSIS_YEARS = list(range(first_year, first_year + n_years))    # 2016..2023
EXCLUDE_YEARS = {2020}                # COVID outlier, out of the multi-year window PAPER_YEARS
PAPER_YEARS = [y for y in ANALYSIS_YEARS if y not in EXCLUDE_YEARS]
N_PAPER_YEARS = len(PAPER_YEARS)                                  # 7
WINDOW_LABEL = f"{first_year}–{last_year}"                   # "2016–2023"


# Source-data artefact fingerprint (1b) in 1_clean.correct_source_data_artifacts. I reset a
# cell's headcount when it spikes to more than five times its average in the other years
# while revenue, profit and assets stay flat. This is the fingerprint of a units error, not a
# verified conversion (examples: CZE->WXD 2023 and SAU domestic 2022, 22 flagged keys in the
# 2026-08 vintage). The replacement counts are historical estimates. For foreign partners I
# take the same deduction off the WXD row, so the disaggregation cannot add it back.
# Set to False to keep the raw OECD headcounts.
CORRECT_EMPLOYEE_UNITS_ERRORS = True

# FY2023 US-parent employee jumps (1_clean.correct_us_employees_2023). The OECD/IRS
# FY2023 file puts US groups' foreign headcount at 22.2 million against 16.1 million in
# 2022 (Brazil ×3, Argentina ×4.4, Korea ×2.9 …) while revenue stays flat, and the BEA
# survey of majority-owned foreign affiliates shows a rise of 0.2%. BEA payroll employment
# and the CbCR counts of full-time equivalents and contractors differ, so the replacement
# counts are estimates. I reset a US 2023 cell to its 2022 employees times the BEA growth
# when employees grew by more than the BEA growth plus 0.25 and revenue by less than 25%.
# Set to False to keep the raw OECD headcount.
CORRECT_US_EMPLOYEES_2023 = True
# Listed corrections of individual cells identified as reporting errors
# (1_clean.correct_listed_cell_artifacts, whose docstring has the full list). Examples are the
# BEL→GBR and BEL→NLD holding chain, the SoftBank fund swings in JPN→JEY and JPN→CYM, THA→CHN
# 2023 (CNY entered as US$), CZE domestic employees 2023, AZE→JPN 2022 and ARG 2021-22
# tangible assets, and cash-tax entry errors, which I set to the accrued tax.
CORRECT_LISTED_CELL_ARTIFACTS = True
# JPN→USA 2022–23 holds SoftBank's US fund losses. I correct the cell like the Jersey and Cayman
# SoftBank cells and set its loss panel to the 2017–19 mean. I correct all three SoftBank cells because
# in the pooled OECD data one group's fund losses shrink the profit pool of all Japanese groups (Japan
# 2023: −35.6bn uncorrected against −16.1bn corrected). False = keep the raw US cell.
CORRECT_JPN_USA_SOFTBANK = True
# JPN→SGP 2022–23 and JPN→GBR 2022 hold the same SoftBank-type fund losses. OECD Table VI shows a
# large loss on negative revenue in the smallest group-size band in 2022 (GBR −38.3bn, SGP −11.1bn),
# the fund signature of the Jersey and Cayman cells. I apply the same rule and set the loss panel to
# its own 2017–19 mean (SGP −0.791bn, GBR −4.748bn). The positive panel stays as reported.
# False = keep the raw cells.
CORRECT_JPN_SGP_GBR_SOFTBANK = True
# Parent-year submissions that I drop entirely in 1_clean, before the WXD and ETR construction. The
# country stays in the data as a partner. The Indonesian submissions of 2021-2023 are unreliable
# (rupiah entered as US$, local filings of foreign-parented groups, broken count fields), and Mexico's
# submission of 2020 gives its Venezuelan line and its foreign total in bolivars as if they were US$.
# Peru's submission of 2018 has the Indonesian fault: a foreign total 39 times that of its neighbouring
# years, with lines that look like local filings of foreign-parented groups.
DROP_PARENT_YEARS = {("IDN", 2021), ("IDN", 2022), ("IDN", 2023), ("MEX", 2020), ("PER", 2018)}
# Huge losses booked in tax havens (1_clean.correct_haven_loss_swings). I reset a loss panel of at least
# US$1bn and more than 2.5 times the cell's ordinary loss (holding or valuation losses, the SoftBank
# pattern) to that ordinary loss, which the benchmark below defines. The Total becomes the positive panel
# plus the reset loss panel, and I move the parent's WXD row by the same amount. Without this correction,
# havens such as Luxembourg, Malta and Mauritius appear to gain from unitary taxation, and in 2021 US
# groups' −101bn Luxembourg loss turns the US into a loser. False = keep the raw loss panels.
CORRECT_HAVEN_LOSS_SWINGS = True
HAVEN_LOSS_SWING_MIN_USD = 1e9
HAVEN_LOSS_SWING_MULTIPLE = 2.5
# Ordinary-loss benchmark of the haven loss-swing rule. The cell's own median alone would treat losses that a
# haven books every year as ordinary, so US groups' losses in the Netherlands (−16 to −30bn a year since
# 2017) and in Luxembourg (−16 to −61bn a year) would never be caught. A loss therefore counts as ordinary
# only if it is ordinary both against the cell's other years and against the loss margin of loss panels in
# non-haven countries in the same year (Σ loss ÷ Σ total revenues over all parents), applied to the cell's
# loss-panel revenues. I reset a swing to the smaller of the two ordinary losses.
# The rule uses the frozen TAX_HAVENS_FUNCTIONAL list because it changes numbers. The representation list
# is re-derived from the estimates and would feed back into them. The margin pools only true losses on
# positive revenues, and a reset never deepens a loss.
# Further raw-data fixes in 1_clean:
#   - REMOVE_STATELESS_FROM_WXD: where a reporter's WXD row contains the stateless amount (90 parent-years,
#     e.g. USA 2016–2020 with US$120–204bn), I take it off that row too, so it is never redistributed.
#   - CORRECT_DNK_2023_PANEL_SWAP: Denmark's FY2023 positive and negative profit panels are swapped in the
#     OECD file, and I exchange them back.
REMOVE_STATELESS_FROM_WXD = True
CORRECT_DNK_2023_PANEL_SWAP = True
# Resource-correction switches. Environment variables can override them, so that 3_38 and script 4 can
# produce sensitivity datasets. The defaults give the headline correction.
# RESOURCE_FOREIGN_RESIDUAL sets what happens to the foreign slice of a GRD or manual national total that no
#   documented operator (EITI bilateral or P2G anchor) and no curated manual share covers. With "excess_tax" I
#   split it over the parent countries by their CbCR tax above the statutory rate, then by Orbis HQ shares.
#   With "unassigned" (the default) I assign it to no parent, so there is no strip without documentation.
RESOURCE_FOREIGN_RESIDUAL = __import__("os").environ.get("RESOURCE_FOREIGN_RESIDUAL", "unassigned")

# UK domestic profit, FY2023. The OECD suppresses the domestic FY2023 Total profit of UK
# parents, while their taxes, activity and positive and negative profit panels are published.
# With IMPUTE_UK_DOMESTIC_PROFIT_2023 = True, 1_clean fills the Total
# (src/_uk_domestic_profit_imputation.py), keeps the raw reported-profit column missing and
# flags the filled value as an estimate. The fill is the published FY2023 positive panel (+111.95bn)
# plus the average loss panel of UK_DOMESTIC_PROFIT_RATIO_YEARS (2017–2022, −83.6bn), which gives
# +28.4bn. A higher home profit lowers the UK's estimated gain under unitary taxation, so the fill is
# more conservative than leaving the Total at zero. The fill is fixed to the missing year, so
# extending the analysis does not roll it forward.
IMPUTE_UK_DOMESTIC_PROFIT_2023 = True
UK_DOMESTIC_PROFIT_IMPUTATION_TARGET_YEAR = 2023
UK_DOMESTIC_PROFIT_RATIO_YEARS = tuple(range(2017, 2023))


# %% MARK: 2. Project folders
# I build all paths from this file's own location, so the scripts work no matter
# which directory they are run from.

import sys as _sys
from pathlib import Path as _Path

_src_dir = _Path(__file__).resolve().parent
_project_root = _src_dir.parent

data_raw = str(_project_root / "data" / "raw") + "/"
data_intermediate = str(_project_root / "data" / "intermediate") + "/"
# Intermediate products of the extractive sub-pipeline (EITI-cleaned panels,
# calibrated rent fractions, BGS scaling, combined and per-mineral rents, the
# consolidated royalty panel, HQ shares). The scripts in src/3_extractive_prep/
# produce them.
data_intermediate_extractive = (
    str(_project_root / "data" / "intermediate" / "extractive") + "/"
)
data_final = str(_project_root / "data" / "final") + "/"
# I create the folders the pipeline writes to, which are absent in a fresh copy of the repository.
for _d in ("data/final", "data/intermediate/extractive", "data/intermediate/firm_level", "data/intermediate/gravity"):
    (_project_root / _d).mkdir(parents=True, exist_ok=True)

output_root = _project_root / "output"

# Variant runs. The environment variable UT_VARIANT=<name> sends every output of scripts 5
# and 6 to output/variants/<name>/, which mirrors the normal output/ layout, without touching
# the headline outputs. Each variant is run on the resources-excluded dataset and the
# reported-only sample (run_all.sh):
#   irs15_gate30, irs15_gate   — profit counted as shifted only into low-taxed destinations,
#                                a robustness check of the methodology note (DEST_GATES)
#   mkt_own_jpn, mkt_own_can   — the Japanese or the Canadian groups on their own national
#                                statistics (methodology note, Tables A1 and A3) (HQ_DEST_KEY_FILES)
#   res_no_tax_inference, res_no_inferred_companies, accrued_tax
#                              — sensitivities of the methodology note whose input dataset differs
#                                from the headline dataset (DATASET_VARIANTS)
import os as _os
UT_VARIANT = _os.environ.get("UT_VARIANT", "").strip() or None
if UT_VARIANT:
    output_root = _project_root / "output" / "variants" / UT_VARIANT

# Dataset variants. For these, script 4 writes its own version of the resources-excluded dataset
# (and step 3_38, where it runs, its own resource tables), and script 5 estimates on it:
#   res_no_tax_inference       — without the resource profit inferred from tax rates and taxes paid: the
#                                strip inferred from an effective rate above the statutory rate ("etr_gap")
#                                and the resource-dominated effective-rate floor ("etr_floor")
#   res_no_inferred_companies  — without the company-level resource profit inferred from published
#                                information (the labelled inferred company tables: BRA_inferred_group_anchors
#                                and the PETRONAS rows of MYS, "inferred_layers"). Step 3_38 needs the Orbis
#                                match, so the package ships that step's two outputs for this variant.
#   accrued_tax                — the tax accrued for the current year in place of the tax paid on a cash basis,
#                                in the effective tax rates, the loss cap and the tax that multinationals pay
# Stripped cells keep their employees and sales.
DATASET_VARIANTS = {
    "res_no_tax_inference": dict(resource_inferred_off={"etr_gap", "etr_floor"}),
    "res_no_inferred_companies": dict(resource_inferred_off={"inferred_layers"}),
    "accrued_tax": dict(tax_measure="accrued"),
}
RESOURCE_INFERRED_OFF = set(DATASET_VARIANTS.get(UT_VARIANT, {}).get("resource_inferred_off", ()))
TAX_MEASURE = DATASET_VARIANTS.get(UT_VARIANT, {}).get("tax_measure", "cash")


def variant_path(path):
    """Return the path of a dataset variant's own version of a file: the name with `__<variant>` before the
    extension when UT_VARIANT is a dataset variant, and the path unchanged otherwise."""
    p = _Path(path)
    if UT_VARIANT in DATASET_VARIANTS:
        return p.with_name(f"{p.stem}__{UT_VARIANT}{p.suffix}")
    return p

# Destination gates: profit can be shifted only into the low-taxed jurisdiction-years that
# src/1_clean.py derives from the IRS SOI country-by-country statistics (Table 4).
# `exclude` removes jurisdictions from the destination set.
DEST_GATES = {
    # more than 50% of US groups' positive profit taxed below 15%
    "irs15_gate": dict(file="irs_low_tax_destinations.csv", exclude=()),
    # at least 30% taxed below 15%
    "irs15_gate30": dict(file="irs_low_tax_destinations_ge30.csv", exclude=()),
}
DEST_GATE = DEST_GATES.get(UT_VARIANT)
# Destination keys by variant. The parents a key covers take it in place of the market key
# mne_plus_dds_share, and every other parent keeps the market key. The keys are built by
# src/1a_destination_based_sales.py. mkt_own_jpn and mkt_own_can give the Japanese or the
# Canadian groups the sales pattern that their national statistics (METI, Statistics Canada) show.
HQ_DEST_KEY_FILES = {"mkt_own_jpn": "destination_based_sales_mkt_own_jpn.csv",
                     "mkt_own_can": "destination_based_sales_mkt_own_can.csv"}
HQ_DEST_KEY_FILE = HQ_DEST_KEY_FILES.get(UT_VARIANT)
# Variant runs write script 5's row-level misalignment files only for these formulas, the
# ones the exhibits read. The full-run folders keep all specifications.
VARIANT_MISALIGNMENT_FORMULAS = (
    "sales_employees_destmnedds", "ccctb_destmnedds",
    "three_factors_destmnedds", "double_weighted_sales_destmnedds",
)

# I make the extractive-prep helpers importable from any src/ script (e.g.
# `from _reference_prices import MINERAL_PRICES`). The prep scripts in
# src/3_extractive_prep/ already have that directory on sys.path. This adds it
# for the top-level src/ scripts too, which all do `from config import *`.
_extractive_prep_dir = str(_src_dir / "3_extractive_prep")
if _extractive_prep_dir not in _sys.path:
    _sys.path.insert(0, _extractive_prep_dir)

# I also put src/ itself on the path, for the shared modules at the top of src/
# (e.g. `from _etr_construction import compute_partner_year_etrs`).
_src_dir_str = str(_src_dir)
if _src_dir_str not in _sys.path:
    _sys.path.insert(0, _src_dir_str)


# %% MARK: 3. Output layout
# This section sets the layout of the output/ tree:
#
#   output/
#     paper/            Figures and tables of the exhibit scripts 7a / 7b.
#       main_text/        Reported-only sample.
#       appendix/         Sample with imputed rows (gravity).
#     estimates/        Full estimation output.
#       reported_only/    Main sample: directly reported CbCR rows only.
#       with_imputed_rows/  Full sample: aggregate rows disaggregated by the
#                           gravity model.
#         2_resources_excluded/           the estimates on the resources-excluded data
#     analysis/         Cross-scenario and cross-sample analyses. Each folder is
#                       named for what it shows.
#     extractive/       Resource sub-pipeline outputs.
#     diagnostics/      QA and diagnostics (bootstrap, coverage, outliers).
#     chapter/          State of Tax Justice 2026 chapter outputs.
#
# `output_dirs()` below is the single chokepoint every script writes through.
# The scripts pass flat topic strings, and the two tables below place the files.
# To relocate a folder, edit the mapping here, not the scripts.

_TOPIC_REMAP_EXACT = {
    # Estimation runs: the sample with imputed rows (gravity disaggregation).
    "unitary_taxation_excl_resource": "estimates/with_imputed_rows/2_resources_excluded",
    # Estimation runs: the reported-only sample (main sample).
    "unitary_taxation_excl_resource_reported": "estimates/reported_only/2_resources_excluded",
    # The cross-sample country table of the data-coverage flags (_data_coverage).
    "deliverables/country_sheet": "analysis/country_overview/cross_sample",
}

# ---- ETR construction ----
# The OECD CbCR panel over which I pool the partner-year ETR family. In script 1
# I build the canonical `etr_*_corrected` family on the "Sub-groups with
# positive profits" panel (tax ÷ profit of the sub-groups that actually
# made a profit, the OECD's own positive-profit ETR base). In script 4 I
# build the excl_resource family on the same positive-profit panel. I take
# the cell's resource strip off the positive sub-group's profit and tax,
# capped at that sub-group's values, so the two families share one
# construction. Pooling the "Total (All sub-groups)" cells instead would
# let one large loss cell (Malta's US-parent cell, −$29.6bn in 2020) wipe
# out a partner's pooled base and push the rate to 100% (net losses below
# −100% of current tax for MLT, JEY, IMN, GIB and FRO, and a foreign rate
# of 30% for GBR against a 19% CIT). Both scripts read this constant.
ETR_PROFIT_SUBGROUP = "Sub-groups with positive profits"

# Remap on the first path segment, for topics that may carry a nested sub-topic
# (e.g. "disaggregation/<check>"). Exact matches above win first.
_TOPIC_REMAP_PREFIX = {
    # Diagnostics of script 2.
    "disaggregation": "diagnostics/disaggregation",
}


def _remap_topic(topic: str) -> str:
    """Translate a flat topic name into its nested output location."""
    if topic in _TOPIC_REMAP_EXACT:
        return _TOPIC_REMAP_EXACT[topic]
    head, sep, tail = topic.partition("/")
    if head in _TOPIC_REMAP_PREFIX:
        return _TOPIC_REMAP_PREFIX[head] + (("/" + tail) if tail else "")
    return topic


def output_dirs(topic: str):
    """Return (tables_dir, figures_dir) Path objects for a topic.

    I create both directories on the first call. I remap the flat topic string
    of a script into the nested output layout (see `_TOPIC_REMAP_*` above).
    Usage:

        from config import output_dirs
        TABLES_DIR, FIGURES_DIR = output_dirs("extractive")
    """
    base = output_root / _remap_topic(topic)
    tables = base / "tables"
    figures = base / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    return tables, figures


# Path helper for scripts that read another run's estimation outputs directly
# (writers go through output_dirs). It accepts the sample and scenario names used
# throughout the pipeline and returns the folder under output/estimates/.
ESTIMATES_SAMPLE_DIRS = {
    "reported_only": "reported_only",
    "gravity": "with_imputed_rows",
    "with_imputed_rows": "with_imputed_rows",
}
ESTIMATES_SCENARIO_DIRS = {
    "excl_resource": "2_resources_excluded",
}


def estimates_dir(sample: str, scenario: str) -> _Path:
    """Return output/estimates/<sample>/<scenario> as a Path.

    `sample` and `scenario` may be either the pipeline names ("gravity",
    "excl_resource", …) or the folder names themselves."""
    return (
        output_root / "estimates"
        / ESTIMATES_SAMPLE_DIRS.get(sample, sample)
        / ESTIMATES_SCENARIO_DIRS.get(scenario, scenario)
    )


# %% MARK: 4. Constant-dollar conversion

# US GDP deflator (BEA / FRED GDPDEF, annual average, index 2017 = 100). I use it to
# express multi-year aggregates in constant BASE_YEAR US dollars:
#     value_in_base_usd = value_in_year_nominal × deflator_to_base()[year]
# The 2016–2022 entries are from an earlier BEA vintage. The 2023–2025 entries are
# annual averages computed from FRED GDPDEF quarterly data (all four quarters of
# 2025 observed).
US_GDP_DEFLATOR_2017100 = {
    2016: 98.13, 2017: 100.00, 2018: 102.29, 2019: 104.14,
    2020: 105.36, 2021: 110.22, 2022: 117.99,
    2023: 122.38, 2024: 125.42, 2025: 128.97,
}

# Base year for constant-dollar reporting. Every monetary aggregate in the
# deliverable figures and tables is expressed in constant BASE_YEAR US dollars.
# Change this single constant to rebase the whole study.
BASE_YEAR = 2025


def deflator_to_base(base_year=BASE_YEAR):
    """Return, for each year, the multiplicative factor that converts that year's
    nominal USD to constant `base_year` USD (default BASE_YEAR)."""
    d = US_GDP_DEFLATOR_2017100
    base = d[base_year]
    return {y: base / v for y, v in d.items()}


# %% MARK: 5. Raw data files
# The most up-to-date file names of the raw inputs. I anchor all of them to the
# project root via `data_raw`, so every script runs from any directory.

# CbCR file
## Please give the path to the most recent CbCR file here. The file is the SDMX bulk export of the OECD (about 570 MB):
## https://sdmx.oecd.org/public/rest/data/OECD.CTP.TPS,DSD_CBCR@DF_CBCRI,1.1/all?format=csvfilewithlabels
## Vintages: the 2026-02 file is CTS 2025 (FY2016-2022), and the 2026-08 file is CTS 2026 (FY2016-2023).
cbcr_data = data_raw + "cbcr/oecd_cbcr_tableI_2026-08.csv.gz"

# BEA, US direct investment abroad, majority-owned foreign affiliates,
# employment by country 2022-2023 (thousands). It is the benchmark for the FY2023
# US-parent employee correction (CORRECT_US_EMPLOYEES_2023).
bea_mofa_employment_data = data_raw + "macro_variables/bea_mofa_employment_by_country_2022-2023.csv"

# Saudi Aramco audited figures 2016-2024 (prospectus and annual reports), one row
# per figure with file, page and URL. 1_clean uses them for the FY2021 duplicate
# filing, and 3_38 for the company-anchored resource strip of the Saudi domestic cell.
aramco_financials_data = data_raw + "extractive/source_tables/SAU_aramco_financials_2016_2024.csv"
# Other Saudi CbCR-filing groups (pre-tax sums per year, scenario
# "A_core+borderline"). 1_clean uses them for the FY2023 Saudi artefact.
sau_other_groups_sums_data = data_raw + "extractive/source_tables/SAU_other_groups_yearly_sums_2018_2023.csv"

# CIT rates
## Please give the path to the most recent corporate income tax (CIT) rate data here. The data come from two sources, the OECD for many countries ('Measure: Combined corporate income tax rate'): https://data-explorer.oecd.org/vis?lc=en&fs[0]=Topic%2C1%7CTaxation%23TAX%23%7CCorporate%20tax%23TAX_CPT%23&pg=0&fc=Topic&bp=true&snb=15&df[ds]=dsDisseminateFinalDMZ&df[id]=DSD_TAX_CIT%40DF_CIT&df[ag]=OECD.CTP.TPS&df[vs]=1.0&dq=AUS%2BAUT%2BBEL%2BCAN%2BCHL%2BCOL%2BCRI%2BCZE%2BDNK%2BEST%2BFIN%2BFRA%2BDEU%2BGRC%2BHUN%2BISL%2BIRL%2BISR%2BITA%2BJPN%2BKOR%2BLVA%2BLTU%2BLUX%2BMEX%2BNLD%2BNZL%2BNOR%2BPOL%2BPRT%2BSVK%2BSVN%2BESP%2BSWE%2BCHE%2BTUR%2BGBR%2BUSA%2BALB%2BAGO%2BAND%2BAIA%2BATG%2BARG%2BARM%2BABW%2BAZE%2BBHS%2BBHR%2BGGY%2BBRB%2BBLZ%2BBEN%2BBMU%2BBIH%2BBWA%2BBRA%2BVGB%2BBRN%2BBGR%2BBFA%2BCPV%2BCMR%2BCYM%2BCHN%2BCOG%2BCOK%2BCIV%2BHRV%2BCUW%2BCOD%2BDJI%2BDMA%2BDOM%2BEGY%2BSWZ%2BFRO%2BGAB%2BGEO%2BGIB%2BGRL%2BGRD%2BHTI%2BHND%2BHKG%2BIND%2BIDN%2BIMN%2BJAM%2BJEY%2BJOR%2BKAZ%2BKEN%2BKWT%2BLBR%2BLIE%2BMAC%2BMYS%2BMDV%2BMLT%2BMRT%2BMUS%2BMCO%2BMNG%2BMNE%2BMSR%2BMAR%2BNAM%2BNGA%2BMKD%2BOMN%2BPAK%2BPAN%2BPNG%2BPRY%2BPER%2BPHL%2BQAT%2BROU%2BKNA%2BLCA%2BVCT%2BWSM%2BSMR%2BSAU%2BSEN%2BSRB%2BSYC%2BSLE%2BSGP%2BZAF%2BLKA%2BTHA%2BTGO%2BTTO%2BTUN%2BTCA%2BUKR%2BARE%2BURY%2BUZB%2BVNM%2BZMB.A.CIT_C.ST..S13%2BS1311%2BS13M..&to[TIME_PERIOD]=false&pd=2016%2C2024
# and the Tax Foundation for all others: https://taxfoundation.org/data/global-tax/?_sft_topics=corporate-tax-rates-around-the-world#results (see src/1_clean.py).
cit_data_oecd = data_raw + "tax_rates/oecd_cit_rates_2026-02.csv"
cit_data_taxfoundation = (
    data_raw + "tax_rates/taxfoundation_cit_rates_1980-2023.xlsx"
)

# Wage data
## Please give the path to the most recent ILO wage data "Wages and Working Time Statistics (COND)" here. The data can be downloaded here: https://www.ilo.org/ilostat-files/WEB_bulk_download/indicator/EAR_4MTH_SEX_ECO_CUR_NB_A.csv.gz (see src/1_clean.py).
wage_data = data_raw + "macro_variables/ilo_wages_ear4mth_2025-08.csv"

# GDP and population data
## Please give the path to the most recent GDP and population data from the World Bank here. The data can be downloaded here: https://databank.worldbank.org/source/world-development-indicators/preview/on, selecting the series "GDP (current US$)" and "Population, total" (see src/1_clean.py).
## Note: I take only population from this file. GDP is overridden by the
## canonical WB snapshot below, because this DataBank export is a stale vintage
## that misses WB revisions such as Nigeria's +41% rebasing and Angola.
gdp_population_data = data_raw + "macro_variables/wb_gdp_population_2026-02.csv"

## Canonical GDP: the single GDP per (iso3, year) used across the repository (in
## the CbCR pipeline and as the extractive WB-GDP reference). It is a dated
## snapshot of WB WDI NY.GDP.MKTP.CD in current US$. Refresh it with
## src/_fetch_canonical_gdp.py.
canonical_gdp_data = data_raw + "macro_variables/wb_gdp_current_usd_2026-08.csv"   # 2016-2023

# Data on regions and membership in regional or international organizations
## Tax Justice Network country classification table (the "unilateral cross" data with
## regions and memberships per jurisdiction). It is shipped in data/raw/country_info/.
unilateral_cross_data = data_raw + "country_info/tjn_portal_unilateral_cross_2024-06.csv"

# Exchange rates
exchange_rates_wb = data_raw + "macro_variables/wb_fx_official_rate_2026-02.csv"
# ECB annual averages of the euro reference rates, 2015–2025 (more than 30 currencies per EUR), for the years
# the WB file does not reach yet. Without them the f1 firm panel would convert FY2025 reports at 2024 rates,
# about 4% too low for EUR.
# Source: https://data-api.ecb.europa.eu/service/data/EXR/A..EUR.SP00.A?format=csvdata&startPeriod=2015&endPeriod=2025
# (retrieved 2026-10-23). The rates match the WB EMU row exactly where both exist.
exchange_rates_ecb = data_raw + "macro_variables/ecb_exr_annual_avg_2026-10.csv"

# Consumer Price Index (national CPI, 2010=100). In 1_clean.py I use it to
# extrapolate ILO survey wage observations across the panel years for countries
# where ILO does not provide annual coverage. It is the WB indicator FP.CPI.TOTL,
# downloaded from the WB Open Data API.
cpi_data = data_raw + "macro_variables/wb_cpi_2026-04.csv"

# Destination-based sales inputs (OECD 2020, "Tax Challenges Arising from
# Digitalisation - Economic Impact Assessment", Chapter 2, p. 40 ff.).
# 1a_destination_based_sales.py uses them to build the destination-based-sales
# allocation keys, which script 2 merges into the disaggregated CbCR dataset.
## OECD Analytical AMNE "MNE" file: output, value added and trade split by
## ownership into foreign-owned (F), domestic-owned MNEs (D_MNE) and other
## domestic-owned non-MNE firms (D_OTH). The exports column is EXGR. It is the source of
## the multinationals' local sales (F + D_MNE) in step 1a. http://oe.cd/gvc-mne
## 2026 edition (downloaded 2026-07-23): 2008-2023, 81 countries (it adds AGO,
## ARE, COD and STP). It has real data for 2021 and 2022, so no roll-forward is
## needed there.
aamne_dmne_data = data_raw + "destination_based_sales/oecd_aamne_mne_xvem_2026-07.csv"
## OECD-WTO BaTIS (Balanced Trade in Services), bilateral EBOPS-2010 categories.
## It is the source of the "digitally deliverable services" imports aggregate
## (IMF-OECD-UNCTAD-WTO Handbook definition: SF, SG, SH, SI, SJ, SK1/SK) used by
## the broadened destination-sales measure. I prefer it to the WTO "digitally
## delivered" series, whose definition is unclear and narrower (see the G24
## paper, g24.org "Options for a Protocol on Services under the UNFCITC").
## Downloaded 2026-07-12: BPM6 December-2025 edition bulk CSV (2.8 GB, with
## Reporter/Partner ISO2 and type flags, Flow M/X, Item_code EBOPS, Year, and
## Reported/Final/Balanced value in million USD). The balanced value is the
## reconciled series (notes sheet). I use it with Final_value as the fallback
## per row.
batis_data = (data_raw + "destination_based_sales/"
              "oecd_wto_batis_bpm6_2025-12_extract_dds_imports.csv.gz")
## WB Trade (% of GDP), indicator NE.TRD.GNFS.ZS (API download CSV).
trade_openness_data = data_raw + "macro_variables/wb_trade_pct_gdp_2026-06.csv"
## WB Personal remittances, received (current US$), BX.TRF.PWKR.CD.DT (API CSV).
remittances_data = data_raw + "macro_variables/wb_remittances_received_2026-06.csv"
## WB Net official development assistance received (current US$),
## DT.ODA.ODAT.CD (Databank export, same wide format as the GDP/population file).
oda_data = data_raw + "context/wb_oda_received_2026-06.csv"


# %% MARK: 6. Tax-haven lists
# Three lists, three distinct purposes. The representation and functional
# lists are both strict supersets of the cleaning list, so the lists never
# disagree on a jurisdiction they share:
#
#   6.1 TAX_HAVENS_CLEANING       — drives the dividend correction (changes numbers)
#   6.2 TAX_HAVENS_REPRESENTATION — the "tax_haven" display group (no effect on the headline estimates)
#   6.3 TAX_HAVENS_FUNCTIONAL     — frozen set for the steps that need a haven set (changes numbers)
#
# 6.4 NO_CIT_JURISDICTIONS lists the jurisdictions without a corporate income tax,
# whose gains script 5 values at zero (changes numbers).
#
# Script 5 reads none of the three lists. Which jurisdictions receive shifted
# profit follows from the misalignment (reported profit above the theoretical
# profit), not from a list.

# %% MARK: 6.1 Cleaning list
# This is the exact tax-haven list of García-Bernardo, Janský & Zucman (2026, "Did
# the Tax Cuts and Jobs Act Reduce Profit Shifting by US Multinational Companies?",
# IMF Economic Review, §4), which groups havens — following Reurink &
# García-Bernardo (2020) — into "profit centres" (used mainly for booking
# profit, little production) and "coordination centres" (booking plus
# management and coordination). It drives the García-Bernardo & Janský (2024)
# dividend double-counting correction in 1_clean.py (10% of haven profits,
# non-US MNCs, 2016-2019). Changing it changes the cleaned profit figures, so
# edit it only to track the GB methodology.
_GB_PROFIT_CENTRES = {
    "BMU",  # Bermuda
    "CYM",  # Cayman Islands
    "PRI",  # Puerto Rico
    "JEY",  # Jersey
    "IMN",  # Isle of Man
    "GIB",  # Gibraltar
    "BRB",  # Barbados
    "MUS",  # Mauritius
    "VGB",  # British Virgin Islands
    "BHS",  # Bahamas
    "MLT",  # Malta
}
_GB_COORDINATION_CENTRES = {
    "SGP",  # Singapore
    "NLD",  # Netherlands
    "CHE",  # Switzerland
    "IRL",  # Ireland
    "LUX",  # Luxembourg
    "HKG",  # Hong Kong
}
TAX_HAVENS_CLEANING = _GB_PROFIT_CENTRES | _GB_COORDINATION_CENTRES  # 17 jurisdictions

# 1_clean.py reads the cleaning list under the name `tax_havens` (the GB dividend
# correction).
tax_havens = TAX_HAVENS_CLEANING

# %% MARK: 6.2 Representation list
# This list sets which jurisdictions are shown as the "tax_haven" group in figures
# and tables. It feeds no correction and has no effect on the headline estimates.
# Two uses go beyond the display. The variants irs15_gate30 and irs15_gate count
# the members that the IRS tables never list separately as low-taxed destinations
# (1_clean, section 6.7), and the extrapolation test of the market key in step 1a
# has a sample without the members.
# Rule: the GB cleaning list, unioned with every jurisdiction that
#   (a) has a CTHI-2025 Haven Score of at least 65
#       (data/raw/country_info/tjn_cthi_2025_scores.csv, cthi_2025_score), and
#   (b) booked inward-shifted profit (reported_profit − theoretical_profit > 0)
#       in at least two years of the multi-year window (PAPER_YEARS, excluding 2020)
#       on the headline specification (reported-only / excl_resource /
#       sales_employees_destmnedds / etrdef_domfor / etrmax_inf),
# plus the manual substance keep, the British Indian Ocean Territory (ISO IOT,
# "BIOT", which has no CTHI score).
#
# The GB leg is effectively non-binding. 15 of the 17 GB members pass the outcome
# test on their own (a CTHI score of at least 65 and 4–7 inward-shift years each).
# Only Puerto Rico and Barbados need it. Both have the maximum of 7 out of 7 shift
# years but no CTHI score to compare against 65.
#
# The gate of a CTHI score of at least 65 is what makes the shift test meaningful.
# Inward-shifted profit alone mostly flags headquarter-bias countries (domestic
# over-booking by their own MNEs), such as Canada, Japan, Saudi Arabia, Norway,
# Chile and Israel. For the two unscored members (PRI, BRB) the GB profit-centre
# classification stands in for the missing score.
#
# Notes on membership (2016–2023 window, 7 years excluding 2020): Hungary qualifies
# exactly at the gate of two years (CTHI 69, inward shift in 2016 and 2023). The
# Cook Islands are not included (no CTHI score, no inward-shift year). Saudi Arabia
# is deliberately not included: it has no CTHI score, and about 98% of its excess
# profit is booked at home, which makes it a headquarter-bias country, not a haven.
# The membership below is hard-coded, which is safe because the headline estimates
# do not depend on the list. src/_build_representation_haven_list.py evaluates the
# rule on the headline run and reports any difference.
_EXTRA_CTHI_GE65_2YR_SHIFT = {
    # Legend: ISO code, CTHI-2025 Haven Score, number of inward-shift years (of 7),
    # largest single-year shift (million USD, headline destmnedds estimates). Non-GB
    # members only (GB members that also pass arrive via TAX_HAVENS_CLEANING).
    "MCO",  # Monaco 66, 7 yrs, +764
    "CUW",  # Curaçao 72, 6 yrs, +1,761
    "PAN",  # Panama 72, 5 yrs, +32,518
    "CYP",  # Cyprus 79, 5 yrs, +22,689
    "ABW",  # Aruba 71, 5 yrs, +144
    "SYC",  # Seychelles 70, 5 yrs, +75
    "LBR",  # Liberia 67, 4 yrs, +529
    "GGY",  # Guernsey 100, 4 yrs, +950
    "LIE",  # Liechtenstein 67, 4 yrs, +285
    "AIA",  # Anguilla 100, 3 yrs, +35
    "HUN",  # Hungary 69, 2 yrs (2016, 2023), +9,854  (at the >=2 threshold)
    "ARE",  # UAE 84, 4 yrs (2018, 2021–23), +54,278 — ADNOC does not file in the Emirati
            # domestic CbCR cell, so the resource correction does not strip that cell
}
_EXTRA_MANUAL = {
    "IOT",  # British Indian Ocean Territory — no CTHI / no FSI, kept on substance
}
TAX_HAVENS_REPRESENTATION = (
    TAX_HAVENS_CLEANING | _EXTRA_CTHI_GE65_2YR_SHIFT | _EXTRA_MANUAL
)

# %% MARK: 6.3 Functional list (frozen)
# Three pipeline steps use a haven set functionally. They change numbers, not the
# display:
#   * 1_clean (correct_haven_loss_swings): the rule resets huge losses in the cells
#     of these havens, and its benchmark is the loss margin outside them (script 8
#     reports that margin for the methodology note).
#   * 2_disaggregate: recognised havens are exempt from the per-country
#     imputed-activity caps (2×GDP and 0.5×population), because micro-state
#     havens like Guernsey and the Cook Islands legitimately host activity above
#     GDP.
#   * 4_correcting (resource-dominated ETR floor): havens are excluded from
#     the floor gate. Resource-dominated economies (e.g. Saudi Arabia) must
#     stay out of this set, because haven status here would silently exempt them
#     from the residual-ETR floor that strips their unremoved resource tax.
# The membership is the GB list, 15 jurisdictions with a CTHI 2025 Haven Score of
# 67 or more (rounded) and the substance adds Cook Islands and BIOT. The list is
# frozen: it does not depend on the estimates. The representation list is derived
# from the estimates and would feed back into them.
TAX_HAVENS_FUNCTIONAL = TAX_HAVENS_CLEANING | {
    "GGY", "AIA", "ARE", "CYP", "PAN", "CUW", "LBN", "CRI", "LVA", "ABW",
    "EST", "SYC", "HUN", "LIE", "LBR",   # CTHI 2025 Haven Score of 67 or more (rounded)
    "COK", "IOT",                        # substance adds (not scored by CTHI)
}

# %% MARK: 6.4 Jurisdictions without a corporate income tax
# The tax that multinationals report in these jurisdictions was paid to other
# countries, mostly as withholding tax on payments to entities there. The OECD
# reporting rules assign it to the receiving entity, so it lifts the observed
# effective rate although the jurisdiction itself collects nothing. Script 5
# therefore values the gains of these jurisdictions at zero instead of at their
# effective rate. Jersey, Guernsey and the Isle of Man (which tax financial
# services), the United Arab Emirates and Bahrain (which tax banks or oil
# companies) also have a zero standard rate in the data. Part of their reported
# tax is their own, so they keep their effective rate. So does Gibraltar, which
# levies a corporate income tax although its rate is zero in the manual values.
NO_CIT_JURISDICTIONS = {"CYM", "BMU", "VGB", "BHS", "VUT", "MHL", "AIA", "TCA", "IOT"}


# %% MARK: 7. Country groups and display names

# CbCR aggregate partner codes (continents / world), and their "other" residual
# counterparts. `non_countries` marks every row that is not a real jurisdiction.
aggregated_country_groups = {"W", "A", "E", "F", "S"}
other_country_groups = {"WXD", "A_O", "E_O", "F_O", "S_O", "W_O"}
non_countries = aggregated_country_groups | other_country_groups

# Short, common country names for the deliverable tables. They override pycountry's
# official long names. I chose politically sensitive labels deliberately. Hong Kong
# and Macao are kept standalone (no "China" qualifier), like Taiwan.
COUNTRY_NAME_OVERRIDES = {
    "TWN": "Taiwan", "KOR": "South Korea", "PRK": "North Korea",
    "PSE": "Palestine", "XKV": "Kosovo", "XKX": "Kosovo",
    "COD": "DR Congo", "COG": "Congo (Rep.)",
    "BOL": "Bolivia", "BRN": "Brunei", "IRN": "Iran", "LAO": "Laos",
    "MDA": "Moldova", "RUS": "Russia", "SYR": "Syria", "TZA": "Tanzania",
    "VEN": "Venezuela", "VNM": "Vietnam", "FSM": "Micronesia",
    "VGB": "British Virgin Islands", "VIR": "U.S. Virgin Islands",
}
