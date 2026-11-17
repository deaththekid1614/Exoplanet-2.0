"""Make patched scores use measured TESS evidence and keep catalog labels separate."""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Stage 2 supplies the physical transit gate. The model can confirm a moderate
# physics signal, but cannot create a transit when TLS/harmonics reject it.
MIN_TRANSIT_TLS_SDE = 3.0
MIN_ML_SUPPORT_SCORE = 0.60
PHYSICS_OVERRIDE_SCORE = 0.70

def _as_float(row: pd.Series, name: str, default: float = np.nan) -> float:
    try:
        value = float(row.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if np.isfinite(value) else default


def _physics_score(row: pd.Series) -> float:
    """Renormalize only measured, available components of the 60% physics arm."""
    weights = {
        "det_quality": 0.10,
        "depth_score": 0.15,
        "shape_score": 0.25,
        "nosec_score": 0.15,
        "oddeven_score": 0.20,
        "ellipsoidal_score": 0.15,
    }
    available = []
    for name, weight in weights.items():
        value = _as_float(row, name)
        if np.isfinite(value):
            available.append((float(np.clip(value, 0.0, 1.0)), weight))
    total_weight = sum(weight for _, weight in available)
    if not total_weight:
        return 0.5
    return float(sum(value * weight for value, weight in available) / total_weight)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    try:
        return bool(value) if pd.notna(value) else False
    except (TypeError, ValueError):
        return False


def _score_row(row: pd.Series) -> pd.Series:
    """Apply the fixed 60/40 score without letting catalog matches decide class."""
    import patch_supervised_classifier as classifier

    ml = float(np.clip(_as_float(row, "ml_score", 0.5), 0.0, 1.0))
    physics = _physics_score(row)
    score = float(np.clip(classifier.PHYSICS_WEIGHT * physics + classifier.ML_WEIGHT * ml, 0.0, 1.0))

    tls_sde = _as_float(row, "tls_sde", np.nan)
    bls_sde = _as_float(row, "sde", 0.0)
    harmonic_ok = _truthy(row.get("harmonic_test_passed", False))
    tls_confirmed = tls_sde >= MIN_TRANSIT_TLS_SDE
    # TLS can legitimately fail to refine a strong BLS signal. Keep that
    # fallback only for high-SDE BLS candidates that also pass harmonic checks.
    bls_fallback = not np.isfinite(tls_sde) and bls_sde >= 10.0
    physics_detector_pass = bool(harmonic_ok and (tls_confirmed or bls_fallback))
    physics_detector_reason = (
        "TLS_AND_HARMONIC_PASS" if harmonic_ok and tls_confirmed else
        "HIGH_SDE_BLS_FALLBACK_AND_HARMONIC_PASS" if harmonic_ok and bls_fallback else
        "HARMONIC_REVIEW_REQUIRED" if not harmonic_ok else
        "TLS_SDE_TOO_LOW_OR_UNAVAILABLE"
    )
    physics_override = bool(physics_detector_pass and physics >= PHYSICS_OVERRIDE_SCORE)
    # ML only decides whether an already physics-admitted event is planetary;
    # it cannot promote a BLS/TLS or harmonic failure to TRANSIT.
    ml_supported_transit = bool(physics_detector_pass and ml >= MIN_ML_SUPPORT_SCORE)
    screening_flag = bool(physics_override or ml_supported_transit)
    sec = _as_float(row, "nosec_score")
    odd_even = _as_float(row, "oddeven_score")
    ellipsoidal = _as_float(row, "ellipsoidal_score")
    eb_evidence = any(np.isfinite(x) and x <= 0.25 for x in (sec, odd_even, ellipsoidal))

    if physics_override or ml_supported_transit:
        label = "TRANSIT"
        confidence = score
        classification_basis = "physics_override" if physics_override else "physics_plus_ml"
    elif eb_evidence and ml < 0.60:
        label = "ECLIPSING_BINARY"
        confidence = 1.0 - score
        classification_basis = "physics_eclipsing_evidence"
    elif score <= 0.30 and ml <= 0.25:
        label = "FALSE_POSITIVE"
        confidence = 1.0 - score
        classification_basis = "low_physics_and_ml_support"
    else:
        label = "UNCERTAIN"
        confidence = 0.5 + abs(score - 0.5)
        classification_basis = "insufficient_physics_support"

    if label == "TRANSIT":
        tier = "High" if score >= 0.75 else "Medium" if score >= 0.60 else "Low"
    else:
        tier = "High" if confidence >= 0.85 else "Medium" if confidence >= 0.65 else "Low"

    return pd.Series({
        "ensemble_score": score,
        "final_classification": label,
        "confidence": float(np.clip(confidence, 0.0, 1.0)),
        "confidence_tier": tier,
        "physics_composite": physics,
        "ml_score": ml,
        "transit_screening_flag": screening_flag,
        "transit_screening_score": score,
        "physics_detector_pass": physics_detector_pass,
        "physics_detector_reason": physics_detector_reason,
        "transit_classification_basis": classification_basis,
        "catalog_match_used_for_classification": False,
    })


def apply() -> None:
    import patch_supervised_classifier as classifier
    import tess_pipeline.stage4_physics as physics
    import tess_pipeline.stage7_ensemble as ensemble

    # These three values were synthetic/placeholder outputs, not measurements
    # from the available single-band TESS light curve and TPF centroid data.
    physics.check_achromaticity = lambda depth, teff: {
        "achromaticity_score": np.nan,
        "color_bands_agreement": np.nan,
        "band_depths": {},
    }
    physics.check_atmosphere_proxy = lambda ingress, egress, duration, period: {
        "atmosphere_proxy_score": np.nan,
        "atmosphere_classification": "UNAVAILABLE",
    }
    physics.check_centroid = lambda tic_id, config: {
        "centroid_shift": np.nan,
        "centroid_stable": np.nan,
        "centroid_check_score": np.nan,
    }

    original_secondary = physics.check_secondary_eclipse
    original_ellipsoidal = physics.check_ellipsoidal_variation

    def secondary_if_observable(time, flux, period, t0, alpha=0.05):
        time = np.asarray(time, dtype=float)
        flux = np.asarray(flux, dtype=float)
        valid = np.isfinite(time) & np.isfinite(flux)
        if (not np.isfinite(period) or period <= 0 or valid.sum() < 30
                or np.ptp(time[valid]) / period < 2.0):
            return 0.5
        try:
            return float(original_secondary(time[valid], flux[valid], period, t0, alpha))
        except Exception:
            logger.debug("Secondary-eclipse check unavailable", exc_info=True)
            return 0.5

    def ellipsoidal_if_observable(time, flux, period, t0):
        time = np.asarray(time, dtype=float)
        flux = np.asarray(flux, dtype=float)
        valid = np.isfinite(time) & np.isfinite(flux)
        if (not np.isfinite(period) or period <= 0 or valid.sum() < 100
                or np.ptp(time[valid]) / period < 2.0):
            return 0.5
        try:
            return float(original_ellipsoidal(time[valid], flux[valid], period, t0))
        except Exception:
            logger.debug("Ellipsoidal check unavailable", exc_info=True)
            return 0.5

    physics.check_secondary_eclipse = secondary_if_observable
    physics.check_ellipsoidal_variation = ellipsoidal_if_observable

    original_extract = physics.extract_physics_features

    def extract_measured_features(candidate, config, run_centroid=False):
        result = original_extract(candidate, config, run_centroid=run_centroid)
        if not result:
            return result

        # A generic Sun-like fallback is not a valid stellar-radius measurement.
        if str(candidate.get("query_source", "")).lower() == "sun-like_default":
            result["depth_score"] = np.nan
            result["depth_consistency_score"] = np.nan

        for name in (
            "achromaticity_score", "achrom_score", "color_bands_agreement",
            "atmosphere_proxy_score", "atmos_score", "centroid_shift",
            "centroid_stable", "centroid_score", "centroid_check_score",
        ):
            result[name] = np.nan
        result["atmosphere_classification"] = "UNAVAILABLE"
        result["achromaticity_status"] = "UNAVAILABLE_SINGLE_BAND_TESS"
        result["atmosphere_status"] = "UNAVAILABLE_NO_SPECTROSCOPY"
        result["centroid_status"] = "UNAVAILABLE_NOT_MEASURED"
        result["depth_status"] = (
            "AVAILABLE_GAIA" if np.isfinite(_as_float(pd.Series(result), "depth_score"))
            else "UNAVAILABLE_NO_VALID_STELLAR_RADIUS"
        )

        bls = _as_float(pd.Series(candidate), "sde", 0.0)
        tls = _as_float(pd.Series(candidate), "tls_sde", 0.0)
        result["det_quality"] = float(np.clip((max(bls, 0.0) + max(tls, 0.0)) / 30.0, 0.0, 1.0))
        score_row = pd.Series({**candidate, **result})
        result["physics_overall"] = _physics_score(score_row)
        result["physics_available_components"] = sum(
            np.isfinite(_as_float(score_row, key)) for key in
            ("det_quality", "depth_score", "shape_score", "nosec_score", "oddeven_score", "ellipsoidal_score")
        )
        return result

    physics.extract_physics_features = extract_measured_features

    # The model must not learn from generated pseudo-colour bands, an atmosphere
    # proxy, or the fixed 0.5 centroid placeholder.
    classifier.FEATURES = [
        "depth_score", "shape_score", "nosec_score", "oddeven_score",
        "det_quality", "log_oot_std", "skewness", "log_period", "log_depth",
        "relative_duration", "log_bls_sde", "log_tls_sde", "stellar_radius",
        "stellar_teff", "ellipsoidal_score",
    ]

    def single_thread_rf():
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.pipeline import make_pipeline
        return make_pipeline(
            SimpleImputer(strategy="median", add_indicator=True),
            RandomForestClassifier(
                n_estimators=300, max_depth=5, min_samples_leaf=2,
                class_weight="balanced", random_state=42, n_jobs=1,
            ),
        )

    classifier._new_model = single_thread_rf

    original_ml_runner = classifier.patched_run_ml_classification

    def ml_runner_without_archive_prior(candidates, config, force_retrain=False):
        enabled = bool(config.get("classification", {}).get("catalog_period_check_enabled", False))
        if enabled:
            rows = original_ml_runner(candidates, config, force_retrain)
        else:
            original_lookup = classifier._confirmed_planet_periods
            classifier._confirmed_planet_periods = lambda tic_ids: {int(t): [] for t in tic_ids}
            try:
                rows = original_ml_runner(candidates, config, force_retrain)
            finally:
                classifier._confirmed_planet_periods = original_lookup
        if rows is not None and not rows.empty:
            rows["archive_period_assistance_enabled"] = enabled
            result_path = __import__("pathlib").Path(config["paths"]["results"]) / "ml_predictions.csv"
            rows.to_csv(result_path, index=False)
        return rows

    classifier.patched_run_ml_classification = ml_runner_without_archive_prior
    import tess_pipeline.stage5_classify as stage5
    stage5.run_ml_classification = ml_runner_without_archive_prior
    classifier.patched_compute_ensemble_score = _score_row
    ensemble.compute_physics_composite = _physics_score
    ensemble.compute_ensemble_score = _score_row
    ensemble.run_ensemble_scoring = classifier.patched_run_ensemble_scoring
    logger.info("Scientific validity patch active: measured physics only; archive is annotation-only")
    print(
        "  Patched detector: TLS SDE >= 3 (or BLS SDE >= 10 when TLS is missing) + harmonic pass; "
        "physics >= 0.70 can override ML, otherwise ML >= 0.60 supports a gated transit; "
        "archive labels cannot force TRANSIT"
    )
