#!/usr/bin/env python3
"""Run the original pipeline with the isolated patches from ``patches``."""

import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="backslashreplace")

sys.path.insert(0, str(Path(__file__).parent))
# The patched runner skips Stage 8 report/plot generation by default. Users can
# still request it explicitly with --stages ...8 when they need those artifacts.
if not any(arg == "--stages" or arg.startswith("--stages=") for arg in sys.argv[1:]):
    sys.argv.extend(["--stages", "1,2,3,4,5,6,7"])

from patches import apply_all_patches
apply_all_patches()

import run_pipeline

if __name__ == "__main__":
    run_pipeline.main()
