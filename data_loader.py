"""Read PowerFactory two-header-row CSV exports without changing source files."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path, PurePosixPath
import re
from typing import Iterable
from zipfile import BadZipFile, LargeZipFile, ZipFile

from validation import ValidationIssue


MAX_ARCHIVE_MEMBERS = 100
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class InputFile:
    name: str
    source_path: str
    content: bytes
    origin: str = "local"
    archive_name: str = ""
    member_path: str = ""

    @property
    def digest(self) -> str:
        return sha256(self.content).hexdigest()


@dataclass(frozen=True)
class Channel:
    object_name: str
    metric_description: str
    unit: str
    column_position: int
    numeric_values: tuple[float | None, ...]


@dataclass(frozen=True)
class CaseData:
    case_id: str
    filename: str
    tokens: tuple[str, ...]
    source_path: str
    source_kind: str
    sha256: str
    sweep_index: tuple[float | None, ...]
    channels: tuple[Channel, ...]
    validation_provenance: tuple[str, ...]

    def channels_for(self, object_name: str) -> tuple[Channel, ...]:
        return tuple(channel for channel in self.channels if channel.object_name == object_name)


@dataclass(frozen=True)
class ParseResult:
    cases: tuple[CaseData, ...]
    issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True)
class ExpandedInputs:
    csv_files: tuple[InputFile, ...]
    mapping_files: tuple[InputFile, ...]
    issues: tuple[ValidationIssue, ...]


def is_mapping_filename(name: str) -> bool:
    lowered = Path(name).name.casefold()
    return lowered == "mapping.xlsx" or (
        lowered.startswith("mapping_") and lowered.endswith(".xlsx")
    )


def discover_local_inputs(input_dir: Path) -> tuple[InputFile, ...]:
    """Read supported local inputs recursively, retaining app-relative provenance."""
    if not input_dir.is_dir():
        return ()

    files: list[InputFile] = []
    for path in sorted(input_dir.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file() or path.name.startswith("~$"):
            continue
        if "__macosx" in {part.casefold() for part in path.parts}:
            continue
        suffix = path.suffix.casefold()
        if suffix == ".csv" or suffix == ".zip" or (suffix == ".xlsx" and is_mapping_filename(path.name)):
            files.append(
                InputFile(
                    name=path.name,
                    source_path=path.relative_to(input_dir).as_posix(),
                    content=path.read_bytes(),
                    origin="local",
                )
            )
    return tuple(files)


def _safe_zip_member(name: str) -> tuple[bool, str]:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or re.match(r"^[A-Za-z]:", normalized) or ".." in path.parts:
        return False, normalized
    if "__macosx" in {part.casefold() for part in path.parts} or path.name.startswith("~$"):
        return False, normalized
    return True, normalized


def expand_inputs(files: Iterable[InputFile]) -> ExpandedInputs:
    """Expand CSVs and Mapping workbooks from loose inputs and ZIPs in memory."""
    csv_files: list[InputFile] = []
    mapping_files: list[InputFile] = []
    issues: list[ValidationIssue] = []

    for source in files:
        suffix = Path(source.name).suffix.casefold()
        if suffix == ".csv":
            csv_files.append(source)
            continue
        if suffix == ".xlsx":
            if is_mapping_filename(source.name):
                mapping_files.append(source)
            continue
        if suffix != ".zip":
            continue

        archive_label = source.archive_name or source.name
        try:
            with ZipFile(BytesIO(source.content)) as archive:
                members = archive.infolist()
                if len(members) > MAX_ARCHIVE_MEMBERS:
                    raise ValueError(
                        f"the archive has {len(members)} entries; the limit is {MAX_ARCHIVE_MEMBERS}."
                    )
                unpacked_size = sum(member.file_size for member in members if not member.is_dir())
                if unpacked_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    limit_mib = MAX_ARCHIVE_UNCOMPRESSED_BYTES // (1024 * 1024)
                    raise ValueError(f"the archive expands beyond the {limit_mib} MiB limit.")

                for member in members:
                    if member.is_dir():
                        continue
                    safe, member_path = _safe_zip_member(member.filename)
                    if not safe:
                        issues.append(
                            ValidationIssue(
                                "warning",
                                "unsafe_zip_member",
                                f"Ignored unsafe or system ZIP member `{member_path}`.",
                                source_path=archive_label,
                            )
                        )
                        continue
                    member_name = PurePosixPath(member_path).name
                    member_suffix = PurePosixPath(member_path).suffix.casefold()
                    if member.flag_bits & 0x1:
                        if member_suffix == ".csv" or (member_suffix == ".xlsx" and is_mapping_filename(member_name)):
                            raise ValueError(f"encrypted member `{member_path}` is not supported.")
                        continue

                    target = csv_files if member_suffix == ".csv" else mapping_files
                    if member_suffix != ".csv" and not (
                        member_suffix == ".xlsx" and is_mapping_filename(member_name)
                    ):
                        continue
                    target.append(
                        InputFile(
                            name=member_name,
                            source_path=f"{archive_label}!/{member_path}",
                            content=archive.read(member),
                            origin=source.origin,
                            archive_name=archive_label,
                            member_path=member_path,
                        )
                    )
        except (BadZipFile, LargeZipFile, OSError, RuntimeError, NotImplementedError, EOFError, ValueError) as exc:
            issues.append(
                ValidationIssue(
                    "error",
                    "invalid_zip",
                    f"Could not read ZIP archive `{archive_label}`: {exc}",
                    source_path=archive_label,
                )
            )

    return ExpandedInputs(tuple(csv_files), tuple(mapping_files), tuple(issues))


def _number(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _unit_from_description(description: str) -> str:
    match = re.search(r"\s+in\s+(.+?)\s*$", description, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def parse_csv_case(source: InputFile) -> tuple[CaseData | None, tuple[ValidationIssue, ...]]:
    """Parse one case independently; unavailable blank-heading columns are excluded."""
    filename = Path(source.name).name
    case_id = Path(filename).stem
    tokens = tuple(Path(filename).stem.split("__"))
    issues: list[ValidationIssue] = []

    try:
        text = source.content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        issue = ValidationIssue(
            "error", "csv_encoding", f"CSV must be UTF-8 or UTF-8 with BOM: {exc}", source.source_path, case_id
        )
        return None, (issue,)

    try:
        rows = list(csv.reader(StringIO(text, newline="")))
    except csv.Error as exc:
        issue = ValidationIssue("error", "csv_parse", f"Could not parse CSV: {exc}", source.source_path, case_id)
        return None, (issue,)

    if len(rows) < 2:
        issue = ValidationIssue(
            "error", "csv_headers", "CSV must contain two header rows.", source.source_path, case_id
        )
        return None, (issue,)

    objects, descriptions = rows[0], rows[1]
    if not objects or not descriptions:
        issue = ValidationIssue("error", "csv_headers", "CSV header rows are empty.", source.source_path, case_id)
        return None, (issue,)
    if objects[0].strip().casefold() != "results" or descriptions[0].strip().casefold() != "index":
        issues.append(
            ValidationIssue(
                "warning",
                "csv_header_labels",
                "Expected first header cells `Results` and `Index`; retained the source labels as supplied.",
                source.source_path,
                case_id,
            )
        )
    if len(objects) != len(descriptions):
        issues.append(
            ValidationIssue(
                "error",
                "header_width_mismatch",
                f"Header rows have different widths ({len(objects)} and {len(descriptions)} columns).",
                source.source_path,
                case_id,
            )
        )
        return None, tuple(issues)

    width = len(objects)
    data_rows: list[list[str]] = []
    ragged_rows: list[int] = []
    for row_number, row in enumerate(rows[2:], start=3):
        if not row or all(not value.strip() for value in row):
            continue
        if len(row) != width:
            ragged_rows.append(row_number)
            row = (row + [""] * width)[:width]
        data_rows.append(row)
    if ragged_rows:
        issues.append(
            ValidationIssue(
                "warning",
                "ragged_rows",
                f"{len(ragged_rows)} data row(s) had a different width and were padded or truncated; first source row {ragged_rows[0]}.",
                source.source_path,
                case_id,
            )
        )
    if not data_rows:
        issues.append(ValidationIssue("error", "empty_case", "CSV contains no sweep samples.", source.source_path, case_id))
        return None, tuple(issues)

    sweep_index: list[float | None] = []
    for offset, row in enumerate(data_rows, start=3):
        value = _number(row[0])
        sweep_index.append(value)
        if row[0].strip() and value is None:
            issues.append(
                ValidationIssue(
                    "warning",
                    "invalid_index",
                    f"Non-numeric sweep index at data row {offset}; that point remains unavailable.",
                    source.source_path,
                    case_id,
                    column_position=0,
                )
            )

    channels: list[Channel] = []
    blank_positions: list[int] = []
    for column_position in range(1, width):
        object_name = objects[column_position].strip()
        description = descriptions[column_position].strip()
        if not description:
            blank_positions.append(column_position)
            continue
        values: list[float | None] = []
        invalid_rows: list[int] = []
        for row_number, row in enumerate(data_rows, start=3):
            raw_value = row[column_position]
            number = _number(raw_value)
            values.append(number)
            if raw_value.strip() and number is None:
                invalid_rows.append(row_number)
        channels.append(
            Channel(
                object_name=object_name,
                metric_description=description,
                unit=_unit_from_description(description),
                column_position=column_position,
                numeric_values=tuple(values),
            )
        )
        if invalid_rows:
            issues.append(
                ValidationIssue(
                    "warning",
                    "non_numeric_values",
                    f"{len(invalid_rows)} non-numeric value(s) in `{description}`; first data row {invalid_rows[0]}.",
                    source.source_path,
                    case_id,
                    object_name,
                    column_position,
                )
            )

    if blank_positions:
        issues.append(
            ValidationIssue(
                "warning",
                "blank_channel_headings",
                f"Excluded {len(blank_positions)} column(s) with blank variable headings; positions: {', '.join(map(str, blank_positions))}.",
                source.source_path,
                case_id,
                column_position=blank_positions[0],
            )
        )

    case = CaseData(
        case_id=case_id,
        filename=filename,
        tokens=tokens,
        source_path=source.source_path,
        source_kind=source.origin,
        sha256=source.digest,
        sweep_index=tuple(sweep_index),
        channels=tuple(channels),
        validation_provenance=(source.source_path, f"sha256:{source.digest}"),
    )
    return case, tuple(issues)


def parse_cases(sources: Iterable[InputFile]) -> ParseResult:
    cases: list[CaseData] = []
    issues: list[ValidationIssue] = []
    for source in sources:
        case, case_issues = parse_csv_case(source)
        issues.extend(case_issues)
        if case is not None:
            cases.append(case)

    by_case_id: dict[str, list[CaseData]] = {}
    for case in cases:
        by_case_id.setdefault(case.case_id.casefold(), []).append(case)
    duplicates = {key: values for key, values in by_case_id.items() if len(values) > 1}
    if duplicates:
        duplicate_paths = {path for values in duplicates.values() for path in (case.source_path for case in values)}
        for key, values in sorted(duplicates.items()):
            files = ", ".join(case.source_path for case in values)
            issues.append(
                ValidationIssue(
                    "error",
                    "duplicate_case_id",
                    f"Case stem `{values[0].case_id}` occurs in multiple files: {files}. Resolve the conflict; none of these cases was loaded.",
                    case_id=values[0].case_id,
                )
            )
        cases = [case for case in cases if case.source_path not in duplicate_paths]

    cases.sort(key=lambda case: (tuple(token.casefold() for token in case.tokens), case.filename.casefold()))
    return ParseResult(tuple(cases), tuple(issues))
