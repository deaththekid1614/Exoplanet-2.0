# Exoplanet Detection Pipeline — Completion Handoff

**Workspace:** `E:\IDE\Exoplanet-main`  
**Handoff date:** 2026-11-17  
**Purpose:** Record what was changed, what was run, what the reported results mean, and what remains unverified.

## 1. Goal and honest outcome

The requested goal was to improve the patched TESS pipeline so it finds transit candidates using measured physical evidence and then uses ML to help classify transit-like signals. This update improves the diagnostics and makes their availability explicit. It does **not** establish that arbitrary TIC IDs can be classified at 89% accuracy. The available labelled set is small and its development batch had already been reviewed during prior tuning.

The preferred current snapshot is:

- **End-to-end out-of-fold accuracy:** 22/25 = **88.0%**, on a small internal cross-validation set after applying the physics gate to out-of-fold ML scores.
- **Development comparison excluding direct training TIC overlaps:** 13/14 = **92.9%**; 9/10 known planets were called `TRANSIT`, and 0/4 known non-transiting systems were called `TRANSIT`.
- **Exact three-class result:** 15/18 = **83.3%**; exact eclipsing-binary subtype match was 3/5 = **60.0%**.

The 13/14 batch result is **not an independent holdout**: the batch was reviewed during earlier development and labels informed the physics audit. There are only four labelled non-transiting examples outside direct training overlap, which is not enough to establish a dependable false-positive rate. These results must not be described as guaranteed performance on unseen TIC IDs.

## 2. Current patched execution flow

`run_pipeline_patched.py` applies the active patches and calls the existing `run_pipeline` entry point. By default, it runs Stages 1–7 and skips Stage 8 report/plot generation.

| Stage | Role in this project | Current notes |
|---|---|---|
| 1 | Retrieve TESS light curves | Active download fallback patch can try alternate MAST products if the preferred product is absent or unusable. |
| 2 | Clean/process light curves and search for periodic dips | Uses the existing BLS/TLS search. The default config has BLS SDE threshold 4.0; the final patched transit decision also has its own stricter gate below. |
| 3 | Build candidate records / obtain supporting catalogue data | Existing pipeline stage; catalogue data are not used to force the class label. |
| 4 | Extract physical diagnostics | Updated measured, coverage-aware checks described in section 4. |
| 5 | Train/apply supervised classifier | Uses the versioned v3 labels/features/model paths. Random Forest is the primary model; XGBoost is the fit-error fallback. |
| 6 | Estimate candidate parameters | Existing stage remains in the normal flow. |
| 7 | Combine physics and ML and write classifications | Patched 60/40 score and explicit `TRANSIT` admission gate. |
| 8 | Generate visual/report artifacts | Skipped by default in the patched runner. Source code remains available in the project. |

No pipeline stage source was removed as part of this documentation cleanup. The README now describes the standard patched run rather than advertising Stage 8 as part of the default path.

## 3. Files changed and added

### Source changes

- `README.md` — restored/rewritten as a concise project introduction, describes the actual patched workflow, command, validation caveats, and physics checks.
- `patches/__init__.py` — activates `patch_measured_physics` after the download, classifier, and scientific-validity patches. The legacy hand-tuned `patch_final_v2` is intentionally not active because its depth rules were found to veto real planets.
- `patches/patch_scientific_validity.py` — removes unsupported synthetic achromaticity/atmosphere/centroid scores from the active calculation; stops archive matches from deciding the classification; applies the final physical detection gate and ML support rule.
- `patches/patch_measured_physics.py` — new measurement and coverage-aware diagnostic patch, including versioned v3 training artifact paths.
- `handoffs/handoff_completion.md` — this record.

The active patch list in `patches/__init__.py` is:

1. `patch_stage1_download_fallback`
2. `patch_supervised_classifier`
3. `patch_scientific_validity`
4. `patch_measured_physics`

Older patches and backup files remain in `patches/` for historical/reference use and are not all active. In particular, the existence of a patch file does not mean the runner applies it.

### Versioned model and data artifacts

Created for the current v3 set, without overwriting the prior generic training files/model:

- `data/real_training/training_labels_physics_v3.csv` — 25 matched source-labelled targets: 13 planet and 12 non-planet.
- `data/real_training/candidate_features_physics_v3.csv` — feature rows for those labels, extracted/recomputed using the patched feature behavior.
- `data/real_training/patched_classifier_physics_v3.joblib` — fitted Random Forest pipeline artifact.
- `data/real_training/patched_validation_physics_v3.json` — LOOCV summary for the v3 candidate-level training table.

Seven source-checked labels were added to the versioned data during the earlier work (one confirmed planet and six non-planet systems). Source attribution and per-target details are recorded in the external-label source CSV and the accuracy cross-check report. Do not copy unverified candidates into the training labels as ground truth.

The user's `data/final_test.csv` was preserved; it is a plain list of TIC IDs and the existing loader accepts one ID per line. The previously user-deleted `data/test_no_planets.csv` remains deleted; it was not restored.

## 4. Physics and classification behavior

### Physics checks

| Diagnostic | Current implementation | Data/interpretation limit |
|---|---|---|
| Depth/radius plausibility | Uses approximate transit relation `depth ≈ (Rp/Rs)^2` and a valid stellar radius to estimate companion size. Small planet-size dips are not penalized just for being smaller than Jupiter; very large inferred companions are down-weighted. | This is a rough screen; blends, grazing geometry, limb darkening, and stellar-radius uncertainty matter. Missing or fallback Sun-like radius is not treated as a measured Gaia radius. |
| Shape | Folds and phase-bins the event and compares flat-bottom trapezoid and V-shaped templates. | Requires repeated, sufficiently sampled events; else NaN/unavailable. |
| Secondary eclipse | Measures event depths per orbit around phase 0.5 against nearby out-of-event baseline, then estimates significance. | Requires at least three measurable secondary events; a missing score is not an observed absence. |
| Odd/even | Measures primary event depths one orbit at a time and compares the two epoch parities with uncertainty. | Requires at least two events in each parity. |
| Ellipsoidal variation | Fits phase-binned first/second orbital harmonics outside the primary transit. | Needs adequate time span, phase coverage, and usable out-of-transit samples. |
| Achromaticity | Explicitly unavailable/NaN. | Single-band TESS data cannot measure color-dependent transit depth. |
| Atmosphere | Explicitly unavailable/NaN. | No spectroscopy is present; proxy values must not be treated as atmospheric measurements. |
| Centroid motion | Explicitly unavailable/NaN when no centroid measurement was run. | Do not infer centroid stability from a placeholder. |

The active physics composite uses available components and renormalizes weights over those measured. It does not invent a passing value for missing color, atmosphere, or centroid evidence. The physics components are screening scores, not calibrated posterior probabilities.

### Final transit admission rule

The patched decision rule requires:

1. `harmonic_test_passed` is true, and
2. either TLS SDE is at least **3.0**, or TLS SDE is missing and BLS SDE is at least **10.0**, and
3. Random Forest `ml_score` is at least **0.50**.

The ensemble score is `0.60 × physics_composite + 0.40 × ml_score`. This score is used for ranking/confidence display, not as a calibrated probability. The extra detector gate and RF support are required for a `TRANSIT` label; physics score alone or a catalogue match cannot force it. A failed/ambiguous detection can remain `UNCERTAIN`, which means evidence is insufficient, not that the object is known to be a non-planet.

## 5. Training and validation details

### Training table

The v3 feature table has **25 rows**: 13 planet labels and 12 non-planet labels. The model patch uses Random Forest as its main estimator, with median imputation and missingness indicators. XGBoost is attempted as a fallback when fitting the primary model raises an error; it is not automatically an ensemble member that boosts every prediction. Fallback folds used in the saved v3 LOOCV evaluation: 0.

The saved `patched_validation_physics_v3.json` reports:

| Evaluation | Value |
|---|---:|
| Method | Candidate-level Leave-One-Out cross-validation |
| Rows | 25 |
| RF accuracy | 21/25 = 84.0% |
| Balanced accuracy | 83.7% |
| End-to-end physics gate + out-of-fold ML accuracy | 22/25 = 88.0% |
| Transit precision for that gated OOF result | 91.7% |
| Transit recall for that gated OOF result | 84.6% |

This is internal validation on a small dataset, not a permanently untouched test set. Do not compare the 88.0% OOF metric with the 92.9% reviewed-batch metric as if they were interchangeable: their sample and evaluation protocols differ.

### Source-labelled batch comparison

The cached 27-TIC batch had 23 decisive binary source labels. Nine labelled targets overlap the model training TICs. The reported table is:

| Population | N | Correct / accuracy | Planet called `TRANSIT` | Known negatives called `TRANSIT` |
|---|---:|---:|---:|---:|
| All labelled targets, including direct training overlap | 23 | 22/23 = 95.7% | 12/13 | 0/10 |
| Excluding all direct training TIC overlaps | 14 | 13/14 = 92.9% | 9/10 | 0/4 |

The second row still is **not blind independent testing**, because this batch was previously reviewed while tuning. Only four non-transiting examples remain in that comparison. These numbers do not establish general performance for any new TIC ID.

For 18 targets with full source subtypes, exact three-way match was 15/18 = 83.3%; EB subtype match was 3/5 = 60.0%. Binary-only literature labels do not support an exact `ECLIPSING_BINARY` versus other false-positive subtype metric.

Known cases to remember from this run:

- TIC `237913194` is a confirmed planet but had no candidate in the saved detection results. Classification cannot recover a signal that the candidate search did not extract.
- TIC `172370679` was called `TRANSIT`, but the selected period did not agree with the catalogue period.
- Therefore, classification accuracy among extracted candidates and end-to-end ability to recover all real planets are different measurements.

## 6. What was actually run

The current validation work was not a new full 27-target download from Stage 1. The run sequence was:

1. Recomputed Stage 4 diagnostics for **26 saved candidates** using cached processed light curves; one of 27 input TICs had no saved candidate.
2. Ran Stage 5 with the versioned training set, then re-applied the patched Stage 7 scoring and classification.
3. Skipped Stage 8.
4. Ran deterministic synthetic diagnostics for:
   - plausible small/Earth-size and Jupiter-size depth handling versus very large companion-radius down-weighting;
   - flat-bottom versus V-shaped events;
   - equal versus alternating odd/even event depths;
   - absent versus present secondary eclipse;
   - absent versus present ellipsoidal modulation;
   - insufficient event/coverage behavior returning unavailable values.
5. Ran `py_compile` on the patched runner and patch files; compilation passed.
6. Ran `git diff --check`; it passed, with only expected line-ending normalization notices.

The synthetic checks establish that those code paths behave as designed for constructed inputs. They do not establish astronomical accuracy. The cached extraction means MAST download fallback and fresh Stage 2 recovery were not verified by this exact re-score.

## 7. Reports and outputs

When generated locally, the detailed artifacts referenced by the README are:

- `outputs/physics_audit_validation/accuracy_report.md` — narrative metrics, validation caveats, diagnostic availability, run notes, and sources.
- `outputs/physics_audit_validation/catalog_accuracy_crosscheck.csv` — per-TIC labels, references, and predictions.
- `outputs/physics_audit_validation/candidate_predictions.csv` — re-scored candidates.
- `data/real_training/patched_validation_physics_v3.json` — versioned model LOOCV summary.

`outputs/` is ignored by Git under `.gitignore`; if these output artifacts are absent on another machine or checkout, regenerate them rather than treating README links as bundled datasets.

## 8. Reproduce the standard patched run

From PowerShell in the project root, after activating the project's virtual environment:

```powershell
python -m pip install -r requirements.txt
python run_pipeline_patched.py --tic-ids data/final_test.csv
```

The input can be a CSV with a `tic_id` column or a file with one TIC ID per line. A request can fail to yield a prediction if MAST has no accessible usable light curve, processing fails, or no transit candidate passes the search. Such cases should be reported as extraction/no-candidate outcomes rather than silently counted as classification misses or true negatives, depending on the metric being calculated.

## 9. Remaining work for a defensible accuracy claim

1. Build a larger source-verified dataset with clearly separated planet, EB, and other false-positive labels; 500 diverse examples is a useful initial goal, not a current state.
2. Freeze the model and thresholds before collecting an untouched test set. Keep TICs and preferably host systems disjoint between training and testing.
3. Report candidate extraction/recovery separately from classification among extracted candidates.
4. Expand negative-class coverage and publish confusion matrices with exact denominators, precision, recall, and abstention/`UNCERTAIN` coverage.
5. Validate fresh MAST downloads and the full Stage 1–7 path on varied new TIC IDs.
6. Only add color, atmosphere, or centroid checks when actual multi-band, spectroscopic, or pixel-centroid measurements are supplied.

No metric threshold should be forced by changing labels, excluding errors after seeing the result, or calling a reviewed sample an independent holdout. The right next step for a credible 89% claim is a larger frozen training set and a genuinely untouched test set.

## Latest end-to-end run on `data/final_test.csv` (2026-11-17)

The standard patched command was run on all 27 IDs in `data/final_test.csv`:

```powershell
python run_pipeline_patched.py --tic-ids data/final_test.csv
```

It exited successfully after Stages 1-7. Stage 1 processed 27 local/cached light curves. BLS/TLS were rerun and produced 26 candidates; TIC `237913194` had no BLS candidate. Gaia reported 25 DR3 sources and one MAST TIC source from existing cache entries. Stage 4 processed 26 candidates, Stage 5 trained the v3 Random Forest on 25 labelled rows (saved LOOCV 84.0%), Stage 6 fitted all 26 candidates, and Stage 7 wrote predictions. Stage 8 was skipped.

| Latest run measure | Result | Meaning |
|---|---:|---|
| Input IDs / processed light curves | 27 / 27 | Every row in the test file was processed |
| Candidate detection | 26/27 = 96.3% | One TIC had no BLS candidate; this is a search miss, not a classification decision |
| Predicted candidate classes | 12 TRANSIT, 7 ECLIPSING_BINARY, 7 UNCERTAIN | Output counts; unlabelled objects are not known right or wrong |
| Source-labelled binary comparison, all 23 | 22/23 = 95.7% | Counts the confirmed planet with no candidate as an end-to-end miss |
| Source-labelled targets with candidate outputs | 22/22 = 100% | Transit vs non-transit classification only, conditional on a candidate existing |
| Confirmed planets called TRANSIT | 12/13 = 92.3% | One confirmed planet was missed during candidate extraction |
| Known non-transiting sources called TRANSIT | 0/10 | No false transit among these ten labels; too few for a general guarantee |
| Excluding nine training-overlap TICs | 13/14 = 92.9% | Includes the no-candidate miss; still not independent because this batch informed development |
| Known planet periods within 1% | 11/12 | One detected planet had a substantially mismatched selected period |

The no-training-overlap subgroup contains ten source-labelled planets and four non-transiting targets: 9/10 planets were called `TRANSIT`, none of the four non-transiting targets were called `TRANSIT`, and one planet had no candidate. Among the 13 with predictions, binary classification was 13/13. This is a development comparison, **not blind holdout accuracy**.

TIC `172370679` was classified `TRANSIT` but its selected period was 13.071975 days versus 29.020000 days in the catalogue (54.96% relative error). The class label counted as correct, but the recovered period did not. TIC `237913194` is the confirmed planet with no candidate.

This run used local/cached light curves and cached Gaia lookups. It was a full Stages 1-7 execution and fresh BLS/TLS search, but not a cold-cache MAST-download test. Latest row-level results are in `outputs/results/candidate_predictions.csv`; parameter estimates are in `outputs/results/candidate_parameters.csv`. These generated files are ignored by Git.

For a single row-by-row comparison of the latest classifications, source labels, candidate/period status, and end-to-end correctness, see `outputs/physics_audit_validation/latest_run_crosscheck.csv`.
