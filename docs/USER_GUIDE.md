# User guide

## Load results

Use the always-visible uploader at the top of the sidebar, below the MPE wordmark, to add CSV files, ZIP archives or mapping workbooks. Loose files in `Input_files/` are loaded automatically. ZIP contents are read in memory and uploads stay in the current browser session. Remove an upload from the uploader when it is no longer needed.

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
- **Power Factor**: sweep index by default, with optional POC active interchange and sign settings.

Each plot has one left-aligned case legend beneath it. Entries use equal pixel widths estimated from the longest case name and the selected layout, then wrap into rows as needed. Values shared by every case in a panel appear once in bold after **Case options:**; each entry shows only values that vary. Selecting a legend entry toggles that case's curves. In WTG P–Q, each case has its own line pattern, shared by its operating curve and Qmin/Qmax boundaries; limits are dark grey and operating curves keep their case colours. The case legend shows the pattern associated with that case's limits. Hover shows case options and plotted X/Y values with their axis names and units. Equipment appears in hover only when a panel contains multiple selected objects; boundary points identify Qmin or Qmax. Filenames, paths, metric descriptions and transforms are omitted. **Download plotted data (CSV)** retains full source provenance.

## Validation

Open **Data validation** below the charts to review input and valid-case counts. Identical issue messages are grouped, with the number of affected files and one example filename, plus the object when relevant. PNG ZIP export is not included.
