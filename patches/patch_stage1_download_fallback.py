"""Try alternate MAST light-curve products when the first FITS is unreadable."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def patched_download_lightcurve(tic_id: int, sector: int | None, quality_bitmask: str):
    import lightkurve as lk

    if sector is not None:
        search = lk.search_lightcurve(f"TIC {tic_id}", mission="TESS", sector=sector)
    else:
        search = lk.search_lightcurve(f"TIC {tic_id}", mission="TESS")
    if len(search) == 0:
        return None

    errors = []
    for index in range(len(search)):
        try:
            lightcurve = search[index].download(quality_bitmask=quality_bitmask)
            if lightcurve is None or len(lightcurve.time) < 50:
                continue
            if index:
                logger.info("TIC %s: using MAST product %d/%d after earlier product failures",
                            tic_id, index + 1, len(search))
            return {
                "time": lightcurve.time.value,
                "flux": lightcurve.flux.value,
                "flux_err": lightcurve.flux_err.value
                if hasattr(lightcurve, "flux_err") and lightcurve.flux_err is not None else None,
            }
        except Exception as exc:
            errors.append(f"product {index + 1}: {exc}")
            logger.debug("TIC %s MAST product %d/%d failed: %s",
                         tic_id, index + 1, len(search), exc)
    if errors:
        logger.warning("No readable MAST light curve for TIC %s (%d products tried): %s",
                       tic_id, len(search), errors[-1])
    return None


def apply():
    import tess_pipeline.stage1_preprocess as stage1
    stage1.download_lightcurve = patched_download_lightcurve
    original_run_preprocess = stage1.run_preprocess

    def run_with_in_process_fallback(tic_ids, config, sector=None, skip_download=False):
        # Joblib process workers import the unpatched module in fresh processes.
        # Run only batches with uncached targets in-process so the patched downloader is used.
        processed_dir = config["paths"]["processed"]
        has_uncached = any(not (stage1.Path(processed_dir) / f"{tic_id}.npz").exists()
                           for tic_id in tic_ids)
        old_n_jobs = config["preprocess"].get("n_jobs", 1)
        if has_uncached:
            config["preprocess"]["n_jobs"] = 1
        try:
            return original_run_preprocess(tic_ids, config, sector, skip_download)
        finally:
            config["preprocess"]["n_jobs"] = old_n_jobs

    stage1.run_preprocess = run_with_in_process_fallback
    print("  Patched Stage 1: alternate MAST products on unreadable FITS")
