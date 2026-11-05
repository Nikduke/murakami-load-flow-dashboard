"""Summaries of WTG sweep points outside their configured limits."""

from __future__ import annotations

import math
from typing import Iterable, Sequence

from channel_catalogue import resolve_channel
from data_loader import CaseData


ViolationRow = dict[str, str | int | float]


def _breach_summary(
    samples: Iterable[tuple[float | None, float | None, float | None]], *, lower: bool
) -> tuple[int, tuple[float, float, float, float]] | None:
    count = 0
    worst: tuple[float, float, float, float] | None = None
    for power, value, limit in samples:
        if power is None or value is None or limit is None:
            continue
        if not all(math.isfinite(item) for item in (power, value, limit)):
            continue
        excess = limit - value if lower else value - limit
        if excess <= 0:
            continue
        count += 1
        if worst is None or excess > worst[3]:
            worst = power, value, limit, excess
    return (count, worst) if worst is not None else None


def _row_prefix(case: CaseData, object_name: str, labels: dict[str, str]) -> dict[str, str]:
    return {
        "WTG": object_name.replace("\\", "/").rsplit("/", 1)[-1],
        "Case": labels.get(case.case_id, case.case_id),
    }


def _sort_rows(rows: list[ViolationRow], excess_column: str) -> list[ViolationRow]:
    rows.sort(
        key=lambda row: (
            -float(row[excess_column]),
            -int(row["Violating points"]),
            str(row["WTG"]).casefold(),
            str(row["Case"]).casefold(),
            str(row["Limit"]).casefold(),
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
                count, (active_power, q_value, q_limit, excess) = result
                rows.append(
                    {
                        **_row_prefix(case, object_name, labels),
                        "Limit": label,
                        "Violating points": count,
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
                count, (active_power, measured_voltage, voltage_limit, excess) = result
                rows.append(
                    {
                        **_row_prefix(case, object_name, labels),
                        "Limit": label,
                        "Violating points": count,
                        "P at worst point (MW)": active_power,
                        "Voltage (p.u.)": measured_voltage,
                        "Limit (p.u.)": voltage_limit,
                        "Excess (p.u.)": excess,
                    }
                )
    return _sort_rows(rows, "Excess (p.u.)")
