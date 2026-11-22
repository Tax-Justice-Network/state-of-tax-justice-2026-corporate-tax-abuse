# %%
"""
Pipeline runner — the resource correction and the estimation: 3_38 → 4 → 5 → 6.

This script runs the resource-correction and estimation part of the pipeline in order: step 3_38, script 4, then
script 5 on the resources-excluded dataset, each run followed by script 6. I run every stage as a subprocess with
the same interpreter and set RUN_DATASET and REPORTED_ONLY as environment variables, so that each run keeps its own
output topic and the exhibit scripts downstream find the outputs.

Without UT_VARIANT, it builds the headline dataset and estimates both samples (reported-only and with imputed
rows). With UT_VARIANT set to a dataset variant (config.DATASET_VARIANTS), it builds that variant's own dataset and
estimates the reported-only sample, and the outputs go to output/variants/<variant>/.

Step 3_38 needs the record-level match of EITI companies to Orbis companies (eiti_company_hq_map.csv), which is not
shipped because Orbis is licensed. Without it, script 4 reads the shipped outputs of 3_38. A dataset variant runs
3_38 only if it switches off company tables that 3_38 reads (res_no_inferred_companies). The package ships the 3_38
outputs of that variant as well.

Section outline (numbers match the cell headings below):
1. Setup.
2. Stage runner.
3. Resource correction.
4. Estimation and consolidation.

Pipeline steps 3_38 to 6 — after 1, 1a and 2 (and f1, f1b), before the exhibit scripts 7a to 10.

Reads:
  data/final/cbcr_main_disaggregated.csv and the extractive inputs   — see scripts 3_38 and 4
Writes:
  data/final/cbcr_main_excl_resource[__<variant>].csv                 — script 4
  output/estimates/… or output/variants/<variant>/estimates/…         — scripts 5 and 6
Usage:
  python src/_run_pipeline.py                                — the headline dataset, both samples
  UT_VARIANT=<variant> python src/_run_pipeline.py           — a dataset variant, reported-only sample

Author: Tax Justice Network.
Last updated: 2026-11-22.
"""
# %% MARK: 1. Setup
import os
import subprocess
import sys
import time
from pathlib import Path

src_dir = Path(__file__).resolve().parent
os.chdir(src_dir)
sys.path.insert(0, str(src_dir))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import UT_VARIANT, DATASET_VARIANTS, RESOURCE_INFERRED_OFF  # noqa: E402

if UT_VARIANT is not None and UT_VARIANT not in DATASET_VARIANTS:
    sys.exit(f"UT_VARIANT={UT_VARIANT} is not a dataset variant; run scripts 5 and 6 directly for it")
ORBIS_MATCH = src_dir.parent / "data" / "intermediate" / "extractive" / "eiti_company_hq_map.csv"


# %% MARK: 2. Stage runner
# RUN_DATASET and REPORTED_ONLY select the run of script 5. A value left over from an earlier shell session would
# change every pass, so I remove them from the environment of the child processes unless this runner sets them.
_SCRUB_ENV = ("RUN_DATASET", "REPORTED_ONLY")


def run(label: str, cmd: list, env_extra: dict | None = None, cwd: str | None = None):
    print(f"\n=== {label} ===", flush=True)
    env = os.environ.copy()
    for k in _SCRUB_ENV:
        env.pop(k, None)
    if env_extra:
        env.update(env_extra)
    # A bare "python" would pick up whatever interpreter comes first on the path, so I run the stages with the
    # same interpreter as this runner.
    if cmd and cmd[0] == "python":
        cmd = [sys.executable] + cmd[1:]
    rc = subprocess.run(cmd, env=env, cwd=cwd)
    if rc.returncode != 0:
        # I stop at the first failure. After a failed stage every later stage would run on stale inputs.
        print(f"  FAILED (rc={rc.returncode}) — aborting pipeline", flush=True)
        sys.exit(rc.returncode)


print(f"WD: {os.getcwd()}  variant: {UT_VARIANT or 'none (headline)'}", flush=True)
print(f"START: {time.strftime('%H:%M:%S')}", flush=True)


# %% MARK: 3. Resource correction
# 3_38 uses paths relative to its own folder, so I run it from that folder.
needs_3_38 = UT_VARIANT is None or "inferred_layers" in RESOURCE_INFERRED_OFF
if needs_3_38 and ORBIS_MATCH.exists():
    run("3_38 resource payments", ["python", "3_38_resource_payments_by_hq_source.py"],
        cwd=str(src_dir / "3_extractive_prep"))
elif needs_3_38:
    print("\n=== 3_38 skipped: no eiti_company_hq_map.csv (Orbis); script 4 reads the shipped 3_38 outputs ===",
          flush=True)
run("script 4 resource correction", ["python", "4_correcting_cbcr_for_resource_payments.py"])


# %% MARK: 4. Estimation and consolidation
# Script 5 on the resources-excluded dataset, each run followed by script 6 on its topic. A dataset variant
# estimates the reported-only sample only.
samples = (True,) if UT_VARIANT else (False, True)
for i, rep in enumerate(samples, 1):
    topic = "unitary_taxation_excl_resource" + ("_reported" if rep else "")
    run(f"script 5 ({i}/{len(samples)}) reported_only={rep}", ["python", "5_estimate_profit_shifting.py"],
        env_extra={"RUN_DATASET": "excl_resource", "REPORTED_ONLY": "1" if rep else "0"})
    run(f"script 6 ({i}/{len(samples)}) {topic}", ["python", "6_consolidate_country_estimates.py", topic])

print(f"\nEND: {time.strftime('%H:%M:%S')}", flush=True)
print("ALL DONE", flush=True)
