# Validation record

**Checked:** 29 October 2026.

## Automated checks

`python -m pytest tests -q` in the app's `.venv` completed with **18 passed**. Coverage includes in-memory CSV and ZIP parsing, safe ZIP member handling, malformed and duplicate cases, six filename tokens, mapping validation and fallback labels, ambiguous/missing/conflicting channels, all five chart builders, sign transforms, layout distribution, plotted-data metadata, and the Streamlit app's tabs and local reload/upload-clear controls.

The real-export regression reads loose CSVs from the sibling `Example_export/` directory without changing them. It confirmed 72 unique cases, 151 sweep rows, five token positions with counts 2 / 3 / 1 / 4 / 3, 317 raw columns, 22 excluded blank headings per case, 3 WTG objects, 64 loading objects, 2 POCs and 63 power-factor objects.

## Numeric spot checks

For `No_Qlim_HTRT__00 Vini 1pu__Filter_Out__Qmax__Cmax.csv`, the plotted channels matched the source CSV at zero-based sweep index 1:

- WTG 1 Q/P: columns 84/85, `−2.760408 Mvar` / `0.103330 MW`; Qmin/Qmax at columns 87/88. Voltage at column 86 was `0.976772 p.u.`.
- Main TR_1 maximum loading is column 65; Exp_Cable_1 loading is column 1. The loading X value is the negative of POC1 active interchange at column 306.
- POC1 interchange columns 306/307 and POC2 columns 308/309 were plotted as `(−Q, −P)` using each POC's own columns.
- Exp_Cable_1 / Exp_Cable_2 power factor channels are columns 4/16. Both are plotted against the original Index; the selected aggregate PF values were negated, with raw values also present in the data export.

The synthetic tests also compare loose and zipped copies of the same CSV and assert numerical X/Y values for all five chart families. All three layouts are exercised against every chart builder, including eight-case/four-panel and three-WTG/two-panel distributions.

## UI and known limits

The Streamlit `AppTest` rendered the five named tabs with no application exception. A live browser review loaded the 72-case example set and rendered all five chart tabs: WTG P–Q, WTG terminal voltage, equipment loading, POC P–Q and power factor. It also confirmed the mapped filename filters, per-tab controls, Plotly figures, axis labels, and the voltage/loading display references. The local Streamlit process was stopped and the temporary example-data copy was removed. The clear-upload control remounts the file uploader because Streamlit does not permit assigning file-uploader widget state.

The PowerFactory POC plot metadata contains one POC1 Unity-PF curve with a positive Q multiplier while the other POC curves use a negative multiplier. The source curve's Q is zero, so this does not change its plotted value. The app follows the specified uniform `−Q` convention and does not include project archives at runtime.

PNG ZIP export is deferred; Plotly's per-figure native image download and the plotted-data CSV are available.
