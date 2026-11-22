# %%
"""
Gravity model — fit the activity model and predict every headquarters–partner pair.

This script fits the first-pass imputation model of García-Bernardo and Janský (2024): one
HistGradientBoostingRegressor per target (log employees, log unrelated-party sales and log tangible
assets), trained on the CbCR cells that are reported country by country. I report the out-of-sample
R² of a 60/40 split (García-Bernardo and Janský report 0.74 / 0.56 / 0.44) and write it to a file,
because the methodology note quotes it. I then refit each model on all observed cells, predict every
pair of the feature matrix and cap the predictions of micro-states. Script 2 uses the predictions as
weights to spread the aggregates of the reporters that give little partner detail.

Section outline (numbers match the cell headings below):
1. Setup.
2. Fit, out-of-sample R² and predictions.
3. Save.

Gravity model, last step — after build_features.py, before script 2.

Reads:
  data/intermediate/gravity/gravity_feature_matrix.parquet — feature matrix (build_features.py)
Writes:
  data/intermediate/gravity/gravity_imputed_activity.csv   — predicted employees, unrelated-party sales and
                                                             tangible assets per (iso_parent, iso_partner, year)
  data/intermediate/gravity/gravity_model_fit.csv          — out-of-sample R² of each target (60/40 split) and
                                                             the number of capped predictions
Usage:
  python src/gravity/impute_model.py

Author: Tax Justice Network (based on the method of García-Bernardo and Janský).
Last updated: 2026-11-23.
"""

# %% MARK: 1. Setup
import os

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import r2_score
from sklearn.model_selection import train_test_split

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GRAVITY_DIR = os.path.join(ROOT, "data", "intermediate", "gravity")
m = pd.read_parquet(os.path.join(GRAVITY_DIR, "gravity_feature_matrix.parquet"))

# Public-feature model. This configuration gives a marginally higher R² than
# García-Bernardo & Janský's per-target hyperparameters. The remaining gap to their R²
# (employees 0.74, sales 0.56) can be attributed to the proprietary LinkedIn variables
# I leave out (their top predictors of employees and sales, which are not publicly
# available).
TARGETS = {
    "employees": ("ln_n_employees", 0.1, 10.0),
    "sales": ("ln_unrelated_party_revenues", 0.1, 10.0),
    "tangible": ("ln_tangible_assets_except_cash", 0.1, 10.0),
}
TEST_SIZE = 0.4
DROP = set(["iso_parent", "iso_partner", "n_employees", "unrelated_party_revenues",
            "tangible_assets_except_cash"] + [t[0] for t in TARGETS.values()])
feat_cols = [c for c in m.columns
             if c not in DROP and pd.api.types.is_numeric_dtype(m[c])]
print(f"{len(feat_cols)} feature columns; {len(m)} rows total")

# %% MARK: 2. Fit, out-of-sample R² and predictions
fit_rows = []
for name, (tgt, lr, l2) in TARGETS.items():
    d = m[m[tgt].notna() & np.isfinite(m[tgt])]
    X, y = d[feat_cols], d[tgt]
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=TEST_SIZE, random_state=0)
    r2 = r2_score(yte, HistGradientBoostingRegressor(
        learning_rate=lr, max_iter=400, l2_regularization=l2,
        min_samples_leaf=20, random_state=0).fit(Xtr, ytr).predict(Xte))
    print(f"  {name:<10} n={len(d):>6}  out-of-sample R2 = {r2:.3f}")
    # I refit on all observed cells and then predict every pair.
    final = HistGradientBoostingRegressor(
        learning_rate=lr, max_iter=400, l2_regularization=l2,
        min_samples_leaf=20, random_state=0,
    ).fit(X, y)
    raw = tgt.replace("ln_", "")
    pred = np.clip(np.expm1(final.predict(m[feat_cols])), 0, None)

    # ---- Micro-state guardrail ----
    # Script 2 uses these predictions only as redistribution weights within each
    # (year, parent, aggregate). A micro-state with an implausibly large predicted value
    # would therefore grab an outsized share of a disaggregated aggregate, which gives a
    # huge imputed profit (Micronesia, American Samoa and the Cook Islands are the worst
    # offenders without a cap). I cap each (parent, partner) prediction at the larger of
    # two ceilings, so that the cap binds only on markets that are tiny on both:
    #   (a) CAP_MULT × the market's largest observed value for this factor
    #       (this keeps real havens — CYM/BMU/… — whose observed cells are large), and
    #   (b) an economic-size ceiling: SALES/ASSETS ≤ GDP_MULT × GDP_d, EMPLOYEES
    #       ≤ POP_FRAC × population_d (this keeps real but sparsely reported economies
    #       such as low-income countries, whose GDP dwarfs their thin CbCR footprint).
    # gdp_d and pop_d are in thousands (CEPII units), so I multiply them by 1000 to get
    # US dollars and persons.
    # A market that is tiny on both dimensions (a true micro-state) is clamped. The point
    # estimates of low-income countries are essentially untouched because (b) is generous
    # for them.
    CAP_MULT, GDP_MULT, POP_FRAC = 10.0, 3.0, 0.5
    obs_cap = (CAP_MULT * m["iso_partner"].map(m.groupby("iso_partner")[raw].max())
               ).to_numpy(dtype=float)
    if name == "employees":
        size_cap = (POP_FRAC * m["pop_d"] * 1e3).to_numpy(dtype=float)
    else:
        size_cap = (GDP_MULT * m["gdp_d"] * 1e3).to_numpy(dtype=float)
    with np.errstate(invalid="ignore"):
        cap = np.nanmax(np.vstack([obs_cap, size_cap]), axis=0)  # NaN only if both NaN
    cap = np.where(np.isfinite(cap), cap, np.nanquantile(cap, 0.10))
    capped = pred > cap
    pred = np.where(capped, cap, pred)
    m["pred_" + raw] = pred
    print(f"  {name:<10} guardrail capped {int(capped.sum()):>6} / "
          f"{len(pred)} pairs ({100*capped.mean():.1f}%)")
    fit_rows.append(dict(target=name, variable=tgt, n_obs=len(d), n_train=len(Xtr), n_test=len(Xte),
                         out_of_sample_r2=r2, pairs_predicted=len(pred), pairs_capped=int(capped.sum())))

# %% MARK: 3. Save
PRED_COLS = ["pred_n_employees", "pred_unrelated_party_revenues",
             "pred_tangible_assets_except_cash"]
preds = m[["iso_parent", "iso_partner", "year"] + PRED_COLS].copy()
preds = preds.dropna(subset=["iso_parent", "iso_partner"])
preds.to_csv(os.path.join(GRAVITY_DIR, "gravity_imputed_activity.csv"), index=False)
pd.DataFrame(fit_rows).to_csv(os.path.join(GRAVITY_DIR, "gravity_model_fit.csv"), index=False)
print(f"\nPredicted activity for {len(preds)} pairs -> data/intermediate/gravity/gravity_imputed_activity.csv")
print("Out-of-sample fit -> data/intermediate/gravity/gravity_model_fit.csv")
