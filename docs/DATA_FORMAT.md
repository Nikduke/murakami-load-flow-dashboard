# CSV data format and chart mappings

## Input schema

Each CSV contains one calculation case. Row 1 gives the PowerFactory object name/path; row 2 gives the exact variable description and unit. The first cells are normally `Results` and `Index`. Numeric samples start on row 3. The first column is retained as the sweep index. Standard CSV quoting and UTF-8 with or without a BOM are supported; empty, non-numeric and non-finite values remain unavailable points.

A channel is identified within a case by its object name, exact metric description and original zero-based CSV column position. Channels are matched across cases by semantic object and description rather than column order. Duplicate role channels and unit conflicts are reported as ambiguous. Rows with mismatched data width are padded or truncated with a warning so other valid cases remain usable.

Columns with blank second-row headings are unavailable channels, even if their data cells contain zeros. A labelled channel containing zero remains valid. The Murakami example contains 22 blank-heading columns per case; this count is a regression fact for that example, not a parser assumption.

## Semantic chart sources

| Tab | X | Y / related channels | Transform |
| --- | --- | --- | --- |
| WTG P–Q | WTG reactive power (Mvar) | WTG active power (MW); optional Qmin/Qmax against the same P | Exported signs retained |
| WTG Terminal Voltage | WTG active power (MW) | WTG voltage (p.u.) | Exported signs retained |
| Equipment Loading | Selected POC active interchange (MW) | Equipment loading (%) | X is `−Pinter`; loading is unchanged |
| POC P–Q | POC reactive interchange (Mvar) | POC active interchange (MW) | X and Y are both negated |
| Power Factor | Sweep index by default; optionally negative POC active interchange | Power factor | Original mode negates only `Exp_Cable_1` and `Exp_Cable_2`; raw and invert-selected modes are available |

For loading, the catalogue prefers `Maximum Loading in %`, then `Max. Loading in %`, then `Loading in %` when one object has more than one recognised description. The code does not infer physical classes from names such as `A1`.

## Murakami regression observations

The checked loose-file set has 72 cases, 151 samples per case and 317 raw columns per sample row. Its token counts are 2 / 3 / 1 / 4 / 3. The discovered catalogue contains 3 WTG objects, 64 loading objects, 2 POCs and 63 power-factor objects. These counts are tested as example-specific expectations; the application does not hard-code them.

PowerFactory variable codes such as `m:P:bus1` and `c:Pinter` were used to verify the semantic chart choices during implementation. Runtime plotting depends only on the CSV headers and values.
