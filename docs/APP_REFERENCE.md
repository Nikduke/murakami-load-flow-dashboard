# Application reference

## Current behaviour

The local Streamlit app reads loose PowerFactory CSV exports, CSVs inside ZIPs, and optional `Mapping.xlsx` / `Mapping_*.xlsx` workbooks from `Input_files/` or session uploads. It parses each case independently and matches channels by object name plus exact metric description. Blank metric headings are excluded. Duplicate case stems are reported and excluded rather than overwritten.

The sidebar provides local reload and session-upload clearing. Local file reads and parsed cases are cached by changing file metadata and source content digests. Uploads remain in the current browser session and are never extracted or saved by the app.

Filename tokens are split only on `__`. Global cascading multiselects apply to every chart tab. A selected mapping workbook changes token labels only. With no mapping row, the UI uses `Case parameter N`.

## Chart tabs

1. **WTG P–Q** plots exported Q against P and can add Qmin and Qmax capability boundaries.
2. **WTG Terminal Voltage** plots terminal voltage against active power and offers editable 0.92 / 1.08 p.u. display references.
3. **Equipment Loading** plots each selected loading against negative POC active interchange and offers a 100% display reference.
4. **POC P–Q** plots negative reactive interchange against negative active interchange.
5. **Power Factor** plots against sweep index by default. The original plot sign inverts `Exp_Cable_1` and `Exp_Cable_2`; other objects remain raw unless the user changes the sign option.

Every tab has 1 plot, 1×2 and 2×2 layouts; Auto, By element and By case bundle distribution; optional axis limits; Plotly pan, zoom, hover and native image export; and a CSV download of plotted X/Y data with source and transform metadata. Element selections are held separately per tab. Voltage selection starts from the P–Q selection when available.

Reference lines are visual guides only. The dashboard displays existing results and does not run PowerFactory or evaluate compliance.

## Known scope

PNG ZIP export is deferred. Individual Plotly figures retain their native image download controls. The app supports UTF-8 and UTF-8-with-BOM CSV input; other encodings produce an actionable validation error.
