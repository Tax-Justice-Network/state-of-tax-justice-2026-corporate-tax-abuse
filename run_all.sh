#!/bin/sh
# Run the whole chain of the SOTJ 2026 corporate-tax-abuse results: the estimates, and every figure, table and number of
# the report's corporate and company parts and of the methodology note.
# Run from the repository root:  PY=/path/to/python sh run_all.sh
# Logs go to output/logs/.
set -e
PY=${PY:-python}
export PY
mkdir -p output/logs data/final data/intermediate/extractive data/intermediate/firm_level
step() { name=$1; shift; echo "$(date '+%H:%M:%S') START $name"; "$@" > "output/logs/$name.log" 2>&1 || { echo "FAILED: $name (see output/logs/$name.log)"; exit 1; }; echo "$(date '+%H:%M:%S') DONE  $name"; }
# a variant run of scripts 5 and 6 on the headline dataset: reported-only sample (outputs in output/variants/<name>/)
variant() { sh -c "cd src && UT_VARIANT=$1 RUN_DATASET=excl_resource REPORTED_ONLY=1 \"$PY\" 5_estimate_profit_shifting.py && \
                   UT_VARIANT=$1 \"$PY\" 6_consolidate_country_estimates.py unitary_taxation_excl_resource_reported"; }
# a dataset variant: its own resources-excluded dataset (script 4), then scripts 5 and 6 on the reported-only sample
dataset_variant() { sh -c "UT_VARIANT=$1 \"$PY\" src/_run_pipeline.py"; }
# environment variables that would change the runs
unset UT_VARIANT RUN_DATASET REPORTED_ONLY RESOURCE_FOREIGN_RESIDUAL

# 1. data preparation: country-by-country, macro and IRS data; the destination keys (the headline market key and the
#    keys of the Japanese and Canadian groups on their own statistics); the disaggregated sample; the public
#    country-by-country reports
step 1_clean            "$PY" src/1_clean.py
step 1a_destination_keys "$PY" src/1a_destination_based_sales.py
step 2_disaggregate     "$PY" src/2_disaggregate_aggregated_values.py
step f1_firm_panel      "$PY" src/firm_level/f1_build_firm_panel.py
step f1b_consolidated   "$PY" src/firm_level/f1b_consolidated_revenue.py --offline

# 2. resource correction and estimation: 4 -> (5 -> 6) on the resources-excluded dataset, both samples;
#    the derivation of the list of tax havens used in the figures and tables
step pipeline           "$PY" src/_run_pipeline.py
step haven_list_check   "$PY" src/_build_representation_haven_list.py

# 3. variant runs of the methodology note: profit shifted only into low-taxed destinations; the Japanese or the
#    Canadian groups on their own national statistics (also Tables A1 and A3 of the report)
step variant_irs15_gate30 variant irs15_gate30
step variant_irs15_gate   variant irs15_gate
step variant_mkt_own_jpn  variant mkt_own_jpn
step variant_mkt_own_can  variant mkt_own_can

# 4. sensitivities of the methodology note with their own dataset: without the resource profit inferred from tax rates
#    and taxes paid, without the inferred company-level resource profit, and with the tax accrued in place of the tax
#    paid
step variant_res_no_tax_inference      dataset_variant res_no_tax_inference
step variant_res_no_inferred_companies dataset_variant res_no_inferred_companies
step variant_accrued_tax               dataset_variant accrued_tax

# 5. scale factors and the formula tables
step 7a_scaleup         "$PY" src/7a_coverage_scaleup.py
step 7b_formulas        "$PY" src/7b_formula_results.py

# 6. the chapter and the methodology note, the company estimates and the annex tables
step 8_chapter_figures  "$PY" src/8_chapter_figures.py
step 9_company_estimates "$PY" src/9_company_estimates.py
step 10_comparisons     "$PY" src/10_comparisons.py
echo "done: estimates in output/estimates/ and output/variants/, figures and tables in output/chapter/, output/paper/ and output/comparisons/"
