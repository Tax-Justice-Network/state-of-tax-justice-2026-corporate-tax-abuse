"""
This module defines the central paths of the project.

Scripts import them with:

    from _paths import BASE, RAW, INTERMEDIATE, EXT_INT, FINAL, ...

Folder convention:
  - RAW          : datasets obtained from elsewhere — external downloads,
                   API pulls, and hand-curated files. Nothing in here is
                   produced by a transformation step in this pipeline.
  - INTERMEDIATE : pipeline working files derived from RAW inputs.
  - EXT_INT      : INTERMEDIATE/extractive — the extractive sub-pipeline's
                   intermediate products (EITI-cleaned panels, calibrated
                   rent fractions, BGS scaling, the combined rents,
                   the consolidated royalty panel, HQ shares, …).
  - FINAL        : the deliverable analysis datasets (cbcr_main_*.csv).

I resolve all paths relative to this file's location, so that the project can be moved or
shared without editing any script. The paths are `Path` objects.
"""

from pathlib import Path

# This file lives at <project_root>/src/3_extractive_prep/_paths.py, so the project root is
# three directories up.
BASE = Path(__file__).resolve().parent.parent.parent

# Canonical subfolders
RAW = BASE / "data" / "raw"
# The resource and extractive raw inputs are grouped under raw/extractive/: the WB rents, EIA,
# BGS, EITI, UNU-WIDER GRD, the manual resource tables and the Orbis extractive extracts.
RESOURCES = RAW / "extractive"
INTERMEDIATE = BASE / "data" / "intermediate"
EXT_INT = INTERMEDIATE / "extractive"
FINAL = BASE / "data" / "final"
OUTPUT_TABLES = BASE / "output" / "tables"
OUTPUT_FIGURES = BASE / "output" / "figures"

EXT_INT.mkdir(parents=True, exist_ok=True)
RESOURCES.mkdir(parents=True, exist_ok=True)
