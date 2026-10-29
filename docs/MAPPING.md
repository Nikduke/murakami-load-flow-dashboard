# Token heading mapping

## Workbook contract

An optional workbook is named `Mapping.xlsx` or `Mapping_*.xlsx` (case-insensitive) and contains a `Headers` sheet with one `Token N` column and one `Header` column. Each data row maps a positive one-based filename token position to a non-empty display heading. For example:

| Token N | Header |
| --- | --- |
| 1 | Study configuration |
| 2 | Initial voltage |

Only the token heading is mapped. Values and available case combinations are discovered from CSV filename stems split on `__`; the mapping workbook does not enumerate them.

## Selection and fallback

Mapping workbooks can be found in local inputs, uploaded separately, or included in a ZIP. A single candidate is selected automatically. When multiple candidates exist, explicitly choose one or choose **Use fallback headings**. This makes an uploaded workbook override a local workbook only after a clear selection.

If no workbook is selected, or a token position has no mapping row, the UI displays `Case parameter N`. Additional token positions do not require workbook changes. Mapping validation reports a missing sheet or required columns, invalid or non-positive positions, duplicate positions and empty headings. Invalid rows are skipped while valid rows remain available.
