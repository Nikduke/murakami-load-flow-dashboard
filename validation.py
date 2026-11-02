"""Validation records shared by the CSV data and mapping layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    code: str
    message: str
    source_path: str = ""
    case_id: str = ""
    object_name: str = ""
    column_position: int | None = None
