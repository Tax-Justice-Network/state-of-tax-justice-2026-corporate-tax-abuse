# Gravity model: activity of the countries that report only aggregates

Some headquarters countries report their multinationals' activity abroad only by continent or as "rest of the world". Script 2 spreads these aggregates over individual countries. The real activity (employees, unrelated-party revenues, tangible assets) of each headquarters–partner pair is predicted with the gravity / machine-learning model of García-Bernardo and Janský (2024), trained on the cells that are reported country by country, with gravity, trade, investment and governance features.

| Script | What it does |
|---|---|
| `fetch_worldbank.py`, `fetch_data360.py`, `fetch_bis.py`, `fetch_cepii.py` | Download the feature sources into `data/raw/gravity/` (World Bank indicators; IMF CDIS and CPIS and the Worldwide Governance Indicators through World Bank Data360; the CEPII Gravity database; `fetch_bis.py` downloads the BIS locational banking statistics, which the features do not use) |
| `build_features.py` | Builds the feature matrix for 2014 to the last analysis year (`--mode update` fills 2022–2023, which the CEPII release does not cover) |
| `impute_model.py` | Fits the model and writes `data/intermediate/gravity/gravity_imputed_activity.csv` and the out-of-sample fit of each target (60/40 split), `data/intermediate/gravity/gravity_model_fit.csv` |
| `_ifs_iso3.py` | Country codes of the IMF data |

The prediction file and the fit file are shipped, because the downloads come to about 1.8 GB and the fit depends on the scikit-learn version (pinned to 1.9.0 in `requirements.txt`). The headline estimate uses the reported-only sample, in which no row is imputed; the imputed rows enter the "with imputed rows" sample and the scale-up of that sample.

To rebuild: `python src/gravity/fetch_worldbank.py` (and the other fetch scripts), then `python src/gravity/build_features.py --mode update` and `python src/gravity/impute_model.py`, from the repository root.
