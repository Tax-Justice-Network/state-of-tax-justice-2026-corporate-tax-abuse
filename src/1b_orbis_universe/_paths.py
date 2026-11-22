# %%
"""
1b (shared paths) — Path shim for the Orbis CbCR-universe passes.

This module resolves the data directories, relative to the repository root, that the
step-1b passes share. The passes write to data/intermediate/extractive/, where step 1a
reads the presence matrix, although their output is not an extractive product.

Author: Tax Justice Network (based on the method of García-Bernardo and Janský).
Last updated: 2026-11-23.
"""
# %% MARK: 1. Shared paths
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
RAW = BASE / "data" / "raw"
INTERMEDIATE = BASE / "data" / "intermediate"
EXT_INT = INTERMEDIATE / "extractive"
EXT_INT.mkdir(parents=True, exist_ok=True)
