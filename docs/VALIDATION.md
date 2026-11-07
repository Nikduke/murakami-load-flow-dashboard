# Validation record

**Checked:** 30 October 2026.

**Retest:** 31 October 2026. The app environment command .venv\Scripts\python.exe -m pytest tests -q completed with **30 passed**. The UI regression now switches the Equipment Loading X-axis from POC1 to POC2 and checks the resulting curve values and axis title.

**Retest:** 5 November 2026. The same app environment command completed with **33 passed** after adding WTG P–Q and terminal-voltage violation summaries.

**Retest:** 5 November 2026. The same app environment command completed with **34 passed** after excluding the initial zero-power Power Factor sample at sweep index 0; the plotted-data CSV retains the correct sweep indices for remaining samples.

## Automated checks

`python -m pytest tests -q` in the app's `.venv` completed with **34 passed**. Coverage includes in-memory CSV and ZIP parsing, mapping validation, all five chart builders, sign transforms, Power Factor's omitted zero-sweep sample on both X-axis modes and aligned plotted-data CSV, balanced panel distribution, shared-token legend headers and single-case labels, legend entry widths and column limits based on the longest displayed label and measured panel width, concise hover fields, dark-grey grouped P–Q boundaries, split-panel titles, highest-loading annotations, editable loading and voltage references, voltage label offsets, trace metadata and WebGL selection, sidebar CSV/ZIP upload, first-value case defaults, the **All cases** action, automatic single-mapping use, explicit choice among multiple mapping workbooks, grouped validation issues and chart-cache reuse. The violation tests verify point-aligned Q/Qmin/Qmax comparisons, editable voltage references, strict outside-limit checks, worst-point summaries and table display on both WTG tabs. The P–Q table remains based on available limits when a boundary is hidden from the plot. An `AppTest` checks the serialized Plotly figures emitted by Streamlit against expected X/Y values, axis titles, voltage limits and the loading peak annotation for all five tabs; it also checks the violation tables, ZIP-to-plot data, local-file refresh and cascading options. `python -m py_compile app.py limit_analysis.py plotting.py equipment_pills.py` also passed.

**Retest:** 7 November 2026. `python -m pytest tests -q` completed with **31 passed, 4 skipped**. ZIP expansion now allows up to 250 archive entries while retaining the 100 MiB uncompressed-size guard. A synthetic archive with 101 CSVs expands successfully. The supplied 181-file export (27.7 MB compressed, 76.6 MB uncompressed) expands in 0.23 s and parses 180 cases in 2.05 s in the app environment; its only parser messages are the existing blank-heading warnings.

The real-export regression reads loose CSVs from the sibling `Example_export/` directory without changing them. It confirmed 72 unique cases, 151 sweep rows, five token positions with counts 2 / 3 / 1 / 4 / 3, 317 raw columns, 22 excluded blank headings per case, 3 WTG objects, 64 loading objects, 2 POCs and 63 power-factor objects.

## Numeric spot checks

For `No_Qlim_HTRT__00 Vini 1pu__Filter_Out__Qmax__Cmax.csv`, the plotted channels matched the source CSV at zero-based sweep index 1:

- WTG 1 Q/P: columns 84/85, `−2.760408 Mvar` / `0.103330 MW`; Qmin/Qmax at columns 87/88. Voltage at column 86 was `0.976772 p.u.`.
- In the same case at the default voltage limits, WTG 1 has 41 samples above Qmax; the worst excess is `3.546701 Mvar` at `14.983335 MW`. Its terminal voltage has 9 samples above the default `1.08 p.u.` maximum; the worst value is `1.088737 p.u.`.
- Main TR_1 maximum loading is column 65; Exp_Cable_1 loading is column 1. The loading X value is the negative of POC1 active interchange at column 306.
- POC1 interchange columns 306/307 and POC2 columns 308/309 were plotted as `(−Q, −P)` using each POC's own columns.
- Exp_Cable_1 / Exp_Cable_2 power factor channels are columns 4/16. Both are plotted against the original Index from sweep 1 onward; the initial sweep-0 sample is omitted. The selected aggregate PF values are negated, with raw values also present in the data export.

The synthetic tests also compare loose and zipped copies of the same CSV and assert numerical X/Y values for all five chart families. Power Factor tests verify that sweep index 0 is omitted on both X-axis modes and from plotted-data CSV while remaining sweep indices stay aligned. All three layouts are exercised against every chart builder, including eight-case/four-panel and three-WTG/two-panel distributions.

## Performance spot check

One Python-side profile of the supplied 12.2 MB ZIP (which contains 72 cases, each with 151 sweep samples) measured ZIP expansion at **0.10 s**, parsing at **0.87 s**, and channel discovery at **0.09 s**. Building one WTG P–Q figure with all 72 cases took **0.38 s** and produced 216 traces with about **709 KB** of Plotly JSON. With the new one-case default, the same chart took **0.015 s** and produced 3 traces with about **17 KB** of Plotly JSON. That reduces the figure payload by about **97.6%** for the initial view. These timings cover Python-side work only, not Streamlit rendering or browser transfer. Session caches skip repeat reads, expansion, parsing and catalogue discovery; the bounded plot cache reuses figures for unchanged selections and includes a rendering revision so changed figure styles do not stay stale in a running session.

## UI and known limits

The live browser check loaded the 11.7 MB sample ZIP through the always-visible sidebar uploader and confirmed the initial filters select **1 of 72 cases**. Across all five tabs with 36 cases selected, full-width plots displayed up to four aligned legend columns and **2×2** displayed two columns per panel. A live recheck of WTG P–Q confirmed two columns per panel at the current sidebar width; automated tests cover narrower and wider panel measurements. Rendered label positions were checked in the browser; screenshots showed readable, unclipped entries. The MPE logo and uploader remain in the sidebar. Equipment chips fit their labels, use light green when unselected and light amber when selected, and retain click/Ctrl-click selection. Plot-specific controls and the **Plot layout** label/buttons share one compact row; the plot starts directly below the settings and summary. The default P–Q view shows one operating curve with dark-grey Qmin/Qmax limits; limits and their case curve share a line pattern. The legend header includes shared case options and the single-case entry reads **Selected case**; for multiple cases, only varying values remain in entries. A **1×2** layout places panels in one column and two rows; **2×2** uses two columns and two rows. In the 2×2 view, all four axes remained full width and headers did not overlap X-axis titles. Clearing the browser console before the fresh render produced no Plotly negative-width errors. The voltage guides read **Min =** and **Max =** and their labels sit to the right of the zero axis. Identical export notices are grouped; the 22 blank-heading columns are shown as one warning affecting 72 files instead of 72 repeated rows. `AppTest` covers the page, all five tabs, filter actions and defaults with a lightweight chip-selector stand-in; the live browser check exercised the actual component and visual layout.

The PowerFactory POC plot metadata contains one POC1 Unity-PF curve with a positive Q multiplier while the other POC curves use a negative multiplier. The source curve's Q is zero, so this does not change its plotted value. The app follows the specified uniform `−Q` convention and does not include project archives at runtime.

PNG ZIP export is deferred; Plotly's per-figure native image download and the plotted-data CSV are available.
