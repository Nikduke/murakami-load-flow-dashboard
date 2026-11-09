# Mapping workbook

## Workbook contract

An optional workbook is named `Mapping.xlsx` or `Mapping_*.xlsx` (case-insensitive). `Mapping_V2.xlsx` and names with any suffix after `Mapping_` are recognized.

The required `Headers` sheet has one `Token N` column and one `Header` column. Each data row maps a positive one-based filename token position to a non-empty display heading. For example:

| Token N | Header |
| --- | --- |
| 1 | Study configuration |
| 2 | Initial voltage |

Values and available case combinations are discovered from CSV filename stems split on `__`; the workbook does not enumerate case values.

## Optional equipment groups

An optional `Grouping` sheet has `HEADER` and `Group` columns. `HEADER` must match an equipment/channel object name in the CSV header row; `Group` is the tab name. Repeated rows assigning the same header to the same group are accepted. A header assigned to conflicting groups is reported as a mapping error; the first assignment is kept.

On **Equipment Loading** and **Power Factor**, the app adds one tab per mapped group that has matching channels, followed by **All cases**. A group tab offers only that group's matching channel chips and plots those selected channels across the currently selected filename cases. **All cases** offers every channel available on that chart, including headers not listed in `Grouping`. Other chart tabs and the sidebar filename-case filters are unchanged. Older workbooks without `Grouping` continue to work as before.

## Optional case option descriptions

An optional `Description` sheet has `ID` and `Description` columns. Each `ID` should exactly match a value in the CSV filename tokens. One **Case option descriptions** table appears directly below the plots and before any violation table. It shows each mapped filter heading once in bold, with its option values in bold and descriptions alongside. Only options present in the loaded cases are shown. IDs are trimmed before matching. Options without a matching description show `—`; description rows unused by the loaded cases are not shown. Workbooks without this sheet continue to work without a description table.

## Selection and fallback

Mapping workbooks can be found in local inputs, uploaded separately, or included in a ZIP. A single candidate is selected automatically. When multiple candidates exist, explicitly choose one or choose **Use fallback headings**. This makes an uploaded workbook override a local workbook only after a clear selection.

If no workbook is selected, or a token position has no mapping row, the UI displays `Case parameter N`. Additional token positions do not require workbook changes. Mapping validation reports missing required sheets or columns, invalid or non-positive positions, duplicate token positions, empty headings, incomplete group/description rows and conflicting header, group or description assignments. Invalid rows are skipped while valid rows remain available.
