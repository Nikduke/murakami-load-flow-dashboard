"""Pure filename-token filtering and stable case-label helpers."""

from __future__ import annotations

import hashlib
import re

from data_loader import CaseData


def natural_key(value: str) -> tuple[tuple[int, object], ...]:
    """Sort embedded numbers numerically while preserving stable text order."""
    parts = re.split(r"(\d+)", value.casefold())
    return tuple((1, int(part)) if part.isdigit() else (0, part) for part in parts)


def case_sort_key(case: CaseData) -> tuple[object, ...]:
    return tuple(natural_key(token) for token in case.tokens) + (natural_key(case.filename),)


def token_values(
    cases: list[CaseData] | tuple[CaseData, ...],
    position: int,
    previous_selections: list[set[str]] | tuple[set[str], ...] = (),
) -> list[str]:
    eligible = filter_cases(cases, previous_selections)
    return sorted(
        {case.tokens[position] for case in eligible if position < len(case.tokens)},
        key=natural_key,
    )


def filter_cases(
    cases: list[CaseData] | tuple[CaseData, ...],
    selections: list[set[str]] | tuple[set[str], ...],
) -> list[CaseData]:
    if any(not values for values in selections):
        return []
    selected = []
    for case in cases:
        if all(position < len(case.tokens) and case.tokens[position] in values
               for position, values in enumerate(selections)):
            selected.append(case)
    return sorted(selected, key=case_sort_key)


def varying_token_positions(cases: list[CaseData] | tuple[CaseData, ...]) -> list[int]:
    width = max((len(case.tokens) for case in cases), default=0)
    return [
        position
        for position in range(width)
        if len({case.tokens[position] if position < len(case.tokens) else "" for case in cases}) > 1
    ]


def case_labels(cases: list[CaseData] | tuple[CaseData, ...], positions: list[int]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for case in cases:
        parts = [case.tokens[position] for position in positions if position < len(case.tokens)]
        labels[case.case_id] = " | ".join(parts) if parts else "Case"
    collisions: dict[str, list[CaseData]] = {}
    for case in cases:
        collisions.setdefault(labels[case.case_id].casefold(), []).append(case)
    for values in collisions.values():
        if len(values) > 1:
            for case in values:
                labels[case.case_id] = f"{labels[case.case_id]} · {case.case_id}"
    return labels


def stable_case_colour(case_id: str) -> str:
    """Return a deterministic colour that does not depend on visible-case order."""
    hue = int(hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:8], 16) % 360
    # HSL is accepted by Plotly and gives readable, repeatable case colours.
    return f"hsl({hue}, 62%, 42%)"

