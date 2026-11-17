# Windows setup

The pipeline runs with Python 3.10 or 3.11 on Windows. Python 3.11 is recommended for the dependency set in `requirements.txt`.

From PowerShell, in the project folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python run_pipeline.py --help
```

If PowerShell blocks virtual environment activation, use the environment's interpreter directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_pipeline.py --demo --demo-n 20
```

With the environment activated, try a small synthetic run first:

```powershell
python run_pipeline.py --demo --demo-n 20
```

The demo does not download light curves. A real-data run needs network access to MAST and SIMBAD:

```powershell
python run_pipeline.py --tic-ids data\test_tic_ids_10.csv --sde-threshold 2.5
```

Use `--sector N` to select a TESS sector. `--skip-download` only works when the matching processed `.npz` files already exist under `data\processed`. Outputs are written under `outputs`, and cached/downloaded data under `data`.

Run commands from any working directory by giving Python the absolute path to `run_pipeline.py`; project data and output paths are resolved from the project location. Input paths supplied with `--tic-ids` and `--config` are still interpreted relative to the current directory unless given as absolute paths.

The default preprocessing uses four Joblib workers. Lower `preprocess.n_jobs` in `config\default.yaml` if you want to reduce CPU or memory use. Transit calculations and thresholds are unchanged by the Windows path fixes.
