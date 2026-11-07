# User guide

## Start the dashboard

Run `app_run.bat` from `LF_dash_app\Murakami\01_App`. This launches the Load-Flow `app.py` with the environment in that same folder. It is separate from the similarly named launchers in the Voltage Envelopes and Harmonics projects. Streamlit uses port 8501 when it is free and chooses another port when it is occupied; use the URL printed in the launcher window.

## Load results

Use the always-visible uploader at the top of the sidebar, below the MPE wordmark, to add CSV files, ZIP archives or mapping workbooks. Loose files in `Input_files/` are loaded automatically. ZIP contents are read in memory and uploads stay in the current browser session. Each archive can contain up to 250 entries and expand to at most 100 MiB. Remove an upload from the uploader when it is no longer needed.

One mapping workbook is applied automatically. If more than one mapping workbook is available, choose which one to use. Mapping workbooks only rename the case-token filters.

## Select cases and equipment

The first available value in each cascading case-token selector is selected when a new result set loads, so the first valid case combination is shown initially. Use the checkboxes in the sidebar to change it. **Select all** and **Clear all** apply to one token; **All cases** selects every available value. Later token options follow earlier selections.

Choose equipment from the visible chips above each chart. Light-green chips are unselected; light-amber chips are selected. A plain click selects that item alone; **Ctrl-click** adds or removes it from a multi-selection. Each tab starts with its first equipment chip selected. Chart-specific controls follow the chips, with each label inline before its input. **Plot layout** and its buttons sit at the far right of the settings row.

## Read the charts

Each chart tab has a compact layout selector. The default **1 plot** view shows one panel; **1×2** shows two panels in one column and two rows; **2×2** shows four panels in two columns and two rows. Panels are balanced automatically.

- **WTG P–Q**: exported Q against P; Qmin/Qmax boundaries can be toggled.
- **WTG Terminal Voltage**: voltage against active power. The minimum and maximum reference lines start at 0.92 and 1.08 p.u. and can be edited.
- **Equipment Loading**: loading against negative POC active interchange. The highest point in each panel is annotated. The red dashed loading reference starts at 100% and can be edited.
- **POC P–Q**: negative reactive interchange against negative active interchange.
- **Power Factor**: sweep index by default, with optional POC active interchange and sign settings. The initial zero-power sample at sweep index 0 is omitted.

Each plot has one left-aligned case legend beneath it. Entries use equal pixel widths estimated from the longest case name and the selected layout, then wrap into rows as needed. Values shared by every case in a panel appear once in bold after **Case options:**; each entry shows only values that vary. Selecting a legend entry toggles that case's curves. In WTG P–Q, each case has its own line pattern, shared by its operating curve and Qmin/Qmax boundaries; limits are dark grey and operating curves keep their case colours. The case legend shows the pattern associated with that case's limits. Hover shows case options and plotted X/Y values with their axis names and units. Equipment appears in hover only when a panel contains multiple selected objects; boundary points identify Qmin or Qmax. Filenames, paths, metric descriptions and transforms are omitted. **Download plotted data (CSV)** retains full source provenance.

The WTG P–Q, WTG Terminal Voltage and Equipment Loading tabs show violation summaries below the plots. P–Q compares each trace point with Qmin and Qmax from the same case and sweep row; voltage uses the current **Min voltage** and **Max voltage** settings; equipment loading uses the **Loading limit** setting (100% by default). The tables show only values beyond a limit, with the case and object, worst measured value, limit, excess and corresponding plot-axis location. Select one or more rows to show the matching trace groups above; for P–Q, the selected operating curve keeps both Q limit boundaries. Clear the table selection to restore all currently filtered traces. The selection clears automatically when the selected case or equipment scope changes, or when the violation rows change. Values equal to a limit are allowed. Set minimum voltage below maximum voltage for the voltage check to run.

## Validation

Open **Data validation** below the charts to review input and valid-case counts. Identical issue messages are grouped, with the number of affected files and one example filename, plus the object when relevant. PNG ZIP export is not included.
