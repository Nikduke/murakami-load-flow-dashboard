"""Summaries of sweep samples outside configured limits."""

from __future__ import annotations

import math
from typing import Iterable, Sequence

from channel_catalogue import resolve_channel
from data_loader import CaseData


ViolationRow = dict[str, str | int | float]


def _breach_summary(
    samples: Iterable[tuple[float | None, float | None, float | None]], *, lower: bool
) -> tuple[float, float, float, float] | None:
    worst: tuple[float, float, float, float] | None = None
    for location, value, limit in samples:
        if location is None or value is None or limit is None:
            continue
        if not all(math.isfinite(item) for item in (location, value, limit)):
            continue
        excess = limit - value if lower else value - limit
        if excess <= 0:
            continue
        if worst is None or excess > worst[3]:
            worst = location, value, limit, excess
    return worst


def _row_prefix(
    case: CaseData, object_name: str, labels: dict[str, str], element_column: str = "WTG"
) -> dict[str, str]:
    return {
        "_case_id": case.case_id,
        "_object_name": object_name,
        element_column: object_name.replace("\\", "/").rsplit("/", 1)[-1],
        "Case": labels.get(case.case_id, case.case_id),
    }


def _sort_rows(
    rows: list[ViolationRow], excess_column: str, element_column: str = "WTG"
) -> list[ViolationRow]:
    rows.sort(
        key=lambda row: (
            -float(row[excess_column]),
            str(row[element_column]).casefold(),
            str(row["Case"]).casefold(),
            str(row.get("Limit", "")).casefold(),
        )
    )
    return rows


def wtg_pq_limit_violations(
    cases: Sequence[CaseData], selected_objects: Sequence[str], labels: dict[str, str]
) -> list[ViolationRow]:
    """Report actual Q samples outside the case-matched Qmin/Qmax channels."""
    rows: list[ViolationRow] = []
    for case in cases:
        for object_name in selected_objects:
            power = resolve_channel(case, object_name, "active_power").channel
            reactive = resolve_channel(case, object_name, "reactive_power").channel
            if power is None or reactive is None:
                continue
            for role, label, lower in (("qmin", "Qmin", True), ("qmax", "Qmax", False)):
                limit = resolve_channel(case, object_name, role).channel
                if limit is None:
                    continue
                result = _breach_summary(
                    zip(power.numeric_values, reactive.numeric_values, limit.numeric_values), lower=lower
                )
                if result is None:
                    continue
                active_power, q_value, q_limit, excess = result
                rows.append(
                    {
                        **_row_prefix(case, object_name, labels),
                        "Limit": label,
                        "P at worst point (MW)": active_power,
                        "Q (Mvar)": q_value,
                        "Limit (Mvar)": q_limit,
                        "Excess (Mvar)": excess,
                    }
                )
    return _sort_rows(rows, "Excess (Mvar)")


def wtg_voltage_limit_violations(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    labels: dict[str, str],
    low_reference: float,
    high_reference: float,
) -> list[ViolationRow]:
    """Report voltage samples outside the user-selected minimum and maximum."""
    if low_reference >= high_reference:
        return []

    rows: list[ViolationRow] = []
    for case in cases:
        for object_name in selected_objects:
            power = resolve_channel(case, object_name, "active_power").channel
            voltage = resolve_channel(case, object_name, "voltage").channel
            if power is None or voltage is None:
                continue
            samples = tuple(zip(power.numeric_values, voltage.numeric_values))
            for label, reference, lower in (
                ("Min voltage", low_reference, True),
                ("Max voltage", high_reference, False),
            ):
                result = _breach_summary(
                    ((active_power, value, reference) for active_power, value in samples), lower=lower
                )
                if result is None:
                    continue
                active_power, measured_voltage, voltage_limit, excess = result
                rows.append(
                    {
                        **_row_prefix(case, object_name, labels),
                        "Limit": label,
                        "P at worst point (MW)": active_power,
                        "Voltage (p.u.)": measured_voltage,
                        "Limit (p.u.)": voltage_limit,
                        "Excess (p.u.)": excess,
                    }
                )
    return _sort_rows(rows, "Excess (p.u.)")


def equipment_loading_limit_violations(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    labels: dict[str, str],
    x_source: str,
    loading_reference: float,
) -> list[ViolationRow]:
    """Report selected equipment-loading samples above the displayed reference."""
    rows: list[ViolationRow] = []
    for case in cases:
        interchange = resolve_channel(case, x_source, "active_interchange").channel
        if interchange is None:
            continue
        for object_name in selected_objects:
            loading = resolve_channel(case, object_name, "loading").channel
            if loading is None:
                continue
            result = _breach_summary(
                (
                    (-value if value is not None else None, load, loading_reference)
                    for value, load in zip(interchange.numeric_values, loading.numeric_values)
                ),
                lower=False,
            )
            if result is None:
                continue
            x_value, measured_loading, limit, excess = result
            rows.append(
                {
                    **_row_prefix(case, object_name, labels, "Equipment"),
                    "X at worst point (MW)": x_value,
                    "Loading (%)": measured_loading,
                    "Limit (%)": limit,
                    "Excess (%)": excess,
                }
            )
    return _sort_rows(rows, "Excess (%)", "Equipment")
