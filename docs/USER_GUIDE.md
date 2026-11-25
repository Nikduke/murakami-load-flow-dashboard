# User guide

## Start the dashboard

Run `app_run.bat` from `LF_dash_app\Murakami\01_App`. This launches the Load-Flow `app.py` with the environment in that same folder. It is separate from the similarly named launchers in the Voltage Envelopes and Harmonics projects. Streamlit uses port 8501 when it is free and chooses another port when it is occupied; use the URL printed in the launcher window.

## Load results

Use the always-visible uploader at the top of the sidebar, below the MPE wordmark, to add CSV files, ZIP archives or mapping workbooks. Loose files in `Input_files/` are loaded automatically. ZIP contents are read in memory and uploads stay in the current browser session. Each archive can contain up to 250 entries and expand to at most 100 MiB. Remove an upload from the uploader when it is no longer needed.

One mapping workbook is applied automatically. If more than one mapping workbook is available, choose which one to use. Its `Headers` sheet names the sidebar filename-token filters. An optional `Grouping` sheet adds group tabs to **Equipment Loading** and **Power Factor**; each group tab shows only its mapped channel chips, while **All cases** shows every available channel. These tabs retain the filename-case selection from the sidebar. See [Mapping workbook](MAPPING.md) for the sheet format.

## Select cases and equipment

The first available value in each cascading case-token selector is selected when a new result set loads, so the first valid case combination is shown initially. Use the checkboxes in the sidebar to change it. **Select all** and **Clear all** apply to one token; **All cases** selects every available value. Later token options follow earlier selections.

Choose equipment from the line above each chart. The **All** button comes first and selects every available channel in the active chart or group tab. Light-green chips are unselected; light-amber chips are selected. A plain chip click selects that item alone; **Ctrl-click** adds or removes it from a multi-selection. Each tab starts with its first equipment chip selected. When a mapping has groups, **Equipment Loading** and **Power Factor** show group tabs below the chart tab row, followed by **All cases**. Each group keeps its own first-chip default and selection. Chart-specific controls follow the chip line, with each label inline before its input. **Plot layout** and its buttons sit at the far right of the settings row.

## Read the charts

Each chart tab has a compact layout selector. The default **1 plot** view shows one panel; **1×2** shows two panels in one column and two rows; **2×2** shows four panels in two columns and two rows. Panels are balanced automatically.

When a mapping workbook includes a `Description` sheet, one **Case option descriptions** table appears immediately below the plots and before the violation table. Each case-filter heading is shown once in bold; its option names are bold and their descriptions are listed alongside. Only options in the loaded cases are shown.

- **WTG P–Q**: exported Q against P; Qmin/Qmax boundaries can be toggled.
- **WTG Terminal Voltage**: voltage against active power. The minimum and maximum reference lines start at 0.92 and 1.08 p.u. and can be edited.
- **Equipment Loading**: loading against negative POC active interchange. The highest point in each panel is annotated. The red dashed loading reference starts at 100% and can be edited.
- **POC P–Q**: negative reactive interchange against negative active interchange.
- **Power Factor**: sweep index by default, with optional POC active interchange and sign settings. The initial zero-power sample at sweep index 0 is omitted.

Each plot has one left-aligned case legend beneath it. Entries use equal pixel widths estimated from the longest case name and the selected layout, then wrap into rows as needed. Values shared by every case in a panel appear once in bold after **Case options:**; each entry shows only values that vary. Selecting a legend entry toggles that case's curves. In WTG P–Q, each case has its own line pattern, shared by its operating curve and Qmin/Qmax boundaries; limits are dark grey and operating curves keep their case colours. The case legend shows the pattern associated with that case's limits. Hover shows case options and plotted X/Y values with their axis names and units. Equipment appears in hover only when a panel contains multiple selected objects; boundary points identify Qmin or Qmax. Filenames, paths, metric descriptions and transforms are omitted. **Download plotted data (CSV)** retains full source provenance.

The WTG P–Q and WTG Terminal Voltage tabs show violation summaries below the plots. Both compare **With boost — worst point in sweep** with **Without boost — 15 MW operating point**. At 15 MW, the app uses an exact sample when present or interpolates the measured value between adjacent samples. It does not extrapolate. P–Q also interpolates the matching Qmin or Qmax limit, so each operating-point group has its own limit. Voltage uses the current **Min voltage** or **Max voltage** setting. In the voltage table, **Voltage Limit** has two columns: **Type** (Min/Max) and **Limit (p.u.)**. The limit appears once because it is shared by both operating points. The tables show the measured value even when there is no breach. **None** in Excess means the 15 MW value is within limits. A small positive excess that would round to `0.000` displays as `<0.001`. Dashes mean the sweep has no usable 15 MW point. Each table identifies the case and WTG. Equipment loading uses the **Loading limit** setting (100% by default). Select one or more rows to show matching trace groups above; for P–Q, the selected operating curve keeps both Q limit boundaries. Clear the table selection to restore all currently filtered traces. The selection clears when the selected case or equipment scope changes, or when the violation rows change. Equality with a limit is allowed. Set minimum voltage below maximum voltage for the voltage check to run.

## Validation

Open **Data validation** below the charts to review input and valid-case counts. Identical issue messages are grouped, with the number of affected files and one example filename, plus the object when relevant. PNG ZIP export is not included.
