"""Replace unsupported Stage 4 heuristics with coverage-aware diagnostics.

These scores are screening evidence, not planet confirmations. Checks that do
not have enough usable events return NaN so the ensemble renormalizes over
measurements that were actually made.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


def _valid_curve(time, flux):
    time = np.asarray(time, dtype=float)
    flux = np.asarray(flux, dtype=float)
    valid = np.isfinite(time) & np.isfinite(flux)
    time, flux = time[valid], flux[valid]
    if len(time) < 10:
        return None
    order = np.argsort(time)
    return time[order], flux[order]


def _robust_sigma(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return np.nan
    median = np.median(values)
    sigma = 1.4826 * np.median(np.abs(values - median))
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = np.std(values, ddof=1)
    return float(sigma) if np.isfinite(sigma) and sigma > 0 else np.nan


def _event_depths(time, flux, period, t0, duration, phase_offset=0.0):
    """Measure event depths against nearby out-of-event data, one orbit at a time."""
    curve = _valid_curve(time, flux)
    if curve is None:
        return []
    time, flux = curve
    if (not np.isfinite(period) or period <= 0 or not np.isfinite(t0)
            or not np.isfinite(duration) or duration <= 0 or duration >= period / 4):
        return []

    first = int(np.ceil((time[0] - t0) / period - phase_offset))
    last = int(np.floor((time[-1] - t0) / period - phase_offset))
    events = []
    for epoch in range(first, last + 1):
        center = t0 + (epoch + phase_offset) * period
        delta = np.abs(time - center)
        inside = delta <= duration / 2
        local_out = (delta >= 1.5 * duration) & (delta <= min(4.0 * duration, period / 4))
        if inside.sum() < 2 or local_out.sum() < 5:
            continue

        in_flux = flux[inside]
        out_flux = flux[local_out]
        baseline = float(np.median(out_flux))
        depth = baseline - float(np.median(in_flux))
        in_sigma = _robust_sigma(in_flux)
        out_sigma = _robust_sigma(out_flux)
        cadence_sigma = max(
            value for value in (in_sigma, out_sigma, 1e-8) if np.isfinite(value)
        )
        error = 1.253 * cadence_sigma * np.sqrt(1 / inside.sum() + 1 / local_out.sum())
        events.append({"epoch": epoch, "depth": depth, "error": float(error),
                       "n_in": int(inside.sum()), "n_out": int(local_out.sum())})
    return events


def _weighted_mean_and_error(events):
    values = np.asarray([event["depth"] for event in events], dtype=float)
    errors = np.asarray([event["error"] for event in events], dtype=float)
    errors = np.maximum(errors, 1e-8)
    weights = 1.0 / errors**2
    mean = float(np.sum(weights * values) / np.sum(weights))
    error = float(np.sqrt(1.0 / np.sum(weights)))
    if len(values) > 1:
        scatter = _robust_sigma(values)
        if np.isfinite(scatter):
            error = max(error, scatter / np.sqrt(len(values)))
    return mean, error


def _depth_plausibility(depth, stellar_radius):
    """One-sided radius plausibility; shallow planet-sized dips are not penalized."""
    try:
        depth, stellar_radius = float(depth), float(stellar_radius)
    except (TypeError, ValueError):
        return np.nan
    if (not np.isfinite(depth) or depth <= 0 or not np.isfinite(stellar_radius)
            or stellar_radius <= 0):
        return np.nan

    # Transit depth ~= (Rp/Rs)^2. This is only a size screen; blending and
    # stellar-radius uncertainty prevent it from proving that the body is a planet.
    jupiter_radius_solar = 0.10045
    companion_radius_jupiter = np.sqrt(depth) * stellar_radius / jupiter_radius_solar
    if companion_radius_jupiter <= 2.0:
        return 1.0
    if companion_radius_jupiter >= 5.0:
        return 0.0
    return float(1.0 - (companion_radius_jupiter - 2.0) / 3.0)


def _shape_check(time, flux, period, t0, duration):
    curve = _valid_curve(time, flux)
    if curve is None or not np.isfinite(period) or period <= 0 or duration <= 0 or duration >= period / 4:
        return {"shape_score": np.nan, "ingress_slope": np.nan, "egress_slope": np.nan,
                "flatness": np.nan, "symmetry": np.nan, "variable_depth_score": np.nan}
    time, flux = curve
    phase_time = ((time - t0 + period / 2) % period) - period / 2
    half_duration = duration / 2
    x = np.abs(phase_time) / half_duration
    in_transit = x <= 1.0
    out_of_transit = x >= 1.5
    observed_epochs = np.unique(np.round((time[in_transit] - t0) / period).astype(int))
    if len(observed_epochs) < 2 or in_transit.sum() < 12 or out_of_transit.sum() < 12:
        return {"shape_score": np.nan, "ingress_slope": np.nan, "egress_slope": np.nan,
                "flatness": np.nan, "symmetry": np.nan, "variable_depth_score": np.nan}

    baseline = float(np.median(flux[out_of_transit]))
    dip = baseline - flux
    noise = _robust_sigma(dip[out_of_transit])
    if not np.isfinite(noise):
        return {"shape_score": np.nan, "ingress_slope": np.nan, "egress_slope": np.nan,
                "flatness": np.nan, "symmetry": np.nan, "variable_depth_score": np.nan}
    depth_estimate = float(np.median(dip[in_transit & (x < 0.2)]))
    if not np.isfinite(depth_estimate) or depth_estimate <= 2.0 * noise:
        return {"shape_score": np.nan, "ingress_slope": np.nan, "egress_slope": np.nan,
                "flatness": np.nan, "symmetry": np.nan, "variable_depth_score": np.nan}

    # Compare a flat-bottom trapezoid with a V-shaped event on phase-binned data.
    edges = np.linspace(0.0, 1.0, 17)
    bin_x, bin_dip = [], []
    for lower, upper in zip(edges[:-1], edges[1:]):
        take = in_transit & (x >= lower) & (x < upper)
        if take.sum() >= 2:
            bin_x.append(float(np.median(x[take])))
            bin_dip.append(float(np.median(dip[take])))
    if len(bin_x) < 8:
        return {"shape_score": np.nan, "ingress_slope": np.nan, "egress_slope": np.nan,
                "flatness": np.nan, "symmetry": np.nan, "variable_depth_score": np.nan}

    bin_x, bin_dip = np.asarray(bin_x), np.asarray(bin_dip)
    v_template = np.clip(1.0 - bin_x, 0.0, 1.0)
    flat_template = np.clip((1.0 - bin_x) / 0.20, 0.0, 1.0)

    def template_sse(template):
        amplitude = max(0.0, float(np.dot(template, bin_dip) / max(np.dot(template, template), 1e-12)))
        residual = bin_dip - amplitude * template
        return float(np.dot(residual, residual))

    sse_v = max(template_sse(v_template), 1e-15)
    sse_flat = max(template_sse(flat_template), 1e-15)
    delta_bic = len(bin_x) * np.log(sse_v / sse_flat)
    shape_score = float(1.0 / (1.0 + np.exp(-np.clip(delta_bic / 2.0, -30, 30))))

    left = in_transit & (phase_time < 0)
    right = in_transit & (phase_time > 0)
    ingress_slope = float(np.polyfit(phase_time[left], flux[left], 1)[0]) if left.sum() >= 3 else np.nan
    egress_slope = float(np.polyfit(phase_time[right], flux[right], 1)[0]) if right.sum() >= 3 else np.nan
    core = in_transit & (x < 0.3)
    flatness = float(np.clip(1.0 - _robust_sigma(dip[core]) / max(depth_estimate, 1e-12), 0, 1)) if core.sum() >= 3 else np.nan
    left_bins = bin_dip[bin_x < 0.5]
    right_bins = bin_dip[bin_x >= 0.5]
    symmetry = (float(np.clip(1.0 - abs(np.mean(left_bins) - np.mean(right_bins)) / max(depth_estimate, 1e-12), 0, 1))
                if len(left_bins) and len(right_bins) else np.nan)

    event_depths = _event_depths(time, flux, period, t0, duration)
    variable_score = np.nan
    if len(event_depths) >= 3:
        depths = np.asarray([event["depth"] for event in event_depths])
        scatter = _robust_sigma(depths)
        variable_score = float(np.clip(1.0 - scatter / max(abs(float(np.median(depths))), 1e-12), 0, 1)) if np.isfinite(scatter) else np.nan

    return {"shape_score": shape_score, "ingress_slope": ingress_slope,
            "egress_slope": egress_slope, "flatness": flatness,
            "symmetry": symmetry, "variable_depth_score": variable_score}


def _secondary_check(time, flux, period, t0, duration):
    events = _event_depths(time, flux, period, t0, duration, phase_offset=0.5)
    if len(events) < 3:
        return np.nan
    depths = np.asarray([event["depth"] for event in events], dtype=float)
    mean, error = _weighted_mean_and_error(events)
    if not np.isfinite(mean) or not np.isfinite(error) or error <= 0:
        return np.nan
    significance = mean / error
    if significance <= 2.0:
        return 1.0
    # Strong, repeatable secondary dimming is EB evidence. This is a diagnostic
    # score, not a claim that every secondary eclipse must be an EB.
    return float(np.clip(1.0 - (significance - 2.0) / 5.0, 0.0, 1.0))


def _odd_even_check(time, flux, period, t0, duration):
    events = _event_depths(time, flux, period, t0, duration)
    odd = [event for event in events if event["epoch"] % 2]
    even = [event for event in events if event["epoch"] % 2 == 0]
    if len(odd) < 2 or len(even) < 2:
        return {"odd_depth_mean": np.nan, "even_depth_mean": np.nan,
                "odd_even_ratio": np.nan, "odd_even_score": np.nan,
                "oddeven_score": np.nan}
    odd_mean, odd_err = _weighted_mean_and_error(odd)
    even_mean, even_err = _weighted_mean_and_error(even)
    diff_err = np.hypot(odd_err, even_err)
    if not np.isfinite(diff_err) or diff_err <= 0:
        return {"odd_depth_mean": odd_mean, "even_depth_mean": even_mean,
                "odd_even_ratio": np.nan, "odd_even_score": np.nan,
                "oddeven_score": np.nan}
    significance = abs(odd_mean - even_mean) / diff_err
    score = float(1.0 / (1.0 + np.exp(np.clip(significance - 3.0, -30, 30))))
    ratio = odd_mean / even_mean if even_mean > 0 else np.nan
    return {"odd_depth_mean": odd_mean, "even_depth_mean": even_mean,
            "odd_even_ratio": float(ratio), "odd_even_score": score,
            "oddeven_score": score}


def _ellipsoidal_check(time, flux, period, t0, duration):
    curve = _valid_curve(time, flux)
    if curve is None or not np.isfinite(period) or period <= 0 or duration <= 0:
        return np.nan
    time, flux = curve
    if np.ptp(time) / period < 2.0:
        return np.nan
    phase = ((time - t0) / period) % 1.0
    distance = np.minimum(phase, 1.0 - phase) * period
    oot = distance >= duration
    if oot.sum() < 50:
        return np.nan
    phase_oot, flux_oot = phase[oot], flux[oot]
    if len(np.unique(np.floor(phase_oot * 20))) < 12:
        return np.nan

    baseline = float(np.median(flux_oot))
    if not np.isfinite(baseline) or baseline == 0:
        return np.nan
    # Phase-bin first. Treating thousands of adjacent cadences as independent
    # would make the harmonic significance spuriously large.
    bins = np.linspace(0.0, 1.0, 21)
    phase_binned, flux_binned = [], []
    for lower, upper in zip(bins[:-1], bins[1:]):
        selected = (phase_oot >= lower) & (phase_oot < upper)
        if selected.sum() >= 2:
            phase_binned.append(float(np.median(phase_oot[selected])))
            flux_binned.append(float(np.median(flux_oot[selected])))
    if len(phase_binned) < 12:
        return np.nan
    phase_binned = np.asarray(phase_binned)
    y = np.asarray(flux_binned) / baseline - 1.0
    angle = 2 * np.pi * phase_binned
    design = np.column_stack((np.ones(len(y)), np.cos(angle), np.sin(angle),
                              np.cos(2 * angle), np.sin(2 * angle)))
    try:
        coefficients, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
        residual = y - design @ coefficients
        sigma = _robust_sigma(residual)
        covariance = sigma**2 * np.linalg.pinv(design.T @ design) if np.isfinite(sigma) else None
        if covariance is None:
            return np.nan
        c2, s2 = coefficients[3], coefficients[4]
        amplitude = float(np.hypot(c2, s2))
        if amplitude <= 0:
            return 1.0
        amp_error = float(np.sqrt((c2**2 * covariance[3, 3] + s2**2 * covariance[4, 4]) / amplitude**2))
        if not np.isfinite(amp_error) or amp_error <= 0:
            return np.nan
        significance = amplitude / amp_error
        return float(1.0 / (1.0 + np.exp(np.clip(significance - 3.0, -30, 30))))
    except (np.linalg.LinAlgError, ValueError, FloatingPointError):
        return np.nan


def apply():
    import tess_pipeline.stage4_physics as physics
    from tess_pipeline.stage1_preprocess import load_processed_curve
    import patch_scientific_validity as validity
    import patch_supervised_classifier as classifier

    original_extract = physics.extract_physics_features

    def extract_measured_physics(candidate, config, run_centroid=False):
        result = original_extract(candidate, config, run_centroid=run_centroid)
        if not result:
            return result
        tic_id = int(candidate["tic_id"])
        data = load_processed_curve(tic_id, config)
        if data is None:
            return result
        time = data["time"]
        flux = data.get("detrended", data.get("flux"))
        period = float(candidate.get("period", np.nan))
        t0 = float(candidate.get("t0", candidate.get("epoch", np.nan)))
        duration = float(candidate.get("duration", np.nan))

        if str(candidate.get("query_source", "")).lower() == "sun-like_default":
            result["depth_score"] = np.nan
            result["depth_status"] = "UNAVAILABLE_NO_VALID_STELLAR_RADIUS"
        else:
            result["depth_score"] = _depth_plausibility(candidate.get("depth", np.nan), candidate.get("r_star", np.nan))
            result["depth_status"] = ("AVAILABLE_GAIA" if np.isfinite(result["depth_score"])
                                       else "UNAVAILABLE_NO_VALID_STELLAR_RADIUS")
        result["depth_consistency_score"] = result["depth_score"]
        shape = _shape_check(time, flux, period, t0, duration)
        result.update(shape)
        result["secondary_eclipse_score"] = _secondary_check(time, flux, period, t0, duration)
        result["nosec_score"] = result["secondary_eclipse_score"]
        result["secondary_eclipse_flag"] = 1.0 - result["nosec_score"] if np.isfinite(result["nosec_score"]) else np.nan
        odd_even = _odd_even_check(time, flux, period, t0, duration)
        result.update(odd_even)
        result["ellipsoidal_score"] = _ellipsoidal_check(time, flux, period, t0, duration)
        import pandas as pd
        score_row = pd.Series({**candidate, **result})
        result["physics_overall"] = validity._physics_score(score_row)
        result["physics_available_components"] = sum(
            np.isfinite(float(score_row.get(key, np.nan))) for key in
            ("det_quality", "depth_score", "shape_score", "nosec_score", "oddeven_score", "ellipsoidal_score")
            if score_row.get(key) is not None
        )
        for name, key in (("shape_status", "shape_score"),
                          ("secondary_eclipse_status", "nosec_score"),
                          ("odd_even_status", "oddeven_score"),
                          ("ellipsoidal_status", "ellipsoidal_score")):
            result[name] = "MEASURED" if np.isfinite(result.get(key, np.nan)) else "UNAVAILABLE_INSUFFICIENT_COVERAGE"
        return result

    physics.extract_physics_features = extract_measured_physics
    version_dir = classifier.ROOT / "data" / "real_training"
    # New feature semantics get their own versioned training/model artifacts;
    # preserve the old validated files so the change can be compared or rolled back.
    classifier.LABELS_PATH = version_dir / "training_labels_physics_v3.csv"
    classifier.FEATURES_PATH = version_dir / "candidate_features_physics_v3.csv"
    classifier.MODEL_PATH = version_dir / "patched_classifier_physics_v3.joblib"
    classifier.METRICS_PATH = version_dir / "patched_validation_physics_v3.json"
    logger.info("Coverage-aware Stage 4 diagnostics patch active")
    print("  Physics diagnostics: size plausibility, transit-shape model comparison, event-level secondary/odd-even checks, and phase-harmonic ellipsoidal check")
