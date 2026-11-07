# Changelog

## 2026-11-07

- Raised the ZIP entry limit from 100 to 250 while retaining the 100 MiB uncompressed-size guard, allowing the supplied 181-file export.

## 2026-11-05

- Omitted the initial zero-power sample at sweep index 0 from Power Factor plots and plotted-data downloads.
- Added WTG P–Q and terminal-voltage violation tables below their plots, grouped by case, WTG and limit with point counts and worst excess.

## 2026-10-29

- Created the local PowerFactory load-flow CSV dashboard with in-memory ZIP and upload handling, mapping workbook support and cascading filename-token filters.
- Added five Plotly chart families with verified data mappings/signs, capability boundaries, editable display references, layouts, metadata hover and CSV download.
- Added parser, plotting, real-export regression and Streamlit UI tests, plus setup and user documentation.
- Deferred selected-chart PNG ZIP export.
- Grouped each global case-token filter with visible checkboxes and explicit per-token actions; moved chart controls and layout selection onto their chart tabs.
- Added per-panel case, object and trace counts, a reset-to-default case-filter action, upload/digest caching, and bounded chart caching to avoid repeated work on widget reruns.

## 2026-10-30

- Matched the Harmonics dashboard by placing the MPE wordmark and always-visible uploader in the sidebar; removed the separate Input actions expander so the main column begins with the dashboard and plots.
- Defaulted each newly loaded case-token selector to its first available value, replaced object dropdowns with visible text-sized chips, and compacted the plot controls.
- Added per-panel highest-loading annotations and an editable red dashed loading reference; retained editable minimum and maximum voltage guides.
- Removed redundant plotted-case details and shortened validation rows and plot hover fields.
- Used compact case-option labels in chart legends and clarified chart and panel titles.
- Made a plain equipment-chip click select one item and Ctrl-click add/remove items; moved the plot-layout selector after chart-specific controls.
- Show the Plotly mode bar on hover so it does not cover panel titles.
- Removed repeated filename prefixes and numeric token indices from legend labels while retaining meaningful values such as Vini.
- Defaulted each chart tab to one plot and its first equipment chip; clarified the Qmin dashed and Qmax dotted styles on the existing controls.
- Structured every plot legend under **Case options**, kept one entry per case, and grouped each case's WTG P–Q boundaries with its operating curve.
- Simplified hover to case options, necessary equipment/boundary context and axis values; removed filename, source path, metric and transform details.
- Moved shared case-token values into the legend header, kept varying values in case entries, and changed WTG P–Q boundary traces to dark grey.
- Styled unselected equipment chips light green and selected chips light amber; placed each plot-layout label and its choices inline at the end of the settings row.
- Grouped identical validation messages and removed unused manual axis-range metadata and clipping code.
- Shifted voltage guide labels right of the zero axis and labelled them **Min =** and **Max =**; versioned the chart cache so revised figures replace stale session entries.
- Matched each case's Qmin and Qmax boundary pattern and applied it to that case's operating curve for clear legend association.
- Defined **1×2** as one column with two rows and **2×2** as two columns with two rows.
- Changed legends to one left-aligned Plotly legend per panel, with pixel-sized entries based on the longest case label and row-aware bottom spacing.
- Fixed 2×2 legend wrapping and header spacing, and removed the unused manual case/element distribution option while preserving automatic point balancing.
