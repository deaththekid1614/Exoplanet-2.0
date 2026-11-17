# 🪐 TESS Transit Detection Pipeline

> CPU-only pipeline for detecting exoplanet transit candidates from NASA TESS time-series photometry. Downloads light curves via MAST, adds Gaia DR3 stellar context, and classifies candidates with a supervised Random Forest plus XGBoost fit fallback. No GPU required.
---

## Physics checks and limits

TESS light curves support some useful transit-shape checks, but they do not provide every measurement needed to reject false positives. In the patched pipeline, unsupported or placeholder values are omitted from the model and physics score.

| Check | What the available TESS data can support |
|---|---|
| Depth vs. Gaia radius | A rough companion-radius consistency check when stellar parameters are available; it is not a planet confirmation. |
| Ingress/egress shape | A light-curve shape score that can flag V-shaped or grazing events. |
| Secondary eclipse | A search near the expected phase when enough orbital cycles and data are available; otherwise neutral/unavailable. |
| Odd/even depths | A comparison of alternating transit depths when enough events are observed. |
| Ellipsoidal variation | A light-curve modulation check when the signal and coverage support it. |
| Centroid motion | Not currently measured by the patched classifier; placeholder values are excluded. |
| Achromaticity and atmosphere | Not measurable from the single-band TESS photometry used here; proxy values are excluded. |

These checks are evidence for ranking candidates, not substitutes for independent validation or follow-up observations.
---


## 🏗️ Pipeline Architecture

```
MAST (TESS) + Gaia DR3 + Curated Training Labels
        |
        v
Stage 1: Preprocess  —  Download, clean, Savitzky-Golay detrend
        |
        v
Stage 2: Detect      —  BLS screen -> TLS refine
        |
        v
Stage 3: Gaia        —  DR3 cross-match for stellar params
        |
        v
Stage 4: Physics     —  7 validation checks
        |
        v
Stage 5: Classify  —  Supervised Random Forest, with XGBoost fit fallback
        |
        v
Stage 6: Parameters  —  Bootstrap uncertainty estimation
        |
        v
Stage 7: Ensemble    —  Weighted confidence scoring
        |
        v
Stage 8: Visualize   —  Plots + PDF report
```

---

## Physics checks and limits

TESS light curves support transit-shape checks, but they do not provide every measurement needed to reject false positives. In the patched pipeline, unsupported or placeholder values are omitted from the model and physics score. The Stage 4 console table prints `N/A` for unavailable measurements; accompanying status columns explain why.

| Check | What the available data support |
|---|---|
| Depth vs. Gaia radius | A rough size-consistency check when a valid stellar radius is available. |
| Ingress/egress shape | A light-curve shape score that can flag V-shaped or grazing events. |
| Secondary eclipse | A search near the expected phase when coverage is sufficient. |
| Odd/even depths | A comparison when enough events are observed. |
| Ellipsoidal variation | A modulation check when signal and coverage support it. |
| Centroid motion | Unavailable in the patched classifier; not measured. |
| Achromaticity and atmosphere | Unavailable from the single-band TESS photometry used here. |

A candidate is not a confirmed planet; catalogue follow-up or independent validation is still required.
---

## Validation Results

Latest patched 50-TIC benchmark (SDE 4.0 primary, 2.5 rescue) produced 45 candidates. Strict overall class accuracy was 42.0% (21/50). Strict transit recall was 91.7% (11/12), with 35.5% precision (11/31): many nonplanets were called transits. This is a benchmark result, not a blind estimate for arbitrary new TICs. See [the detailed report](outputs/patched_master50_sde4/final_accuracy_report.md).

There are 18 usable labeled feature rows (27 labels total). Leave-One-Out accuracy was 72.2% and balanced accuracy 62.5%. The data do not support an 89% general accuracy claim; expanding and independently validating the training set remains necessary.
---

## ⚡ Quick Start

```bash
# 📦 Install dependencies
pip install -r requirements.txt

# Patched real-TIC pipeline (supervised classifier + catalog period check)
python run_pipeline_patched.py --tic-ids data/tic_ids.csv  # Stage 8 is skipped by default

# 🎲 Demo mode — synthetic data, no network required
python run_pipeline.py --demo --demo-n 200

# 🧪 Validation run — 10 new TIC IDs
python3 -B run_pipeline.py --tic-ids data/test_tic_ids_10.csv --sde-threshold 2.5

# 🧪 Validation run — 20 mixed targets with known labels
python3 -B run_pipeline.py --tic-ids data/test_confirmed_planets.csv --sde-threshold 2.5

# 🚀 Production run — full sector
python run_pipeline.py --tic-ids data/tic_ids.csv --sector 14

# 💾 Resume from cached preprocessing
python run_pipeline.py --tic-ids data/tic_ids.csv --sector 14 --skip-download
```

### Patched classifier notes

`run_pipeline_patched.py` uses Random Forest with XGBoost as a fit-error fallback and combines physics (60%) with ML (40%). Stage 8 plotting and PDF generation are skipped by default; explicitly pass `--stages 1,2,3,4,5,6,7,8` to request them. `transit_screening_flag` is a broad candidate-review marker, not confirmation. Physics checks that the available single-band TESS data cannot measure are shown as unavailable and excluded from scoring. The latest benchmark is in [the validation report](outputs/patched_master50_sde4/final_accuracy_report.md).
---

## 📁 Project Structure

```
tess-transit-pipeline/
├── config/
│   └── default.yaml              # ⚙️ Pipeline parameters
├── data/
│   ├── processed/                # Detrended .npz files
│   ├── candidates/               # BLS+TLS detection outputs
│   ├── gaia_cache/               # Cached stellar parameters
│   ├── training/                 # Curated label CSVs
│   ├── test_tic_ids_10.csv       # 10-target blind test set
│   └── test_confirmed_planets.csv # 20-target mixed validation set
├── models/                       # Trained XGBoost + scalers
├── outputs/
│   ├── results/                  # candidate_predictions.csv
│   ├── plots/                    # Per-candidate diagnostics
│   └── reports/                  # PDF summary report
├── tess_pipeline/
│   ├── stage1_preprocess.py      # 📥 Download, clean, detrend
│   ├── stage2_detect.py          # 🔍 BLS screen + TLS refine
│   ├── stage3_gaia.py            # ⭐ Gaia DR3 cross-match
│   ├── stage4_physics.py         # ⚛️ 7 physics checks
│   ├── stage5_classify.py        # 🤖 base ML classifier; patched runner uses RF + XGBoost fallback
│   ├── stage6_params.py          # 📐 Bootstrap parameter fitting
│   ├── stage7_ensemble.py        # 🎯 Confidence scoring
│   ├── stage8_visualize.py       # 📊 Plots + PDF generation
│   └── demo_data.py              # 🎲 Synthetic test data
├── run_pipeline.py               # 🚀 Main entry point
└── requirements.txt              # 📦 Python dependencies
```

---

## ⚙️ Configuration

Pipeline behavior is controlled via `config/default.yaml`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `bls.sde_threshold` | 7.0 | Minimum BLS Signal Detection Efficiency |
| `detrend.sg_window` | 0.5 days | Savitzky-Golay smoothing window |
| `ensemble.ml_weight` | 0.40 | ML contribution to final score |
| `ensemble.physics_weight` | 0.60 | Physics contribution to final score |
| `classify.threshold_transit` | 0.65 | Score threshold for TRANSIT label |
| `classify.threshold_uncertain` | 0.35 | Score threshold for UNCERTAIN label |

---

## 📊 Output Files

| File | Description |
|------|-------------|
| `outputs/results/candidate_predictions.csv` | Final classifications with confidence scores |
| `outputs/results/candidate_parameters.csv` | Fitted transit parameters and uncertainties |
| `outputs/plots/candidates/{tic_id}/` | Diagnostic plots per candidate |
| `outputs/reports/pipeline_report.pdf` | Summary methodology and results report |

---

## 🏎️ Performance Notes

- **Batch processing:** Stage 1 handles 100 curves per batch to manage memory.
- **Parallel BLS:** 4 worker threads via `joblib`.
- **TLS optimization:** TLS runs only on BLS candidates, not the full sector.
- **Centroid sampling:** Computed only for the top 10% of candidates by SDE.
- **Memory hygiene:** `plt.close()` after every figure to prevent RAM accumulation.
- **No GPU required:** XGBoost trains in under 30 seconds on a modern CPU.

### Estimated Runtime (per TESS sector, CPU-only)

| Stage | Estimated Time |
|-------|---------------|
| 1. Preprocess | 4–6 hours |
| 2. BLS + TLS | 4–7 hours |
| 3. Gaia cross-match | 1–2 hours |
| 4–7. Physics + ML + Ensemble | ~15 minutes |
| 8. Plots (top 100 candidates) | ~10 minutes |


---

## 📦 Requirements

- Python 3.8+
- lightkurve
- astropy
- transitleastsquares
- harmonica
- scikit-learn
- xgboost
- matplotlib
- reportlab
- pandas, numpy, scipy
- joblib

See `requirements.txt` for pinned dependency versions.

---

#   E x o p l a n e t - 2 . 0  
 