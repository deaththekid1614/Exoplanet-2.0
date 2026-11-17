# 🪐 TESS Transit Detection Pipeline

> CPU-based Python pipeline for finding and checking possible exoplanet transits in NASA TESS light curves. Enter TIC IDs, search the light curves for repeating dips, measure the evidence, and review the final candidate table. The patched run uses physics checks (60%) and a Random Forest score (40%).

---

## 📋 Table of Contents

1. [How It Works](#-how-it-works)
2. [Pipeline Architecture](#-pipeline-architecture)
3. [Physics Checks](#-physics-checks)
4. [Validation Results](#-validation-results)
5. [Quick Start](#-quick-start)
6. [Project Structure](#-project-structure)
7. [Configuration](#-configuration)
8. [Output Files](#-output-files)
9. [Performance Notes](#-performance-notes)
10. [Requirements](#-requirements)
11. [License](#-license)

---

## 🚀 How It Works

You give the pipeline one or more **TIC IDs**. A TIC ID is a number used to identify a star in the TESS Input Catalog. The pipeline looks for that star's TESS brightness measurements, searches for repeating dips, checks the signal, and writes a result.

| Stage | What it does | In simple words |
|---|---|---|
| **1. Prepare light curves** 📥 | Gets TESS light curves through MAST, tries another available data product if needed, cleans invalid measurements, and removes slow brightness trends. | Prepares the star's brightness-over-time data for the search. Previously processed curves are reused from the local cache. |
| **2. Search for transits** 🔍 | Uses BLS to screen periods, TLS to refine promising signals, and harmonic checks to identify possible period aliases. | Looks for a dip that repeats at a regular interval. |
| **3. Look up the star** ⭐ | Checks Gaia DR3, MAST/TIC, and available local catalogues for stellar properties. | Finds information such as the star's radius and temperature when available. |
| **4. Measure physics clues** ⚛️ | Measures depth, shape, secondary events, alternating-event depths, and orbital brightness changes where the data allow. | Checks whether the light-curve signal looks more planet-like or binary-like. |
| **5. Classify candidates** 🤖 | Fits a Random Forest classifier using the versioned, labelled training features. XGBoost is tried if Random Forest fitting raises an error. | Adds a learned planet-support score to the measured evidence. |
| **6. Estimate parameters** 📐 | Fits a transit or eclipse model and estimates parameters such as radius ratio and event timing. | Produces approximate values for inspecting or following up a candidate. |
| **7. Combine results** 🎯 | Applies the patched transit rule and combines physics and ML scores. | Writes the final class, score, and confidence tier. |

The patched runner executes **Stages 1–7** by default. The original project contains Stage 8 visualization/report code, but the patched runner skips it by default.

### What the final labels mean

| Label | Meaning |
|---|---|
| `TRANSIT` | The candidate passed the patched physics detection gate and the Random Forest also supports the planet class. This is a candidate classification, not formal planet confirmation. |
| `ECLIPSING_BINARY` | The measured clues suggest two stars eclipsing one another. |
| `FALSE_POSITIVE` | The available evidence does not support a planet-like transit strongly enough. |
| `UNCERTAIN` | The available evidence is not strong enough to choose another label. It means “needs more evidence,” not “definitely no planet.” |
| **No candidate** | The search did not find a signal that passed its detection settings, so there was no candidate for later stages to classify. |

### How a `TRANSIT` result is selected

The patched rule requires all of these:

1. The harmonic check passes.
2. TLS SDE is **3.0 or higher**. If TLS SDE is missing, BLS SDE must be **10.0 or higher**.
3. The Random Forest planet-support score is **0.50 or higher**.

The final ensemble score combines **60% physics and 40% ML**. Physics has the larger share of that combined score. The ensemble score is a ranking/confidence score; it is not a calibrated probability of discovering a planet. A catalogue match is kept as reference information and cannot force the `TRANSIT` label.

**SDE** means *Signal Detection Efficiency*. It measures how strongly a period-search signal stands out from the other trial periods. A high SDE is useful evidence, but it does not prove that the signal is a planet on its own.

---

## 🏗️ Pipeline Architecture

```text
TIC ID list (CSV or one ID per line)
        |
        v
Stage 1: MAST/TESS data  —  download or reuse cached light curves, clean and detrend
        |
        v
Stage 2: Transit search  —  BLS screen, TLS refinement, harmonic checks
        |
        +---- no candidate found ----> no-candidate outcome for that TIC
        |
        v
Stage 3: Star information —  Gaia DR3 / MAST TIC / local catalogue lookups
        |
        v
Stage 4: Physics checks   —  measured light-curve evidence where coverage allows
        |
        v
Stage 5: ML classification — Random Forest planet-support score
        |
        v
Stage 6: Parameters        — transit/eclipse model fit
        |
        v
Stage 7: Ensemble          — 60% physics + 40% ML and patched transit rule
        |
        v
CSV results in outputs/results/
```

---

## ⚛️ Physics Checks

The active patched version uses these five checks as clues from the measured light curve:

| Check | What it measures | How to understand it |
|---|---|---|
| **Depth and Gaia star radius** 🔭 | Uses transit depth and the measured stellar radius to estimate the companion's rough size with `depth ≈ (companion radius / star radius)²`. | A very large estimated companion is less consistent with a planet. |
| **Transit shape** 📈 | Folds the measurements at the candidate period and compares a flat-bottom transit shape with a V-shaped shape. | A flat-bottom event can support a planet-like signal; a V shape can also occur when stars eclipse each other. |
| **Secondary eclipse** 🌑 | Measures brightness near the expected halfway point in the orbit, one event at a time. | A repeating second dip can support an eclipsing-binary interpretation. |
| **Odd/even depths** 🔁 | Compares the depths of alternating primary events. | Different alternating depths can indicate an eclipsing binary or a period that should be doubled. |
| **Ellipsoidal variation** 🌊 | Fits repeating brightness changes outside the main dip. | Orbital brightness changes can be a clue for a close stellar companion. |

These checks are evidence from the light curve. Together they help rank a candidate; no single check confirms a planet on its own.

---

## 📈 Validation Results

### 🏆 Final Pipeline Performance

The final documented run used the 27 IDs in [`data/final_test.csv`](data/final_test.csv). Predictions were checked against source-catalogue labels.

| Metric | Result |
|---|---:|
| **Overall: transit vs. non-transit** | **95.7% (22/23)** |
| **Planets correctly called `TRANSIT`** | **12/13 (92.3%)** |
| **Eclipsing binaries correctly called `ECLIPSING_BINARY`** | **3/5 (60.0%)** |
| **False-positive subtype accuracy** | **Not measured: no verified FP subtype examples in this test** |
| **Known non-transiting targets called `TRANSIT`** | **0/10** |
| **Candidate detection** | **26/27** |
| **Ensemble weighting** | **Physics 60% / ML 40%** |

### 🧪 Test: 27-TIC Source-Labelled Run

| Measure | Result |
|---|---:|
| Total TIC IDs | 27 |
| Light curves processed | 27/27 |
| Candidates found | 26 |
| Targets with decisive source labels | 23/27 |
| Pipeline predictions | 12 `TRANSIT`, 7 `ECLIPSING_BINARY`, 7 `UNCERTAIN`, 0 `FALSE_POSITIVE` |
| Confirmed planets correctly detected as `TRANSIT` | **12/13**; one had no candidate |
| Labelled eclipsing binaries correctly classified | **3/5**; two were `UNCERTAIN` |
| Labelled false positives correctly classified as `FALSE_POSITIVE` | **Not measurable from this test's verified subtype labels** |
| Overall transit/non-transit result | **22/23 correct (95.7%)** |
| Transit/non-transit result where a candidate was found | **22/22 correct** |
| Detected planet periods within 1% of reference | **11/12** |

### What these numbers mean

- **Planets:** 12 of the 13 confirmed transiting planets were called `TRANSIT`. The remaining planet had no candidate, so the search missed it.
- **Eclipsing binaries:** 3 of the 5 source-labelled eclipsing binaries were called `ECLIPSING_BINARY`; 2 were marked `UNCERTAIN`.
- **False positives:** the test has non-transiting labels, but it does not have a verified, consistent false-positive subtype set. So it cannot tell us how many false positives were correctly called `FALSE_POSITIVE`. The pipeline made zero `FALSE_POSITIVE` calls in this run.
- **Overall binary result:** 22/23 means deciding “transiting planet” versus “not a transiting planet.” It counts the planet with no candidate as a miss. Four targets without decisive labels are left out. The 22/22 figure includes only labelled targets that produced a candidate.

These results describe this test list; they do not guarantee the same result for every new TIC ID. The full subtype check is **15/18 (83.3%)**: 12 correct planet labels plus 3 correct eclipsing-binary labels. The [validation report](outputs/physics_audit_validation/accuracy_report.md) and [per-TIC results](outputs/physics_audit_validation/catalog_accuracy_crosscheck.csv) contain the source references and detailed comparisons when those generated files are available locally.

---

## ⚡ Quick Start

### 1. Create a Python environment (Windows PowerShell)

From the project directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Create a TIC ID CSV

Save a file such as `data\my_tic_ids.csv` with a `tic_id` header:

```csv
tic_id
98796344
452866790
307809773
```

A plain text file with one TIC ID per line is also accepted.

### 3. Run the patched pipeline

```powershell
python run_pipeline_patched.py --tic-ids data\my_tic_ids.csv
```

Run the included 27-ID validation list with:

```powershell
python run_pipeline_patched.py --tic-ids data\final_test.csv
```

The first run needs internet access to retrieve available light curves from MAST and query stellar catalogues. Processed light curves and Gaia lookups are cached locally for reuse. To run only with already processed local light curves, add `--skip-download`:

```powershell
python run_pipeline_patched.py --tic-ids data\my_tic_ids.csv --skip-download
```

Use this command to see all supported options:

```powershell
python run_pipeline_patched.py --help
```

### Demo mode

The original runner can create artificial demo light curves without downloading TESS data:

```powershell
python run_pipeline.py --demo --demo-n 20
```

Demo results are synthetic and are not real astronomical observations or a real-data accuracy test.

---

## 📁 Project Structure

```text
Exoplanet-main/
├── config/
│   ├── default.yaml                 # Main pipeline settings
│   └── patched_training.yaml        # Separate patched-training settings
├── data/
│   ├── final_test.csv               # 27-ID validation input
│   ├── real_training/               # Labelled data, features, and model files
│   ├── processed/                   # Cached prepared light curves
│   ├── candidates/                  # BLS/TLS candidate tables
│   └── gaia_cache/                  # Cached stellar lookups
├── handoffs/
│   └── handoff_completion.md        # Detailed engineering handoff
├── outputs/
│   └── results/                     # Predictions and parameter CSV files
├── patches/                        # Fixes loaded by patched runner
├── tess_pipeline/
│   ├── stage1_preprocess.py         # Get, clean, and prepare light curves
│   ├── stage2_detect.py             # BLS/TLS search and harmonic checks
│   ├── stage3_gaia.py               # Gaia and stellar catalogue lookup
│   ├── stage4_physics.py            # Physics features and diagnostics
│   ├── stage5_classify.py           # Original classifier entry point
│   ├── stage6_params.py             # Transit/eclipse parameter estimates
│   ├── stage7_ensemble.py           # Original ensemble scorer
│   ├── stage8_visualize.py          # Optional plots and PDF reports
│   └── demo_data.py                 # Synthetic demo light curves
├── LICENSE                         # MIT License
├── README.md                       # Project guide
├── requirements.txt                # Python dependencies
├── run_pipeline.py                 # Original runner
└── run_pipeline_patched.py          # Patched Stages 1–7 runner
```

### Patches loaded by the patched runner

1. `patch_stage1_download_fallback.py` — tries another available MAST light-curve product if the first one cannot be used.
2. `patch_supervised_classifier.py` — uses source-labelled training data, Random Forest, and XGBoost only as a fitting fallback.
3. `patch_scientific_validity.py` — prevents catalogue matches from forcing a class and applies the physics-plus-ML transit rule.
4. `patch_measured_physics.py` — replaces unsupported physics proxies with measured, coverage-aware checks and selects the versioned v3 model files.

Older patches and backup files are kept in `patches/` for comparison; they are not all activated.

---

## ⚙️ Configuration

Main settings are in `config/default.yaml`. The patched runner uses the same default configuration unless you pass another file with `--config`.

| Setting | Current default | What it controls |
|---|---:|---|
| `detection.bls_sde_threshold` | `4.0` | Initial BLS search cutoff. A lower cutoff sends more possible signals to later stages; a higher cutoff is more selective. |
| `detection.period_min` | `0.5` days | Shortest period searched. |
| `detection.period_max` | `27.0` days | Longest period searched. |
| `preprocess.savgol_window_days` | `0.5` days | Time window used to remove slow brightness changes before searching. |
| `preprocess.n_jobs` | `4` | Number of workers used for preprocessing in the default config. |
| `gaia.cache_enabled` | `true` | Reuse saved stellar lookup results. |
| `parameters.bootstrap_iterations` | `100` | Number of repeated fits used for parameter uncertainty estimates. |
| `pipeline.sector` | `null` | Optional TESS sector limit. `null` means use available sectors. |

The final patched transit rule also uses the harmonic, TLS/BLS SDE, and ML thresholds listed in [How It Works](#-how-it-works). The initial BLS cutoff and final transit gate are separate steps: passing BLS only makes a signal a candidate for later checks.

---

## 📊 Output Files

| File or folder | Description |
|---|---|
| `outputs/results/candidate_predictions.csv` | Main output. Contains the final class, candidate period/depth, physics and ML scores, ensemble score, confidence tier, and decision details. |
| `outputs/results/candidate_parameters.csv` | Transit/eclipse model fit and estimated candidate parameters. |
| `outputs/results/ml_predictions.csv` | Stage 5 model scores before the final ensemble decision. |
| `data/candidates/candidates.csv` | Periodic signals returned by BLS/TLS. |
| `data/processed/<TIC_ID>.npz` | Prepared light curve cache for an individual TIC ID. |
| `data/processed/manifest.csv` | TIC IDs processed or reused during Stage 1. |
| `data/gaia_cache/` | Cached stellar catalogue results. |
| `outputs/physics_audit_validation/` | Generated source-label cross-check and validation report, when available. |

Open `candidate_predictions.csv` first to see the final classifications. A TIC with no candidate will not have a candidate row in that file; check the input list and Stage 1/2 logs to see why.

### Useful prediction columns

| Column | Meaning |
|---|---|
| `tic_id` | TESS catalog ID. |
| `period` | Time between repeating events, in days. |
| `depth` | Fraction of measured star light blocked during the dip. |
| `sde` / `tls_sde` | Signal strength reported by BLS / TLS. |
| `physics_composite` | Combined score from physics checks that could be measured. |
| `ml_score` | Random Forest support for the planet class. |
| `ensemble_score` | Combined physics and ML score, weighted 60/40. |
| `final_classification` | Final label such as `TRANSIT`, `ECLIPSING_BINARY`, or `UNCERTAIN`. |
| `confidence_tier` | High, Medium, or Low display tier; not a calibrated probability. |
| `physics_detector_reason` | Says which physical detection gate passed or why it did not. |

---

## 🏎️ Performance Notes

- **CPU only:** a GPU is not required.
- **Cached data:** an existing processed `.npz` light curve avoids downloading and preprocessing it again. BLS/TLS searches still run when the pipeline is rerun.
- **TLS work:** TLS refinement is run on signals that pass the BLS candidate screen, not every possible period for every star.
- **Parallel preprocessing:** the default configuration uses four preprocessing workers. Change `preprocess.n_jobs` in `config/default.yaml` to use fewer workers.
- **Runtime:** depends on the number of TIC IDs, available TESS sectors, cached data, and how many candidates reach TLS and parameter fitting. There is no fixed runtime per target.
- **No candidate:** means the configured search did not return a candidate; it does not prove the star has no planet.

---

## 📦 Requirements

- Python **3.10 or 3.11** (Python 3.11 recommended for Windows setup)
- `numpy`, `scipy`, `pandas`
- `astropy`, `lightkurve`, `transitleastsquares`, `astroquery`
- `scikit-learn`, `xgboost`, `joblib`
- `pyyaml`, `tqdm`
- `matplotlib`, `reportlab` (used by the original visualization/report stage)

Install the dependencies from the project root with:

```powershell
python -m pip install -r requirements.txt
```

---

## 📜 License

This project is provided under the MIT License. See [`LICENSE`](LICENSE) for the full terms.
