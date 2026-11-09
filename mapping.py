"""Optional filename-token headings from a Mapping workbook."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

from openpyxl import load_workbook

from data_loader import InputFile, is_mapping_filename
from validation import ValidationIssue


@dataclass(frozen=True)
class MappingResult:
    headers: dict[int, str]
    issues: tuple[ValidationIssue, ...]
    grouping: dict[str, str] = field(default_factory=dict)
    descriptions: dict[str, str] = field(default_factory=dict)


def _read_string_pairs(
    workbook,
    sheet_name: str,
    key_label: str,
    value_label: str,
    source_path: str,
    issues: list[ValidationIssue],
    issue_prefix: str,
) -> dict[str, str]:
    if sheet_name not in workbook.sheetnames:
        return {}

    rows = list(workbook[sheet_name].iter_rows(values_only=True))
    columns = [str(value).strip().casefold() if value is not None else "" for value in rows[0]] if rows else []
    keys = [index for index, name in enumerate(columns) if name == key_label.casefold()]
    values = [index for index, name in enumerate(columns) if name == value_label.casefold()]
    if len(keys) != 1 or len(values) != 1 or sum(bool(name) for name in columns) != 2:
        issues.append(
            ValidationIssue(
                "error",
                f"mapping_{issue_prefix}_columns",
                f"`{sheet_name}` must contain exactly the `{key_label}` and `{value_label}` columns, once each.",
                source_path,
            )
        )
        return {}

    result: dict[str, str] = {}
    for row_number, row in enumerate(rows[1:], start=2):
        if max(keys[0], values[0]) >= len(row):
            continue
        raw_key, raw_value = row[keys[0]], row[values[0]]
        if raw_key is None and raw_value is None:
            continue
        key = str(raw_key).strip() if raw_key is not None else ""
        value = str(raw_value).strip() if raw_value is not None else ""
        if not key or not value:
            issues.append(
                ValidationIssue(
                    "error",
                    f"mapping_{issue_prefix}_empty",
                    f"Row {row_number}: `{key_label}` and `{value_label}` must both be non-empty.",
                    source_path,
                )
            )
            continue
        if key in result and result[key] != value:
            issues.append(
                ValidationIssue(
                    "error",
                    f"mapping_{issue_prefix}_duplicate_{key_label.casefold()}",
                    f"Row {row_number}: `{key}` has conflicting `{value_label}` values.",
                    source_path,
                )
            )
            continue
        result[key] = value
    return result


def load_mapping(source: InputFile) -> MappingResult:
    issues: list[ValidationIssue] = []
    if not is_mapping_filename(source.name):
        issue = ValidationIssue(
            "error",
            "mapping_filename",
            "Mapping workbook must be named `Mapping.xlsx` or `Mapping_*.xlsx`.",
            source.source_path,
        )
        return MappingResult({}, (issue,))

    try:
        workbook = load_workbook(BytesIO(source.content), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl reports several malformed ZIP/XML exception types
        issue = ValidationIssue("error", "mapping_open", f"Could not read mapping workbook: {exc}", source.source_path)
        return MappingResult({}, (issue,))

    try:
        if "Headers" not in workbook.sheetnames:
            issue = ValidationIssue(
                "error", "mapping_sheet", "Mapping workbook is missing the required `Headers` sheet.", source.source_path
            )
            return MappingResult({}, (issue,))

        rows = list(workbook["Headers"].iter_rows(values_only=True))
        if not rows:
            issue = ValidationIssue("error", "mapping_headers", "`Headers` sheet is empty.", source.source_path)
            return MappingResult({}, (issue,))

        column_names = [str(value).strip().casefold() if value is not None else "" for value in rows[0]]
        non_empty_columns = [name for name in column_names if name]
        positions = [index for index, value in enumerate(column_names) if value == "token n"]
        headings = [index for index, value in enumerate(column_names) if value == "header"]
        if len(positions) != 1 or len(headings) != 1 or len(non_empty_columns) != 2:
            issue = ValidationIssue(
                "error",
                "mapping_columns",
                "`Headers` must contain exactly the `Token N` and `Header` columns, once each.",
                source.source_path,
            )
            return MappingResult({}, (issue,))

        result: dict[int, str] = {}
        for row_number, row in enumerate(rows[1:], start=2):
            if max(positions[0], headings[0]) >= len(row):
                continue
            raw_position = row[positions[0]]
            raw_heading = row[headings[0]]
            if raw_position is None and (raw_heading is None or not str(raw_heading).strip()):
                continue

            if isinstance(raw_position, bool):
                token_position = None
            else:
                try:
                    number = float(str(raw_position).strip())
                    token_position = int(number) if number.is_integer() else None
                except (TypeError, ValueError):
                    token_position = None
            if token_position is None or token_position <= 0:
                issues.append(
                    ValidationIssue(
                        "error",
                        "mapping_position",
                        f"Row {row_number}: `Token N` must be a positive integer.",
                        source.source_path,
                    )
                )
                continue

            heading = str(raw_heading).strip() if raw_heading is not None else ""
            if not heading:
                issues.append(
                    ValidationIssue(
                        "error",
                        "mapping_empty_heading",
                        f"Row {row_number}: `Header` cannot be empty for token {token_position}.",
                        source.source_path,
                    )
                )
                continue
            if token_position in result:
                issues.append(
                    ValidationIssue(
                        "error",
                        "mapping_duplicate_position",
                        f"Row {row_number}: token position {token_position} is duplicated.",
                        source.source_path,
                    )
                )
                continue
            result[token_position] = heading
        grouping = _read_string_pairs(
            workbook, "Grouping", "HEADER", "Group", source.source_path, issues, "group"
        )
        descriptions = _read_string_pairs(
            workbook, "Description", "ID", "Description", source.source_path, issues, "description"
        )

        return MappingResult(result, tuple(issues), grouping, descriptions)
    finally:
        workbook.close()


def token_heading(position: int, headers: dict[int, str]) -> str:
    return headers.get(position, f"Case parameter {position}")

