"""Plotly curve construction, layout distribution, hover data and CSV export."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
import math
from typing import Iterable, Sequence

import plotly.graph_objects as go

from case_filters import case_sort_key, natural_key, stable_case_colour
from channel_catalogue import resolve_channel
from data_loader import CaseData, Channel
from validation import ValidationIssue


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
    line_colour: str = ""
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
    distribution_used: str
    x_range: tuple[float, float] | None
    y_range: tuple[float, float] | None


@dataclass(frozen=True)
class PlotOptions:
    layout: str = "1 plot"
    distribution: str = "Auto"
    independent_ranges: bool = False
    x_range: tuple[float, float] | None = None
    y_range: tuple[float, float] | None = None
    height: int | None = None


def _transform(values: Sequence[float | None], factor: float) -> tuple[float | None, ...]:
    return tuple(None if value is None else value * factor for value in values)


def _case_label(labels: dict[str, str], case: CaseData) -> str:
    return labels.get(case.case_id, case.case_id)


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
    line_colour: str = "",
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
        line_colour=line_colour,
    )


def build_wtg_pq_bundles(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    labels: dict[str, str],
    show_qmin: bool = True,
    show_qmax: bool = True,
) -> tuple[tuple[CurveBundle, ...], tuple[ValidationIssue, ...]]:
    bundles: list[CurveBundle] = []
    issues: list[ValidationIssue] = []
    for case in sorted(cases, key=case_sort_key):
        for object_name in sorted(selected_objects, key=natural_key):
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
                )
            ]
            for role, enabled, name, dash in (
                ("qmin", show_qmin, "Qmin capability boundary", "dash"),
                ("qmax", show_qmax, "Qmax capability boundary", "dot"),
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
                        dash=dash,
                        line_colour="#687386",
                    )
                )
            bundles.append(CurveBundle(object_name, case, tuple(curves)))
    return tuple(bundles), tuple(issues)


def build_wtg_voltage_bundles(
    cases: Sequence[CaseData], selected_objects: Sequence[str], labels: dict[str, str]
) -> tuple[tuple[CurveBundle, ...], tuple[ValidationIssue, ...]]:
    bundles: list[CurveBundle] = []
    issues: list[ValidationIssue] = []
    for case in sorted(cases, key=case_sort_key):
        for object_name in sorted(selected_objects, key=natural_key):
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
) -> tuple[tuple[CurveBundle, ...], tuple[ValidationIssue, ...]]:
    bundles: list[CurveBundle] = []
    issues: list[ValidationIssue] = []
    for case in sorted(cases, key=case_sort_key):
        x_channel = _resolved(case, x_source, "active_interchange", issues)
        if x_channel is None:
            continue
        for object_name in sorted(selected_objects, key=natural_key):
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
                x_values=_transform(raw_x, -1.0 if x_source != "Sweep index" else 1.0),
                y_values=_transform(y_channel.numeric_values, y_factor),
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


def _auto_strategy(bundles: Sequence[CurveBundle]) -> str:
    element_count = len({bundle.element_name for bundle in bundles})
    case_count = len({bundle.case.case_id for bundle in bundles})
    if element_count == 1 and case_count > 1:
        return "By case"
    if case_count == 1 and element_count > 1:
        return "By element"
    return "By element" if element_count >= case_count else "By case"


def distribute_bundles(
    bundles: Sequence[CurveBundle], panel_count: int, strategy: str = "Auto"
) -> tuple[tuple[CurveBundle, ...], ...]:
    """Assign each complete element×case bundle once, balancing panel bundle counts."""
    ordered = sorted(bundles, key=lambda bundle: (natural_key(bundle.element_name), case_sort_key(bundle.case)))
    if not ordered:
        return ()
    panel_count = min(max(1, panel_count), len(ordered))
    chosen = _auto_strategy(ordered) if strategy == "Auto" else strategy
    if chosen not in {"By element", "By case"}:
        raise ValueError(f"Unknown bundle distribution: {strategy}")

    grouped: dict[str, list[CurveBundle]] = {}
    for bundle in ordered:
        key = bundle.element_name if chosen == "By element" else bundle.case.case_id
        grouped.setdefault(key, []).append(bundle)
    group_items = sorted(
        grouped.items(),
        key=lambda item: natural_key(item[0]) if chosen == "By element" else case_sort_key(item[1][0].case),
    )

    panels: list[list[CurveBundle]] = [[] for _ in range(panel_count)]
    for _, group in group_items:
        panel_index = min(range(panel_count), key=lambda index: (len(panels[index]), index))
        panels[panel_index].extend(group)

    # Split a group only when needed to avoid an empty panel and there are enough bundles.
    for empty_index in [index for index, panel in enumerate(panels) if not panel]:
        donors = [index for index, panel in enumerate(panels) if len(panel) > 1]
        if not donors:
            break
        donor_index = max(donors, key=lambda index: (len(panels[index]), -index))
        moved = panels[donor_index].pop()
        panels[empty_index].append(moved)

    for panel in panels:
        panel.sort(key=lambda bundle: (natural_key(bundle.element_name), case_sort_key(bundle.case)))
    return tuple(tuple(panel) for panel in panels if panel)


def _finite(values: Iterable[float | None]) -> list[float]:
    return [float(value) for value in values if value is not None and math.isfinite(float(value))]


def _expanded_range(values: Sequence[float], fraction: float = 0.04) -> tuple[float, float] | None:
    if not values:
        return None
    low, high = min(values), max(values)
    span = high - low
    pad = span * fraction if span else max(abs(high) * fraction, 0.5)
    return low - pad, high + pad


def bundle_ranges(
    bundles: Sequence[CurveBundle], reference_y: Sequence[float] = ()
) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    xs: list[float] = []
    ys: list[float] = list(reference_y)
    for bundle in bundles:
        for curve in bundle.curves:
            xs.extend(_finite(curve.x_values))
            ys.extend(_finite(curve.y_values))
    return _expanded_range(xs), _expanded_range(ys)


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
    panels = distribute_bundles(bundles, panel_count, options.distribution)
    flat_bundles = tuple(bundle for panel in panels for bundle in panel)
    shared_x, shared_y = bundle_ranges(flat_bundles, [value for value, _ in reference_y])
    x_range = options.x_range if options.x_range is not None else (None if options.independent_ranges else shared_x)
    y_range = options.y_range if options.y_range is not None else (None if options.independent_ranges else shared_y)
    height = options.height or (700 if panel_count == 1 else 520 if panel_count == 2 else 450)
    figures: list[go.Figure] = []

    for panel_index, panel in enumerate(panels, start=1):
        figure = go.Figure()
        for bundle in panel:
            for curve in bundle.curves:
                if not any(value is not None for value in curve.x_values) or not any(
                    value is not None for value in curve.y_values
                ):
                    continue
                colour = curve.line_colour or stable_case_colour(curve.case.case_id)
                name = f"{curve.element_name} | {curve.case_label}"
                if curve.series_name != "operating curve" and curve.series_name != "power factor":
                    name = f"{name} | {curve.series_name}"
                customdata = [
                    [
                        curve.case_label,
                        curve.case.filename,
                        curve.case.source_path,
                        curve.element_name,
                        " | ".join(curve.case.tokens),
                        curve.x_metric_description,
                        curve.metric_description,
                        curve.x_transform,
                        curve.y_transform,
                        curve.series_name,
                        curve.case.case_id,
                    ]
                    for _ in curve.x_values
                ]
                figure.add_trace(
                    go.Scatter(
                        x=curve.x_values,
                        y=curve.y_values,
                        customdata=customdata,
                        mode="lines+markers",
                        name=name,
                        legendgroup=f"{curve.element_name}|{curve.case.case_id}",
                        line={"color": colour, "dash": curve.dash, "width": curve.width},
                        marker={"size": 3.2, "color": colour},
                        hovertemplate=(
                            "<b>%{customdata[0]}</b><br>"
                            "Case ID: %{customdata[10]}<br>"
                            "Filename: %{customdata[1]}<br>"
                            "Source path: %{customdata[2]}<br>"
                            "Object: %{customdata[3]}<br>"
                            "All filename tokens: %{customdata[4]}<br>"
                            "X metric: %{customdata[5]}<br>"
                            "Y metric: %{customdata[6]}<br>"
                            "X transform: %{customdata[7]}<br>"
                            "Y transform: %{customdata[8]}<br>"
                            "Series: %{customdata[9]}<br>"
                            f"{curve.x_label} ({curve.x_unit or 'unitless'}): %{{x:.7g}}<br>"
                            f"{curve.y_label} ({curve.y_unit or 'unitless'}): %{{y:.7g}}"
                            "<extra></extra>"
                        ),
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
                annotation_font_color="#9d2d29",
            )
        figure.update_layout(
            title={"text": title if len(panels) == 1 else f"{title} · panel {panel_index}", "x": 0.02},
            template="plotly_white",
            height=height,
            margin={"l": 70, "r": 24, "t": 58, "b": 135},
            hovermode="closest",
            font={"color": "#263445", "family": "Arial, sans-serif", "size": 12},
            paper_bgcolor="white",
            plot_bgcolor="white",
            legend={
                "orientation": "h",
                "y": -0.26,
                "x": 0,
                "xanchor": "left",
                "yanchor": "top",
                "groupclick": "togglegroup",
                "itemclick": "toggle",
                "itemdoubleclick": "toggleothers",
                "tracegroupgap": 5,
                "maxheight": 0.26,
                "font": {"size": 10},
            },
            showlegend=True,
        )
        figure.update_xaxes(
            title_text=f"{x_title} ({panel[0].curves[0].x_unit or 'unitless'})" if panel else x_title,
            showgrid=True,
            gridcolor="#e6e9ed",
            zeroline=True,
            zerolinecolor="#b9c0c8",
            range=list(x_range) if x_range else None,
            autorange=True if x_range is None else False,
        )
        figure.update_yaxes(
            title_text=f"{y_title} ({panel[0].curves[0].y_unit or 'unitless'})" if panel else y_title,
            showgrid=True,
            gridcolor="#e6e9ed",
            zeroline=True,
            zerolinecolor="#b9c0c8",
            range=list(y_range) if y_range else None,
            autorange=True if y_range is None else False,
        )
        figures.append(figure)

    chosen = _auto_strategy(flat_bundles) if options.distribution == "Auto" and flat_bundles else options.distribution
    return PlotSet(tuple(figures), panels, tuple(bundles), (), chosen, x_range, y_range)


def build_wtg_pq_figures(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    labels: dict[str, str],
    *,
    options: PlotOptions,
    show_qmin: bool = True,
    show_qmax: bool = True,
) -> PlotSet:
    bundles, issues = build_wtg_pq_bundles(cases, selected_objects, labels, show_qmin, show_qmax)
    result = build_plot_set(
        bundles,
        title="WTG P–Q",
        x_title="Reactive power, Q",
        y_title="Active power, P",
        options=options,
    )
    return PlotSet(result.figures, result.panels, result.bundles, issues, result.distribution_used, result.x_range, result.y_range)


def build_wtg_voltage_figures(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    labels: dict[str, str],
    *,
    options: PlotOptions,
    show_references: bool = True,
    low_reference: float = 0.92,
    high_reference: float = 1.08,
) -> PlotSet:
    bundles, issues = build_wtg_voltage_bundles(cases, selected_objects, labels)
    references = ((low_reference, f"Display reference {low_reference:g} p.u."),
                  (high_reference, f"Display reference {high_reference:g} p.u.")) if show_references else ()
    result = build_plot_set(
        bundles,
        title="WTG terminal voltage",
        x_title="Active power, P",
        y_title="Terminal voltage, U",
        options=options,
        reference_y=references,
    )
    return PlotSet(result.figures, result.panels, result.bundles, issues, result.distribution_used, result.x_range, result.y_range)


def build_equipment_loading_figures(
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    x_source: str,
    labels: dict[str, str],
    *,
    options: PlotOptions,
    show_reference: bool = True,
    loading_reference: float = 100.0,
) -> PlotSet:
    bundles, issues = build_loading_bundles(cases, selected_objects, x_source, labels)
    references = ((loading_reference, f"Display reference {loading_reference:g}%"),) if show_reference else ()
    result = build_plot_set(
        bundles,
        title="Equipment loading",
        x_title=f"−{x_source} active power interchange",
        y_title="Equipment loading",
        options=options,
        reference_y=references,
    )
    return PlotSet(result.figures, result.panels, result.bundles, issues, result.distribution_used, result.x_range, result.y_range)


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
    return PlotSet(result.figures, result.panels, result.bundles, issues, result.distribution_used, result.x_range, result.y_range)


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
    return PlotSet(result.figures, result.panels, result.bundles, issues, result.distribution_used, result.x_range, result.y_range)


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


def clipped_values(
    bundles: Sequence[CurveBundle],
    x_range: tuple[float, float] | None,
    y_range: tuple[float, float] | None,
) -> tuple[int, int]:
    x_clipped = y_clipped = 0
    for bundle in bundles:
        for curve in bundle.curves:
            if x_range:
                x_clipped += sum(1 for value in _finite(curve.x_values) if value < x_range[0] or value > x_range[1])
            if y_range:
                y_clipped += sum(1 for value in _finite(curve.y_values) if value < y_range[0] or value > y_range[1])
    return x_clipped, y_clipped

