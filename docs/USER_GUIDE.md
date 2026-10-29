# User guide

## Load results

Put loose CSVs, ZIP archives or mapping workbooks in `Input_files/` and select **Reload local files**, or upload them in the sidebar. ZIP contents are read in memory. Use **Clear uploads** to discard this session's uploaded files. No input files are written by the dashboard.

The **Data validation and sources** panel reports ignored unsafe ZIP members, malformed files, duplicate case stems, blank headings, mapping problems and channel issues. A valid case can still be used when another case is invalid.

## Select cases

The global selectors follow filename token order. Each selector lists values available after all earlier choices; its caption shows how many cases remain. Use **Select all** or **Clear** beside a selector as needed. A compact initial choice selects one case combination. A downstream value that becomes invalid after an earlier change is removed with an explanation.

Legend labels default to token positions that vary among the currently selected cases. Choose other token positions above the chart tabs if useful. Hover any curve to see its short label, full filename, all original token values, source path, object, metrics, units and sign transforms.

## Choose sources and charts

- **WTG P–Q**: choose WTG objects; toggle Qmin and Qmax capability boundaries independently.
- **WTG Terminal Voltage**: choose WTG objects and optionally edit the 0.92 / 1.08 p.u. visual reference lines. These are display guides, not universal limits.
- **Equipment Loading**: choose loading channels, choose the POC active-interchange source and optionally edit the loading display reference (100% by default).
- **POC P–Q**: choose POC objects. Both axes use the verified negative export convention.
- **Power Factor**: choose PF channels, use sweep index or a selected POC active interchange for X, and choose the PF sign handling. Original plot mode applies the negative sign only to the two aggregate export-cable objects.

Selections, layouts, ranges, reference values and sign options remain in the current Streamlit session. Layout choices are **1 plot**, **1×2** and **2×2**. Bundle distribution can be automatic, by element or by case. Axis limits are optional; invalid min/max pairs revert to automatic limits.

Use Plotly's mode bar to pan, zoom, inspect points or save a figure image. The **Download plotted data (CSV)** button exports the plotted X/Y values, raw source values, axis descriptions, units, case identity, filename tokens, source object and sign transforms. PNG ZIP export is not included.
