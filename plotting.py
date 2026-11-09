"""Plotly curve construction, layout distribution, hover data and CSV export."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from html import escape
from io import StringIO
from itertools import chain
import math
import re
from typing import Iterable, Sequence

import plotly.graph_objects as go

from case_filters import case_sort_key, natural_key, stable_case_colour
from channel_catalogue import resolve_channel
from data_loader import CaseData, Channel
from validation import ValidationIssue


WEBGL_POINT_THRESHOLD = 20_000
CASE_LINE_STYLES = ("dash", "dot", "dashdot", "longdash", "longdashdot", "solid")
LEGEND_COLUMN_MAX = 4


@dataclass(frozen=True)
class Curve:
    case: CaseData
    case_label: str
    element_name: str
    series_name: str
    x_metric_description: str
    metric_description: str
    x_label: str
    x_unit: str
    y_label: str
    y_unit: str
    x_transform: str
    y_transform: str
    x_values: tuple[float | None, ...]
    y_values: tuple[float | None, ...]
    raw_x_values: tuple[float | None, ...]
    raw_y_values: tuple[float | None, ...]
    dash: str = "solid"
    width: float = 2.0


@dataclass(frozen=True)
class CurveBundle:
    element_name: str
    case: CaseData
    curves: tuple[Curve, ...]


@dataclass(frozen=True)
class PlotSet:
    figures: tuple[go.Figure, ...]
    panels: tuple[tuple[CurveBundle, ...], ...]
    bundles: tuple[CurveBundle, ...]
    issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True)
class PlotOptions:
    layout: str = "1 plot"
    panel_width: int | None = None


def _transform(values: Sequence[float | None], factor: float) -> tuple[float | None, ...]:
    return tuple(None if value is None else value * factor for value in values)


def _case_label(labels: dict[str, str], case: CaseData) -> str:
    return labels.get(case.case_id, case.case_id)


def _strip_shared_token_prefix(values: dict[str, str]) -> dict[str, str]:
    prefix = next(iter(values.values()))
    for value in values.values():
        common = 0
        while common < min(len(prefix), len(value)) and prefix[common].casefold() == value[common].casefold():
            common += 1
        prefix = prefix[:common]
    if len(prefix) >= 3 and prefix[-1] in "_-":
        return {case_id: value[len(prefix):] for case_id, value in values.items()}
    return values


def _legend_case_labels(panel: Sequence[CurveBundle]) -> tuple[dict[str, str], str]:
    cases = {bundle.case.case_id: bundle.case for bundle in panel}
    full_labels = {
        bundle.case.case_id: bundle.curves[0].case_label
        for bundle in panel
        if bundle.curves
    }
    compact_parts = {case_id: [] for case_id in cases}
    common_values: list[str] = []
    token_width = max((len(case.tokens) for case in cases.values()), default=0)
    for position in range(token_width):
        values = {
            case_id: case.tokens[position] if position < len(case.tokens) else ""
            for case_id, case in cases.items()
        }
        unique_values = set(values.values())
        if len(unique_values) == 1:
            common = re.sub(r"^\d+\s+", "", next(iter(unique_values)))
            if common:
                common_values.append(common)
            continue
        if not all(values.values()):
            continue

        values = _strip_shared_token_prefix(values)

        without_index = {
            case_id: re.sub(r"^\d+\s+", "", value)
            for case_id, value in values.items()
        }
        if len(set(without_index.values())) == len(set(values.values())):
            values = _strip_shared_token_prefix(without_index)

        for case_id, value in values.items():
            compact_parts[case_id].append(value)

    labels = {
        case_id: " · ".join(parts) if parts else "Selected case" if len(cases) == 1 else full_labels.get(case_id, case_id)
        for case_id, parts in compact_parts.items()
    }
    collisions: dict[str, list[str]] = {}
    for case_id, label in labels.items():
        collisions.setdefault(label.casefold(), []).append(case_id)
    for case_ids in collisions.values():
        if len(case_ids) > 1:
            for case_id in case_ids:
                labels[case_id] = full_labels.get(case_id, case_id)
    return labels, " · ".join(common_values)


def _legend_column_layout(
    longest_label: str,
    case_count: int,
    panel_count: int,
    panel_width: int | None = None,
) -> tuple[int, float]:
    container_width = panel_width or (520 if panel_count == 4 else 1066)
    available_width = max(1, container_width - 110)

    if case_count <= 1:
        return 1, available_width

    column_width = max(160.0, 40.0 + 6.0 * len(longest_label))
    layout_column_max = 2 if panel_count == 4 else LEGEND_COLUMN_MAX
    columns = max(1, min(layout_column_max, case_count, int(available_width // column_width)))
    return columns, available_width / columns - 45


def _issue(case: CaseData, object_name: str, role: str, message: str, severity: str = "warning") -> ValidationIssue:
    return ValidationIssue(
        severity, f"plot_{role}", f"{case.filename}: {message}", case.source_path, case.case_id, object_name
    )


def _resolved(
    case: CaseData,
    object_name: str,
    role: str,
    issues: list[ValidationIssue],
    optional: bool = False,
) -> Channel | None:
    result = resolve_channel(case, object_name, role)
    if result.status == "found":
        return result.channel
    if optional and result.status == "missing":
        return None
    severity = "error" if result.status in {"ambiguous", "unit_conflict"} else "warning"
    issues.append(_issue(case, object_name, role, result.message, severity))
    return None


def _pair_bundle(
    case: CaseData,
    object_name: str,
    case_label: str,
    x_channel: Channel,
    y_channel: Channel,
    *,
    x_factor: float,
    y_factor: float,
    x_label: str,
    y_label: str,
    series_name: str = "operating curve",
    x_transform: str = "raw exported values",
    y_transform: str = "raw exported values",
    dash: str = "solid",
) -> Curve:
    return Curve(
        case=case,
        case_label=case_label,
        element_name=object_name,
        series_name=series_name,
        x_metric_description=x_channel.metric_description,
        metric_description=y_channel.metric_description,
        x_label=x_label,
        x_unit=x_channel.unit,
        y_label=y_label,
        y_unit=y_channel.unit,
        x_transform=x_transform,
        y_transform=y_transform,
        x_values=_transform(x_channel.numeric_values, x_factor),
        y_values=_transform(y_channel.numeric_values, y_factor),
        raw_x_values=x_channel.numeric_values,
        raw_y_values=y_channel.numeric_values,
        dash=dash,
    )


def build_wtg_pq_bundles(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    labels: dict[str, str],
    show_qmin: bool = True,
    show_qmax: bool = True,
    selected_bundle_ids: frozenset[tuple[str, str]] | None = None,
) -> tuple[tuple[CurveBundle, ...], tuple[ValidationIssue, ...]]:
    bundles: list[CurveBundle] = []
    issues: list[ValidationIssue] = []
    ordered_cases = sorted(cases, key=case_sort_key)
    case_line_styles = {
        case.case_id: CASE_LINE_STYLES[index % len(CASE_LINE_STYLES)]
        for index, case in enumerate(ordered_cases)
    }
    selected_case_ids = {case_id for case_id, _ in selected_bundle_ids} if selected_bundle_ids is not None else None
    for case in ordered_cases:
        if selected_case_ids is not None and case.case_id not in selected_case_ids:
            continue
        case_line_style = case_line_styles[case.case_id]
        for object_name in sorted(selected_objects, key=natural_key):
            if selected_bundle_ids is not None and (case.case_id, object_name) not in selected_bundle_ids:
                continue
            p_channel = _resolved(case, object_name, "active_power", issues)
            q_channel = _resolved(case, object_name, "reactive_power", issues)
            if p_channel is None or q_channel is None:
                continue
            case_label = _case_label(labels, case)
            curves = [
                _pair_bundle(
                    case,
                    object_name,
                    case_label,
                    q_channel,
                    p_channel,
                    x_factor=1.0,
                    y_factor=1.0,
                    x_label="Reactive power, Q",
                    y_label="Active power, P",
                    dash=case_line_style,
                )
            ]
            for role, enabled, name in (
                ("qmin", show_qmin, "Qmin capability boundary"),
                ("qmax", show_qmax, "Qmax capability boundary"),
            ):
                if not enabled:
                    continue
                limit_channel = _resolved(case, object_name, role, issues, optional=True)
                if limit_channel is None:
                    continue
                if not any(value is not None for value in limit_channel.numeric_values):
                    continue
                curves.append(
                    _pair_bundle(
                        case,
                        object_name,
                        case_label,
                        limit_channel,
                        p_channel,
                        x_factor=1.0,
                        y_factor=1.0,
                        x_label="Reactive power, Q",
                        y_label="Active power, P",
                        series_name=name,
                        dash=case_line_style,
                    )
                )
            bundles.append(CurveBundle(object_name, case, tuple(curves)))
    return tuple(bundles), tuple(issues)


def build_wtg_voltage_bundles(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    labels: dict[str, str],
    selected_bundle_ids: frozenset[tuple[str, str]] | None = None,
) -> tuple[tuple[CurveBundle, ...], tuple[ValidationIssue, ...]]:
    bundles: list[CurveBundle] = []
    issues: list[ValidationIssue] = []
    selected_case_ids = {case_id for case_id, _ in selected_bundle_ids} if selected_bundle_ids is not None else None
    for case in sorted(cases, key=case_sort_key):
        if selected_case_ids is not None and case.case_id not in selected_case_ids:
            continue
        for object_name in sorted(selected_objects, key=natural_key):
            if selected_bundle_ids is not None and (case.case_id, object_name) not in selected_bundle_ids:
                continue
            p_channel = _resolved(case, object_name, "active_power", issues)
            u_channel = _resolved(case, object_name, "voltage", issues)
            if p_channel is None or u_channel is None:
                continue
            curve = _pair_bundle(
                case,
                object_name,
                _case_label(labels, case),
                p_channel,
                u_channel,
                x_factor=1.0,
                y_factor=1.0,
                x_label="Active power, P",
                y_label="Terminal voltage, U",
            )
            bundles.append(CurveBundle(object_name, case, (curve,)))
    return tuple(bundles), tuple(issues)


def build_loading_bundles(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    x_source: str,
    labels: dict[str, str],
    selected_bundle_ids: frozenset[tuple[str, str]] | None = None,
) -> tuple[tuple[CurveBundle, ...], tuple[ValidationIssue, ...]]:
    bundles: list[CurveBundle] = []
    issues: list[ValidationIssue] = []
    selected_case_ids = {case_id for case_id, _ in selected_bundle_ids} if selected_bundle_ids is not None else None
    for case in sorted(cases, key=case_sort_key):
        if selected_case_ids is not None and case.case_id not in selected_case_ids:
            continue
        x_channel = _resolved(case, x_source, "active_interchange", issues)
        if x_channel is None:
            continue
        for object_name in sorted(selected_objects, key=natural_key):
            if selected_bundle_ids is not None and (case.case_id, object_name) not in selected_bundle_ids:
                continue
            y_channel = _resolved(case, object_name, "loading", issues)
            if y_channel is None:
                continue
            x_label = f"−{x_source} active power interchange"
            curve = _pair_bundle(
                case,
                object_name,
                _case_label(labels, case),
                x_channel,
                y_channel,
                x_factor=-1.0,
                y_factor=1.0,
                x_label=x_label,
                y_label="Equipment loading",
                x_transform=f"−1 × exported Active Power Interchange from {x_source}",
                y_transform="raw exported loading value",
            )
            bundles.append(CurveBundle(object_name, case, (curve,)))
    return tuple(bundles), tuple(issues)


def build_poc_pq_bundles(
    cases: Sequence[CaseData], selected_objects: Sequence[str], labels: dict[str, str]
) -> tuple[tuple[CurveBundle, ...], tuple[ValidationIssue, ...]]:
    bundles: list[CurveBundle] = []
    issues: list[ValidationIssue] = []
    for case in sorted(cases, key=case_sort_key):
        for object_name in sorted(selected_objects, key=natural_key):
            p_channel = _resolved(case, object_name, "active_interchange", issues)
            q_channel = _resolved(case, object_name, "reactive_interchange", issues)
            if p_channel is None or q_channel is None:
                continue
            curve = _pair_bundle(
                case,
                object_name,
                _case_label(labels, case),
                q_channel,
                p_channel,
                x_factor=-1.0,
                y_factor=-1.0,
                x_label="−Reactive power interchange",
                y_label="−Active power interchange",
                x_transform="−1 × exported Reactive Power Interchange",
                y_transform="−1 × exported Active Power Interchange",
            )
            bundles.append(CurveBundle(object_name, case, (curve,)))
    return tuple(bundles), tuple(issues)


def build_power_factor_bundles(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    labels: dict[str, str],
    x_source: str = "Sweep index",
    pf_sign_mode: str = "Original PowerFactory plot",
) -> tuple[tuple[CurveBundle, ...], tuple[ValidationIssue, ...]]:
    bundles: list[CurveBundle] = []
    issues: list[ValidationIssue] = []
    for case in sorted(cases, key=case_sort_key):
        zero_sweep_indices = {
            index for index, sweep_index in enumerate(case.sweep_index) if sweep_index == 0
        }
        for object_name in sorted(selected_objects, key=natural_key):
            y_channel = _resolved(case, object_name, "power_factor", issues)
            if y_channel is None:
                continue

            if pf_sign_mode == "Raw exported values":
                y_factor = 1.0
                y_transform = "raw exported power-factor value (× +1)"
            elif pf_sign_mode == "Invert selected channels":
                y_factor = -1.0
                y_transform = "−1 × raw exported power-factor value (user selected)"
            else:
                aggregate = object_name.casefold() in {"exp_cable_1", "exp_cable_2"}
                y_factor = -1.0 if aggregate else 1.0
                y_transform = (
                    "−1 × raw exported power-factor value (PowerFactory aggregate export-cable plot)"
                    if aggregate
                    else "raw exported power-factor value (× +1; no verified aggregate transform)"
                )

            if x_source == "Sweep index":
                raw_x = case.sweep_index
                x_unit = "index"
                x_label = "Sweep index"
                x_transform = "raw sweep index; not a physical power axis"
            else:
                x_channel = _resolved(case, x_source, "active_interchange", issues)
                if x_channel is None:
                    continue
                raw_x = x_channel.numeric_values
                x_unit = x_channel.unit
                x_label = f"−{x_source} active power interchange"
                x_transform = f"−1 × exported Active Power Interchange from {x_source}"
            x_values = _transform(raw_x, -1.0 if x_source != "Sweep index" else 1.0)
            y_values = _transform(y_channel.numeric_values, y_factor)
            x_values = tuple(
                None if index in zero_sweep_indices else value
                for index, value in enumerate(x_values)
            )
            y_values = tuple(
                None if index in zero_sweep_indices else value
                for index, value in enumerate(y_values)
            )
            curve = Curve(
                case=case,
                case_label=_case_label(labels, case),
                element_name=object_name,
                series_name="power factor",
                x_metric_description="Sweep index" if x_source == "Sweep index" else x_channel.metric_description,
                metric_description=y_channel.metric_description,
                x_label=x_label,
                x_unit=x_unit,
                y_label="Power factor",
                y_unit="",
                x_transform=x_transform,
                y_transform=y_transform,
                x_values=x_values,
                y_values=y_values,
                raw_x_values=raw_x,
                raw_y_values=y_channel.numeric_values,
            )
            bundles.append(CurveBundle(object_name, case, (curve,)))
    return tuple(bundles), tuple(issues)


def _layout_count(layout: str) -> int:
    normalized = layout.casefold().replace(" ", "").replace("×", "x")
    if normalized == "1plot":
        return 1
    if normalized == "1x2":
        return 2
    if normalized == "2x2":
        return 4
    raise ValueError(f"Unknown plot layout: {layout}")


def distribute_bundles(
    bundles: Sequence[CurveBundle], panel_count: int
) -> tuple[tuple[CurveBundle, ...], ...]:
    """Assign complete bundles once, balancing plotted points across panels."""
    ordered = sorted(bundles, key=lambda bundle: (natural_key(bundle.element_name), case_sort_key(bundle.case)))
    if not ordered:
        return ()
    panel_count = min(max(1, panel_count), len(ordered))
    group_by_element = len({bundle.element_name for bundle in ordered}) >= len(
        {bundle.case.case_id for bundle in ordered}
    )

    grouped: dict[str, list[CurveBundle]] = {}
    for bundle in ordered:
        key = bundle.element_name if group_by_element else bundle.case.case_id
        grouped.setdefault(key, []).append(bundle)
    group_items = sorted(
        grouped.items(),
        key=lambda item: natural_key(item[0]) if group_by_element else case_sort_key(item[1][0].case),
    )

    def group_weight(group: Sequence[CurveBundle]) -> int:
        return sum(len(curve.x_values) for bundle in group for curve in bundle.curves)

    # Keep case/element groups when possible; otherwise balance individual bundles.
    if len(group_items) < panel_count:
        group_items = [
            (str(index), [bundle])
            for index, bundle in enumerate(bundle for _, group in group_items for bundle in group)
        ]
    group_items.sort(key=lambda item: -group_weight(item[1]))

    panels: list[list[CurveBundle]] = [[] for _ in range(panel_count)]
    panel_weights = [0] * panel_count
    for _, group in group_items:
        panel_index = min(range(panel_count), key=lambda index: (panel_weights[index], len(panels[index]), index))
        panels[panel_index].extend(group)
        panel_weights[panel_index] += group_weight(group)

    for panel in panels:
        panel.sort(key=lambda bundle: (natural_key(bundle.element_name), case_sort_key(bundle.case)))
    return tuple(tuple(panel) for panel in panels if panel)


def _finite(values: Iterable[float | None]) -> Iterable[float]:
    for value in values:
        if value is None:
            continue
        number = float(value)
        if math.isfinite(number):
            yield number


def _expanded_range(values: Iterable[float], fraction: float = 0.04) -> tuple[float, float] | None:
    iterator = iter(values)
    try:
        low = high = next(iterator)
    except StopIteration:
        return None
    for value in iterator:
        if value < low:
            low = value
        elif value > high:
            high = value
    span = high - low
    pad = span * fraction if span else max(abs(high) * fraction, 0.5)
    return low - pad, high + pad


def bundle_ranges(
    bundles: Sequence[CurveBundle], reference_y: Sequence[float] = ()
) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    def values(axis: str) -> Iterable[float | None]:
        for bundle in bundles:
            for curve in bundle.curves:
                yield from getattr(curve, axis)

    return (
        _expanded_range(_finite(values("x_values"))),
        _expanded_range(_finite(chain(reference_y, values("y_values")))),
    )


def build_plot_set(
    bundles: Sequence[CurveBundle],
    *,
    title: str,
    x_title: str,
    y_title: str,
    options: PlotOptions,
    reference_y: Sequence[tuple[float, str]] = (),
) -> PlotSet:
    panel_count = _layout_count(options.layout)
    panels = distribute_bundles(bundles, panel_count)
    flat_bundles = tuple(bundle for panel in panels for bundle in panel)
    shared_x, shared_y = bundle_ranges(flat_bundles, [value for value, _ in reference_y])
    base_height = 700 if panel_count == 1 else 520 if panel_count == 2 else 450
    panel_legend_data = [_legend_case_labels(panel) for panel in panels]
    columns_per_row = 2 if panel_count == 4 else 1
    panel_legend_layouts = []
    row_legend_rows: dict[int, int] = {}
    for panel_index, (labels, _) in enumerate(panel_legend_data):
        longest_label = max(labels.values(), key=len, default="")
        column_capacity, entry_width = _legend_column_layout(
            longest_label, len(labels), panel_count, options.panel_width
        )
        legend_rows = math.ceil(len(labels) / column_capacity) if labels else 0
        panel_legend_layouts.append((legend_rows, entry_width))
        display_row = panel_index // columns_per_row
        row_legend_rows[display_row] = max(row_legend_rows.get(display_row, 0), legend_rows)
    compact_grid_layout = panel_count == 4
    figures: list[go.Figure] = []

    for panel_index, panel in enumerate(panels, start=1):
        _, legend_entry_width = panel_legend_layouts[panel_index - 1]
        display_row = (panel_index - 1) // columns_per_row
        legend_bottom = max(
            104 if compact_grid_layout else 110,
            86 + 18 * row_legend_rows[display_row],
        )
        height = base_height + legend_bottom - 110
        plot_area_height = height - 58 - legend_bottom
        legend_y = -78 / plot_area_height
        case_options_y = -46 / plot_area_height
        figure = go.Figure()
        legend_cases: set[str] = set()
        legend_labels, shared_case_options = panel_legend_data[panel_index - 1]
        capability_labels = {
            "Qmin capability boundary": "Qmin",
            "Qmax capability boundary": "Qmax",
        }
        panel_objects = {bundle.element_name for bundle in panel}
        panel_point_count = sum(
            len(curve.x_values)
            for bundle in panel
            for curve in bundle.curves
        )
        trace_type = go.Scattergl if panel_point_count > WEBGL_POINT_THRESHOLD else go.Scatter
        for bundle in panel:
            for curve in bundle.curves:
                if not any(value is not None for value in curve.x_values) or not any(
                    value is not None for value in curve.y_values
                ):
                    continue
                is_limit = curve.series_name in capability_labels
                colour = "#555555" if is_limit else stable_case_colour(curve.case.case_id)
                show_legend = curve.case.case_id not in legend_cases
                legend_cases.add(curve.case.case_id)
                legend_group = curve.case.case_id
                trace_meta = [
                    curve.case_label,
                    curve.element_name,
                    capability_labels.get(curve.series_name, ""),
                ]
                hover_lines = ["Case options: <b>%{meta[0]}</b>"]
                if len(panel_objects) > 1:
                    hover_lines.append("Equipment: %{meta[1]}")
                if trace_meta[2]:
                    hover_lines.append("Boundary: %{meta[2]}")
                hover_lines.extend((
                    f"{curve.x_label} ({curve.x_unit or 'unitless'}): %{{x:.7g}}",
                    f"{curve.y_label} ({curve.y_unit or 'unitless'}): %{{y:.7g}}",
                    "<extra></extra>",
                ))
                figure.add_trace(
                    trace_type(
                        x=curve.x_values,
                        y=curve.y_values,
                        meta=trace_meta,
                        mode="lines",
                        name=legend_labels.get(curve.case.case_id, curve.case_label),
                        showlegend=show_legend,
                        legendgroup=legend_group,
                        line={"color": colour, "dash": curve.dash, "width": 1.4 if is_limit else curve.width},
                        hovertemplate="<br>".join(hover_lines),
                    )
                )

        for value, label in reference_y:
            figure.add_hline(
                y=value,
                line_dash="dash",
                line_color="#c33b35",
                line_width=1.2,
                annotation_text=label,
                annotation_position="top left",
                annotation_xshift=48,
                annotation_font_color="#9d2d29",
            )
        title_parts = [title]
        if len(panel_objects) == 1:
            object_label = next(iter(panel_objects)).replace("\\", "/").rsplit("/", 1)[-1]
            title_parts.append(object_label)
        if len(panels) > 1:
            title_parts.append(f"Panel {panel_index} of {len(panels)}")
        figure.update_layout(
            title={"text": " · ".join(title_parts), "x": 0.02},
            template="plotly_white",
            height=height,
            margin={"l": 70, "r": 24, "t": 58, "b": legend_bottom},
            hovermode="closest",
            font={"color": "#263445", "family": "Arial, sans-serif", "size": 12},
            paper_bgcolor="white",
            plot_bgcolor="white",
            legend={
                "orientation": "h",
                "y": legend_y,
                "yref": "paper",
                "x": 0,
                "xref": "paper",
                "xanchor": "left",
                "yanchor": "top",
                "entrywidth": legend_entry_width,
                "entrywidthmode": "pixels",
                "tracegroupgap": 0,
                "groupclick": "togglegroup",
                "itemclick": "toggle",
                "itemdoubleclick": "toggleothers",
                "font": {"size": 12},
            },
            showlegend=True,
        )
        figure.add_annotation(
            text=(
                f"Case options: <b>{escape(shared_case_options)}</b>"
                if shared_case_options
                else "Case options"
            ),
            xref="paper",
            yref="paper",
            x=0,
            y=case_options_y,
            xanchor="left",
            yanchor="top",
            align="left",
            showarrow=False,
            font={"size": 12, "color": "#263445"},
        )
        figure.update_xaxes(
            title_text=f"{x_title} ({panel[0].curves[0].x_unit or 'unitless'})" if panel else x_title,
            title_standoff=6 if compact_grid_layout else 15,
            showgrid=True,
            gridcolor="#e6e9ed",
            zeroline=True,
            zerolinecolor="#b9c0c8",
            range=list(shared_x) if shared_x else None,
            autorange=shared_x is None,
        )
        figure.update_yaxes(
            title_text=f"{y_title} ({panel[0].curves[0].y_unit or 'unitless'})" if panel else y_title,
            showgrid=True,
            gridcolor="#e6e9ed",
            zeroline=True,
            zerolinecolor="#b9c0c8",
            range=list(shared_y) if shared_y else None,
            autorange=shared_y is None,
        )
        figures.append(figure)

    return PlotSet(tuple(figures), panels, tuple(bundles), ())


def build_wtg_pq_figures(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    labels: dict[str, str],
    *,
    options: PlotOptions,
    show_qmin: bool = True,
    show_qmax: bool = True,
    selected_bundle_ids: frozenset[tuple[str, str]] | None = None,
) -> PlotSet:
    bundles, issues = build_wtg_pq_bundles(
        cases, selected_objects, labels, show_qmin, show_qmax, selected_bundle_ids
    )
    result = build_plot_set(
        bundles,
        title="WTG P–Q",
        x_title="Reactive power, Q",
        y_title="Active power, P",
        options=options,
    )
    return PlotSet(result.figures, result.panels, result.bundles, issues)


def build_wtg_voltage_figures(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    labels: dict[str, str],
    *,
    options: PlotOptions,
    show_references: bool = True,
    low_reference: float = 0.92,
    high_reference: float = 1.08,
    selected_bundle_ids: frozenset[tuple[str, str]] | None = None,
) -> PlotSet:
    bundles, issues = build_wtg_voltage_bundles(cases, selected_objects, labels, selected_bundle_ids)
    references = ((low_reference, f"Min = {low_reference:.2f} p.u."),
                  (high_reference, f"Max = {high_reference:.2f} p.u.")) if show_references else ()
    result = build_plot_set(
        bundles,
        title="WTG terminal voltage",
        x_title="Active power, P",
        y_title="Terminal voltage, U",
        options=options,
        reference_y=references,
    )
    return PlotSet(result.figures, result.panels, result.bundles, issues)


def build_equipment_loading_figures(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    x_source: str,
    labels: dict[str, str],
    *,
    options: PlotOptions,
    loading_reference: float = 100.0,
    selected_bundle_ids: frozenset[tuple[str, str]] | None = None,
) -> PlotSet:
    bundles, issues = build_loading_bundles(
        cases, selected_objects, x_source, labels, selected_bundle_ids
    )
    result = build_plot_set(
        bundles,
        title="Equipment loading",
        x_title=f"−{x_source} active power interchange",
        y_title="Equipment loading",
        options=options,
        reference_y=((loading_reference, f"Y = {loading_reference:g}%"),),
    )
    figures = list(result.figures)
    for figure, panel in zip(figures, result.panels):
        peak: tuple[float, float, Curve] | None = None
        for bundle in panel:
            for curve in bundle.curves:
                for x, y in zip(curve.x_values, curve.y_values):
                    if x is None or y is None:
                        continue
                    x_value, y_value = float(x), float(y)
                    if not math.isfinite(x_value) or not math.isfinite(y_value):
                        continue
                    if peak is None or y_value > peak[1]:
                        peak = (x_value, y_value, curve)
        if peak is None:
            continue
        x_value, y_value, curve = peak
        figure.add_annotation(
            x=x_value,
            y=y_value,
            text=f"{x_value:.1f} {curve.x_unit}<br>{y_value:.1f} {curve.y_unit}",
            showarrow=True,
            arrowhead=2,
            ax=-40,
            ay=-30,
            font={"size": 11, "color": "#263445"},
            bgcolor="rgba(255,255,255,0.8)",
        )
    return PlotSet(tuple(figures), result.panels, result.bundles, issues)


def build_poc_pq_figures(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    labels: dict[str, str],
    *,
    options: PlotOptions,
) -> PlotSet:
    bundles, issues = build_poc_pq_bundles(cases, selected_objects, labels)
    result = build_plot_set(
        bundles,
        title="POC P–Q",
        x_title="−Reactive power interchange",
        y_title="−Active power interchange",
        options=options,
    )
    return PlotSet(result.figures, result.panels, result.bundles, issues)


def build_power_factor_figures(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    labels: dict[str, str],
    *,
    options: PlotOptions,
    x_source: str = "Sweep index",
    pf_sign_mode: str = "Original PowerFactory plot",
) -> PlotSet:
    bundles, issues = build_power_factor_bundles(cases, selected_objects, labels, x_source, pf_sign_mode)
    x_title = "Sweep index" if x_source == "Sweep index" else f"−{x_source} active power interchange"
    result = build_plot_set(
        bundles,
        title="Power factor",
        x_title=x_title,
        y_title="Power factor",
        options=options,
    )
    return PlotSet(result.figures, result.panels, result.bundles, issues)


def plotted_data_csv(bundles: Sequence[CurveBundle]) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "case_id",
            "case_filename",
            "case_tokens",
            "case_source_path",
            "source_object",
            "series",
            "original_x_metric_description",
            "original_metric_description",
            "x_axis",
            "x_unit",
            "y_axis",
            "y_unit",
            "x_transform",
            "y_transform",
            "sweep_index",
            "raw_x_value",
            "raw_y_value",
            "plotted_x_value",
            "plotted_y_value",
        ]
    )
    for bundle in bundles:
        for curve in bundle.curves:
            for index, (x_value, y_value) in enumerate(zip(curve.x_values, curve.y_values)):
                if x_value is None or y_value is None:
                    continue
                writer.writerow(
                    [
                        curve.case.case_id,
                        curve.case.filename,
                        " | ".join(curve.case.tokens),
                        curve.case.source_path,
                        curve.element_name,
                        curve.series_name,
                        curve.x_metric_description,
                        curve.metric_description,
                        curve.x_label,
                        curve.x_unit,
                        curve.y_label,
                        curve.y_unit,
                        curve.x_transform,
                        curve.y_transform,
                        curve.case.sweep_index[index] if index < len(curve.case.sweep_index) else "",
                        curve.raw_x_values[index] if index < len(curve.raw_x_values) else "",
                        curve.raw_y_values[index] if index < len(curve.raw_y_values) else "",
                        x_value,
                        y_value,
                    ]
                )
    return output.getvalue().encode("utf-8-sig")
