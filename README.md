# PowerFactory Load-Flow Dashboard

A local Streamlit and Plotly viewer for PowerFactory load-flow sweep CSVs. Each CSV represents one case and has two header rows followed by numeric sweep samples. The app does not run PowerFactory calculations.

## Run locally

The checked environment used Python 3.12.14. From this folder, create the virtual environment and install the pinned packages:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Double-click `app_run.bat`, or start the app from PowerShell:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The launcher changes to its own folder and uses `.venv`, so it can be started from another working directory. Streamlit serves the app on localhost, using its default port selection.

## Add results

- Place loose `.csv` files, `.zip` archives, or `Mapping.xlsx` / `Mapping_*.xlsx` under `Input_files/`. Subfolders are scanned recursively.
- Or upload one or more CSV, ZIP, and mapping files in the sidebar. Browser uploads remain in the current session and are not written to disk.
- ZIP files are read in memory. The current safeguards allow up to 100 archive entries and 100 MiB uncompressed content.
- When more than one mapping workbook is available, choose the intended workbook in the sidebar. Mapping files supply token headings only; case values are discovered from filenames.

The app reads source files locally and does not send project data to a service. `.gitignore` excludes input files, uploads, secrets and generated exports. Keep proprietary PowerFactory files outside the repository.

## Use the dashboard

Global filename-token filters cascade from left to right and apply across five tabs: WTG P–Q, WTG terminal voltage, equipment loading, POC P–Q, and power factor. Each tab offers 1 plot, 1×2 or 2×2 layouts, bundle distribution options, Plotly controls and a plotted-data CSV download. See [the user guide](docs/USER_GUIDE.md) for details.

## Tests

Run the synthetic, real-export regression and Streamlit UI tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

The regression tests read the example data from the sibling `Example_export/` folder when it is present. They do not copy or modify those files. Synthetic inputs are generated in memory.

## Documentation

- [App reference](docs/APP_REFERENCE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [CSV format and plot mappings](docs/DATA_FORMAT.md)
- [Mapping workbook](docs/MAPPING.md)
- [User guide](docs/USER_GUIDE.md)
- [Validation record](docs/VALIDATION.md)
- [Changelog](docs/CHANGELOG.md)
- [Project status](docs/PROJECT_STATUS.md)
